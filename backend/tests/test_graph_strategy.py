"""Unit tests for GraphStrategy (app/services/substrate/strategies/graph.py)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.substrate.strategies.graph import GraphStrategy
from app.services.substrate.workflow_models import (
    Workflow,
    WorkflowNode,
    WorkflowEdge,
    WorkflowType,
    StrategyResult,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_graph_workflow(
    nodes=None,
    edges=None,
    metadata=None,
    budget=None,
):
    if nodes is None:
        nodes = [
            WorkflowNode(id="n1", type="llm_call", title="Node 1"),
            WorkflowNode(id="n2", type="llm_call", title="Node 2"),
        ]
    if edges is None:
        edges = [WorkflowEdge(source="n1", target="n2")]
    wf = Workflow(
        id=str(uuid4()),
        type=WorkflowType.GRAPH,
        title="Graph Test",
        nodes=nodes,
        edges=edges,
        user_id="1",
        metadata=metadata or {},
    )
    if budget is not None:
        wf.budget = budget
    return wf


def _mock_executor(is_aborted=False):
    executor = MagicMock()
    executor.is_aborted = MagicMock(return_value=is_aborted)
    executor.execute_node = AsyncMock(
        return_value={
            "success": True,
            "output": {"text": "ok"},
            "tokens": 10,
            "cost": 0.01,
        }
    )
    return executor


# ── can_handle ───────────────────────────────────────────────────────


class TestGraphCanHandle:
    def test_handles_graph(self):
        s = GraphStrategy()
        assert s.can_handle(WorkflowType.GRAPH) is True

    def test_rejects_solo(self):
        s = GraphStrategy()
        assert s.can_handle(WorkflowType.SOLO) is False

    def test_rejects_dag(self):
        s = GraphStrategy()
        assert s.can_handle(WorkflowType.DAG) is False

    def test_rejects_pipeline(self):
        s = GraphStrategy()
        assert s.can_handle(WorkflowType.PIPELINE) is False


# ── validate ─────────────────────────────────────────────────────────


class TestGraphValidate:
    @pytest.mark.asyncio
    async def test_valid_graph(self):
        s = GraphStrategy()
        wf = _make_graph_workflow()
        errors = await s.validate(wf)
        assert errors == []

    @pytest.mark.asyncio
    async def test_empty_nodes_rejected(self):
        s = GraphStrategy()
        wf = _make_graph_workflow(nodes=[], edges=[])
        errors = await s.validate(wf)
        assert any("at least 1 node" in e for e in errors)

    @pytest.mark.asyncio
    async def test_missing_edge_source(self):
        s = GraphStrategy()
        wf = _make_graph_workflow(
            nodes=[WorkflowNode(id="n1", type="llm_call", title="N1")],
            edges=[WorkflowEdge(source="missing", target="n1")],
        )
        errors = await s.validate(wf)
        assert any("missing" in e.lower() for e in errors)

    @pytest.mark.asyncio
    async def test_missing_edge_target_still_validates(self):
        """Only source is validated; target missing is not caught by validate()."""
        s = GraphStrategy()
        wf = _make_graph_workflow(
            nodes=[WorkflowNode(id="n1", type="llm_call", title="N1")],
            edges=[WorkflowEdge(source="n1", target="missing")],
        )
        errors = await s.validate(wf)
        assert errors == []

    @pytest.mark.asyncio
    async def test_validates_with_multiple_edges(self):
        s = GraphStrategy()
        nodes = [
            WorkflowNode(id="a", type="llm_call", title="A"),
            WorkflowNode(id="b", type="llm_call", title="B"),
            WorkflowNode(id="c", type="llm_call", title="C"),
        ]
        edges = [
            WorkflowEdge(source="a", target="b"),
            WorkflowEdge(source="a", target="c"),
        ]
        wf = _make_graph_workflow(nodes=nodes, edges=edges)
        errors = await s.validate(wf)
        assert errors == []


# ── execute ──────────────────────────────────────────────────────────


class TestGraphExecute:
    @pytest.mark.asyncio
    async def test_execute_two_node_linear(self):
        s = GraphStrategy()
        wf = _make_graph_workflow()
        db = AsyncMock()
        executor = _mock_executor()

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        assert result.status == "completed"
        assert len(result.completed_nodes) == 2
        assert result.total_tokens == 20
        assert result.total_cost_usd == pytest.approx(0.02)

    @pytest.mark.asyncio
    async def test_execute_single_node_no_edges(self):
        s = GraphStrategy()
        wf = _make_graph_workflow(
            nodes=[WorkflowNode(id="solo", type="llm_call", title="Solo")],
            edges=[],
        )
        db = AsyncMock()
        executor = _mock_executor()

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        assert len(result.completed_nodes) == 1

    @pytest.mark.asyncio
    async def test_execute_aborted(self):
        s = GraphStrategy()
        wf = _make_graph_workflow(
            nodes=[WorkflowNode(id="a", type="llm_call", title="A")],
            edges=[],
        )
        db = AsyncMock()
        executor = _mock_executor(is_aborted=True)

        result = await s.execute(wf, {}, executor, db)

        assert result.success is False
        assert result.status == "aborted"
        executor.execute_node.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_node_failure(self):
        s = GraphStrategy()
        wf = _make_graph_workflow(
            nodes=[WorkflowNode(id="a", type="llm_call", title="A")],
            edges=[],
        )
        db = AsyncMock()
        executor = _mock_executor()
        executor.execute_node = AsyncMock(
            return_value={
                "success": False,
                "error": "boom",
            }
        )

        result = await s.execute(wf, {}, executor, db)

        assert result.success is False
        assert "a" in result.failed_nodes
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_node_exception(self):
        s = GraphStrategy()
        wf = _make_graph_workflow(
            nodes=[WorkflowNode(id="a", type="llm_call", title="A")],
            edges=[],
        )
        db = AsyncMock()
        executor = _mock_executor()
        executor.execute_node = AsyncMock(side_effect=RuntimeError("kaboom"))

        result = await s.execute(wf, {}, executor, db)

        assert result.success is False
        assert "a" in result.failed_nodes

    @pytest.mark.asyncio
    async def test_execute_with_substrate_run_id(self):
        s = GraphStrategy()
        wf = _make_graph_workflow(
            nodes=[WorkflowNode(id="a", type="llm_call", title="A")],
            edges=[],
            metadata={"substrate_run_id": "custom-run"},
        )
        db = AsyncMock()
        executor = _mock_executor()

        await s.execute(wf, {}, executor, db)

        call_kwargs = executor.execute_node.call_args[1]
        assert call_kwargs["run_id"] == "custom-run"

    @pytest.mark.asyncio
    async def test_execute_pause_detected(self):
        """When a node returns output with 'pause' key, execution stops."""
        s = GraphStrategy()
        wf = _make_graph_workflow(
            nodes=[
                WorkflowNode(id="a", type="llm_call", title="A"),
                WorkflowNode(id="b", type="llm_call", title="B"),
            ],
            edges=[WorkflowEdge(source="a", target="b")],
        )
        db = AsyncMock()
        executor = _mock_executor()
        executor.execute_node = AsyncMock(
            return_value={
                "success": True,
                "output": {"pause": True, "reason": "needs approval"},
                "tokens": 5,
                "cost": 0.005,
            }
        )

        result = await s.execute(wf, {}, executor, db)

        assert result.success is False
        assert result.status == "paused"

    @pytest.mark.asyncio
    async def test_execute_conditional_edge_true(self):
        """Edge with condition that evaluates to True — downstream node executes."""
        s = GraphStrategy()
        nodes = [
            WorkflowNode(id="gate", type="llm_call", title="Gate"),
            WorkflowNode(id="after", type="llm_call", title="After"),
        ]
        edges = [WorkflowEdge(source="gate", target="after", condition="true")]
        wf = _make_graph_workflow(nodes=nodes, edges=edges)
        db = AsyncMock()
        executor = _mock_executor()

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        assert len(result.completed_nodes) == 2

    @pytest.mark.asyncio
    async def test_execute_conditional_edge_false(self):
        """Edge with condition that evaluates to False — downstream node skipped."""
        s = GraphStrategy()
        nodes = [
            WorkflowNode(id="gate", type="llm_call", title="Gate"),
            WorkflowNode(id="after", type="llm_call", title="After"),
        ]
        edges = [WorkflowEdge(source="gate", target="after", condition="false")]
        wf = _make_graph_workflow(nodes=nodes, edges=edges)
        db = AsyncMock()
        executor = _mock_executor()

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        assert "gate" in result.completed_nodes
        assert "after" not in result.completed_nodes

    @pytest.mark.asyncio
    async def test_execute_with_context_interpolation(self):
        """Condition references {{node_id.field}} that gets resolved from node output."""
        s = GraphStrategy()
        nodes = [
            WorkflowNode(id="check", type="llm_call", title="Check"),
            WorkflowNode(id="next", type="llm_call", title="Next"),
        ]
        edges = [
            WorkflowEdge(
                source="check",
                target="next",
                condition="{{check.status}}",
            )
        ]
        wf = _make_graph_workflow(nodes=nodes, edges=edges)
        db = AsyncMock()
        executor = _mock_executor()

        # First call returns output with status=success, second is generic
        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": True,
                    "output": {"status": "success"},
                    "tokens": 5,
                    "cost": 0.005,
                }
            return {
                "success": True,
                "output": {"text": "done"},
                "tokens": 5,
                "cost": 0.005,
            }

        executor.execute_node = AsyncMock(side_effect=mock_execute)

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        assert "check" in result.completed_nodes
        assert "next" in result.completed_nodes

    @pytest.mark.asyncio
    async def test_execute_subgraph(self):
        """start_node_id in context filters to a subgraph."""
        s = GraphStrategy()
        nodes = [
            WorkflowNode(id="a", type="llm_call", title="A"),
            WorkflowNode(id="b", type="llm_call", title="B"),
            WorkflowNode(id="c", type="llm_call", title="C"),
        ]
        edges = [
            WorkflowEdge(source="a", target="b"),
            WorkflowEdge(source="a", target="c"),
        ]
        wf = _make_graph_workflow(nodes=nodes, edges=edges)
        db = AsyncMock()
        executor = _mock_executor()

        # Only run subgraph starting from b
        result = await s.execute(wf, {"start_node_id": "b"}, executor, db)

        assert result.success is True
        assert "b" in result.completed_nodes
        # a and c should not be in the subgraph starting from b
        # (b has no outgoing edges, so only b runs)
        assert "a" not in result.completed_nodes

    @pytest.mark.asyncio
    async def test_execute_subgraph_invalid_start(self):
        """Invalid start_node_id → empty subgraph → completes immediately."""
        s = GraphStrategy()
        wf = _make_graph_workflow()
        db = AsyncMock()
        executor = _mock_executor()

        result = await s.execute(wf, {"start_node_id": "nonexistent"}, executor, db)

        assert result.success is True
        assert result.completed_nodes == []

    @pytest.mark.asyncio
    async def test_execute_with_previous_outputs(self):
        """Context with previous_outputs feeds into node_outputs."""
        s = GraphStrategy()
        wf = _make_graph_workflow(
            nodes=[WorkflowNode(id="a", type="llm_call", title="A")],
            edges=[],
        )
        db = AsyncMock()
        executor = _mock_executor()

        result = await s.execute(
            wf,
            {"previous_outputs": {"prior": {"text": "cached"}}, "start_node_id": None},
            executor,
            db,
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_three_layer_diamond(self):
        """Diamond: a → b, a → c, b → d, c → d."""
        s = GraphStrategy()
        nodes = [
            WorkflowNode(id="a", type="llm_call", title="A"),
            WorkflowNode(id="b", type="llm_call", title="B"),
            WorkflowNode(id="c", type="llm_call", title="C"),
            WorkflowNode(id="d", type="llm_call", title="D"),
        ]
        edges = [
            WorkflowEdge(source="a", target="b"),
            WorkflowEdge(source="a", target="c"),
            WorkflowEdge(source="b", target="d"),
            WorkflowEdge(source="c", target="d"),
        ]
        wf = _make_graph_workflow(nodes=nodes, edges=edges)
        db = AsyncMock()
        executor = _mock_executor()

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        assert len(result.completed_nodes) == 4
        assert result.total_tokens == 40


# ── _get_subgraph_ids ────────────────────────────────────────────────


class TestGraphSubgraphIds:
    def test_subgraph_from_root(self):
        s = GraphStrategy()
        nodes = [
            WorkflowNode(id="a", type="llm_call", title="A"),
            WorkflowNode(id="b", type="llm_call", title="B"),
            WorkflowNode(id="c", type="llm_call", title="C"),
        ]
        edges = [
            WorkflowEdge(source="a", target="b"),
            WorkflowEdge(source="a", target="c"),
        ]
        wf = _make_graph_workflow(nodes=nodes, edges=edges)

        ids = s._get_subgraph_ids(wf, "a")
        assert ids == {"a", "b", "c"}

    def test_subgraph_from_middle(self):
        s = GraphStrategy()
        nodes = [
            WorkflowNode(id="a", type="llm_call", title="A"),
            WorkflowNode(id="b", type="llm_call", title="B"),
        ]
        edges = [WorkflowEdge(source="a", target="b")]
        wf = _make_graph_workflow(nodes=nodes, edges=edges)

        ids = s._get_subgraph_ids(wf, "b")
        assert ids == {"b"}

    def test_subgraph_invalid_start(self):
        s = GraphStrategy()
        wf = _make_graph_workflow()
        ids = s._get_subgraph_ids(wf, "nonexistent")
        assert ids == set()


# ── _evaluate_condition ──────────────────────────────────────────────


class TestEvaluateCondition:
    def test_no_condition_returns_true(self):
        s = GraphStrategy()
        edge = WorkflowEdge(source="a", target="b", condition=None)
        assert s._evaluate_condition(edge, {}) is True

    def test_bool_condition(self):
        s = GraphStrategy()
        edge = WorkflowEdge(source="a", target="b", condition="{{a.output.ok}}")
        assert s._evaluate_condition(edge, {"a": {"output": {"ok": True}}}) is True
        assert s._evaluate_condition(edge, {"a": {"output": {"ok": False}}}) is False

    def test_string_true_variants(self):
        s = GraphStrategy()
        for val in ("true", "success", "completed", "True", "SUCCESS"):
            edge = WorkflowEdge(source="a", target="b", condition="{{a.output.s}}")
            assert (
                s._evaluate_condition(edge, {"a": {"output": {"s": val}}}) is True
            ), f"Failed for {val}"

    def test_string_false(self):
        s = GraphStrategy()
        edge = WorkflowEdge(source="a", target="b", condition="{{a.output.s}}")
        assert s._evaluate_condition(edge, {"a": {"output": {"s": "false"}}}) is False

    def test_non_string_truthy(self):
        s = GraphStrategy()
        edge = WorkflowEdge(source="a", target="b", condition="{{a.output.n}}")
        assert s._evaluate_condition(edge, {"a": {"output": {"n": 42}}}) is True
        assert s._evaluate_condition(edge, {"a": {"output": {"n": 0}}}) is False

    def test_exception_in_resolution_returns_true(self):
        """If condition resolution raises, default to True."""
        s = GraphStrategy()
        edge = WorkflowEdge(source="a", target="b", condition="always")
        with patch.object(
            s, "_resolve_interpolation", side_effect=RuntimeError("boom")
        ):
            assert s._evaluate_condition(edge, {}) is True


# ── _resolve_interpolation ───────────────────────────────────────────


class TestResolveInterpolation:
    def test_non_string_passthrough(self):
        s = GraphStrategy()
        assert s._resolve_interpolation(42, {}) == 42

    def test_no_template_passthrough(self):
        s = GraphStrategy()
        assert s._resolve_interpolation("plain text", {}) == "plain text"

    def test_single_ref_resolved(self):
        s = GraphStrategy()
        result = s._resolve_interpolation(
            "{{n1.output.text}}",
            {"n1": {"output": {"text": "hello"}}},
        )
        assert result == "hello"

    def test_multiple_refs_interpolated(self):
        s = GraphStrategy()
        result = s._resolve_interpolation(
            "{{a.output.x}} and {{b.output.y}}",
            {"a": {"output": {"x": "foo"}}, "b": {"output": {"y": "bar"}}},
        )
        assert result == "foo and bar"

    def test_missing_ref_substituted_with_empty(self):
        s = GraphStrategy()
        result = s._resolve_interpolation(
            "Value: {{missing.output.x}}",
            {},
        )
        assert result == "Value: "


# ── _resolve_ref ─────────────────────────────────────────────────────


class TestResolveRef:
    def test_simple_ref(self):
        s = GraphStrategy()
        assert s._resolve_ref("n1.output", {"n1": {"output": "val"}}) == "val"

    def test_nested_ref(self):
        s = GraphStrategy()
        assert (
            s._resolve_ref("n1.output.text", {"n1": {"output": {"text": "hi"}}}) == "hi"
        )

    def test_missing_node(self):
        s = GraphStrategy()
        assert s._resolve_ref("missing.field", {}) is None

    def test_traversal_through_non_dict(self):
        s = GraphStrategy()
        assert (
            s._resolve_ref("n1.output.text.deep", {"n1": {"output": "scalar"}}) is None
        )


# ── _topological_sort_for_ids ────────────────────────────────────────


class TestGraphTopologicalSort:
    def test_single_node(self):
        s = GraphStrategy()
        wf = _make_graph_workflow(
            nodes=[WorkflowNode(id="solo", type="llm_call", title="S")],
            edges=[],
        )
        layers = s._topological_sort_for_ids(wf, {"solo"}, [])
        assert layers == [["solo"]]

    def test_two_layers(self):
        s = GraphStrategy()
        wf = _make_graph_workflow()
        layers = s._topological_sort_for_ids(wf, {"n1", "n2"}, wf.edges)
        assert layers[0] == ["n1"]
        assert layers[1] == ["n2"]

    def test_diamond_sort(self):
        s = GraphStrategy()
        nodes = [
            WorkflowNode(id="a", type="llm_call", title="A"),
            WorkflowNode(id="b", type="llm_call", title="B"),
            WorkflowNode(id="c", type="llm_call", title="C"),
            WorkflowNode(id="d", type="llm_call", title="D"),
        ]
        edges = [
            WorkflowEdge(source="a", target="b"),
            WorkflowEdge(source="a", target="c"),
            WorkflowEdge(source="b", target="d"),
            WorkflowEdge(source="c", target="d"),
        ]
        wf = _make_graph_workflow(nodes=nodes, edges=edges)
        layers = s._topological_sort_for_ids(wf, {"a", "b", "c", "d"}, edges)
        assert layers[0] == ["a"]
        assert set(layers[1]) == {"b", "c"}
        assert layers[2] == ["d"]

    def test_parallel_nodes_no_edges(self):
        s = GraphStrategy()
        nodes = [
            WorkflowNode(id="x", type="llm_call", title="X"),
            WorkflowNode(id="y", type="llm_call", title="Y"),
        ]
        wf = _make_graph_workflow(nodes=nodes, edges=[])
        layers = s._topological_sort_for_ids(wf, {"x", "y"}, [])
        assert len(layers) == 1
        assert set(layers[0]) == {"x", "y"}

    def test_subset_ids(self):
        """Only sort a subset of nodes."""
        s = GraphStrategy()
        nodes = [
            WorkflowNode(id="a", type="llm_call", title="A"),
            WorkflowNode(id="b", type="llm_call", title="B"),
            WorkflowNode(id="c", type="llm_call", title="C"),
        ]
        edges = [
            WorkflowEdge(source="a", target="b"),
            WorkflowEdge(source="b", target="c"),
        ]
        wf = _make_graph_workflow(nodes=nodes, edges=edges)
        # Only sort {b, c}
        layers = s._topological_sort_for_ids(
            wf, {"b", "c"}, [WorkflowEdge(source="b", target="c")]
        )
        assert layers[0] == ["b"]
        assert layers[1] == ["c"]
