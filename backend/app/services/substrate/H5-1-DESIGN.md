# H5.1 — Unified Executor Design Spec

> **Status:** Design (pre-implementation)
> **Date:** 2026-06-01
> **Horizon:** H5 — Collapse the Executors
> **Effort:** ~8–12 weeks (one engineer), or ~2–3 weeks for the core strategy layer

---

## 0. Executive Summary

Today Flowmanner has **7 separate executor implementations** totalling ~4,500 lines of code. They overlap heavily (4 of 7 route to the same LLM call loop) but each has its own task loop, retry logic, abort handling, and observability integration. Bugs fixed in one executor don't propagate to the others.

H5.1 replaces all 7 with a **single unified executor** (`substrate/executor.py`, ~600–800 new lines of strategy code) that:

1. **Accepts a single `Workflow` definition** (nodes + edges + type)
2. **Dispatches to a typed `ExecutionStrategy`** based on the workflow type
3. **Records every state transition** through the substrate event log
4. **Enforces budget, capability, and depth invariants** at execution time
5. **Deletes ~4,500 lines of old executor code** — the deletion is the value

The 7 old models become **strategies** on the unified executor:

| Old Executor | LOC | Strategy | What Changes |
|---|---|---|---|
| `mission_executor.py` | 1,387 | `SoloStrategy` | Task loop + LLM/tool execution moves to base; only solo-specific stays |
| `dag_executor.py` | 179 | `DAGStrategy` | Topological sort utilities already pure functions; strategy wraps them |
| `swarm/orchestrator.py` | 331 | `SwarmStrategy` | Decompose/dispatch/synthesize becomes a strategy on fan-out nodes |
| `swarm_pipeline/orchestrator.py` | ~1,700 | `PipelineStrategy` | 7-phase pipeline becomes a strategy with phase gates |
| `graph_executor.py` | 293 | `GraphStrategy` | Node interpolation + handler dispatch becomes a strategy |
| `langgraph/agent.py` | ~900 | `LangGraphStrategy` | Native LangGraph checkpointed subgraph support |
| `nexus/meta_loop_orchestrator.py` | 225 | `MetaStrategy` | Recursive plan-execute-observe in the strategy layer |

**Total saved:** ~2,865 lines of orchestrator code deleted, ~1,800 lines of strategy + adapter code added. Net: ~1,000 lines removed.

**Preserved (not deleted):**
- `swarm_pipeline/phases/*.py` (~1,500 lines) — phase handlers are strategy helpers
- `langgraph/` module except agent.py (~650 lines) — tool handlers, approval, persistence
- `dag_executor.py` topo-sort utilities — moved into `UnifiedExecutor` as pure functions
- `nexus/failure_analyzer.py`, `nexus/capability_lattice.py` — already shared

---

## 1. Design Principles

### 1.1 Every execution is a Workflow

The H4 consolidation (Flow + Graph → Workflow) is a prerequisite for H5.1. If H4 is not fully complete, H5.1 defines its own internal `Workflow` model and provides **adapters** from the existing ORM models. The adapters are in `substrate/adapters.py` and handle:

- `Mission` + `MissionTask` → `Workflow` (extracts tasks, dependencies, budget)
- `Flow` / `GraphWorkflow` → `Workflow` (maps graph definitions to nodes/edges)
- `OrchestratorExecution` + `OrchestratorTask` → `Workflow` (swarm decomposition)
- `NexusPipeline` + `SwarmAgent` → `Workflow` (pipeline phases)

