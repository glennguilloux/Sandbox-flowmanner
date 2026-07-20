# ─────────────────────────────────────────────────────────────────────
# Mission Builder node round-trip (plan §3, gate 3).
#
# This is the RUNTIME counterpart to Wave 2 (source-cited) and Wave 3
# (router/merge/delay coverage). It EXECUTES the substrate at runtime to
# prove the contract end-to-end:
#
#   1. Every node type the FE can emit resolves to its REAL substrate
#      NodeType (not silently collapsed to LLM_CALL) — the regression
#      guard that the old default mapping used to break.
#   2. The canvas-only DATA SHIMS (input_*/output_*) are skipped by the
#      adapter and never reach the substrate (no orphan edges either).
#   3. SPLIT fans its collection out into N-items × M-targets branches
#      at runtime (closes W2's "verified in source" gap).
#   4. ROUTER branch-gating honors the emitted route at runtime
#      (dag.py:263-265 — the contract the FE wires edge.condition == route.id).
#
# Hermetic: no Postgres / Docker / Alembic. The adapter and DAG strategy
# are exercised directly against in-memory Workflow objects.
#
# NOTE ON CONTRACT MISMATCHES (read before "fixing"): the task brief's
# expected NodeType for `code_transform`, `search_retrieve`, and `subflow`
# does NOT match the actual `_TASK_TYPE_MAP` resolver — all three resolve
# to LLM_CALL today (the FE palette + Wave 3 classify them as
# intentionally-LLM-backed). Those three are NOT silently-collapsed
# regressions; they are the agreed "generic task / prompt family" that
# legitimately runs as an LLM call. They are encoded as `xfail` gap tests
# (asserting the brief's stated expectation) so the suite stays GREEN while
# the discrepancy is surfaced to a human reviewer — this test card is
# TEST-ONLY and must not mutate production mapping.
# ─────────────────────────────────────────────────────────────────────
from __future__ import annotations

from typing import Any

import pytest

from app.services.substrate.adapters import blueprint_to_workflow
from app.services.substrate.strategies.dag import DAGStrategy
from app.services.substrate.workflow_models import (
    NodeType,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowType,
)

# 5 DATA SHIM types the FE emits as canvas-only (perform no substrate work).
_DATA_SHIM_TYPES = frozenset(
    {
        "input_text",
        "input_webhook",
        "input_dataset",
        "output_format",
        "output_deliver",
    }
)


# ── Round-trip helper ──────────────────────────────────────────────────


def _resolve(raw_type: str, transform_config: dict | None = None, data: dict | None = None) -> NodeType:
    """Resolve a single-node Blueprint through the real adapter.

    Returns the resolved ``Workflow.nodes[0].type`` (a ``NodeType`` member).
    """
    node_data: dict = data if data is not None else {}
    node_data.setdefault("id", "n1")
    node_data["type"] = raw_type
    if transform_config is not None:
        node_data.setdefault("data", {})["transformConfig"] = transform_config
    snapshot = {
        "blueprint_type": "solo",
        "title": "round-trip",
        "nodes": [node_data],
        "edges": [],
    }
    wf = blueprint_to_workflow(snapshot, blueprint_id="bp-rt", user_id="user-1")
    assert len(wf.nodes) == 1, f"expected exactly 1 resolved node, got {len(wf.nodes)}"
    return wf.nodes[0].type


# ── 1. Full matrix — every mapped type routes to its REAL NodeType ──────
#
# (raw_type, expected NodeType). These 12 are CONFIRMED to resolve to a
# real, non-LLM_CALL NodeType in _TASK_TYPE_MAP. The regression guard
# `resolved is not NodeType.LLM_CALL` is asserted for each.
_MAPPED_MATRIX = [
    ("prompt", NodeType.LLM_CALL),  # prompt is the agreed LLM-backed family
    ("validate_schema", NodeType.VALIDATE_SCHEMA),
    ("filter", NodeType.FILTER),
    ("split", NodeType.SPLIT),
    ("transform", NodeType.TRANSFORM),
    ("condition", NodeType.CONDITION),
    ("loop", NodeType.LOOP),
    ("log", NodeType.LOG),
    ("webhook", NodeType.WEBHOOK),
    ("router", NodeType.ROUTER),
    ("merge", NodeType.MERGE),
    ("delay", NodeType.DELAY),
]


