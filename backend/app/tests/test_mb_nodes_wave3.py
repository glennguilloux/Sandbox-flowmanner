# ─────────────────────────────────────────────────────────────────────
# Wave 3 — backend-native node coverage + round-trip + handler tests.
#
# Scope (Mission Builder New Nodes, Wave 3 backend):
#   * NodeType.ROUTER / DELAY / MERGE exist and map in _TASK_TYPE_MAP
#   * input_*/output_* are canvas-only DATA SHIMS (skipped, NOT mapped)
#   * _handle_router / _handle_delay / _handle_merge are wired + behave
#   * DAG + Graph branch-gating honor a router source node
#
# Hermetic: no Postgres / Docker / Alembic. NodeExecutor handlers are
# exercised directly (they only touch context + asyncio.sleep). The
# blueprint adapter is called with Blueprint-shaped snapshots.
#
# The adapter-coverage gate reads the CURRENT frontend palette
# (mission-types.ts NODE_DEFAULTS) so a future un-mapped palette type
# fails the build. See test_palette_fully_mapped for the contract.
# ─────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import inspect
import re

import pytest

from app.services.substrate.adapters import (
    _DATA_SHIM_TYPES,
    _TASK_TYPE_MAP,
    blueprint_to_workflow,
)
from app.services.substrate.node_executor import NodeExecutor, _safe_eval
from app.services.substrate.strategies.dag import DAGStrategy
from app.services.substrate.strategies.graph import GraphStrategy
from app.services.substrate.workflow_models import (
    NodeType,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowType,
)

# Frontend palette source of truth (read-only; not edited here).
_FE_MISSION_TYPES = "/home/glenn/FlowmannerV2-frontend/src/lib/mission-types.ts"

# Start/end are canvas bookkeeping sentinels (跳过 by the adapter, never
# mapped to a NodeType). Mirrors _SENTINEL_NODE_TYPES in adapters.py.
_SENTINEL_TYPES = {"start", "end"}

# Palette types the FE intends to be LLM-backed (generic task / prompt
# family) with NO dedicated substrate NodeType — they legitimately map to
# LLM_CALL. A future palette type that is neither a real (non-LLM_CALL)
# handler, nor a data shim, nor a sentinel, nor in this allowlist is a
# coverage GAP and must fail the build (plan §3 gate 1).
KNOWN_LLM_TYPES = {
    "task",
    "subflow",
    "prompt",
    "code_transform",
    "search_retrieve",
}


# ── FE palette parsing (drift-free coverage gate) ──────────────────────


def _extract_node_defaults_keys(path: str) -> set[str]:
    """Return the set of node-type keys declared in the FE NODE_DEFAULTS map.

    Parses the TypeScript source read-only so the backend gate can never
    silently drift from the shipped palette.
    """
    with open(path, encoding="utf-8") as fh:
        src = fh.read()

    marker = "NODE_DEFAULTS"
    start = src.index(marker)
    # Find the first '{' opening the object literal.
    brace_open = src.index("{", start)
    # Balance braces to find the matching close '}' at column 0.
    depth = 0
    end = None
    for i in range(brace_open, len(src)):
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        raise RuntimeError("Could not balance NODE_DEFAULTS braces")
    block = src[brace_open + 1 : end]

    # Each entry is a top-level `  key: { ... }` line inside the object.
    keys = set(re.findall(r"^\s{2}([A-Za-z_][A-Za-z0-9_]*):\s*\{", block, re.M))
    return keys


_FE_PALETTE = _extract_node_defaults_keys(_FE_MISSION_TYPES)


# ── Adapter coverage gate (plan §3 gate 1) ─────────────────────────────


