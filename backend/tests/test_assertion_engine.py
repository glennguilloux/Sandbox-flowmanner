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
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.substrate_models import (
    SubstrateEvent,
    SubstrateEventType,
    SubstrateRunState,
)
from app.observability.intervention_distance import compute_intervention_distance
from app.services.substrate.assertion_engine import (
    AssertionResult,
    AssertionType,
    BaselineVersion,
    ReplayAssertionEngine,
    Severity,
    get_assertion_engine,
)
from app.services.substrate.event_log import EventLog
from app.services.substrate.replay_engine import ReplayEngine

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
    state.started_at = started_at or datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC)
    state.last_event_at = last_event_at or datetime(2026, 6, 12, 10, 2, 0, tzinfo=UTC)
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
            _make_event(
                run_id,
                3,
                SubstrateEventType.TOOL_CALL,
                {"tool_name": "extract_content"},
            ),
            _make_event(run_id, 4, SubstrateEventType.TOOL_CALL, {"tool_name": "summarize"}),
            _make_event(run_id, 5, SubstrateEventType.MISSION_COMPLETED, {}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "tool_sequence",
                        "expected_tools": [
                            "search_docs",
                            "extract_content",
                            "summarize",
                        ],
                        "order": "subset",
                        "max_calls_per_tool": {
                            "search_docs": 3,
                            "extract_content": 2,
                            "summarize": 2,
                        },
                    }
                ],
            )
        )

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

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "tool_sequence",
                        "expected_tools": [
                            "search_docs",
                            "extract_content",
                            "summarize",
                        ],
                        "order": "subset",
                    }
                ],
            )
        )

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

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "tool_sequence",
                        "expected_tools": ["search_docs"],
                        "order": "any",
                        "max_calls_per_tool": {"search_docs": 3},
                    }
                ],
            )
        )

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

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "tool_sequence",
                        "expected_tools": ["search_docs", "summarize"],
                        "order": "exact",
                    }
                ],
            )
        )

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

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [{"type": "cost_ceiling", "max_cost_usd": 0.50, "warn_at_pct": 80}],
            )
        )

        assert results[0].passed is True
        assert results[0].severity == Severity.INFO
        assert results[0].actual["cost_usd"] == 0.12

    def test_fails_when_over_budget(self):
        """Cost assertion fails when actual cost exceeds ceiling."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, total_cost_usd=0.75)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [{"type": "cost_ceiling", "max_cost_usd": 0.50, "warn_at_pct": 80}],
            )
        )

        assert results[0].passed is False
        assert results[0].severity == Severity.FAILURE

    def test_warns_when_near_ceiling(self):
        """Cost assertion warns when at or above warn_at_pct threshold."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, total_cost_usd=0.45)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [{"type": "cost_ceiling", "max_cost_usd": 0.50, "warn_at_pct": 80}],
            )
        )

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
            started_at=datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC),
            last_event_at=datetime(2026, 6, 12, 10, 1, 30, tzinfo=UTC),
        )
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [{"type": "latency", "max_duration_seconds": 120, "warn_at_pct": 80}],
            )
        )

        assert results[0].passed is True
        assert results[0].actual["duration_seconds"] == 90.0

    def test_fails_when_over_limit(self):
        """Latency assertion fails when duration exceeds limit."""
        run_id = str(uuid4())
        state = _make_run_state(
            run_id,
            started_at=datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC),
            last_event_at=datetime(2026, 6, 12, 10, 3, 0, tzinfo=UTC),
        )
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [{"type": "latency", "max_duration_seconds": 120, "warn_at_pct": 80}],
            )
        )

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

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "task_completion",
                        "min_tasks_completed": 3,
                        "max_tasks_failed": 0,
                    }
                ],
            )
        )

        assert results[0].passed is True
        assert results[0].actual["completed"] == 3

    def test_fails_when_too_few_completed(self):
        """Task completion assertion fails when fewer than minimum completed."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, completed_tasks={"t1"}, failed_tasks=set())
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "task_completion",
                        "min_tasks_completed": 3,
                        "max_tasks_failed": 0,
                    }
                ],
            )
        )

        assert results[0].passed is False

    def test_fails_when_tasks_failed(self):
        """Task completion assertion fails when tasks failed above max."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, completed_tasks={"t1"}, failed_tasks={"t2"})
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "task_completion",
                        "min_tasks_completed": 1,
                        "max_tasks_failed": 0,
                    }
                ],
            )
        )

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

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [{"type": "no_circuit_breaker", "description": "CB should not trip"}],
            )
        )

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

        results = asyncio.run(engine.evaluate(db, run_id, [{"type": "no_circuit_breaker"}]))

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

        results = asyncio.run(engine.evaluate(db, run_id, [{"type": "unknown_type", "foo": "bar"}]))

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

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {"type": "cost_ceiling", "max_cost_usd": 0.50},
                    {
                        "type": "task_completion",
                        "min_tasks_completed": 2,
                        "max_tasks_failed": 0,
                    },
                    {"type": "no_circuit_breaker"},
                ],
            )
        )

        assert len(results) == 3
        assert all(r.passed for r in results)

    def test_get_assertion_engine_singleton(self):
        """get_assertion_engine() returns the same instance."""
        e1 = get_assertion_engine()
        e2 = get_assertion_engine()
        assert e1 is e2