```python
class NodeType(str, Enum):
    """All node types supported by the unified executor."""
    # From mission_executor
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    CODE_EXECUTION = "code_execution"
    RAG_QUERY = "rag_query"
    WEB_SEARCH = "web_search"
    FILE_OPERATION = "file_operation"
    HUMAN_REVIEW = "human_review"
    # Browser-specific (from BROWSER_TASK_TYPES)
    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_SNAPSHOT = "browser_snapshot"
    BROWSER_CLICK = "browser_click"
    BROWSER_TYPE = "browser_type"
    BROWSER_SCROLL = "browser_scroll"
    BROWSER_SCREENSHOT = "browser_screenshot"
    BROWSER_CLOSE = "browser_close"
    # Strategy-specific
    APPROVAL = "approval"           # Human-in-the-loop pause
    SUB_WORKFLOW = "sub_workflow"   # Recursive execution
    PHASE_GATE = "phase_gate"       # Pipeline phase boundary
    FAN_OUT = "fan_out"             # Swarm decomposition
    FAN_IN = "fan_in"               # Swarm synthesis

class WorkflowNode(BaseModel):
    id: str
    type: NodeType
    config: dict[str, Any]  # Node-type-specific configuration
    dependencies: list[str] = []  # Node IDs that must complete first
    assigned_model: str | None = None
    assigned_agent_id: str | None = None
    max_retries: int = 3
    fallback_strategy: str = "human_escalate"  # human_escalate, abort, skip, retry

class WorkflowEdge(BaseModel):
    source: str
    target: str
    condition: str | None = None  # Python expression for conditional edges
    label: str | None = None

class WorkflowType(str, Enum):
    SOLO = "solo"
    DAG = "dag"
    SWARM = "swarm"
    PIPELINE = "pipeline"
    GRAPH = "graph"
    META = "meta"
    LANGGRAPH = "langgraph"

class Workflow(BaseModel):
    id: str
    type: WorkflowType
    title: str
    description: str | None = None
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    budget: Budget
    user_id: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # For substrate_run_id, etc.
```

### 1.2 Strategy Pattern

Every workflow type maps to a strategy class implementing `ExecutionStrategy`:

```python
class StrategyResult(BaseModel):
    """Result from any strategy execution."""
    success: bool
    status: str  # "completed", "failed", "aborted", "paused"
    data: Any = None
    error: str | None = None
    completed_nodes: list[str] = []
    failed_nodes: list[str] = []
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    execution_time_ms: float = 0.0
    event_count: int = 0

class ExecutionStrategy(ABC):
    """Interface for all workflow execution strategies."""

    @abstractmethod
    async def validate(self, workflow: Workflow) -> list[str]:
        """Pre-flight validation. Returns list of errors (empty = valid).

        Each strategy enforces its own structural rules:
        - SoloStrategy: exactly 1 node, no edges
        - DAGStrategy: no cycles, all dep references valid
        - SwarmStrategy: at least 1 FAN_OUT and 1 FAN_IN node
        - PipelineStrategy: all nodes are PHASE_GATE, ordered by edges
        - GraphStrategy: nodes have handlers in NodeHandlerRegistry
        - MetaStrategy: contains at least 1 SUB_WORKFLOW node, depth ≤ max
        - LangGraphStrategy: nodes reference valid LangGraph graphs
        """
        ...

    @abstractmethod
    async def execute(
        self,
        workflow: Workflow,
        context: ExecutionContext,
        executor: "UnifiedExecutor",
    ) -> StrategyResult:
        """Execute the strategy against a workflow."""
        ...

    @abstractmethod
    def can_handle(self, workflow_type: WorkflowType) -> bool:
        """Check if this strategy handles the given workflow type."""
        ...
```

### 1.3 The UnifiedExecutor is the only entry point

```python
class UnifiedExecutor:
    """The single durable executor. No subclasses."""

    def __init__(self):
        self.event_log: EventLog
        self.replay_engine: ReplayEngine
        self.budget_enforcer: BudgetEnforcer
        self.capability_engine: CapabilityEngine
        self.failure_analyzer: FailureAnalyzer
        self.lattice: CapabilityLattice
        self._strategies: dict[WorkflowType, ExecutionStrategy]
        self._abort_signals: dict[str, asyncio.Event]

    async def execute(
        self,
        db: AsyncSession,
        workflow: Workflow,
        *,
        run_id: str | None = None,          # For crash recovery
        start_node_id: str | None = None,    # For partial replay
        context: dict[str, Any] | None = None,
    ) -> StrategyResult: ...
```

