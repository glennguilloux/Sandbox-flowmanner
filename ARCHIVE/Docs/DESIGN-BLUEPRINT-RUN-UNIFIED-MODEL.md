# Design Doc: Blueprint + Run Unified Model

**Status:** DRAFT
**Date:** 2026-06-03
**Author:** Hermes Agent (based on codebase audit)
**Scope:** Backend models, services, API, frontend pages

---

## 1. Problem Statement

FlowManner has **5 overlapping concepts** for "a unit of executable work":

| Concept | ORM Table | What It Represents |
|---------|-----------|-------------------|
| Mission | `missions` + `mission_tasks` | A goal decomposed into tasks, executed by an agent |
| Workflow (Graph) | `workflows` + `workflow_executions` + `workflow_states` | A visual graph of nodes with edges, executed |
| Flow | Same `workflows` table (FlowService) | Alias for a Workflow used by `/flow/run` |
| OrchestratorExecution | `orchestrator_executions` + `orchestrator_tasks` | A swarm goal decomposed into agent tasks |
| SwarmPipeline | `swarm_pipelines` | A phased pipeline execution for swarms |

Plus 3 auxiliary tables:
- `substrate_events` — event-sourced log (run_id keyed)
- `execution_events` — append-only log per workflow execution
- `mission_logs` — text log per mission

**This causes:**
- Users cannot answer: "What is the primary thing I create and run?"
- Adapters exist (`substrate/adapters.py`) to convert ALL of these into one `Workflow` Pydantic model before execution
- The `UnifiedExecutor` already treats everything as `Workflow` internally
- But the DB and API still expose 5 different shapes
- Frontend has separate `/missions` and `/graphs` pages for what is the same conceptual action

**The core insight:** The codebase already solved this problem at the execution layer (`workflow_models.py` + `UnifiedExecutor`). The gap is that the DB schema, API, and UI still expose the old fragmented concepts.

---

## 2. Target Model

### Two Core Objects

```
Blueprint  =  Reusable definition of work
Run        =  One execution instance of a Blueprint
```

Everything else becomes a property, a projection, or implementation detail.

### 2.1 Blueprint

A Blueprint is a **reusable, versioned definition** of executable work.

**Merges:**
- `missions` (Mission) — the plan, constraints, context
- `workflows` (Workflow/Graph) — the graph_definition
- `mission_templates` — the reusable template concept
- `mission_versions` — the version snapshot

**Target table:** `blueprints`

