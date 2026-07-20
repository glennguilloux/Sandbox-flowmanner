"""Unit tests for the Scope B NodeType handlers (Finding 3, Feature variant).

Covers the 5 template node types that previously had no NodeExecutor
handler and silently collapsed to LLM_CALL:

    transform  -> NodeType.TRANSFORM
    condition  -> NodeType.CONDITION
    log       -> NodeType.LOG
    loop      -> NodeType.LOOP   (strategy-level iteration)
    webhook   -> NodeType.WEBHOOK (irreversible side effect)

Plus:
- CONDITION + LOOP branching/iteration wired at the DAGStrategy layer.
- The fail-closed default still rejects a truly unknown node type.

No DB / LLM required: handlers that need ``db``/``run_id`` accept a
MagicMock and write best-effort events (failures are swallowed). The
webhook handler is exercised with a mocked ``httpx.AsyncClient`` so no
real network call is made.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.capability_models import Budget
from app.services.substrate.node_executor import NodeExecutor, _is_safe_url, _safe_eval, _safe_transform
from app.services.substrate.strategies.dag import DAGStrategy
from app.services.substrate.workflow_models import (
    EffectClass,
    NodeType,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowType,
)


def _budget() -> Budget:
    return Budget(
        max_cost_usd=Decimal("10.00"),
        max_wall_time_seconds=300,
        max_iterations=100,
        max_depth=5,
    )


def _node(node_type: str | NodeType, config=None, **kw) -> WorkflowNode:
    if isinstance(node_type, NodeType):
        node_type = node_type.value
    return WorkflowNode(
        id=kw.get("id", "n1"),
        type=node_type,  # type: ignore[arg-type]
        title=kw.get("title", "N"),
        config=config or {},
    )


class _StubUnifiedExecutor:
    """Minimal stand-in so NodeExecutor(self, unified_executor) is happy."""

    def is_aborted(self, run_id):
        return False

    def check_circuit_breaker(self, **kwargs):
        return (True, "ok")


def _executor() -> NodeExecutor:
    return NodeExecutor(_StubUnifiedExecutor())


# ── TRANSFORM ─────────────────────────────────────────────────


class TestTransformHandler:
    @pytest.mark.asyncio
    async def test_map_transform(self):
        ex = _executor()
        node = _node("transform", {"transformType": "map", "transformExpression": "x * 2", "input": [1, 2, 3]})
        res = await ex._handle_transform(node, {})
        assert res["success"] is True
        assert res["output"] == [2, 4, 6]
        assert res["tokens"] == 0

    @pytest.mark.asyncio
    async def test_filter_transform(self):
        ex = _executor()
        node = _node("transform", {"transformType": "filter", "transformExpression": "x > 1", "input": [0, 1, 2, 3]})
        res = await ex._handle_transform(node, {})
        assert res["success"] is True
        assert res["output"] == [2, 3]

    @pytest.mark.asyncio
    async def test_expression_transform(self):
        ex = _executor()
        node = _node(
            "transform",
            {"transformType": "expression", "transformExpression": "data['a'] + data['b']", "input": {"a": 1, "b": 2}},
        )
        res = await ex._handle_transform(node, {})
        assert res["output"] == 3

    @pytest.mark.asyncio
    async def test_missing_expression_fails(self):
        ex = _executor()
        node = _node("transform", {"transformType": "map"})
        res = await ex._handle_transform(node, {})
        assert res["success"] is False
        assert "transformExpression" in res["error"]

    @pytest.mark.asyncio
    async def test_rejects_arbitrary_code(self):
        ex = _executor()
        # getattr escape attempt -> must be rejected, never executed.
        node = _node("transform", {"transformType": "expression", "transformExpression": "().__class__.__bases__"})
        res = await ex._handle_transform(node, {})
        assert res["success"] is False

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_transform(self):
        ex = _executor()
        node = _node("transform", {"transformType": "map", "transformExpression": "x + 1", "input": [10]})
        res = await ex._dispatch(MagicMock(), node, {}, _budget(), "run-1", None)
        assert res["success"] is True
        assert res["output"] == [11]


# ── CONDITION ────────────────────────────────────────────────


class TestConditionHandler:
    @pytest.mark.asyncio
    async def test_true_expression(self):
        ex = _executor()
        node = _node("condition", {"expression": "data['score'] > 0.5"})
        res = await ex._handle_condition(node, {"data": {"score": 0.9}})
        assert res["success"] is True
        assert res["output"]["value"] is True

    @pytest.mark.asyncio
    async def test_false_expression(self):
        ex = _executor()
        node = _node("condition", {"expression": "data['score'] > 0.5"})
        res = await ex._handle_condition(node, {"data": {"score": 0.1}})
        assert res["output"]["value"] is False

    @pytest.mark.asyncio
    async def test_missing_expression_fails(self):
        ex = _executor()
        res = await ex._handle_condition(_node("condition", {}), {})
        assert res["success"] is False

    @pytest.mark.asyncio
    async def test_rejects_arbitrary_code(self):
        ex = _executor()
        node = _node("condition", {"expression": "__import__('os')"})
        res = await ex._handle_condition(node, {})
        assert res["success"] is False

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_condition(self):
        ex = _executor()
        node = _node("condition", {"expression": "True"})
        res = await ex._dispatch(MagicMock(), node, {}, _budget(), "run-1", None)
        assert res["output"]["value"] is True


# ── LOG ─────────────────────────────────────────────────────


class TestLogHandler:
    @pytest.mark.asyncio
    async def test_returns_success_read_only(self):
        ex = _executor()
        db = MagicMock()
        db.add = MagicMock()
        node = _node("log", {"message": "hello {{n1.output.v}}", "level": "info"})
        res = await ex._handle_log(db, node, {"n1": {"output": {"v": 42}}}, "run-1", None)
        assert res["success"] is True
        assert "42" in res["output"]["message"]
        assert res["tokens"] == 0

    @pytest.mark.asyncio
    async def test_interpolates_context(self):
        ex = _executor()
        node = _node("log", {"message": "score={{n1.output.score}}"})
        res = await ex._handle_log(None, node, {"n1": {"output": {"score": 7}}}, "run-1", None)
        assert "score=7" in res["output"]["message"]


# ── LOOP (handler is a marker; iteration is strategy-level) ──


class TestLoopHandler:
    @pytest.mark.asyncio
    async def test_marker_reports_bounds(self):
        ex = _executor()
        node = _node("loop", {"max_iterations": 5, "stop_condition": "data['done']", "loop_var": "i"})
        res = await ex._handle_loop(node, {})
        assert res["success"] is True
        assert res["output"]["max_iterations"] == 5
        assert res["output"]["stop_condition"] == "data['done']"

    @pytest.mark.asyncio
    async def test_hard_cap_clamp(self):
        ex = _executor()
        node = _node("loop", {"max_iterations": 99999})
        res = await ex._handle_loop(node, {})
        assert res["output"]["max_iterations"] == 1000


# ── WEBHOOK ────────────────────────────────────────────────


class TestWebhookHandler:
    @pytest.mark.asyncio
    async def test_missing_url_fails(self):
        ex = _executor()
        res = await ex._handle_webhook(MagicMock(), _node("webhook", {}), {}, "run-1", None)
        assert res["success"] is False
        assert "url" in res["error"]

    @pytest.mark.asyncio
    async def test_ssrf_guard_blocks_private(self):
        ex = _executor()
        node = _node("webhook", {"url": "http://127.0.0.1:8080/hook"})
        res = await ex._handle_webhook(MagicMock(), node, {}, "run-1", None)
        assert res["success"] is False
        assert "SSRF" in res["error"]

    @pytest.mark.asyncio
    async def test_sends_post_and_records_event(self):
        ex = _executor()
        db = MagicMock()
        db.add = MagicMock()

        class _Resp:
            status_code = 200

            def json(self):
                return {"ok": True}

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def request(self, method, url, json=None, headers=None):
                return _Resp()

        with patch("httpx.AsyncClient", return_value=_Client()):
            node = _node("webhook", {"url": "https://example.com/hook", "payload": {"x": 1}})
            res = await ex._handle_webhook(db, node, {}, "run-1", None)
        assert res["success"] is True
        assert res["output"]["status_code"] == 200


# ── FAIL-CLOSED DEFAULT ───────────────────────────────────


class TestFailClosed:
    @pytest.mark.asyncio
    async def test_unknown_type_still_rejected(self):
        ex = _executor()
        # Build a node with a type that is NOT a NodeType member so the
        # fail-closed `case _` in _dispatch is reached.
        node = _node("llm_call", {})
        node.type = "totally_unknown_type"  # type: ignore[assignment]
        res = await ex._dispatch(MagicMock(), node, {}, _budget(), "run-1", None)
        assert res["success"] is False
        assert "Unknown node type" in res["error"]

    def test_effect_class_default_irreversible(self):
        # webhook is not in the reversible set -> IRREVERSIBLE by default,
        # so the two-phase STAGE→CONFIRM dispatch gates it.
        node = _node("webhook", {"url": "https://example.com/hook"})
        assert node.effect_class == EffectClass.IRREVERSIBLE


# ── SAFE EVAL / TRANSFORM HELPERS ──────────────────────


class TestSafeEval:
    def test_basic(self):
        assert _safe_eval("a + b", {"a": 2, "b": 3}) == 5

    def test_subscript(self):
        assert _safe_eval("d['k']", {"d": {"k": 9}}) == 9

    def test_blocks_import(self):
        with pytest.raises(ValueError, match="Unknown name"):
            _safe_eval("__import__('os')", {})

    def test_blocks_attribute_escape(self):
        class C:
            secret = "x"

        with pytest.raises(ValueError, match="non-container"):
            _safe_eval("c.secret", {"c": C()})

    def test_transform_helper(self):
        assert _safe_transform("map", "x * 10", [1, 2], {}) == [10, 20]


# ── DAG STRATEGY: CONDITION + LOOP ──────────────────────


def _make_dag(nodes, edges):
    return Workflow(
        id="wf-dag",
        type=WorkflowType.DAG,
        title="DAG",
        nodes=nodes,
        edges=edges,
        user_id="1",
        budget=_budget(),
    )


class TestDAGConditionBranching:
    @pytest.mark.asyncio
    async def test_true_branch_taken_false_branch_skipped(self):
        # cond evaluates True -> only the "true" target runs.
        nodes = [
            WorkflowNode(id="cond", type="condition", title="C", config={"expression": "data['v'] > 5"}),
            WorkflowNode(id="t_true", type="llm_call", title="T", dependencies=["cond"]),
            WorkflowNode(id="t_false", type="llm_call", title="F", dependencies=["cond"]),
        ]
        edges = [
            WorkflowEdge(source="cond", target="t_true", condition="true"),
            WorkflowEdge(source="cond", target="t_false", condition="false"),
        ]
        wf = _make_dag(nodes, edges)
        # validate() must still pass: both edges reference real node ids.
        errors = await DAGStrategy().validate(wf)
        assert errors == []

        db = MagicMock()
        exec_mock = MagicMock()
        exec_mock.is_aborted = MagicMock(return_value=False)
        ran = {}

        async def run_node(*a, **k):
            n = k["node"]
            nid = n.id
            ran[nid] = True
            if n.type.value == "condition":
                # Return the condition handler's REAL output so the
                # strategy's branch gating sees the evaluated boolean.
                from app.services.substrate.node_executor import NodeExecutor

                out = await NodeExecutor(_StubUnifiedExecutor())._handle_condition(n, k["context"])
                out.setdefault("tokens", 1)
                out.setdefault("cost", 0.0)
                return out
            return {"success": True, "output": {"v": 1}, "tokens": 1, "cost": 0.0}

        exec_mock.execute_node = AsyncMock(side_effect=run_node)
        result = await DAGStrategy().execute(wf, {"data": {"v": 10}}, exec_mock, db, run_id="r-1")
        assert result.success is True
        assert "t_true" in ran
        assert "t_false" not in ran

    @pytest.mark.asyncio
    async def test_false_branch_taken(self):
        nodes = [
            WorkflowNode(id="cond", type="condition", title="C", config={"expression": "data['v'] > 5"}),
            WorkflowNode(id="t_true", type="llm_call", title="T", dependencies=["cond"]),
            WorkflowNode(id="t_false", type="llm_call", title="F", dependencies=["cond"]),
        ]
        edges = [
            WorkflowEdge(source="cond", target="t_true", condition="true"),
            WorkflowEdge(source="cond", target="t_false", condition="false"),
        ]
        wf = _make_dag(nodes, edges)
        db = MagicMock()
        exec_mock = MagicMock()
        exec_mock.is_aborted = MagicMock(return_value=False)
        ran = {}

        async def run_node(*a, **k):
            n = k["node"]
            nid = n.id
            ran[nid] = True
            if n.type.value == "condition":
                from app.services.substrate.node_executor import NodeExecutor

                out = await NodeExecutor(_StubUnifiedExecutor())._handle_condition(n, k["context"])
                out.setdefault("tokens", 1)
                out.setdefault("cost", 0.0)
                return out
            return {"success": True, "output": {"v": 0}, "tokens": 1, "cost": 0.0}

        exec_mock.execute_node = AsyncMock(side_effect=run_node)
        await DAGStrategy().execute(wf, {"data": {"v": 1}}, exec_mock, db, run_id="r-2")
        assert "t_false" in ran
        assert "t_true" not in ran


class TestDAGLoopIteration:
    @pytest.mark.asyncio
    async def test_loop_body_runs_to_max_iterations(self):
        # Loop has no stop_condition -> runs max_iterations times.
        nodes = [
            WorkflowNode(id="start", type="llm_call", title="S"),
            WorkflowNode(
                id="loop",
                type="loop",
                title="L",
                dependencies=["start"],
                config={"body": ["b1", "b2"], "max_iterations": 3},
            ),
            WorkflowNode(id="b1", type="llm_call", title="B1", dependencies=["loop"]),
            WorkflowNode(id="b2", type="llm_call", title="B2", dependencies=["loop"]),
        ]
        edges = [
            WorkflowEdge(source="start", target="loop"),
            WorkflowEdge(source="loop", target="b1"),
            WorkflowEdge(source="loop", target="b2"),
        ]
        wf = _make_dag(nodes, edges)
        db = MagicMock()
        exec_mock = MagicMock()
        exec_mock.is_aborted = MagicMock(return_value=False)
        counts: dict[str, int] = {}

        async def run_node(*a, **k):
            nid = k["node"].id
            counts[nid] = counts.get(nid, 0) + 1
            return {"success": True, "output": {}, "tokens": 1, "cost": 0.0}

        exec_mock.execute_node = AsyncMock(side_effect=run_node)
        result = await DAGStrategy().execute(wf, {}, exec_mock, db, run_id="r-3")
        assert result.success is True
        # b1/b2 executed once per loop iteration (3) PLUS not during normal
        # layering (they're skipped there because the loop already ran them).
        assert counts["b1"] == 3
        assert counts["b2"] == 3

    @pytest.mark.asyncio
    async def test_loop_stops_on_condition(self):
        # stop_condition becomes true after iteration 1 -> loop breaks early.
        nodes = [
            WorkflowNode(
                id="loop",
                type="loop",
                title="L",
                config={"body": ["b1"], "max_iterations": 10, "stop_condition": "data['done'] == 1"},
            ),
            WorkflowNode(id="b1", type="llm_call", title="B1", dependencies=["loop"]),
        ]
        edges = [WorkflowEdge(source="loop", target="b1")]
        wf = _make_dag(nodes, edges)
        db = MagicMock()
        exec_mock = MagicMock()
        exec_mock.is_aborted = MagicMock(return_value=False)
        counts: dict[str, int] = {}

        async def run_node(*a, **k):
            nid = k["node"].id
            counts[nid] = counts.get(nid, 0) + 1
            # After b1 runs once, flip the stop flag so the next condition eval
            # (against previous_outputs) sees done == 1.
            if nid == "b1":
                k["context"]["previous_outputs"]["done"] = 1
            return {"success": True, "output": {}, "tokens": 1, "cost": 0.0}

        exec_mock.execute_node = AsyncMock(side_effect=run_node)
        await DAGStrategy().execute(wf, {}, exec_mock, db, run_id="r-4")
        # Should stop after 1 iteration (not run 10 times).
        assert counts["b1"] == 1


# ── SPLIT (collection fan-out) ──────────────────────────


class TestSplitHandler:
    """Unit tests for the Scope B SPLIT handler (data-driven fan-out)."""

    @pytest.mark.asyncio
    async def test_splits_list_into_items(self):
        ex = _executor()
        node = _node("split", {"splitOn": "input"})
        res = await ex._handle_split(node, {"input": [1, 2, 3]})
        assert res["success"] is True
        assert res["output"]["items"] == [1, 2, 3]
        assert res["output"]["count"] == 3
        assert res["output"]["empty"] is False

    @pytest.mark.asyncio
    async def test_splits_dict_over_values(self):
        ex = _executor()
        node = _node("split", {"splitOn": "input"})
        res = await ex._handle_split(node, {"input": {"a": 10, "b": 20}})
        assert res["success"] is True
        assert res["output"]["items"] == [10, 20]
        assert res["output"]["count"] == 2

    @pytest.mark.asyncio
    async def test_empty_collection_marks_empty(self):
        ex = _executor()
        node = _node("split", {"splitOn": "input"})
        res = await ex._handle_split(node, {"input": []})
        assert res["success"] is True
        assert res["output"]["items"] == []
        assert res["output"]["empty"] is True

    @pytest.mark.asyncio
    async def test_scalar_becomes_single_item(self):
        ex = _executor()
        node = _node("split", {"splitOn": "input"})
        res = await ex._handle_split(node, {"input": "solo"})
        assert res["output"]["items"] == ["solo"]
        assert res["output"]["count"] == 1

    @pytest.mark.asyncio
    async def test_split_on_nested_key(self):
        ex = _executor()
        node = _node("split", {"splitOn": "input.rows"})
        res = await ex._handle_split(node, {"input": {"rows": ["x", "y"]}})
        assert res["output"]["items"] == ["x", "y"]
        assert res["output"]["split_on"] == "input.rows"

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_handler(self):
        ex = _executor()
        node = _node("split", {"splitOn": "input"})
        res = await ex._dispatch(MagicMock(), node, {"input": [1, 2]}, _budget(), "run-1", None)
        assert res["success"] is True
        assert res["output"]["count"] == 2


class TestDAGSplitFanout:
    """SPLIT node drives one branch per item at the DAG strategy level."""

    @pytest.mark.asyncio
    async def test_one_branch_per_item(self):
        # split -> worker ; collection of 3 -> worker runs 3 times.
        nodes = [
            WorkflowNode(
                id="src",
                type="llm_call",
                title="S",
                config={"collection": [1, 2, 3]},
            ),
            WorkflowNode(
                id="split",
                type="split",
                title="Split",
                dependencies=["src"],
                config={"splitOn": "input"},
            ),
            WorkflowNode(id="worker", type="llm_call", title="W", dependencies=["split"]),
        ]
        edges = [
            WorkflowEdge(source="src", target="split"),
            WorkflowEdge(source="split", target="worker"),
        ]
        wf = _make_dag(nodes, edges)
        # validate() must still pass: the edge references a real node id.
        errors = await DAGStrategy().validate(wf)
        assert errors == []

        db = MagicMock()
        exec_mock = MagicMock()
        exec_mock.is_aborted = MagicMock(return_value=False)
        ran: dict[str, int] = {}

        async def run_node(*a, **k):
            n = k["node"]
            nid = n.id
            ran[nid] = ran.get(nid, 0) + 1
            if n.type.value == "split":
                # Return the REAL split handler output so the strategy fans out.
                from app.services.substrate.node_executor import NodeExecutor

                out = await NodeExecutor(_StubUnifiedExecutor())._handle_split(n, k["context"])
                out.setdefault("tokens", 0)
                out.setdefault("cost", 0.0)
                return out
            # worker receives the per-item input from the fan-out.
            return {
                "success": True,
                "output": {"got": k["context"].get("input")},
                "tokens": 1,
                "cost": 0.0,
            }

        exec_mock.execute_node = AsyncMock(side_effect=run_node)
        result = await DAGStrategy().execute(wf, {"input": [1, 2, 3]}, exec_mock, db, run_id="r-split-1")
        assert result.success is True
        # split fanned its 3 items out: worker executed once per item.
        assert ran["worker"] == 3
        assert ran["split"] == 1

    @pytest.mark.asyncio
    async def test_empty_collection_no_fanout(self):
        nodes = [
            WorkflowNode(id="split", type="split", title="Split", config={"splitOn": "input"}),
            WorkflowNode(id="worker", type="llm_call", title="W", dependencies=["split"]),
        ]
        edges = [WorkflowEdge(source="split", target="worker")]
        wf = _make_dag(nodes, edges)
        db = MagicMock()
        exec_mock = MagicMock()
        exec_mock.is_aborted = MagicMock(return_value=False)
        ran: dict[str, int] = {}

        async def run_node(*a, **k):
            n = k["node"]
            ran[n.id] = ran.get(n.id, 0) + 1
            if n.type.value == "split":
                from app.services.substrate.node_executor import NodeExecutor

                out = await NodeExecutor(_StubUnifiedExecutor())._handle_split(n, k["context"])
                out.setdefault("tokens", 0)
                out.setdefault("cost", 0.0)
                return out
            return {"success": True, "output": {}, "tokens": 1, "cost": 0.0}

        exec_mock.execute_node = AsyncMock(side_effect=run_node)
        result = await DAGStrategy().execute(wf, {"input": []}, exec_mock, db, run_id="r-split-2")
        assert result.success is True
        # Empty collection -> no fan-out -> worker never runs.
        assert ran.get("worker", 0) == 0
        assert ran["split"] == 1
