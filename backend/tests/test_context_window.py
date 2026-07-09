"""Unit tests for the last-N event context window (Q2-Q3 Chunk 2 Tier 1).

Covers:
- _build_context_window(): correct event range, noise filtering, empty runs
- _format_context_events(): serialization format, payload truncation
- context_window_size configurability via workflow.metadata
- Context injection into _handle_llm() messages
- task.started event records context window range for replay
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.substrate_models import SubstrateEvent, SubstrateEventType
from app.services.substrate.node_executor import (
    _DEFAULT_CONTEXT_WINDOW_SIZE,
    _NOISY_EVENT_TYPES,
    NodeExecutor,
)
from app.services.substrate.workflow_models import Workflow, WorkflowNode, WorkflowType

# ── Helpers ────────────────────────────────────────────────────────


def _make_event(
    sequence: int, event_type: str = "task.completed", actor: str = "node_executor", payload: dict | None = None
) -> SubstrateEvent:
    """Create a SubstrateEvent with the given sequence and type."""
    return SubstrateEvent(
        id=str(uuid4()),
        sequence=sequence,
        run_id="run-1",
        type=event_type,
        actor=actor,
        payload=payload or {"task_id": f"t{sequence}", "output": f"result_{sequence}"},
    )


def _make_mock_executor():
    """Create a NodeExecutor with a mocked UnifiedExecutor."""
    mock_executor = MagicMock()
    mock_executor.is_aborted = MagicMock(return_value=False)
    mock_executor.event_log = MagicMock()
    mock_executor.event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])
    mock_executor.event_log.get_latest_sequence = AsyncMock(return_value=0)
    mock_executor.event_log.get_events = AsyncMock(return_value=[])
    return NodeExecutor(mock_executor), mock_executor


def _make_budget(exhausted: bool = False):
    budget = MagicMock()
    budget.is_exhausted = MagicMock(return_value=(exhausted, ""))
    return budget


def _make_workflow(context_window_size: int | None = None) -> Workflow:
    """Create a Workflow with optional context_window_size in metadata."""
    metadata = {}
    if context_window_size is not None:
        metadata["context_window_size"] = context_window_size
    return Workflow(
        id="wf-1",
        type=WorkflowType.SOLO,
        title="Test Workflow",
        nodes=[],
        metadata=metadata,
    )


# ═══════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════


class TestContextWindowConstants:
    def test_default_context_window_size_is_20(self):
        assert _DEFAULT_CONTEXT_WINDOW_SIZE == 20

    def test_noisy_event_types_include_lease_events(self):
        assert SubstrateEventType.LEASE_CLAIMED in _NOISY_EVENT_TYPES
        assert SubstrateEventType.LEASE_RENEWED in _NOISY_EVENT_TYPES
        assert SubstrateEventType.LEASE_RELEASED in _NOISY_EVENT_TYPES

    def test_noisy_event_types_include_circuit_breaker_events(self):
        assert SubstrateEventType.CIRCUIT_BREAKER_TRIGGERED in _NOISY_EVENT_TYPES
        assert SubstrateEventType.CIRCUIT_BREAKER_BROKEN in _NOISY_EVENT_TYPES
        assert SubstrateEventType.CIRCUIT_BREAKER_RESET in _NOISY_EVENT_TYPES
        assert SubstrateEventType.CIRCUIT_BREAKER_OPENED in _NOISY_EVENT_TYPES

    def test_noisy_event_types_include_checkpoint(self):
        assert SubstrateEventType.CHECKPOINT in _NOISY_EVENT_TYPES

    def test_noisy_event_types_do_not_include_task_events(self):
        """Task lifecycle events must NOT be filtered — they're the core context."""
        assert SubstrateEventType.TASK_STARTED not in _NOISY_EVENT_TYPES
        assert SubstrateEventType.TASK_COMPLETED not in _NOISY_EVENT_TYPES
        assert SubstrateEventType.TASK_FAILED not in _NOISY_EVENT_TYPES
        assert SubstrateEventType.LLM_CALL not in _NOISY_EVENT_TYPES
        assert SubstrateEventType.TOOL_CALL not in _NOISY_EVENT_TYPES