```python
class Blueprint(Base, TimestampMixin):
    __tablename__ = "blueprints"

    id: Mapped[str] = mapped_column(UUID, primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(UUID, FK("workspaces.id"))
    user_id: Mapped[int] = mapped_column(Integer, FK("users.id"))

    # Identity
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")

    # Definition
    blueprint_type: Mapped[str] = mapped_column(String(50))
    # Values: "solo" | "dag" | "swarm" | "pipeline" | "graph" | "meta" | "langgraph"
    # Maps 1:1 to existing WorkflowType enum

    definition: Mapped[dict] = mapped_column(JSONB)
    # Unified structure: {nodes: [...], edges: [...], config: {...}}
    # Replaces: mission.plan, workflow.graph_definition, constraints, context_files

    input_schema: Mapped[dict | None] = mapped_column(JSONB)
    output_schema: Mapped[dict | None] = mapped_column(JSONB)

    # Lifecycle
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # Values: "draft" | "published" | "deprecated"
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Metadata
    tags: Mapped[list | None] = mapped_column(JSONB)
    category: Mapped[str | None] = mapped_column(String(100))
    icon: Mapped[str | None] = mapped_column(String(50))

    # Usage stats (denormalized, updated periodically)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

**Key decisions:**
- `blueprint_type` is a string, not an enum, to allow future types without migration
- `definition` is a single JSONB column that replaces `plan`, `graph_definition`, `constraints`, and `context_files`
- The structure of `definition` mirrors the existing `Workflow` Pydantic model from `workflow_models.py`
- Versioning is handled by a separate `blueprint_versions` table (same pattern as current `mission_versions` / `workflow_versions`)

### 2.2 Run

A Run is a **single execution instance** of a Blueprint.

**Merges:**
- `mission_tasks` (MissionTask) — individual task states during execution
- `workflow_executions` (WorkflowExecution) — the execution record
- `workflow_states` (WorkflowState) — per-node state
- `orchestrator_executions` + `orchestrator_tasks` — swarm execution state
- `swarm_pipelines` — pipeline execution state
- `substrate_events` — remains the source of truth for event sourcing
- `execution_events` — absorbed into substrate_events
- `mission_logs` — absorbed into substrate_events

**Target table:** `runs`

```python
class Run(Base, TimestampMixin):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(UUID, primary_key=True)
    blueprint_id: Mapped[str | None] = mapped_column(
        UUID, FK("blueprints.id", ondelete="SET NULL")
    )
    workspace_id: Mapped[str | None] = mapped_column(UUID, FK("workspaces.id"))
    user_id: Mapped[int | None] = mapped_column(Integer, FK("users.id"))

    # Execution state
    status: Mapped[RunStatus] = mapped_column(String(20), default="pending", index=True)
    # Values: "pending" | "queued" | "executing" | "paused" |
    #         "completed" | "failed" | "aborted"

    # Snapshot of blueprint definition AT RUN TIME (immutable once started)
    # This is critical: if the blueprint changes later, the run preserves what was executed
    snapshot: Mapped[dict] = mapped_column(JSONB)
    # Structure: {blueprint_type, nodes, edges, config, budget, ...}
    # Copied from Blueprint.definition when run is created

    # Results
    output_data: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Budget tracking
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    budget_limit_usd: Mapped[float | None] = mapped_column(Float)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Parent/child for sub-runs
    parent_run_id: Mapped[str | None] = mapped_column(UUID, FK("runs.id"))

    # Context
    input_data: Mapped[dict | None] = mapped_column(JSONB)
    # Runtime overrides, user-provided inputs, environment variables

    # Metadata
    meta: Mapped[dict | None] = mapped_column(JSONB)
    # Agent IDs used, model IDs, integration configs, etc.
