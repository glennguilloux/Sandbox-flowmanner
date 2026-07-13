"""Regression tests for Comment 1 — run ID unification.

UnifiedExecutor.execute() is the ONLY source of the run ID. Every strategy
must receive that run_id (never generate or read its own from
workflow.metadata). These tests assert the contract that mission.started,
node events, LLM events, and terminal events for one execution all share
exactly the same run_id.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.capability_models import Budget
from app.services.substrate.executor import UnifiedExecutor
from app.services.substrate.strategies.solo import SoloStrategy
from app.services.substrate.workflow_models import (
    StrategyResult,
    Workflow,
    WorkflowNode,
    WorkflowType,
)


def _make_solo_workflow() -> Workflow:
    node = WorkflowNode(
        id="n1",
        type=__import__("app.services.substrate.workflow_models", fromlist=["NodeType"]).NodeType.LLM_CALL,
        title="say hi",
        config={"prompt": "hello"},
        effect_class=__import__(
            "app.services.substrate.workflow_models", fromlist=["EffectClass"]
        ).EffectClass.REVERSIBLE,
    )
    budget = Budget(
        max_cost_usd=Decimal("1.00"),
        max_wall_time_seconds=60,
        max_iterations=5,
        max_depth=1,
    )
    return Workflow(
        id="wf-1",
        type=WorkflowType.SOLO,
        title="solo",
        nodes=[node],
        budget=budget,
        user_id="u1",
        # Intentionally include a bogus metadata run_id; strategies must IGNORE it.
        metadata={"substrate_run_id": "should-be-ignored"},
    )


class TestSoloStrategyUsesPassedRunId:
    """SoloStrategy must use the run_id passed by the executor, not generate one."""

    async def test_solo_uses_passed_run_id_not_metadata(self):
        strategy = SoloStrategy()
        run_id = "run-fixed-1234"

        executor = MagicMock()
        executor.is_aborted.return_value = False
        captured = {}

        async def fake_execute_node(db, node, context, budget, run_id, workflow=None):
            captured["run_id"] = run_id
            return {"success": True, "output": "ok", "tokens": 1, "cost": 0.0}

        executor.execute_node = fake_execute_node

        result = await strategy.execute(
            _make_solo_workflow(),
            {},
            executor,
            MagicMock(),
            run_id,
        )

        assert result.success is True
        # The run_id the strategy passed downstream equals the one it received.
        assert captured["run_id"] == run_id
        # It must NOT have fallen back to the bogus metadata id.
        assert captured["run_id"] != "should-be-ignored"


class TestUnifiedExecutorOwnsRunId:
    """The executor resolves a single run_id and threads it into the strategy."""

    @patch("app.services.substrate.executor.get_replay_engine")
    @patch("app.services.substrate.executor.get_event_log")
    async def test_executor_threads_single_run_id(self, mock_get_log, mock_get_replay):
        # In-memory event log capturing every appended event's run_id.
        appended_run_ids: list[str] = []

        log = MagicMock()
        log.run_exists = AsyncMock(return_value=False)
        log.get_events = AsyncMock(return_value=[])
        log.get_latest_sequence = AsyncMock(return_value=0)
        log.append = AsyncMock(side_effect=lambda db, rid, *a, **k: appended_run_ids.append(rid))
        mock_get_log.return_value = log
        mock_get_replay.return_value = MagicMock()

        executor = UnifiedExecutor(event_log=log, replay_engine=MagicMock())

        # Stub lease + circuit breaker + strategy so execute() reaches strategy call.
        executor._lease_context = MagicMock()
        executor._lease_context.__aenter__ = AsyncMock(return_value=None)
        executor._lease_context.__aexit__ = AsyncMock(return_value=False)
        executor._ensure_circuit_breaker = AsyncMock()
        executor._finalize_run = AsyncMock()

        # These attributes are normally set by _lease_context(); the executor
        # reads them inside the context, so define them to avoid AttributeError.
        executor._lease_already_running = None
        executor._lease_manager = None

        strategy = MagicMock()
        strategy.validate = AsyncMock(return_value=[])
        captured = {}

        async def fake_strategy_execute(workflow, context, exec_, db, run_id):
            captured["run_id"] = run_id
            return StrategyResult(
                success=True, status="completed", completed_nodes=["n1"], total_tokens=1, total_cost_usd=0.0
            )

        strategy.execute = fake_strategy_execute
        executor._get_strategy = MagicMock(return_value=strategy)

        # Use a deterministic run_id by passing one explicitly.
        run_id = "run-executor-owned-999"
        result = await executor.execute(
            db=MagicMock(),
            workflow=_make_solo_workflow(),
            run_id=run_id,
        )

        assert result.success is True
        # The strategy received exactly the executor's run_id.
        assert captured["run_id"] == run_id
        # Every event the executor emitted carries the same run_id.
        assert appended_run_ids, "executor emitted no events"
        assert all(r == run_id for r in appended_run_ids)
