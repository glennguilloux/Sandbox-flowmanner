"""Stale-lease reclaimer — scans for expired worker leases and reclaims them.

When a worker crashes without calling ``release_lease`` (OOM kill, segfault,
network partition, ``kill -9``), the lease sits in the table until its TTL
expires.  The reclaimer periodically scans for expired leases, claims them
with a very short TTL, immediately releases them, and emits a
``LEASE_RELEASED`` event with ``reason="reclaimed"`` so the audit trail
reflects what happened.

Design notes:
- Calls chunk-1 primitives directly (not LeaseManager) because the reclaimer
  has a different lifecycle: one-shot claim+release per expired lease, no
  heartbeat.
- The reclaimer runs as a per-process background loop inside the existing
  Celery worker, not as a Celery beat task (beat is for scheduled one-shots;
  this is a continuous loop).
- All exceptions are caught per-iteration so one bad scan never kills the loop.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import os
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.services.substrate.leases import (
    LeaseRecord,
    release_lease,
    try_claim_lease,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.substrate.event_log import EventLog

logger = logging.getLogger(__name__)


# ── Scan primitives ────────────────────────────────────────────────


async def find_expired_leases(
    db: AsyncSession,
    limit: int = 100,
) -> list[LeaseRecord]:
    """Return expired leases ordered by ``expires_at ASC`` (oldest first).

    Only returns leases where ``expires_at < now()``, capped at *limit*
    rows to avoid blowing memory on a long backlog.
    """
    result = await db.execute(
        text(
            """
            SELECT id, worker_id, run_id, acquired_at, expires_at,
                   renewed_count, generation
            FROM substrate_worker_leases
            WHERE expires_at < now()
            ORDER BY expires_at ASC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    rows = result.fetchall()
    return [
        LeaseRecord(
            id=row.id,
            worker_id=row.worker_id,
            run_id=row.run_id,
            acquired_at=row.acquired_at,
            expires_at=row.expires_at,
            renewed_count=row.renewed_count,
            generation=row.generation,
        )
        for row in rows
    ]


async def reclaim_one(
    db: AsyncSession,
    lease: LeaseRecord,
    reclaimer_worker_id: str,
    event_log: EventLog | None = None,
) -> bool:
    """Reclaim a single expired lease.

    Claims the lease with a very short TTL (so we own it), then immediately
    releases it and emits a ``LEASE_RELEASED`` event with
    ``reason="reclaimed"``.

    Returns ``True`` if the lease was reclaimed, ``False`` if another process
    beat us to it (or the lease was already released).  Idempotent — safe to
    call on a lease that was already cleaned up.
    """
    # Claim with a short TTL — the ON CONFLICT ... WHERE expires_at < now()
    # guard ensures we only reclaim truly expired leases.
    claimed = await try_claim_lease(
        db, reclaimer_worker_id, lease.run_id, ttl_seconds=1
    )

    if not claimed:
        # Another process reclaimed or re-created the lease first.
        return False

    # Release the lease (the reclaimer has no use for it).
    await release_lease(db, reclaimer_worker_id, lease.run_id)

    # Emit a LEASE_RELEASED event with audit metadata.
    try:
        from app.models.substrate_models import SubstrateEventType
        from app.services.substrate.event_log import get_event_log

        el = event_log or get_event_log()
        await el.append(
            db,
            lease.run_id,
            [
                {
                    "type": SubstrateEventType.LEASE_RELEASED,
                    "payload": {
                        "worker_id": reclaimer_worker_id,
                        "run_id": lease.run_id,
                        "reason": "reclaimed",
                        "previous_worker_id": lease.worker_id,
                        "previous_renewed_count": lease.renewed_count,
                    },
                    "actor": "lease_reclaimer",
                }
            ],
        )
    except Exception as exc:
        # Event emission failure must not crash the reclaimer.
        logger.debug("reclaim_one: event skipped for run=%s: %s", lease.run_id, exc)

    logger.info(
        "Lease reclaimed: run=%s previous_worker=%s renewed_count=%d",
        lease.run_id,
        lease.worker_id,
        lease.renewed_count,
    )
    return True


# ── Reclaimer loop ─────────────────────────────────────────────────


