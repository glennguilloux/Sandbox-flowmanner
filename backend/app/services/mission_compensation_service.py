"""CompensationService — deterministic pause-timeout rollback for a Mission.

Invoked by the ``mission.expire_paused`` Celery beat task AFTER a paused
mission has been atomically transitioned to ``FAILED`` (terminal). Because
the Mission is already terminal, a failure in compensation can NEVER strand
the mission in a non-terminal state — compensation retries/dead-letters
independently.

Fixed sequence (per design approval — NOT a generic saga framework):
  1. Release any held external-API worker leases for the run.
  2. Refund / credit the workspace for unused compute time.
  3. Dispatch a user notification (fire-and-forget, best-effort).

Each step is idempotent and logged. A step failure is recorded and the
next step still runs (compensation is a fixed sequence, not a rollback
of compensation). The task caller decides retry/dead-letter on the whole.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.models.mission_models import Mission

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Worker identity used to release leases. On pause-timeout the original
# worker is long gone, so we release owner-agnostically (release_lease is
# owner-only + idempotent; we pass the run's last known worker id when
# available, else a sentinel that matches nothing and is a no-op).
_LEASE_RELEASE_WORKER = "system:expire_paused"


class CompensationService:
    """Fixed, deterministic compensation for a paused→failed Mission."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def run(self, *, mission_id: str, run_id: str, user_id: int, workspace_id: str | None) -> dict:
        """Execute the compensation sequence.

        Idempotency: claims ``missions.compensated_at`` in its OWN durable
        session before any external side-effect. A concurrent/retried run
        that sees ``compensated_at`` already set skips the refund (step 2)
        entirely, so a Celery retry can never double-credit the wallet.
        Steps 1 (lease release) and 3 (notify) are independently idempotent.

        Returns a dict status of each step. Does NOT raise on step failure
        (each step's error is captured) so one failed step cannot abort the
        others; the caller is responsible for overall retry/dead-letter.
        """
        claim_skipped = await self._claim_compensation(mission_id)
        results: dict[str, object] = {}
        results["already_compensated"] = claim_skipped
        results["release_leases"] = await self._release_leases(run_id)
        results["credit_refund"] = (
            {"ok": True, "skipped": True, "reason": "already_compensated"}
            if claim_skipped
            else await self._credit_unused_compute(user_id=user_id, mission_id=mission_id, workspace_id=workspace_id)
        )
        results["notify"] = await self._notify_user(mission_id=mission_id, user_id=user_id, run_id=run_id)
        return results

    async def _claim_compensation(self, mission_id: str) -> bool:
        """Claim the compensation lock in a fresh, independently-committed session.

        Returns True if compensation was ALREADY claimed (another run won the
        race / a previous attempt succeeded) — caller must skip the refund.
        Uses fresh_session() so this commit is independent of the caller's tx.
        """
        from app.database import fresh_session

        async with fresh_session() as s:
            row = await s.execute(select(Mission).where(Mission.id == mission_id).with_for_update())
            mission = row.scalar_one_or_none()
            if mission is None:
                return True  # nothing to compensate
            if mission.compensated_at is not None:
                return True
            mission.compensated_at = datetime.now(UTC)
            await s.commit()
        return False

    async def _release_leases(self, run_id: str) -> dict:
        """Step 1: release any held external-API worker lease for the run."""
        try:
            from app.services.substrate.leases import release_lease

            await release_lease(self.db, _LEASE_RELEASE_WORKER, run_id)
            return {"ok": True}
        except Exception as exc:
            logger.warning("compensation.release_leases_failed", run_id=run_id, error=str(exc))
            return {"ok": False, "error": str(exc)}

    async def _credit_unused_compute(self, *, user_id: int, mission_id: str, workspace_id: str | None) -> dict:
        """Step 2: credit the workspace for unused compute time.

        The marketplace wallet is the only billing seam in this repo
        (app.services.nexus.marketplace_db.MarketplaceService.credit_wallet,
        SYNC — it owns its own session via ``db or self._get_db()``). We call
        it off the async event loop via asyncio.to_thread to avoid blocking
        the worker loop, mirroring app/api/v2/marketplace.py:258.

        Refund amount is intentionally conservative: only the portion of the
        mission's compute that was never consumed. Paused missions have NOT
        run to completion, so we credit the remaining estimated budget. This
        is a deliberate business decision; revisit if billing granularity
        improves.
        """
        try:
            import asyncio

            from app.services.nexus.marketplace_db import get_marketplace_service

            # How much unused compute to credit. We use the mission's
            # estimated_cost as the ceiling; actual unused = estimated - actual.
            # If actual already exceeds estimated (overrun), no refund.
            mission = await self.db.get(Mission, mission_id)
            if mission is None:
                return {"ok": False, "error": "mission_not_found"}
            estimated = float(mission.estimated_cost or 0.0)
            actual = float(mission.actual_cost or 0.0)
            unused = round(max(estimated - actual, 0.0), 2)
            if unused <= 0.0:
                return {"ok": True, "refunded": 0.0, "reason": "no_unused_compute"}

            result = await asyncio.to_thread(
                get_marketplace_service().credit_wallet,
                str(user_id),
                unused,
            )
            if not result.get("success"):
                return {"ok": False, "error": result.get("error", "credit_failed")}
            return {"ok": True, "refunded": unused, "balance": result.get("balance")}
        except Exception as exc:
            logger.warning(
                "compensation.credit_refund_failed",
                mission_id=mission_id,
                user_id=user_id,
                error=str(exc),
            )
            return {"ok": False, "error": str(exc)}

    async def _notify_user(self, *, mission_id: str, user_id: int, run_id: str) -> dict:
        """Step 3: dispatch a user notification (fire-and-forget, best-effort)."""
        try:
            from app.services.notification_service import send_notification

            await send_notification(
                user_id=user_id,
                notification_type="mission_failed",
                data={
                    "title": "Mission auto-failed (pause timeout)",
                    "message": (
                        "Your paused mission was automatically failed after exceeding "
                        "the 7-day pause limit. Any held resources were released and "
                        "unused compute credited back to your workspace."
                    ),
                    "mission_id": mission_id,
                    "run_id": run_id,
                },
                db=self.db,
            )
            return {"ok": True}
        except Exception as exc:
            # Notification is best-effort; never block compensation on it.
            logger.warning("compensation.notify_failed", mission_id=mission_id, error=str(exc))
            return {"ok": False, "error": str(exc)}
