"""LeaseManager — high-level lease lifecycle for UnifiedExecutor.

Wraps the chunk-1 lease primitives (``try_claim_lease``, ``renew_lease``,
``release_lease``) into a stateful object that the executor can use:

- **claim** at the start of ``execute()``
- **heartbeat_loop** running in the background to renew the lease
- **lease_lost** flag checked by the executor mid-run
- **release** on every return path (success / exception / abort)

The heartbeat interval is ``ttl_seconds / 3`` by default, which is the
standard ratio: fast enough to renew before expiry, slow enough to avoid
wasted DB traffic.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import TYPE_CHECKING

from app.services.substrate.leases import (
    get_active_lease,
    release_lease,
    renew_lease,
    try_claim_lease,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.substrate.event_log import EventLog

logger = logging.getLogger(__name__)


def _default_worker_id() -> str:
    """Generate a worker ID from hostname + PID."""
    return f"{socket.gethostname()}-{os.getpid()}"


class LeaseManager:
    """Stateful lease manager for a single executor run.

    Usage::

        lm = LeaseManager()
        claimed = await lm.claim(run_id, db)
        if not claimed:
            # another worker holds the lease — don't re-execute
            ...
        # spawn heartbeat
        stop = asyncio.Event()
        task = asyncio.create_task(lm.heartbeat_loop(db, stop))
        try:
            ...  # execute
        finally:
            stop.set()
            await task
            await lm.release(db, reason="completed")
    """

    def __init__(
        self,
        worker_id: str | None = None,
        ttl_seconds: int = 300,
        heartbeat_interval_seconds: int | None = None,
        event_log: EventLog | None = None,
    ) -> None:
        self._worker_id = worker_id or _default_worker_id()
        self._ttl_seconds = ttl_seconds
        self._heartbeat_interval = heartbeat_interval_seconds or max(ttl_seconds // 3, 10)
        self._run_id: str | None = None
        self._lease_lost = False
        self._renew_count = 0
        self._event_log: EventLog | None = event_log

    @property
    def renew_count(self) -> int:
        """Number of successful renewals since the last claim."""
        return self._renew_count

    # ── Public properties ───────────────────────────────────────────

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def run_id(self) -> str | None:
        return self._run_id

    @property
    def lease_lost(self) -> bool:
        """``True`` if the heartbeat detected that another worker stole
        the lease.  The executor should abort the run when this is set."""
        return self._lease_lost

    # ── Public methods ──────────────────────────────────────────────

    async def claim(self, run_id: str, db: AsyncSession) -> bool:
        """Attempt to claim a lease for *run_id*.

        Returns ``True`` if the claim succeeded (caller now holds the
        lease).  Returns ``False`` if another worker already holds a
        valid lease.
        """
        self._run_id = run_id
        self._lease_lost = False
        ok = await try_claim_lease(db, self._worker_id, run_id, self._ttl_seconds)
        if ok:
            logger.info(
                "Lease claimed: worker=%s run=%s ttl=%ds",
                self._worker_id,
                run_id,
                self._ttl_seconds,
            )
        else:
            logger.info(
                "Lease claim failed (already held): worker=%s run=%s",
                self._worker_id,
                run_id,
            )
        return ok

    async def renew(self, db: AsyncSession) -> bool:
        """Renew the lease.  Returns ``False`` if the lease was lost."""
        if self._run_id is None:
            return False
        ok = await renew_lease(db, self._worker_id, self._run_id, self._ttl_seconds)
        if not ok:
            logger.warning(
                "Lease renewal failed (lost): worker=%s run=%s",
                self._worker_id,
                self._run_id,
            )
            self._lease_lost = True
        return ok

    async def release(self, db: AsyncSession, reason: str = "completed") -> None:
        """Release the lease.  Idempotent — safe to call multiple times."""
        if self._run_id is None:
            return
        await release_lease(db, self._worker_id, self._run_id)
        logger.info(
            "Lease released: worker=%s run=%s reason=%s",
            self._worker_id,
            self._run_id,
            reason,
        )

    async def get_existing_lease(self, db: AsyncSession, run_id: str):
        """Check if another worker holds a valid lease for *run_id*.

        Returns a ``LeaseRecord`` if held by *another* worker, or
        ``None`` if no active lease exists (or the caller holds it).
        """
        from app.services.substrate.leases import LeaseRecord

        lease = await get_active_lease(db, run_id)
        if lease is not None and lease.worker_id != self._worker_id:
            return lease
        return None

    async def heartbeat_loop(
        self,
        db: AsyncSession,
        stop_event: asyncio.Event,
    ) -> None:
        """Background heartbeat that renews the lease periodically.

        Runs until *stop_event* is set or the lease is lost.  On lease
        loss, sets ``self._lease_lost = True`` so the executor can react.
        """
        if self._run_id is None:
            logger.error("heartbeat_loop called with no active run_id")
            return

        logger.debug(
            "Heartbeat started: worker=%s run=%s interval=%ds",
            self._worker_id,
            self._run_id,
            self._heartbeat_interval,
        )

        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._heartbeat_interval)
                # stop_event was set — exit cleanly
                break
            except TimeoutError:
                # Interval elapsed — renew the lease
                ok = await self.renew(db)
                if not ok:
                    self._lease_lost = True
                    logger.warning(
                        "Heartbeat detected lost lease: worker=%s run=%s",
                        self._worker_id,
                        self._run_id,
                    )
                    return
                else:
                    self._renew_count += 1
                    logger.debug(
                        "Lease renewed: worker=%s run=%s count=%d",
                        self._worker_id,
                        self._run_id,
                        self._renew_count,
                    )
                    # Emit run.lease.renewed event
                    try:
                        from app.models.substrate_models import SubstrateEventType

                        await self._event_log.append(
                            db,
                            self._run_id,
                            [
                                {
                                    "type": SubstrateEventType.LEASE_RENEWED,
                                    "payload": {
                                        "worker_id": self._worker_id,
                                        "run_id": self._run_id,
                                        "renewed_count": self._renew_count,
                                        "ttl_seconds": self._ttl_seconds,
                                    },
                                    "actor": "lease_heartbeat",
                                }
                            ],
                        )
                    except Exception as exc:
                        logger.debug("Lease renewed event skipped: %s", exc)

        logger.debug(
            "Heartbeat stopped: worker=%s run=%s",
            self._worker_id,
            self._run_id,
        )
