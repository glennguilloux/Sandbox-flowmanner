# ─────────────────────────────────────────────────────────────────────
# Tests for Phase-3 graph promotion: a branching/conditional run renders
# as a full graph (nodes + conditional edges + which edges were taken),
# distinct from the DAG's layered step tree.
#
# Hermetic unit tests — no Postgres / Docker / Alembic. The async session
# and the substrate replay engine are faked with AsyncMock / SimpleNamespace
# so the suite runs on the host.
#
# Coverage:
#   * build_graph_workflow produces a WorkflowType.GRAPH with conditional
#     edges (decide → branch_a / branch_b) and a converging synthesize.
#   * RunService.get_run_graph derives the full node/edge set + runtime
#     `taken` flag from a synthetic event log over a stored snapshot.
#
# Run from the backend worktree:
#     PYTHONPATH=. uv run pytest app/tests/test_graph_run.py -q
# ─────────────────────────────────────────────────────────────────────
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.chat.substrate_client import build_graph_workflow
from app.services.run_service import RunService


def _fake_replay_state(task_states: dict) -> SimpleNamespace:
    """Mimic SubstrateRunState: only task_states is read by get_run_graph."""
    return SimpleNamespace(task_states=task_states)


def _graph_snapshot() -> dict:
    """A branching blueprint snapshot: a -> decide ; decide -> branch_a,branch_b ; both -> d."""
    return {
        "blueprint_type": "graph",
        "title": "Branching plan",
        "nodes": [
            {"id": "a", "type": "llm_call", "title": "Step A"},
            {"id": "decide", "type": "llm_call", "title": "Decide"},
            {"id": "branch_a", "type": "llm_call", "title": "Branch A"},
            {"id": "branch_b", "type": "llm_call", "title": "Branch B"},
            {"id": "d", "type": "llm_call", "title": "Synthesize"},
        ],
        "edges": [
            {"source": "a", "target": "decide"},
            {"source": "decide", "target": "branch_a", "condition": "x == 'branch_a'", "label": "a path"},
            {"source": "decide", "target": "branch_b", "condition": "x == 'branch_b'", "label": "b path"},
            {"source": "branch_a", "target": "d"},
            {"source": "branch_b", "target": "d"},
        ],
    }


# ── build_graph_workflow ───────────────────────────────────────────


def test_build_graph_workflow_sets_graph_type_with_conditional_edges():
    wf = build_graph_workflow(goal="route the work", run_id="run-g")
    assert wf.type.value == "graph"

    ids = {n.id for n in wf.nodes}
    assert ids == {"plan", "decide", "branch_a", "branch_b", "synthesize"}

    # Exactly two conditional edges leaving `decide` (the branch points).
    cond_edges = [e for e in wf.edges if e.source == "decide"]
    assert len(cond_edges) == 2
    assert {e.target for e in cond_edges} == {"branch_a", "branch_b"}
    assert all(e.condition for e in cond_edges)
    assert all(e.label for e in cond_edges)

    # Both branches converge on synthesize.
    synth_in = [e.source for e in wf.edges if e.target == "synthesize"]
    assert set(synth_in) == {"branch_a", "branch_b"}


# ── RunService.get_run_graph (event-log derived) ───────────────────


async def test_get_run_graph_returns_full_graph_with_taken_flags():
    """The graph must return every node + edge and mark taken branches."""
    snapshot = _graph_snapshot()

    fake_run = MagicMock()
    object.__setattr__(fake_run, "id", "run-g9")
    object.__setattr__(fake_run, "blueprint_id", "bp-g")
    object.__setattr__(fake_run, "status", "completed")
    object.__setattr__(fake_run, "snapshot", snapshot)

    # Synthetic event-log state: a, decide, branch_b, d executed; branch_a did NOT.
    task_states = {
        "a": {"status": "completed"},
        "decide": {"status": "completed"},
        "branch_b": {"status": "completed"},
        "d": {"status": "completed"},
        # branch_a intentionally absent → not executed
    }

    db = MagicMock()
    service = RunService(db=db)

    with (
        patch.object(RunService, "get", new=AsyncMock(return_value=fake_run)),
        patch(
            "app.services.run_service.get_replay_engine",
            return_value=SimpleNamespace(rebuild_state=AsyncMock(return_value=_fake_replay_state(task_states))),
        ),
    ):
        graph = await service.get_run_graph("run-g9", 1)

    assert graph["run_id"] == "run-g9"
    assert graph["workflow_type"] == "graph"
    assert graph["status"] == "completed"

    # All 5 nodes present with status from the event log.
    nodes = {n["node_id"]: n for n in graph["nodes"]}
    assert set(nodes) == {"a", "decide", "branch_a", "branch_b", "d"}
    assert nodes["a"]["status"] == "completed"
    assert nodes["branch_a"]["status"] == "pending"  # not in event log
    assert nodes["branch_b"]["status"] == "completed"
    assert nodes["d"]["status"] == "completed"

    # Edges carry condition + label + a runtime `taken` flag.
    edges = {(e["source"], e["target"]): e for e in graph["edges"]}
    decide_to_b = edges[("decide", "branch_a")]
    decide_to_c = edges[("decide", "branch_b")]
    assert decide_to_b["condition"]
    assert decide_to_b["label"]
    assert decide_to_c["condition"]
    assert decide_to_c["label"]
    # branch_a was NOT executed → both its edges (decide→branch_a and
    # branch_a→d) are not taken; branch_b WAS executed → its edges are taken.
    assert decide_to_b["taken"] is False
    assert decide_to_c["taken"] is True
    # The converging edge branch_b → synthesize is taken (branch_b ran).
    assert edges[("branch_b", "d")]["taken"] is True
    assert edges[("branch_a", "d")]["taken"] is False


async def test_get_run_graph_solo_is_single_node_no_edges():
    """A solo run (1 node) yields one node and zero edges."""
    snapshot = {
        "blueprint_type": "solo",
        "title": "Solo",
        "nodes": [{"id": "goal", "type": "llm_call", "title": "Goal"}],
        "edges": [],
    }
    fake_run = MagicMock()
    object.__setattr__(fake_run, "id", "run-solo-g")
    object.__setattr__(fake_run, "blueprint_id", "bp-sg")
    object.__setattr__(fake_run, "status", "pending")
    object.__setattr__(fake_run, "snapshot", snapshot)

    db = MagicMock()
    service = RunService(db=db)
    with (
        patch.object(RunService, "get", new=AsyncMock(return_value=fake_run)),
        patch(
            "app.services.run_service.get_replay_engine",
            return_value=SimpleNamespace(rebuild_state=AsyncMock(return_value=_fake_replay_state({}))),
        ),
    ):
        graph = await service.get_run_graph("run-solo-g", 1)

    assert graph["workflow_type"] == "solo"
    assert len(graph["nodes"]) == 1
    assert graph["nodes"][0]["node_id"] == "goal"
    assert graph["edges"] == []