# ═══════════════════════════════════════════════════════════════════
# _build_context_window()
# ═══════════════════════════════════════════════════════════════════


class TestBuildContextWindow:
    @pytest.mark.asyncio
    async def test_returns_last_n_events_in_order(self):
        """Context window returns the last N events, ordered by sequence ascending."""
        ne, _ = _make_mock_executor()
        events = [_make_event(i) for i in range(1, 21)]  # 20 events

        mock_event_log = MagicMock()
        mock_event_log.get_events = AsyncMock(return_value=events)

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await ne._build_context_window(AsyncMock(), "run-1", current_sequence=21, context_window_size=20)

        assert len(result) == 20
        assert result[0].sequence == 1
        assert result[-1].sequence == 20
        # Verify sequences are ascending (causal order)
        sequences = [e.sequence for e in result]
        assert sequences == sorted(sequences)

    @pytest.mark.asyncio
    async def test_filters_noisy_events(self):
        """Lease, circuit breaker, and checkpoint events are excluded."""
        ne, _ = _make_mock_executor()
        events = [
            _make_event(1, SubstrateEventType.TASK_COMPLETED),
            _make_event(2, SubstrateEventType.LEASE_CLAIMED),
            _make_event(3, SubstrateEventType.TASK_COMPLETED),
            _make_event(4, SubstrateEventType.CIRCUIT_BREAKER_TRIGGERED),
            _make_event(5, SubstrateEventType.CHECKPOINT),
            _make_event(6, SubstrateEventType.TASK_FAILED),
        ]

        mock_event_log = MagicMock()
        mock_event_log.get_events = AsyncMock(return_value=events)

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await ne._build_context_window(AsyncMock(), "run-1", current_sequence=7, context_window_size=20)

        assert len(result) == 3
        assert all(e.type not in _NOISY_EVENT_TYPES for e in result)
        assert result[0].sequence == 1
        assert result[1].sequence == 3
        assert result[2].sequence == 6

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_prior_events(self):
        """When no prior events exist, returns empty list."""
        ne, _ = _make_mock_executor()
        mock_event_log = MagicMock()
        mock_event_log.get_events = AsyncMock(return_value=[])

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await ne._build_context_window(AsyncMock(), "run-1", current_sequence=1, context_window_size=20)

        assert result == []

    @pytest.mark.asyncio
    async def test_uses_correct_from_sequence(self):
        """Verifies the correct from_sequence calculation: current - N."""
        ne, _ = _make_mock_executor()
        mock_event_log = MagicMock()
        mock_event_log.get_events = AsyncMock(return_value=[])

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            await ne._build_context_window(AsyncMock(), "run-1", current_sequence=50, context_window_size=20)

        mock_event_log.get_events.assert_called_once()
        call_kwargs = mock_event_log.get_events.call_args
        # from_sequence = max(0, 50 - 20) = 30
        assert call_kwargs[1]["from_sequence"] == 30
        assert call_kwargs[1]["to_sequence"] == 49  # current_sequence - 1
        assert call_kwargs[1]["limit"] == 20

    @pytest.mark.asyncio
    async def test_clamps_from_sequence_to_zero(self):
        """When current_sequence < N, from_sequence clamps to 0."""
        ne, _ = _make_mock_executor()
        mock_event_log = MagicMock()
        mock_event_log.get_events = AsyncMock(return_value=[])

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            await ne._build_context_window(AsyncMock(), "run-1", current_sequence=5, context_window_size=20)

        call_kwargs = mock_event_log.get_events.call_args
        assert call_kwargs[1]["from_sequence"] == 0  # max(0, 5-20) = 0
        assert call_kwargs[1]["to_sequence"] == 4

    @pytest.mark.asyncio
    async def test_all_noisy_events_returns_empty(self):
        """When all events in the window are noisy, returns empty list."""
        ne, _ = _make_mock_executor()
        events = [
            _make_event(1, SubstrateEventType.LEASE_CLAIMED),
            _make_event(2, SubstrateEventType.CIRCUIT_BREAKER_TRIGGERED),
            _make_event(3, SubstrateEventType.CHECKPOINT),
            _make_event(4, SubstrateEventType.LEASE_RELEASED),
        ]

        mock_event_log = MagicMock()
        mock_event_log.get_events = AsyncMock(return_value=events)

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await ne._build_context_window(AsyncMock(), "run-1", current_sequence=5, context_window_size=20)

        assert result == []

    @pytest.mark.asyncio
    async def test_mixed_events_preserves_non_noisy_ordering(self):
        """After filtering noisy events, remaining events maintain causal order."""
        ne, _ = _make_mock_executor()
        events = [
            _make_event(1, SubstrateEventType.TASK_STARTED),
            _make_event(2, SubstrateEventType.LEASE_RENEWED),
            _make_event(3, SubstrateEventType.TASK_COMPLETED),
            _make_event(4, SubstrateEventType.CIRCUIT_BREAKER_RESET),
            _make_event(5, SubstrateEventType.LLM_CALL),
            _make_event(6, SubstrateEventType.CHECKPOINT),
            _make_event(7, SubstrateEventType.TASK_FAILED),
        ]

        mock_event_log = MagicMock()
        mock_event_log.get_events = AsyncMock(return_value=events)

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await ne._build_context_window(AsyncMock(), "run-1", current_sequence=8, context_window_size=20)

        assert len(result) == 4
        sequences = [e.sequence for e in result]
        assert sequences == [1, 3, 5, 7]