# ═══════════════════════════════════════════════════════════════════
# BaselineVersion dataclass
# ═══════════════════════════════════════════════════════════════════


class TestBaselineVersion:
    def test_is_valid_when_all_fields_set(self):
        """BaselineVersion.is_valid() returns True when all fields are set."""
        bv = BaselineVersion(
            model_id="deepseek-chat",
            pricing_table_version="v1.2.3",
            template_version="tmpl-abc",
        )
        assert bv.is_valid() is True

    def test_is_valid_false_when_empty(self):
        """BaselineVersion.is_valid() returns False when any field is empty."""
        bv = BaselineVersion(model_id="deepseek-chat")
        assert bv.is_valid() is False

    def test_to_dict(self):
        """BaselineVersion.to_dict() produces correct dict."""
        bv = BaselineVersion(
            model_id="m",
            pricing_table_version="p",
            template_version="t",
        )
        d = bv.to_dict()
        assert d["model_id"] == "m"
        assert d["pricing_table_version"] == "p"
        assert d["template_version"] == "t"


# ═══════════════════════════════════════════════════════════════════
# ReplayAssertionEngine: tool_sequence — partial order (Item #9)
# ═══════════════════════════════════════════════════════════════════


class TestToolSequencePartialOrder:
    def test_required_edges_pass_when_order_respected(self):
        """Assertion passes when required ordering edges are respected."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        events = [
            _make_event(run_id, 1, SubstrateEventType.TOOL_CALL, {"tool_name": "search"}),
            _make_event(run_id, 2, SubstrateEventType.TOOL_CALL, {"tool_name": "extract"}),
            _make_event(run_id, 3, SubstrateEventType.TOOL_CALL, {"tool_name": "summarize"}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "tool_sequence",
                        "expected_tools": ["search", "extract", "summarize"],
                        "order": "subset",
                        "required_edges": [["search", "summarize"], ["extract", "summarize"]],
                    }
                ],
            )
        )
        assert results[0].passed is True

    def test_required_edges_fail_when_reversed(self):
        """Assertion fails when a required edge is violated."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        events = [
            _make_event(run_id, 1, SubstrateEventType.TOOL_CALL, {"tool_name": "summarize"}),
            _make_event(run_id, 2, SubstrateEventType.TOOL_CALL, {"tool_name": "search"}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "tool_sequence",
                        "expected_tools": ["search", "summarize"],
                        "order": "subset",
                        "required_edges": [["search", "summarize"]],
                    }
                ],
            )
        )
        assert results[0].passed is False
        assert "Ordering violation" in results[0].message

    def test_forbidden_tools_fail_when_present(self):
        """Assertion fails when a forbidden tool is called."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        events = [
            _make_event(run_id, 1, SubstrateEventType.TOOL_CALL, {"tool_name": "search"}),
            _make_event(run_id, 2, SubstrateEventType.TOOL_CALL, {"tool_name": "dangerous_tool"}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "tool_sequence",
                        "expected_tools": ["search"],
                        "order": "subset",
                        "forbidden_tools": ["dangerous_tool"],
                    }
                ],
            )
        )
        assert results[0].passed is False
        assert "Forbidden" in results[0].message

    def test_forbidden_tools_pass_when_absent(self):
        """Assertion passes when no forbidden tools are called."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        events = [
            _make_event(run_id, 1, SubstrateEventType.TOOL_CALL, {"tool_name": "search"}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "tool_sequence",
                        "expected_tools": ["search"],
                        "order": "subset",
                        "forbidden_tools": ["dangerous_tool"],
                    }
                ],
            )
        )
        assert results[0].passed is True

    def test_equivalence_classes_merge_aliases(self):
        """Equivalence classes treat aliases as the same tool."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        events = [
            _make_event(run_id, 1, SubstrateEventType.TOOL_CALL, {"tool_name": "web_search"}),
            _make_event(run_id, 2, SubstrateEventType.TOOL_CALL, {"tool_name": "rag_search"}),
        ]
        engine = _mock_engine(state, events)
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "tool_sequence",
                        "expected_tools": ["search"],
                        "order": "subset",
                        "equivalence_classes": {"search": ["web_search", "rag_search"]},
                    }
                ],
            )
        )
        assert results[0].passed is True
        assert results[0].actual["missing"] == []


# ═══════════════════════════════════════════════════════════════════
# ReplayAssertionEngine: cost_ceiling — token ceiling (Item #9)
# ═══════════════════════════════════════════════════════════════════


class TestCostCeilingTokenMode:
    def test_token_ceiling_passes_when_within_limit(self):
        """Token-based cost assertion passes when tokens are within ceiling."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, total_cost_usd=0.001, total_tokens=5000)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        # max_tokens=10000, pricing input=0.14/1M → dynamic ceiling = 0.0014
        # actual cost 0.001 < 0.0014, actual tokens 5000 < 10000 → pass
        pricing = {
            "deepseek-chat": {"input": 0.14, "output": 0.28},
            "default": {"input": 0.50, "output": 2.00},
        }
        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "cost_ceiling",
                        "max_tokens": 10000,
                        "pricing_table": pricing,
                        "model_id": "deepseek-chat",
                        "warn_at_pct": 80,
                    }
                ],
            )
        )
        assert results[0].passed is True
        assert results[0].actual["total_tokens"] == 5000

    def test_token_ceiling_fails_when_tokens_exceeded(self):
        """Token-based cost assertion fails when tokens exceed ceiling."""
        run_id = str(uuid4())
        state = _make_run_state(run_id, total_cost_usd=0.001, total_tokens=15000)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        pricing = {
            "deepseek-chat": {"input": 0.14, "output": 0.28},
            "default": {"input": 0.50, "output": 2.00},
        }
        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "cost_ceiling",
                        "max_tokens": 10000,
                        "pricing_table": pricing,
                        "model_id": "deepseek-chat",
                        "warn_at_pct": 80,
                    }
                ],
            )
        )
        assert results[0].passed is False
        assert "Tokens" in results[0].message

    def test_token_ceiling_dynamic_dollar_recomputation(self):
        """Dynamic pricing recomputation adjusts the dollar ceiling."""
        run_id = str(uuid4())
        # actual cost is high, but tokens are within ceiling
        state = _make_run_state(run_id, total_cost_usd=0.003, total_tokens=5000)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        # max_rate = max(0.14, 0.28) = 0.28
        # dynamic ceiling = (10000/1M) * 0.28 = 0.0028
        # actual_cost 0.003 > 0.0028 → fail
        pricing = {
            "deepseek-chat": {"input": 0.14, "output": 0.28},
            "default": {"input": 0.50, "output": 2.00},
        }
        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "cost_ceiling",
                        "max_tokens": 10000,
                        "pricing_table": pricing,
                        "model_id": "deepseek-chat",
                        "warn_at_pct": 80,
                    }
                ],
            )
        )
        assert results[0].passed is False
        assert results[0].expected["max_cost_usd"] == pytest.approx(0.0028, abs=1e-6)