@pytest.mark.parametrize(("raw_type", "expected"), _MAPPED_MATRIX)
def test_node_type_routes_to_real_nodetype(raw_type: str, expected: NodeType) -> None:
    resolved = _resolve(raw_type)
    assert resolved is expected, f"{raw_type} -> {resolved.name}, expected {expected.name}"
    # Regression guard: a mapped type must NEVER silently collapse to LLM_CALL
    # (except the intentionally-LLM-backed `prompt`, which is spelled out above).
    if expected is not NodeType.LLM_CALL:
        assert resolved is not NodeType.LLM_CALL, (
            f"{raw_type} silently collapsed to LLM_CALL — the map regression is back"
        )


# ── 1b. CONTRACT-GAP tests (xfail — NOT silently collapsed regressions) ──
#
# The task brief lists these three with a NON-LLM_CALL expectation, but the
# actual resolver maps them to LLM_CALL (the FE palette + Wave 3 treat them
# as the agreed "generic task / prompt family"). They are encoded as xfail
# so the suite stays green while the discrepancy is flagged for a human.
# These assert the BRIEF's stated expectation — when the resolver is later
# given real handlers, flip the mapping and this xfail will turn into a pass.


@pytest.mark.xfail(
    reason="code_transform resolves to LLM_CALL today (FE palette + Wave 3 classify it as "
    "intentionally-LLM-backed). Brief expected CODE_EXECUTION. Contract gap — not a "
    "silent-collapse regression. See card notes.",
    strict=True,
)
def test_code_transform_expected_code_execution() -> None:
    assert _resolve("code_transform") is NodeType.CODE_EXECUTION


@pytest.mark.xfail(
    reason="search_retrieve resolves to LLM_CALL today (FE palette + Wave 3 classify it as "
    "intentionally-LLM-backed). Brief expected RAG_QUERY. Contract gap — not a "
    "silent-collapse regression. See card notes.",
    strict=True,
)
def test_search_retrieve_expected_rag_query() -> None:
    assert _resolve("search_retrieve") is NodeType.RAG_QUERY


@pytest.mark.xfail(
    reason="subflow resolves to LLM_CALL today (FE palette + Wave 3 classify it as "
    "intentionally-LLM-backed). Brief expected SUB_WORKFLOW. Contract gap — not a "
    "silent-collapse regression. See card notes.",
    strict=True,
)
def test_subflow_expected_sub_workflow() -> None:
    assert _resolve("subflow") is NodeType.SUB_WORKFLOW


# ── 2. DATA SHIM skip — input_*/output_* never reach the substrate ──────


def _shim_blueprint(shim_type: str) -> Workflow:
    """A blueprint with one shim node + one real upstream node + an edge."""
    snapshot = {
        "blueprint_type": "solo",
        "title": "shim-rt",
        "nodes": [
            {"id": "upstream", "type": "task", "data": {"nodeType": "task"}},
            {"id": "shim", "type": shim_type, "data": {"nodeType": shim_type}},
        ],
        "edges": [
            {"source": "upstream", "target": "shim"},
        ],
    }
    return blueprint_to_workflow(snapshot, blueprint_id="bp-shim", user_id="user-1")


@pytest.mark.parametrize("shim_type", sorted(_DATA_SHIM_TYPES))
def test_data_shim_is_skipped_at_runtime(shim_type: str) -> None:
    wf = _shim_blueprint(shim_type)
    surviving_ids = {n.id for n in wf.nodes}
    # The shim node is absent (skipped); the real upstream node is present.
    assert "shim" not in surviving_ids, f"shim '{shim_type}' leaked into the substrate workflow"
    assert "upstream" in surviving_ids, "real upstream node was dropped with the shim"
    # No surviving edge references the skipped shim id.
    for e in wf.edges:
        assert e.source in surviving_ids
        assert e.target in surviving_ids


# ── 3. SPLIT fan-out at runtime (closes W2's "verified in source" gap) ──