# ═══════════════════════════════════════════════════════════════════
# _format_context_events()
# ═══════════════════════════════════════════════════════════════════


class TestFormatContextEvents:
    def test_formats_events_as_structured_text(self):
        """Each event is formatted as [seq] type (actor=...) payload."""
        _ne, _ = _make_mock_executor()
        events = [
            _make_event(5, "task.completed", "node_executor", {"task_id": "t5", "tokens": 100}),
            _make_event(6, "llm.call", "budget_enforcer", {"model": "deepseek-chat"}),
        ]

        result = NodeExecutor._format_context_events(events)

        assert "[5] task.completed (actor=node_executor)" in result
        assert "[6] llm.call (actor=budget_enforcer)" in result
        assert "task_id" in result
        assert "model" in result

    def test_truncates_large_payloads(self):
        """Payloads exceeding 300 chars are truncated."""
        _ne, _ = _make_mock_executor()
        large_payload = {"data": "x" * 400}
        events = [_make_event(1, "task.completed", "test", large_payload)]

        result = NodeExecutor._format_context_events(events)

        assert "..." in result
        # The full 400-char string should NOT appear
        assert "x" * 400 not in result

    def test_returns_empty_string_for_empty_list(self):
        _ne, _ = _make_mock_executor()
        assert NodeExecutor._format_context_events([]) == ""

    def test_events_separated_by_newlines(self):
        _ne, _ = _make_mock_executor()
        events = [
            _make_event(1, "task.started", "executor"),
            _make_event(2, "task.completed", "executor"),
        ]

        result = NodeExecutor._format_context_events(events)

        lines = result.strip().split("\n")
        assert len(lines) == 2


# ═══════════════════════════════════════════════════════════════════
# Context window configurability
# ═══════════════════════════════════════════════════════════════════


