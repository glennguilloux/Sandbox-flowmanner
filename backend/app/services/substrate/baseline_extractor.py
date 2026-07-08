"""BaselineExtractor — auto-extract expected behaviors from a successful run (Phase 0.3).

The fastest path to populating expected_behaviors: analyze a completed
mission's event log and generate suggested assertions with headroom.

Item #9 enhancements:
- Tighter default headrooms (cost: 1.15x, latency: 1.5x)
- Required ordering edges for causal tool dependencies
- Forbidden tools set for dangerous/unexpected tools
- Baseline version metadata for auto-invalidation
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
        cost_headroom: float = 1.15,
        latency_headroom: float = 1.5,
        model_id: str = "",
        pricing_table_version: str = "",
        template_version: str = "",
        forbidden_tools: list[str] | None = None,
        required_edges: list[list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Analyze a successful run and generate expected_behaviors.

        Args:
            db: Async database session
            run_id: UUID string identifying the execution run
            cost_headroom: Multiplier for cost/token ceiling (default 1.15x)
            latency_headroom: Multiplier for latency ceiling (default 1.5x)
            model_id: Model used for this run (for baseline versioning)
            pricing_table_version: Version hash of the pricing table
            template_version: Version hash of the template/prompt
            forbidden_tools: Tools that must not appear in any replay
            required_edges: Ordering constraints [[before, after], ...]

        Returns:
            List of expected behavior dicts ready to store in a template
        """
        state = await self._replay_engine.rebuild_state(db, run_id)
        events = await self._event_log.get_events(db, run_id)

        behaviors: list[dict[str, Any]] = []

        # 0. Baseline version metadata (Item #9)
        if model_id and pricing_table_version and template_version:
            behaviors.append(
                {
                    "type": "baseline_version",
                    "model_id": model_id,
                    "pricing_table_version": pricing_table_version,
                    "template_version": template_version,
                }
            )

        # 1. Extract tool sequence with partial order support
        tool_events = [e for e in events if e.type == SubstrateEventType.TOOL_CALL]
        tool_names = [e.payload.get("tool_name", "") for e in tool_events]
        call_counts = Counter(tool_names)

        if tool_names:
            tool_seq: dict[str, Any] = {
                "type": "tool_sequence",
                "expected_tools": list(dict.fromkeys(tool_names)),
                "order": "subset",
                "max_calls_per_tool": {name: count + 1 for name, count in call_counts.items()},
            }
            # Item #9: add forbidden and required edges if provided
            if forbidden_tools:
                tool_seq["forbidden_tools"] = forbidden_tools
            if required_edges:
                tool_seq["required_edges"] = required_edges
            behaviors.append(tool_seq)

        # 2. Cost ceiling with token ceiling (Item #9)
        actual_cost = state.total_cost_usd or 0.0
        try:
            actual_tokens = int(state.total_tokens or 0)
        except (TypeError, ValueError):
            actual_tokens = 0
        cost_behavior: dict[str, Any] = {
            "type": "cost_ceiling",
            "max_cost_usd": round(actual_cost * cost_headroom, 4),
            "warn_at_pct": 80,
        }
        # Token ceiling (1.15x) for dynamic pricing recomputation
        if actual_tokens > 0:
            cost_behavior["max_tokens"] = int(actual_tokens * cost_headroom)
            cost_behavior["model_id"] = model_id
        behaviors.append(cost_behavior)

        # 3. Latency (actual duration × headroom)
        duration = 0.0
        if state.started_at and state.last_event_at:
            duration = (state.last_event_at - state.started_at).total_seconds()
        behaviors.append(
            {
                "type": "latency",
                "max_duration_seconds": (int(duration * latency_headroom) if duration > 0 else 300),
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