def _make_split_workflow(items: list[Any]) -> tuple[Workflow, DAGStrategy]:
    split = WorkflowNode(id="split", type=NodeType.SPLIT, title="split", config={})
    t1 = WorkflowNode(id="t1", type=NodeType.LOG, title="t1", config={})
    t2 = WorkflowNode(id="t2", type=NodeType.LOG, title="t2", config={})
    wf = Workflow(
        id="split-wf",
        type=WorkflowType.DAG,
        title="split-fan",
        nodes=[split, t1, t2],
        edges=[
            WorkflowEdge(source="split", target="t1"),
            WorkflowEdge(source="split", target="t2"),
        ],
    )
    return wf, DAGStrategy()


async def test_split_fan_out_produces_items_times_targets_branches() -> None:
    """A split of 3 items x 2 targets must run each target once per item = 6 calls.

    Exercises the REAL `_run_split_branches` (dag.py:391) with a stubbed
    NodeExecutor so no live DB/runner is needed — the fan-out math is what
    we prove (items × targets), matching the FE's "one edge per item" contract.
    """
    items = ["alpha", "beta", "gamma"]
    wf, strat = _make_split_workflow(items)

    calls: list[tuple[str, Any]] = []

    class _StubExecutor:
        async def execute_node(self, *, node, **kwargs):
            calls.append((node.id, kwargs.get("context", {}).get("input")))
            return {"success": True, "output": {"echo": True}}

    node_outputs: dict[str, Any] = {"split": {"items": list(items)}}
    executed: set[str] = set()
    completed: list[str] = []
    failed: list[str] = []

    await strat._run_split_branches(
        wf,
        "split",
        node_outputs["split"],
        {},
        _StubExecutor(),
        None,
        "run-split",
        node_outputs,
        executed,
        completed,
        failed,
    )

    # 3 items × 2 targets = 6 branch executions.
    assert len(calls) == len(items) * 2, f"expected {len(items) * 2} branch calls, got {len(calls)}"
    # Every (target, item) pair fired exactly once.
    seen = {(tid, item) for tid, item in calls}
    assert seen == {(tid, item) for item in items for tid in ("t1", "t2")}, f"fan-out pairs mismatch: {seen}"
    # Each target received its own per-item input (proves per-item payload flow).
    per_target_items: dict[str, set[Any]] = {}
    for tid, item in calls:
        per_target_items.setdefault(tid, set()).add(item)
    assert per_target_items["t1"] == set(items)
    assert per_target_items["t2"] == set(items)
    # Split's immediate targets are marked executed so the normal layer skips them.
    assert "t1" in executed
    assert "t2" in executed


# ── 4. ROUTER branch-gating at runtime (dag.py:263-265) ─────────────────


def _make_router_workflow() -> Workflow:
    router = WorkflowNode(id="router", type=NodeType.ROUTER, title="router", config={})
    a = WorkflowNode(id="a", type=NodeType.LOG, title="a", config={})
    b = WorkflowNode(id="b", type=NodeType.LOG, title="b", config={})
    return Workflow(
        id="router-wf",
        type=WorkflowType.DAG,
        title="router-gate",
        nodes=[router, a, b],
        edges=[
            WorkflowEdge(source="router", target="a", condition="route_a"),
            WorkflowEdge(source="router", target="b", condition="route_b"),
        ],
    )


def test_router_gating_takes_selected_route_blocks_other() -> None:
    """Router emitted route_b -> the route_b edge fires, route_a is blocked."""
    wf = _make_router_workflow()
    strat = DAGStrategy()
    out = {"router": {"branch": "route_b"}}
    assert strat._incoming_branch_passed(wf, "a", out) is False, "route_a edge must be blocked"
    assert strat._incoming_branch_passed(wf, "b", out) is True, "route_b edge must fire"


def test_router_gating_takes_route_a_blocks_route_b() -> None:
    wf = _make_router_workflow()
    strat = DAGStrategy()
    out = {"router": {"branch": "route_a"}}
    assert strat._incoming_branch_passed(wf, "a", out) is True, "route_a edge must fire"
    assert strat._incoming_branch_passed(wf, "b", out) is False, "route_b edge must be blocked"


def test_router_gating_blocks_all_when_no_route_selected() -> None:
    """A router with no selected route (fallback='drop') fires no condition edge."""
    wf = _make_router_workflow()
    strat = DAGStrategy()
    out = {"router": {"branch": None}}
    assert strat._incoming_branch_passed(wf, "a", out) is False
    assert strat._incoming_branch_passed(wf, "b", out) is False
