"""Episodic Memory Consolidation Worker — Q2-Q3 Chunk 2.

Event-driven worker that subscribes to mission-completed events from
the substrate event log and records compact, redacted episode records
via EpisodicMemoryService.

Extends (does not replace) the existing MemoryConsolidationWorker.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Sequence

from app.models.substrate_models import SubstrateEvent, SubstrateEventType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Qdrant collection for episodic memory
EPISODES_COLLECTION = "episodes"

# Retention policy: episodes older than this are archived
DEFAULT_RETENTION_DAYS = 90

# Cost classification thresholds
_COST_SMALL_MAX = 0.05
_COST_MEDIUM_MAX = 0.50


class EpisodicMemoryWorker:
    """Consolidates mission executions into episodic memory.

    This worker is event-driven: it processes mission.completed events
    from the substrate event log. It does NOT poll.

    Usage::

        worker = EpisodicMemoryWorker()
        await worker.process_mission_completed(db, mission_id="...", run_id="...")
    """

    async def process_mission_completed(
        self,
        db: AsyncSession,
        *,
        mission_id: str,
        run_id: str,
        workspace_id: str | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Process a mission.completed event into an episodic memory record.

        Extracts compact episode data from the event log, applies redaction,
        and stores via EpisodicMemoryService.

        Args:
            db: Async database session
            mission_id: The completed mission's UUID
            run_id: The execution run's UUID
            workspace_id: Optional workspace ID (looked up from mission if not provided)
            user_id: Optional user ID (looked up from mission if not provided)

        Returns:
            The created episode dict, or None if processing was skipped.
        """
        from sqlalchemy import select

        from app.models.mission_models import Mission
        from app.services.episodic_memory_service import get_episodic_memory_service

        service = get_episodic_memory_service()
        if service is None:
            logger.debug("Cross-mission memory disabled — skipping episode recording")
            return None

        # 1. Fetch mission metadata if workspace/user not provided
        mission = await db.get(Mission, mission_id)
        if mission is None:
            logger.warning("Mission %s not found — skipping episode recording", mission_id)
            return None

        if workspace_id is None:
            workspace_id = getattr(mission, "workspace_id", None)
        if user_id is None:
            user_id = getattr(mission, "user_id", None)

        if not workspace_id or not user_id:
            logger.warning("Mission %s missing workspace_id or user_id — skipping", mission_id)
            return None

        # 2. Fetch event log for this run
        stmt = (
            select(SubstrateEvent).where(SubstrateEvent.run_id == run_id).order_by(SubstrateEvent.sequence).limit(500)
        )
        events = (await db.execute(stmt)).scalars().all()
        if not events:
            logger.info("No events for run %s — skipping", run_id)
            return None

        # 3. Extract episode data
        outcome = self._extract_outcome(mission, events)
        cost_usd = self._extract_cost(events)
        hitl_outcome = self._extract_hitl_outcome(events)
        summary = self._build_summary(mission, events)
        step_types = self._extract_step_types(events)

        # 4. Record episode via service (handles redaction + embedding)
        episode = await service.record_episode(
            db,
            payload={
                "workspace_id": workspace_id,
                "user_id": user_id,
                "mission_id": mission_id,
                "step_type": ",".join(step_types) if step_types else "mission",
                "outcome": outcome,
                "cost_usd": cost_usd,
                "hitl_outcome": hitl_outcome,
                "summary_text": summary,
                "event_count": len(events),
            },
        )

        if episode is None:
            return None

        result = {
            "episode_id": episode.id,
            "mission_id": mission_id,
            "run_id": run_id,
            "outcome": outcome,
            "cost_bucket": episode.cost_bucket,
            "event_count": len(events),
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        logger.info(
            "Episode recorded: mission=%s outcome=%s events=%d",
            mission_id,
            outcome,
            len(events),
        )
        return result

    # ── Internal helpers ─────────────────────────────────────────

    def _extract_outcome(self, mission: Any, events: Sequence[Any]) -> str:
        """Determine mission outcome from terminal events."""
        for event in reversed(events):
            if event.type == SubstrateEventType.MISSION_COMPLETED:
                return "success"
            elif event.type == SubstrateEventType.MISSION_FAILED:
                return "failure"
            elif event.type == SubstrateEventType.MISSION_ABORTED:
                return "partial"

        # Fallback to mission status
        status = getattr(mission, "status", None)
        if status is not None:
            status_str = status if isinstance(status, str) else status.value
            if status_str in ("completed", "approved"):
                return "success"
            elif status_str in ("failed", "error"):
                return "failure"
        return "partial"

    def _extract_cost(self, events: Sequence[Any]) -> float:
        """Sum cost from task.completed events."""
        total = 0.0
        for event in events:
            if event.type == SubstrateEventType.TASK_COMPLETED:
                payload = event.payload or {}
                total += payload.get("cost_usd", 0.0)
        return total

    def _extract_hitl_outcome(self, events: Sequence[Any]) -> str | None:
        """Extract HITL outcome from human_interrupt events."""
        for event in events:
            if event.type == SubstrateEventType.HUMAN_INTERRUPT_RESOLVED:
                payload = event.payload or {}
                action = payload.get("action", "")
                if action in ("approved", "approve"):
                    return "approved"
                elif action in ("rejected", "reject"):
                    return "rejected"
        return None

    def _extract_step_types(self, events: Sequence[Any]) -> list[str]:
        """Extract unique step types from events."""
        types = set()
        for event in events:
            if event.type == SubstrateEventType.TASK_COMPLETED:
                payload = event.payload or {}
                task_type = payload.get("task_type") or payload.get("step_type")
                if task_type:
                    types.add(task_type)
            elif event.type == SubstrateEventType.TOOL_CALL:
                types.add("tool_call")
            elif event.type == SubstrateEventType.LLM_CALL:
                types.add("llm_call")
        return sorted(types)

    def _build_summary(self, mission: Any, events: Sequence[Any]) -> str:
        """Build a compact summary from mission metadata and events.

        This summary is REDACTED by the service before storage.
        """
        title = getattr(mission, "title", "Untitled") or "Untitled"
        task_count = sum(1 for e in events if e.type == SubstrateEventType.TASK_COMPLETED)
        tool_count = sum(1 for e in events if e.type == SubstrateEventType.TOOL_CALL)
        llm_count = sum(1 for e in events if e.type == SubstrateEventType.LLM_CALL)

        parts = [
            f"Mission '{title}'",
            f"{task_count} tasks completed",
        ]
        if tool_count:
            parts.append(f"{tool_count} tool calls")
        if llm_count:
            parts.append(f"{llm_count} LLM calls")

        return ", ".join(parts)


# ── Singleton ──────────────────────────────────────────────────────

_worker: EpisodicMemoryWorker | None = None


def get_episodic_memory_worker() -> EpisodicMemoryWorker:
    """Get or create the EpisodicMemoryWorker singleton."""
    global _worker
    if _worker is None:
        _worker = EpisodicMemoryWorker()
    return _worker
