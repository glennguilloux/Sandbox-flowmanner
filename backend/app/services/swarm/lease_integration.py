"""Lease lifecycle integration for HandoffProtocol (Q2-Q3 Chunk 5).

Wraps chunk-1 lease primitives (``try_claim_lease``, ``renew_lease``,
``release_lease``) for handoff-specific scenarios:

- **claim_for_handoff**: Claim a new lease for a handoff packet.
- **renew**: Extend lease on heartbeat.
- **transfer**: Move a lease from one worker to another (worker churn).
- **release**: Release on completion / failure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.substrate.leases import (
    release_lease,
    renew_lease,
    try_claim_lease,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

HANDOFF_LEASE_TTL_SECONDS = 300  # 5 min default


class HandoffLeaseIntegration:
    """Handoff-specific lease lifecycle wrapper.

    Each handoff gets a synthetic ``run_id`` of the form
    ``handoff-{handoff_id}`` so that the existing lease table can
    track it without schema changes.
    """

    def __init__(self, db: AsyncSession, worker_id: str = "handoff-worker"):
        self.db = db
        self._worker_id = worker_id

    async def _claim_for_worker(self, handoff_id: str, agent_id: str, worker_id: str) -> str:
        """Internal: claim a lease for *handoff_id* under *worker_id*.

        Shared by ``claim_for_handoff`` (instance default worker) and
        ``transfer`` (explicit new worker).
        """
        run_id = f"handoff-{handoff_id}"
        ok = await try_claim_lease(
            self.db,
            worker_id=worker_id,
            run_id=run_id,
            ttl_seconds=HANDOFF_LEASE_TTL_SECONDS,
        )
        if not ok:
            raise RuntimeError(f"Could not claim lease for handoff {handoff_id}")
        logger.info(
            "Handoff lease claimed: handoff=%s agent=%s worker=%s run=%s",
            handoff_id,
            agent_id,
            worker_id,
            run_id,
        )
        return run_id

    async def claim_for_handoff(self, handoff_id: str, agent_id: str) -> str:
        """Claim a lease for a handoff.  Returns the synthetic run_id."""
        return await self._claim_for_worker(handoff_id, agent_id, self._worker_id)

    async def renew(self, handoff_id: str) -> bool:
        """Renew the lease for an in-flight handoff."""
        run_id = f"handoff-{handoff_id}"
        ok = await renew_lease(
            self.db,
            worker_id=self._worker_id,
            run_id=run_id,
            ttl_seconds=HANDOFF_LEASE_TTL_SECONDS,
        )
        if not ok:
            logger.warning("Handoff lease renewal failed: handoff=%s", handoff_id)
        return ok

    async def release(self, handoff_id: str) -> None:
        """Release the lease on completion / failure."""
        run_id = f"handoff-{handoff_id}"
        await release_lease(self.db, worker_id=self._worker_id, run_id=run_id)
        logger.info("Handoff lease released: handoff=%s", handoff_id)

    async def transfer(
        self,
        handoff_id: str,
        from_agent_id: str,
        to_agent_id: str,
        new_worker_id: str | None = None,
    ) -> None:
        """Transfer lease ownership during worker churn.

        Releases the lease held by the instance's current worker and claims
        a new lease for *new_worker_id* (if provided) — falling back to
        the instance's default worker when not.  The HandoffRecord itself
        is unchanged.

        Args:
            handoff_id: The handoff whose lease is being transferred.
            from_agent_id: The agent losing the lease (recorded in log).
            to_agent_id: The agent gaining the lease (recorded in log).
            new_worker_id: The worker_id to claim under.  If ``None``
                (default), the instance's worker_id is used (preserves
                pre-fix behavior).  Pass an explicit worker_id to actually
                transfer ownership across workers.
        """
        target_worker = new_worker_id if new_worker_id is not None else self._worker_id
        await self.release(handoff_id)
        await self._claim_for_worker(handoff_id, to_agent_id, target_worker)
        logger.info(
            "Handoff lease transferred: handoff=%s %s → %s worker=%s",
            handoff_id,
            from_agent_id,
            to_agent_id,
            target_worker,
        )