class TestFrontendPaletteCoverage:
    def test_palette_nonempty(self):
        assert _FE_PALETTE, "FE NODE_DEFAULTS parsed to an empty set — parser broke"

    def test_every_palette_type_is_accounted_for(self):
        """Every FE palette type must be EITHER:
        (a) mapped in _TASK_TYPE_MAP to a NON-LLM_CALL NodeType (a real
            backend-native handler), OR
        (b) a canvas-only DATA SHIM (input_*/output_*, skipped), OR
        (c) an explicitly-acknowledged LLM-backed type (generic task /
            prompt family that legitimately runs as LLM_CALL).

        This fails the build on any future un-mapped palette type.
        """
        failures = []
        for key in sorted(_FE_PALETTE):
            if key in _DATA_SHIM_TYPES:
                continue
            if key in _SENTINEL_TYPES:  # start / end bookkeeping, never mapped
                continue
            if key in KNOWN_LLM_TYPES:  # intentional LLM-backed task/prompt family
                continue
            mapped = _TASK_TYPE_MAP.get(key)
            if mapped is not None and mapped != NodeType.LLM_CALL:
                continue
            failures.append(key)
        assert not failures, (
            "FE palette types are neither mapped to a real backend NodeType, "
            f"nor data shims, nor acknowledged LLM types: {failures}"
        )

    def test_new_wave3_types_map_to_non_llm_node_types(self):
        assert _TASK_TYPE_MAP.get("router") == NodeType.ROUTER
        assert _TASK_TYPE_MAP.get("merge") == NodeType.MERGE
        assert _TASK_TYPE_MAP.get("delay") == NodeType.DELAY

    def test_data_shims_are_not_in_task_type_map(self):
        # The shims must be SKIPPED, never mapped (mapping them as LLM_CALL
        # would make them run). Assert they are absent from the map.
        for shim in _DATA_SHIM_TYPES:
            assert shim not in _TASK_TYPE_MAP, f"DATA SHIM '{shim}' must NOT be in _TASK_TYPE_MAP"


# ── Round-trip: blueprint_to_workflow ──────────────────────────────────


def _node(nid: str, node_type: str) -> dict:
    return {"id": nid, "type": node_type, "data": {"nodeType": node_type}}


def _edge(src: str, tgt: str, condition: str | None = None) -> dict:
    e: dict[str, str | None] = {"source": src, "target": tgt}
    if condition is not None:
        e["condition"] = condition
    return e


def _convert(snapshot: dict) -> Workflow:
    return blueprint_to_workflow(snapshot, blueprint_id="bp-test", user_id="user-1")


class TestBlueprintRoundTrip:
    def test_router_merge_delay_map_to_correct_node_types(self):
        wf = _convert(
            {
                "blueprint_type": "solo",
                "title": "ctl",
                "nodes": [
                    _node("r", "router"),
                    _node("m", "merge"),
                    _node("d", "delay"),
                ],
                "edges": [],
            }
        )
        by_id = {n.id: n.type for n in wf.nodes}
        assert by_id["r"] == NodeType.ROUTER
        assert by_id["m"] == NodeType.MERGE
        assert by_id["d"] == NodeType.DELAY

    def test_input_output_shims_are_skipped(self):
        wf = _convert(
            {
                "blueprint_type": "solo",
                "title": "shims",
                "nodes": [
                    _node("in_text", "input_text"),
                    _node("in_hook", "input_webhook"),
                    _node("in_ds", "input_dataset"),
                    _node("out_fmt", "output_format"),
                    _node("out_del", "output_deliver"),
                    _node("real", "task"),
                ],
                "edges": [
                    _edge("in_text", "real"),
                    _edge("in_hook", "real"),
                    _edge("in_ds", "real"),
                    _edge("real", "out_fmt"),
                    _edge("real", "out_del"),
                ],
            }
        )
        surviving = {n.id for n in wf.nodes}
        # All five shims are gone; only the real task node remains.
        assert surviving == {"real"}, surviving
        # No edge references a skipped shim id.
        for e in wf.edges:
            assert e.source in surviving
            assert e.target in surviving


# ── Handler dispatch wiring ────────────────────────────────────────────


class TestHandlerDispatch:
    async def test_dispatch_routes_router_merge_delay(self):
        src = inspect.getsource(NodeExecutor._dispatch)
        assert "ROUTER" in src
        assert "_handle_router" in src
        assert "DELAY" in src
        assert "_handle_delay" in src
        assert "MERGE" in src
        assert "_handle_merge" in src

    async def test_handlers_exist(self):
        assert hasattr(NodeExecutor, "_handle_router")
        assert hasattr(NodeExecutor, "_handle_delay")
        assert hasattr(NodeExecutor, "_handle_merge")


# ── Router handler ─────────────────────────────────────────────────────


