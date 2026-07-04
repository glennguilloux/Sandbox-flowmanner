"""Memory Action Service — records and queries memory action events.

Follows the async pattern from app/services/tool_router.py:
- Constructor takes AsyncSession
- Uses select() + db.execute() + db.add() + db.flush()
- Does NOT call db.commit() (caller owns the transaction)

Every recorded action is also emitted to the substrate event log
(fire-and-forget, best-effort) for unified episode tracing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Integer, func, select

from app.models.memory_action_models import MemoryActionEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MemoryActionService:
    """Records and retrieves memory actions for episode tracing.

    Usage::

        service = MemoryActionService(db)
        event_id = await service.record_action(
            workspace_id="...",
            user_id=1,
            action_type="recall_episodic",
            action_input={"query": "..."},
            action_result={"matches": 3},
            latency_ms=45.2,
            success=True,
        )
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record_action(
        self,
        *,
        workspace_id: str,
        user_id: int,
        action_type: str,
        action_input: dict[str, Any],
        action_result: dict[str, Any],
        latency_ms: float,
        success: bool,
        mission_id: str | None = None,
        agent_confidence: float | None = None,
    ) -> str:
        """Record a memory action event.

        Inserts a row into memory_action_events and fire-and-forget emits
        a substrate event. Returns the event ID.

        Does NOT commit — caller owns the transaction.
        """
        event_id = str(uuid4())
        event = MemoryActionEvent(
            id=event_id,
            workspace_id=workspace_id,
            user_id=user_id,
            mission_id=mission_id,
            action_type=action_type,
            action_input=action_input,
            action_result=action_result,
            action_latency_ms=latency_ms,
            action_success=success,
            agent_confidence=agent_confidence,
        )
        self._db.add(event)
        await self._db.flush()

        # Fire-and-forget substrate event (best-effort)
        if mission_id:
            self._emit_substrate_event(
                mission_id=mission_id,
                event_id=event_id,
                action_type=action_type,
                success=success,
                latency_ms=latency_ms,
            )

        logger.debug(
            "memory_action_recorded event_id=%s action_type=%s success=%s latency_ms=%s",
            event_id,
            action_type,
            success,
            latency_ms,
        )
        return event_id

    async def get_episode_traces(
        self,
        mission_id: str,
    ) -> list[MemoryActionEvent]:
        """Return all memory actions for a mission, ordered by time."""
        stmt = (
            select(MemoryActionEvent)
            .where(MemoryActionEvent.mission_id == mission_id)
            .order_by(MemoryActionEvent.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def score_episode(
        self,
        mission_id: str,
    ) -> dict[str, Any]:
        """Compute memory proficiency score for an episode.

        Returns::

            {
                "total_actions": 12,
                "successful": 10,
                "failed": 2,
                "avg_latency_ms": 45.3,
                "by_type": {
                    "recall_episodic": {"count": 5, "success": 5, "avg_latency_ms": 30.1},
                    ...
                }
            }
        """
        # Total counts
        count_stmt = select(
            func.count(MemoryActionEvent.id).label("total"),
            func.sum(func.cast(MemoryActionEvent.action_success, Integer)).label("successful"),
            func.avg(MemoryActionEvent.action_latency_ms).label("avg_latency"),
        ).where(MemoryActionEvent.mission_id == mission_id)
        row = (await self._db.execute(count_stmt)).first()
        total = row.total if row else 0
        successful = int(row.successful or 0) if row else 0
        avg_latency = round(float(row.avg_latency or 0), 1) if row else 0.0

        # Per-type breakdown
        type_stmt = (
            select(
                MemoryActionEvent.action_type,
                func.count(MemoryActionEvent.id).label("count"),
                func.sum(func.cast(MemoryActionEvent.action_success, Integer)).label("success"),
                func.avg(MemoryActionEvent.action_latency_ms).label("avg_latency"),
            )
            .where(MemoryActionEvent.mission_id == mission_id)
            .group_by(MemoryActionEvent.action_type)
        )
        type_rows = (await self._db.execute(type_stmt)).all()

        by_type: dict[str, dict[str, Any]] = {}
        for tr in type_rows:
            by_type[tr.action_type] = {
                "count": tr.count,
                "success": int(tr.success or 0),
                "avg_latency_ms": round(float(tr.avg_latency or 0), 1),
            }

        return {
            "total_actions": total,
            "successful": successful,
            "failed": total - successful,
            "avg_latency_ms": avg_latency,
            "by_type": by_type,
        }

    def _emit_substrate_event(
        self,
        *,
        mission_id: str,
        event_id: str,
        action_type: str,
        success: bool,
        latency_ms: float,
    ) -> None:
        """Emit a substrate event (fire-and-forget, best-effort)."""
        try:
            import asyncio

            from app.models.substrate_models import SubstrateEventType
            from app.services.substrate.event_log import get_event_log

            async def _emit():
                try:
                    from app.database import AsyncSessionLocal

                    async with AsyncSessionLocal() as db:
                        await get_event_log().append(
                            db,
                            mission_id,
                            [
                                {
                                    "type": SubstrateEventType.MEMORY_ACTION_RECORDED,
                                    "payload": {
                                        "event_id": event_id,
                                        "action_type": action_type,
                                        "success": success,
                                        "latency_ms": latency_ms,
                                    },
                                    "actor": "memory_action_service",
                                    "mission_id": mission_id,
                                }
                            ],
                            mission_id=mission_id,
                        )
                        await db.commit()
                except Exception:
                    logger.debug("substrate_event_emit_failed", exc_info=True)

            asyncio.create_task(_emit())
        except Exception:
            logger.debug("substrate_event_schedule_failed", exc_info=True)


# ── Factory ──────────────────────────────────────────────────────────


def get_memory_action_service(db: AsyncSession) -> MemoryActionService:
    """Create a MemoryActionService bound to the given session.

    Not a singleton — each caller provides its own DB session.
    """
    return MemoryActionService(db)
