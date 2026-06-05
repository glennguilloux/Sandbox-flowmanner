"""BaselineExtractor — auto-extract expected behaviors from a successful run (Phase 0.3).

The fastest path to populating expected_behaviors: analyze a completed
mission's event log and generate suggested assertions with headroom.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import TYPE_CHECKING, Any

from app.models.substrate_models import SubstrateEventType
from app.services.substrate.event_log import get_event_log
from app.services.substrate.replay_engine import get_replay_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class BaselineExtractor:
    """Extract expected behaviors from a known-good run."""

    def __init__(self):
        self._event_log = get_event_log()
        self._replay_engine = get_replay_engine()

    async def extract_from_run(
        self,
        db: AsyncSession,
        run_id: str,
        *,
        cost_headroom: float = 1.5,
        latency_headroom: float = 2.0,
    ) -> list[dict[str, Any]]:
        """Analyze a successful run and generate expected_behaviors.

        Args:
            db: Async database session
            run_id: UUID string identifying the execution run
            cost_headroom: Multiplier for cost ceiling (default 1.5x)
            latency_headroom: Multiplier for latency ceiling (default 2.0x)

        Returns:
            List of expected behavior dicts ready to store in a template
        """
        state = await self._replay_engine.rebuild_state(db, run_id)
        events = await self._event_log.get_events(db, run_id)

        behaviors: list[dict[str, Any]] = []

        # 1. Extract tool sequence
        tool_events = [e for e in events if e.type == SubstrateEventType.TOOL_CALL]
        tool_names = [e.payload.get("tool_name", "") for e in tool_events]
        call_counts = Counter(tool_names)

        if tool_names:
            behaviors.append(
                {
                    "type": "tool_sequence",
                    "expected_tools": list(
                        dict.fromkeys(tool_names)
                    ),  # preserve order, dedupe
                    "order": "subset",  # allow reordering
                    "max_calls_per_tool": {
                        name: count + 1  # allow 1 extra call as headroom
                        for name, count in call_counts.items()
                    },
                }
            )

        # 2. Cost ceiling (actual cost × headroom)
        actual_cost = state.total_cost_usd or 0.0
        behaviors.append(
            {
                "type": "cost_ceiling",
                "max_cost_usd": round(actual_cost * cost_headroom, 4),
                "warn_at_pct": 80,
            }
        )

        # 3. Latency (actual duration × headroom)
        duration = 0.0
        if state.started_at and state.last_event_at:
            duration = (state.last_event_at - state.started_at).total_seconds()
        behaviors.append(
            {
                "type": "latency",
                "max_duration_seconds": (
                    int(duration * latency_headroom) if duration > 0 else 300
                ),
                "warn_at_pct": 80,
            }
        )

        # 4. Task completion
        behaviors.append(
            {
                "type": "task_completion",
                "min_tasks_completed": len(state.completed_tasks),
                "max_tasks_failed": 0,
            }
        )

        # 5. No circuit breaker (always include)
        behaviors.append(
            {
                "type": "no_circuit_breaker",
                "description": "Circuit breaker should not trip",
            }
        )

        logger.info(
            "Extracted %d behaviors from run %s (cost=$%.4f, duration=%.0fs, %d tools)",
            len(behaviors),
            run_id,
            actual_cost,
            duration,
            len(call_counts),
        )

        return behaviors


# ── Singleton ──────────────────────────────────────────────────────

_extractor: BaselineExtractor | None = None


def get_baseline_extractor() -> BaselineExtractor:
    """Get or create the BaselineExtractor singleton."""
    global _extractor
    if _extractor is None:
        _extractor = BaselineExtractor()
    return _extractor
