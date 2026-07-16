"""Unit tests for SoloStrategy (app/services/substrate/strategies/solo.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.capability_models import Budget
from app.services.substrate.strategies.solo import SoloStrategy
from app.services.substrate.workflow_models import (
    StrategyResult,
    Workflow,
    WorkflowNode,
    WorkflowType,
)


def _make_solo_workflow(node_count: int = 1):
    nodes = [WorkflowNode(id=f"n{i}", type="llm_call", title=f"Node {i}") for i in range(node_count)]
    return Workflow(
        id=str(uuid4()),
        type=WorkflowType.SOLO,
        title="Solo Test",
        nodes=nodes,
        edges=[],
        user_id="1",
    )


class TestSoloCanHandle:
    def test_handles_solo(self):
        strategy = SoloStrategy()
        assert strategy.can_handle(WorkflowType.SOLO) is True

    def test_rejects_dag(self):
        strategy = SoloStrategy()
        assert strategy.can_handle(WorkflowType.DAG) is False

    def test_rejects_graph(self):
        strategy = SoloStrategy()
        assert strategy.can_handle(WorkflowType.GRAPH) is False


class TestSoloValidate:
    @pytest.mark.asyncio
    async def test_valid_single_node_no_edges(self):
        strategy = SoloStrategy()
        wf = _make_solo_workflow(node_count=1)
        errors = await strategy.validate(wf)
        assert errors == []

    @pytest.mark.asyncio
    async def test_rejects_multiple_nodes(self):
        strategy = SoloStrategy()
        wf = _make_solo_workflow(node_count=3)
        errors = await strategy.validate(wf)
        assert len(errors) == 1
        assert "exactly 1 node" in errors[0]

    @pytest.mark.asyncio
    async def test_rejects_edges(self):
        strategy = SoloStrategy()
        from app.services.substrate.workflow_models import WorkflowEdge

        wf = _make_solo_workflow(node_count=1)
        wf.edges = [WorkflowEdge(source="n0", target="n0")]
        errors = await strategy.validate(wf)
        assert len(errors) >= 1
        assert any("no edges" in e for e in errors)


class TestSoloExecute:
    @pytest.mark.asyncio
    async def test_execute_success(self):
        strategy = SoloStrategy()
        wf = _make_solo_workflow()
        db = AsyncMock()

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(return_value=False)
        mock_executor.execute_node = AsyncMock(
            return_value={
                "success": True,
                "output": {"text": "Done"},
                "tokens": 42,
                "cost": 0.03,
            }
        )

        result = await strategy.execute(wf, {}, mock_executor, db, run_id="test-run-solo")

        assert result.success is True
        assert result.status == "completed"
        assert result.total_tokens == 42
        assert result.total_cost_usd == 0.03
        assert wf.nodes[0].id in result.completed_nodes
        assert result.failed_nodes == []

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        strategy = SoloStrategy()
        wf = _make_solo_workflow()
        db = AsyncMock()

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(return_value=False)
        mock_executor.execute_node = AsyncMock(
            return_value={
                "success": False,
                "error": "LLM call failed",
            }
        )

        result = await strategy.execute(wf, {}, mock_executor, db, run_id="test-run-solo")

        assert result.success is False
        assert result.status == "failed"
        assert result.error == "LLM call failed"
        assert wf.nodes[0].id in result.failed_nodes

    @pytest.mark.asyncio
    async def test_execute_aborted(self):
        strategy = SoloStrategy()
        wf = _make_solo_workflow()
        db = AsyncMock()

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(return_value=True)

        result = await strategy.execute(wf, {}, mock_executor, db, run_id="test-run-solo")

        assert result.success is False
        assert result.status == "aborted"
        mock_executor.execute_node.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_uses_substrate_run_id_from_metadata(self):
        strategy = SoloStrategy()
        wf = _make_solo_workflow()
        wf.metadata["substrate_run_id"] = "custom-run-id"
        db = AsyncMock()

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(return_value=False)
        mock_executor.execute_node = AsyncMock(return_value={"success": True, "output": "ok"})

        await strategy.execute(wf, {}, mock_executor, db, run_id="custom-run-id")

        # Verify the run_id was passed to execute_node
        call_kwargs = mock_executor.execute_node.call_args[1]
        assert call_kwargs["run_id"] == "custom-run-id"
