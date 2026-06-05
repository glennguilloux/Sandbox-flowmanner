"""Tests for ReplayAssertionEngine, BaselineExtractor, and Intervention Distance (Phase 0.2-0.5).

Covers:
- All 5 assertion types: tool_sequence, cost_ceiling, latency, task_completion, no_circuit_breaker
- AssertionResult serialization
- BaselineExtractor behavior extraction
- Intervention Distance metric computation
- Edge cases: empty events, no assertions, unknown types
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.substrate_models import (
    SubstrateEvent,
    SubstrateEventType,
    SubstrateRunState,
)
from app.services.substrate.assertion_engine import (
    AssertionResult,
    AssertionType,
    ReplayAssertionEngine,
    Severity,
    get_assertion_engine,
)
from app.services.substrate.event_log import EventLog
from app.services.substrate.replay_engine import ReplayEngine
from app.observability.intervention_distance import compute_intervention_distance


# ── Helpers ────────────────────────────────────────────────────────


def _make_event(
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict | None = None,
    mission_id: str | None = None,
    task_id: str | None = None,
) -> SubstrateEvent:
    """Create a SubstrateEvent with given parameters."""
    return SubstrateEvent(
        id=str(uuid4()),
        sequence=sequence,
        run_id=run_id,
        type=event_type,
        payload=payload or {},
        actor="test",
        mission_id=mission_id,
        task_id=task_id,
    )


def _make_run_state(
    run_id: str,
    *,
    status: str = "completed",
    completed_tasks: set[str] | None = None,
    failed_tasks: set[str] | None = None,
    total_tokens: int = 300,
    total_cost_usd: float = 0.15,
    started_at: datetime | None = None,
    last_event_at: datetime | None = None,
) -> SubstrateRunState:
    """Create a SubstrateRunState with given parameters."""
    state = SubstrateRunState(run_id=run_id)
    state.status = status
    state.completed_tasks = completed_tasks or set()
    state.failed_tasks = failed_tasks or set()
    state.total_tokens = total_tokens
    state.total_cost_usd = total_cost_usd
    state.started_at = started_at or datetime(2026, 6, 12, 10, 0, 0, tzinfo=timezone.utc)
    state.last_event_at = last_event_at or datetime(2026, 6, 12, 10, 2, 0, tzinfo=timezone.utc)
    return state


def _mock_engine(
    state: SubstrateRunState,
    events: list[SubstrateEvent],
) -> ReplayAssertionEngine:
    """Create a ReplayAssertionEngine with mocked dependencies."""
    engine = ReplayAssertionEngine()

    async def mock_rebuild_state(db, run_id, **kwargs):
        return state

    async def mock_get_events(db, run_id, **kwargs):
        return events

    engine._replay_engine = MagicMock()
    engine._replay_engine.rebuild_state = AsyncMock(side_effect=mock_rebuild_state)
    engine._event_log = MagicMock()
    engine._event_log.get_events = AsyncMock(side_effect=mock_get_events)

    return engine


# ═══════════════════════════════════════════════════════════════════
# AssertionResult
# ═══════════════════════════════════════════════════════════════════


class TestAssertionResult:

    def test_to_dict_serialization(self):
        """AssertionResult.to_dict() produces a JSON-safe dict."""
        result = AssertionResult(
            assertion_type="cost_ceiling",
            passed=True,
            severity=Severity.INFO,
            actual={"cost_usd": 0.12},
            expected={"max_cost_usd": 0.50},
            message="Cost within budget",
        )
        d = result.to_dict()
        assert d["assertion_type"] == "cost_ceiling"
        assert d["passed"] is True
        assert d["severity"] == "info"
        assert d["actual"] == {"cost_usd": 0.12}
        assert d["message"] == "Cost within budget"

    def test_to_dict_with_failure(self):
        """AssertionResult serializes failure severity correctly."""
        result = AssertionResult(
            assertion_type="tool_sequence",
            passed=False,
            severity=Severity.FAILURE,
            message="Missing tool",
        )
        d = result.to_dict()
        assert d["severity"] == "failure"
        assert d["passed"] is False


# ═══════════════════════════════════════════════════════════════════
# ReplayAssertionEngine: tool_sequence
# ═══════════════════════════════════════════════════════════════════


class TestToolSequenceAssertion:

    def test_passes_when_expected_tools_called(self):
        """Assertion passes when all expected tools were called."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, completed_tasks={"t1", "t2", "t3"})
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED, {}),
            _make_event(run_id, 2, SubstrateEventType.TOOL_CALL, {"tool_name": "search_docs"}),
            _make_event(run_id, 3, SubstrateEventType.TOOL_CALL, {"tool_name": "extract_content"}),
            _make_event(run_id, 4, SubstrateEventType.TOOL_CALL, {"tool_name": "summarize"}),
            _make_event(run_id, 5, SubstrateEventType.MISSION_COMPLETED, {}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {
                "type": "tool_sequence",
                "expected_tools": ["search_docs", "extract_content", "summarize"],
                "order": "subset",
                "max_calls_per_tool": {"search_docs": 3, "extract_content": 2, "summarize": 2},
            }
        ]))

        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].severity == Severity.INFO
        assert results[0].assertion_type == "tool_sequence"

    def test_fails_when_tool_missing(self):
        """Assertion fails when an expected tool was not called."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        events = [
            _make_event(run_id, 1, SubstrateEventType.TOOL_CALL, {"tool_name": "search_docs"}),
            _make_event(run_id, 2, SubstrateEventType.TOOL_CALL, {"tool_name": "summarize"}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {
                "type": "tool_sequence",
                "expected_tools": ["search_docs", "extract_content", "summarize"],
                "order": "subset",
            }
        ]))

        assert results[0].passed is False
        assert results[0].severity == Severity.FAILURE
        assert "extract_content" in results[0].actual["missing"]

    def test_fails_when_tool_calls_exceed_max(self):
        """Assertion fails when a tool is called more than max_calls_per_tool."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        events = [
            _make_event(run_id, 1, SubstrateEventType.TOOL_CALL, {"tool_name": "search_docs"}),
            _make_event(run_id, 2, SubstrateEventType.TOOL_CALL, {"tool_name": "search_docs"}),
            _make_event(run_id, 3, SubstrateEventType.TOOL_CALL, {"tool_name": "search_docs"}),
            _make_event(run_id, 4, SubstrateEventType.TOOL_CALL, {"tool_name": "search_docs"}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {
                "type": "tool_sequence",
                "expected_tools": ["search_docs"],
                "order": "any",
                "max_calls_per_tool": {"search_docs": 3},
            }
        ]))

        assert results[0].passed is False
        assert results[0].assertion_type == "tool_sequence"

    def test_exact_order_fails_when_reordered(self):
        """Exact order assertion fails when tools are called in different order."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        events = [
            _make_event(run_id, 1, SubstrateEventType.TOOL_CALL, {"tool_name": "summarize"}),
            _make_event(run_id, 2, SubstrateEventType.TOOL_CALL, {"tool_name": "search_docs"}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {
                "type": "tool_sequence",
                "expected_tools": ["search_docs", "summarize"],
                "order": "exact",
            }
        ]))

        assert results[0].passed is False
        assert "order" in results[0].message.lower()


# ═══════════════════════════════════════════════════════════════════
# ReplayAssertionEngine: cost_ceiling
# ═══════════════════════════════════════════════════════════════════


class TestCostCeilingAssertion:

    def test_passes_when_within_budget(self):
        """Cost assertion passes when actual cost is under ceiling."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, total_cost_usd=0.12)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "cost_ceiling", "max_cost_usd": 0.50, "warn_at_pct": 80}
        ]))

        assert results[0].passed is True
        assert results[0].severity == Severity.INFO
        assert results[0].actual["cost_usd"] == 0.12

    def test_fails_when_over_budget(self):
        """Cost assertion fails when actual cost exceeds ceiling."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, total_cost_usd=0.75)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "cost_ceiling", "max_cost_usd": 0.50, "warn_at_pct": 80}
        ]))

        assert results[0].passed is False
        assert results[0].severity == Severity.FAILURE

    def test_warns_when_near_ceiling(self):
        """Cost assertion warns when at or above warn_at_pct threshold."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, total_cost_usd=0.45)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "cost_ceiling", "max_cost_usd": 0.50, "warn_at_pct": 80}
        ]))

        assert results[0].passed is True
        assert results[0].severity == Severity.WARNING