# ═══════════════════════════════════════════════════════════════════
# ReplayAssertionEngine: latency — rolling-aggregate (Item #9)
# ═══════════════════════════════════════════════════════════════════


class TestLatencyRollingAggregate:
    def test_single_breach_is_warning_only(self):
        """A single latency breach is a warning, not a failure."""
        run_id = str(uuid4())
        state = _make_run_state(
            run_id,
            started_at=datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC),
            last_event_at=datetime(2026, 6, 12, 10, 5, 0, tzinfo=UTC),
        )
        engine = _mock_engine(state, [])
        db = AsyncMock()

        # History: 3 short runs → p95 ≈ 110, ceiling = 110*1.5 = 165
        # Current = 300s → single breach → warning only
        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [{"type": "latency", "p95_headroom": 1.5, "consecutive_violations": 3}],
                latency_history=[100.0, 110.0, 90.0],
            )
        )
        assert results[0].passed is True
        assert results[0].severity == Severity.WARNING
        assert results[0].actual["consecutive_breaches"] == 1

    def test_consecutive_breaches_triggers_failure(self):
        """N consecutive breaches trigger a failure."""
        run_id = str(uuid4())
        state = _make_run_state(
            run_id,
            started_at=datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC),
            last_event_at=datetime(2026, 6, 12, 10, 5, 0, tzinfo=UTC),
        )
        engine = _mock_engine(state, [])
        db = AsyncMock()

        # Large stable baseline (p95=10) + 1 recent spike in history +
        # current run also spiking → 2 consecutive breaches.
        # sorted = [10x20, 200] → p95_idx=19 → p95=10 → ceiling=15
        # all_runs[-3:] = [200, 200, actual=200] → 2 breaches (200>15)
        history = [10.0] * 20 + [200.0]
        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [{"type": "latency", "p95_headroom": 1.5, "consecutive_violations": 2}],
                latency_history=history,
            )
        )
        assert results[0].passed is False
        assert results[0].severity == Severity.FAILURE
        assert results[0].actual["consecutive_breaches"] >= 2

    def test_no_breach_passes(self):
        """No breaches passes with INFO."""
        run_id = str(uuid4())
        state = _make_run_state(
            run_id,
            started_at=datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC),
            last_event_at=datetime(2026, 6, 12, 10, 1, 0, tzinfo=UTC),
        )
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [{"type": "latency", "p95_headroom": 1.5, "consecutive_violations": 3}],
                latency_history=[100.0, 110.0, 90.0],
            )
        )
        assert results[0].passed is True
        assert results[0].severity == Severity.INFO
        assert results[0].actual["consecutive_breaches"] == 0

    def test_fallback_to_legacy_when_no_history(self):
        """Falls back to legacy max_duration_seconds when no history provided."""
        run_id = str(uuid4())
        state = _make_run_state(
            run_id,
            started_at=datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC),
            last_event_at=datetime(2026, 6, 12, 10, 1, 30, tzinfo=UTC),
        )
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [{"type": "latency", "max_duration_seconds": 120}],
            )
        )
        assert results[0].passed is True
        assert "p95" not in results[0].message


