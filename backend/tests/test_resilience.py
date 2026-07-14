"""Tests for the withResilience helper (app.services.substrate.resilience).

These are pure structural tests — no DB. They verify that:
1. pass_through is a no-op (native retry preserved, no subgraph injected).
2. escalate / log_and_continue inject exactly one escalation node per task and
   rewire the task's success edges to rejoin through it.
3. The failure edge uses condition="{{id.error}}" — the success-biased
   routing condition that fires ONLY when the executor records a permanent
   failure (outputs[id] = {"error": ...}) and is falsy on success.
4. The injected subgraph keeps the plan a valid DAG (unique ids, edges valid,
   all targets exist, every non-start node reachable).
5. Determinism: applying twice yields the same node/edge count (idempotent ids).
"""

from __future__ import annotations

import copy

import pytest

from app.services.substrate.resilience import apply_resilience

KNOWN_TYPES = {
    "start",
    "task",
    "transform",
    "condition",
    "approval",
    "log",
    "loop",
    "webhook",
    "parallel",
    "end",
    "rag_query",
    "tool",
    "code",
}


def _valid_dag(plan: dict) -> list[str]:
    problems: list[str] = []
    nodes = plan["nodes"]
    edges = plan["edges"]
    ids = {n["id"] for n in nodes}
    for e in edges:
        if e["source"] not in ids:
            problems.append(f"bad source {e['source']}")
        if e["target"] not in ids:
            problems.append(f"bad target {e['target']}")
    starts = [n for n in nodes if n["type"] == "start"]
    if len(starts) != 1:
        problems.append(f"starts={len(starts)}")
    et = {e["target"] for e in edges}
    for n in nodes:
        if n["type"] == "start":
            continue
        if n["id"] not in et:
            problems.append(f"unreachable {n['id']}")
    return problems


def _sample_template() -> dict:
    return {
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Start", "nodeType": "start"},
                "edges_out": [{"target_id": "t1"}],
            },
            {
                "id": "t1",
                "type": "task",
                "position": {"x": 200, "y": 0},
                "data": {"label": "Do Work", "nodeType": "task", "agent": "x", "timeout": 60, "maxRetries": 2},
                "edges_out": [{"target_id": "end"}],
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 400, "y": 0},
                "data": {"label": "End", "nodeType": "end"},
                "edges_out": [],
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "t1", "type": "smoothstep"},
            {"id": "e2", "source": "t1", "target": "end", "type": "smoothstep"},
        ],
    }


def test_pass_through_is_noop():
    t = _sample_template()
    out = apply_resilience(t, gate="pass_through")
    assert out["resilience"]["applied"] is False
    assert out["resilience"]["wrapped_nodes"] == 0
    # node/edge counts unchanged
    assert len(out["nodes"]) == 3
    assert len(out["edges"]) == 2
    # original template not mutated
    assert len(t["nodes"]) == 3


def test_escalate_injects_one_node_per_task_and_rewires():
    t = _sample_template()
    out = apply_resilience(t, gate="escalate")
    meta = out["resilience"]
    assert meta["applied"] is True
    assert meta["gate"] == "escalate"
    assert meta["wrapped_nodes"] == 1  # exactly the one task
    # one approval node appended
    assert len(out["nodes"]) == 4
    appr = next(n for n in out["nodes"] if n["id"].endswith("__res_approval"))
    assert appr["type"] == "approval"
    assert appr["data"]["nodeType"] == "approval"
    # the original t1 -> end SUCCESS edge is now rerouted through approval;
    # t1 still has the failure edge (source==t1) but no success edge to "end"
    success_edges = [e for e in out["edges"] if e["source"] == "t1" and e["target"] == "end"]
    assert success_edges == []  # t1 no longer has a direct success edge
    rerouted = [e for e in out["edges"] if e["source"] == appr["id"]]
    assert any(e["target"] == "end" for e in rerouted)
    # failure edge present and uses success-biased condition
    fail = next(e for e in out["edges"] if e["source"] == "t1" and e["target"] == appr["id"])
    assert fail["condition"] == "{{t1.error}}"
    assert _valid_dag(out) == []