### 1.4 The 4 Guarantees are enforced at the executor level

Every execution through `UnifiedExecutor` satisfies:
1. **Durable** — every state transition emits a substrate event
2. **Type-checked** — input/output validated via `PydanticAdapter`
3. **Capability-bounded** — tool calls require `CapabilityToken`
4. **Bounded** — `BudgetEnforcer` wraps every LLM call

---

## 2. Strategy Catalog

### 2.1 SoloStrategy (replaces `mission_executor.py`)

**When:** `workflow.type == WorkflowType.SOLO`

**Behavior:**
- A Workflow with one node and no edges.
- The node's `config` contains the task definition (type, prompt, tool, etc.).
- Executes the node directly — no dependency resolution needed.

**What moves to `UnifiedExecutor` base:**
- Task execution (LLM calls, tool calls, code execution) — the executor provides `execute_node()` as a shared method
- Retry with budget enforcement
- Abort signal checking
- Event logging
- Learning context injection
- LLM call recording

**What stays in SoloStrategy:**
- Single-node workflow validation
- Direct dispatch to `executor.execute_node()`

**~50 lines of strategy code.**

### 2.2 DAGStrategy (replaces `dag_executor.py`)

**When:** `workflow.type == WorkflowType.DAG`

**Behavior:**
- Topological sort using Kahn's algorithm (pure function, already exists in `dag_executor.py`).
- Executes nodes in dependency order, with parallel execution within each layer.
- Layer 0 (roots) run in parallel; layer N only after all nodes in layers 0..N-1 complete.

**What moves to base:**
- Kahn's algorithm becomes a utility on `UnifiedExecutor` (all strategies need topological sort)
- Node execution (`execute_node()`)

**What stays in DAGStrategy:**
- DAG validation (cycle detection, missing dep references)  
- Layer-based parallel dispatch
- Layer completion tracking

**~80 lines of strategy code.**

### 2.3 SwarmStrategy (replaces `swarm/orchestrator.py`)

**When:** `workflow.type == WorkflowType.SWARM`

**Behavior:**
- The workflow has a FAN_OUT node that decomposes a goal into subtasks.
- Subtasks are dispatched in parallel to matched agents.
- A FAN_IN node synthesizes results via a consensus sub-protocol.
- Two-phase: decompose (LLM) → dispatch (parallel) → synthesize (LLM).

**What moves to base:**
- LLM calls (through `BudgetEnforcer`)
- Agent matching (through `AgentRegistryService`, already shared)
- Event logging

**What stays in SwarmStrategy:**
- Goal decomposition prompt and parsing
- Synthesis prompt and conflict resolution
- Fan-out/fan-in node handling

**~150 lines of strategy code.**

### 2.4 PipelineStrategy (replaces `swarm_pipeline/orchestrator.py` + phases/*.py)

**When:** `workflow.type == WorkflowType.PIPELINE`

**Behavior:**
- 7 sequential phases: DISPATCH → RESEARCH → DRAFT → DEBATE → CONSENSUS → SYNTHESIS → REVIEW
- Each phase is a PHASE_GATE node in the workflow.
- REVIEW phase can trigger a retry loop (max 3 retries) back to DEBATE.
- Pause/cancel/resume supported via abort signals.

**What moves to base:**
- Abort/pause/resume signal handling
- Event logging per phase
- WebSocket broadcasting (through a shared utility)

**What stays in PipelineStrategy:**
- Phase ordering and transition logic
- Review retry loop
- Phase duration tracking
- Phase gate validation

**~200 lines of strategy code.** The 7 phase modules (~1,500 lines) are preserved as strategy helpers, not deleted.