class TestRouterHandler:
    def _router_node(self, config: dict) -> WorkflowNode:
        return WorkflowNode(id="r1", type=NodeType.ROUTER, title="R", config=config)

    async def test_selects_first_matching_route_by_expression(self):
        node = self._router_node(
            {
                "routerConfig": {
                    "routes": [
                        {"id": "a", "name": "A", "enabled": True, "expression": "1 > 2"},
                        {"id": "b", "name": "B", "enabled": True, "expression": "2 > 1"},
                        {"id": "c", "name": "C", "enabled": True, "expression": "1 > 0"},
                    ],
                    "fallbackBehavior": "drop",
                }
            }
        )
        res = await NodeExecutor(None)._handle_router(node, {"x": 1})
        assert res["success"] is True
        assert res["branch"] == "b"
        assert res["output"]["route_id"] == "b"

    async def test_skips_disabled_routes(self):
        node = self._router_node(
            {
                "routerConfig": {
                    "routes": [
                        {"id": "a", "name": "A", "enabled": False, "expression": "1 > 0"},
                        {"id": "b", "name": "B", "enabled": True, "expression": "1 > 0"},
                    ],
                    "fallbackBehavior": "drop",
                }
            }
        )
        res = await NodeExecutor(None)._handle_router(node, {})
        assert res["branch"] == "b"

    async def test_no_match_with_drop_falls_through(self):
        node = self._router_node(
            {
                "routerConfig": {
                    "routes": [
                        {"id": "a", "name": "A", "enabled": True, "expression": "1 > 2"},
                    ],
                    "fallbackBehavior": "drop",
                }
            }
        )
        res = await NodeExecutor(None)._handle_router(node, {})
        assert res["success"] is True
        assert res["branch"] is None  # no condition-gated edge fires

    async def test_no_match_with_route_to_default(self):
        node = self._router_node(
            {
                "routerConfig": {
                    "routes": [
                        {"id": "a", "name": "A", "enabled": True, "expression": "1 > 2", "isDefault": True},
                        {"id": "b", "name": "B", "enabled": True, "expression": "1 > 2"},
                    ],
                    "fallbackBehavior": "route_to_default",
                }
            }
        )
        res = await NodeExecutor(None)._handle_router(node, {})
        assert res["branch"] == "a"

    async def test_bad_expression_on_route_is_skipped_not_crash(self):
        node = self._router_node(
            {
                "routerConfig": {
                    "routes": [
                        # Unparseable expression must be skipped, not raised.
                        {"id": "a", "name": "A", "enabled": True, "expression": "this is not code @@@"},
                        {"id": "b", "name": "B", "enabled": True, "expression": "1 > 0"},
                    ],
                    "fallbackBehavior": "drop",
                }
            }
        )
        res = await NodeExecutor(None)._handle_router(node, {})
        assert res["branch"] == "b"


# ── Delay handler ──────────────────────────────────────────────────────


class TestDelayHandler:
    async def test_sleeps_then_passes_through(self):
        node = WorkflowNode(id="d1", type=NodeType.DELAY, title="D", config={"delayMs": 10})
        start = asyncio.get_event_loop().time()
        res = await NodeExecutor(None)._handle_delay(node, {})
        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
        assert res["success"] is True
        assert res["branch"] == "default"
        assert res["output"]["delayed_ms"] == 10
        assert elapsed_ms >= 8  # slept ~10ms

    async def test_missing_delayMs_fails_closed(self):
        node = WorkflowNode(id="d1", type=NodeType.DELAY, title="D", config={})
        res = await NodeExecutor(None)._handle_delay(node, {})
        assert res["success"] is False
        assert "delayMs" in res["error"]

    async def test_non_positive_delayMs_fails_closed(self):
        node = WorkflowNode(id="d1", type=NodeType.DELAY, title="D", config={"delayMs": 0})
        res = await NodeExecutor(None)._handle_delay(node, {})
        assert res["success"] is False


# ── Merge handler ──────────────────────────────────────────────────────


class TestMergeHandler:
    def _merge_node(self, strategy: str, deps: list[str] | None = None) -> WorkflowNode:
        return WorkflowNode(
            id="m1",
            type=NodeType.MERGE,
            title="M",
            config={"mergeStrategy": strategy},
            dependencies=deps or [],
        )

    async def test_concat_default(self):
        node = self._merge_node("concat", deps=["a", "b", "c"])
        ctx = {"previous_outputs": {"a": [1, 2], "b": 3, "c": [4]}}
        res = await NodeExecutor(None)._handle_merge(node, ctx)
        assert res["success"] is True
        assert res["branch"] == "default"
        assert res["output"]["merged"] == [1, 2, 3, 4]

    async def test_merge_dict(self):
        node = self._merge_node("merge_dict", deps=["a", "b"])
        ctx = {"previous_outputs": {"a": {"x": 1}, "b": {"y": 2}}}
        res = await NodeExecutor(None)._handle_merge(node, ctx)
        assert res["output"]["merged"] == {"x": 1, "y": 2}

    async def test_first(self):
        node = self._merge_node("first", deps=["a", "b"])
        ctx = {"previous_outputs": {"a": None, "b": "hello"}}
        res = await NodeExecutor(None)._handle_merge(node, ctx)
        assert res["output"]["merged"] == "hello"

    async def test_falls_back_to_all_previous_outputs(self):
        node = self._merge_node("concat")  # no deps -> use all
        ctx = {"previous_outputs": {"a": [1], "b": [2]}}
        res = await NodeExecutor(None)._handle_merge(node, ctx)
        assert res["output"]["merged"] == [1, 2]