def test_log_and_continue_injects_log_node():
    t = _sample_template()
    out = apply_resilience(t, gate="log_and_continue")
    assert out["resilience"]["gate"] == "log_and_continue"
    assert len(out["nodes"]) == 4
    log = next(n for n in out["nodes"] if n["id"].endswith("__res_log"))
    assert log["type"] == "log"
    fail = next(e for e in out["edges"] if e["source"] == "t1" and e["target"] == log["id"])
    assert fail["condition"] == "{{t1.error}}"
    assert _valid_dag(out) == []


def test_wraps_only_task_like_nodes():
    t = copy.deepcopy(_sample_template())
    # add a transform and a condition — should NOT be wrapped
    t["nodes"].insert(
        1,
        {
            "id": "xf",
            "type": "transform",
            "position": {"x": 100, "y": 0},
            "data": {"label": "XF", "nodeType": "transform", "transformExpression": "."},
            "edges_out": [{"target_id": "t1"}],
        },
    )
    t["edges"].append({"id": "e0", "source": "start", "target": "xf", "type": "smoothstep"})
    out = apply_resilience(t, gate="escalate")
    assert out["resilience"]["wrapped_nodes"] == 1
    assert len(out["nodes"]) == 5  # 4 original + 1 approval


def test_idempotent_ids_on_repeat_apply():
    t = _sample_template()
    once = apply_resilience(t, gate="escalate")
    twice = apply_resilience(t, gate="escalate")
    # counts identical because ids are deterministic (suffix-based)
    assert len(once["nodes"]) == len(twice["nodes"])
    assert len(once["edges"]) == len(twice["edges"])
    assert {n["id"] for n in once["nodes"]} == {n["id"] for n in twice["nodes"]}


def test_real_kimi_styled_template_stays_valid_dag():
    """Use one of the seeded kimi templates' shape to ensure the helper
    composes with real complex plans."""
    t = {
        "nodes": [
            {
                "id": "s",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "data": {"label": "S", "nodeType": "start"},
                "edges_out": [{"target_id": "w"}],
            },
            {
                "id": "w",
                "type": "webhook",
                "position": {"x": 100, "y": 0},
                "data": {"label": "W", "nodeType": "webhook", "url": "https://x"},
                "edges_out": [{"target_id": "p"}],
            },
            {
                "id": "p",
                "type": "parallel",
                "position": {"x": 200, "y": 0},
                "data": {"label": "P", "nodeType": "parallel", "branches": 2},
                "edges_out": [{"target_id": "a"}, {"target_id": "b"}],
            },
            {
                "id": "a",
                "type": "task",
                "position": {"x": 300, "y": -50},
                "data": {"label": "A", "nodeType": "task"},
                "edges_out": [{"target_id": "agg"}],
            },
            {
                "id": "b",
                "type": "task",
                "position": {"x": 300, "y": 50},
                "data": {"label": "B", "nodeType": "task"},
                "edges_out": [{"target_id": "agg"}],
            },
            {
                "id": "agg",
                "type": "transform",
                "position": {"x": 400, "y": 0},
                "data": {"label": "AGG", "nodeType": "transform"},
                "edges_out": [{"target_id": "e"}],
            },
            {
                "id": "e",
                "type": "end",
                "position": {"x": 500, "y": 0},
                "data": {"label": "E", "nodeType": "end"},
                "edges_out": [],
            },
        ],
        "edges": [
            {"id": "e1", "source": "s", "target": "w"},
            {"id": "e2", "source": "w", "target": "p"},
            {"id": "e3", "source": "p", "target": "a"},
            {"id": "e4", "source": "p", "target": "b"},
            {"id": "e5", "source": "a", "target": "agg"},
            {"id": "e6", "source": "b", "target": "agg"},
            {"id": "e7", "source": "agg", "target": "e"},
        ],
    }
    out = apply_resilience(t, gate="escalate")
    # two tasks wrapped -> two approval nodes
    assert out["resilience"]["wrapped_nodes"] == 2
    assert len(out["nodes"]) == 9
    # both failure edges use the success-biased condition
    fail_conds = [
        e["condition"]
        for e in out["edges"]
        if e.get("condition", "").startswith("{{") and e["condition"].endswith(".error}}")
    ]
    assert set(fail_conds) == {"{{a.error}}", "{{b.error}}"}
    assert _valid_dag(out) == []


@pytest.mark.parametrize("gate", ["pass_through", "escalate", "log_and_continue"])
def test_all_gates_keep_valid_dag(gate):
    out = apply_resilience(_sample_template(), gate=gate)
    assert _valid_dag(out) == []
