"""Validation & hardening of substrate DAG edge-target conversion.

Pure-conversion test for ``blueprint_to_workflow`` (the Blueprint/Run snapshot
-> canonical Workflow adapter in ``app/services/substrate/adapters.py``).

This test does NOT touch the DB, LLM, or tools. It calls the adapter directly
with Blueprint-shaped ``{nodes, edges, ...}`` snapshots and asserts the exact
surviving node/edge counts, NodeType mapping, and effective WorkflowType.

It is the lock-in guard for edge-target handling during the Blueprint migration.

Edge-target failure modes covered
---------------------------------
A. sentinel source/target (start/end) is dropped from the edge set
B. edge whose source/target points to a node id that does NOT exist in the
   snapshot is PASSED THROUGH (no crash, no validation)  [documented, see report]
C. self-loop (source == target) is PASSED THROUGH (no crash, no validation)
D. duplicate edges (same source+target) are PASSED THROUGH (not deduplicated)
E. edge missing ``source`` or ``target`` is DROPPED (logged warning) instead of
   crashing the whole conversion  [FIXED, see report: adapters.py edge loop]
F. topology-derived solo->dag flip correctness (exactly-1-node solo stays solo;
   solo with >1 real node OR any edge becomes DAG; declared dag stays dag)
G. NodeType mapping for every template nodeType value
   (task/transform/condition/approval/log/loop/webhook/parallel/rag_query)

Nothing here mutates production source. The adapter is exercised read-only.
"""

from __future__ import annotations

import pytest

from app.services.substrate.adapters import blueprint_to_workflow
from app.services.substrate.workflow_models import NodeType, WorkflowType

# ── Helpers ──────────────────────────────────────────────────────────────────


def _node(nid: str, node_type: str) -> dict:
    """Build a Blueprint-shaped node.

    Mirrors seed_templates.make_template, where the node's *id* is the
    step id and the type living in ``data.nodeType`` is the template nodeType.
    For these tests we set ``id == nodeType`` so a node's Id is its nodeType
    string (this is what the adapter keyed on before the HEAD change, and the
    mapping is driven by the ``type`` field / ``data.nodeType`` either way).
    """
    return {"id": nid, "type": node_type, "data": {"nodeType": node_type}}


def _edge(src: str, tgt: str) -> dict:
    return {"source": src, "target": tgt}


def _convert(snapshot: dict):
    return blueprint_to_workflow(snapshot, blueprint_id="bp-test", user_id="user-1")


# ── A. Start/end sentinel nodes + their edges are dropped ────────────────────


class TestSentinelDrop:
    def test_sentinels_dropped_but_internal_edge_between_real_nodes_survives(self):
        snapshot = {
            "blueprint_type": "solo",
            "title": "ETL",
            "nodes": [
                _node("start-1", "start"),
                _node("task-extract", "task"),
                _node("task-load", "task"),
                _node("end-1", "end"),
            ],
            # start->extract and load->end reference sentinels and must vanish;
            # task-extract->task-load is real<->real and must survive.
            "edges": [
                _edge("start-1", "task-extract"),
                _edge("task-extract", "task-load"),
                _edge("task-load", "end-1"),
            ],
        }
        wf = _convert(snapshot)

        surviving_ids = {n.id for n in wf.nodes}
        assert surviving_ids == {"task-extract", "task-load"}, surviving_ids
        assert [(e.source, e.target) for e in wf.edges] == [("task-extract", "task-load")]

    def test_internal_edge_survives_when_both_endpoints_real(self):
        snapshot = {
            "blueprint_type": "solo",
            "title": "transform",
            "nodes": [
                _node("start-1", "start"),
                _node("t1", "transform"),
                _node("t2", "task"),
                _node("end-1", "end"),
            ],
            "edges": [
                _edge("start-1", "t1"),  # dropped (start sentinel)
                _edge("t1", "t2"),  # kept  (both real)
                _edge("t2", "end-1"),  # dropped (end sentinel)
            ],
        }
        wf = _convert(snapshot)
        assert len(wf.nodes) == 2
        assert [(e.source, e.target) for e in wf.edges] == [("t1", "t2")]


