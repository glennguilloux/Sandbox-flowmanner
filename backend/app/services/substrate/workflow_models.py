"""Workflow models for the unified executor (H5.1).

Defines the canonical Workflow representation that all 7 strategies
consume.  Adapters (in substrate/adapters.py) convert from the existing
ORM models (Mission, Flow, GraphWorkflow, OrchestratorExecution, etc.)
into this unified format.

The Workflow model is the single data structure that flows through
UnifiedExecutor.execute().  Every old executor's task representation
maps to nodes and edges in a Workflow.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.capability_models import Budget

__all__ = [
    "EffectClass",
    "NodeType",
    "ReasoningProfile",
    "StrategyResult",
    "Workflow",
    "WorkflowEdge",
    "WorkflowNode",
    "WorkflowType",
]

# ── Node types (union of all old executor node types) ────────────────


class EffectClass(str, Enum):
    """Per-invocation classification of a node's external side effect.

    Declared on the WorkflowNode (by the planner/adapter that builds it) — NEVER
    inferred from the backend type. A POST can be reversible (idempotent upsert)
    or not (send email); a GET can be irreversible (debiting a quota). The class
    describes the *semantics* of this invocation's effect.

    Default is IRREVERSIBLE (fail-closed): an unannotated node is treated as a
    point-of-no-return effect, so the two-phase STAGE→CONFIRM dispatch gates it.
    Read-only nodes (LLM_CALL, CODE_EXECUTION, RAG_QUERY, WEB_SEARCH, read-only
    FILE_OPERATION, HUMAN_REVIEW/APPROVAL, the PHASE_GATE/FAN_OUT/FAN_IN passthrough)
    MUST be explicitly annotated REVERSIBLE — see node_executor / side-effect-safety
    skill.
    """

    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


class NodeType(str, Enum):
    """Every node type supported by the unified executor.

    Each old executor contributes its node types here.  The shared
    execute_node() dispatches on node.type.
    """

    # From mission_executor
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    CODE_EXECUTION = "code_execution"
    RAG_QUERY = "rag_query"
    WEB_SEARCH = "web_search"
    FILE_OPERATION = "file_operation"
    HUMAN_REVIEW = "human_review"

    # Browser-specific (from mission_executor BROWSER_TASK_TYPES)
    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_SNAPSHOT = "browser_snapshot"
    BROWSER_CLICK = "browser_click"
    BROWSER_TYPE = "browser_type"
    BROWSER_SCROLL = "browser_scroll"
    BROWSER_SCREENSHOT = "browser_screenshot"
    BROWSER_CLOSE = "browser_close"

    # Strategy-specific
    APPROVAL = "approval"  # Human-in-the-loop pause
    SUB_WORKFLOW = "sub_workflow"  # Recursive execution
    PHASE_GATE = "phase_gate"  # Pipeline phase boundary
    FAN_OUT = "fan_out"  # Swarm decomposition
    FAN_IN = "fan_in"  # Swarm synthesis
    SANDBOX = "sandbox"  # sandboxd Docker container execution

    # Template node types (Scope B — real handlers in node_executor)
    # Previously these collapsed to LLM_CALL through the task-type map default.
    TRANSFORM = "transform"  # pure data transform (no LLM/tool)
    FILTER = "filter"  # pure data-control transform: keep collection items matching a predicate
    CONDITION = "condition"  # evaluate a boolean expression, drive branching
    LOG = "log"  # append a substrate log event (read-only)
    LOOP = "loop"  # strategy-level bounded iteration marker
    WEBHOOK = "webhook"  # outbound HTTP POST (irreversible side effect)

    # Convention: read-only / internal-passthrough node types are annotated
    # REVERSIBLE by the planner/adapter (see EffectClass + side-effect-safety
    # skill). The IRREVERSIBLE default otherwise applies to TOOL_CALL,
    # BROWSER_*, SUB_WORKFLOW, SANDBOX.


# ── Workflow types (maps 1:1 to old executors) ──────────────────────


class WorkflowType(str, Enum):
    """Each old executor maps to one WorkflowType.

    New workflow types can be added without writing new executors.
    """

    SOLO = "solo"  # mission_executor.py
    DAG = "dag"  # dag_executor.py
    SWARM = "swarm"  # swarm/orchestrator.py
    PIPELINE = "pipeline"  # swarm_pipeline/orchestrator.py
    GRAPH = "graph"  # graph_executor.py
    META = "meta"  # nexus/meta_loop_orchestrator.py
    LANGGRAPH = "langgraph"  # langgraph/agent.py


# ── Workflow components ──────────────────────────────────────────────


class ReasoningProfile(str, Enum):
    """Reasoning depth profile carried on a node/execution context (Comment 7).

    Mirrors DepthPolicy depth levels. ``shallow`` -> local/cheap, no reasoning;
    ``normal`` -> default cloud path; ``deep`` -> premium-reasoning tier when
    budget + catalog policy allow (e.g. Opus). The profile drives model and
    reasoning-option selection in ``NodeExecutor._handle_llm``.
    """

    SHALLOW = "shallow"
    NORMAL = "normal"
    DEEP = "deep"


class WorkflowNode(BaseModel):
    """A single node in a workflow.

    Replaces MissionTask, OrchestratorTask, GraphNode, and others.
    """

    id: str
    type: NodeType
    title: str = ""
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    assigned_model: str | None = None
    assigned_agent_id: str | None = None
    # Comment 7: reasoning depth profile for this node. Consumed by
    # NodeExecutor._handle_llm to select the model + ReasoningOptions. Defaults
    # to NORMAL when the planner/adapter does not set it.
    reasoning_profile: ReasoningProfile = ReasoningProfile.NORMAL
    max_retries: int = 3
    fallback_strategy: str = "human_escalate"
    # Side-effect classification (per-invocation, fail-closed default).
    # IRREVERSIBLE nodes are gated by the two-phase STAGE→CONFIRM dispatch in
    # NodeExecutor.execute(): the effect intent is committed before any
    # external call, and the effect is only FIRED after the orchestrator's
    # fallback/skip/escalate decision. Read-only nodes MUST set REVERSIBLE.
    effect_class: EffectClass = EffectClass.IRREVERSIBLE
    # Runtime fields (populated during execution)
    status: str = "pending"
    output_data: dict[str, Any] | None = None
    error_message: str | None = None
    retry_count: int = 0
    tokens_used: int = 0
    cost: float = 0.0


class WorkflowEdge(BaseModel):
    """A directed edge between two workflow nodes."""

    source: str
    target: str
    condition: str | None = None  # e.g., "{{node_id.output.status}} == 'success'"
    label: str | None = None


class Workflow(BaseModel):
    """The single canonical workflow representation.

    All 7 old executors' data models are adapted into this format
    before execution.  The UnifiedExecutor operates exclusively on
    Workflow instances.
    """

    id: str
    type: WorkflowType
    title: str
    description: str | None = None
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    budget: Budget = Field(
        default_factory=lambda: Budget(
            max_cost_usd=Decimal("10.00"),
            max_wall_time_seconds=300,
            max_iterations=100,
            max_depth=5,
        )
    )
    user_id: str | None = None
    # Workspace the run belongs to. Required for workspace-scoped features
    # (Epic 4.1b standing constraints, circuit breaker, HITL inbox). Adapters
    # MUST propagate it from the source ORM (Mission.workspace_id, etc.) — if
    # it is None the substrate executor treats the run as unscoped and the
    # constraint gate is skipped (fail-open), which silently disables
    # enforcement for that run.
    workspace_id: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def node_map(self) -> dict[str, WorkflowNode]:
        """Index nodes by ID for O(1) lookup."""
        return {n.id: n for n in self.nodes}

    @property
    def dependency_map(self) -> dict[str, list[WorkflowEdge]]:
        """Build adjacency: source → list of outgoing edges."""
        adj: dict[str, list[WorkflowEdge]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            if e.source in adj:
                adj[e.source].append(e)
        return adj

    def get_in_degree(self) -> dict[str, int]:
        """Compute in-degree for each node."""
        deg: dict[str, int] = {n.id: 0 for n in self.nodes}
        for e in self.edges:
            if e.target in deg:
                deg[e.target] += 1
        return deg


# ── Strategy result (returned by all strategies) ────────────────────


class StrategyResult(BaseModel):
    """Result from any strategy execution.

    All 7 strategies return this type.  Consumers only need to check
    success and status; details are in the fields below.
    """

    success: bool
    status: str  # "completed", "failed", "aborted", "paused"
    # The substrate run id this result belongs to.  Optional / nullable because
    # some call sites construct a StrategyResult without a run context (e.g.
    # lease-already-running early returns); the executor's post-execution hooks
    # read ``result.run_id or workflow.id`` so a missing value degrades safely.
    run_id: str | None = None
    data: Any = None
    error: str | None = None
    completed_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    execution_time_ms: float = 0.0
    event_count: int = 0
