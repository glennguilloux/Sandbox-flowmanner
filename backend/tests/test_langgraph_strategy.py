"""Unit tests for LangGraphStrategy (app/services/substrate/strategies/langgraph.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.substrate.strategies.langgraph import LangGraphStrategy
from app.services.substrate.workflow_models import (
    StrategyResult,
    Workflow,
    WorkflowNode,
    WorkflowType,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_langgraph_workflow(
    node_count=1,
    graph_name="test_graph",
    metadata=None,
):
    nodes = [
        WorkflowNode(
            id=f"lg{i}",
            type="llm_call",
            title=f"LangGraph Node {i}",
            config={"graph_name": graph_name},
        )
        for i in range(node_count)
    ]
    return Workflow(
        id=str(uuid4()),
        type=WorkflowType.LANGGRAPH,
        title="LangGraph Test",
        nodes=nodes,
        edges=[],
        user_id="1",
        metadata=metadata or {},
    )


def _make_executor():
    executor = MagicMock()
    executor.is_aborted = MagicMock(return_value=False)
    executor.execute_node = AsyncMock(
        return_value={
            "success": True,
            "output": {"text": "Fallback output"},
            "tokens": 30,
            "cost": 0.03,
        }
    )
    return executor


# ── can_handle ───────────────────────────────────────────────────────


class TestLangGraphCanHandle:
    def test_handles_langgraph(self):
        s = LangGraphStrategy()
        assert s.can_handle(WorkflowType.LANGGRAPH) is True

    def test_rejects_solo(self):
        s = LangGraphStrategy()
        assert s.can_handle(WorkflowType.SOLO) is False

    def test_rejects_dag(self):
        s = LangGraphStrategy()
        assert s.can_handle(WorkflowType.DAG) is False

    def test_rejects_graph(self):
        s = LangGraphStrategy()
        assert s.can_handle(WorkflowType.GRAPH) is False

    def test_rejects_swarm(self):
        s = LangGraphStrategy()
        assert s.can_handle(WorkflowType.SWARM) is False

    def test_rejects_pipeline(self):
        s = LangGraphStrategy()
        assert s.can_handle(WorkflowType.PIPELINE) is False

    def test_rejects_meta(self):
        s = LangGraphStrategy()
        assert s.can_handle(WorkflowType.META) is False


# ── validate ─────────────────────────────────────────────────────────


class TestLangGraphValidate:
    @pytest.mark.asyncio
    async def test_valid_workflow(self):
        s = LangGraphStrategy()
        wf = _make_langgraph_workflow()
        errors = await s.validate(wf)
        assert errors == []

    @pytest.mark.asyncio
    async def test_empty_nodes_rejected(self):
        s = LangGraphStrategy()
        wf = _make_langgraph_workflow(node_count=0)
        errors = await s.validate(wf)
        assert any("at least 1 node" in e for e in errors)

    @pytest.mark.asyncio
    async def test_missing_graph_name(self):
        s = LangGraphStrategy()
        wf = Workflow(
            id=str(uuid4()),
            type=WorkflowType.LANGGRAPH,
            title="Bad",
            nodes=[WorkflowNode(id="n1", type="llm_call", title="No graph name", config={})],
            user_id="1",
        )
        errors = await s.validate(wf)
        assert any("graph_name" in e for e in errors)

    @pytest.mark.asyncio
    async def test_multiple_nodes_all_with_graph_name(self):
        s = LangGraphStrategy()
        wf = _make_langgraph_workflow(node_count=3, graph_name="my_agent")
        errors = await s.validate(wf)
        assert errors == []

    @pytest.mark.asyncio
    async def test_one_node_missing_graph_name(self):
        s = LangGraphStrategy()
        nodes = [
            WorkflowNode(id="good", type="llm_call", title="Good", config={"graph_name": "g"}),
            WorkflowNode(id="bad", type="llm_call", title="Bad", config={}),
        ]
        wf = Workflow(
            id=str(uuid4()),
            type=WorkflowType.LANGGRAPH,
            title="Mixed",
            nodes=nodes,
            user_id="1",
        )
        errors = await s.validate(wf)
        assert len(errors) == 1
        assert "bad" in errors[0]


# ── execute ──────────────────────────────────────────────────────────


class TestLangGraphExecute:
    @pytest.mark.asyncio
    async def test_native_fails_fallback_succeeds(self):
        """Native LangGraph execution fails → falls back to shared executor."""
        s = LangGraphStrategy()
        wf = _make_langgraph_workflow(node_count=1)
        db = AsyncMock()
        executor = _make_executor()

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        assert result.status == "completed"
        assert len(result.completed_nodes) == 1
        assert result.total_tokens == 30
        assert result.total_cost_usd == pytest.approx(0.03)
        executor.execute_node.assert_called_once()

    @pytest.mark.asyncio
    async def test_native_fails_fallback_also_fails(self):
        """Both native and fallback fail → node in failed list."""
        s = LangGraphStrategy()
        wf = _make_langgraph_workflow(node_count=1)
        db = AsyncMock()
        executor = _make_executor()
        executor.execute_node = AsyncMock(
            return_value={
                "success": False,
                "error": "Fallback also failed",
            }
        )

        result = await s.execute(wf, {}, executor, db)

        assert result.success is False
        assert result.status == "failed"
        assert "lg0" in result.failed_nodes
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_aborted(self):
        s = LangGraphStrategy()
        wf = _make_langgraph_workflow(node_count=1)
        db = AsyncMock()
        executor = _make_executor()
        executor.is_aborted = MagicMock(return_value=True)

        result = await s.execute(wf, {}, executor, db)

        assert result.success is False
        assert result.status == "aborted"
        executor.execute_node.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_multiple_nodes(self):
        """Multiple nodes, all succeed via fallback."""
        s = LangGraphStrategy()
        wf = _make_langgraph_workflow(node_count=3)
        db = AsyncMock()
        executor = _make_executor()

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        assert len(result.completed_nodes) == 3
        assert executor.execute_node.call_count == 3
        assert result.total_tokens == 90

    @pytest.mark.asyncio
    async def test_execute_mixed_success_failure(self):
        """Some nodes succeed, some fail."""
        s = LangGraphStrategy()
        wf = _make_langgraph_workflow(node_count=3)
        db = AsyncMock()
        executor = _make_executor()

        call_count = 0

        async def alternating(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return {"success": False, "error": "Node 1 failed"}
            return {
                "success": True,
                "output": {"text": "ok"},
                "tokens": 10,
                "cost": 0.01,
            }

        executor.execute_node = AsyncMock(side_effect=alternating)

        result = await s.execute(wf, {}, executor, db)

        assert result.success is False
        assert len(result.completed_nodes) == 2
        assert len(result.failed_nodes) == 1
        assert "lg1" in result.failed_nodes

    @pytest.mark.asyncio
    async def test_execute_with_substrate_run_id(self):
        s = LangGraphStrategy()
        wf = _make_langgraph_workflow(
            node_count=1,
            metadata={"substrate_run_id": "lg-run-1"},
        )
        db = AsyncMock()
        executor = _make_executor()

        await s.execute(wf, {}, executor, db)

        call_kwargs = executor.execute_node.call_args[1]
        assert call_kwargs["run_id"] == "lg-run-1"

    @pytest.mark.asyncio
    async def test_execute_aborted_between_nodes(self):
        """Aborted detected between sequential node executions.

        Note: LangGraphStrategy's abort path returns a fresh StrategyResult
        without propagating completed_nodes (unlike GraphStrategy), so the
        result has empty completed_nodes.
        """
        s = LangGraphStrategy()
        wf = _make_langgraph_workflow(node_count=3)
        db = AsyncMock()
        executor = _make_executor()

        nodes_executed = []

        def abort_after_first_completed(rid):
            return len(nodes_executed) >= 1

        executor.is_aborted = MagicMock(side_effect=abort_after_first_completed)

        async def track_and_succeed(*args, **kwargs):
            nodes_executed.append("x")
            return {
                "success": True,
                "output": {"text": "ok"},
                "tokens": 10,
                "cost": 0.01,
            }

        executor.execute_node = AsyncMock(side_effect=track_and_succeed)

        # Patch _execute_langgraph_node to always return failure so the fallback path runs
        async def native_fails(*args, **kwargs):
            return {"success": False, "error": "native not available"}

        with patch.object(s, "_execute_langgraph_node", side_effect=native_fails):
            result = await s.execute(wf, {}, executor, db)

        assert result.success is False
        assert result.status == "aborted"
        # The first node was executed via fallback before abort was detected
        assert len(nodes_executed) == 1
        # But LangGraphStrategy's abort path doesn't propagate completed_nodes
        assert len(result.completed_nodes) == 0


# ── _execute_langgraph_node ─────────────────────────────────────────


class TestExecuteLangGraphNode:
    @pytest.mark.asyncio
    async def test_import_error_returns_not_available(self):
        """When LangGraph module is not importable, returns error."""
        s = LangGraphStrategy()
        node = WorkflowNode(
            id="n1",
            type="llm_call",
            title="N1",
            config={"graph_name": "test"},
        )
        wf = _make_langgraph_workflow()
        executor = MagicMock()
        db = AsyncMock()

        with patch.dict(
            "sys.modules",
            {"app.services.langgraph": None, "app.services.langgraph.agent": None},
        ):
            result = await s._execute_langgraph_node(
                node,
                {},
                executor,
                db,
                "run-1",
                wf,
            )

        assert result["success"] is False
        assert (
            "not found" in result["error"].lower()
            or "not available" in result["error"].lower()
            or "import" in result["error"].lower()
            or "module" in result["error"].lower()
        )

    @pytest.mark.asyncio
    async def test_native_not_wired_returns_error(self):
        """When LangGraph module is available but native execution isn't wired."""
        s = LangGraphStrategy()
        node = WorkflowNode(
            id="n1",
            type="llm_call",
            title="N1",
            config={"graph_name": "test"},
        )
        wf = _make_langgraph_workflow()
        executor = MagicMock()
        db = AsyncMock()

        # Mock the import to succeed (LangGraphAgent exists)
        mock_module = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "app.services.langgraph": mock_module,
                "app.services.langgraph.agent": mock_module,
            },
        ):
            result = await s._execute_langgraph_node(
                node,
                {},
                executor,
                db,
                "run-1",
                wf,
            )

        assert result["success"] is False
        assert "not found" in result["error"].lower() or "shared executor" in result["error"].lower()
