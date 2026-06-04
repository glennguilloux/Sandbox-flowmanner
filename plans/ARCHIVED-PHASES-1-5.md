# Postgres-Native Migration — Session Handoff

> **Last updated:** 2026-06-08
> **Current phase:** Phase 5 COMPLETE ✅ | Phase 6 IN PROGRESS | Phase 7.4 PARTIAL

---

## Phase 1 Status: ✅ COMPLETE

### What was built

| Item | Status | Files |
|------|--------|-------|
| **1.1a** Tools catalog + versions | ✅ Done | `app/models/tool_catalog_models.py`, `alembic/versions/20260603_tools_capabilities.py` |
| **1.1b** Capabilities catalog + versions | ✅ Done | `app/models/capability_catalog_models.py` (same migration) |
| **1.1c** Agent template canonicalization | ✅ Done | slug/version/source/definition columns + `agent_template_versions` table |
| **1.1d** Unified memory (memory_entries) | ✅ Done | `app/models/memory_models.py`, `app/services/memory_service.py` (Postgres-first) |
| **1.1e** Materialization state table | ✅ Done | `app/models/materialization_models.py`, `alembic/versions/20260603_materialization_state.py` |
| **1.1f** Topology tables | ✅ Done | `app/models/topology_models.py`, `alembic/versions/20260603_topology.py` |
| **1.2** Builtin importers | ✅ Done | `scripts/import_builtin_tools.py`, `import_builtin_capabilities.py`, `import_agent_templates.py` |
| **1.3** Memory service rewrite | ✅ Done | Postgres-first writes, Redis as optional cache |
| **1.4** Startup refactor | ✅ Done | `app/lifespan.py` — hydration from DB with Python fallback |
| **1.5** Disaster recovery test | ✅ Done | `tests/test_disaster_recovery.py` — 22/22 passing |

### DB Population (import scripts already run)

```
tools_catalog:            110 rows
tool_versions:            110 rows
capabilities_catalog:     299 rows
capability_versions:      299 rows
agent_templates:          299 rows (289 markdown + 10 Python)
agent_template_versions:  245 rows
```

### Key fixes applied during implementation

1. `:param::jsonb` → `CAST(:param AS jsonb)` in all SQL `text()` queries (SQLAlchemy parameter binding conflict)
2. `datetime.now(timezone.utc).isoformat()` → `datetime.now(timezone.utc)` (asyncpg needs datetime objects)
3. Test patch targets: `app.database.AsyncSessionLocal` (not `app.lifespan.AsyncSessionLocal`)
4. `check_memory_service()` is async — must use `await` in `run_all()`
5. DR test uses TCP socket for DB reachability (avoids event loop conflicts)

---

## Phase 2: Registry Replacement — ✅ COMPLETE

**Goal:** Replace singleton registries with DB-derived projections.

### 2.1 ToolRegistry Hydration Pipeline ✅

**File:** `app/tools/base.py`

Added `resolve_handler_ref()` shared utility + `ToolRegistry.hydrate_from_db(session)` method + `_resolve_handler()` static method. `lifespan._hydrate_tools_from_db()` now delegates to `registry.hydrate_from_db(session)`.

### 2.2 CapabilityRegistry Hydration Pipeline ✅

**File:** `app/services/nexus/capability_registry.py`

Added `CapabilityRegistry.hydrate_from_db(session)` with passthrough handler fallback + `_resolve_handler()` delegating to shared utility. `lifespan._hydrate_capabilities_from_db()` now delegates to `registry.hydrate_from_db(session)`.

### 2.3 Normalized Bindings ✅

**New files:**
- `app/models/binding_models.py` — `AgentToolBinding`, `AgentCapabilityBinding`, `CapabilityDependency`
- `alembic/versions/20260604_bindings.py` — migration with unique composite indexes + self-dep CHECK constraint
- `scripts/import_bindings.py` — idempotent script to populate bindings from `agent_templates.definition` JSONB
- `scripts/add_stub_tools.py` — adds 15 stub tools for agent template tool IDs not in catalog

**DB population:**
```
tools_catalog:            125 rows (110 builtin + 15 stubs)
tool_versions:            125 rows
agent_tool_bindings:      32 bindings (10 agents)
agent_capability_bindings: 0 (template cap strings don't match catalog slugs)
capability_dependencies:  0 (no dependency data source yet)
```

