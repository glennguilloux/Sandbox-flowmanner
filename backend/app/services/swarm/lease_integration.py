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

    def __init__(self, db: "AsyncSession", worker_id: str = "handoff-worker"):
        self.db = db
        self._worker_id = worker_id

    async def claim_for_handoff(self, handoff_id: str, agent_id: str) -> str:
        """Claim a lease for a handoff.  Returns the synthetic run_id."""
        run_id = f"handoff-{handoff_id}"
        ok = await try_claim_lease(
            self.db,
            worker_id=self._worker_id,
            run_id=run_id,
            ttl_seconds=HANDOFF_LEASE_TTL_SECONDS,
        )
        if not ok:
            raise RuntimeError(f"Could not claim lease for handoff {handoff_id}")
        logger.info(
            "Handoff lease claimed: handoff=%s agent=%s run=%s",
            handoff_id,
            agent_id,
            run_id,
        )
        return run_id

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
        self, handoff_id: str, from_agent_id: str, to_agent_id: str
    ) -> None:
        """Transfer lease ownership during worker churn.

        Releases the old lease and immediately claims a new one for the
        new agent.  The HandoffRecord itself is unchanged.
        """
        await self.release(handoff_id)
        await self.claim_for_handoff(handoff_id, to_agent_id)
        logger.info(
            "Handoff lease transferred: handoff=%s %s → %s",
            handoff_id,
            from_agent_id,
            to_agent_id,
        )