### 2.5 GraphStrategy (replaces `graph_executor.py`)

**When:** `workflow.type == WorkflowType.GRAPH`

**Behavior:**
- Conditional edges: `edge.condition` is a Python expression or field match evaluated at runtime.
- `ExecutionContext` with interpolation (`{{node_id.output.field}}`).
- NodeHandlerRegistry dispatches node types to handlers.
- Subgraph execution: `start_node_id` filters to a subgraph.

**What moves to base:**
- Topological sort (Kahn's)
- Node execution (`execute_node()`)

**What stays in GraphStrategy:**
- Conditional edge evaluation
- Context interpolation (`resolve_interpolation`, `interpolate_dict`)
- Subgraph filtering (`get_subgraph_nodes`)
- NodeHandlerRegistry integration

**~120 lines of strategy code.**

### 2.6 MetaStrategy (replaces `nexus/meta_loop_orchestrator.py`)

**When:** `workflow.type == WorkflowType.META`

**Behavior:**
- A workflow containing SUB_WORKFLOW nodes.
- Recursive plan-execute-observe loop.
- Failure analysis via `FailureAnalyzer` with budget enforcement.
- Depth clamping via `CapabilityLattice`.
- Alternative tool fallback on failure.

**What moves to base:**
- Budget enforcement (already in `BudgetEnforcer`)
- Depth clamping (already in `CapabilityLattice`)
- Failure analysis (already shared via `FailureAnalyzer`)

**What stays in MetaStrategy:**
- Recursive cycle orchestration
- Retry decision logic
- Context update merging

**~100 lines of strategy code.**

### 2.7 LangGraphStrategy (replaces `langgraph/agent.py`)

**When:** `workflow.type == WorkflowType.LANGGRAPH`

**Behavior:**
- Native LangGraph StateGraph execution.
- Checkpointed subgraph — state is persisted via LangGraph's checkpointer.
- Human-in-the-loop approval workflow.
- Tool handler registry for n8n, ComfyUI, integrations.

**What moves to base:**
- Tool execution (through `CapabilityEngine`)
- Event logging
- Session persistence

**What stays in LangGraphStrategy:**
- StateGraph compilation and invocation
- Approval workflow (already in `langgraph/approval_workflow.py`)
- Tool converter (already in `langgraph/tool_converter.py`)
- Legacy handler registration

**~150 lines of strategy code.**

---

## 3. Shared Base: What `UnifiedExecutor` Provides

Every strategy gets these for free:

### 3.0 Cross-cutting concerns (post-execution hooks)

After every workflow execution (regardless of strategy), `UnifiedExecutor` runs these hooks:

1. **Analytics calculation** — `analytics_service.calculate_mission_metrics()`
2. **Audit logging** — `log_event(mission.user_id, "mission_{status}", {...})`
3. **Linear sync** — `sync_mission_to_linear(mission_id, status, results, error)`
4. **Learning recording** — `learning_service.record_execution(...)`
5. **Self-improvement analysis** — `improvement_loop.on_mission_complete(...)`

These are NOT strategy responsibilities — they're base class post-execution hooks that fire after every run.

### 3.1 Node Execution (`execute_node`)

```python
async def execute_node(
    self,
    db: AsyncSession,
    node: WorkflowNode,
    context: ExecutionContext,
    budget: Budget,
    run_id: str,
) -> NodeResult:
```

This is the single code path for executing a node, regardless of strategy (~500 lines). It handles:

1. **Pre-execution budget check** — `BudgetEnforcer.check_budget()`
2. **Capability token creation** — `CapabilityEngine.issue()` for tool nodes
3. **Node dispatch** — matches `node.type` to the appropriate handler:
   - `LLM_CALL` → `BudgetEnforcer.call()` (the ONLY LLM call path)
   - `TOOL_CALL` → tool handler with `CapabilityEngine.verify()`
   - `CODE_EXECUTION` → sandboxed subprocess with restricted builtins
   - `RAG_QUERY` → `RAGService.query_documents()`
   - `WEB_SEARCH` → `SearchService.search()`
   - `FILE_OPERATION` → `FileStorageService` (read/write/list)
   - `HUMAN_REVIEW` → pause with `waiting_input` status
   - `BROWSER_*` → `ToolRegistry` dispatch (preserves existing browser handlers)
   - `APPROVAL` → human-in-the-loop pause (via LangGraph approval workflow)
   - `SUB_WORKFLOW` → recursive `UnifiedExecutor.execute()`
   - `PHASE_GATE` → delegates to strategy (opaque to node executor)
   - `FAN_OUT` / `FAN_IN` → delegates to strategy (opaque to node executor)
4. **Fallback strategy execution** — `human_escalate` (pause), `abort` (fail), `skip` (continue), `retry` (re-queue)
5. **Event logging** — `EventLog.append()` for node.started / node.completed / node.failed
6. **Retry with budget** — uses `FailureAnalyzer` for error classification and retry budget
7. **LLM call recording** — `LLMCallRecord` + Prometheus metrics

**Important:** All LLM calls go through `BudgetEnforcer.call()`. The direct `httpx` calls in the old swarm orchestrator and mission_executor fallback are replaced. Strategies that currently use direct httpx are refactored to use `executor.budget_enforcer.call()`.

### 3.2 Abort/Pause/Resume

```python
async def abort(self, run_id: str, reason: str) -> bool
async def pause(self, run_id: str) -> bool
async def resume(self, run_id: str) -> bool
```

All strategies check `self._abort_signals[run_id]` between node executions. The signal is an `asyncio.Event`.

### 3.3 Crash Recovery

On `execute()`, the executor checks for an existing `run_id` in the workflow metadata. If found, it replays the event log via `ReplayEngine.rebuild_state()` and resumes from the last completed node.

### 3.4 Budget Enforcement

Every LLM call goes through `BudgetEnforcer.call()`. Tool calls that incur cost also go through budget checks. The budget is a first-class `Budget` object declared at workflow creation time.

### 3.5 Capability Enforcement

Tool nodes require a `CapabilityToken`. The executor calls `CapabilityEngine.issue()` for the tool and `CapabilityEngine.verify()` before execution. Attenuation is supported for sub-workflows.

### 3.6 Observability

Every node execution emits:
- A substrate event (to `substrate_events` table)
- An OpenTelemetry span
- A Langfuse trace
- Prometheus metrics

### 3.7 WebSocket Broadcasting

A shared `WorkflowWSManager` utility provides event broadcasting for all strategies:

```python
class WorkflowWSManager:
    async def send_event(run_id: str, event_type: str, data: dict) -> None
    async def broadcast_phase(run_id: str, phase: str, status: str) -> None
    async def broadcast_node_state(run_id: str, node_id: str, status: str, output: dict) -> None
```

This replaces the scattered `ws_manager.send_event()` (pipeline) and `sio.emit()` (graph) patterns.

### 3.8 LangGraph State Management Strategy

**Problem:** LangGraph uses its own `MemorySaver` checkpointer and Redis-backed `AgentPersistence`. The unified executor has its own event-sourced `EventLog` + `ReplayEngine`. Two competing sources of truth.

**Resolution:** In `LangGraphStrategy`, the substrate event log is the **source of truth** for workflow-level state (node started/completed/failed). LangGraph's checkpointer manages **intra-node** state only (the StateGraph's internal message history and tool execution state). The boundary is:
- Workflow-level: substrate events → ReplayEngine
- Node-level (LangGraph): LangGraph checkpointer → MemorySaver/Redis

