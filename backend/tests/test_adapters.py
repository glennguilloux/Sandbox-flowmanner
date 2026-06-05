"""Unit tests for adapters.py (app/services/substrate/adapters.py).

Tests the ORM → Workflow conversion functions.
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from app.services.substrate.adapters import (
    mission_to_workflow,
    flow_to_workflow,
    graph_to_workflow,
    blueprint_to_workflow,
    _resolve_deps,
    _TASK_TYPE_MAP,
    _MISSION_TYPE_MAP,
)
from app.services.substrate.workflow_models import WorkflowType, NodeType


def _make_mission(**overrides):
    """Create a mock Mission ORM object."""
    m = MagicMock()
    m.id = overrides.get("id", "mission-1")
    m.title = overrides.get("title", "Test Mission")
    m.description = overrides.get("description", "A test")
    m.mission_type = overrides.get("mission_type", "solo")
    m.user_id = overrides.get("user_id", 1)
    m.budget_usd = overrides.get("budget_usd", 5.0)
    m.budget_seconds = overrides.get("budget_seconds", 120)
    m.actual_cost = overrides.get("actual_cost", 0.5)
    m.tokens_used = overrides.get("tokens_used", 500)
    m.plan = overrides.get("plan", None)
    m.fallback_strategy = overrides.get("fallback_strategy", "human_escalate")
    return m


def _make_task(**overrides):
    """Create a mock MissionTask ORM object."""
    t = MagicMock()
    t.id = overrides.get("id", "task-1")
    t.title = overrides.get("title", "Test Task")
    t.description = overrides.get("description", "Do something")
    t.task_type = overrides.get("task_type", "llm")
    t.tool_id = overrides.get("tool_id", None)
    t.assigned_model = overrides.get("assigned_model", "deepseek-chat")
    t.assigned_agent_id = overrides.get("assigned_agent_id", None)
    t.max_retries = overrides.get("max_retries", 3)
    t.status = overrides.get("status", "pending")
    t.output_data = overrides.get("output_data", None)
    t.error_message = overrides.get("error_message", None)
    t.retry_count = overrides.get("retry_count", 0)
    t.tokens_used = overrides.get("tokens_used", 0)
    t.cost = overrides.get("cost", 0.0)
    t.dependencies = overrides.get("dependencies", None)
    return t


class TestMappingDictionaries:
    def test_task_type_map_covers_key_types(self):
        assert _TASK_TYPE_MAP["llm"] == NodeType.LLM_CALL
        assert _TASK_TYPE_MAP["tool"] == NodeType.TOOL_CALL
        assert _TASK_TYPE_MAP["rag"] == NodeType.RAG_QUERY
        assert _TASK_TYPE_MAP["code"] == NodeType.CODE_EXECUTION
        assert _TASK_TYPE_MAP["web_search"] == NodeType.WEB_SEARCH
        assert _TASK_TYPE_MAP["approval"] == NodeType.APPROVAL

    def test_mission_type_map_covers_key_types(self):
        assert _MISSION_TYPE_MAP["solo"] == WorkflowType.SOLO
        assert _MISSION_TYPE_MAP["dag"] == WorkflowType.DAG
        assert _MISSION_TYPE_MAP["swarm"] == WorkflowType.SWARM
        assert _MISSION_TYPE_MAP["pipeline"] == WorkflowType.PIPELINE


class TestMissionToWorkflow:
    def test_solo_mission_with_no_tasks(self):
        mission = _make_mission(mission_type="solo")
        wf = mission_to_workflow(mission)

        assert wf.type == WorkflowType.SOLO
        assert wf.title == "Test Mission"
        assert wf.nodes == []
        assert wf.id == "mission-1"
        assert wf.user_id == "1"
        assert float(wf.budget.max_cost_usd) == 5.0
        assert float(wf.budget.spent_usd) == 0.5

    def test_mission_with_llm_tasks(self):
        mission = _make_mission()
        task1 = _make_task(id="t1", task_type="llm", title="Task 1")
        task2 = _make_task(
            id="t2", task_type="tool", title="Task 2", tool_id="web_search"
        )

        wf = mission_to_workflow(mission, tasks=[task1, task2])

        assert len(wf.nodes) == 2
        assert wf.nodes[0].type == NodeType.LLM_CALL
        assert wf.nodes[1].type == NodeType.TOOL_CALL
        assert wf.nodes[1].config["tool_name"] == "web_search"

    def test_dag_mission_builds_edges(self):
        mission = _make_mission(mission_type="dag")
        task1 = _make_task(id="t1", task_type="llm", title="First")
        task2 = _make_task(
            id="t2", task_type="llm", title="Second", dependencies=["t1"]
        )

        wf = mission_to_workflow(mission, tasks=[task1, task2])

        assert wf.type == WorkflowType.DAG
        assert len(wf.edges) == 1
        assert wf.edges[0].source == "t1"
        assert wf.edges[0].target == "t2"

    def test_unknown_mission_type_defaults_to_solo(self):
        mission = _make_mission(mission_type="something_weird")
        wf = mission_to_workflow(mission)
        assert wf.type == WorkflowType.SOLO

    def test_mission_with_plan_and_substrate_run_id(self):
        mission = _make_mission(plan={"substrate_run_id": "run-abc"})
        wf = mission_to_workflow(mission)
        assert wf.metadata["substrate_run_id"] == "run-abc"

    def test_task_type_mapping_all_types(self):
        mission = _make_mission()
        types_to_test = [
            "llm",
            "tool",
            "rag",
            "code",
            "web_search",
            "approval",
            "review",
            "file_operation",
        ]
        tasks = [
            _make_task(id=f"t-{t}", task_type=t, title=f"Task {t}")
            for t in types_to_test
        ]
        wf = mission_to_workflow(mission, tasks=tasks)
        assert len(wf.nodes) == len(types_to_test)


class TestFlowToWorkflow:
    def test_convert_flow_with_nodes_and_edges(self):
        flow = MagicMock()
        flow.id = "flow-1"
        flow.title = "My Flow"
        flow.description = "A flow"
        flow.user_id = 42
        flow.flow_definition = {
            "nodes": [
                {"id": "n1", "data": {"nodeType": "llm", "label": "Start"}},
                {"id": "n2", "data": {"nodeType": "tool", "label": "Do tool"}},
            ],
            "edges": [
                {
                    "source": "n1",
                    "target": "n2",
                    "data": {"condition": "ok", "label": "next"},
                },
            ],
        }

        wf = flow_to_workflow(flow)

        assert wf.type == WorkflowType.GRAPH
        assert wf.title == "My Flow"
        assert len(wf.nodes) == 2
        assert wf.nodes[0].type == NodeType.LLM_CALL
        assert wf.nodes[1].type == NodeType.TOOL_CALL
        assert len(wf.edges) == 1
        assert wf.edges[0].condition == "ok"
        assert wf.edges[0].label == "next"

    def test_flow_with_empty_definition(self):
        flow = MagicMock()
        flow.id = "flow-empty"
        flow.title = "Empty Flow"
        flow.description = None
        flow.user_id = 1
        flow.flow_definition = None

        wf = flow_to_workflow(flow)
        assert wf.nodes == []
        assert wf.edges == []


class TestGraphToWorkflow:
    def test_convert_graph_with_nodes_and_edges(self):
        graph = MagicMock()
        graph.id = "graph-1"
        graph.title = "My Graph"
        graph.user_id = 7
        graph.graph_definition = {
            "nodes": [
                {"id": "g1", "data": {"nodeType": "task", "label": "Node 1"}},
            ],
            "edges": [
                {"source": "g1", "target": "g2", "label": "link"},
            ],
        }

        wf = graph_to_workflow(graph)

        assert wf.type == WorkflowType.GRAPH
        assert len(wf.nodes) == 1
        assert len(wf.edges) == 1
        assert wf.edges[0].label == "link"

    def test_graph_with_none_definition(self):
        graph = MagicMock()
        graph.id = "graph-empty"
        graph.title = "Empty Graph"
        graph.user_id = 1
        graph.graph_definition = None

        wf = graph_to_workflow(graph)
        assert wf.nodes == []


class TestBlueprintToWorkflow:
    def test_convert_blueprint_snapshot(self):
        snapshot = {
            "blueprint_type": "solo",
            "title": "Blueprint Mission",
            "description": "From blueprint",
            "nodes": [
                {"id": "bp1", "type": "llm_call", "title": "BP Node"},
            ],
            "edges": [],
            "budget": {
                "max_cost_usd": "20.00",
                "max_wall_time_seconds": 600,
                "max_iterations": 50,
            },
            "config": {"key": "value"},
        }

        wf = blueprint_to_workflow(snapshot, blueprint_id="bp-id-1", user_id="user-5")

        assert wf.id == "bp-id-1"
        assert wf.type == WorkflowType.SOLO
        assert wf.title == "Blueprint Mission"
        assert wf.user_id == "user-5"
        assert len(wf.nodes) == 1
        assert float(wf.budget.max_cost_usd) == 20.0
        assert wf.metadata["key"] == "value"

    def test_blueprint_with_empty_snapshot(self):
        snapshot = {}
        wf = blueprint_to_workflow(snapshot, blueprint_id="empty")
        assert wf.id == "empty"
        assert wf.type == WorkflowType.SOLO
        assert wf.nodes == []


class TestResolveDeps:
    def test_no_deps_returns_empty(self):
        task = _make_task(dependencies=None)
        assert _resolve_deps(task, []) == []

    def test_list_of_uuids(self):
        task = _make_task(dependencies=["uuid-1", "uuid-2"])
        result = _resolve_deps(task, [])
        assert result == ["uuid-1", "uuid-2"]

    def test_dict_with_depends_on(self):
        task = _make_task(dependencies={"depends_on": ["uuid-a"]})
        result = _resolve_deps(task, [])
        assert result == ["uuid-a"]

    def test_index_based_deps_resolves_to_ids(self):
        t0 = _make_task(id="task-0")
        t1 = _make_task(id="task-1")
        t2 = _make_task(dependencies=[0, 1])

        result = _resolve_deps(t2, [t0, t1])
        assert result == ["task-0", "task-1"]

    def test_out_of_bounds_index_uses_raw_value(self):
        t2 = _make_task(dependencies=[99])
        result = _resolve_deps(t2, [])
        assert result == ["99"]

    def test_unknown_deps_type_returns_empty(self):
        task = MagicMock()
        task.dependencies = "invalid"
        assert _resolve_deps(task, []) == []