# ═══════════════════════════════════════════════════════════════════
# ReplayAssertionEngine: baseline_version (Item #9)
# ═══════════════════════════════════════════════════════════════════


class TestBaselineVersionAssertion:
    def test_passes_when_versions_match(self):
        """Baseline version assertion passes when stored and current match."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        current = BaselineVersion(
            model_id="deepseek-chat",
            pricing_table_version="v1",
            template_version="tmpl-1",
        )
        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "baseline_version",
                        "model_id": "deepseek-chat",
                        "pricing_table_version": "v1",
                        "template_version": "tmpl-1",
                    }
                ],
                current_baseline_version=current,
            )
        )
        assert results[0].passed is True
        assert results[0].severity == Severity.INFO

    def test_fails_when_model_id_drifts(self):
        """Baseline version assertion warns on model_id drift."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        current = BaselineVersion(
            model_id="gpt-4o",  # different!
            pricing_table_version="v1",
            template_version="tmpl-1",
        )
        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "baseline_version",
                        "model_id": "deepseek-chat",
                        "pricing_table_version": "v1",
                        "template_version": "tmpl-1",
                    }
                ],
                current_baseline_version=current,
            )
        )
        assert results[0].passed is False
        assert results[0].severity == Severity.WARNING
        assert "drift" in results[0].message.lower()

    def test_fails_when_pricing_drifts(self):
        """Baseline version assertion warns on pricing table drift."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        current = BaselineVersion(
            model_id="deepseek-chat",
            pricing_table_version="v2",  # different!
            template_version="tmpl-1",
        )
        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [
                    {
                        "type": "baseline_version",
                        "model_id": "deepseek-chat",
                        "pricing_table_version": "v1",
                        "template_version": "tmpl-1",
                    }
                ],
                current_baseline_version=current,
            )
        )
        assert results[0].passed is False
        assert "pricing" in results[0].message.lower()

    def test_skips_when_no_stored_version(self):
        """Baseline version assertion skips when stored version is empty."""
        run_id = str(uuid4())
        state = _make_run_state(run_id)
        engine = _mock_engine(state, [])
        db = AsyncMock()

        results = asyncio.run(
            engine.evaluate(
                db,
                run_id,
                [{"type": "baseline_version"}],
                current_baseline_version=BaselineVersion(),
            )
        )
        assert results[0].passed is True
        assert "skipping" in results[0].message.lower()


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
