"""Unit tests for UnifiedExecutor (app/services/substrate/executor.py)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.substrate.workflow_models import (
    StrategyResult,
    Workflow,
    WorkflowNode,
    WorkflowType,
)


def _make_workflow(wtype: WorkflowType = WorkflowType.SOLO) -> Workflow:
    return Workflow(
        id=str(uuid4()),
        type=wtype,
        title="Test Workflow",
        nodes=[WorkflowNode(id="n1", type="llm_call", title="Test Node")],
        user_id="1",
    )


def _make_mock_executor():
    from app.services.substrate.executor import UnifiedExecutor

    event_log = MagicMock()
    event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])
    event_log.get_latest_sequence = AsyncMock(return_value=0)
    event_log.run_exists = AsyncMock(return_value=False)

    replay_engine = MagicMock()
    replay_engine.rebuild_state = AsyncMock(return_value=None)
    replay_engine.get_checkpoint_sequences = AsyncMock(return_value=[])

    executor = UnifiedExecutor(event_log=event_log, replay_engine=replay_engine)
    return executor, event_log, replay_engine


class TestUnifiedExecutorInit:
    def test_init_creates_event_log_and_replay_engine(self):
        from app.services.substrate.executor import UnifiedExecutor

        executor = UnifiedExecutor()
        assert executor.event_log is not None
        assert executor.replay_engine is not None

    def test_get_unified_executor_returns_singleton(self):
        from app.services.substrate.executor import get_unified_executor

        e1 = get_unified_executor()
        e2 = get_unified_executor()
        assert e1 is e2

    def test_init_accepts_custom_event_log_and_replay_engine(self):
        from app.services.substrate.executor import UnifiedExecutor

        mock_el = MagicMock()
        mock_re = MagicMock()
        executor = UnifiedExecutor(event_log=mock_el, replay_engine=mock_re)
        assert executor.event_log is mock_el
        assert executor.replay_engine is mock_re


class TestStrategyLoading:
    def test_load_strategies_populates_internal_dict(self):
        executor, _, _ = _make_mock_executor()
        executor._load_strategies()
        assert isinstance(executor._strategies, dict)
        assert WorkflowType.SOLO in executor._strategies

    def test_all_workflow_types_have_strategies(self):
        executor, _, _ = _make_mock_executor()
        executor._load_strategies()
        for wtype in WorkflowType:
            assert wtype in executor._strategies


class TestAbortAndRunningState:
    def test_is_aborted_returns_false_initially(self):
        executor, _, _ = _make_mock_executor()
        assert executor.is_aborted(str(uuid4())) is False

    @pytest.mark.asyncio
    async def test_abort_sets_signal(self):
        executor, _, _ = _make_mock_executor()
        run_id = str(uuid4())
        executor._abort_signals[run_id] = asyncio.Event()
        result = await executor.abort(run_id, reason="test_abort")
        assert executor._abort_signals[run_id].is_set() is True
        assert result is True

    @pytest.mark.asyncio
    async def test_abort_returns_false_for_already_aborted(self):
        executor, _, _ = _make_mock_executor()
        run_id = str(uuid4())
        event = asyncio.Event()
        event.set()
        executor._abort_signals[run_id] = event
        result = await executor.abort(run_id, reason="test")
        assert result is False


class TestExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_strategy_result(self):
        executor, event_log, _ = _make_mock_executor()
        workflow = _make_workflow()
        db = AsyncMock()

        mock_strategy = MagicMock()
        mock_strategy.validate = AsyncMock(return_value=[])
        mock_strategy.execute = AsyncMock(
            return_value=StrategyResult(success=True, status="completed", total_tokens=100, total_cost_usd=0.05)
        )

        with patch.object(executor, "_get_strategy", return_value=mock_strategy):
            result = await executor.execute(db, workflow)

        assert result.success is True
        assert result.status == "completed"
        assert result.total_tokens == 100

    @pytest.mark.asyncio
    async def test_execute_handles_strategy_failure(self):
        executor, _, _ = _make_mock_executor()
        workflow = _make_workflow()
        db = AsyncMock()

        mock_strategy = MagicMock()
        mock_strategy.validate = AsyncMock(return_value=[])
        mock_strategy.execute = AsyncMock(
            return_value=StrategyResult(success=False, status="failed", error="Something went wrong")
        )

        with patch.object(executor, "_get_strategy", return_value=mock_strategy):
            result = await executor.execute(db, workflow)

        assert result.success is False
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self):
        executor, _, _ = _make_mock_executor()
        workflow = _make_workflow()
        db = AsyncMock()

        mock_strategy = MagicMock()
        mock_strategy.validate = AsyncMock(return_value=[])
        mock_strategy.execute = AsyncMock(side_effect=RuntimeError("boom"))

        with patch.object(executor, "_get_strategy", return_value=mock_strategy):
            result = await executor.execute(db, workflow)

        assert result.success is False
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_execute_logs_mission_started_event(self):
        executor, event_log, _ = _make_mock_executor()
        workflow = _make_workflow()
        db = AsyncMock()

        mock_strategy = MagicMock()
        mock_strategy.validate = AsyncMock(return_value=[])
        mock_strategy.execute = AsyncMock(return_value=StrategyResult(success=True, status="completed"))

        with patch.object(executor, "_get_strategy", return_value=mock_strategy):
            await executor.execute(db, workflow)

        event_log.append.assert_called()
        first_events = event_log.append.call_args_list[0][0][2]
        assert any(e.get("type") == "mission.started" for e in first_events)

    @pytest.mark.asyncio
    async def test_execute_validation_failure_returns_early(self):
        executor, _, _ = _make_mock_executor()
        workflow = _make_workflow()
        db = AsyncMock()

        mock_strategy = MagicMock()
        mock_strategy.validate = AsyncMock(return_value=["Missing start node", "No end node"])

        with patch.object(executor, "_get_strategy", return_value=mock_strategy):
            result = await executor.execute(db, workflow)

        assert result.success is False
        assert result.status == "failed"
        assert "Missing start node" in result.error


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_check_circuit_breaker_returns_tuple(self):
        executor, _, _ = _make_mock_executor()
        db = AsyncMock()

        mock_cb = MagicMock()
        mock_cb.is_circuit_open = AsyncMock(return_value=True)

        with patch(
            "app.services.circuit_breaker_service.CircuitBreakerService",
            return_value=mock_cb,
        ):
            result = await executor.check_circuit_breaker(db, "m1")
            assert isinstance(result, tuple)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_check_circuit_breaker_allowed_when_closed(self):
        executor, _, _ = _make_mock_executor()
        db = AsyncMock()

        mock_cb = MagicMock()
        mock_cb.is_circuit_open = AsyncMock(return_value=False)

        with patch(
            "app.services.circuit_breaker_service.CircuitBreakerService",
            return_value=mock_cb,
        ):
            allowed, reason = await executor.check_circuit_breaker(db, "m1")
            assert allowed is True

    @pytest.mark.asyncio
    async def test_record_circuit_breaker_call_records_when_breaker_exists(self):
        executor, _, _ = _make_mock_executor()
        db = AsyncMock()
        # begin_nested must return a valid async context manager
        db.begin_nested = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))

        mock_breaker = MagicMock()
        mock_cb = MagicMock()
        mock_cb.get_breaker = AsyncMock(return_value=mock_breaker)
        mock_cb.record_call = AsyncMock()

        with patch(
            "app.services.circuit_breaker_service.CircuitBreakerService",
            return_value=mock_cb,
        ):
            await executor.record_circuit_breaker_call(db, "m1", call_type="llm", cost_usd=0.01)

        # Verify record_call was invoked with the breaker and correct args
        mock_cb.record_call.assert_called_once()
        call_kwargs = mock_cb.record_call.call_args
        assert call_kwargs[0][0] is mock_breaker
        assert call_kwargs[1]["call_type"] == "llm"
        assert call_kwargs[1]["cost_usd"] == 0.01


class TestCallLLM:
    @pytest.mark.asyncio
    async def test_call_llm_delegates_to_budget_enforcer(self):
        executor, _, _ = _make_mock_executor()
        db = AsyncMock()

        mock_response = {
            "success": True,
            "response": "Hello",
            "budget": {"prompt_tokens": 10, "completion_tokens": 5, "cost_usd": 0.01},
        }

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(return_value=mock_response)

        budget = MagicMock()

        with patch(
            "app.services.budget_enforcer.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            result = await executor.call_llm(
                budget=budget,
                model_id="test-model",
                messages=[{"role": "user", "content": "hi"}],
                db_session=db,
            )

        assert result["success"] is True
        assert result["response"] == "Hello"