### 2.4 Topology from DB ✅

**File:** `app/services/semantic/topology_manager.py`

Added `TopologyManager.build_from_db(session)` — reads latest `topology_snapshots` row, falls back to filesystem `graph.json`. Added `save_snapshot(session)` for persisting topology. Fixed `build()` to accept both `links` and `edges` keys.

Added `_hydrate_topology_from_db()` to `lifespan.py` — loads topology from DB on startup.

Added `scripts/seed_topology.py` — seeds `topology_snapshots` from graph.json or synthetic data from agent_templates + tools_catalog + capabilities_catalog.

**DB population:**
```
topology_snapshots: 1 row (v1, 366 nodes, 32 edges, source=computed)
```

### 2.5 Qdrant as Rebuildable Index ✅

**Files modified:**
- `app/services/tool_discovery_service.py` — Added `reindex_from_db(session)` that reads from `tools_catalog` + `capabilities_catalog`, rebuilds Qdrant collection. Added `_build_search_text_from_row()` helper; `_build_search_text` now delegates to it.
- `app/api/v1/admin.py` — Added `POST /admin/reindex` endpoint with `source` param (`'db'` or `'registry'`), `Literal`-validated. Added `ReindexResponse` schema.

**Endpoint:** `POST /api/v1/admin/reindex?source=db` (admin auth required)

**Tests:** `backend/tests/test_reindex_from_db.py` — 5/5 passing

### 2.6 Workflow Model Cleanup ✅

**Files created:**
- `app/models/workflow_version_models.py` — `WorkflowVersion` (version snapshots, FK→workflows.id as UUID) + `ExecutionEvent` (append-only event log with sequence, event_type, level, node_id)
- `alembic/versions/20260605_workflow_versions.py` — migration creating both tables with UUID FKs, unique composite indexes on (workflow_id, version) and (execution_id, sequence)

**Status:** Table names already unified (workflows, workflow_executions, workflow_states). Graph* aliases kept as backward-compat. New tables empty and ready for data.

**Tests:** `backend/tests/test_workflow_version_models.py` — 12/12 passing

**DB population:**
```
workflow_versions: 0 rows (ready for data)
execution_events:  0 rows (ready for data)
workflows:         9 rows (existing)
workflow_executions: 2 rows (existing)
```

- Unify `project`/`flow`/`workflow` semantics
- Add `workflow_versions` table
- Add `execution_events` append-only table

### 2.7 Marketplace Normalization ✅

**Files modified/created:**
- `alembic/versions/20260605_marketplace.py` — Migration that adds `slug` column to `marketplace_categories`, adds `artifact_type`/`artifact_id`/`artifact_version_id` to `marketplace_listings`, normalizes freeform `category_id` values to FK IDs, adds FK constraint
- `app/models/models.py` — Added 3 new columns to `MarketplaceListingModel`

**DB state after migration:**
```
marketplace_categories: 5 rows (cat-ai, cat-automation, cat-data, cat-integration, cat-template)
marketplace_listings:   10 rows (all category_ids now valid FK values)
  artifact_type/artifact_id/artifact_version_id: ready for population
```

**Tests:** `backend/tests/test_marketplace_normalization.py` — 8/8 passing

- `marketplace_listings` gets `artifact_type` enum + `artifact_id` + `artifact_version_id`
- `category_id` becomes a proper FK to `marketplace_categories`

---

## Phase 3: Durable Agent OS (Months 3-6)

### 3.1 Entity Versioning ✅

**What was built:**

| Item | Status | Files |
|------|--------|-------|
| **Agent version column** | ✅ Done | `app/models/agent.py` — `version` column + `AgentVersion` model |
| **Workspace version column** | ✅ Done | `app/models/workspace_models.py` — `version` column + `WorkspaceVersion` model |
| **Mission version normalization** | ✅ Done | `app/models/mission_models.py` (version col), `mission_advanced_models.py` (version_number→version) |
| **Versioning service** | ✅ Done | `app/services/versioning.py` — `create_version_snapshot()`, `get_version_history()`, `get_version_snapshot()` |
| **Alembic migration** | ✅ Done | `alembic/versions/20260605_entity_versioning.py` |
| **Model registration** | ✅ Done | `app/models/__init__.py` — AgentVersion, WorkspaceVersion, MissionVersion imports |
| **Tests** | ✅ Done | `tests/test_entity_versioning.py` — 22/22 passing |

