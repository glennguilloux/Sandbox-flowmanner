"""Worker lease service — claim / release / renew / query for execution runs.

Provides durable async lease primitives backed by the
``substrate_worker_leases`` table (migration ``worker_leases_001``).

Design contract:
- All functions accept ``AsyncSession`` and **never commit** — the caller
  owns the transaction boundary.
- ``try_claim_lease`` uses ``ON CONFLICT (run_id) DO UPDATE`` with a
  ``WHERE expires_at < now()`` guard so only expired leases are reclaimable.
- Duplicate claims by the *same* worker are idempotent (returns True).
- ``release_lease`` is owner-only and idempotent.
- ``renew_lease`` extends ``expires_at`` only for the current owner.

This module is deliberately small: no heartbeat loop, no stale-reclaimer,
no Celery integration, no HTTP surface.  Those are deferred to later chunks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Public model ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LeaseRecord:
    """Immutable snapshot of a worker lease row."""

    id: int
    worker_id: str
    run_id: str
    acquired_at: datetime
    expires_at: datetime
    renewed_count: int
    generation: int


# ── Lease operations ───────────────────────────────────────────────


async def try_claim_lease(
    db: AsyncSession,
    worker_id: str,
    run_id: str,
    ttl_seconds: int = 300,
) -> bool:
    """Attempt to acquire (or reclaim) a lease for *run_id*.

    Returns ``True`` when the caller now holds an active lease.
    Returns ``False`` when another worker already holds a non-expired lease.

    Duplicate claims by the **same** worker for the **same** run are
    idempotent — the existing lease is left untouched and ``True`` is
    returned.

    The claim uses an ``ON CONFLICT … DO UPDATE`` so that concurrent
    callers race at the SQL level; the ``WHERE expires_at < now()``
    guard ensures only expired leases are reclaimable.
    """
    # Fast path: check if this exact worker already holds an active lease.
    # This avoids an unnecessary upsert and makes same-worker idempotency
    # work without relying on RETURNING semantics.
    existing = await get_active_lease(db, run_id)
    if existing is not None and existing.worker_id == worker_id:
        return True

    # Upsert: insert a new lease, or reclaim an expired one.
    # The RETURNING clause returns the generation ONLY when a row was
    # actually inserted or updated (i.e. the conflict UPDATE succeeded).
    # If the UPDATE WHERE clause fails (lease is still active with another
    # worker), no row is returned → claim failure.
    result = await db.execute(
        text(
            """
            INSERT INTO substrate_worker_leases
                (worker_id, run_id, acquired_at, expires_at)
            VALUES
                (:worker_id, :run_id, now(), now() + make_interval(secs := :ttl))
            ON CONFLICT (run_id) DO UPDATE
                SET worker_id    = :worker_id,
                    acquired_at  = now(),
                    expires_at   = now() + make_interval(secs := :ttl),
                    renewed_count = 0,
                    generation   = substrate_worker_leases.generation + 1
                WHERE substrate_worker_leases.expires_at < now()
            RETURNING generation
            """
        ),
        {"worker_id": worker_id, "run_id": run_id, "ttl": ttl_seconds},
    )
    row = result.fetchone()
    return row is not None


async def get_active_lease(
    db: AsyncSession,
    run_id: str,
) -> LeaseRecord | None:
    """Return the active lease for *run_id*, or ``None`` if missing / expired."""
    result = await db.execute(
        text(
            """
            SELECT id, worker_id, run_id, acquired_at, expires_at,
                   renewed_count, generation
            FROM substrate_worker_leases
            WHERE run_id = :run_id
              AND expires_at > now()
            """
        ),
        {"run_id": run_id},
    )
    row = result.fetchone()
    if row is None:
        return None
    return LeaseRecord(
        id=row.id,
        worker_id=row.worker_id,
        run_id=row.run_id,
        acquired_at=row.acquired_at,
        expires_at=row.expires_at,
        renewed_count=row.renewed_count,
        generation=row.generation,
    )


async def release_lease(
    db: AsyncSession,
    worker_id: str,
    run_id: str,
) -> None:
    """Release the lease for *run_id* if held by *worker_id*.

    Idempotent and owner-only: if the lease is held by another worker
    or does not exist, this is a silent no-op.
    """
    await db.execute(
        text(
            """
            DELETE FROM substrate_worker_leases
            WHERE run_id = :run_id
              AND worker_id = :worker_id
              AND expires_at > now()
            """
        ),
        {"worker_id": worker_id, "run_id": run_id},
    )


async def renew_lease(
    db: AsyncSession,
    worker_id: str,
    run_id: str,
    ttl_seconds: int = 300,
) -> bool:
    """Extend the lease expiry for *run_id* by *ttl_seconds* from now.

    Returns ``True`` if the lease was renewed (caller is the owner and
    the lease is active).  Returns ``False`` if the lease is missing,
    expired, or held by another worker.
    """
    result = await db.execute(
        text(
            """
            UPDATE substrate_worker_leases
            SET expires_at     = now() + make_interval(secs := :ttl),
                renewed_count  = renewed_count + 1
            WHERE run_id = :run_id
              AND worker_id = :worker_id
              AND expires_at > now()
            RETURNING id
            """
        ),
        {"worker_id": worker_id, "run_id": run_id, "ttl": ttl_seconds},
    )
    row = result.fetchone()
    return row is not None
