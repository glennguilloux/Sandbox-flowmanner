# Blueprint + Run Unified Model — Deep-Dive Implementation Plan

**Status:** READY FOR REVIEW  
**Date:** 2026-06-03  
**Based on:** [DESIGN-BLUEPRINT-RUN-UNIFIED-MODEL.md](./DESIGN-BLUEPRINT-RUN-UNIFIED-MODEL.md)  
**Codebase Audit:** Full dependency graph mapped  

---

## 0. Executive Summary

This plan transforms the design doc into an actionable, sequenced implementation
roadmap grounded in the actual codebase state. The core insight remains: the
execution layer already solved the unification problem (`Workflow` Pydantic model
+ `UnifiedExecutor`). What remains is unifying the **schema**, **API**, and
**UI** layers.

**Scope:** Backend only. Frontend is a separate deliverable (§11).  
**Estimated effort:** 5–7 sprints (backend), 3–4 sprints (frontend).  
**Risk posture:** Conservative — dual-write with automatic rollback at every phase.

---

## 1. Codebase Reality Check

### 1.1 Current Execution Tables (14 tables, 5 concepts)

| Concept | ORM Table(s) | ORM Model File |
|---------|-------------|----------------|
| Mission | `missions`, `mission_tasks`, `mission_logs` | `models/mission_models.py` |
| Workflow/Graph | `workflows`, `workflow_executions`, `workflow_states` | `models/graph.py` |
| Flow | Reuses `workflows` table (FlowService) | `services/flow/flow_service.py` |
| Orchestrator | `orchestrator_executions`, `orchestrator_tasks` | `models/swarm_models.py` |
| Pipeline | `swarm_pipelines` | `models/swarm_pipeline.py` |

Plus auxiliary:
- `substrate_events` — append-only event log (`models/substrate_models.py`)
- `execution_events` — workflow execution log (`models/workflow_version_models.py`)
- `mission_versions` — version snapshots (`models/mission_advanced_models.py`)
- `workflow_versions` — version snapshots (`models/workflow_version_models.py`)
- `mission_templates` — reusable templates (`models/mission_advanced_models.py`)
- `mission_improvements` — self-improvement suggestions (`models/mission_models.py`)
- `mission_triggers` — cron/webhook triggers (`models/trigger_models.py`)
- `mission_circuit_breakers` — safety limits (`models/circuit_breaker_models.py`)
- `node_groups` — mission builder UI (`models/mission_advanced_models.py`)

### 1.2 The Unified Execution Layer (Already Built)

The execution path is already unified:

```
User creates Mission → mission_to_workflow() → Workflow (Pydantic) → UnifiedExecutor.execute()
User creates Graph   → graph_to_workflow()   → Workflow (Pydantic) → UnifiedExecutor.execute()
User runs Flow       → flow_to_workflow()    → Workflow (Pydantic) → UnifiedExecutor.execute()
```

**Key files in the substrate layer:**

| File | Purpose | Lines |
|------|---------|-------|
| `services/substrate/workflow_models.py` | `Workflow`, `WorkflowNode`, `WorkflowEdge`, `WorkflowType`, `StrategyResult` Pydantic models | ~150 |
| `services/substrate/adapters.py` | `mission_to_workflow()`, `flow_to_workflow()`, `graph_to_workflow()` — ORM → Pydantic converters | ~240 |
| `services/substrate/executor.py` | `UnifiedExecutor` — sole execution entry point, strategy dispatch, budget enforcement | ~310 |
| `services/substrate/strategies/base.py` | `ExecutionStrategy` ABC + `WorkflowWSManager` | ~110 |
| `services/substrate/strategies/*.py` | 7 strategy implementations (Solo, DAG, Graph, Swarm, Pipeline, Meta, LangGraph) | ~varies |
| `services/substrate/event_log.py` | `EventLog` — append-only event store with SERIALIZABLE isolation | ~140 |
| `services/substrate/replay_engine.py` | `ReplayEngine` — rebuilds `SubstrateRunState` from events | ~110 |
| `services/substrate/node_executor.py` | `NodeExecutor` — shared node execution path (~500 lines) | ~500 |
| `models/substrate_models.py` | `SubstrateEvent` ORM + `SubstrateRunState` in-memory projection | ~170 |

### 1.3 Dependency Impact Analysis

**Critical finding:** The existing models are deeply embedded across the codebase.

| Model | Import Sites | Impact |
|-------|-------------|--------|
| `Mission`, `MissionTask`, `MissionStatus`, etc. | **78 files** | Massive — touches API, services, tasks, tests, observability, CQRS |
| `Workflow` (graph.py), `WorkflowExecution`, `WorkflowState` | **20 files** | Moderate — graph API, graph service, flow service, tests |
| `OrchestratorExecution`, `OrchestratorTask` | **7 files** | Low — swarm orchestrator, tasks |
| `SwarmPipeline` / `NexusPipeline` | **10 files** | Low — swarm pipeline phases, analytics |
| `SubstrateEvent` | **~8 files** | Low — event log, replay engine, substrate API |

**Adapter call sites (the critical execution path):**

| Adapter Function | Call Sites | File |
|-----------------|------------|------|
| `mission_to_workflow()` | `commands.py:214` (execute_mission), `commands.py:310` (execute_async fallback) | `api/_mission_cqrs/commands.py` |
| `graph_to_workflow()` | `node_executor.py:610` (sub-workflow execution) | `services/substrate/node_executor.py` |
| `flow_to_workflow()` | `flow_service.py` (flow/run endpoint) | `services/flow/flow_service.py` |

### 1.4 CQRS Pattern (Already Established)

Missions already use a full CQRS architecture:

```
api/v1/mission.py          → Thin route handlers, DI-based
api/_mission_cqrs/commands.py  → MissionCommandHandlers (mutations)
api/_mission_cqrs/queries.py   → MissionQueryHandlers (reads, caching)
api/_mission_cqrs/base.py      → Shared base classes
api/_mission_cqrs/audit.py     → Audit logging
api/_mission_cqrs/deps.py      → FastAPI dependency injection
api/_mission_cqrs/errors.py    → Custom error types
```

**This is the pattern to replicate for Blueprints + Runs.**

### 1.5 Alembic Migration Pattern

The project uses descriptive revision names (not auto-generated hashes):

```python
revision = "h2_substrate_init"         # Descriptive
down_revision = "h13_observability"    # Clear chain
```

Recent migrations follow a date-prefixed or phase-prefixed convention:
- `20260603_phase91_plugins.py`
- `h5_rename_graph_tables.py`
- `20260608_phase6_hitl_cost_cb.py`

---

## 2. Phase 0 — Pre-Work (No Schema Changes)

**Goal:** Eliminate technical debt that would complicate the migration.  
**Duration:** 1 sprint  
**Risk:** Low — no schema changes, no user-visible changes.

### Task 0.1: Verify UnifiedExecutor Is the Sole Execution Path

**Current state:** The CQRS `commands.py:execute_mission()` already routes through
`UnifiedExecutor`. The `execute_async()` fallback also uses it. The
`node_executor.py` uses `graph_to_workflow()` for sub-workflows.

**Action:** Audit all callers of old executors. There should be zero direct calls
to `MissionExecutor.execute()` or `GraphInterpreter.execute()` that bypass
`UnifiedExecutor`.

**Files to audit:**
- `services/mission_executor.py` — Verify this is a thin wrapper or deprecated
- `services/graph_executor.py` — Verify `GraphInterpreter` is only used by `node_executor.py` via adapter
- `services/dag_executor.py` — Verify deprecated
- `services/swarm/orchestrator.py` — Verify routes through unified
- `services/swarm_pipeline/orchestrator.py` — Verify routes through unified

**Acceptance criteria:** Grep for direct executor instantiation shows only
`UnifiedExecutor` in production paths. Legacy executors exist only as
import-compatibility shims.

### Task 0.2: Add Integration Tests for Current Execution Path

Write tests that exercise the full path:
1. Create Mission → adapt → execute → verify substrate_events
2. Create GraphWorkflow → adapt → execute → verify substrate_events
3. Create Flow → adapt → execute → verify substrate_events