**DB state after migration:**
```
agent_versions:      0 rows (ready for data)
workspace_versions:  0 rows (ready for data)
mission_versions:    0 rows (ready for data, version_number→version normalized)
```

**Code review fixes applied:**
1. Added `server_default="1"` to `Agent.version` for consistency
2. Removed unused `UUIDMixin` import from workspace_models.py
3. Moved `import importlib` to top-level in versioning service
4. Fixed `entity.version` falsy check (version=0 edge case)
5. Fixed test absolute path to use relative `Path(__file__)`
6. Added retrieval function tests (`get_version_history`, `get_version_snapshot`)

**Integration tests added:**
- `backend/tests/test_entity_versioning_integration_pg.py` — 12/12 passing
  - Agent: create + version, multi-version lifecycle (3 versions), cascade delete
  - Workspace: create + version, history + snapshot query, missing version returns None
  - Mission: create + version (individual columns), cascade delete
  - Unique index enforcement: duplicate (agent_id, version) rejected, duplicate (workspace_id, version) rejected
  - Empty history for non-existent entity, pagination (limit/offset)

**Additional fixes found during integration testing:**
1. `agents` table was missing `state` column (added via migration + manual ALTER TABLE)
2. `MissionVersion` model didn't match actual DB schema — updated to use individual columns (title, description, plan, etc.) with `@property snapshot` synthesizer
3. `versioning.py` updated to write MissionVersion with individual columns
4. Unit test `test_mission_version_table_normalized` updated to match new schema

### 3.2 Event-Sourced Operational State ✅

**What was built:**

| Item | Status | Files |
|------|--------|-------|
| **UnifiedExecutor as default** | ✅ Done | `app/services/substrate/executor.py` — default changed from 'off' to 'run' |
| **Simplified execution routing** | ✅ Done | `app/api/_mission_cqrs/commands.py` — 3-tier → 2-tier (unified / legacy fallback) |
| **Async execution wired** | ✅ Done | `commands.py` `execute_async` fallback now uses UnifiedExecutor |
| **Abort signal propagation** | ✅ Done | `commands.py` `abort_mission` signals UnifiedExecutor abort |
| **Event history endpoint** | ✅ Done | `GET /missions/{id}/events` — reads from substrate_events |
| **State reconstruction endpoint** | ✅ Done | `GET /missions/{id}/state` — replays events via ReplayEngine |
| **Query handler methods** | ✅ Done | `queries.py` — `get_events()`, `get_substrate_state()` |
| **Route handlers** | ✅ Done | `mission.py` — two new GET endpoints |
| **Tests** | ✅ Done | `tests/test_event_sourced_state.py` — 24/24 passing |

**Key changes:**
- `FLOWMANNER_UNIFIED_EXECUTOR` now defaults to `'run'` instead of `'off'`
- `ExecutorV2` middle tier removed from execution routing (still exists as code, will be deleted in 3.5)
- Abort now signals UnifiedExecutor in addition to DB mutation
- Event queries sort by `(timestamp, sequence)` for correct cross-run ordering
- State reconstruction picks the latest run deterministically via `ORDER BY max(timestamp) DESC`

**Code review fixes applied:**
1. Fixed event ordering bug — was sorting by sequence alone (interleaved runs), now sorts by (timestamp, sequence)
2. Fixed state reconstruction to pick latest run deterministically
3. Removed redundant nested import in execute_async fallback
4. Added missing `func` import to queries.py

### 3.3 Workspace-Native Substrate ✅

**What was built:**

| Item | Status | Files |
|------|--------|-------|
| **Mission workspace_id** | ✅ Done | `app/models/mission_models.py` — FK → workspaces.id, SET NULL |
| **Workflow workspace_id** | ✅ Done | `app/models/graph.py` — Workflow + WorkflowExecution |
| **Agent workspace_id** | ✅ Done | `app/models/agent.py` — Agent + AgentTemplate |
| **Tool catalog workspace_id** | ✅ Done | `app/models/tool_catalog_models.py` — NULL = global builtin |
| **Capability catalog workspace_id** | ✅ Done | `app/models/capability_catalog_models.py` — NULL = global builtin |
| **Chat workspace_id** | ✅ Done | `app/models/chat.py` — ChatThread |
| **Alembic migration** | ✅ Done | `alembic/versions/20260606_workspace_native.py` — 8 tables, 8 indexes |
| **Tests** | ✅ Done | `tests/test_workspace_native.py` — 19/19 passing |