# ── DAG router branch gating ───────────────────────────────────────────


def _router_wf(edges: list[WorkflowEdge], routes_config: dict | None = None) -> Workflow:
    cfg = routes_config or {"routerConfig": {"routes": [], "fallbackBehavior": "drop"}}
    router = WorkflowNode(id="router1", type=NodeType.ROUTER, title="R", config=cfg)
    term = WorkflowNode(id="t1", type=NodeType.LLM_CALL, title="T", config={})
    return Workflow(id="w", type=WorkflowType.DAG, title="t", nodes=[router, term], edges=edges)


class TestDagRouterBranchGating:
    def test_router_edge_taken_when_condition_matches_selected_route(self):
        strat = DAGStrategy()
        wf = _router_wf([WorkflowEdge(source="router1", target="t1", condition="branch_a")])
        strat.workflow = wf
        out = {"router1": {"branch": "branch_a"}}
        assert strat._incoming_branch_passed(wf, "t1", out) is True

    def test_router_edge_blocked_when_condition_mismatches(self):
        strat = DAGStrategy()
        wf = _router_wf([WorkflowEdge(source="router1", target="t1", condition="branch_a")])
        strat.workflow = wf
        out = {"router1": {"branch": "branch_b"}}
        assert strat._incoming_branch_passed(wf, "t1", out) is False

    def test_router_edge_blocked_when_no_route_selected(self):
        strat = DAGStrategy()
        wf = _router_wf([WorkflowEdge(source="router1", target="t1", condition="branch_a")])
        strat.workflow = wf
        out = {"router1": {"branch": None}}
        assert strat._incoming_branch_passed(wf, "t1", out) is False

    def test_router_edge_without_condition_passes(self):
        strat = DAGStrategy()
        wf = _router_wf([WorkflowEdge(source="router1", target="t1")])  # condition=None
        strat.workflow = wf
        out = {"router1": {"branch": "branch_a"}}
        assert strat._incoming_branch_passed(wf, "t1", out) is True


# ── Graph router branch gating ─────────────────────────────────────────


def _router_graph_wf(edges: list[WorkflowEdge], routes_config: dict | None = None) -> Workflow:
    cfg = routes_config or {"routerConfig": {"routes": [], "fallbackBehavior": "drop"}}
    router = WorkflowNode(id="router1", type=NodeType.ROUTER, title="R", config=cfg)
    term = WorkflowNode(id="t1", type=NodeType.LLM_CALL, title="T", config={})
    return Workflow(id="w", type=WorkflowType.GRAPH, title="t", nodes=[router, term], edges=edges)


class TestGraphRouterBranchGating:
    def test_router_edge_taken_when_condition_matches(self):
        strat = GraphStrategy()
        wf = _router_graph_wf([WorkflowEdge(source="router1", target="t1", condition="branch_a")])
        strat.workflow = wf
        out = {"router1": {"branch": "branch_a"}}
        assert strat._evaluate_condition(wf.edges[0], out) is True

    def test_router_edge_blocked_when_mismatch(self):
        strat = GraphStrategy()
        wf = _router_graph_wf([WorkflowEdge(source="router1", target="t1", condition="branch_a")])
        strat.workflow = wf
        out = {"router1": {"branch": "branch_b"}}
        assert strat._evaluate_condition(wf.edges[0], out) is False

    def test_router_edge_blocked_when_no_route_selected(self):
        strat = GraphStrategy()
        wf = _router_graph_wf([WorkflowEdge(source="router1", target="t1", condition="branch_a")])
        strat.workflow = wf
        out = {"router1": {"branch": None}}
        assert strat._evaluate_condition(wf.edges[0], out) is False