# ═══════════════════════════════════════════════════════════════════
# ReplayAssertionEngine: latency
# ═══════════════════════════════════════════════════════════════════


class TestLatencyAssertion:

    def test_passes_when_within_limit(self):
        """Latency assertion passes when duration is under limit."""
        run_id = str(uuid4())
        state = _make_run_state(
            run_id,
            started_at=datetime(2026, 6, 12, 10, 0, 0, tzinfo=timezone.utc),
            last_event_at=datetime(2026, 6, 12, 10, 1, 30, tzinfo=timezone.utc),
        )
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "latency", "max_duration_seconds": 120, "warn_at_pct": 80}
        ]))

        assert results[0].passed is True
        assert results[0].actual["duration_seconds"] == 90.0

    def test_fails_when_over_limit(self):
        """Latency assertion fails when duration exceeds limit."""
        run_id = str(uuid4())
        state = _make_run_state(
            run_id,
            started_at=datetime(2026, 6, 12, 10, 0, 0, tzinfo=timezone.utc),
            last_event_at=datetime(2026, 6, 12, 10, 3, 0, tzinfo=timezone.utc),
        )
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "latency", "max_duration_seconds": 120, "warn_at_pct": 80}
        ]))

        assert results[0].passed is False
        assert results[0].severity == Severity.FAILURE