These tests become the **regression safety net** for all subsequent phases.

**Files to create:**
- `tests/integration/test_unified_execution_path.py`

### Task 0.3: Document Current Event Types in SubstrateEventType

Create a mapping document from current `MISSION_*` event types to proposed
`RUN_*` types (cosmetic rename deferred to Phase 3):

```python
# Current → Proposed
MISSION_STARTED   → RUN_STARTED
MISSION_COMPLETED → RUN_COMPLETED
MISSION_FAILED    → RUN_FAILED
MISSION_ABORTED   → RUN_ABORTED
MISSION_PAUSED    → RUN_PAUSED
MISSION_RESUMED   → RUN_RESUMED
TASK_STARTED      → NODE_STARTED
TASK_COMPLETED    → NODE_COMPLETED
TASK_FAILED       → NODE_FAILED
TASK_RETRYING     → NODE_RETRYING
TASK_SKIPPED      → NODE_SKIPPED
```

### Task 0.4: Add `run_id` Index to `substrate_events`

The `run_id` column already exists and is indexed, but the FK constraint to a
`runs` table doesn't exist yet. No action needed — this is handled in Phase 1.

---

## 3. Phase 1 — New Tables + Compatibility Views (Additive)

**Goal:** Create `blueprints`, `runs`, and `blueprint_versions` tables alongside
existing tables. Create PostgreSQL views that map old table names to new tables
for zero-downtime compatibility.  
**Duration:** 2 sprints  
**Risk:** Low — purely additive, no existing code changes.

### Task 1.1: Create `Blueprint` ORM Model

**File:** `backend/app/models/blueprint_models.py` (new)

```python
class BlueprintStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"

class BlueprintType(str, Enum):
    SOLO = "solo"
    DAG = "dag"
    SWARM = "swarm"
    PIPELINE = "pipeline"
    GRAPH = "graph"
    META = "meta"
    LANGGRAPH = "langgraph"

class Blueprint(Base, TimestampMixin):
    __tablename__ = "blueprints"

    id: Mapped[str]            # UUID PK
    workspace_id: Mapped[str | None]  # FK → workspaces.id
    user_id: Mapped[int]       # FK → users.id

    # Identity
    title: Mapped[str]         # String(255)
    description: Mapped[str]   # Text, default=""

    # Definition — THE key column
    blueprint_type: Mapped[str]   # String(50), maps 1:1 to WorkflowType
    definition: Mapped[dict]      # JSONB — stores the Workflow-shaped data
    input_schema: Mapped[dict | None]   # JSONB
    output_schema: Mapped[dict | None]  # JSONB

    # Lifecycle
    status: Mapped[str]        # String(20), default="draft"
    version: Mapped[int]       # Integer, default=1

    # Metadata
    tags: Mapped[list | None]  # JSONB
    category: Mapped[str | None]  # String(100)
    icon: Mapped[str | None]  # String(50)

    # Usage stats (denormalized)
    run_count: Mapped[int]     # Integer, default=0
    last_run_at: Mapped[datetime | None]

    # Soft delete
    deleted_at: Mapped[datetime | None]
    deleted_by: Mapped[int | None]
```

**Design decisions grounded in codebase:**
- `blueprint_type` is a `str` not an enum column — matches the pattern in
  `Mission.mission_type` and `Workflow.status` (both strings, not PG enums).
- `definition` JSONB stores the same shape as `Workflow` Pydantic model — see
  §3.1 for the exact schema.
- `workspace_id` is `String(36)` FK matching the pattern in `Mission.workspace_id`
  and `Workflow.workspace_id`.
- `user_id` is `Integer` FK matching existing patterns.

### Task 1.2: Create `Run` ORM Model

**File:** `backend/app/models/blueprint_models.py` (same file)

```python
class RunStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"

class Run(Base, TimestampMixin):
    __tablename__ = "runs"

    id: Mapped[str]            # UUID PK
    blueprint_id: Mapped[str | None]  # FK → blueprints.id, SET NULL on delete
    workspace_id: Mapped[str | None]  # FK → workspaces.id
    user_id: Mapped[int | None]       # FK → users.id

    # Execution state
    status: Mapped[str]        # String(20), default="pending", indexed

    # Immutable snapshot of blueprint definition at run creation time
    snapshot: Mapped[dict]     # JSONB — {blueprint_type, nodes, edges, config, budget, ...}

    # Results
    output_data: Mapped[dict | None]  # JSONB
    error_message: Mapped[str | None]

    # Budget tracking
    total_tokens: Mapped[int]        # Integer, default=0
    total_cost_usd: Mapped[float]    # Float, default=0.0
    budget_limit_usd: Mapped[float | None]

    # Timing
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]

    # Parent/child for sub-workflows (SUB_WORKFLOW NodeType)
    parent_run_id: Mapped[str | None]  # FK → runs.id

    # Context
    input_data: Mapped[dict | None]  # JSONB — runtime overrides

    # Metadata
    meta: Mapped[dict | None]  # JSONB — agent IDs, model IDs, etc.
```

**Design decisions:**
- `snapshot` is the immutable copy of `Blueprint.definition` at run time.
  This is critical for deterministic replay — the existing `ReplayEngine`
  already rebuilds state from events, but `snapshot` tells you *what* was executed.
- `parent_run_id` supports the existing `SUB_WORKFLOW` NodeType in
  `workflow_models.py` — `node_executor.py:610` currently creates sub-workflows
  via `graph_to_workflow()`. With the new model, it creates a child `Run`.
- `blueprint_id` is `SET NULL` on delete — runs survive blueprint deletion.
  This matches the pattern for `WorkflowExecution.workflow_id` which uses `CASCADE`,
  but `SET NULL` is safer for audit trails.

### Task 1.3: Create `BlueprintVersion` ORM Model

**File:** `backend/app/models/blueprint_models.py` (same file)

```python
class BlueprintVersion(Base, TimestampMixin):
    __tablename__ = "blueprint_versions"

    id: Mapped[str]            # UUID PK
    blueprint_id: Mapped[str]  # FK → blueprints.id, CASCADE on delete
    version: Mapped[int]       # Integer
    snapshot: Mapped[dict]     # JSONB — full blueprint definition at this version
    description: Mapped[str | None]  # changelog
    created_by: Mapped[int | None]   # FK → users.id
```

This replaces:
- `MissionVersion` (`mission_advanced_models.py`) — stores individual columns
  (title, description, plan, etc.). The new model uses a single `snapshot` JSONB,
  matching the pattern in `WorkflowVersion.snapshot`.

### Task 1.4: Alembic Migration — Create Tables

**File:** `backend/alembic/versions/20260604_phase101_blueprints_runs.py` (new)

```python
revision = "20260604_phase101_blueprints_runs"
down_revision = <current head>
```