# ── B/C/D/E. Malformed-but-tolerable (or crashing) edge inputs ───────────────


class TestMalformedEdges:
    def test_orphan_edge_to_missing_node_is_passed_through(self):
        """DOCUMENTED BEHAVIOR: the adapter does NOT validate that an edge's
        endpoint exists in the node set. An edge pointing at a non-existent
        node id is passed straight through (no crash)."""
        snapshot = {
            "blueprint_type": "solo",
            "title": "orphan",
            "nodes": [_node("a", "task"), _node("b", "task")],
            "edges": [_edge("a", "ghost"), _edge("a", "b")],
        }
        wf = _convert(snapshot)
        assert len(wf.nodes) == 2
        pairs = {(e.source, e.target) for e in wf.edges}
        assert pairs == {("a", "ghost"), ("a", "b")}, pairs

    def test_self_loop_is_passed_through(self):
        """DOCUMENTED BEHAVIOR: source == target is not rejected."""
        snapshot = {
            "blueprint_type": "solo",
            "title": "self",
            "nodes": [_node("x", "task")],
            "edges": [_edge("x", "x")],
        }
        wf = _convert(snapshot)
        assert len(wf.nodes) == 1
        assert [(e.source, e.target) for e in wf.edges] == [("x", "x")]

    def test_duplicate_edges_are_not_deduplicated(self):
        """DOCUMENTED BEHAVIOR: same (source, target) twice is kept twice."""
        snapshot = {
            "blueprint_type": "solo",
            "title": "dup",
            "nodes": [_node("a", "task"), _node("b", "task")],
            "edges": [_edge("a", "b"), _edge("a", "b")],
        }
        wf = _convert(snapshot)
        assert len(wf.edges) == 2, [e.model_dump() for e in wf.edges]

    @pytest.mark.parametrize(
        "bad_edge",
        [
            {"source": "a"},  # missing target
            {"target": "b"},  # missing source
            {},  # missing both
        ],
        ids=["missing-target", "missing-source", "missing-both"],
    )
    def test_edge_missing_endpoint_is_dropped_not_raised(self, bad_edge):
        """FIXED (FIX 1): an edge with no ``source`` or no ``target`` no longer
        raises pydantic ValidationError and aborts the WHOLE blueprint
        conversion. The offending edge is dropped (with a logged warning) and
        the surrounding valid graph converts normally.

        Previously (baseline 24b1895e) this asserted ``pytest.raises(
        ValidationError)`` to lock the bug in place; the source fix in
        adapters.py wraps ``WorkflowEdge(**e)`` so a single malformed edge is
        skipped instead of crashing the run.
        """
        snapshot = {
            "blueprint_type": "solo",
            "title": "bad-edge",
            "nodes": [_node("a", "task"), _node("b", "task")],
            "edges": [bad_edge],
        }
        # No crash: the malformed edge is silently dropped.
        wf = _convert(snapshot)
        # Both real nodes survive; the single bad edge produced zero edges.
        assert len(wf.nodes) == 2
        assert wf.edges == []


# ── F. Topology-derived solo -> dag flip ─────────────────────────────────────


