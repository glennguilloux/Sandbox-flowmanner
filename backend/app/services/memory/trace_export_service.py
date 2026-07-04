"""Trace Export Service — collects episode traces for meta-LLM review (AutoMem Phase 2).

Gathers memory_action_events and substrate_events for recent missions
into a structured format that the meta-LLM can review.

Uses existing infrastructure:
- MemoryActionService.get_episode_traces() for memory actions
- SubstrateEvent queries for mission events
- MemoryActionService.score_episode() for proficiency metrics
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import func, select

from app.models.memory_action_models import MemoryActionEvent
from app.models.mission_models import Mission
from app.models.substrate_models import SubstrateEvent
from app.services.memory_action_service import MemoryActionService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Maximum traces to export per review cycle
DEFAULT_TRACE_LIMIT = 20
MAX_SUBSTRATE_EVENTS_PER_MISSION = 50


class TraceExportService:
    """Collects episode traces for meta-LLM review.

    Usage::

        service = TraceExportService(db)
        traces = await service.export_episode_traces(
            workspace_id="...",
            limit=20,
        )
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._action_service = MemoryActionService(db)

    async def export_episode_traces(
        self,
        *,
        workspace_id: str | None = None,
        user_id: int | None = None,
        limit: int = DEFAULT_TRACE_LIMIT,
    ) -> list[dict[str, Any]]:
        """Export recent mission traces with memory actions and outcomes.

        Returns list of dicts with mission context, memory actions,
        substrate events, and memory proficiency scores.

        Only includes missions that have at least one memory action event
        (so the meta-LLM has signal to work with).
        """
        # Find missions that have memory action events
        mission_ids = await self._find_missions_with_actions(
            workspace_id=workspace_id,
            user_id=user_id,
            limit=limit,
        )

        if not mission_ids:
            logger.debug("No missions with memory actions found for export")
            return []

        traces: list[dict[str, Any]] = []
        for mid in mission_ids:
            trace = await self._build_trace(mid)
            if trace is not None:
                traces.append(trace)

        logger.info(
            "trace_export_completed",
            mission_count=len(traces),
            workspace_id=workspace_id,
        )
        return traces

    async def _find_missions_with_actions(
        self,
        *,
        workspace_id: str | None,
        user_id: int | None,
        limit: int,
    ) -> list[str]:
        """Find mission IDs that have memory action events."""
        stmt = select(MemoryActionEvent.mission_id).where(MemoryActionEvent.mission_id.isnot(None))

        if workspace_id is not None:
            stmt = stmt.where(MemoryActionEvent.workspace_id == workspace_id)
        if user_id is not None:
            stmt = stmt.where(MemoryActionEvent.user_id == user_id)

        stmt = (
            stmt.group_by(MemoryActionEvent.mission_id)
            .order_by(func.max(MemoryActionEvent.created_at).desc())
            .limit(limit)
        )

        result = await self._db.execute(stmt)
        return [str(row[0]) for row in result.all()]

    async def _build_trace(self, mission_id: str) -> dict[str, Any] | None:
        """Build a complete trace for a single mission."""
        # Get mission metadata
        mission = (await self._db.execute(select(Mission).where(Mission.id == mission_id))).scalar_one_or_none()

        if mission is None:
            return None

        # Get memory actions
        actions = await self._action_service.get_episode_traces(mission_id)
        action_dicts = [
            {
                "action_type": a.action_type,
                "action_input": a.action_input,
                "action_result": a.action_result,
                "latency_ms": a.action_latency_ms,
                "success": a.action_success,
                "agent_confidence": a.agent_confidence,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in actions
        ]

        # Get substrate events (bounded)
        substrate_events = await self._get_substrate_events(mission_id)

        # Get memory proficiency score
        proficiency = await self._action_service.score_episode(mission_id)

        # Determine success from mission status
        status_val = mission.status.value if hasattr(mission.status, "value") else str(mission.status)
        success = status_val in ("completed",)

        return {
            "mission_id": mission_id,
            "title": mission.title or "",
            "description": (mission.description or "")[:500],
            "success": success,
            "status": status_val,
            "error_message": mission.error_message,
            "memory_actions": action_dicts,
            "substrate_events": substrate_events,
            "memory_proficiency": proficiency,
            "started_at": mission.started_at.isoformat() if mission.started_at else None,
            "completed_at": mission.completed_at.isoformat() if mission.completed_at else None,
        }

    async def _get_substrate_events(self, mission_id: str) -> list[dict[str, Any]]:
        """Fetch bounded substrate events for a mission."""
        stmt = (
            select(SubstrateEvent)
            .where(SubstrateEvent.mission_id == mission_id)
            .order_by(SubstrateEvent.sequence.asc())
            .limit(MAX_SUBSTRATE_EVENTS_PER_MISSION)
        )
        result = await self._db.execute(stmt)
        events = result.scalars().all()

        return [
            {
                "type": e.type,
                "payload": e.payload,
                "actor": e.actor,
                "sequence": e.sequence,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in events
        ]