**Tables modified:**
```
missions:              workspace_id (FK, SET NULL, indexed)
agents:                workspace_id (FK, SET NULL, indexed)
workflows:             workspace_id (FK, SET NULL, indexed)
workflow_executions:   workspace_id (FK, SET NULL, indexed)
agent_templates:       workspace_id (FK, SET NULL, indexed)
tools_catalog:         workspace_id (nullable, no FK, indexed)  ← NULL = global
capabilities_catalog:  workspace_id (nullable, no FK, indexed)  ← NULL = global
chat_threads:          workspace_id (nullable, no FK, indexed)
```

**Design decisions:**
- Operational tables (missions, agents, workflows, agent_templates) use FK with SET NULL on delete
- Catalog tables (tools, capabilities) use no FK — NULL means global/builtin, non-NULL means workspace-specific custom
- All columns nullable for backward compat with existing data
- MissionTask inherits workspace scope through mission_id FK

### 3.4 Deterministic Bootstrap Command ✅

**What was built:**

| Item | Status | Files |
|------|--------|-------|
| **Bootstrap CLI** | ✅ Done | `app/cli/bootstrap.py` — 9-step deterministic sequence |
| **Entry point** | ✅ Done | `app/cli/__main__.py` — `python -m app.cli.bootstrap` |
| **Dockerfile update** | ✅ Done | `Dockerfile` — added `COPY scripts/ /app/scripts/` |
| **.dockerignore update** | ✅ Done | `.dockerignore` — removed `scripts/` exclusion |
| **Tests** | ✅ Done | `tests/test_bootstrap.py` — 14/14 passing |

**Bootstrap steps (all idempotent):**
1. Verify DB connectivity
2. Run pending Alembic migrations
3. Seed agent templates from disk
4. Import builtin tools (subprocess → `scripts/import_builtin_tools.py`)
5. Import builtin capabilities (subprocess → `scripts/import_builtin_capabilities.py`)
6. Import agent-tool bindings (subprocess → `scripts/import_bindings.py`)
7. Seed topology snapshot (subprocess → `scripts/seed_topology.py`)
8. Rebuild Qdrant index from DB
9. Verify system health (PG, Redis, Qdrant, catalog counts)

**CLI flags:** `--skip-migrations`, `--skip-qdrant`, `--dry-run`

**End-to-end timing:** ~12s, ALL OK

**Code review fixes applied:**
1. Fixed wrong `cwd` for alembic (was computing `app/` instead of `backend/`)
2. Converted script steps from broken `from scripts.X import run` to subprocess calls via shared `_run_script()` helper
3. Removed dead `sys.path` manipulation at top of file
4. Extracted `_get_backend_root()` helper to eliminate duplicated path computation

### 3.5 Remove Legacy Systems ✅

**What was removed:**

| Item | Status | Details |
|------|--------|-------|
| **ExecutorV2** | ✅ Deleted | `app/services/substrate/executor_v2.py` (~500 lines) |
| **ExecutorV2 tests** | ✅ Deleted | `tests/test_substrate_executor_v2.py` (19 tests) |
| **FLOWMANNER_SUBSTRATE_V2 flag** | ✅ Removed | All references cleaned from codebase |
| **substrate __init__.py** | ✅ Updated | Removed ExecutorV2/get_executor_v2 imports and __all__ |
| **test_event_sourced_state.py** | ✅ Updated | Removed TestSubstrateFeatureFlag class (2 tests) |
| **test_mission_handlers.py** | ✅ Updated | Removed stale `_substrate_feature_enabled` patch |
| **test_mission_cqrs.py** | ✅ Updated | Removed stale `_substrate_feature_enabled` patch |
| **CI workflow** | ✅ Updated | Removed test_substrate_executor_v2.py from substrate-critical and backend jobs |

**What was kept:** EventLog, ReplayEngine, UnifiedExecutor — these are the active execution infrastructure.

**Net result:** ~700 lines of dead code removed. The UnifiedExecutor is now the sole execution path.

---

## Workspace ID Backfill ✅

After Phase 3.3 added workspace_id columns to 8 tables, all existing rows had NULL workspace_id.

