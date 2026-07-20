# ─────────────────────────────────────────────────────────────────────
# Tests for Phase-2 DAG promotion: a multi-step plan renders as a layered
# step tree derived from the run's event log.
#
# These are hermetic unit tests — no Postgres / Docker / Alembic. The async
# session and the substrate replay engine are faked with AsyncMock /
# SimpleNamespace so the test suite runs on the host.
#
# Coverage:
#   * build_dag_workflow produces a WorkflowType.DAG with the expected
#     layered topology (plan → N steps → synthesize).
#   * _workflow_layers groups nodes into dependency-ordered layers.
#   * RunService.get_run_tree derives layer grouping + node status from a
#     synthetic event log (replay state) over a stored snapshot topology.
#   * run_dag_turn_sse emits a run_tree frame before streaming events.
#
# Run from the backend worktree:
#     PYTHONPATH=. uv run pytest app/tests/test_dag_run_tree.py -q
# ─────────────────────────────────────────────────────────────────────
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat.substrate_client import (
    _workflow_layers,
    build_dag_workflow,
    run_dag_turn_sse,
)
from app.services.run_service import RunService

# ── builders ────────────────────────────────────────────────────────


def _dag_snapshot() -> dict:
    """A 3-layer blueprint snapshot: a -> b,c ; b,c -> d."""
    return {
        "blueprint_type": "dag",
        "title": "Multi-step plan",
        "nodes": [
            {"id": "a", "type": "llm_call", "title": "Step A"},
            {"id": "b", "type": "llm_call", "title": "Step B"},
            {"id": "c", "type": "llm_call", "title": "Step C"},
            {"id": "d", "type": "llm_call", "title": "Step D"},
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "a", "target": "c"},
            {"source": "b", "target": "d"},
            {"source": "c", "target": "d"},
        ],
    }


def _fake_replay_state(task_states: dict) -> SimpleNamespace:
    """Mimic SubstrateRunState: only task_states is read by get_run_tree."""
    return SimpleNamespace(task_states=task_states)


# ── build_dag_workflow ──────────────────────────────────────────────


def test_build_dag_workflow_sets_dag_type():
    wf = build_dag_workflow(goal="ship the feature", run_id="run-1")
    assert wf.type.value == "dag"
    # plan → N step nodes → synthesize
    ids = {n.id for n in wf.nodes}
    assert ids == {"plan", "step_1", "step_2", "step_3", "synthesize"}
    titles = {n.title for n in wf.nodes}
    assert "Plan decomposition" in titles
    assert "Synthesize" in titles
    # Every step depends on plan; synthesize depends on every step.
    step_nodes = [n for n in wf.nodes if n.id.startswith("step_")]
    assert all("plan" in n.dependencies for n in step_nodes)
    synth = next(n for n in wf.nodes if n.id == "synthesize")
    assert {s.id for s in step_nodes} <= set(synth.dependencies)


def test_build_dag_workflow_respects_step_count():
    wf = build_dag_workflow(goal="g", run_id="r", budget={"step_count": 5})
    step_nodes = [n for n in wf.nodes if n.id.startswith("step_")]
    assert len(step_nodes) == 5
    # Capped at 5 even if asked for more.
    wf2 = build_dag_workflow(goal="g", run_id="r2", budget={"step_count": 99})
    step_nodes2 = [wf2.nodes[i] for i in range(len(wf2.nodes)) if wf2.nodes[i].id.startswith("step_")]
    assert len(step_nodes2) == 5


# ── _workflow_layers ────────────────────────────────────────────────


def test_workflow_layers_grouping():
    wf = build_dag_workflow(goal="g", run_id="r")
    layers = _workflow_layers(wf)
    # 3 layers: [plan], [step_1..3], [synthesize]
    assert len(layers) == 3
    assert layers[0] == ["plan"]
    assert set(layers[1]) == {"step_1", "step_2", "step_3"}
    assert layers[2] == ["synthesize"]


def test_workflow_layers_from_dag_snapshot():
    from app.services.substrate.adapters import blueprint_to_workflow

    wf = blueprint_to_workflow(snapshot=_dag_snapshot(), blueprint_id="bp-1", user_id="1")
    layers = _workflow_layers(wf)
    # a in layer 0; b,c in layer 1; d in layer 2
    assert layers[0] == ["a"]
    assert set(layers[1]) == {"b", "c"}
    assert layers[2] == ["d"]


# ── RunService.get_run_tree (event-log derived) ─────────────────────