```

**Key decisions:**
- `snapshot` is immutable after run creation — this is what enables deterministic replay
- `blueprint_id` is nullable (SET NULL on delete) — runs survive blueprint deletion
- `parent_run_id` enables sub-workflows (the existing `SUB_WORKFLOW` NodeType)
- The `substrate_events` table gains a `run_id` FK (it already has `run_id` as a UUID column)

### 2.3 Substrate Event (Modified)

The existing `substrate_events` table already has the right shape. Changes are minimal:

```python
class SubstrateEvent(Base):
    __tablename__ = "substrate_events"  # unchanged

    # ... existing columns unchanged ...

    # ADD:
    blueprint_id: Mapped[str | None] = mapped_column(
        UUID, FK("blueprints.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Replace mission_id FK with run_id FK (run_id already exists as UUID, add FK constraint)
```

The `SubstrateRunState` in-memory projection stays the same — it already operates on `run_id`.

---

## 3. What Gets Removed / Deprecated

### Tables deprecated (kept as views for migration):

| Old Table | Fate | Migration |
|-----------|------|-----------|
| `missions` | View → `blueprints` + `runs` | Data migration script |
| `mission_tasks` | Absorbed into `substrate_events` (run_id keyed) | Data migration |
| `mission_logs` | Absorbed into `substrate_events` | Data migration |
| `mission_improvements` | Keep, add `run_id` FK | Schema migration |
| `mission_templates` | Absorbed into `blueprints` (status='published') | Data migration |
| `mission_versions` | Replaced by `blueprint_versions` | Data migration |
| `workflows` | View → `blueprints` | Data migration |
| `workflow_executions` | View → `runs` | Data migration |
| `workflow_states` | Absorbed into `substrate_events` | Data migration |
| `workflow_versions` | Replaced by `blueprint_versions` | Data migration |
| `execution_events` | Absorbed into `substrate_events` | Data migration |
| `orchestrator_executions` | View → `runs` | Data migration |
| `orchestrator_tasks` | Absorbed into `substrate_events` | Data migration |
| `swarm_pipelines` | View → `runs` | Data migration |
| `node_groups` | Keep (used by mission builder UI) | Unchanged |

### Tables kept as-is:

| Table | Reason |
|-------|--------|
| `substrate_events` | Source of truth — minimal changes |
| `agents` | Capability carriers, not execution concepts |
| `swarm_profiles`, `swarm_agents` | Team composition, not execution |
| `mission_triggers` | Keep, retarget to `blueprints` |
| `mission_circuit_breakers` | Keep, retarget to `runs` |
| `inbox_items` (HITL) | Keep, already keyed by run_id |

---

## 4. API Changes

### 4.1 New Endpoints

```
POST   /api/v2/blueprints          Create a blueprint
GET    /api/v2/blueprints          List blueprints (workspace-scoped)
GET    /api/v2/blueprints/:id      Get blueprint details
PATCH  /api/v2/blueprints/:id      Update blueprint (creates new version)
DELETE /api/v2/blueprints/:id      Soft-delete blueprint
POST   /api/v2/blueprints/:id/run  Create and start a run from blueprint

GET    /api/v2/runs                List runs (workspace-scoped)
GET    /api/v2/runs/:id            Get run details + current state
POST   /api/v2/runs/:id/abort      Abort a running run
POST   /api/v2/runs/:id/retry      Retry a failed run
GET    /api/v2/runs/:id/events     Get substrate event stream
GET    /api/v2/runs/:id/replay     Replay run state at sequence N
GET    /api/v2/runs/:id/diff       Diff two runs of same blueprint
```

### 4.2 Backward Compatibility

The old endpoints remain functional through DB views:

```
# These continue to work — they read from views that map old tables → new tables
GET  /api/v1/missions           → reads from blueprints + runs views
POST /api/v1/missions           → creates blueprint + starts run
GET  /api/v1/graphs             → reads from blueprints view (type='graph')
POST /api/v1/flow/run           → creates blueprint + starts run
```

The adapter layer (`substrate/adapters.py`) is inverted. Currently it converts old models → `Workflow`. In the new model, the `Blueprint` IS a `Workflow` — the adapter becomes trivial.

### 4.3 Frontend Routes

Current:
```
/missions          → Mission list
/missions/builder  → Mission builder (plan tasks)
/graphs            → Graph editor
```

Target:
```
/blueprints           → Blueprint list (unified, filterable by type)
/blueprints/new       → Create blueprint (choose type: solo/dag/graph/swarm)
/blueprints/:id       → Blueprint detail (definition + version history)
/blueprints/:id/edit  → Edit blueprint definition
/runs                 → Run list (all executions, filterable by status)
/runs/:id             → Run detail (timeline, events, replay, diff)
```

The mission builder and graph editor become **edit modes** within the blueprint editor, chosen by `blueprint_type`.

---

## 5. Migration Strategy

### Phase 0: Pre-work (No schema changes)

1. Ensure `UnifiedExecutor` is the ONLY execution path
2. Audit all callers of old executors — confirm they route through `UnifiedExecutor`
3. Add integration tests that exercise: create mission → adapt → execute → verify events

### Phase 1: New Tables + Views (Parallel operation)

1. Create `blueprints` and `runs` tables via Alembic migration
2. Create `blueprint_versions` table
3. Create PostgreSQL views named after old tables:
   - `missions` view → `SELECT ... FROM blueprints JOIN runs`
   - `workflows` view → `SELECT ... FROM blueprints WHERE blueprint_type IN ('graph','dag')`
   - `workflow_executions` view → `SELECT ... FROM runs`
   - `orchestrator_executions` view → `SELECT ... FROM runs WHERE blueprint_type IN ('swarm','pipeline')`
4. Old ORM models point to views instead of tables
5. New code writes to new tables; old code reads from views

### Phase 2: Dual-Write (Transition period)

1. All new creates go through new API → new tables
2. Background job backfills existing data from old tables → new tables
3. Run in dual-write for 2 weeks, verify consistency
4. Old API endpoints redirect to new ones with deprecation headers

### Phase 3: Cut Over

1. Switch all reads to new tables
2. Drop views
3. Drop old tables (after verified backup)
4. Update frontend routes

### Phase 4: Cleanup

1. Remove old adapters (`substrate/adapters.py` — the `mission_to_workflow` etc. functions)
2. Remove old services that only existed for old models
3. Unify the 3 event tables into `substrate_events` only

---

## 6. Impact on Substrate

### Current State (Already Built)

```
UnifiedExecutor.execute()
  → takes Workflow (Pydantic model)
  → emits SubstrateEvents
  → ReplayEngine rebuilds SubstrateRunState from events
```

### After Blueprint + Run

```
UnifiedExecutor.execute()
  → takes Blueprint (ORM model, same shape as Workflow)
  → creates Run (ORM model)
  → emits SubstrateEvents (with run_id FK)
  → ReplayEngine rebuilds RunState from events
```

**The change is minimal at the execution layer.** The `Workflow` Pydantic model in `workflow_models.py` already IS the right shape. The `Blueprint.definition` column stores the same JSONB structure. The `mission_to_workflow()` adapter becomes:

```python
def blueprint_to_workflow(blueprint: Blueprint, snapshot: dict) -> Workflow:
    """Trivial: the snapshot IS the Workflow."""
    return Workflow(
        id=str(blueprint.id),
        type=WorkflowType(snapshot["blueprint_type"]),
        title=blueprint.title,
        description=blueprint.description,
        nodes=[WorkflowNode(**n) for n in snapshot["nodes"]],
        edges=[WorkflowEdge(**e) for e in snapshot.get("edges", [])],
        budget=Budget(**snapshot.get("budget", {})),
        user_id=str(blueprint.user_id),
        metadata=snapshot.get("config", {}),
    )
```

---

## 7. Impact on Other Systems

### 7.1 Learning / Improvement

Current: `learning_service` records against `mission_id`
After: Records against `run_id` — more precise, connects learning to specific executions

### 7.2 HITL (Human-in-the-Loop)

Current: `inbox_items` already keyed by execution context
After: Direct `run_id` FK — cleaner

### 7.3 Analytics

Current: `analytics_events` and `mission_analytics` service keyed by mission
After: Keyed by `run_id` — enables per-run cost analysis, success rates by blueprint version

### 7.4 Triggers

Current: `mission_triggers` fire when a mission event occurs
After: `blueprint_triggers` — "when a run of blueprint X completes, start run of blueprint Y"

### 7.5 Marketplace

Current: Listings reference agents, tools, templates
After: Listings can reference **Blueprints** — "install this blueprint" becomes meaningful. This is where marketplace eventually makes sense.

### 7.6 Nexus

Current: `nexus/meta_loop_orchestrator.py` orchestrates multi-agent loops
After: Creates a Run with `blueprint_type='meta'` — same path

---

## 8. What This Unlocks

### 8.1 Replay UX

Every Run has a complete event stream. Frontend can render:
- Timeline of all state transitions
- Per-node execution timeline
- Cost/token accumulation over time
- "What was the state at sequence 42?" (time-travel debugging)

### 8.2 Run Diffing

Compare two Runs of the same Blueprint:
- Which nodes succeeded in both? Which diverged?
- Cost difference
- Which model was used? Did it matter?
- "Run A with GPT-4 succeeded at node 5 but Run B with Claude failed — why?"

### 8.3 Blueprint Evolution

Version history of Blueprint definitions:
- "How did this blueprint change over time?"
- "Did run success rate improve after version 3?"
- Rollback to any version

### 8.4 Self-Improvement Loop

With Runs as first-class objects:
- System analyzes failed Runs → generates improvement suggestions
- Suggestions applied to Blueprint → new version
- Compare success rates across versions
- **Learning becomes visible and measurable**

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Migration breaks existing runs | Medium | High | Phase 0 tests; views for backward compat |
| Performance regression on unified table | Low | Medium | Proper indexes; partition runs by created_at |
| Frontend rewrite too large | Medium | Medium | Phase frontend changes; keep old routes working via views |
| Concept confusion during transition | Medium | Low | Clear naming; don't ship both concepts simultaneously |
| Existing substrate_events FK constraints | Low | High | Test FK migration on staging data first |

---

## 10. Table Count Impact

**Before:** 14 execution-related tables
**After:** 4 tables + substrate_events

| Table | Purpose |
|-------|---------|
| `blueprints` | Reusable definitions |
| `blueprint_versions` | Version snapshots |
| `runs` | Execution instances |
| `node_groups` | Mission builder UI groups |
| `substrate_events` | Event source of truth (unchanged) |

---

## 11. Files That Change

### New files:
- `backend/app/models/blueprint_models.py` — Blueprint + Run + BlueprintVersion ORM models
- `backend/app/schemas/blueprint.py` — Pydantic request/response schemas
- `backend/app/api/v2/blueprints.py` — Blueprint API routes
- `backend/app/api/v2/runs.py` — Run API routes
- `backend/app/services/blueprint_service.py` — Blueprint CRUD + version logic
- `backend/app/services/run_service.py` — Run lifecycle management
- `backend/alembic/versions/xxx_create_blueprints_runs.py` — Migration

### Modified files:
- `backend/app/services/substrate/adapters.py` — Simplify to trivial mapping
- `backend/app/services/substrate/executor.py` — Accept Run context alongside Workflow
- `backend/app/services/substrate/workflow_models.py` — Add `from_blueprint()` classmethod
- `backend/app/models/__init__.py` — Register new models
- `backend/app/services/mission_service.py` — Deprecate, redirect to blueprint_service
- `backend/app/services/graph_service.py` — Deprecate, redirect to blueprint_service
- `backend/app/services/flow/flow_service.py` — Deprecate, redirect to blueprint_service

### Frontend (separate repo):
- New: `src/app/[locale]/(dashboard)/blueprints/` pages
- New: `src/app/[locale]/(dashboard)/runs/` pages
- New: `src/components/blueprint-editor/` (unified builder + graph editor)
- Deprecated: `src/app/[locale]/(dashboard)/missions/`
- Deprecated: `src/app/[locale]/(dashboard)/graphs/`
- New: `src/stores/blueprint-store.ts`, `src/stores/run-store.ts`

---

## 12. Open Questions

1. **Should `definition` use the exact `Workflow` Pydantic shape or a simplified version?**
   The `Workflow` model has runtime fields (`status`, `output_data`, `retry_count` on nodes). The Blueprint definition should only contain the declarative parts. Proposal: separate `BlueprintDefinition` Pydantic model for storage, convert to `Workflow` at execution time.

2. **Should `runs` be range-partitioned by `created_at`?**
   Runs are append-heavy, read-recent. Partitioning would help at scale. Proposal: defer until >1M runs.

3. **How to handle in-flight runs during migration?**
   In-flight runs have active `substrate_events` being written. The `run_id` column already exists in `substrate_events` and is independent of any FK. Proposal: migrate schema first, then backfill FKs in a background job.

4. **Should the old `/missions` and `/graphs` frontend routes redirect or coexist?**
   Proposal: redirect with a toast notification ("Missions are now Blueprints"). Coexistence creates confusion.

---

## Appendix A: Current Table → New Table Mapping

```
missions                    → blueprints (type-based rows) + runs (one per execution)
mission_tasks               → runs.snapshot.nodes + substrate_events (task.* events)
mission_logs                → substrate_events (level field in payload)
mission_improvements        → mission_improvements (add run_id FK)
mission_templates           → blueprints (status='published')
mission_versions            → blueprint_versions
mission_triggers            → blueprint_triggers (FK change)
mission_circuit_breakers    → run_circuit_breakers (FK change)

workflows                   → blueprints (blueprint_type IN ('graph', 'dag'))
workflow_executions         → runs
workflow_states             → substrate_events (per-node state in task events)
workflow_versions           → blueprint_versions
execution_events            → substrate_events (absorbed)

orchestrator_executions     → runs (blueprint_type IN ('swarm', 'pipeline'))
orchestrator_tasks          → runs.snapshot.nodes + substrate_events

swarm_pipelines             → runs (blueprint_type='pipeline')
```

## Appendix B: SubstrateEvent Types After Migration

The existing `SubstrateEventType` enum stays the same but is conceptually reorganized:

```
Run lifecycle:   run.started, run.completed, run.failed, run.aborted, run.paused, run.resumed
Node lifecycle:  node.started, node.completed, node.failed, node.retrying, node.skipped
LLM:             llm.call, llm.response
Tool:            tool.call, tool.response
HITL:            human_interrupt.raised, human_interrupt.resolved
Circuit breaker: circuit_breaker.triggered, circuit_breaker.broken, circuit_breaker.reset
System:          substrate.checkpoint, substrate.budget_exhausted, substrate.error
```

Renaming `MISSION_*` → `RUN_*` is cosmetic and can happen in Phase 3.