class LeaseReclaimer:
    """Background loop that periodically scans for and reclaims expired leases.

    Usage::

        reclaimer = LeaseReclaimer()
        stop = asyncio.Event()
        await reclaimer.run_loop(stop)   # blocks until stop is set

    The reclaimer is designed to run in its own asyncio event loop (e.g. in a
    background thread inside the Celery worker process).  It does NOT use the
    chunk-2 LeaseManager — it calls chunk-1 primitives directly because it has
    a different lifecycle (one-shot claim+release per expired lease, no
    heartbeat).
    """

    def __init__(
        self,
        worker_id: str | None = None,
        scan_interval_seconds: int = 60,
        batch_size: int = 100,
    ) -> None:
        self._worker_id = worker_id or (
            f"reclaimer-{socket.gethostname()}-{os.getpid()}"
        )
        self._scan_interval = scan_interval_seconds
        self._batch_size = batch_size

    @property
    def worker_id(self) -> str:
        return self._worker_id

    async def run_loop(self, stop_event: asyncio.Event) -> None:
        """Run the reclaimer scan loop until *stop_event* is set.

        Each iteration: wait for *scan_interval_seconds* (or until the stop
        event fires), then run one scan.  All exceptions are caught per
        iteration — the loop never crashes.
        """
        logger.info(
            "LeaseReclaimer started: worker=%s interval=%ds batch=%d",
            self._worker_id,
            self._scan_interval,
            self._batch_size,
        )

        while not stop_event.is_set():
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=self._scan_interval
                )
                # stop_event was set — exit cleanly.
                break
            except asyncio.TimeoutError:
                # Interval elapsed — run a scan.
                pass

            try:
                reclaimed = await self._scan_once()
                logger.debug("LeaseReclaimer scan: %d reclaimed", reclaimed)
            except Exception as exc:
                logger.warning("LeaseReclaimer scan error: %s", exc)
                # Continue — next iteration will retry.

        logger.info("LeaseReclaimer stopped: worker=%s", self._worker_id)

    async def _scan_once(self) -> int:
        """Run a single scan-and-reclaim pass.  Returns the count reclaimed."""
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            expired = await find_expired_leases(db, limit=self._batch_size)
            if not expired:
                return 0

            reclaimed = 0
            for lease in expired:
                ok = await reclaim_one(db, lease, self._worker_id)
                if ok:
                    reclaimed += 1

            await db.commit()
            return reclaimed


# ── Module-level reclaimer lifecycle (used by celery_app.py) ───────

_reclaimer_stop: asyncio.Event | None = None
_reclaimer_thread: object | None = None  # threading.Thread | None


def start_reclaimer() -> None:
    """Start the reclaimer in a background thread (called on worker_ready).

    Each Celery worker process gets its own reclaimer instance.  The reclaimer
    runs in a daemon thread with its own asyncio event loop so it does not
    interfere with Celery's own event loop.
    """
    global _reclaimer_stop, _reclaimer_thread

    import threading

    if _reclaimer_thread is not None:
        return  # Already running.

    _reclaimer_stop = asyncio.Event()

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            reclaimer = LeaseReclaimer()
            loop.run_until_complete(reclaimer.run_loop(_reclaimer_stop))
        finally:
            loop.close()

    _reclaimer_thread = threading.Thread(
        target=_run, name="lease-reclaimer", daemon=True
    )
    _reclaimer_thread.start()
    logger.info("LeaseReclaimer background thread started")


def stop_reclaimer() -> None:
    """Signal the reclaimer to stop and wait for it to finish (worker_shutdown).

    Idempotent — safe to call multiple times.
    """
    global _reclaimer_stop, _reclaimer_thread

    if _reclaimer_stop is None or _reclaimer_thread is None:
        return

    # Signal the reclaimer to stop.  The Event is set from the main thread;
    # the reclaimer's asyncio loop will see it on its next wait() cycle.
    _reclaimer_stop.set()

    thread = _reclaimer_thread
    _reclaimer_thread = None
    _reclaimer_stop = None

    thread.join(timeout=10)  # type: ignore[union-attr]
    logger.info("LeaseReclaimer background thread stopped")