For crash recovery of a LangGraph workflow, the replay engine rebuilds which nodes completed, then LangGraph resumes from the last checkpoint within the current node.

---

## 4. File-Level Changes

### New files

| File | Description | LOC (est.) |
|---|---|---|
| `substrate/executor.py` | `UnifiedExecutor` — the single entry point | ~400 |
| `substrate/strategies/__init__.py` | Strategy registry | ~20 |
| `substrate/strategies/base.py` | `ExecutionStrategy` ABC + `StrategyResult` + `WorkflowWSManager` | ~60 |
| `substrate/strategies/solo.py` | `SoloStrategy` | ~50 |
| `substrate/strategies/dag.py` | `DAGStrategy` | ~80 |
| `substrate/strategies/swarm.py` | `SwarmStrategy` | ~150 |
| `substrate/strategies/pipeline.py` | `PipelineStrategy` | ~250 |
| `substrate/strategies/graph.py` | `GraphStrategy` | ~150 |
| `substrate/strategies/meta.py` | `MetaStrategy` | ~100 |
| `substrate/strategies/langgraph.py` | `LangGraphStrategy` | ~150 |
| `substrate/node_executor.py` | `execute_node()` — shared node execution (~500 lines) | ~500 |
| `substrate/adapters.py` | ORM → Workflow adapters (Mission, Flow, Graph, Pipeline) | ~250 |
| `substrate/workflow_models.py` | `Workflow`, `WorkflowNode`, `WorkflowEdge`, `NodeType`, `WorkflowType` | ~100 |