class TestContextWindowConfigurability:
    def test_default_size_when_no_metadata(self):
        workflow = _make_workflow()
        assert workflow.metadata.get("context_window_size", _DEFAULT_CONTEXT_WINDOW_SIZE) == 20

    def test_custom_size_from_metadata(self):
        workflow = _make_workflow(context_window_size=50)
        assert workflow.metadata["context_window_size"] == 50

    def test_zero_size_disables_context(self):
        workflow = _make_workflow(context_window_size=0)
        assert workflow.metadata["context_window_size"] == 0


# ═══════════════════════════════════════════════════════════════════
# Context injection into _handle_llm()
# ═══════════════════════════════════════════════════════════════════


class TestContextInjectionInLLM:
    @pytest.mark.asyncio
    async def test_context_events_injected_as_system_message(self):
        """Context events are added as a system message before the user prompt."""
        ne, _mock_executor = _make_mock_executor()
        node = WorkflowNode(
            id="n1",
            type="llm_call",
            config={"prompt": "Do something"},
        )
        db = AsyncMock()
        run_id = str(uuid4())
        budget = MagicMock()
        context_events = [
            _make_event(10, "task.completed", "node_executor", {"task_id": "t10"}),
            _make_event(11, "task.failed", "node_executor", {"error": "timeout"}),
        ]

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value={
                "success": True,
                "response": "Done",
                "budget": {"prompt_tokens": 10, "completion_tokens": 5, "spent_usd": 0.001},
            }
        )

        with (
            patch("app.services.budget_enforcer.get_budget_enforcer", return_value=mock_enforcer),
            patch("app.services.circuit_breaker_service.CircuitBreakerService"),
        ):
            await ne._handle_llm(
                db,
                node,
                {},
                budget,
                run_id,
                context_events=context_events,
            )

        call_args = mock_enforcer.call.call_args
        messages = call_args[1]["messages"]

        # Should have: system (context), user (prompt)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "Recent mission events" in messages[0]["content"]
        assert "[10] task.completed" in messages[0]["content"]
        assert "[11] task.failed" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Do something"

    @pytest.mark.asyncio
    async def test_context_with_system_prompt(self):
        """Context events go AFTER the existing system prompt."""
        ne, _mock_executor = _make_mock_executor()
        node = WorkflowNode(
            id="n1",
            type="llm_call",
            config={"prompt": "Do something", "system_prompt": "You are helpful"},
        )
        db = AsyncMock()
        run_id = str(uuid4())
        budget = MagicMock()
        context_events = [_make_event(5, "task.completed", "executor")]

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value={
                "success": True,
                "response": "Done",
                "budget": {"prompt_tokens": 10, "completion_tokens": 5, "spent_usd": 0.001},
            }
        )

        with (
            patch("app.services.budget_enforcer.get_budget_enforcer", return_value=mock_enforcer),
            patch("app.services.circuit_breaker_service.CircuitBreakerService"),
        ):
            await ne._handle_llm(
                db,
                node,
                {},
                budget,
                run_id,
                context_events=context_events,
            )

        messages = mock_enforcer.call.call_args[1]["messages"]
        assert len(messages) == 3
        assert messages[0]["content"] == "You are helpful"
        assert "Recent mission events" in messages[1]["content"]
        assert messages[2]["content"] == "Do something"

    @pytest.mark.asyncio
    async def test_no_context_message_when_events_empty(self):
        """When context_events is empty, no extra message is added."""
        ne, _mock_executor = _make_mock_executor()
        node = WorkflowNode(
            id="n1",
            type="llm_call",
            config={"prompt": "Hello"},
        )
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget()

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value={
                "success": True,
                "response": "Hi",
                "budget": {"prompt_tokens": 5, "completion_tokens": 2, "spent_usd": 0.001},
            }
        )

        with (
            patch("app.services.budget_enforcer.get_budget_enforcer", return_value=mock_enforcer),
            patch("app.services.circuit_breaker_service.CircuitBreakerService"),
        ):
            await ne._handle_llm(db, node, {}, budget, run_id, context_events=[])

        messages = mock_enforcer.call.call_args[1]["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"


# ═══════════════════════════════════════════════════════════════════
# task.started event records context window range
# ═══════════════════════════════════════════════════════════════════


class TestTaskStartedRecordsContextWindow:
    @pytest.mark.asyncio
    async def test_task_started_includes_context_window_range(self):
        """The task.started event payload includes context window metadata."""
        ne, _mock_executor = _make_mock_executor()
        node = WorkflowNode(id="n1", type="llm_call", config={"prompt": "Hi"})
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget()
        workflow = _make_workflow()

        context_events = [
            _make_event(8, "task.completed", "executor"),
            _make_event(9, "task.completed", "executor"),
            _make_event(10, "task.failed", "executor"),
        ]

        mock_event_log = MagicMock()
        mock_event_log.get_latest_sequence = AsyncMock(return_value=10)
        mock_event_log.get_events = AsyncMock(return_value=context_events)
        mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=11)])

        mock_result = {"success": True, "output": "ok", "tokens": 10, "cost": 0.01}

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_event_log,
            ),
            patch.object(ne, "_dispatch", new_callable=AsyncMock, return_value=mock_result),
        ):
            await ne.execute(db, node, {}, budget, run_id, workflow)

        # Find the task.started event in the append calls
        all_events = []
        for call in mock_event_log.append.call_args_list:
            all_events.extend(call[0][2])

        started_events = [e for e in all_events if e["type"] == SubstrateEventType.TASK_STARTED]
        assert len(started_events) >= 1

        payload = started_events[0]["payload"]
        assert payload["context_window_from_seq"] == 8
        assert payload["context_window_to_seq"] == 10
        assert payload["context_window_event_count"] == 3

    @pytest.mark.asyncio
    async def test_task_started_omits_context_when_empty(self):
        """When no context events exist, task.started omits context window keys."""
        ne, _mock_executor = _make_mock_executor()
        node = WorkflowNode(id="n1", type="llm_call", config={"prompt": "Hi"})
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget()
        workflow = _make_workflow()

        mock_event_log = MagicMock()
        mock_event_log.get_latest_sequence = AsyncMock(return_value=0)
        mock_event_log.get_events = AsyncMock(return_value=[])
        mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])

        mock_result = {"success": True, "output": "ok", "tokens": 10, "cost": 0.01}

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_event_log,
            ),
            patch.object(ne, "_dispatch", new_callable=AsyncMock, return_value=mock_result),
        ):
            await ne.execute(db, node, {}, budget, run_id, workflow)

        all_events = []
        for call in mock_event_log.append.call_args_list:
            all_events.extend(call[0][2])

        started_events = [e for e in all_events if e["type"] == SubstrateEventType.TASK_STARTED]
        payload = started_events[0]["payload"]
        assert "context_window_from_seq" not in payload
        assert "context_window_to_seq" not in payload
        assert "context_window_event_count" not in payload

    @pytest.mark.asyncio
    async def test_execute_respects_custom_context_window_size(self):
        """Custom context_window_size from workflow.metadata is used."""
        ne, _mock_executor = _make_mock_executor()
        node = WorkflowNode(id="n1", type="llm_call", config={"prompt": "Hi"})
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget()
        workflow = _make_workflow(context_window_size=5)

        mock_event_log = MagicMock()
        mock_event_log.get_latest_sequence = AsyncMock(return_value=10)
        mock_event_log.get_events = AsyncMock(return_value=[])
        mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=11)])

        mock_result = {"success": True, "output": "ok", "tokens": 10, "cost": 0.01}

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_event_log,
            ),
            patch.object(ne, "_dispatch", new_callable=AsyncMock, return_value=mock_result),
        ):
            await ne.execute(db, node, {}, budget, run_id, workflow)

        # Verify get_events was called with limit=5
        mock_event_log.get_events.assert_called_once()
        call_kwargs = mock_event_log.get_events.call_args[1]
        assert call_kwargs["limit"] == 5
