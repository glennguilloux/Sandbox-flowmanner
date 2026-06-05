# Postgres-Native Migration Plan

> **Goal:** "If FlowManner disappears and only Postgres survives, the platform can be fully reconstructed."
>
> **Generated:** 2026-06-03
> **Based on:** GPT-6.4 architecture analysis + homelab codebase validation
> **Status:** PLANNED — not started

---

## Executive Summary

FlowManner is currently **not Postgres-native**. The running system is assembled at startup from:
- Postgres (partial — agents, agent_templates, memories, workflows, chat, marketplace)
- Redis (memory service is 100% Redis-backed)
- Qdrant (tool semantic index, topology)
- Python singleton registries (ToolRegistry × 2, CapabilityRegistry)
- Markdown/YAML agent definitions (agent_definitions/*.md → seeded to DB at boot)
- Hardcoded Python template lists (agent_templates.py → 10 templates)
- Filesystem graph artifacts (/mnt/workflows/workflows/graphify-out/graph.json)
- Startup side effects in lifespan.py that construct the ontology

**The fix:** Make Postgres the canonical declarative control plane. Treat Redis/Qdrant/registries as rebuildable caches. Startup should **hydrate** from Postgres, not **invent** state.

---

## Verified Codebase Findings

### What GPT-6.4 Said vs. What I Found

| Claim | Verified | Notes |
|-------|----------|-------|
| ToolRegistry is a singleton | ✅ | `app/tools/base.py` — global `_tool_registry`, also `app/services/unified_tools/tool_registry.py` (separate registry!) |
| CapabilityRegistry is a singleton | ✅ | `app/services/nexus/capability_registry.py` — global `_capability_registry` |
| MemoryService is Redis-only | ✅ | `app/services/memory_service.py` — pure Redis, falls back to "disabled" on Redis outage |
| TopologyManager reads graph.json | ✅ | `app/services/semantic/topology_manager.py` — reads `/mnt/workflows/workflows/graphify-out/graph.json` |
| lifespan.py constructs ontology at boot | ✅ | Seeds agents from markdown, registers capabilities, indexes tools into Qdrant, seeds marketplace |
| Agent templates split across DB + Python + markdown | ✅ | 3 sources: DB rows, `agent_templates.py` (10 hardcoded), `agent_definitions/*.md` (seeded to DB) |
| agent_capabilities table has schema drift | ✅ | Current model in `agent.py` has `name/description/task_types/tools/confidence_score` — not capability catalog |
| Marketplace uses seed data | ✅ | `marketplace_service.py` — `_SEED_LISTINGS` hardcoded, seeds if table empty |
| Workflows are mostly Postgres-native | ✅ | Closest to target, but naming is muddy |

### Additional Findings (Not in GPT-6.4 Analysis)

1. **Two separate ToolRegistries exist:**
   - `app/tools/base.py` — `ToolRegistry` with `BaseTool` instances (the real one)
   - `app/services/unified_tools/tool_registry.py` — `ToolRegistry` with `Tool` dataclass instances (stub registry)
   - lifespan.py registers into BOTH

2. **Agent slug is stored inside model_config JSONB**, not as a proper column:
   ```python
   slug = tpl.model_config.get("slug")  # JSON path, not a column
   ```

3. **Memory has THREE separate stores:**
   - `app/models/memory_models.py` — `Memory` + `MemorySession` tables (Postgres)
   - `app/models/agent.py` — `AgentMemory` table (Postgres, different schema)
   - `app/services/memory_service.py` — Redis-only `MemoryService`

4. **marketplace_service.py uses `category_id` as a freeform string** ("Sales", "AI"), not an FK

5. **Tool discovery indexes from in-memory registry into Qdrant** — if registry is empty, Qdrant is empty. No rebuild path.

---

## Phase 1: Foundation (Weeks 1-4)

**Goal:** Stop losing ontology at startup. Postgres becomes canonical for definitions.

### 1.1 New Canonical Schema Tables

Create Alembic migration: `20260603_postgres_native_foundation.py`

#### 1.1a Tools Catalog

```sql
CREATE TABLE tools (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            VARCHAR(255) UNIQUE NOT NULL,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    category        VARCHAR(100),
    tool_type       VARCHAR(50) NOT NULL DEFAULT 'builtin',
    -- 'builtin', 'http', 'workflow', 'agent', 'capability', 'integration'
    handler_ref     VARCHAR(500),  -- Python dotted path, e.g. 'app.tools.browser_ping.BrowserPingTool'
    input_schema    JSONB DEFAULT '{}',
    output_schema   JSONB DEFAULT '{}',
    auth_policy     JSONB DEFAULT '{}',
    visibility      VARCHAR(50) DEFAULT 'public',
    owner_id        UUID REFERENCES users(id),
    enabled         BOOLEAN DEFAULT TRUE,
    version         INTEGER DEFAULT 1,
    source          VARCHAR(50) DEFAULT 'db',
    -- 'db', 'builtin_imported'
    metadata        JSONB DEFAULT '{}',
    tags            JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tool_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_id         UUID REFERENCES tools(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL,
    snapshot        JSONB NOT NULL,  -- full tool definition at this version
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tool_id, version)
);

CREATE INDEX idx_tools_slug ON tools(slug);
CREATE INDEX idx_tools_category ON tools(category);
CREATE INDEX idx_tools_enabled ON tools(enabled);
```

#### 1.1b Capabilities Catalog

```sql
CREATE TABLE capabilities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            VARCHAR(255) UNIQUE NOT NULL,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    category        VARCHAR(100),
    input_schema    JSONB DEFAULT '{}',
    output_schema   JSONB DEFAULT '{}',
    handler_ref     VARCHAR(500),
    auth_policy     JSONB DEFAULT '{}',
    timeout_seconds INTEGER DEFAULT 30,
    rate_limit      INTEGER,
    enabled         BOOLEAN DEFAULT TRUE,
    version         INTEGER DEFAULT 1,
    source          VARCHAR(50) DEFAULT 'db',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE capability_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    capability_id   UUID REFERENCES capabilities(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL,
    snapshot        JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(capability_id, version)
);

CREATE TABLE capability_dependencies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    capability_id   UUID REFERENCES capabilities(id) ON DELETE CASCADE,
    depends_on_id   UUID REFERENCES capabilities(id) ON DELETE CASCADE,
    dependency_type VARCHAR(50) DEFAULT 'requires',
    UNIQUE(capability_id, depends_on_id)
);
```

#### 1.1c Agent Template Canonicalization

Add columns to existing `agent_templates` table:

```sql
ALTER TABLE agent_templates ADD COLUMN slug VARCHAR(255) UNIQUE;
ALTER TABLE agent_templates ADD COLUMN version INTEGER DEFAULT 1;
ALTER TABLE agent_templates ADD COLUMN source VARCHAR(50) DEFAULT 'db';
-- 'db', 'file_imported', 'python_imported'
ALTER TABLE agent_templates ADD COLUMN definition JSONB;
-- Full template definition, replaces model_config overloaded usage

CREATE TABLE agent_template_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id     UUID REFERENCES agent_templates(template_id) ON DELETE CASCADE,
    version         INTEGER NOT NULL,
    snapshot        JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(template_id, version)
);

CREATE TABLE agent_tool_bindings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID REFERENCES agents(id) ON DELETE CASCADE,
    tool_id         UUID REFERENCES tools(id) ON DELETE CASCADE,
    enabled         BOOLEAN DEFAULT TRUE,
    config          JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_id, tool_id)
);

CREATE TABLE agent_capability_bindings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID REFERENCES agents(id) ON DELETE CASCADE,
    capability_id   UUID REFERENCES capabilities(id) ON DELETE CASCADE,
    enabled         BOOLEAN DEFAULT TRUE,
    config          JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_id, capability_id)
);

-- Link agents to their template
ALTER TABLE agents ADD COLUMN template_id UUID REFERENCES agent_templates(template_id);
ALTER TABLE agents ADD COLUMN runtime_config JSONB DEFAULT '{}';
ALTER TABLE agents ADD COLUMN desired_state VARCHAR(30);
ALTER TABLE agents ADD COLUMN observed_state VARCHAR(30);
```

#### 1.1d Unified Memory

```sql
CREATE TABLE memory_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID,
    user_id         INTEGER REFERENCES users(id),
    agent_id        VARCHAR(255),
    session_id      UUID,
    namespace       VARCHAR(255) DEFAULT 'default',
    memory_type     VARCHAR(100) DEFAULT 'episodic',
    content         TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}',
    importance      FLOAT DEFAULT 0.5,
    supersedes_id   UUID REFERENCES memory_entries(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_memory_entries_user ON memory_entries(user_id);
CREATE INDEX idx_memory_entries_agent ON memory_entries(agent_id);
CREATE INDEX idx_memory_entries_session ON memory_entries(session_id);
CREATE INDEX idx_memory_entries_type ON memory_entries(memory_type);

-- Optional: pgvector for semantic search (future)
-- ALTER TABLE memory_entries ADD COLUMN embedding vector(384);
```

#### 1.1e Materialization State

```sql
CREATE TABLE materialization_state (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    object_type         VARCHAR(100) NOT NULL,
    -- 'tool', 'capability', 'agent_template', 'memory', 'topology'
    object_id           UUID NOT NULL,
    target              VARCHAR(50) NOT NULL,
    -- 'redis', 'qdrant', 'inproc', 'all'
    version             INTEGER DEFAULT 1,
    status              VARCHAR(50) DEFAULT 'pending',
    -- 'pending', 'materializing', 'materialized', 'stale', 'failed'
    checksum            VARCHAR(64),
    last_materialized_at TIMESTAMPTZ,
    error_message       TEXT,
    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(object_type, object_id, target)
);

CREATE INDEX idx_mat_state_status ON materialization_state(status);
CREATE INDEX idx_mat_state_type ON materialization_state(object_type);
```

#### 1.1f Topology (DB-Native)

```sql
CREATE TABLE topology_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version         INTEGER NOT NULL,
    description     TEXT,
    node_count      INTEGER DEFAULT 0,
    edge_count      INTEGER DEFAULT 0,
    community_count INTEGER DEFAULT 0,
    source          VARCHAR(50) DEFAULT 'computed',
    -- 'computed', 'imported', 'manual'
    snapshot_data   JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE topology_nodes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id     UUID REFERENCES topology_snapshots(id) ON DELETE CASCADE,
    external_id     VARCHAR(255) NOT NULL,
    label           VARCHAR(500),
    node_type       VARCHAR(100),
    community_id    INTEGER,
    metadata        JSONB DEFAULT '{}',
    -- Lineage: where this node came from
    derived_from_agent_id       UUID REFERENCES agents(id),
    derived_from_capability_id  UUID REFERENCES capabilities(id),
    derived_from_workflow_id    UUID,
    confidence      FLOAT DEFAULT 1.0,
    evidence        JSONB DEFAULT '{}'
);

CREATE TABLE topology_edges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id     UUID REFERENCES topology_snapshots(id) ON DELETE CASCADE,
    source_node_id  UUID REFERENCES topology_nodes(id) ON DELETE CASCADE,
    target_node_id  UUID REFERENCES topology_nodes(id) ON DELETE CASCADE,
    relation        VARCHAR(100) DEFAULT 'calls',
    confidence      VARCHAR(50) DEFAULT 'INFERRED',
    metadata        JSONB DEFAULT '{}'
);

CREATE INDEX idx_topo_nodes_snapshot ON topology_nodes(snapshot_id);
CREATE INDEX idx_topo_edges_snapshot ON topology_edges(snapshot_id);
```

### 1.2 Builtin Importers

Create management commands to backfill existing builtins into Postgres:

#### 1.2a `import_builtin_tools`

```
backend/app/cli/import_builtin_tools.py
```

- Reads all tools from `app/tools/base.ToolRegistry` after `_register_core_tools()`
- For each tool, creates/updates a row in the `tools` table
- Sets `source='builtin_imported'`, `handler_ref='app.tools.<module>.<ClassName>'`
- Creates version snapshot in `tool_versions`

**Imports ~30 tools:** browser_*, topology, terminal, integration_*, llm_*, data_*, utility_*, external_*, differentiators_*

#### 1.2b `import_builtin_capabilities`

```
backend/app/cli/import_builtin_capabilities.py
```

- Reads capabilities from `CapabilityRegistry` after startup registration
- Creates rows in `capabilities` table
- Sets `handler_ref` to Python path

#### 1.2c `import_agent_templates`

```
backend/app/cli/import_agent_templates.py
```

- Backfills `agent_templates.slug` from existing `model_config['slug']`
- Backfills `agent_templates.source` = 'file_imported' for markdown-sourced, 'python_imported' for `agent_templates.py` sourced
- Creates `agent_template_versions` snapshots
- Imports the 10 hardcoded `AGENT_TEMPLATES` from `agent_templates.py`

#### 1.2d `import_markdown_agents`

```
backend/app/cli/import_markdown_agents.py
```

- Reads `agent_definitions/*.md` files via `agent_parser.py`
- Upserts into `agent_templates` with `source='file_imported'`
- Creates version snapshots

### 1.3 Memory Service Rewrite (Postgres-First)

**File:** `app/services/memory_service.py`

**Current:** Pure Redis. Falls back to "disabled" when Redis is unavailable.

**New behavior:**
1. Write to `memory_entries` table FIRST (always)
2. Optionally mirror to Redis cache (best-effort)
3. Read from Redis cache if available, fallback to Postgres
4. Redis outage = degraded performance, NOT memory loss

**Migration steps:**
1. Add `MemoryEntry` ORM model pointing to `memory_entries` table
2. Rewrite `MemoryService.store()` → write to Postgres, then mirror to Redis
3. Rewrite `MemoryService.retrieve_by_query()` → check Redis first, fallback to Postgres
4. Rewrite `MemoryService.delete_memory()` → delete from Postgres, then Redis
5. Add migration to copy existing Redis memories into `memory_entries` (one-time)
6. Deprecate `AgentMemory` model in `agent.py` (consolidate into `memory_entries`)
7. Deprecate `Memory`/`MemorySession` in `memory_models.py` (consolidate into `memory_entries`)

### 1.4 Startup Refactor (lifespan.py)

**Current startup sequence:**
```
1. Validate production secrets
2. Init Langfuse
3. Init Sentry
4. Init LiteLLM callbacks
5. Seed agent templates from markdown files  ← creates ontology
6. Register agent capabilities into in-memory registry  ← creates ontology
7. Seed marketplace from hardcoded list  ← creates ontology
8. Start trigger scheduler
9. Register core tools into in-memory registry  ← creates ontology
10. Init tool discovery (indexes tools into Qdrant)  ← creates ontology
11. Register differentiator stubs into unified_tools registry  ← creates ontology
12. Register integration capabilities  ← creates ontology
```

**New startup sequence:**
```
1. Validate production secrets
2. Init Langfuse
3. Init Sentry
4. Init LiteLLM callbacks
5. Start trigger scheduler

── Hydration Phase (all read from Postgres) ──

6. Hydrate tools from DB → ToolRegistry
   - Load all enabled tools from `tools` table
   - Resolve `handler_ref` to Python classes
   - Register into in-memory ToolRegistry
   - Log count, warn on missing handlers

7. Hydrate capabilities from DB → CapabilityRegistry
   - Load all enabled capabilities from `capabilities` table
   - Resolve `handler_ref` to Python functions
   - Register into in-memory CapabilityRegistry

8. Hydrate agent templates from DB → CapabilityRegistry
   - Agent templates are already in DB (no markdown seeding)
   - Register as capabilities (same as today, but source is DB only)

9. Rebuild Qdrant index from DB
   - Read all tools from `tools` table
   - Index into Qdrant collection
   - Update `materialization_state`

10. Warm Redis caches from DB
    - Load hot memory entries into Redis
    - Update `materialization_state`
```

**Key change:** Steps 5-8 in current flow become no-ops or are deleted. The system hydrates from Postgres, not from Python/markdown/filesystem.

### 1.5 Disaster Recovery Acceptance Test

```
backend/tests/test_disaster_recovery.py
```

**Test flow:**
1. Create a fresh Postgres database
2. Run all Alembic migrations
3. Run all import commands (tools, capabilities, agent templates)
4. Simulate startup hydration
5. Assert:
   - All tools are discoverable
   - All capabilities are registered
   - All agent templates are loadable
   - Memory service reads/writes work
   - Tool discovery (Qdrant) can be rebuilt
   - Topology can be reconstructed
6. Output reconstruction report

---

## Phase 2: Registry Replacement (Weeks 5-12)

**Goal:** Replace singleton registries with DB-derived projections.

### 2.1 ToolRegistry Hydration Pipeline

**Current:** `ToolRegistry.__init__()` → empty dict → `_register_core_tools()` adds tools one by one

**New:** `ToolRegistry.hydrate_from_db(session)` → reads `tools` table → resolves handlers → populates registry

```python
class ToolRegistry:
    async def hydrate_from_db(self, session: AsyncSession) -> int:
        """Load all enabled tools from Postgres and populate the registry."""
        result = await session.execute(
            select(ToolModel).where(ToolModel.enabled.is_(True))
        )
        db_tools = result.scalars().all()
        hydrated = 0
        for tool_row in db_tools:
            handler = self._resolve_handler(tool_row.handler_ref)
            if handler is None:
                logger.warning("Cannot resolve handler for tool %s: %s", tool_row.slug, tool_row.handler_ref)
                continue
            tool = self._build_tool_from_db(tool_row, handler)
            self.register(tool)
            hydrated += 1
        return hydrated
```

**Breaking change:** `register()` calls at import time are no longer canonical. The hydration pipeline reads from DB.

### 2.2 CapabilityRegistry Hydration Pipeline

Same pattern as tools. Load from `capabilities` table, resolve handlers, register.

### 2.3 Normalized Bindings

Create the binding tables from Phase 1 schema:
- `agent_tool_bindings` — which tools each agent can use
- `agent_capability_bindings` — which capabilities each agent has
- `capability_dependencies` — capability dependency graph

### 2.4 Topology from DB

**Current:** `TopologyManager.build()` reads `graph.json` from filesystem

**New:**
1. `TopologyManager.build_from_db(session)` — reads latest `topology_snapshots`
2. Add `TopologyManager.rebuild_from_agents(session)` — reconstructs topology from `agents` + `capabilities` + `tools` tables
3. `graph.json` becomes an export artifact, not the source

### 2.5 Qdrant as Rebuildable Index

**Current:** `_init_tool_discovery()` indexes from in-memory registry → Qdrant. No rebuild path.

**New:**
1. Add `semantic_index_documents` table — tracks what's indexed and its checksum
2. Reindex job reads from `tools` + `capabilities` tables → rebuilds Qdrant
3. "Qdrant empty" must not mean "system forgot tools"
4. Add `/admin/reindex` endpoint for manual trigger

### 2.6 Workflow Model Cleanup

- Unify `project`/`flow`/`workflow` semantics
- Add `workflow_versions` table
- Add `execution_events` append-only table
- Make workflow references point to canonical tool/capability/agent IDs

### 2.7 Marketplace Normalization

- `marketplace_listings` gets `artifact_type` enum + `artifact_id` + `artifact_version_id`
- Seed listings become optional demo content, not required for system integrity
- `category_id` becomes a proper FK to `marketplace_categories`

---

## Phase 3: Durable Agent OS (Months 3-6)

**Goal:** Full versioned control plane with deterministic bootstrap.

### 3.1 Versioned Object Model

All major entities get version tables:
- `agent_template_versions`
- `tool_versions`
- `capability_versions`
- `workflow_versions`
- `topology_snapshots`

### 3.2 Event-Sourced Operational State

Append-only event streams:
- `agent_lifecycle_events`
- `tool_execution_events`
- `workflow_execution_events`
- `memory_mutation_events`
- `registry_materialization_events`

### 3.3 Workspace-Native Substrate

- Workspace-scoped installations
- Policy bindings
- Secret references
- Quotas/rate limits
- Execution environments

### 3.4 Deterministic Bootstrap Command

```python
# backend/app/cli/bootstrap.py
async def bootstrap_from_postgres():
    """Reconstruct entire system from Postgres alone.
    
    1. Connect to Postgres
    2. Hydrate tool definitions
    3. Hydrate capability definitions
    4. Hydrate agent templates
    5. Rebuild Qdrant index
    6. Warm Redis caches
    7. Rebuild topology
    8. Validate checksums
    9. Output reconstruction report
    """
```

### 3.5 Remove Legacy Systems

Delete or retire:
- ~~markdown-as-canonical agent source~~ → import source only
- ~~hardcoded AGENT_TEMPLATES as runtime authority~~ → import source only
- ~~Redis-only memory paths~~ → cache only
- ~~file-based topology dependency~~ → export only
- ~~duplicate tool registry (unified_tools)~~ → consolidate into one
- ~~schema-drifted capability paths~~ → canonical table

---

## Priority Matrix

```
P0 — Blockers (do first)
├── Tools catalog table + importer          [~3 days]
├── Capabilities catalog table + importer   [~3 days]
├── Agent template canonicalization         [~2 days]
├── Memory Postgres-first rewrite           [~3 days]
├── Materialization state table             [~1 day]
└── Disaster recovery test                  [~2 days]

P1 — Foundation cleanup (after P0)
├── Registry hydration from DB              [~3 days]
├── Topology DB tables + builder            [~3 days]
├── Qdrant rebuild pipeline                 [~2 days]
├── Workflow model cleanup                  [~2 days]
└── Marketplace normalization               [~1 day]

P2 — Durable agent OS (after P1)
├── Version tables for all entities         [~2 days]
├── Event sourcing                          [~5 days]
├── Workspace-native substrate              [~5 days]
├── Deterministic bootstrap command         [~3 days]
└── Legacy system removal                   [~3 days]
```

**Estimated total:** 8-12 weeks for Phases 1+2, 6 months for Phase 3.

---

## Breaking Changes to Accept

1. **Builtins stop being born in Python.** They're still *implemented* in Python, but *defined* in Postgres. The `handler_ref` column points to the Python class.

2. **Redis becomes cache only.** No durable memory solely in Redis. Memory writes go to Postgres first.

3. **Qdrant becomes index only.** No semantic entity should exist only because Qdrant has it.

4. **Startup becomes hydration, not creation.** `lifespan.py` should not define the ontology.

5. **Files become import/export, not truth.** Markdown and `graph.json` are artifacts, not system memory.

6. **Two ToolRegistries must be consolidated.** The `unified_tools/tool_registry.py` registry is redundant. Merge into `app/tools/base.py`'s `ToolRegistry`.

---

## Files to Create

| File | Purpose |
|------|---------|
| `alembic/versions/20260603_postgres_native_foundation.py` | Phase 1 schema migration |
| `app/models/tool_models_new.py` | Canonical Tool + ToolVersion ORM models |
| `app/models/capability_models_new.py` | Canonical Capability + CapabilityVersion ORM models |
| `app/models/topology_models.py` | TopologySnapshot, TopologyNode, TopologyEdge |
| `app/models/materialization_models.py` | MaterializationState ORM model |
| `app/cli/import_builtin_tools.py` | Backfill tools from Python registry into DB |
| `app/cli/import_builtin_capabilities.py` | Backfill capabilities into DB |
| `app/cli/import_agent_templates.py` | Backfill agent templates with slug/version/source |
| `app/cli/bootstrap.py` | Deterministic reconstruction from Postgres |
| `tests/test_disaster_recovery.py` | Acceptance test for reconstruction |

## Files to Modify

| File | Change |
|------|--------|
| `app/lifespan.py` | Replace creation with hydration |
| `app/tools/base.py` | Add `hydrate_from_db()` method |
| `app/services/nexus/capability_registry.py` | Add `hydrate_from_db()` method |
| `app/services/memory_service.py` | Postgres-first writes, Redis as cache |
| `app/services/semantic/topology_manager.py` | Read from DB, not graph.json |
| `app/services/tool_discovery_service.py` | Rebuild from DB, not in-memory registry |
| `app/services/agent_service.py` | Populate slug/version/source columns |
| `app/services/marketplace_service.py` | Normalize artifact references |
| `app/models/agent.py` | Add slug/version/source to AgentTemplate |

## Files to Eventually Delete

| File | Reason |
|------|--------|
| `app/services/unified_tools/tool_registry.py` | Duplicate of `app/tools/base.py` ToolRegistry |
| `app/services/unified_tools/unified_bridge.py` | Bridge between two redundant registries |
| `app/services/nexus/agent_templates.py` | Hardcoded templates → import source only |

---

## Acceptance Criteria

The migration is complete when:

```bash
# 1. Drop all non-Postgres state
docker compose stop redis qdrant
docker compose rm -f redis qdrant
rm /mnt/workflows/workflows/graphify-out/graph.json

# 2. Rebuild from Postgres
python -m app.cli.bootstrap

# 3. Verify
curl http://localhost:8000/api/v1/tools          # Returns all tools
curl http://localhost:8000/api/v1/capabilities    # Returns all capabilities
curl http://localhost:8000/api/v1/agents/templates # Returns all templates
curl http://localhost:8000/api/v1/memory           # Read/write works
curl http://localhost:8000/api/health              # Healthy

# 4. Output
# "Reconstruction complete: 30 tools, 45 capabilities, 12 templates, 150 memories"
```

When this passes, FlowManner is Postgres-native.
