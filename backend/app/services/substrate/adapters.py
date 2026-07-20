"""ORM → Workflow adapters (H5.1).

Converts existing ORM models (Mission, Flow, GraphWorkflow, etc.)
into the unified Workflow format consumed by UnifiedExecutor.

Each adapter is a pure function: ORM object → Workflow.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.models.capability_models import Budget
from app.services.substrate.workflow_models import (
    EffectClass,
    NodeType,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowType,
)


class InvalidBlueprintGraphError(Exception):
    """Raised when a Blueprint snapshot's graph is internally inconsistent.

    Covers cases the trivial adapter used to SILENTLY drop (data loss):
    an edge endpoint that names a node id absent from the surviving real-node
    set (orphan/dangling edge), or a self-loop (source == target). Both are
    model errors in the DAG substrate that must FAIL LOUD — the adapter
    raises this instead of discarding the edge, so the caller (RunService)
    can surface a clear validation error rather than running a silently
    truncated graph.
    """

    pass


# Per-NodeType default side-effect classification (side-effect-safety skill).
# Read-only / internal-passthrough node types are REVERSIBLE so they keep normal
# retry semantics. TOOL_CALL, BROWSER_*, SUB_WORKFLOW, SANDBOX default to
# IRREVERSIBLE (WorkflowNode.effect_class default) — see the skill's self-critique
# table. NOTE: classification is per-invocation semantics, not backend type; a
# caller may still override effect_class on the WorkflowNode for a specific tool
# that happens to be a pure read (e.g. web_search/rag_search/code_executor).
_REVERSIBLE_NODE_TYPES: frozenset[NodeType] = frozenset(
    {
        NodeType.LLM_CALL,
        NodeType.CODE_EXECUTION,
        NodeType.RAG_QUERY,
        NodeType.WEB_SEARCH,
        NodeType.FILE_OPERATION,  # current handlers implement read/list only
        NodeType.HUMAN_REVIEW,
        NodeType.APPROVAL,
        NodeType.PHASE_GATE,
        NodeType.FAN_OUT,
        NodeType.FAN_IN,
        NodeType.LOG,  # read-only substrate event append
        NodeType.CONDITION,  # handler only evaluates + reports branch
        NodeType.TRANSFORM,  # pure data transform, no LLM/tool
        NodeType.CACHE_GET,  # read-through Redis cache lookup (reversible)
        NodeType.MEMORY_READ,  # read-only semantic memory read from Qdrant
    }
)


def _effect_class_for(node_type: NodeType) -> EffectClass:
    """Resolve the default EffectClass for a node type in an adapter."""
    return EffectClass.REVERSIBLE if node_type in _REVERSIBLE_NODE_TYPES else EffectClass.IRREVERSIBLE


logger = logging.getLogger(__name__)


# ── Task type mapping (MissionTask.task_type → NodeType) ────────────

_TASK_TYPE_MAP: dict[str, NodeType] = {
    "llm": NodeType.LLM_CALL,
    "llm_call": NodeType.LLM_CALL,
    "tool": NodeType.TOOL_CALL,
    "tool_execution": NodeType.TOOL_CALL,
    "rag": NodeType.RAG_QUERY,
    "rag_query": NodeType.RAG_QUERY,
    "web_search": NodeType.WEB_SEARCH,
    "code": NodeType.CODE_EXECUTION,
    "code_execution": NodeType.CODE_EXECUTION,
    "sandbox": NodeType.SANDBOX,
    "file_operation": NodeType.FILE_OPERATION,
    "review": NodeType.HUMAN_REVIEW,
    "human_review": NodeType.HUMAN_REVIEW,
    "browser_navigate": NodeType.BROWSER_NAVIGATE,
    "browser_snapshot": NodeType.BROWSER_SNAPSHOT,
    "browser_click": NodeType.BROWSER_CLICK,
    "browser_type": NodeType.BROWSER_TYPE,
    "browser_scroll": NodeType.BROWSER_SCROLL,
    "browser_screenshot": NodeType.BROWSER_SCREENSHOT,
    "browser_close": NodeType.BROWSER_CLOSE,
    "approval": NodeType.APPROVAL,
    "parallel": NodeType.FAN_OUT,
    # Scope B template node types — previously unmapped, defaulted to
    # LLM_CALL (silently collapsing to an LLM call with no config).
    "transform": NodeType.TRANSFORM,
    "condition": NodeType.CONDITION,
    "log": NodeType.LOG,
    "loop": NodeType.LOOP,
    "webhook": NodeType.WEBHOOK,
    "memory_read": NodeType.MEMORY_READ,
}


# ── Mission workflow type mapping ───────────────────────────────────

_MISSION_TYPE_MAP: dict[str, WorkflowType] = {
    "solo": WorkflowType.SOLO,
    "single": WorkflowType.SOLO,
    "dag": WorkflowType.DAG,
    "swarm": WorkflowType.SWARM,
    "pipeline": WorkflowType.PIPELINE,
    "graph": WorkflowType.GRAPH,
    "meta": WorkflowType.META,
    "langgraph": WorkflowType.LANGGRAPH,
}


def _build_mission_metadata(mission: Any) -> dict[str, Any]:
    """Build workflow metadata, omitting substrate_run_id unless a real ID exists.

    Comment 1: the executor is the sole source of the run ID. The adapter must
    never inject a ``None`` ``substrate_run_id`` (which previously caused
    strategies to fall back to a freshly generated UUID, splitting event
    correlation). Only forward a real ID when the mission plan carries one.
    """
    metadata: dict[str, Any] = {
        "fallback_strategy": getattr(mission, "fallback_strategy", "human_escalate"),
    }
    if getattr(mission, "plan", None):
        _rid = mission.plan.get("substrate_run_id")
        if _rid:
            metadata["substrate_run_id"] = _rid
    return metadata


def mission_to_workflow(
    mission: Any,  # app.models.mission_models.Mission
    tasks: list[Any] | None = None,  # list of MissionTask
    input_data: dict | None = None,  # per-run overrides surfaced as {{ inputs.<key> }}
) -> Workflow:
    """Convert a Mission + its tasks into a unified Workflow.

    Args:
        mission: ORM Mission object.
        tasks: Optional pre-fetched tasks (avoids extra query).
        input_data: Optional per-run input values (e.g. {"model": "<slug>"})
            that sandbox nodes can reference via ``{{ inputs.model }}``. When
            present, sandbox-type nodes get ``config["model"]`` set so the
            substrate renders it at node_executor.py:2152.

    Returns:
        Workflow ready for UnifiedExecutor.execute().
    """
    # Determine workflow type
    wf_type = _MISSION_TYPE_MAP.get(
        getattr(mission, "mission_type", "solo") or "solo",
        WorkflowType.SOLO,
    )

    # Convert tasks to nodes
    nodes: list[WorkflowNode] = []
    if tasks:
        for task in tasks:
            node_type = _TASK_TYPE_MAP.get(
                getattr(task, "task_type", "llm") or "llm",
                NodeType.LLM_CALL,
            )
            config = {
                "prompt": getattr(task, "description", "") or getattr(task, "title", ""),
                "tool_name": getattr(task, "tool_id", None),
            }
            # Surface per-run model selection to sandbox nodes so the opencode
            # agent uses the chosen model (node_executor.py:2152 renders
            # {{ inputs.model }} -> submit_task(model=...)). Mirrors the
            # blueprint path, which already threads input_data.model through.
            if input_data and input_data.get("model") is not None and node_type == NodeType.SANDBOX:
                config["model"] = "{{ inputs.model }}"

            nodes.append(
                WorkflowNode(
                    id=str(task.id) if hasattr(task, "id") else f"task_{len(nodes)}",
                    type=node_type,
                    title=getattr(task, "title", ""),
                    description=getattr(task, "description", ""),
                    config=config,
                    dependencies=_resolve_deps(task, tasks or []),
                    assigned_model=getattr(task, "assigned_model", None),
                    assigned_agent_id=getattr(task, "assigned_agent_id", None),
                    max_retries=getattr(task, "max_retries", 3),
                    status=getattr(task, "status", "pending"),
                    output_data=getattr(task, "output_data", None),
                    error_message=getattr(task, "error_message", None),
                    retry_count=getattr(task, "retry_count", 0),
                    tokens_used=getattr(task, "tokens_used", 0),
                    cost=getattr(task, "cost", 0.0),
                    effect_class=_effect_class_for(node_type),
                )
            )

    # Build edges from dependencies (for DAG and others)
    edges: list[WorkflowEdge] = []
    if wf_type == WorkflowType.DAG:
        # Flatten (node, dep) pairs into edges.
        edges = [WorkflowEdge(source=dep_id, target=node.id) for node in nodes for dep_id in node.dependencies]

    # Build budget
    budget = Budget(
        max_cost_usd=Decimal(str(getattr(mission, "budget_usd", 10.0) or 10.0)),
        max_wall_time_seconds=getattr(mission, "budget_seconds", 300) or 300,
        max_iterations=(len(nodes) * 3) if nodes else 100,
        max_depth=5,
    )

    # Add existing spend
    budget.spent_usd = Decimal(str(getattr(mission, "actual_cost", 0.0) or 0.0))
    budget.iterations_used = getattr(mission, "tokens_used", 0) or 0

    return Workflow(
        id=str(mission.id) if hasattr(mission, "id") else "",
        type=wf_type,
        title=getattr(mission, "title", "Untitled"),
        description=getattr(mission, "description", None),
        nodes=nodes,
        edges=edges,
        budget=budget,
        user_id=str(mission.user_id) if hasattr(mission, "user_id") else None,
        workspace_id=(str(mission.workspace_id) if hasattr(mission, "workspace_id") and mission.workspace_id else None),
        metadata=_build_mission_metadata(mission),
    )


def flow_to_workflow(flow: Any) -> Workflow:
    """Convert a Flow into a unified Workflow.

    Args:
        flow: ORM Flow object with flow_definition dict.

    Returns:
        Workflow ready for UnifiedExecutor.execute().
    """
    flow_def = getattr(flow, "flow_definition", {}) or {}

    nodes: list[WorkflowNode] = [
        WorkflowNode(
            id=node_data.get("id", ""),
            type=_TASK_TYPE_MAP.get(
                node_data.get("data", {}).get("nodeType", "llm"),
                NodeType.LLM_CALL,
            ),
            title=node_data.get("data", {}).get("label", ""),
            config=node_data.get("data", {}),
            effect_class=_effect_class_for(
                _TASK_TYPE_MAP.get(
                    node_data.get("data", {}).get("nodeType", "llm"),
                    NodeType.LLM_CALL,
                )
            ),
        )
        for node_data in flow_def.get("nodes", [])
    ]

    edges: list[WorkflowEdge] = [
        WorkflowEdge(
            source=edge_data.get("source", ""),
            target=edge_data.get("target", ""),
            condition=edge_data.get("data", {}).get("condition"),
            label=edge_data.get("data", {}).get("label"),
        )
        for edge_data in flow_def.get("edges", [])
    ]

    return Workflow(
        id=str(flow.id) if hasattr(flow, "id") else "",
        type=WorkflowType.GRAPH,
        title=getattr(flow, "title", "Untitled Flow"),
        description=getattr(flow, "description", None),
        nodes=nodes,
        edges=edges,
        user_id=str(flow.user_id) if hasattr(flow, "user_id") else None,
        workspace_id=(str(flow.workspace_id) if hasattr(flow, "workspace_id") and flow.workspace_id else None),
    )


def graph_to_workflow(graph: Any) -> Workflow:
    """Convert a GraphWorkflow into a unified Workflow.

    Args:
        graph: ORM GraphWorkflow object with graph_definition dict.
    """
    graph_def = getattr(graph, "graph_definition", {}) or {}

    nodes: list[WorkflowNode] = []
    for node_data in graph_def.get("nodes", []):
        node_type = _TASK_TYPE_MAP.get(
            node_data.get("data", {}).get("nodeType", "task"),
            NodeType.LLM_CALL,
        )
        nodes.append(
            WorkflowNode(
                id=node_data.get("id", ""),
                type=node_type,
                title=node_data.get("data", {}).get("label", ""),
                config=node_data.get("data", {}),
            )
        )

    edges: list[WorkflowEdge] = [
        WorkflowEdge(
            source=edge_data.get("source", ""),
            target=edge_data.get("target", ""),
            label=edge_data.get("label"),
        )
        for edge_data in graph_def.get("edges", [])
    ]

    return Workflow(
        id=str(graph.id) if hasattr(graph, "id") else "",
        type=WorkflowType.GRAPH,
        title=getattr(graph, "title", "Untitled Graph"),
        nodes=nodes,
        edges=edges,
        user_id=str(graph.user_id) if hasattr(graph, "user_id") else None,
        workspace_id=(str(graph.workspace_id) if hasattr(graph, "workspace_id") and graph.workspace_id else None),
    )


def blueprint_to_workflow(
    snapshot: dict,
    blueprint_id: str,
    user_id: str | None = None,
) -> Workflow:
    """Convert a Run's snapshot dict into a Workflow for UnifiedExecutor.

    This is the trivial adapter — the snapshot IS the Workflow shape.
    The old adapters (mission_to_workflow, flow_to_workflow, graph_to_workflow)
    remain for backward compatibility during the dual-write transition.
    """
    from decimal import Decimal

    from app.models.capability_models import Budget

    budget_data = snapshot.get("budget", {})
    budget = Budget(
        max_cost_usd=Decimal(str(budget_data.get("max_cost_usd", "10.00"))),
        max_wall_time_seconds=budget_data.get("max_wall_time_seconds", 300),
        max_iterations=budget_data.get("max_iterations", 100),
        max_depth=budget_data.get("max_depth", 5),
    )

    # The frontend mission builder emits `start`/`end` sentinel nodes
    # (nodeType "start"/"end") that are bookkeeping, not executable steps.
    # The canonical WorkflowNode.NodeType enum has no such member, so passing
    # them verbatim raises `ValidationError: 1 validation error for
    # WorkflowNode / type / Input should be 'llm_call', ...`. The old mission
    # builder already tolerates these sentinels (templates use them), so the
    # adapter must too: skip pure `start`/`end` sentinels and map any other
    # unknown nodeType through the existing task-type map (defaulting to
    # LLM_CALL) instead of crashing the whole blueprint load.
    #
    # Additionally, the frontend frequently labels multi-node mission graphs as
    # `blueprint_type: "solo"` even though they contain several real task nodes
    # and edges (start -> task -> ... -> end). SoloStrategy enforces a strict
    # "exactly 1 node, no edges" contract, so such a graph would fail validation
    # ("Solo workflow must have exactly 1 node"). Rather than silently dropping
    # the user's work, derive the real WorkflowType from the *topology*: a
    # "solo" blueprint that actually has >1 real node or any real edge is a DAG.
    _SENTINEL_NODE_TYPES = frozenset({"start", "end"})

    workflow_nodes: list[WorkflowNode] = []
    sentinel_ids: set[str] = set()
    for n in snapshot.get("nodes", []):
        raw_type = n.get("type") or (n.get("data", {}) or {}).get("nodeType") or "task"
        if raw_type in _SENTINEL_NODE_TYPES:
            sentinel_ids.add(n.get("id"))
            continue
        mapped = _TASK_TYPE_MAP.get(raw_type, NodeType.LLM_CALL)
        n = {**n, "type": mapped.value}
        workflow_nodes.append(WorkflowNode(**n))

    # Drop edges that reference skipped sentinel nodes (e.g. start->task,
    # task->end) so the surviving graph only connects real nodes.
    #
    # A single malformed edge (missing `source`/`target`, or otherwise not
    # constructible as a WorkflowEdge) must NOT abort the entire blueprint
    # conversion. Drop the offending edge and log a warning instead of letting
    # the pydantic ValidationError propagate.
    #
    # Edge normalization policy (Finding 4) — applied AFATER sentinel/malformed
    # dropping so downstream strategies receive a clean graph:
    #   1. Orphan edge (source or target NOT in the surviving real-node set,
    #      i.e. excluding the already-dropped start/end sentinels) and
    #      NEITHER endpoint is a sentinel: RAISE InvalidBlueprintGraphError.
    #      A dangling edge is silent data loss — the named node id is simply
    #      absent, so the run would be truncated with no signal. Fail loud
    #      instead, naming the offending edge + the missing node id.
    #   2. Self-loop (source == target) and NEITHER endpoint is a sentinel:
    #      RAISE InvalidBlueprintGraphError. A self-loop is a modeling
    #      error in this DAG substrate; revisit if a real use case appears.
    #   3. Duplicate edge (same (source, target) appearing >1 time): KEEP the
    #      first occurrence, DROP later duplicates with logger.info (default =
    #      dedupe; if a strategy ever needs parallel duplicate edges, document
    #      WHY and skip this dedup).
    real_node_ids: set[str] = {n.id for n in workflow_nodes}
    workflow_edges: list[WorkflowEdge] = []
    _seen_edge_pairs: set[tuple[str, str]] = set()
    for e in snapshot.get("edges", []):
        # Keep the existing sentinel-drop filter.
        if e.get("source") in sentinel_ids or e.get("target") in sentinel_ids:
            continue
        # Skip edges that lack both `source` and `target` outright.
        if e.get("source") is None and e.get("target") is None:
            logger.warning(
                "blueprint_to_workflow(%s): dropping edge missing both source and target: %r",
                blueprint_id,
                e,
            )
            continue
        # Drop any other non-constructible edge (FIX 1: e.g. missing source OR
        # target) rather than crashing the whole conversion.
        try:
            edge = WorkflowEdge(**e)
        except (ValidationError, TypeError) as exc:
            logger.warning(
                "blueprint_to_workflow(%s): dropping malformed edge %r: %s",
                blueprint_id,
                e,
                exc,
            )
            continue
        # 1. Orphan edge: an endpoint is not in the surviving real-node set
        #    AND neither endpoint is a sentinel (sentinels were already
        #    dropped above). This is silent data loss — a node id the
        #    edge refers to simply does not exist. Fail loud instead of
        #    truncating the graph.
        if edge.source not in real_node_ids or edge.target not in real_node_ids:
            missing = edge.source if edge.source not in real_node_ids else edge.target
            raise InvalidBlueprintGraphError(
                f"Invalid blueprint {blueprint_id}: edge "
                f"'{edge.source}'->'{edge.target}' references missing "
                f"node '{missing}' (not in nodes)"
            )
        # 2. Self-loop: source == target is a modeling error in this
        #    DAG substrate. Neither endpoint is a sentinel (sentinels
        #    already dropped). Fail loud.
        if edge.source == edge.target:
            raise InvalidBlueprintGraphError(
                f"Invalid blueprint {blueprint_id}: self-loop edge '{edge.source}'->'{edge.target}' is not allowed"
            )
        # 3. Duplicate edge: keep the first, drop later duplicates.
        _pair = (edge.source, edge.target)
        if _pair in _seen_edge_pairs:
            logger.info(
                "blueprint_to_workflow(%s): dropping duplicate edge %r",
                blueprint_id,
                e,
            )
            continue
        _seen_edge_pairs.add(_pair)
        workflow_edges.append(edge)

    # Derive the effective workflow type from topology (see note above).
    # Only apply the solo->dag flip when there are real nodes: an empty
    # ({}) snapshot declared "solo" stays SOLO (restores the empty-snapshot
    # contract), while a "solo" blueprint with >1 real node or any real edge
    # is treated as a DAG.
    declared_type = snapshot.get("blueprint_type", "solo")
    effective_type = declared_type
    if declared_type == WorkflowType.SOLO.value and workflow_nodes and (len(workflow_nodes) != 1 or workflow_edges):
        effective_type = WorkflowType.DAG.value

    return Workflow(
        id=blueprint_id,
        type=WorkflowType(effective_type),
        title=snapshot.get("title", ""),
        description=snapshot.get("description"),
        nodes=workflow_nodes,
        edges=workflow_edges,
        budget=budget,
        user_id=user_id,
        workspace_id=snapshot.get("workspace_id"),
        metadata=snapshot.get("config", {}),
    )


def validate_blueprint_definition(snapshot: dict, blueprint_id: str = "") -> list[str]:
    """Validate that every edge in a blueprint definition connects real nodes.

    Returns a list of human-readable error strings. An empty list means the
    graph is structurally sound. This function does NOT raise — callers turn
    the returned errors into an appropriate 4xx response.

    Sentinels: the frontend mission builder emits ``start``/``end`` sentinel
    nodes (nodeType ``start``/``end``) that are bookkeeping, not executable
    steps (see ``blueprint_to_workflow``). Edges that touch those sentinels are
    ignored, exactly like the adapter does, so they never produce a false error.

    Pure / read-only: no DB, no LLM.
    """
    errors: list[str] = []

    # Skip start/end sentinels (bookkeeping, not executable nodes).
    _SENTINEL = frozenset({"start", "end"})

    real_ids = {
        n.get("id")
        for n in (snapshot.get("nodes", []) or [])
        if (n.get("type") or (n.get("data", {}) or {}).get("nodeType")) not in _SENTINEL
    }

    for e in snapshot.get("edges", []) or []:
        src, tgt = e.get("source"), e.get("target")
        # Ignore edges that only touch sentinel nodes.
        if src in _SENTINEL or tgt in _SENTINEL:
            continue
        if src is None or tgt is None:
            errors.append(f"Edge missing source/target in blueprint {blueprint_id}")
            continue
        if src not in real_ids:
            errors.append(f"Edge source '{src}' not found in nodes (blueprint {blueprint_id})")
        if tgt not in real_ids:
            errors.append(f"Edge target '{tgt}' not found in nodes (blueprint {blueprint_id})")

    return errors


def _resolve_deps(task: Any, all_tasks: list[Any]) -> list[str]:
    """Resolve task dependencies to node IDs.

    Handles both index-based (dependencies is list of ints) and
    UUID-based (dependencies is dict with "depends_on" list) formats.
    """
    deps = getattr(task, "dependencies", None)
    if deps is None:
        return []

    if isinstance(deps, dict):
        dep_ids = deps.get("depends_on", [])
    elif isinstance(deps, list):
        dep_ids = deps
    else:
        return []

    # If deps are indices, resolve to task IDs
    resolved = []
    for dep in dep_ids:
        if isinstance(dep, int):
            if 0 <= dep < len(all_tasks):
                resolved.append(str(all_tasks[dep].id))
            else:
                logger.warning(
                    "Dependency index %d out of bounds (task count: %d), using raw value",
                    dep,
                    len(all_tasks),
                )
                resolved.append(str(dep))
        else:
            resolved.append(str(dep))
    return resolved
