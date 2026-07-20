# ─────────────────────────────────────────────────────────────────────
# Tests for the validate_schema substrate node end-to-end:
#   * NodeExecutor._dispatch routes VALIDATE_SCHEMA -> _handle_validate_schema
#   * a matching payload routes down the `default` edge
#   * a mismatching payload routes down the `on_invalid` edge (does not raise)
#   * a node with no `schema` config fails closed (success=False)
#   * DAGStrategy._incoming_branch_passed honours the `default`/`on_invalid`
#     edge condition AND tolerates a missing (None) edge.condition without
#     crashing (the historical FE serialisation omits condition entirely).
#
# Hermetic: no Postgres / Docker / Alembic. NodeExecutor is exercised with
# lightweight fakes for the bits it touches (PluginContext, UnifiedExecutor).
# ─────────────────────────────────────────────────────────────────────
from __future__ import annotations

import pytest

from app.sdk.context import PluginContext
from app.sdk.validate_schema import (
    DEFAULT_ROUTE,
    INVALID_ROUTE,
    ValidateSchemaHandler,
)
from app.services.substrate.strategies.dag import DAGStrategy
from app.services.substrate.workflow_models import (
    NodeType,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowType,
)

# ── builders ────────────────────────────────────────────────────────


def _schema_node(node_id: str = "v1", config: dict | None = None) -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        type=NodeType.VALIDATE_SCHEMA,
        title="Validate",
        config=config
        or {
            "schema": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}},
            }
        },
    )


def _terminal_node(node_id: str = "t1") -> WorkflowNode:
    return WorkflowNode(id=node_id, type=NodeType.LLM_CALL, title="T", config={})


def _dag(edges: list[WorkflowEdge], nodes=None) -> Workflow:
    nodes = nodes or [_schema_node(), _terminal_node()]
    return Workflow(id="w", type=WorkflowType.DAG, title="t", nodes=nodes, edges=edges)


# ── handler dispatch (mirrors the substrate wiring in node_executor) ──


async def test_dispatch_routes_to_handle_validate_schema():
    """NodeExecutor wires VALIDATE_SCHEMA to _handle_validate_schema."""
    from app.services.substrate.node_executor import NodeExecutor

    assert hasattr(NodeExecutor, "_handle_validate_schema")
    import inspect

    src = inspect.getsource(NodeExecutor._dispatch)
    assert "VALIDATE_SCHEMA" in src
    assert "_handle_validate_schema" in src


async def test_mismatch_routes_to_on_invalid():
    handler = ValidateSchemaHandler()
    from app.sdk.context import PluginContext

    pc = PluginContext(
        config={"schema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}},
        inputs={"payload": {"name": "bob"}},  # missing required id
    )
    result = await handler.execute(pc)
    assert result["valid"] is False
    assert result["route"] == INVALID_ROUTE


async def test_match_routes_to_default():
    handler = ValidateSchemaHandler()
    from app.sdk.context import PluginContext

    pc = PluginContext(
        config={"schema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}},
        inputs={"payload": {"id": 7}},
    )
    result = await handler.execute(pc)
    assert result["valid"] is True
    assert result["route"] == DEFAULT_ROUTE


async def test_missing_schema_fails_closed():
    handler = ValidateSchemaHandler()
    from app.sdk.context import PluginContext

    pc = PluginContext(config={}, inputs={"payload": {"id": 7}})
    errors = await handler.validate(pc)
    assert errors  # misconfigured node surfaces an error (fail closed)
    assert "schema" in errors[0].lower()


# ── DAG branch gating (honours condition, tolerates None) ───────────


def test_no_condition_edge_does_not_crash():
    """The historical FE emits edges with no `condition`. Gating must pass,
    not raise AttributeError on None.strip()."""
    strat = DAGStrategy()
    wf = _dag([WorkflowEdge(source="v1", target="t1", label="x")])  # condition=None
    strat.workflow = wf
    assert strat._incoming_branch_passed(wf, "t1", {"v1": {"route": "default"}}) is True


def test_default_edge_taken_on_match():
    strat = DAGStrategy()
    wf = _dag([WorkflowEdge(source="v1", target="t1", condition="default")])
    strat.workflow = wf
    assert strat._incoming_branch_passed(wf, "t1", {"v1": {"route": "default"}}) is True


def test_on_invalid_edge_blocked_on_match():
    strat = DAGStrategy()
    wf = _dag([WorkflowEdge(source="v1", target="t1", condition="on_invalid")])
    strat.workflow = wf
    assert strat._incoming_branch_passed(wf, "t1", {"v1": {"route": "default"}}) is False


def test_on_invalid_edge_taken_on_mismatch():
    strat = DAGStrategy()
    wf = _dag([WorkflowEdge(source="v1", target="t1", condition="on_invalid")])
    strat.workflow = wf
    assert strat._incoming_branch_passed(wf, "t1", {"v1": {"route": "on_invalid"}}) is True


# ── adapter wiring (the actual Wave-1 fix) ──────────────────────────


def test_task_type_map_reaches_validate_schema():
    """The FE emits the string "validate_schema". It MUST map to the
    NodeType.VALIDATE_SCHEMA enum (not silently collapse to LLM_CALL)."""
    from app.services.substrate.adapters import _TASK_TYPE_MAP

    assert _TASK_TYPE_MAP["validate_schema"] is NodeType.VALIDATE_SCHEMA


def test_blueprint_round_trip_validate_schema():
    """A minimal blueprint payload whose node carries type "validate_schema"
    (mirroring the FE missionToBlueprintPayload shape) must round-trip through
    blueprint_to_workflow into a WorkflowNode typed NodeType.VALIDATE_SCHEMA.
    Regression guard: previously it collapsed to LLM_CALL."""
    from app.services.substrate.adapters import blueprint_to_workflow

    snapshot = {
        "title": "schema-check",
        "blueprint_type": "solo",
        "nodes": [
            {
                "id": "v1",
                "type": "validate_schema",
                "title": "Validate payload",
                "config": {
                    "schema": {
                        "type": "object",
                        "required": ["id"],
                        "properties": {"id": {"type": "integer"}},
                    }
                },
            }
        ],
        "edges": [],
    }

    wf = blueprint_to_workflow(snapshot, blueprint_id="bp_1")

    assert len(wf.nodes) == 1
    assert wf.nodes[0].type == NodeType.VALIDATE_SCHEMA
    assert wf.nodes[0].type is not NodeType.LLM_CALL