class TestTopologyTypeDerivation:
    def test_empty_snapshot_stays_solo(self):
        """FIXED (FIX 2): an empty snapshot (no nodes/edges) declared 'solo'
        stays SOLO, restoring the previously-documented empty-snapshot contract
        (see tests/test_adapters.py::test_blueprint_with_empty_snapshot).

        Baseline 24b1895e locked in the regression (empty -> DAG) because the
        topology rule ``declared=='solo' and (len(real_nodes)!=1 or edges)``
        evaluated ``0 != 1`` -> True -> DAG. The source fix guards the
        solo->dag flip on ``workflow_nodes`` being non-empty, so an empty
        blueprint keeps its declared SOLO type. The flip still fires for
        non-empty blueprints (covered by the sibling tests below).
        """
        wf = _convert({})
        assert wf.type == WorkflowType.SOLO

    def test_solo_exactly_one_node_no_edges_stays_solo(self):
        wf = _convert(
            {
                "blueprint_type": "solo",
                "title": "single",
                "nodes": [_node("a", "task")],
                "edges": [],
            }
        )
        assert wf.type == WorkflowType.SOLO

    def test_solo_with_two_real_nodes_flips_to_dag(self):
        wf = _convert(
            {
                "blueprint_type": "solo",
                "title": "multi",
                "nodes": [_node("a", "task"), _node("b", "task")],
                "edges": [],
            }
        )
        assert wf.type == WorkflowType.DAG

    def test_solo_sentinel_edge_does_not_force_dag_when_only_one_real_node(self):
        """A 'solo' blueprint with exactly one REAL node and only a
        start->real sentinel edge: the sentinel edge is dropped, leaving 0 real
        edges and 1 real node, so the topology rule keeps it SOLO."""
        wf = _convert(
            {
                "blueprint_type": "solo",
                "title": "one-edge",
                "nodes": [_node("start-1", "start"), _node("a", "task")],
                "edges": [_edge("start-1", "a")],
            }
        )
        assert len(wf.nodes) == 1
        assert len(wf.edges) == 0
        assert wf.type == WorkflowType.SOLO

    def test_solo_real_edge_forces_dag(self):
        """A 'solo' blueprint with 1 real node but a real->real self edge yields
        DAG (an edge now exists after sentinel dropping)."""
        wf = _convert(
            {
                "blueprint_type": "solo",
                "title": "self",
                "nodes": [_node("a", "task")],
                "edges": [_edge("a", "a")],
            }
        )
        assert wf.type == WorkflowType.DAG

    def test_declared_dag_stays_dag_with_single_node(self):
        wf = _convert(
            {
                "blueprint_type": "dag",
                "title": "declared-dag",
                "nodes": [_node("a", "task")],
                "edges": [],
            }
        )
        assert wf.type == WorkflowType.DAG


# ── G. NodeType mapping for every template nodeType ──────────────────────────


class TestNodeTypeMapping:
    def test_template_node_types_map_without_crashing(self):
        # ids == nodeType (per _node above), so a node's id is its nodeType.
        template_types = [
            "task",
            "transform",
            "condition",
            "approval",
            "log",
            "loop",
            "webhook",
            "parallel",
            "rag_query",
        ]
        snapshot = {
            "blueprint_type": "solo",
            "title": "typemap",
            "nodes": [_node(t, t) for t in template_types],
            "edges": [],
        }
        wf = _convert(snapshot)
        # start/end not included above -> all 9 should survive.
        assert len(wf.nodes) == 9, [n.id for n in wf.nodes]

        by_id = {n.id: n.type for n in wf.nodes}
        assert by_id["approval"] == NodeType.APPROVAL
        assert by_id["parallel"] == NodeType.FAN_OUT
        assert by_id["rag_query"] == NodeType.RAG_QUERY
        # Documented semantic-loss: these all fall back to LLM_CALL because they
        # are absent from _TASK_TYPE_MAP (see report). Locked as current behavior.
        for t in ["task", "transform", "condition", "log", "loop", "webhook"]:
            assert by_id[t] == NodeType.LLM_CALL, (t, by_id[t])

    def test_explicit_canonical_type_via_data_nodeType(self):
        """The map path uses ``data.nodeType``. 'tool' maps to TOOL_CALL;
        'llm_call' maps to LLM_CALL. (A raw ``type`` field value that is not in
        the map -- e.g. 'tool_call' -- is NOT the looked-up key; mapping is on
        data.nodeType, with ``type`` as fallback.)
        """
        snapshot = {
            "blueprint_type": "solo",
            "title": "canonical",
            "nodes": [
                {"id": "x", "type": "llm_call", "data": {"nodeType": "llm_call"}},
                {"id": "y", "type": "tool", "data": {"nodeType": "tool"}},
            ],
            "edges": [],
        }
        wf = _convert(snapshot)
        types = {n.id: n.type for n in wf.nodes}
        assert types["x"] == NodeType.LLM_CALL
        assert types["y"] == NodeType.TOOL_CALL