**Total new code:** ~2,260 lines

### Modified files

| File | Change |
|---|---|
| `substrate/executor_v2.py` | Replaced by `substrate/executor.py` — `ExecutorV2` becomes `UnifiedExecutor` |
| `app/api/v1/mission.py` | Route to use `UnifiedExecutor` instead of `mission_executor` |
| `app/services/swarm_pipeline/phases/*.py` | Preserved as helpers for `PipelineStrategy` |

### Deleted files (after verification)

| File | LOC |
|---|---|
| `mission_executor.py` | 1,387 |
| `dag_executor.py` | 179 |
| `graph_executor.py` | 293 |
| `swarm/orchestrator.py` | 331 |
| `swarm_pipeline/orchestrator.py` | ~200 |
| `langgraph/agent.py` | ~250 (keep the module, remove the agent orchestration) |
| `nexus/meta_loop_orchestrator.py` | 225 |
| **Total deleted** | **~2,865** (core orchestrators) |

**Net change:** ~2,260 new - ~2,865 deleted = **~600 lines removed**

Note: The 7 phase modules in `swarm_pipeline/phases/` (~1,500 lines) and the `langgraph/` module's tool handlers, approval workflow, etc. (~650 lines) are preserved. They are strategy helpers, not orchestrators.

---

## 5. Feature Flag & Migration Path

### 5.1 Feature Flag

```python
# .env
FLOWMANNER_UNIFIED_EXECUTOR=off  # off | run | all
```

- `off` — Old executors (current behavior). Default.
- `run` — New missions use `UnifiedExecutor`. Old missions (in-flight) still use old executors.
- `all` — All missions use `UnifiedExecutor`, even in-flight ones (requires migration of in-flight state).

### 5.2 Migration Phases

**Phase A (this implementation):**
1. Build `UnifiedExecutor` + all 7 strategies
2. Gate behind `FLOWMANNER_UNIFIED_EXECUTOR=run`
3. New missions go through the new path
4. Old executors coexist

**Phase B (verification, 2–4 weeks):**
1. Run both paths in parallel on a sample of missions, compare results
2. Fix any divergence
3. Production soak with `run` for 2 weeks

**Phase C (cleanup, 1 week):**
1. Set `FLOWMANNER_UNIFIED_EXECUTOR=all`
2. Delete old executor files
3. Remove feature flag code from routes

---

## 6. Testing Strategy

### 6.1 Unit Tests (per strategy)