**Script:** `scripts/backfill_workspace_id.py`
- Builds user_id → workspace_id map from workspaces.owner_id + workspace_members
- User-scoped tables (missions, agents, workflows, chat_threads) matched by user_id
- Catalog tables (agent_templates, tools_catalog, capabilities_catalog) and workflow_executions assigned to default workspace
- Handles VARCHAR vs Integer uid columns via dynamic type detection

**Results:**
```
missions:              433 matched by user, 59 assigned to default
agents:                7 assigned to default
workflows:             9 matched by user
chat_threads:          14 matched by user
workflow_executions:   2 assigned to default
agent_templates:       299 assigned to default
tools_catalog:         125 assigned to default
capabilities_catalog:  299 assigned to default
─────────────────────────────────────────────
Total:                 1,247 rows updated
```

**Verified:** 0 NULL workspace_id across all 8 tables.

---

## Phase 3 COMPLETE ✅

All Phase 3 items (3.1–3.5) plus workspace backfill are done.

---

## Phase 4: Multi-Workspace — ✅ COMPLETE (4.1–4.13)

**Goal:** Workspace-scoped queries, RBAC enforcement, tenant isolation.

### Phase 4 Summary So Far

All three entity domains (missions, graphs, chats) now have full workspace-aware access control:
- **List/Create** endpoints filter by `X-Workspace-Id` header via `get_workspace_id` dependency
- **Read/Update/Delete** endpoints verify workspace membership via entity's own `workspace_id` field
- **Cache keys** include `workspace_id` to prevent cross-workspace stale reads
- **19/19 tenant isolation tests passing**

### 4.1 Fix roles.py `tid` bug ✅

**File:** `app/api/v1/roles.py`

Fixed undefined `tid` → `wid` in `assign_role_to_user()` and `unassign_role_from_user()` functions. Was a runtime error on any role assignment.

### 4.2 Workspace Resolution Dependency ✅

**File:** `app/api/deps.py`

Added `get_workspace_id(request, user, db)` async dependency:
1. Resolves from `X-Workspace-Id` header or `workspace_id` query param
2. Validates user membership in that workspace
3. If explicit workspace fails validation → returns None (security: no silent fallback)
4. If no explicit workspace → auto-detects user's primary workspace (highest role priority)
5. If no workspaces → returns None

### 4.3 Workspace-Scoped Missions ✅

**Files modified:**
- `app/services/mission_service.py` — `create_mission()` accepts `workspace_id`, sets on Mission object. `list_missions()` filters by `workspace_id` when provided, falls back to `user_id`.
- `app/api/_mission_cqrs/commands.py` — `MissionCommandHandlers.create_mission()` passes `workspace_id`
- `app/api/_mission_cqrs/queries.py` — `MissionQueryHandlers.list_missions()` passes `workspace_id` to both service AND cache layer
- `app/api/v1/mission.py` — `list_items` and `create_item` endpoints use `get_workspace_id` dependency
- `app/services/mission_cache.py` — Cache keys now include `workspace_id` to prevent cross-workspace stale reads (`mission:list:{uid}:ws:{wid}:p{page}:pp{pp}`)

### 4.4 Workspace-Scoped Workflows ✅

**Files modified:**
- `app/services/graph_service.py` — `create_graph_workflow()` accepts `workspace_id`. `list_graph_workflows()` filters by workspace when provided.
- `app/api/v1/graph.py` — `list_items` and `create_item` endpoints use `get_workspace_id` dependency

### 4.5 Workspace-Scoped Chat ✅

**Files modified:**
- `app/services/chat_service.py` — `create_chat_thread()` accepts `workspace_id`. `list_chat_threads()` filters by workspace when provided.
- `app/api/v1/chat.py` — `list_threads_route` and `create_thread` endpoints use `get_workspace_id` dependency

### 4.6 Tenant Isolation Tests ✅

**File:** `backend/tests/test_tenant_isolation.py` — 35/35 passing

Covers:
- `get_workspace_id` dependency: header resolution, query param resolution, primary workspace fallback, no-workspace case
- Mission service: workspace filtering, user_id fallback, create with workspace_id
- Graph service: create with workspace_id, list with workspace filter, user_id fallback
- Graph access isolation: `require_graph_access` — workspace member allowed, non-member denied, user_id fallback, wrong user denied, missing workflow 404
- Chat service: create with workspace_id, list with workspace filter, user_id fallback
- Chat access isolation: `require_chat_thread_access` — workspace member allowed, non-member denied, user_id fallback, wrong user denied, missing thread 404
- Active missions: `list_active` and `active_missions` workspace filtering, user_id fallback, pro subscription enforcement
- CQRS propagation: create and list pass workspace_id through
- Roles.py bug fix: AST check confirms no `tid` references
- PermissionService: returns False for non-members

