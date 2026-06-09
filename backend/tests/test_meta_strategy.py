"""Unit tests for MetaStrategy (app/services/substrate/strategies/meta.py)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.capability_models import Budget
from app.services.substrate.strategies.meta import MetaStrategy
from app.services.substrate.workflow_models import (
    NodeType,
    StrategyResult,
    Workflow,
    WorkflowNode,
    WorkflowType,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_meta_workflow(
    node_count=2,
    max_depth=5,
    metadata=None,
):
    nodes = [
        WorkflowNode(id=f"sw{i}", type=NodeType.SUB_WORKFLOW, title=f"Sub {i}")
        for i in range(node_count)
    ]
    budget = Budget(
        max_cost_usd=Decimal("10.00"),
        max_wall_time_seconds=300,
        max_iterations=100,
        max_depth=max_depth,
    )
    return Workflow(
        id=str(uuid4()),
        type=WorkflowType.META,
        title="Meta Test",
        description="Test meta workflow",
        nodes=nodes,
        edges=[],
        budget=budget,
        user_id="1",
        metadata=metadata or {},
    )


def _make_executor(is_aborted=False):
    executor = MagicMock()
    executor.is_aborted = MagicMock(return_value=is_aborted)
    executor.execute_node = AsyncMock(
        return_value={
            "success": True,
            "output": {"text": "Done"},
            "tokens": 20,
            "cost": 0.02,
        }
    )
    return executor


# ── can_handle ───────────────────────────────────────────────────────


class TestMetaCanHandle:
    def test_handles_meta(self):
        s = MetaStrategy()
        assert s.can_handle(WorkflowType.META) is True

    def test_rejects_solo(self):
        s = MetaStrategy()
        assert s.can_handle(WorkflowType.SOLO) is False

    def test_rejects_dag(self):
        s = MetaStrategy()
        assert s.can_handle(WorkflowType.DAG) is False

    def test_rejects_swarm(self):
        s = MetaStrategy()
        assert s.can_handle(WorkflowType.SWARM) is False

    def test_rejects_graph(self):
        s = MetaStrategy()
        assert s.can_handle(WorkflowType.GRAPH) is False

    def test_rejects_pipeline(self):
        s = MetaStrategy()
        assert s.can_handle(WorkflowType.PIPELINE) is False


# ── validate ─────────────────────────────────────────────────────────


class TestMetaValidate:
    @pytest.mark.asyncio
    async def test_valid_meta(self):
        s = MetaStrategy()
        wf = _make_meta_workflow()
        errors = await s.validate(wf)
        assert errors == []

    @pytest.mark.asyncio
    async def test_no_sub_workflow_nodes(self):
        s = MetaStrategy()
        wf = Workflow(
            id=str(uuid4()),
            type=WorkflowType.META,
            title="Bad Meta",
            nodes=[WorkflowNode(id="n1", type="llm_call", title="Not sub")],
            user_id="1",
        )
        errors = await s.validate(wf)
        assert any("SUB_WORKFLOW" in e for e in errors)

    @pytest.mark.asyncio
    async def test_multiple_sub_workflows_valid(self):
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=5)
        errors = await s.validate(wf)
        assert errors == []

    @pytest.mark.asyncio
    async def test_mixed_node_types_with_one_sub(self):
        s = MetaStrategy()
        wf = Workflow(
            id=str(uuid4()),
            type=WorkflowType.META,
            title="Mixed",
            nodes=[
                WorkflowNode(id="n1", type="llm_call", title="LLM"),
                WorkflowNode(id="sw1", type=NodeType.SUB_WORKFLOW, title="Sub"),
            ],
            user_id="1",
        )
        errors = await s.validate(wf)
        assert errors == []


# ── execute ──────────────────────────────────────────────────────────


class TestMetaExecute:
    @pytest.mark.asyncio
    async def test_execute_all_nodes_succeed(self):
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=2)
        db = AsyncMock()
        executor = _make_executor()

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        assert result.success is True
        assert result.status == "completed"
        assert len(result.completed_nodes) == 2
        assert result.total_tokens == 40
        assert result.total_cost_usd == pytest.approx(0.04)

    @pytest.mark.asyncio
    async def test_execute_single_node(self):
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=1)
        db = AsyncMock()
        executor = _make_executor()

        result = await s.execute(wf, {"goal": "Solo"}, executor, db)

        assert result.success is True
        assert len(result.completed_nodes) == 1

    @pytest.mark.asyncio
    async def test_execute_aborted(self):
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=1)
        db = AsyncMock()
        executor = _make_executor(is_aborted=True)

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        assert result.success is False
        assert result.status == "aborted"
        executor.execute_node.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_first_node_fails_retry_succeeds(self):
        """First node fails → retries at depth+1 with new goal."""
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=1, max_depth=3)
        db = AsyncMock()
        executor = _make_executor()

        call_count = 0

        async def fail_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"success": False, "error": "LLM error"}
            return {
                "success": True,
                "output": {"text": "Fixed"},
                "tokens": 10,
                "cost": 0.01,
            }

        executor.execute_node = AsyncMock(side_effect=fail_then_succeed)

        result = await s.execute(wf, {"goal": "Original"}, executor, db)

        assert result.success is True
        assert call_count == 2  # failed once, succeeded on retry

    @pytest.mark.asyncio
    async def test_execute_max_depth_reached(self):
        """Node fails at max_depth → returns failure (no more retries)."""
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=1, max_depth=2)
        db = AsyncMock()
        executor = _make_executor()
        executor.execute_node = AsyncMock(
            return_value={
                "success": False,
                "error": "Persistent failure",
            }
        )

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        assert result.success is False
        assert result.status == "failed"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_depth_limit_clamps_execution(self):
        """max_depth=1 → depth 0 runs, any failure immediately stops."""
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=1, max_depth=1)
        db = AsyncMock()
        executor = _make_executor()
        executor.execute_node = AsyncMock(
            return_value={
                "success": False,
                "error": "Fail",
            }
        )

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        assert result.success is False
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_execute_max_depth_0_fails_immediately(self):
        """max_depth=0 → _run_cycle returns failed immediately."""
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=1, max_depth=0)
        db = AsyncMock()
        executor = _make_executor()

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        assert result.success is False
        assert "depth" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_aborted_between_nodes(self):
        """Aborted detected between node executions within a cycle."""
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=2)
        db = AsyncMock()
        executor = _make_executor()

        call_count = 0

        def abort_after_first(rid):
            nonlocal call_count
            return call_count >= 1

        executor.is_aborted = MagicMock(side_effect=abort_after_first)

        async def count_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {
                "success": True,
                "output": {"text": "ok"},
                "tokens": 10,
                "cost": 0.01,
            }

        executor.execute_node = AsyncMock(side_effect=count_calls)

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        assert result.success is False
        assert result.status == "aborted"

    @pytest.mark.asyncio
    async def test_execute_uses_goal_from_description(self):
        """When no goal in context, falls back to workflow description."""
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=1)
        db = AsyncMock()
        executor = _make_executor()

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        call_kwargs = executor.execute_node.call_args[1]
        assert call_kwargs["context"]["goal"] == "Test meta workflow"

    @pytest.mark.asyncio
    async def test_execute_uses_title_as_goal(self):
        """When no goal and no description, uses title."""
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=1)
        wf.description = None
        db = AsyncMock()
        executor = _make_executor()

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        call_kwargs = executor.execute_node.call_args[1]
        assert call_kwargs["context"]["goal"] == "Meta Test"

    @pytest.mark.asyncio
    async def test_execute_passes_depth_in_context(self):
        """Each node gets depth in its context."""
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=1)
        db = AsyncMock()
        executor = _make_executor()

        await s.execute(wf, {"goal": "Test"}, executor, db)

        call_kwargs = executor.execute_node.call_args[1]
        assert call_kwargs["context"]["depth"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_substrate_run_id(self):
        s = MetaStrategy()
        wf = _make_meta_workflow(
            node_count=1, metadata={"substrate_run_id": "meta-run-1"}
        )
        db = AsyncMock()
        executor = _make_executor()

        await s.execute(wf, {}, executor, db)

        call_kwargs = executor.execute_node.call_args[1]
        assert call_kwargs["run_id"] == "meta-run-1"

    @pytest.mark.asyncio
    async def test_execute_retry_includes_previous_error_in_context(self):
        """Retry cycle includes previous_error in context."""
        s = MetaStrategy()
        wf = _make_meta_workflow(node_count=1, max_depth=3)
        db = AsyncMock()
        executor = _make_executor()

        contexts_seen = []

        async def capture_and_succeed(*args, **kwargs):
            contexts_seen.append(kwargs.get("context", {}))
            if len(contexts_seen) == 1:
                return {"success": False, "error": "First failure"}
            return {
                "success": True,
                "output": {"text": "ok"},
                "tokens": 10,
                "cost": 0.01,
            }

        executor.execute_node = AsyncMock(side_effect=capture_and_succeed)

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        assert result.success is True
        assert contexts_seen[1].get("previous_error") == "First failure"