async def test_get_run_tree_derives_layer_grouping_and_status():
    """The tree must group nodes by layer and surface event-log status."""
    snapshot = _dag_snapshot()

    fake_run = MagicMock()
    object.__setattr__(fake_run, "id", "run-9")
    object.__setattr__(fake_run, "blueprint_id", "bp-1")
    object.__setattr__(fake_run, "status", "completed")
    object.__setattr__(fake_run, "snapshot", snapshot)

    # Synthetic event-log state: a/b/d completed, c failed.
    task_states = {
        "a": {"status": "completed"},
        "b": {"status": "completed"},
        "c": {"status": "failed"},
        "d": {"status": "completed"},
    }

    db = MagicMock()  # not touched because get() and replay are patched
    service = RunService(db=db)

    with (
        patch.object(RunService, "get", new=AsyncMock(return_value=fake_run)),
        patch(
            "app.services.run_service.get_replay_engine",
            return_value=SimpleNamespace(rebuild_state=AsyncMock(return_value=_fake_replay_state(task_states))),
        ),
    ):
        tree = await service.get_run_tree("run-9", 1)

    assert tree["run_id"] == "run-9"
    assert tree["workflow_type"] == "dag"
    assert tree["status"] == "completed"
    layers = tree["layers"]
    assert len(layers) == 3
    assert layers[0]["layer"] == 0
    assert [n["node_id"] for n in layers[0]["nodes"]] == ["a"]
    assert {n["node_id"] for n in layers[1]["nodes"]} == {"b", "c"}
    assert [n["node_id"] for n in layers[2]["nodes"]] == ["d"]

    # Status must come from the event log, not default to pending.
    by_id = {n["node_id"]: n for layer in layers for n in layer["nodes"]}
    assert by_id["a"]["status"] == "completed"
    assert by_id["b"]["status"] == "completed"
    assert by_id["c"]["status"] == "failed"
    assert by_id["d"]["status"] == "completed"

    # depends_on reflects the snapshot topology.
    assert by_id["b"]["depends_on"] == ["a"]
    assert by_id["d"]["depends_on"] == ["b", "c"]


async def test_get_run_tree_solo_is_single_layer():
    """A solo run (1 node) yields a single layer with one pending node."""
    snapshot = {
        "blueprint_type": "solo",
        "title": "Solo",
        "nodes": [{"id": "goal", "type": "llm_call", "title": "Goal"}],
        "edges": [],
    }
    fake_run = MagicMock()
    object.__setattr__(fake_run, "id", "run-solo")
    object.__setattr__(fake_run, "blueprint_id", "bp-s")
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
        tree = await service.get_run_tree("run-solo", 1)

    assert tree["workflow_type"] == "solo"
    assert len(tree["layers"]) == 1
    assert tree["layers"][0]["nodes"][0]["node_id"] == "goal"
    assert tree["layers"][0]["nodes"][0]["status"] == "pending"


# ── run_dag_turn_sse emits a run_tree frame ─────────────────────────


@pytest.mark.asyncio
async def test_run_dag_turn_sse_emits_run_tree_frame():
    """The dag SSE pipe must emit a run_tree frame with layered vocab."""
    from app.tests.test_substrate_client import _FakeEventLog

    fake_log = _FakeEventLog([])

    async def _fake_execute(*args, **kwargs):
        return {"success": True, "status": "completed"}

    with (
        patch(
            "app.services.chat.substrate_client.get_event_log",
            return_value=fake_log,
        ),
        patch(
            "app.services.chat.substrate_client.execute_dag_run",
            _fake_execute,
        ),
    ):
        frames = [
            __import__("json").loads(f) async for f in run_dag_turn_sse(db=object(), goal="plan it", run_id="dag-1")
        ]

    types = [f["type"] for f in frames]
    assert types[0] == "run_started"
    assert "run_tree" in types
    # run_tree must carry the layered structure.
    tree_frame = next(f for f in frames if f["type"] == "run_tree")
    assert tree_frame["workflow_type"] == "dag"
    assert len(tree_frame["layers"]) == 3
    assert tree_frame["layers"][0]["layer"] == 0
    assert tree_frame["layers"][0]["nodes"][0]["node_id"] == "plan"
    # Every node carries status + depends_on (layered step vocab).
    for layer in tree_frame["layers"]:
        for node in layer["nodes"]:
            assert "status" in node
            assert "depends_on" in node
            assert "node_id" in node
    assert frames[-1]["type"] == "run_complete"
    assert frames[-1]["workflow_type"] == "dag"