**Migration steps:**
1. Create `blueprints` table with all columns + indexes
2. Create `runs` table with all columns + indexes
3. Create `blueprint_versions` table
4. Add `blueprint_id` column to `substrate_events` (nullable, indexed)
5. Add FK constraint `substrate_events.blueprint_id → blueprints.id` (SET NULL)
6. **Do NOT** create compatibility views yet (that's Task 1.5)

**Indexes to create:**
```sql
-- blueprints
CREATE INDEX ix_blueprints_user_id ON blueprints(user_id);
CREATE INDEX ix_blueprints_workspace_id ON blueprints(workspace_id);
CREATE INDEX ix_blueprints_status ON blueprints(status);
CREATE INDEX ix_blueprints_blueprint_type ON blueprints(blueprint_type);
CREATE INDEX ix_blueprints_deleted_at ON blueprints(deleted_at);

-- runs
CREATE INDEX ix_runs_blueprint_id ON runs(blueprint_id);
CREATE INDEX ix_runs_user_id ON runs(user_id);
CREATE INDEX ix_runs_workspace_id ON runs(workspace_id);
CREATE INDEX ix_runs_status ON runs(status);
CREATE INDEX ix_runs_parent_run_id ON runs(parent_run_id);
CREATE INDEX ix_runs_created_at ON runs(created_at);

-- substrate_events (new column)
CREATE INDEX ix_substrate_events_blueprint_id ON substrate_events(blueprint_id);
```

### Task 1.5: Register New Models in `__init__.py`

**File:** `backend/app/models/__init__.py`

Add imports after the existing model registrations:

```python
# Blueprint + Run models (Phase 10.1)
from app.models.blueprint_models import (  # noqa: E402, F401
    Blueprint,
    BlueprintVersion,
    Run,
)
```

### Task 1.6: Verify Migration on Staging

**Action:** Apply migration to staging database. Verify:
- Tables created with correct schema
- Existing data untouched
- `substrate_events` still append-only (trigger not broken by new column)
- Performance: new indexes don't slow down existing queries

---

## 4. Phase 2 — Blueprint Definition Schema

**Goal:** Define the exact JSONB structure for `Blueprint.definition` and create
the Pydantic models for validation.  
**Duration:** 1 sprint  
**Risk:** Low — new code only, no existing code changes.

### Task 2.1: Create `BlueprintDefinition` Pydantic Model

**File:** `backend/app/schemas/blueprint.py` (new)

The `definition` column stores a JSONB structure that maps directly to the
existing `Workflow` Pydantic model, but without runtime fields.

```python
class BlueprintNodeDefinition(BaseModel):
    """Declarative node definition — no runtime fields."""
    id: str
    type: str  # NodeType value
    title: str = ""
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    assigned_model: str | None = None
    assigned_agent_id: str | None = None
    max_retries: int = 3
    fallback_strategy: str = "human_escalate"

class BlueprintEdgeDefinition(BaseModel):
    source: str
    target: str
    condition: str | None = None
    label: str | None = None

class BlueprintBudgetDefinition(BaseModel):
    max_cost_usd: float = 10.0
    max_wall_time_seconds: int = 300
    max_iterations: int = 100
    max_depth: int = 5

class BlueprintDefinition(BaseModel):
    """The declarative part of a blueprint — stored in definition JSONB."""
    blueprint_type: str
    nodes: list[BlueprintNodeDefinition] = Field(default_factory=list)
    edges: list[BlueprintEdgeDefinition] = Field(default_factory=list)
    budget: BlueprintBudgetDefinition = Field(default_factory=BlueprintBudgetDefinition)
    config: dict[str, Any] = Field(default_factory=dict)
```

**Why a separate `BlueprintDefinition` model?** The `Workflow` Pydantic model
includes runtime fields (`status`, `output_data`, `retry_count` on nodes) that
should not be stored in the blueprint. The `BlueprintDefinition` is the
declarative subset.

### Task 2.2: Create `blueprint_to_workflow()` Adapter

**File:** `backend/app/services/substrate/adapters.py`

Add a new function that trivially converts a Blueprint's snapshot to a `Workflow`:

```python
def blueprint_to_workflow(snapshot: dict, blueprint_id: str, user_id: str | None = None) -> Workflow:
    """Convert a Run's snapshot dict into a Workflow for UnifiedExecutor.
    
    This is the trivial adapter — the snapshot IS the Workflow shape.
    """
    from app.models.capability_models import Budget
    from decimal import Decimal
    
    budget_data = snapshot.get("budget", {})
    budget = Budget(
        max_cost_usd=Decimal(str(budget_data.get("max_cost_usd", "10.00"))),
        max_wall_time_seconds=budget_data.get("max_wall_time_seconds", 300),
        max_iterations=budget_data.get("max_iterations", 100),
        max_depth=budget_data.get("max_depth", 5),
    )
    
    return Workflow(
        id=blueprint_id,
        type=WorkflowType(snapshot.get("blueprint_type", "solo")),
        title=snapshot.get("title", ""),
        description=snapshot.get("description"),
        nodes=[WorkflowNode(**n) for n in snapshot.get("nodes", [])],
        edges=[WorkflowEdge(**e) for e in snapshot.get("edges", [])],
        budget=budget,
        user_id=user_id,
        metadata=snapshot.get("config", {}),
    )
```

**Keep the old adapters.** `mission_to_workflow()`, `flow_to_workflow()`,
`graph_to_workflow()` remain functional throughout the transition. They are
deprecated in Phase 3 and removed in Phase 4.

### Task 2.3: Create Request/Response Schemas

**File:** `backend/app/schemas/blueprint.py` (extend)

```python
class BlueprintCreate(BaseModel):
    title: str
    description: str = ""
    blueprint_type: str = "solo"
    definition: BlueprintDefinition | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    tags: list[str] | None = None
    category: str | None = None
    icon: str | None = None

class BlueprintUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    definition: BlueprintDefinition | None = None
    status: str | None = None
    tags: list[str] | None = None
    category: str | None = None
    icon: str | None = None

class BlueprintResponse(BaseModel):
    id: str
    workspace_id: str | None
    user_id: int
    title: str
    description: str
    blueprint_type: str
    definition: dict
    status: str
    version: int
    tags: list | None
    category: str | None
    icon: str | None
    run_count: int
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class RunCreate(BaseModel):
    """Create a run from a blueprint."""
    input_data: dict | None = None
    budget_override: BlueprintBudgetDefinition | None = None

class RunResponse(BaseModel):
    id: str
    blueprint_id: str | None
    workspace_id: str | None
    user_id: int | None
    status: str
    snapshot: dict
    output_data: dict | None
    error_message: str | None
    total_tokens: int
    total_cost_usd: float
    budget_limit_usd: float | None
    started_at: datetime | None
    completed_at: datetime | None
    parent_run_id: str | None
    input_data: dict | None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class RunEventResponse(BaseModel):
    id: str
    sequence: int
    run_id: str
    type: str
    payload: dict | None
    actor: str
    timestamp: datetime
```

---

## 5. Phase 3 — Service Layer (Blueprint CRUD + Run Lifecycle)

**Goal:** Implement `BlueprintService` and `RunService` with full lifecycle
management. The old services continue to work unchanged.  
**Duration:** 2 sprints  
**Risk:** Medium — new code, but exercises the same execution path.

### Task 3.1: Implement `BlueprintService`

**File:** `backend/app/services/blueprint_service.py` (new)

**Responsibilities:**
- CRUD operations on `Blueprint` ORM model
- Version management (create version on every `definition` change)
- Publish/unpublish lifecycle
- Soft delete
- Usage stats update (run_count, last_run_at)

**Key methods:**

```python
class BlueprintService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: int, payload: BlueprintCreate, 
                     workspace_id: str | None = None) -> Blueprint:
        """Create a new blueprint. Creates initial version."""
        
    async def get(self, blueprint_id: str, user_id: int) -> Blueprint:
        """Get blueprint with ownership/workspace check."""
        
    async def list(self, user_id: int, page: int, per_page: int,
                   workspace_id: str | None = None,
                   blueprint_type: str | None = None,
                   status: str | None = None) -> tuple[list[Blueprint], int]:
        """List blueprints with filtering and pagination."""
        
    async def update(self, blueprint_id: str, user_id: int, 
                     payload: BlueprintUpdate) -> Blueprint:
        """Update blueprint. If definition changed, creates new version."""
        
    async def delete(self, blueprint_id: str, user_id: int) -> bool:
        """Soft delete blueprint."""
        
    async def publish(self, blueprint_id: str, user_id: int) -> Blueprint:
        """Publish blueprint (draft → published)."""
        
    async def create_version(self, blueprint: Blueprint, change_summary: str | None = None) -> BlueprintVersion:
        """Snapshot current definition as a new version."""
```

**Pattern to follow:** Mirror the `MissionService` patterns in
`services/mission_service.py` — workspace-aware access checks, ownership
validation, soft delete with `deleted_at`.

### Task 3.2: Implement `RunService`

**File:** `backend/app/services/run_service.py` (new)

**Responsibilities:**
- Create run from blueprint (snapshot the definition)
- Start execution (delegate to `UnifiedExecutor`)
- Abort/retry/pause lifecycle
- Query run status, events, replay
- Parent/child run management

**Key methods:**

```python
class RunService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_from_blueprint(
        self, blueprint_id: str, user_id: int,
        input_data: dict | None = None,
        budget_override: dict | None = None,
    ) -> Run:
        """Create a Run from a Blueprint.
        
        1. Load Blueprint
        2. Snapshot Blueprint.definition into Run.snapshot
        3. Create Run record (status=pending)
        4. Return Run (caller decides when to execute)
        """
        
    async def execute(self, run_id: str, user_id: int) -> Run:
        """Execute a run through UnifiedExecutor.
        
        1. Load Run + snapshot
        2. Convert snapshot to Workflow via blueprint_to_workflow()
        3. Call UnifiedExecutor.execute(db, workflow, run_id=run.id)
        4. Update Run status based on StrategyResult
        5. Update Blueprint.run_count, Blueprint.last_run_at
        """
        
    async def execute_async(self, run_id: str, user_id: int) -> Run:
        """Queue run for async execution via Celery."""
        
    async def abort(self, run_id: str, user_id: int, reason: str = "user_requested") -> Run:
        """Abort a running execution."""
        
    async def retry(self, run_id: str, user_id: int) -> Run:
        """Retry a failed run — creates a NEW run from the same blueprint."""
        
    async def get(self, run_id: str, user_id: int) -> Run:
        """Get run with ownership/workspace check."""
        
    async def list(self, user_id: int, page: int, per_page: int,
                   workspace_id: str | None = None,
                   blueprint_id: str | None = None,
                   status: str | None = None) -> tuple[list[Run], int]:
        """List runs with filtering."""
        
    async def get_events(self, run_id: str, user_id: int,
                         from_sequence: int = 0, limit: int = 1000) -> list[SubstrateEvent]:
        """Get substrate events for a run."""
        
    async def replay_state(self, run_id: str, user_id: int,
                           at_sequence: int | None = None) -> SubstrateRunState:
        """Replay events to rebuild run state."""
        
    async def diff_runs(self, run_a_id: str, run_b_id: str, user_id: int) -> dict:
        """Compare two runs of the same blueprint."""
```

**Critical detail — the execute() flow:**

```python
async def execute(self, run_id: str, user_id: int) -> Run:
    run = await self.get(run_id, user_id)
    
    # Convert snapshot to Workflow
    workflow = blueprint_to_workflow(
        snapshot=run.snapshot,
        blueprint_id=str(run.blueprint_id) if run.blueprint_id else str(run.id),
        user_id=str(user_id),
    )
    
    # Execute through the unified executor
    executor = get_unified_executor()
    result = await executor.execute(
        db=self.db,
        workflow=workflow,
        run_id=str(run.id),
    )
    
    # Update run from result
    run.status = result.status
    run.total_tokens = result.total_tokens
    run.total_cost_usd = result.total_cost_usd
    run.error_message = result.error
    run.completed_at = datetime.now(timezone.utc) if result.status in ("completed", "failed", "aborted") else None
    
    # Update blueprint stats
    if run.blueprint_id:
        blueprint = await self.db.get(Blueprint, run.blueprint_id)
        if blueprint:
            blueprint.run_count = (blueprint.run_count or 0) + 1
            blueprint.last_run_at = datetime.now(timezone.utc)
    
    await self.db.commit()
    return run
```

### Task 3.3: Update `UnifiedExecutor` to Accept Run Context

**File:** `backend/app/services/substrate/executor.py`

**Changes are minimal.** The `execute()` method already accepts a `run_id`.
The change is to also accept and propagate `blueprint_id`:

```python
async def execute(
    self,
    db: AsyncSession,
    workflow: Workflow,
    *,
    run_id: str | None = None,
    blueprint_id: str | None = None,  # NEW
    start_node_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> StrategyResult:
```

In the event emission, add `blueprint_id` to the payload:

```python
await self.event_log.append(db, run_id, [{
    "type": SubstrateEventType.MISSION_STARTED,  # Renamed in Phase 5
    "payload": {
        "title": workflow.title,
        "workflow_type": workflow.type.value,
        "user_id": workflow.user_id,
        "node_count": len(workflow.nodes),
        "blueprint_id": blueprint_id,  # NEW
    },
    "actor": "unified_executor",
    "mission_id": workflow.id,
    "blueprint_id": blueprint_id,  # NEW — stored on event row
}])
```

### Task 3.4: Update `EventLog.append()` to Support `blueprint_id`

**File:** `backend/app/services/substrate/event_log.py`

The `append()` method needs to accept and store `blueprint_id`:

```python
async def append(
    self, db: AsyncSession, run_id: str, events: list[dict],
    *, mission_id: str | None = None, blueprint_id: str | None = None,  # NEW
) -> list[SubstrateEvent]:
    # ... existing logic ...
    for i, event_dict in enumerate(events):
        event = SubstrateEvent(
            # ... existing fields ...
            blueprint_id=blueprint_id or event_dict.get("blueprint_id"),  # NEW
        )
```

---

## 6. Phase 4 — API Layer (V2 Endpoints)

**Goal:** Create `/api/v2/blueprints` and `/api/v2/runs` endpoints following
the CQRS pattern established by missions.  
**Duration:** 2 sprints  
**Risk:** Medium — new endpoints, no existing endpoints affected.

### Task 4.1: Create Blueprint CQRS Handlers

**Files:**
- `backend/app/api/_blueprint_cqrs/__init__.py` (new)
- `backend/app/api/_blueprint_cqrs/commands.py` (new)
- `backend/app/api/_blueprint_cqrs/queries.py` (new)
- `backend/app/api/_blueprint_cqrs/deps.py` (new)
- `backend/app/api/_blueprint_cqrs/base.py` (new)

Follow the exact same pattern as `_mission_cqrs/`:

```python
# _blueprint_cqrs/deps.py
def get_blueprint_queries(db: AsyncSession = Depends(get_db)) -> BlueprintQueryHandlers:
    return BlueprintQueryHandlers(db)

def get_blueprint_commands(db: AsyncSession = Depends(get_db)) -> BlueprintCommandHandlers:
    return BlueprintCommandHandlers(db)
```

### Task 4.2: Create V2 Blueprint API Routes

**File:** `backend/app/api/v2/blueprints.py` (new)

```python
router = APIRouter(prefix="/blueprints", tags=["blueprints-v2"])

@router.get("")
async def list_blueprints(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    blueprint_type: str | None = None,
    status: str | None = None,
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    q: BlueprintQueryHandlers = Depends(get_blueprint_queries),
):
    """List blueprints with optional type/status filtering."""

@router.post("", status_code=201)
async def create_blueprint(
    payload: BlueprintCreate,
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    c: BlueprintCommandHandlers = Depends(get_blueprint_commands),
):
    """Create a new blueprint."""

@router.get("/{blueprint_id}")
async def get_blueprint(
    blueprint_id: str,
    user: User = Depends(get_current_user),
    q: BlueprintQueryHandlers = Depends(get_blueprint_queries),
):
    """Get blueprint details."""

@router.patch("/{blueprint_id}")
async def update_blueprint(
    blueprint_id: str,
    payload: BlueprintUpdate,
    user: User = Depends(get_current_user),
    c: BlueprintCommandHandlers = Depends(get_blueprint_commands),
):
    """Update blueprint (creates new version if definition changes)."""

@router.delete("/{blueprint_id}", status_code=204)
async def delete_blueprint(
    blueprint_id: str,
    user: User = Depends(get_current_user),
    c: BlueprintCommandHandlers = Depends(get_blueprint_commands),
):
    """Soft-delete blueprint."""

@router.post("/{blueprint_id}/run", status_code=201)
async def run_blueprint(
    blueprint_id: str,
    payload: RunCreate | None = None,
    user: User = Depends(get_current_user),
    c: BlueprintCommandHandlers = Depends(get_blueprint_commands),
):
    """Create and execute a run from this blueprint."""

@router.get("/{blueprint_id}/versions")
async def list_versions(
    blueprint_id: str,
    user: User = Depends(get_current_user),
    q: BlueprintQueryHandlers = Depends(get_blueprint_queries),
):
    """List version history."""
```

### Task 4.3: Create V2 Run API Routes

**File:** `backend/app/api/v2/runs.py` (new)

```python
router = APIRouter(prefix="/runs", tags=["runs-v2"])

@router.get("")
async def list_runs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    blueprint_id: str | None = None,
    status: str | None = None,
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """List all runs, filterable by blueprint and status."""

@router.get("/{run_id}")
async def get_run(
    run_id: str,
    user: User = Depends(get_current_user),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """Get run details + current state."""

@router.post("/{run_id}/abort")
async def abort_run(
    run_id: str,
    reason: str = "user_requested",
    user: User = Depends(get_current_user),
    c: RunCommandHandlers = Depends(get_run_commands),
):
    """Abort a running execution."""

@router.post("/{run_id}/retry")
async def retry_run(
    run_id: str,
    user: User = Depends(get_current_user),
    c: RunCommandHandlers = Depends(get_run_commands),
):
    """Retry a failed run (creates new run from same blueprint)."""

@router.get("/{run_id}/events")
async def get_run_events(
    run_id: str,
    from_sequence: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
    user: User = Depends(get_current_user),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """Get substrate event stream for this run."""

@router.get("/{run_id}/replay")
async def replay_run(
    run_id: str,
    at_sequence: int | None = None,
    user: User = Depends(get_current_user),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """Replay run state at a given sequence number (time-travel)."""

@router.get("/{run_id}/diff/{other_run_id}")
async def diff_runs(
    run_id: str,
    other_run_id: str,
    user: User = Depends(get_current_user),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """Compare two runs of the same blueprint."""
```

### Task 4.4: Register V2 Router

**File:** `backend/app/api/v1/__init__.py` or `backend/app/main_fastapi.py`

Add the V2 router:

```python
from app.api.v2.blueprints import router as blueprints_v2_router
from app.api.v2.runs import router as runs_v2_router

app.include_router(blueprints_v2_router, prefix="/api/v2")
app.include_router(runs_v2_router, prefix="/api/v2")
```

### Task 4.5: Add Subscription/Tier Checks

Follow the existing pattern from `commands.py`:

```python
from app.services.subscription_service import check_mission_create_allowed
# Replicate for blueprints:
from app.services.subscription_service import check_blueprint_create_allowed
```

---

## 7. Phase 5 — Dual-Write Transition

**Goal:** All new creates go through the new Blueprint + Run path. Old API
endpoints write to BOTH old and new tables. Background job backfills existing
data.  
**Duration:** 2 sprints  
**Risk:** High — this is the most complex phase. Requires careful monitoring.

### Task 5.1: Implement Dual-Write in Mission Creation

**File:** `backend/app/api/_mission_cqrs/commands.py`

When `create_mission()` is called, also create a Blueprint:

```python
async def create_mission(self, user, payload, workspace_id=None):
    # ... existing mission creation ...
    mission = await create_mission(...)
    
    # DUAL-WRITE: Also create a Blueprint
    try:
        from app.services.blueprint_service import BlueprintService
        bp_service = BlueprintService(self.session)
        await bp_service.create(
            user_id=user.id,
            payload=BlueprintCreate(
                title=payload.title,
                description=payload.description or "",
                blueprint_type=payload.mission_type or "solo",
                # definition populated by mission planner
            ),
            workspace_id=workspace_id,
            _source_mission_id=str(mission.id),  # Link back
        )
    except Exception:
        logger.warning("Dual-write blueprint creation failed", exc_info=True)
    
    return mission
```

### Task 5.2: Implement Dual-Write in Mission Execution

When `execute_mission()` is called, also create a Run:

```python
# In commands.py execute_mission():
async def _op():
    # Existing path
    workflow = mission_to_workflow(mission, tasks)
    strategy_result = await unified.execute(self.session, workflow)
    
    # DUAL-WRITE: Also create a Run
    try:
        from app.services.run_service import RunService
        from app.services.blueprint_service import BlueprintService
        bp_service = BlueprintService(self.session)
        # Look up the linked blueprint by source_mission_id
        linked_blueprint = await bp_service.get_by_source_mission_id(
            str(mission.id), user.id,
        )
        if linked_blueprint:
            run_service = RunService(self.session)
            run = await run_service.create_from_blueprint(
                blueprint_id=str(linked_blueprint.id),
                user_id=user.id,
            )
            run.status = strategy_result.status
            run.total_tokens = strategy_result.total_tokens
            run.total_cost_usd = strategy_result.total_cost_usd
            run.error_message = strategy_result.error
            await self.session.commit()
    except Exception:
        logger.warning("Dual-write run creation failed", exc_info=True)
```

**Note:** `BlueprintService.get_by_source_mission_id()` requires adding a
`source_mission_id` column to the `blueprints` table (or a separate link
table `mission_blueprint_map`) to maintain the bidirectional link during
dual-write. This column is dropped in Phase 7 cleanup.

### Task 5.3: Backfill Script

**⚠️ ORDERING CONSTRAINT:** The backfill script MUST run AFTER dual-write is
live in production. If backfill runs first and then dual-write creates new
records, you get duplicates. The correct sequence is:
1. Deploy dual-write code (Phase 5.1 + 5.2)
2. Verify dual-write is working (check new table counts increasing)
3. THEN run backfill for historical data
4. THEN run consistency verification

**File:** `backend/scripts/backfill_blueprints_runs.py` (new)

A one-time script that:
1. Reads all existing `missions` → creates corresponding `blueprints`
2. Reads all existing `mission_tasks` → populates `blueprint.definition.nodes`
3. Links `substrate_events` rows to new `blueprints` via `blueprint_id`
4. Creates `runs` from `workflow_executions` and `orchestrator_executions`

**Run this as a background Celery task:**

```python
@celery_app.task(bind=True, max_retries=3)
def backfill_blueprints_runs(self, batch_size=100):
    """Backfill blueprints + runs from existing mission/workflow data."""
```

### Task 5.4: Consistency Verification

**File:** `backend/scripts/verify_backfill_consistency.py` (new)

After backfill:
1. Count blueprints vs missions — should match (minus soft-deleted)
2. Count runs vs (workflow_executions + orchestrator_executions + swarm_pipelines)
3. Sample 100 random missions → verify corresponding blueprint has correct definition
4. Sample 100 random runs → verify snapshot matches original execution

### Task 5.5: Add Deprecation Headers to Old Endpoints

**Files:**
- `backend/app/api/v1/mission.py`
- `backend/app/api/v1/graph.py`
- `backend/app/api/v1/flow_compat.py`
- `backend/app/api/v2/missions.py` (also exists — must not be forgotten)

Add response headers:

```python
@router.get("")
async def list_items(...):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-09-01"
    response.headers["Link"] = '</api/v2/blueprints>; rel="successor-version"'
    # ... existing logic ...
```

---

## 8. Phase 6 — Cut Over

**Goal:** Switch all reads to new tables. Drop compatibility views. Drop old
tables after verified backup.  
**Duration:** 1 sprint  
**Risk:** High — point of no return. Requires rollback plan.

### Task 8.1: Switch Read Paths

Update old API endpoints to read from new tables:

```python
# In api/v1/mission.py list_items():
async def list_items(...):
    # NEW: Read from blueprints + runs views
    from app.services.blueprint_service import BlueprintService
    bp_service = BlueprintService(db)
    blueprints, total = await bp_service.list(
        user_id=user.id, page=page, per_page=per_page,
        workspace_id=workspace_id, blueprint_type="solo",
    )
    # Convert to MissionResponse format for backward compat
    return {"items": [_blueprint_to_mission_response(b) for b in blueprints], ...}
```

### Task 8.2: Create Compatibility Views

**File:** `backend/alembic/versions/20260604_phase102_compat_views.py` (new)

```python
def upgrade():
    # Create views that map old table names to new tables
    # NOTE: missions_compat uses LATERAL join to get ONE row per blueprint
    # (the latest run). A plain LEFT JOIN would produce duplicate rows when
    # a blueprint has multiple runs, breaking list endpoints.
    op.execute("""
        CREATE OR REPLACE VIEW missions_compat AS
        SELECT 
            b.id,
            b.user_id,
            b.title,
            b.description,
            b.blueprint_type AS mission_type,
            b.status,
            latest_run.total_tokens AS tokens_used,
            latest_run.total_cost_usd AS actual_cost,
            latest_run.started_at,
            latest_run.completed_at,
            b.created_at,
            b.updated_at,
            b.deleted_at,
            b.workspace_id
        FROM blueprints b
        LEFT JOIN LATERAL (
            SELECT r.total_tokens, r.total_cost_usd, r.started_at, r.completed_at
            FROM runs r
            WHERE r.blueprint_id = b.id
            ORDER BY r.created_at DESC
            LIMIT 1
        ) latest_run ON true
        WHERE b.blueprint_type IN ('solo', 'dag')
    """)
    
    op.execute("""
        CREATE OR REPLACE VIEW workflows_compat AS
        SELECT 
            b.id,
            b.title AS name,
            b.description,
            b.definition AS graph_definition,
            b.status,
            b.user_id,
            b.workspace_id,
            b.created_at,
            b.updated_at
        FROM blueprints b
        WHERE b.blueprint_type IN ('graph', 'dag')
    """)
    
    op.execute("""
        CREATE OR REPLACE VIEW workflow_executions_compat AS
        SELECT 
            r.id,
            r.blueprint_id AS workflow_id,
            r.user_id,
            r.status,
            r.input_data,
            r.output_data,
            r.error_message,
            r.started_at,
            r.created_at,
            r.completed_at,
            r.workspace_id
        FROM runs r
    """)
```

### Task 8.3: Drop Old Tables (After Verified Backup)

**File:** `backend/alembic/versions/20260604_phase103_drop_old_tables.py` (new)

**Pre-conditions:**
1. All reads switched to new tables
2. Compatibility views verified working
3. Full database backup taken
4. 2-week soak period with no issues

```python
def upgrade():
    # Drop in dependency order
    op.drop_table("mission_logs")
    op.drop_table("mission_tasks")
    op.drop_table("execution_events")
    op.drop_table("workflow_states")
    op.drop_table("workflow_executions")
    op.drop_table("workflow_versions")
    op.drop_table("orchestrator_tasks")
    op.drop_table("orchestrator_executions")
    op.drop_table("swarm_pipelines")
    op.drop_table("mission_versions")
    op.drop_table("mission_templates")
    # missions and workflows tables last (most FK dependencies)
    op.drop_table("missions")
    op.drop_table("workflows")
    
    # Drop compat views
    op.execute("DROP VIEW IF EXISTS missions_compat")
    op.execute("DROP VIEW IF EXISTS workflows_compat")
    op.execute("DROP VIEW IF EXISTS workflow_executions_compat")
```

**⚠️ This migration has NO downgrade.** The old tables are gone. Rollback
requires restoring from backup.

---

## 9. Phase 7 — Cleanup

**Goal:** Remove deprecated code, unify event types, simplify adapters.  
**Duration:** 1 sprint  
**Risk:** Low — removing dead code.

### Task 9.1: Remove Old Adapters

**File:** `backend/app/services/substrate/adapters.py`

Remove:
- `mission_to_workflow()` — replaced by `blueprint_to_workflow()`
- `flow_to_workflow()` — replaced by `blueprint_to_workflow()`
- `graph_to_workflow()` — replaced by `blueprint_to_workflow()`
- `_TASK_TYPE_MAP` — no longer needed (definition uses NodeType directly)
- `_MISSION_TYPE_MAP` — no longer needed (blueprint_type IS WorkflowType)
- `_resolve_deps()` — no longer needed

Keep only `blueprint_to_workflow()`.

### Task 9.2: Remove Old Services

**Files to deprecate/remove:**
- `services/mission_service.py` → replaced by `blueprint_service.py`
- `services/mission_executor.py` → replaced by `run_service.py` + `UnifiedExecutor`
- `services/mission_planner.py` → absorbed into `blueprint_service.py`
- `services/graph_service.py` → replaced by `blueprint_service.py`
- `services/graph_executor.py` → replaced by `run_service.py` + `UnifiedExecutor`
- `services/dag_executor.py` → removed (strategy handles this)
- `services/flow/flow_service.py` → replaced by `blueprint_service.py`
- `services/task_executor.py` → removed (node_executor handles this)
- `services/decomposition_service.py` → absorbed into blueprint creation

**Files to keep (cross-cutting concerns):**
- `services/mission_analytics.py` → retarget to `run_id`
- `services/mission_cache.py` → rewrite for blueprints/runs
- `services/mission_errors.py` → keep, add blueprint/run error types
- `services/self_improvement.py` → retarget to `run_id`
- `services/improvement/` → retarget to `run_id`
- `services/learning_service.py` → retarget to `run_id`
- `services/feedback_synthesizer.py` → retarget to `run_id`

### Task 9.3: Unify Event Types

**File:** `backend/app/models/substrate_models.py`

Rename event types (cosmetic — data already stored as strings):

```python
class SubstrateEventType:
    # Run lifecycle (was MISSION_*)
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_ABORTED = "run.aborted"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    
    # Node lifecycle (was TASK_*)
    NODE_STARTED = "node.started"
    NODE_COMPLETED = "node.completed"
    NODE_FAILED = "node.failed"
    NODE_RETRYING = "node.retrying"
    NODE_SKIPPED = "node.skipped"
    
    # Keep existing (no rename needed)
    LLM_CALL = "llm.call"
    LLM_RESPONSE = "llm.response"
    TOOL_CALL = "tool.call"
    TOOL_RESPONSE = "tool.response"
    CHECKPOINT = "substrate.checkpoint"
    BUDGET_EXHAUSTED = "substrate.budget_exhausted"
    ERROR = "substrate.error"
    HUMAN_INTERRUPT_RAISED = "human_interrupt.raised"
    HUMAN_INTERRUPT_RESOLVED = "human_interrupt.resolved"
    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker.triggered"
    CIRCUIT_BREAKER_BROKEN = "circuit_breaker.broken"
    CIRCUIT_BREAKER_RESET = "circuit_breaker.reset"
    
    # Backward compat aliases (deprecated)
    MISSION_STARTED = RUN_STARTED
    MISSION_COMPLETED = RUN_COMPLETED
    MISSION_FAILED = RUN_FAILED
    MISSION_ABORTED = RUN_ABORTED
    TASK_STARTED = NODE_STARTED
    TASK_COMPLETED = NODE_COMPLETED
    TASK_FAILED = NODE_FAILED
    TASK_RETRYING = NODE_RETRYING
    TASK_SKIPPED = NODE_SKIPPED
```

**CRITICAL: Event type string values must NOT change.** The plan renames the
Python constants (e.g., `MISSION_STARTED` → `RUN_STARTED`) but the string
values stored in the DB remain `"mission.started"`, `"task.started"`, etc.
This ensures existing events in `substrate_events` continue to match in
`SubstrateRunState.apply()` match/case blocks without a data migration.

```python
# The string values stay the same — only the Python constant names change
RUN_STARTED = "mission.started"     # NOT "run.started"
RUN_COMPLETED = "mission.completed" # NOT "run.completed"
NODE_STARTED = "task.started"       # NOT "node.started"
NODE_COMPLETED = "task.completed"   # NOT "task.completed"
# etc.
```

**If you want to also change the string values** (e.g., `"run.started"`),
you need a dual-match in `SubstrateRunState.apply()`:

```python
case "mission.started" | "run.started":
    self.status = "executing"
    self.started_at = event.timestamp
```

This dual-match approach is safer but adds complexity. Recommendation: keep
string values unchanged initially, change them in a later cleanup pass.

### Task 9.4: Update `ReplayEngine` for New Event Types

**File:** `backend/app/services/substrate/replay_engine.py`

The `SubstrateRunState.apply()` method in `substrate_models.py` needs to
handle the renamed events. Since we use backward compat aliases, this is
a no-op — the match/case already handles the string values.

### Task 9.5: Retarget Cross-Cutting Services

Update all services that reference `mission_id` to also accept `run_id`:

| Service | Current Key | New Key | Change |
|---------|-----------|---------|--------|
| `learning_service.py` | `mission_id` | `run_id` | Add `run_id` param |
| `self_improvement.py` | `mission_id` | `run_id` | Add `run_id` param |
| `analytics_service.py` | `mission_id` | `run_id` | Add `run_id` param |
| `episodic_memory_worker.py` | `mission_id` | `run_id` | Already has `run_id` |
| `circuit_breaker_service.py` | `mission_id` | `run_id` | Add `run_id` param |
| `cost_attribution_service.py` | `mission_id` | `run_id` | Add `run_id` param |
| `cost_engine.py` (observability) | `mission_id` | `run_id` | Add `run_id` param |
| `consolidation_worker.py` (memory) | `mission_id` | `run_id` | Add `run_id` param |
| `dashboard_service.py` | `mission_id` | `run_id` | Add `run_id` param |
| `subscription_service.py` | `mission_id` | `run_id` | Add `run_id` param; add `check_blueprint_create_allowed()` |
| `linear/sync.py` | `mission_id` | `run_id` | Add `run_id` param |

### Task 9.6: Retarget Triggers and Circuit Breakers

**File:** `backend/app/models/trigger_models.py`

`mission_triggers` → `blueprint_triggers`:
- Change FK from `mission_id` to `blueprint_id`
- Update trigger service to fire on blueprint/run events

**File:** `backend/app/models/circuit_breaker_models.py`

`mission_circuit_breakers` → `run_circuit_breakers`:
- Change FK from `mission_id` to `run_id`
- Circuit breaker is per-run, not per-blueprint

### Task 9.7: Retarget Mission Improvements

**File:** `backend/app/models/mission_models.py` (→ absorbed into `blueprint_models.py`)

`mission_improvements` — keep table, add `run_id` FK:

**Alembic migration:** `20260604_phase104_retarget_aux_tables.py`

```python
def upgrade():
    # mission_improvements: add run_id FK
    op.add_column('mission_improvements', sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index('ix_mission_improvements_run_id', 'mission_improvements', ['run_id'])
    op.create_foreign_key('fk_mission_improvements_run_id', 'mission_improvements', 'runs', ['run_id'], ['id'])

    # mission_triggers: add blueprint_id FK (keep mission_id for backward compat)
    op.add_column('mission_triggers', sa.Column('blueprint_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index('ix_mission_triggers_blueprint_id', 'mission_triggers', ['blueprint_id'])
    op.create_foreign_key('fk_mission_triggers_blueprint_id', 'mission_triggers', 'blueprints', ['blueprint_id'], ['id'])

    # mission_circuit_breakers: add run_id FK (keep mission_id for backward compat)
    op.add_column('mission_circuit_breakers', sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index('ix_mission_circuit_breakers_run_id', 'mission_circuit_breakers', ['run_id'])
    op.create_foreign_key('fk_mission_circuit_breakers_run_id', 'mission_circuit_breakers', 'runs', ['run_id'], ['id'])
```

**ORM model updates:**
- `MissionImprovement` — add `run_id: Mapped[str | None]` column
- `MissionCircuitBreaker` — add `run_id: Mapped[str | None]` column
- `MissionTrigger` — add `blueprint_id: Mapped[str | None]` column

During dual-write (Phase 5), populate both old and new FK columns.
During cleanup (Phase 7), drop old FK columns.

---

## 10. Phase 8 — Testing Strategy

### 10.1 Unit Tests (Per Phase)

| Phase | Test File | What to Test |
|-------|-----------|-------------|
| 1 | `test_blueprint_models.py` | ORM model creation, constraints, defaults |
| 2 | `test_blueprint_definition_schema.py` | Pydantic validation, serialization |
| 3 | `test_blueprint_service.py` | CRUD, versioning, publish/unpublish |
| 3 | `test_run_service.py` | Create from blueprint, execute, abort, retry |
| 4 | `test_blueprint_api.py` | All V2 endpoints, auth, pagination, filtering |
| 4 | `test_run_api.py` | All V2 endpoints, event stream, replay |
| 5 | `test_dual_write.py` | Mission create → blueprint created, execution → run created |
| 6 | `test_compat_views.py` | Old reads return correct data from views |
| 7 | `test_blueprint_to_workflow.py` | Adapter produces correct Workflow |

### 10.2 Integration Tests

**File:** `tests/integration/test_blueprint_run_lifecycle.py`

End-to-end test:
1. Create Blueprint (solo type)
2. Add nodes to definition
3. Publish Blueprint
4. Create Run from Blueprint
5. Execute Run → verify status transitions
6. Verify substrate_events contain correct run_id and blueprint_id
7. Replay run state → verify matches final state
8. Retry run → verify new run created
9. Diff two runs → verify comparison works

### 10.3 Migration Tests

**File:** `tests/integration/test_migration_blueprints_runs.py`

1. Apply Phase 1 migration → verify tables exist
2. Insert test data into old tables
3. Run backfill → verify data in new tables
4. Apply Phase 6 views → verify old reads still work
5. Apply Phase 6 drop → verify new reads work

---

## 11. Phase 9 — Frontend (Separate Deliverable)

**Duration:** 3–4 sprints  
**Prerequisite:** Backend Phase 4 complete (V2 API available)

### Task 9.1: Blueprint List Page

**Route:** `/blueprints`  
**Components:**
- `BlueprintList` — filterable grid/table
- `BlueprintCard` — shows type, status, run_count, last_run_at
- `BlueprintFilters` — type dropdown, status filter, search

### Task 9.2: Blueprint Editor

**Route:** `/blueprints/:id/edit`  
**Components:**
- `BlueprintEditor` — unified editor that switches mode based on `blueprint_type`:
  - `solo` → Mission builder (plan + tasks)
  - `dag` → DAG builder
  - `graph` → ReactFlow graph editor (reuse existing)
  - `swarm` → Swarm configuration
  - `pipeline` → Pipeline phase editor
- `BlueprintDefinitionPanel` — JSON editor for advanced users
- `BlueprintVersionHistory` — side panel showing versions

### Task 9.3: Run List Page

**Route:** `/runs`  
**Components:**
- `RunList` — table with status badges, cost, duration
- `RunFilters` — status filter, blueprint filter, date range

### Task 9.4: Run Detail Page

**Route:** `/runs/:id`  
**Components:**
- `RunTimeline` — visual timeline of substrate events
- `RunNodeStates` — per-node status with expandable details
- `RunCostBreakdown` — token/cost accumulation over time
- `RunReplay` — time-travel slider (select sequence → see state)
- `RunDiff` — side-by-side comparison with another run

### Task 9.5: Route Migration

- `/missions` → redirect to `/blueprints?type=solo`
- `/missions/builder` → redirect to `/blueprints/new?type=solo`
- `/graphs` → redirect to `/blueprints?type=graph`

---

## 12. Execution Order & Dependencies

```
Phase 0: Pre-work ─────────────────────────────┐
   │                                            │
Phase 1: New tables ────────────────────────────┤
   │                                            │
Phase 2: Definition schema ─────────────────────┤ (can parallel with Phase 1)
   │                                            │
Phase 3: Service layer ─────────────────────────┤ (depends on Phase 1 + 2)
   │                                            │
Phase 4: API layer ─────────────────────────────┤ (depends on Phase 3)
   │                                            │
Phase 5: Dual-write ────────────────────────────┤ (depends on Phase 4)
   │      │                                     │
   │      ├─ 2-week soak ──────────────────────►│
   │                                            │
Phase 6: Cut over ──────────────────────────────┤ (depends on Phase 5 soak)
   │                                            │
Phase 7: Cleanup ───────────────────────────────┘ (depends on Phase 6)
   │
Phase 8: Testing (continuous across all phases)
   │
Phase 9: Frontend (after Phase 4)
```

**Parallelizable work:**
- Phase 1 (schema) and Phase 2 (definition schema) can run in parallel
- Phase 8 (testing) runs continuously alongside all phases
- Phase 9 (frontend) can start as soon as Phase 4 delivers V2 API

---

## 13. Risk Register

| # | Risk | Likelihood | Impact | Mitigation | Phase |
|---|------|-----------|--------|------------|-------|
| R1 | Migration breaks existing in-flight runs | Medium | High | Phase 0 integration tests; dual-write ensures old path still works | 0-5 |
| R2 | 78-file import refactor causes regressions | High | High | Don't refactor imports until Phase 7; keep old models as aliases | 7 |
| R3 | Dual-write inconsistency (mission ≠ blueprint) | Medium | Medium | Consistency verification script; monitoring dashboard | 5 |
| R4 | Performance regression on unified `runs` table | Low | Medium | Index strategy; partition by `created_at` when >1M rows | 1, 6 |
| R5 | `substrate_events` FK migration blocks writes | Low | High | Add FK as nullable; backfill in background; test on staging | 1 |
| R6 | Old API consumers break during deprecation | Medium | Low | Deprecation headers + 3-month sunset period; compat views | 5-6 |
| R7 | Frontend rewrite scope creep | Medium | Medium | Phase frontend changes; keep old routes working via redirects | 9 |

---

## 14. Success Metrics

| Metric | Before | Target After |
|--------|--------|-------------|
| Execution-related tables | 14 | 4 + substrate_events |
| Concepts for "executable work" | 5 | 2 (Blueprint + Run) |
| Adapter functions | 3 (mission_to, flow_to, graph_to) | 1 (blueprint_to) |
| API surface for execution | 3 separate (missions, graphs, flow) | 1 unified (blueprints + runs) |
| Time to add new execution type | ~2 days (new table + service + API + adapter) | ~2 hours (add new `blueprint_type`) |
| Frontend pages for execution | 2 (missions, graphs) | 2 (blueprints, runs) — but unified |

---

## Appendix A: File Change Summary

### New Files (17)

| File | Phase | Purpose |
|------|-------|---------|
| `models/blueprint_models.py` | 1 | Blueprint, Run, BlueprintVersion ORM models |
| `schemas/blueprint.py` | 2 | Pydantic request/response schemas |
| `services/blueprint_service.py` | 3 | Blueprint CRUD + version logic |
| `services/run_service.py` | 3 | Run lifecycle management |
| `api/_blueprint_cqrs/__init__.py` | 4 | Package init |
| `api/_blueprint_cqrs/commands.py` | 4 | Blueprint mutation handlers |
| `api/_blueprint_cqrs/queries.py` | 4 | Blueprint read handlers |
| `api/_blueprint_cqrs/deps.py` | 4 | FastAPI DI |
| `api/_blueprint_cqrs/base.py` | 4 | Shared base classes |
| `api/_blueprint_cqrs/errors.py` | 4 | Custom error types |
| `api/v2/blueprints.py` | 4 | V2 Blueprint API routes |
| `api/v2/runs.py` | 4 | V2 Run API routes |
| `scripts/backfill_blueprints_runs.py` | 5 | Data migration script |
| `scripts/verify_backfill_consistency.py` | 5 | Consistency verification |
| `alembic/versions/20260604_phase101_blueprints_runs.py` | 1 | Create tables migration |
| `alembic/versions/20260604_phase102_compat_views.py` | 6 | Compat views migration |
| `alembic/versions/20260604_phase103_drop_old_tables.py` | 6 | Drop old tables migration |

### Modified Files (12)

| File | Phase | Change |
|------|-------|--------|
| `models/__init__.py` | 1 | Register new models |
| `services/substrate/adapters.py` | 2, 7 | Add `blueprint_to_workflow()` (Ph2), remove old adapters (Ph7) |
| `services/substrate/executor.py` | 3 | Accept `blueprint_id` param |
| `services/substrate/event_log.py` | 3 | Accept `blueprint_id` param |
| `models/substrate_models.py` | 7 | Rename event types, add aliases |
| `services/substrate/replay_engine.py` | 7 | Handle renamed event types |
| `api/_mission_cqrs/commands.py` | 5 | Dual-write to blueprints + runs |
| `api/v1/mission.py` | 5, 6 | Deprecation headers (Ph5), switch reads (Ph6) |
| `api/v1/graph.py` | 5, 6 | Deprecation headers (Ph5), switch reads (Ph6) |
| `main_fastapi.py` | 4 | Register V2 routers |
| `services/learning_service.py` | 7 | Accept `run_id` |
| `services/self_improvement.py` | 7 | Accept `run_id` |

### Deprecated Files (8, removed in Phase 7)

| File | Replacement |
|------|-------------|
| `services/mission_service.py` | `services/blueprint_service.py` |
| `services/mission_executor.py` | `services/run_service.py` |
| `services/mission_planner.py` | Absorbed into `blueprint_service.py` |
| `services/graph_service.py` | `services/blueprint_service.py` |
| `services/graph_executor.py` | `services/run_service.py` |
| `services/dag_executor.py` | Removed (strategy handles) |
| `services/flow/flow_service.py` | `services/blueprint_service.py` |
| `services/task_executor.py` | Removed (node_executor handles) |

---

## Appendix B: `Blueprint.definition` JSONB Schema

The `definition` column stores the exact same structure that `Workflow` Pydantic
model expects, minus runtime fields:

```json
{
  "blueprint_type": "solo",
  "title": "Analyze customer feedback",
  "description": "Read feedback CSV, extract themes, generate report",
  "nodes": [
    {
      "id": "node_1",
      "type": "llm_call",
      "title": "Extract themes",
      "description": "Analyze the feedback and extract top 5 themes",
      "config": {
        "prompt": "Analyze the following customer feedback...",
        "model": "gpt-4o"
      },
      "dependencies": [],
      "assigned_model": "gpt-4o",
      "max_retries": 3,
      "fallback_strategy": "human_escalate"
    },
    {
      "id": "node_2",
      "type": "llm_call",
      "title": "Generate report",
      "description": "Create a markdown report from the themes",
      "config": {
        "prompt": "Create a report from these themes..."
      },
      "dependencies": ["node_1"],
      "assigned_model": "gpt-4o",
      "max_retries": 3
    }
  ],
  "edges": [
    {
      "source": "node_1",
      "target": "node_2"
    }
  ],
  "budget": {
    "max_cost_usd": 5.00,
    "max_wall_time_seconds": 120,
    "max_iterations": 10,
    "max_depth": 3
  },
  "config": {
    "fallback_strategy": "human_escalate",
    "model_preference": "gpt-4o"
  }
}
```

---

## Appendix C: `Run.snapshot` Immutability Contract

The `snapshot` is copied from `Blueprint.definition` at `Run` creation time.
Once the `Run` status transitions out of `pending`, the `snapshot` MUST NOT be
modified. This is enforced at the application level (not DB level):

```python
async def create_from_blueprint(self, blueprint_id, user_id, input_data=None):
    blueprint = await self.db.get(Blueprint, blueprint_id)
    
    # Build snapshot from current blueprint definition
    snapshot = {
        "blueprint_type": blueprint.blueprint_type,
        "title": blueprint.title,
        "description": blueprint.description,
        **blueprint.definition,  # nodes, edges, budget, config
    }
    
    run = Run(
        blueprint_id=blueprint_id,
        user_id=user_id,
        status="pending",
        snapshot=snapshot,  # Immutable copy
        input_data=input_data,
    )
    self.db.add(run)
    await self.db.flush()
    return run
```

This contract enables:
1. **Deterministic replay** — replay the same snapshot, get the same execution
2. **Audit trail** — know exactly what was executed, even if blueprint changed
3. **Blueprint evolution** — change blueprint without affecting past runs
4. **Run diffing** — compare two runs of the same blueprint across versions

---

## Appendix D: Migration Rollback Plan

### Phase 1 Rollback
```bash
alembic downgrade h2_substrate_init  # Reverts to pre-Phase 1 state
```
No data loss — new tables were empty.

### Phase 5 Rollback
1. Stop dual-write (deploy code without dual-write)
2. New tables contain backfilled data — safe to truncate
3. Old tables untouched — everything still works

### Phase 6 Rollback
**⚠️ Phase 6 drop migration has no downgrade.** If issues are found after
dropping old tables:
1. Restore from backup taken immediately before Phase 6 migration
2. Re-deploy code that reads from old tables
3. Investigate and fix before re-attempting

**Recommendation:** Keep the database backup for 30 days after Phase 6.