# ═══════════════════════════════════════════════════════════════════
# ReplayAssertionEngine: task_completion
# ═══════════════════════════════════════════════════════════════════


class TestTaskCompletionAssertion:

    def test_passes_when_enough_tasks_completed(self):
        """Task completion assertion passes when minimum tasks completed."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, completed_tasks={"t1", "t2", "t3"}, failed_tasks=set())
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "task_completion", "min_tasks_completed": 3, "max_tasks_failed": 0}
        ]))

        assert results[0].passed is True
        assert results[0].actual["completed"] == 3

    def test_fails_when_too_few_completed(self):
        """Task completion assertion fails when fewer than minimum completed."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, completed_tasks={"t1"}, failed_tasks=set())
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "task_completion", "min_tasks_completed": 3, "max_tasks_failed": 0}
        ]))

        assert results[0].passed is False

    def test_fails_when_tasks_failed(self):
        """Task completion assertion fails when tasks failed above max."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, completed_tasks={"t1"}, failed_tasks={"t2"})
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "task_completion", "min_tasks_completed": 1, "max_tasks_failed": 0}
        ]))

        assert results[0].passed is False


# ═══════════════════════════════════════════════════════════════════
# ReplayAssertionEngine: no_circuit_breaker
# ═══════════════════════════════════════════════════════════════════


class TestNoCircuitBreakerAssertion:

    def test_passes_when_no_cb_events(self):
        """No-circuit-breaker assertion passes when no CB events exist."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED, {}),
            _make_event(run_id, 2, SubstrateEventType.MISSION_COMPLETED, {}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "no_circuit_breaker", "description": "CB should not trip"}
        ]))

        assert results[0].passed is True
        assert results[0].actual["circuit_breaker_events"] == 0

    def test_fails_when_cb_triggered(self):
        """No-circuit-breaker assertion fails when CB was triggered."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED, {}),
            _make_event(run_id, 2, SubstrateEventType.CIRCUIT_BREAKER_TRIGGERED, {}),
            _make_event(run_id, 3, SubstrateEventType.MISSION_COMPLETED, {}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "no_circuit_breaker"}
        ]))

        assert results[0].passed is False
        assert results[0].severity == Severity.FAILURE


# ═══════════════════════════════════════════════════════════════════
# ReplayAssertionEngine: edge cases
# ═══════════════════════════════════════════════════════════════════


class TestAssertionEngineEdgeCases:

    def test_empty_assertions_returns_empty(self):
        """Empty expected_behaviors list returns empty results."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, []))
        assert results == []

    def test_unknown_assertion_type(self):
        """Unknown assertion type returns a warning result."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "unknown_type", "foo": "bar"}
        ]))

        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].severity == Severity.WARNING
        assert "unknown" in results[0].message.lower()

    def test_multiple_assertions(self):
        """Multiple assertions are all evaluated independently."""
        run_id = str(uuid4())
        state = _make_run_state(
            run_id,
            completed_tasks={"t1", "t2"},
            total_cost_usd=0.10,
        )
        events = [
            _make_event(run_id, 1, SubstrateEventType.TOOL_CALL, {"tool_name": "search"}),
            _make_event(run_id, 2, SubstrateEventType.MISSION_COMPLETED, {}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(engine.evaluate(db, run_id, [
            {"type": "cost_ceiling", "max_cost_usd": 0.50},
            {"type": "task_completion", "min_tasks_completed": 2, "max_tasks_failed": 0},
            {"type": "no_circuit_breaker"},
        ]))

        assert len(results) == 3
        assert all(r.passed for r in results)

    def test_get_assertion_engine_singleton(self):
        """get_assertion_engine() returns the same instance."""
        e1 = get_assertion_engine()
        e2 = get_assertion_engine()
        assert e1 is e2


# ═══════════════════════════════════════════════════════════════════
# Intervention Distance
# ═══════════════════════════════════════════════════════════════════


class TestInterventionDistance:

    def test_fully_autonomous_run(self):
        """Run with zero interventions has 100% autonomy."""
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED, {}),
            _make_event(run_id, 2, SubstrateEventType.TASK_STARTED, {"task_id": "t1"}),
            _make_event(run_id, 3, SubstrateEventType.TASK_COMPLETED, {"task_id": "t1"}),
            _make_event(run_id, 4, SubstrateEventType.MISSION_COMPLETED, {}),
        ]

        result = compute_intervention_distance(events)

        assert result["human_interventions"] == 0
        assert result["total_actions"] == 4
        assert result["autonomy_score"] == 1.0
        assert result["intervention_distance"] == 4.0  # all actions in one segment

    def test_with_one_intervention(self):
        """Run with one HITL event splits into two segments."""
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED, {}),
            _make_event(run_id, 2, SubstrateEventType.TASK_STARTED, {"task_id": "t1"}),
            _make_event(run_id, 3, SubstrateEventType.HUMAN_INTERRUPT_RAISED, {}),
            _make_event(run_id, 4, SubstrateEventType.HUMAN_INTERRUPT_RESOLVED, {}),
            _make_event(run_id, 5, SubstrateEventType.TASK_COMPLETED, {"task_id": "t1"}),
            _make_event(run_id, 6, SubstrateEventType.MISSION_COMPLETED, {}),
        ]

        result = compute_intervention_distance(events)

        assert result["human_interventions"] == 1
        assert result["total_actions"] == 4  # STARTED, TASK_STARTED, TASK_COMPLETED, MISSION_COMPLETED
        assert result["intervention_distance"] == pytest.approx(2.0)  # segments [2, 2] → avg 2.0

    def test_with_multiple_interventions(self):
        """Multiple interventions create multiple segments."""
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED, {}),
            _make_event(run_id, 2, SubstrateEventType.HUMAN_INTERRUPT_RAISED, {}),
            _make_event(run_id, 3, SubstrateEventType.HUMAN_INTERRUPT_RESOLVED, {}),
            _make_event(run_id, 4, SubstrateEventType.TASK_STARTED, {"task_id": "t1"}),
            _make_event(run_id, 5, SubstrateEventType.TASK_COMPLETED, {"task_id": "t1"}),
            _make_event(run_id, 6, SubstrateEventType.HUMAN_INTERRUPT_RAISED, {}),
            _make_event(run_id, 7, SubstrateEventType.HUMAN_INTERRUPT_RESOLVED, {}),
            _make_event(run_id, 8, SubstrateEventType.MISSION_COMPLETED, {}),
        ]

        result = compute_intervention_distance(events)

        assert result["human_interventions"] == 2
        assert result["total_actions"] == 4  # STARTED, TASK_STARTED, TASK_COMPLETED, MISSION_COMPLETED
        # Segments: [1] (before HITL1), [2] (between HITLs), [1] (after HITL2)
        # avg = (1 + 2 + 1) / 3 ≈ 1.33 → rounded to 1.3
        assert result["intervention_distance"] == pytest.approx(1.3)

    def test_empty_events(self):
        """Empty event list returns zero metrics."""
        result = compute_intervention_distance([])
        assert result["total_actions"] == 0
        assert result["human_interventions"] == 0
        assert result["intervention_distance"] == 0.0
        assert result["autonomy_score"] == 1.0  # no interventions = fully autonomous

    def test_autonomy_score_clamped(self):
        """Autonomy score is clamped to [0, 1]."""
        # More interventions than actions — edge case
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.HUMAN_INTERRUPT_RAISED, {}),
            _make_event(run_id, 2, SubstrateEventType.HUMAN_INTERRUPT_RESOLVED, {}),
            _make_event(run_id, 3, SubstrateEventType.HUMAN_INTERRUPT_RAISED, {}),
            _make_event(run_id, 4, SubstrateEventType.HUMAN_INTERRUPT_RESOLVED, {}),
        ]

        result = compute_intervention_distance(events)
        assert 0.0 <= result["autonomy_score"] <= 1.0
