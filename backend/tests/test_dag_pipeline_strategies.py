"""Unit tests for DAGStrategy and PipelineStrategy."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.substrate.strategies.dag import DAGStrategy
from app.services.substrate.strategies.pipeline import PipelineStrategy, PHASES
from app.services.substrate.workflow_models import (
    Workflow,
    WorkflowNode,
    WorkflowEdge,
    WorkflowType,
    NodeType,
    StrategyResult,
)


def _make_dag_workflow(nodes=None, edges=None):
    if nodes is None:
        nodes = [
            WorkflowNode(id="n1", type="llm_call", title="Node 1"),
            WorkflowNode(id="n2", type="llm_call", title="Node 2", dependencies=["n1"]),
        ]
    if edges is None:
        edges = [WorkflowEdge(source="n1", target="n2")]
    return Workflow(
        id=str(uuid4()),
        type=WorkflowType.DAG,
        title="DAG Test",
        nodes=nodes,
        edges=edges,
        user_id="1",
    )


def _make_pipeline_workflow():
    nodes = [
        WorkflowNode(
            id=f"p-{phase}",
            type="phase_gate",
            title=f"Phase: {phase}",
            config={"phase": phase},
        )
        for phase in PHASES
    ]
    return Workflow(
        id=str(uuid4()),
        type=WorkflowType.PIPELINE,
        title="Pipeline Test",
        nodes=nodes,
        edges=[],
        user_id="1",
    )


class TestDAGCanHandle:
    def test_handles_dag(self):
        s = DAGStrategy()
        assert s.can_handle(WorkflowType.DAG) is True

    def test_rejects_solo(self):
        s = DAGStrategy()
        assert s.can_handle(WorkflowType.SOLO) is False


class TestDAGValidate:
    @pytest.mark.asyncio
    async def test_valid_dag(self):
        s = DAGStrategy()
        wf = _make_dag_workflow()
        errors = await s.validate(wf)
        assert errors == []

    @pytest.mark.asyncio
    async def test_empty_nodes_rejected(self):
        s = DAGStrategy()
        wf = _make_dag_workflow(nodes=[], edges=[])
        errors = await s.validate(wf)
        assert any("at least 1 node" in e for e in errors)

    @pytest.mark.asyncio
    async def test_missing_edge_source(self):
        s = DAGStrategy()
        wf = _make_dag_workflow(
            nodes=[WorkflowNode(id="n1", type="llm_call", title="N1")],
            edges=[WorkflowEdge(source="missing", target="n1")],
        )
        errors = await s.validate(wf)
        assert any("source" in e and "missing" in e for e in errors)

    @pytest.mark.asyncio
    async def test_cycle_detected(self):
        s = DAGStrategy()
        wf = _make_dag_workflow(
            nodes=[
                WorkflowNode(id="a", type="llm_call", title="A"),
                WorkflowNode(id="b", type="llm_call", title="B"),
            ],
            edges=[
                WorkflowEdge(source="a", target="b"),
                WorkflowEdge(source="b", target="a"),
            ],
        )
        errors = await s.validate(wf)
        assert any("cycle" in e.lower() for e in errors)


class TestDAGExecute:
    @pytest.mark.asyncio
    async def test_execute_two_layer_dag(self):
        s = DAGStrategy()
        wf = _make_dag_workflow()
        db = AsyncMock()

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(return_value=False)
        mock_executor.execute_node = AsyncMock(
            return_value={
                "success": True,
                "output": "ok",
                "tokens": 10,
                "cost": 0.01,
            }
        )

        result = await s.execute(wf, {}, mock_executor, db)

        assert result.success is True
        assert result.status == "completed"
        assert len(result.completed_nodes) == 2
        assert result.total_tokens == 20

    @pytest.mark.asyncio
    async def test_execute_aborted_between_layers(self):
        s = DAGStrategy()
        wf = _make_dag_workflow()
        db = AsyncMock()

        call_count = 0

        def abort_after_first(rid):
            nonlocal call_count
            return call_count >= 1

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(side_effect=abort_after_first)

        async def mock_execute_node(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"success": True, "output": "ok", "tokens": 5, "cost": 0.01}

        mock_executor.execute_node = AsyncMock(side_effect=mock_execute_node)

        # Abort between layers — only layer 0 runs, layer 1 is aborted
        # But since abort_after_first checks call_count >= 1, and execute_node
        # is called once for n1 (layer 0), the is_aborted check for layer 1
        # will return True
        result = await s.execute(wf, {}, mock_executor, db)
        assert result.status == "aborted"
        assert "n1" in result.completed_nodes  # layer 0 node completed
        assert "n2" not in result.completed_nodes  # layer 1 was aborted
        assert result.total_tokens == 5

    @pytest.mark.asyncio
    async def test_execute_node_failure(self):
        s = DAGStrategy()
        wf = _make_dag_workflow()
        db = AsyncMock()

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(return_value=False)
        mock_executor.execute_node = AsyncMock(
            return_value={
                "success": False,
                "error": "boom",
            }
        )

        result = await s.execute(wf, {}, mock_executor, db)

        assert result.success is False
        assert "failed" in result.status.lower()
        assert len(result.failed_nodes) == 2


class TestDAGTopologicalSort:
    def test_single_node(self):
        s = DAGStrategy()
        wf = Workflow(
            id="x",
            type=WorkflowType.DAG,
            title="T",
            nodes=[WorkflowNode(id="solo", type="llm_call", title="S")],
            edges=[],
            user_id="1",
        )
        layers = s._topological_sort(wf)
        assert layers == [["solo"]]

    def test_two_layers(self):
        s = DAGStrategy()
        wf = _make_dag_workflow()
        layers = s._topological_sort(wf)
        assert layers[0] == ["n1"]
        assert layers[1] == ["n2"]

    def test_cycle_raises(self):
        s = DAGStrategy()
        wf = _make_dag_workflow(
            nodes=[
                WorkflowNode(id="a", type="llm_call", title="A"),
                WorkflowNode(id="b", type="llm_call", title="B"),
            ],
            edges=[
                WorkflowEdge(source="a", target="b"),
                WorkflowEdge(source="b", target="a"),
            ],
        )
        with pytest.raises(ValueError, match="cycle"):
            s._topological_sort(wf)


class TestPipelineCanHandle:
    def test_handles_pipeline(self):
        s = PipelineStrategy()
        assert s.can_handle(WorkflowType.PIPELINE) is True

    def test_rejects_dag(self):
        s = PipelineStrategy()
        assert s.can_handle(WorkflowType.DAG) is False


class TestPipelineValidate:
    @pytest.mark.asyncio
    async def test_valid_pipeline(self):
        s = PipelineStrategy()
        wf = _make_pipeline_workflow()
        errors = await s.validate(wf)
        assert errors == []

    @pytest.mark.asyncio
    async def test_empty_nodes(self):
        s = PipelineStrategy()
        wf = Workflow(
            id="x",
            type=WorkflowType.PIPELINE,
            title="T",
            nodes=[],
            edges=[],
            user_id="1",
        )
        errors = await s.validate(wf)
        assert any("at least 1 node" in e for e in errors)

    @pytest.mark.asyncio
    async def test_non_phase_gate_rejected(self):
        s = PipelineStrategy()
        wf = Workflow(
            id="x",
            type=WorkflowType.PIPELINE,
            title="T",
            nodes=[WorkflowNode(id="n1", type="llm_call", title="Bad")],
            edges=[],
            user_id="1",
        )
        errors = await s.validate(wf)
        assert any("PHASE_GATE" in e for e in errors)

    @pytest.mark.asyncio
    async def test_missing_phase_detected(self):
        s = PipelineStrategy()
        # Only include 6 of 7 phases
        nodes = [
            WorkflowNode(
                id=f"p-{phase}",
                type="phase_gate",
                title=f"Phase: {phase}",
                config={"phase": phase},
            )
            for phase in PHASES[:-1]  # drop "review"
        ]
        wf = Workflow(
            id="x",
            type=WorkflowType.PIPELINE,
            title="T",
            nodes=nodes,
            edges=[],
            user_id="1",
        )
        errors = await s.validate(wf)
        assert any("review" in e for e in errors)


class TestPipelineExecute:
    @pytest.mark.asyncio
    async def test_execute_pass_on_first_review(self):
        s = PipelineStrategy()
        wf = _make_pipeline_workflow()
        db = AsyncMock()

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(return_value=False)
        mock_executor.ws_manager = MagicMock()
        mock_executor.ws_manager.broadcast_phase = AsyncMock()
        mock_executor.execute_node = AsyncMock(
            return_value={
                "success": True,
                "output": {"verdict": "PASS"},
                "tokens": 10,
                "cost": 0.01,
            }
        )

        result = await s.execute(wf, {}, mock_executor, db)

        assert result.success is True
        assert len(result.completed_nodes) == 7
        assert result.total_tokens == 70

    @pytest.mark.asyncio
    async def test_execute_review_retry_then_pass(self):
        s = PipelineStrategy()
        wf = _make_pipeline_workflow()
        db = AsyncMock()

        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First review: FAIL with feedback, second review: PASS
            if call_count <= 7:
                return {
                    "success": True,
                    "output": {"verdict": "FAIL", "feedback": "needs work"},
                    "tokens": 10,
                    "cost": 0.01,
                }
            return {
                "success": True,
                "output": {"verdict": "PASS"},
                "tokens": 10,
                "cost": 0.01,
            }

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(return_value=False)
        mock_executor.ws_manager = MagicMock()
        mock_executor.ws_manager.broadcast_phase = AsyncMock()
        mock_executor.execute_node = AsyncMock(side_effect=mock_execute)

        result = await s.execute(wf, {}, mock_executor, db)

        assert result.success is True
        # 7 phases first pass + 4 retry phases (debate, consensus, synthesis, review) = 11
        assert call_count == 11

    @pytest.mark.asyncio
    async def test_execute_aborted(self):
        s = PipelineStrategy()
        wf = _make_pipeline_workflow()
        db = AsyncMock()

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(return_value=True)

        result = await s.execute(wf, {}, mock_executor, db)
        assert result.status == "aborted"

    @pytest.mark.asyncio
    async def test_execute_phase_failure(self):
        s = PipelineStrategy()
        wf = _make_pipeline_workflow()
        db = AsyncMock()

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(return_value=False)
        mock_executor.ws_manager = MagicMock()
        mock_executor.ws_manager.broadcast_phase = AsyncMock()
        mock_executor.execute_node = AsyncMock(
            return_value={
                "success": False,
                "error": "LLM unavailable",
            }
        )

        result = await s.execute(wf, {}, mock_executor, db)

        assert result.success is False
        assert "failed" in result.status.lower()

    @pytest.mark.asyncio
    async def test_execute_max_review_retries_exceeded(self):
        s = PipelineStrategy()
        wf = _make_pipeline_workflow()
        db = AsyncMock()

        mock_executor = MagicMock()
        mock_executor.is_aborted = MagicMock(return_value=False)
        mock_executor.ws_manager = MagicMock()
        mock_executor.ws_manager.broadcast_phase = AsyncMock()
        # Always return FAIL verdict
        mock_executor.execute_node = AsyncMock(
            return_value={
                "success": True,
                "output": {"verdict": "FAIL", "feedback": "still wrong"},
                "tokens": 10,
                "cost": 0.01,
            }
        )

        result = await s.execute(wf, {}, mock_executor, db)

        assert result.success is False
        assert "Max review retries" in result.error