Each strategy gets:
- **Validation test:** `test_validate_<strategy>()` — rejects invalid workflows
- **Happy path:** `test_<strategy>_happy_path()` — valid workflow → `StrategyResult(success=True)`
- **Error path:** `test_<strategy>_error_handling()` — node failure → retry → abort
- **Abort test:** `test_<strategy>_abort_mid_execution()` — abort signal → clean shutdown
- **Budget test:** `test_<strategy>_budget_exhausted()` — budget exhausted → `BudgetExhausted` raised

### 6.2 Integration Tests

- `test_unified_executor_crash_recovery()` — kill worker mid-execution, restart, verify state
- `test_unified_executor_deterministic_replay()` — same workflow → same result
- `test_unified_executor_all_strategies()` — one test per strategy via the unified entry point

### 6.3 Chaos Tests (H3.3)

The existing chaos test suite (`tests/chaos/`) should pass against `UnifiedExecutor`:
- `test_kill_worker_mid_mission`
- `test_revoke_capability_mid_run`
- `test_exhaust_budget`
- `test_type_violation_rejected`
- `test_replay_yields_same_state`
- `test_attenuation_preserves_subset`
- `test_no_ambient_authority`

### 6.4 Regression: Old executor parity

Run the existing test suite against both old and new executors on the same set of mission fixtures. Compare:
- Status (completed/failed/aborted)
- Completed task count
- Token usage (within 5%)
- Cost (within 5%)

---

## 7. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LangGraph strategy loses checkpoint compatibility | Medium | High | Keep LangGraph's checkpointer as-is; the strategy is a thin wrapper |
| SwarmPipeline phase handlers depend on old orchestrator state | Medium | Medium | Phase modules are preserved; only the orchestration loop changes |
| Graph node interpolation has edge cases not covered by tests | Medium | Low | Interpolation logic is extracted verbatim from old `graph_executor.py` |
| Performance regression from strategy dispatch overhead | Low | Low | Dispatch is O(1) dict lookup; node execution is the bottleneck, not strategy selection |
| H4 (Workflow consolidation) is a prerequisite but hasn't shipped | High | High | **H5.1 assumes a minimal `Workflow` model.** If H4 hasn't shipped, H5.1 defines its own internal `Workflow` model and adapts the old `Mission`/`Flow`/`Graph` models at the entry point. This is ~50 lines of adapter code. |

---

## 8. Open Questions

1. **Is H4 (Workflow consolidation) actually complete?** The roadmap says H1-H4 are done. If the `Flow`/`Graph` models still exist separately, H5.1 needs adapters.

2. **Should `swarm_pipeline/phases/*.py` be collapsed too?** The 7 phase modules are ~1,500 lines of mostly LLM prompt templates. The roadmap says "the deletion is the value" — but phase templates are data, not orchestration. Recommendation: preserve them.

3. **Should `langgraph/` module be kept intact?** The `langgraph/` module has tool handlers, approval workflow, and persistence that other parts of the system may depend on. Only `langgraph/agent.py`'s orchestration logic is replaced.

4. **Test infrastructure?** Does the homelab have a test runner? The roadmap asked this in §12. If tests exist, TDD this. If not, write the tests alongside the implementation.

---

## 9. Implementation Order

1. **`ExecutionStrategy` ABC + `StrategyResult`** — the interface
2. **`UnifiedExecutor`** — the single entry point with abort/pause/resume
3. **`execute_node()`** — shared node execution with budget, capability, events
4. **`SoloStrategy`** — simplest, verifies the strategy pattern works
5. **`DAGStrategy`** — verifies topological sort + parallel execution
6. **`GraphStrategy`** — verifies conditional edges + interpolation
7. **`SwarmStrategy`** — verifies fan-out/fan-in + synthesis
8. **`PipelineStrategy`** — verifies phase gates + retry loop
9. **`LangGraphStrategy`** — verifies native LangGraph integration
10. **`MetaStrategy`** — verifies recursive execution + failure analysis
11. **Route wiring** — feature flag in API routes
12. **Old executor deletion** — after Phase B verification