### 4.7 Workspace-Aware Entity Access ✅

**Files modified:**
- `app/services/mission_service.py` — Added `require_mission_access(db, mission_id, user_id)` helper:
  - If mission has `workspace_id` → verifies user is an active member of that workspace
  - If mission has no `workspace_id` → falls back to `user_id` ownership check
  - Raises `MissionNotFoundError` on access denial
- `app/api/_mission_cqrs/queries.py` — `get_mission()` and `get_mission_response()` use `require_mission_access` instead of inline `user_id` check
- `app/api/_mission_cqrs/commands.py` — All 12 mutation methods (update, delete, create_task, update_task, create_log, plan, execute, execute_async, pause, resume, retry, create_improvement, apply_improvement) use `require_mission_access`. `abort_mission` and `batch_abort` use inline workspace checks (abort needs FOR UPDATE lock first; batch_abort pre-fetches memberships to avoid N+1)

**Design decisions:**
- Mission's own `workspace_id` is the source of truth for access (not request's workspace context)
- A user who is a member of workspace A AND workspace B can access missions in both
- Isolation prevents access from non-members (workspace C cannot access A's missions)
- `abort_mission` checks access post-lock to avoid TOCTOU races
- `batch_abort` pre-fetches all workspace memberships in one query before the loop (N+1 fix)

### 4.8 Graph + Active Missions Workspace Scoping ✅

**Files modified:**
- `app/services/graph_service.py` — Added `require_graph_access(db, workflow_id, user_id)`: workspace-aware access check for workflows. Returns the workflow object (avoids double-fetch). Raises HTTPException(404) on denial. Added `from fastapi import HTTPException`.
- `app/api/v1/graph.py` — Replaced ALL `_require_owner(workflow, user)` calls with `require_graph_access(db, workflow_id, user.id)` across all endpoints: get_item, patch_item, delete_item, run_graph, resume_graph, list_executions, get_execution, list_states, list_execution_nodes, compare_executions. Eliminated double-fetch in patch_item and delete_item. Removed unused `_require_owner` function.
- `app/api/_mission_cqrs/queries.py` — Added `workspace_id` param to `list_active()` and `active_missions()`. Filters by workspace_id when provided, falls back to user_id.
- `app/api/v1/mission.py` — Updated `list_active_missions` endpoint to use `get_workspace_id` dependency.

**Tests:** 19/19 passing, backend healthy

### Phase 4 Remaining Gaps & Plan

#### 4.9 Chat Endpoint Isolation ✅

**Files modified:**
- `app/services/chat_service.py` — Added `require_chat_thread_access(db, thread_id, user)` helper:
  - If thread has `workspace_id` → verifies user is an active member of that workspace
  - If thread has no `workspace_id` → falls back to `user_id` ownership check
  - Raises HTTPException(404) on access denial
  - Returns the thread object (single fetch pattern)
- `app/api/v1/chat.py` — Replaced ALL 14 `_require_owner(thread, user)` calls with `require_chat_thread_access(db, thread_id, user)`:
  - Thread CRUD: get_thread, patch_thread, delete_thread
  - Message CRUD: list_messages, send_message, get_message, patch_message
  - Branch CRUD: list_branches, create_branch, get_branch, delete_branch
  - Utility: generate_title, search_messages, list_threads
  - Branch access now checks via parent thread's workspace (not branch.user_id directly)
  - Removed unused `_require_owner` function

**Design decisions:**
- Thread's own `workspace_id` is the source of truth for access control
- Branch access is checked via parent thread's workspace
- Returns thread object to avoid double-fetch

#### 4.10 Frontend `X-Workspace-Id` Header Integration ✅

**Files modified:**
- `src/stores/workspace-store.ts` — Added Zustand `persist` middleware:
  - `WORKSPACE_STORAGE_KEY = "flowmanner-workspace"` exported constant
  - `partialize` only persists `activeWorkspace` (workspaces list fetched fresh on mount)
  - `loadWorkspaces` validates persisted workspace against fresh list (handles membership removal)
  - `switchWorkspace` manually flushes to localStorage via `persistWorkspaceNow()` to avoid async persist race with `window.location.reload()`
- `src/lib/api-client.ts` — Added `X-Workspace-Id` header injection:
  - `getActiveWorkspaceId()` reads from localStorage (Zustand persist format), returns workspace ID or undefined
  - Hardcoded storage key (not imported from store) to avoid circular dep: api-client → workspace-store → workspace-api → api-client
  - Sets `headers["X-Workspace-Id"]` on every API request when workspace ID available
  - SSR-safe and error-safe (try/catch, typeof window check)

**Design decisions:**
- Read localStorage directly in api-client (not Zustand store import) to break circular dependency
- Belt-and-suspenders: both Zustand persist and explicit `persistWorkspaceNow()` write to localStorage
- `loadWorkspaces` validates persisted workspace exists in fresh list to prevent stale workspace after membership removal
- No SWR cache clearing needed: app uses React Query, and switcher already does `window.location.reload()`
- TypeScript compiles with zero errors

**Flow:** Workspace switcher → `switchWorkspace()` → persist to localStorage → `window.location.reload()` → all API requests include `X-Workspace-Id` header → backend `get_workspace_id` dependency scopes queries

**Deployed:** 2026-06-03 via `bash /opt/flowmanner/deploy-frontend.sh` from homelab.

**End-to-end verification:**
- ✅ TypeScript compiled with zero errors
- ✅ Frontend Docker build succeeded (Next.js 16.2.6, compiled in 26.8s, 16 static pages)
- ✅ VPS containers healthy: `flowmanner-frontend` Up, `flowmanner-nginx` Up
- ✅ HTTPS responding (HTTP/2 200 at `flowmanner.com`)
- ✅ Backend healthy through WireGuard (PG 1.7ms, Redis 0.9ms, Langfuse CLOSED)
- ✅ Workspace isolation confirmed: fake workspace ID → `404 Not Found`, unauthenticated → `404 Not Found`
- ✅ Frontend container logs: `Next.js 16.2.6 — Ready in 0ms`, no errors

#### 4.11 Cross-Workspace Permission Grants ✅

**Files created/modified:**
- `app/models/workspace_models.py` — Added `WorkspaceShare` model: source/target workspace FKs, entity_type (`mission`/`workflow`/`chat_thread`), entity_id, permission (`read`/`write`), granted_by, is_active, unique constraint
- `alembic/versions/20260607_workspace_shares.py` — Migration creating `workspace_shares` table with composite indexes
- `app/services/cross_workspace_service.py` — New service: `grant_share()` (idempotent), `revoke_share()` (soft-delete), `check_entity_access()` (verify membership + find grant), `list_shares_for_entity/workspace()`, `find_user_workspaces()`
- `app/services/mission_service.py` — `require_mission_access` now checks cross-workspace grants as fallback (iterates user's workspaces)
- `app/services/graph_service.py` — Same cross-workspace fallback in `require_graph_access`
- `app/services/chat_service.py` — Same cross-workspace fallback in `require_chat_thread_access`
- `app/api/v1/workspace_shares.py` — API endpoints: `POST /` (create), `DELETE /{id}` (revoke), `GET /?direction=outgoing|incoming` (list)
- `app/api/v1/__init__.py` — Registered workspace_shares router

**Design decisions:**
- Per-entity granularity (share specific missions/workflows/threads, not blanket workspace access)
- Read + write permission levels (no admin/delete across boundaries)
- Self-share prevented (cannot share entity with its own workspace)
- Idempotent grants (re-granting updates permission level)
- Soft-revoke (is_active flag, preserves audit trail)
- Cross-workspace fallback only triggers after direct workspace membership check fails

**Tests:** `backend/tests/test_cross_workspace_shares.py` — 19/19 passing

#### 4.12 Audit Trail for Workspace Access ✅

**Files modified:**
- `app/api/deps.py` — `get_workspace_id` logs `workspace_access_denied` warning + fires `log_event` when explicit workspace fails membership check
- `app/services/mission_service.py` — Added logger + `entity_access_denied` warning + `log_event` on workspace denial and owner mismatch in `require_mission_access`
- `app/services/graph_service.py` — Same pattern in `require_graph_access`
- `app/services/chat_service.py` — Same pattern in `require_chat_thread_access`

**Log format:** Consistent structured `event_name key=%s` pattern — `workspace_access_denied` for deps-level denials, `entity_access_denied` for entity-level denials with `entity_type`, `entity_id`, `workspace_id`, and `reason`.

**Tests:** `backend/tests/test_workspace_audit_logging.py` — 13/13 passing

#### 4.13 Minor Optimizations ✅

**1. `compare_executions` double-fetch fix** (`graph.py`): Refactored to fetch both executions first, verify same workflow, then call `require_graph_access` once. Removed dead synchronous `_get_nodes_for_execution` function.

**2. `GraphNotFoundError` extraction** (`mission_errors.py`, `graph_service.py`, `graph.py`): Added `GraphNotFoundError` domain exception. `require_graph_access` raises it instead of `HTTPException`. All 11 call sites in `graph.py` catch it and translate to HTTP 404. Consistent with `MissionNotFoundError` pattern.

**3. Active missions cache by `workspace_id`** (`mission_cache.py`, `queries.py`): `_active_key` now includes workspace scope (`mission:active:{uid}:ws:{wid}`). `cache_active` and `cache_set_active` accept optional `workspace_id`. All 4 call sites pass it through. `invalidate_user_caches` SCAN-deletes both workspace-scoped and non-scoped active cache keys.

**Tests:** 33/33 tenant isolation + 13/13 audit logging + mission handlers + P1/P2 fixes — all passing

---

## Phase 5: Marketplace v2 — ✅ COMPLETE (5.1–5.6)

**Goal:** Publish workflow, install-to-workspace, version management, rating aggregation.

### 5.1 Marketplace v2 Migration ✅

**File:** `alembic/versions/20260607_marketplace_v2.py`

Adds to `marketplace_listings`:
- `workspace_id` (FK → workspaces.id, SET NULL, indexed)
- `status` (draft/published/deprecated, replaces is_published boolean)
- `version` (semver string, e.g. '1.0.0')
- `published_at` (timestamp)
- `review_count` (integer, backfilled from existing reviews)

Adds to `marketplace_reviews`:
- `title` column for review headlines

Backfills status from is_published boolean.

### 5.2 Model Updates ✅

**File:** `app/models/models.py`

- `MarketplaceListingModel`: added workspace_id, status, version, published_at, review_count
- `MarketplaceReviewModel`: added title

### 5.3 API Rewrite ✅

**File:** `app/api/v1/marketplace.py` — Complete rewrite with:

**Publish workflow:**
- `POST /listings/{id}/publish` — draft → published (owner-only)
- `POST /listings/{id}/unpublish` — published → draft (owner-only)
- `POST /listings/{id}/deprecate` — published → deprecated (owner-only)

**Install-to-workspace:**
- `POST /listings/{id}/install` — clones workflow artifacts into user's workspace, records installation
- `DELETE /listings/{id}/install` — uninstall, decrements download count

**Rating aggregation:**
- `POST /listings/{id}/reviews` — submit/update review, auto-aggregates avg rating + review_count
- `GET /listings/{id}/rating` — returns RatingSummary with breakdown
- `GET /listings/{id}/reviews` — includes rating_breakdown dict

**Version management:**
- `_bump_version()` — increments patch version on content updates
- Only bumps when actual field changes occur (no no-op bumps)

**Other:**
- ID-based lookups (replaces slug-based name lookups)
- Workspace scoping via `get_workspace_id` dependency on create/install
- Reviews restricted to published listings only

### 5.4 Code Review Fixes ✅

1. `update_listing` only bumps version when fields actually changed (no no-op bumps)
2. `submit_review` now rejects reviews on non-published listings
3. Removed unnecessary `getattr(m, "review_count", 0)` — direct attribute access

### 5.5 Tests ✅

**File:** `backend/tests/test_marketplace_v2.py` — 16/16 passing

Covers: publish/unpublish/deprecate workflow, admin access, non-owner denial, rating aggregation, version bumping, install response schema, valid artifact types, review validation, listing response fields.

### 5.6 Deployment ✅

- Migration `marketplace_v2_001` applied successfully
- Backend rebuilt and restarted
- All 24 marketplace columns verified in DB
- Existing marketplace normalization tests (8/8) still passing

**DB state:**
```
marketplace_listings: 10 rows (status backfilled from is_published)
marketplace_reviews:  0 rows
marketplace_categories: 5 rows
user_installations:   0 rows
workspace_shares:     0 rows
```

---

