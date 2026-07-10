# FlowManner Architecture Context Window Survival Guide

**Purpose:** Short-lived operational reference for agents whose context window gets tight while working on FlowManner. This is not a replacement for the full codebase; it is the map to recover quickly, avoid wrong assumptions, and continue the current architecture audit without re-reading everything.

**Created:** 2026-06-11
**Backend root:** `/opt/flowmanner/backend/app`
**Frontend source:** `/home/glenn/FlowmannerV2-frontend/`
**Canonical docs already in repo:**
- `/opt/flowmanner/Docs/FLOWMANNER-COMPLETE-SPEC-FOR-GPT.md`
- `/opt/flowmanner/Docs/FLOWMANNER_ARCHITECTURAL_ANALYSIS.md`
- `/opt/flowmanner/Docs/FLOWMANNER-ROADMAP.md`
- `/opt/flowmanner/docs/REBUILD-ROADMAP.md`
- `/opt/flowmanner/backend/H2-SUBSTRATE-HARDENING-REPORT.md`
- `/opt/flowmanner/Docs/FLOWMANNER-CANONICAL-KNOWLEDGE.md`

## 1. Hard Rules for Agents

1. You are on the **homelab**. Source edits happen here.
2. **Never edit files on the VPS directly.** VPS is a deployment target, not the source of truth.
3. Source edits only take effect after rebuild/deploy. Docker images have no code volume mounts.
4. Backend deploy: `bash /opt/flowmanner/deploy-backend.sh` from homelab. Use `timeout=300`; it handles backup, build, restart, health checks, and rollback.
5. Frontend deploy: `bash /opt/flowmanner/deploy-frontend.sh` from homelab. Takes roughly 4 minutes. Do not retry a timed-out deploy blindly; first check whether it completed.
6. Before relying on repo state, re-run: `git status --short && git branch --show-current && git rev-parse --short HEAD`.
7. Do not claim verification unless you actually ran the command in the current turn and saw the result.
8. English only.

## 2. Current Session Audit State

Active architecture audit plan:

| ID | Area | Status |
|---|---|---|
| `audit_structure_api` | Map backend repository structure, modules, dependencies, and API entry points | In progress |
| `audit_domain_agent` | Inspect domain model, CQRS/mission layer, agent runtime, tools, and workflow engines | Pending |
| `audit_data_async` | Inspect data architecture, migrations, indexing, transactions, and async queue design | Pending |
| `audit_report` | Synthesize findings into architecture audit document with diagrams, matrices, and scorecard | Pending |
| `audit_verify` | Verify report references and provide concise delivery summary | Pending |

Evidence already gathered:
- Backend has **745 Python files** under `/opt/flowmanner/backend/app`.
- Top-level module counts:
  - `api`: 135 files
  - `services`: 253 files
  - `models`: 49 files
  - `schemas`: 28 files
  - `tools`: 114 files
  - `tasks`: 17 files
  - `tests`: 51 files
- FastAPI app currently has **726 API routes** and **1 websocket route** when imported:
  - `/api/v1-legacy`: 538 routes
  - `/api/v2`: 151 routes
  - `/api/v3`: 31 routes
  - root docs/health/metrics: 6 routes
- Importing the app logged: `Router not available: triggers`, then v2 initialized successfully.
- `main_fastapi.py` includes routers at lines 333-358: health, v1, v2, v3.
- `api/v1/__init__.py` imports v1 routers with tiered failure handling:
  - CRITICAL: `auth`, `users`, `mission`, `chat`, `graph`, `browser`
  - STANDARD: most user-facing routes
  - OPTIONAL: `playground`, `admin_sandboxes`, `agent_personalities`, `community`, `integrations`, `marketplace`, `newsletter`
- `api/v2/__init__.py` includes auth, missions, agents, chat, workspaces, search, dashboard, integrations, openapi, blueprints, runs, regression.
- `api/v3/__init__.py` includes auth, workspaces, invitations, teams, workspace activity, workspace billing, OIDC, auth webhooks.

## 3. FastAPI Entry Points

### Main app

File: `backend/app/main_fastapi.py`

Important lines:
- Lines 78-106: FastAPI app construction and tags.
- Lines 108-137: middleware stack:
  - `AuthCookieMiddleware`
  - `ScopeValidationMiddleware`
  - CORS
  - security headers
  - audit logging
  - metrics
  - global rate limiting
- Lines 333-358: route registration:
  - health root and `/api`
  - v1 router
  - v2 router and v2 middleware/exception handlers
  - v3 router and v3 exception handlers
- Lines 360-388: GraphQL endpoint at `/api/v2/graphql` if `strawberry-graphql` is installed.
- Lines 473-539: resilient OpenAPI generation that skips routes with unresolved forward refs.

### v1 legacy router

File: `backend/app/api/v1/__init__.py`

Important lines:
- Lines 9-20: `RouterTier` enum.
- Lines 22-47: `_import_router()` with CRITICAL/STANDARD/OPTIONAL import behavior.
- Lines 50-57: CRITICAL routers.
- Lines 61-124: STANDARD routers.
- Lines 125-131: OPTIONAL routers.
- Lines 149-251: v1 API assembly under `prefix="/api"`.

Notable v1 route groups:
- Auth/users/sessions/2FA
- Agents/agent registry/agent capabilities/personalities
- Missions, mission advanced, mission decomposition
- Chat/browser/io
- Graphs/flows
- Workspaces/teams/invitations/messages/shares/activity
- Swarm/swarm protocol
- RAG/search/web search
- Integrations/webhooks/linear
- Sandbox/sandbox preview/admin sandboxes
- HITL/inbox
- Circuit breaker/cost attribution/plugins
- Substrate replay events

### v2 router

File: `backend/app/api/v2/__init__.py`

Important lines:
- Line 3: v2 is a redesign, not a wrapper around v1.
- Lines 16-28: core v2 routers.
- Lines 30-40: dashboard, integrations, openapi.
- Lines 42-47: Blueprint + Run endpoints.
- Lines 49-52: regression/assertion endpoints.

### v3 router

File: `backend/app/api/v3/__init__.py`

Important lines:
- Line 9: prefix `/api/v3`.
- Lines 11-27: auth, workspaces, invitations, teams, workspace activity, workspace billing, OIDC, auth webhooks.

### Response envelope

File: `backend/app/api/envelope.py`

- Lines 19-21: v2-style envelope:
  - `{"data": ..., "meta": ..., "error": None}`

## 4. API Version Mental Model

| Version | Prefix | Role | Notes |
|---|---|---|---|
| v1 | `/api/*` | Legacy everything-included API | 538 routes. Broad feature surface. Import failures are tiered. |
| v2 | `/api/v2/*` | Cleaner next-gen API | 151 routes. Standardized envelope, middleware, GraphQL, Blueprint+Run, regression endpoints. |
| v3 | `/api/v3/*` | Workspace-scoped cookie/scope API | 31 routes. Auth v3, workspaces, invitations, teams, workspace activity/billing. |

Known caution:
- v3 feature flags and scope enforcement exist, but do not assume every v3 endpoint is production-gated or fully wired without checking the route and middleware.

## 5. Backend Module Map

| Module | Files | What it contains |
|---|---:|---|
| `api/` | 135 | FastAPI routers, middleware, CQRS handler packages, response envelope |
| `services/` | 253 | Business logic: agents, missions, substrate, LLM routing, connectors, RAG, web search, swarm, self-improvement |
| `models/` | 49 | SQLAlchemy ORM models and migrations |
| `schemas/` | 28 | Pydantic request/response schemas |
| `tools/` | 114 | Tool implementations for agents and sandbox/browser/web/search workflows |
| `tasks/` | 17 | Celery tasks and background jobs |
| `workers/` | 2 | Celery worker app entry points |
| `middleware/` | 10 | App-level middleware: auth cookies, scope validation, idempotency, service auth, canary router |
| `websocket/` | 3 | Mission and presence websocket handlers |
| `integrations/` | 18 | Adapter base classes and third-party integrations |
| `governance/` | 11 | Controlflow, data governance, workflow config, tool handlers |
| `sdk/` | 9 | Runtime SDK and examples |
| `tests/` | 51 | Backend tests |

## 6. Core Execution Architecture

FlowManner has multiple overlapping execution concepts. Treat them as a transition, not as one clean model.

| Concept | DB/source location | Meaning |
|---|---|---|
| Mission | `models/mission_models.py`, `models/mission_advanced_models.py` | User-defined decomposable work unit. Legacy source of truth for mission APIs. |
| MissionTask | `models/mission_models.py` | Subtask under a mission. |
| Workflow/Graph | `models/graph.py`, `models/workflow_version_models.py` | Visual workflow/graph execution. |
| Swarm | `models/swarm.py`, `models/swarm_models.py` | Swarm/orchestrator execution concepts. |
| Substrate | `models/substrate_models.py`, `services/substrate/*` | Event-sourced execution layer and unified workflow DTOs. |
| Blueprint+Run | `services/blueprint_service.py`, `services/run_service.py`, `api/v2/blueprints.py`, `api/v2/runs.py` | Newer unified model being phased in. |

Key substrate files:
- `services/substrate/adapters.py` — converts Mission/Flow/Graph into unified `Workflow` DTO.
- `services/substrate/workflow_models.py` — `Workflow`, `WorkflowNode`, `WorkflowEdge`, `NodeType`, `WorkflowType`, `StrategyResult`.
- `services/substrate/executor.py` — `UnifiedExecutor`.
- `services/substrate/strategies/*` — solo, DAG, graph, langgraph, meta, pipeline, swarm strategies.
- `services/substrate/event_log.py` — append-only substrate event log.
- `services/substrate/replay_engine.py` or equivalent replay code in substrate package — verify exact filename if needed.
- `services/substrate/node_executor.py` — node-level execution.

Important finding from prior docs:
- Substrate is considered the most architecturally valuable part.
- H2 substrate hardening report says 133 tests across 7 files passed, but current audit should verify if needed before claiming.

## 7. CQRS Packages

There are internal CQRS handler packages under `api/`:

| Package | Files | Purpose |
|---|---|---|
| `api/_mission_cqrs/` | `base.py`, `commands.py`, `queries.py`, `audit.py`, `compat.py`, `deps.py`, `errors.py`, `AGENTS.md` | Internal mission command/query handlers. Routes should be thin shells over these handlers. |
| `api/_blueprint_cqrs/` | `base.py`, `commands.py`, `queries.py`, `deps.py`, `AGENTS.md` | Internal Blueprint/Run command/query handlers. |

Mission CQRS rules from `backend/app/api/_mission_cqrs/AGENTS.md`:
1. Routes must not contain business logic.
2. Single-commit mutations use `wrap_command()`.
3. Multi-commit flows are explicit and should not be wrapped blindly.
4. Audit calls are no-fail and non-blocking at the session level.
5. Cache invalidation is fire-and-forget via `_schedule_fire_and_forget()`.
6. Dual-writes to Blueprint/Run are fire-and-forget.
7. `USE_NEW_READS=1` routes mission reads through Blueprint/Run compat.
8. Workspace-aware access checks are mandatory.
9. Mission executions go through substrate, not the old `MissionExecutor`.
10. Subscription tier limits are checked for create and execute.
11. Analytics tracking is fire-and-forget.
12. Abort signals propagate to substrate.
13. `_schedule_fire_and_forget()` replaced deprecated `asyncio.ensure_future`.

Mission CQRS base:
- `CommandHandlerBase.tx()` commits on success and rolls back on exception.
- `CommandHandlerBase.wrap_command()` wraps mutations and maps infrastructure errors.
- `QueryHandlerBase` is a simple session holder.
- `_make_execution_status()` builds `MissionExecutionStatus`.

Blueprint CQRS base:
- Similar transaction wrapper.
- `BlueprintCommandHandlers` uses `BlueprintService`.
- `RunCommandHandlers` uses `RunService`.

## 8. Domain Agents and Agent Runtime

Relevant files/directories:
- `models/agent.py`
- `models/capability_models.py`
- `models/tool_catalog_models.py`
- `models/tool_models.py`
- `services/agent_service.py`
- `services/agent_registry_service.py`
- `services/capability_engine.py`
- `services/domain_agents/base_domain_agent.py`
- `services/domain_agents/biotech/agent.py`
- `services/domain_agents/finance/agent.py`
- `services/domain_agents/legal/agent.py`
- `services/nexus/agent_capability_registrar.py`
- `services/nexus/agent_templates.py`
- `services/nexus/capability_*`
- `services/unified_tools/*`
- `tools/*`

Agent system mental model:
- Agents are first-class entities with identity, personality, capabilities, and templates.
- Capabilities are bounded by capability tokens/registry patterns.
- Domain agents inherit a shared base and specialize by domain.
- Tools live in `tools/` and are surfaced through registries/adapters.
- Agent execution can flow through missions, substrate strategies, or direct agent APIs.

Audit questions:
- Which agent APIs are v1 vs v2?
- Are agent capabilities enforced consistently?
- Are domain agents actually wired into mission execution or mostly standalone?
- Are tool calls capability-bounded at runtime?
- Are agent templates marketplace-ready or still internal?

Verified findings:
- `agent_service.py` is the main catalog/template persistence path:
  - `list_agent_templates()` paginates `AgentTemplate` and supports `division`, `search`, `is_active`, and workspace filters (`backend/app/services/agent_service.py:398-488`).
  - `get_agent_template_by_slug()` resolves templates by slug with workspace scoping (`backend/app/services/agent_service.py:505-518`).
  - `create_agent_template()` and `update_agent_template()` write template metadata directly to DB; no explicit state-machine transition into `ACTIVE` or capability grant is enforced there (`backend/app/services/agent_service.py:520-636`).
- `agent_registry_service.py` is a separate capability-matching registry over `AgentCapability`, not a runtime agent orchestrator:
  - `register_or_update_capability()` upserts a single capability profile by `agent_id`, including task types, tools, confidence score, and embedding id (`backend/app/services/agent_registry_service.py:102-192`).
  - `match_agent_to_task()` first tries vector search via Qdrant, then falls back to text search, then applies required-tool filtering (`backend/app/services/agent_registry_service.py:194-326`).
  - This means the agent registry is best understood as a capability index, not the actual executor.
- `domain_agents` are lightweight standalone domain wrappers:
  - `BaseDomainAgent` defines `handle_task()`, `get_capabilities()`, and `get_tool_definitions()` (`backend/app/services/domain_agents/base_domain_agent.py:10-35`).
  - `LegalAgent`, `FinanceAgent`, and `BiotechAgent` each hard-code domain-specific prompts/capabilities/tools (`backend/app/services/domain_agents/legal/agent.py:8-42`, `backend/app/services/domain_agents/finance/agent.py:8-42`, `backend/app/services/domain_agents/biotech/agent.py:8-42`).
  - `DOMAIN_REGISTRY` is a simple dict factory; it does not register agents into DB, grant capabilities, or wire them into substrate (`backend/app/services/domain_agents/__init__.py:15-28`).
- `agent_parser.py` is a deterministic markdown-to-template loader:
  - It parses YAML frontmatter, normalizes slug/name, and returns `AgentDefinition` objects (`backend/app/services/agent_parser.py:1-103`).
  - Static verification in this turn parsed **185 markdown agent definitions** under `backend/agent_definitions` with **0 YAML parse errors**.
  - Definition counts by parent directory: `specialized`: 41, `engineering`: 29, `marketing`: 30, `academic`: 5, `finance`: 5, `game-development`: 5, `product`: 5, `sales`: 8, `design`: 8, `project-management`: 6, `spatial-computing`: 6, `support`: 6, `testing`: 8, `blender`: 1, `browser`: 1, `godot`: 3, `paid-media`: 7, `roblox-studio`: 3, `unity`: 4, `unreal-engine`: 4.
- `agent_templates.py` is an internal marketplace-like template list, not yet DB-hydrated:
  - It defines 10 hard-coded `AgentTemplate` instances and conversion helpers (`backend/app/services/nexus/agent_templates.py:79-478`, `backend/app/services/nexus/agent_templates.py:481-550`).
  - It references tool ids such as `web_search`, `code_executor`, and `workflow_builder`, but this file does not validate them against the unified tool registry.
- `capability_registry.py` centralizes capability execution:
  - `CapabilityRegistry.register()` stores capabilities by id and category, and `execute()` delegates to the registered handler (`backend/app/services/nexus/capability_registry.py:76-127`, `backend/app/services/nexus/capability_registry.py:167-210`).
  - `hydrate_from_db()` loads enabled capabilities from `Capability` DB rows, resolves dotted handler refs via `resolve_handler_ref()`, and falls back to passthrough handlers when no handler exists (`backend/app/services/nexus/capability_registry.py:230-288`).
- `tool_registry.py` exposes a singleton tool registry:
  - `register_tool()` / `unregister_tool()` manage tools by id, and `execute_tool()` validates input with Pydantic before calling the tool (`backend/app/services/unified_tools/tool_registry.py:35-131`).
  - The registry has optional tool discovery integration through `ToolDiscoveryService`, but `execute_tool()` itself does not enforce capability tokens (`backend/app/services/unified_tools/tool_registry.py:104-131`).
- `capability_engine.py` has the token/budget model but needs runtime wiring verification:
  - `issue_token()` creates scoped `CapabilityToken`s and `verify_token()` checks resource/action, expiration, revocation, and attenuation proof (`backend/app/services/capability_engine.py:162-246`).
  - `execute_with_capability()` is the intended enforcement path: it verifies a token, checks budget, then calls the capability handler (`backend/app/services/capability_engine.py:248-308`).
  - The current audit has not yet traced every tool call site to this enforcement path; treat token enforcement as a hypothesis until route-level tracing is complete.

Architecture implications:
- Agent definitions, DB templates, marketplace templates, domain-agent wrappers, capability registry, and tool registry are overlapping but not fully unified.
- The safest current mental model is: markdown definitions are catalog content; `AgentTemplate` is persisted catalog metadata; `AgentCapability` is a matching index; `CapabilityRegistry` is the execution registry; `domain_agents` are standalone domain wrappers; `tools` are executable primitives.
- Main risk: there is no single source of truth connecting an agent definition → persisted template → granted capability → runtime token → tool execution → substrate/mission executor.

## 9. LLM Routing and Providers

Relevant files:
- `services/llm_router.py`
- `services/model_router.py`
- `services/providers/provider_factory.py`
- `services/providers/deepseek_service.py`
- `services/providers/openrouter_service.py`
- `services/chat_service.py`
- `services/cost_tracker.py`
- `services/budget_enforcer.py`
- `services/langgraph/cost_aware_router.py`

Mental model:
- FlowManner supports BYOK and multiple providers.
- There is a 3-layer routing architecture described in prior docs:
  1. Service-level provider resolution.
  2. Model routing/cost optimization.
  3. LangGraph cost-aware routing.
- Cost and budget enforcement are architectural requirements, not optional polish.

Audit questions:
- Where exactly are provider decisions made?
- Are fallbacks deterministic and observable?
- Are cost limits enforced before and during execution?
- Are provider failures classified into the Nexus error taxonomy?

## 10. Data Architecture

Relevant files/directories:
- `models/*`
- `migrations/versions/*`
- `database.py`
- `services/substrate/event_log.py`
- `services/substrate/replay_engine.py`
- `services/substrate/executor.py`
- `tasks/*`
- `workers/*`

Known from prior docs:
- Total DB tables in prior audit: 123.
- Execution-related overlap:
  - Mission: `missions`, `mission_tasks`, `mission_logs`, `mission_improvements`
  - Workflow/Graph: `workflows`, `workflow_executions`, `workflow_states`
  - Workflow versioning: `workflow_versions`, `execution_events`
  - Orchestrator/Swarm: `orchestrator_executions`, `orchestrator_tasks`, `swarm_pipelines`, `swarm_profiles`, `swarm_agents`, `swarm_tasks`, `swarm_consensus_rounds`
  - Substrate: `substrate_events`
- `services/substrate/adapters.py` maps Mission/Flow/Graph into the unified substrate DTO.
- `substrate_events` is the append-only event log for substrate runs.

Audit questions:
- Which tables are canonical source of truth vs transition/dual-write?
- Which migrations are active and applied?
- Which tables have indexes, constraints, triggers?
- Which writes are transactional vs fire-and-forget?
- Which async jobs are durable vs in-memory?
- Does RabbitMQ/Celery have retries/idempotency?

## 11. Async and Queue Design

Relevant files:
- `tasks/celery_app.py`
- `tasks/tasks.py`
- `tasks/base_task.py`
- `tasks/batch_processing.py`
- `tasks/mission_execution.py`
- `tasks/init_rabbitmq.py`
- `workers/celery_app.py`
- `services/sse_service.py`
- `services/trigger_service.py`
- `services/webhook_handler/*`

Mental model:
- Celery + RabbitMQ handles background jobs.
- Redis is used for cache/pub-sub/SSE broadcasting.
- WebSockets stream mission/presence updates.
- Some side effects are fire-and-forget coroutines, not durable queue jobs.

Audit questions:
- Which side effects are durable queue tasks vs `asyncio.create_task()`?
- What retry policies exist?
- Are idempotency keys used consistently?
- Are async cache invalidations safe if they fail?
- Is RabbitMQ durable for critical mission state transitions?

## 12. Auth and Security

Relevant files:
- `middleware/auth_cookie.py`
- `middleware/scope_validator.py`
- `middleware/service_auth.py`
- `api/v3/auth.py`
- `api/v3/auth_cookies.py`
- `api/v3/auth_webhooks.py`
- `api/v3/auth_oidc.py`
- `api/v1/auth.py`
- `api/v1/sessions.py`
- `api/v1/api_keys.py`
- `api/v1/byok.py`

Recent state from `docs/REBUILD-ROADMAP.md`:
- Dual-auth `fm_tokens` was eliminated from live frontend source as of 2026-06-10.
- Sandbox preview auth chain was fixed and deployed.
- NextAuth/httpOnly cookie model is intended as the single auth source, but v1 still has bearer/JWT routes and v3 has cookie/scope routes.

Audit questions:
- Which endpoints use which auth scheme?
- Are v1 and v3 auth semantics compatible?
- Are scopes enforced on all v3 routes?
- Are service-to-service auth and user auth separated?
- Are cookie paths and refresh-token revocation correct across all routes?

## 13. Observability

Relevant files:
- `main_fastapi.py`
- `api/middleware/audit.py`
- `api/middleware/metrics.py`
- `api/middleware/rate_limit.py`
- `api/middleware/security_headers.py`
- `api/middleware/versioning.py`
- `core/telemetry.py`
- `core/metrics.py`
- `core/slo.py`
- `core/slo_dashboard.py`
- `observability/cost_engine.py`
- `observability/intervention_distance.py`
- `services/sentry/*`
- `services/langfuse_metrics.py`

Known:
- Structlog is configured in `main_fastapi.py`.
- Middleware includes audit, metrics, rate limiting, security headers.
- OpenTelemetry is opt-in via `OTLP_ENDPOINT`.
- OpenAPI generation is resilient to route schema errors.

Audit questions:
- Are request IDs propagated across middleware, logs, Celery, and LLM calls?
- Are SLO dashboards actually live?
- Are alerts wired?
- Do 500s include actionable error codes or stack traces?
- Are cost/token metrics complete?

## 14. Known Warnings / Active Risks

Treat these as hypotheses unless verified in the current turn:
- Production API may still have user-facing 500s in chat code execution or sandbox preview paths.
- Some v1 routers are optional and may be absent depending on dependencies.
- v2/v3 are not complete replacements for v1; expect overlapping endpoints.
- Substrate is valuable but still in transition with Blueprint+Run dual-writes.
- Some prior docs mention fixed issues; verify before relying on them for production claims.
- The app import logs `Router not available: triggers`; investigate if trigger functionality is expected.

## 15. Quick Commands

Use these to recover context quickly.

```bash
# Repo state
git status --short && git branch --show-current && git rev-parse --short HEAD

# Count backend Python files by top-level module
python3 - <<'PY'
from pathlib import Path
root=Path('/opt/flowmanner/backend/app')
for d in sorted([p for p in root.iterdir() if p.is_dir()]):
    files=list(d.rglob('*.py'))
    print(f'{d.name:28} {len(files):3} files')
print('total', len(list(root.rglob('*.py'))))
PY

# Import app and count FastAPI routes
PYTHONPATH=/opt/flowmanner/backend python3 - <<'PY'
from fastapi.routing import APIRoute, APIWebSocketRoute
from collections import Counter, defaultdict
from app.main_fastapi import app
api_routes=[r for r in app.routes if isinstance(r, APIRoute)]
ws_routes=[r for r in app.routes if isinstance(r, APIWebSocketRoute)]
print('api_routes', len(api_routes))
print('websocket_routes', len(ws_routes))
print('methods', Counter(m for r in api_routes for m in r.methods if m not in {'HEAD','OPTIONS'}))
by_prefix=defaultdict(list)
for r in api_routes:
    p=r.path
    if p.startswith('/api/v3'): prefix='/api/v3'
    elif p.startswith('/api/v2'): prefix='/api/v2'
    elif p.startswith('/api/'): prefix='/api/v1-legacy'
    elif p.startswith('/api'): prefix='/api-root'
    else: prefix='root'
    by_prefix[prefix].append(r)
for prefix in sorted(by_prefix):
    methods=Counter(m for r in by_prefix[prefix] for m in r.methods if m not in {'HEAD','OPTIONS'})
    print(prefix, len(by_prefix[prefix]), dict(methods))
PY

# Inspect OpenAPI route paths without loading browser
PYTHONPATH=/opt/flowmanner/backend python3 - <<'PY'
from fastapi.routing import APIRoute
from app.main_fastapi import app
for r in app.routes:
    if isinstance(r, APIRoute):
        print(','.join(sorted(m for m in r.methods if m not in {'HEAD','OPTIONS'})), r.path)
PY

# Backend tests
cd /opt/flowmanner/backend
PYTHONPATH=/opt/flowmanner/backend python -m pytest -q

# Frontend checks
cd /home/glenn/FlowmannerV2-frontend
npm run lint
npm run build
```

## 16. What to Read Next If Context Is Tight

Minimum files for `audit_structure_api`:
1. `backend/app/main_fastapi.py`
2. `backend/app/api/v1/__init__.py`
3. `backend/app/api/v2/__init__.py`
4. `backend/app/api/v3/__init__.py`
5. `backend/app/api/envelope.py`
6. `backend/app/api/_mission_cqrs/AGENTS.md`
7. `backend/app/api/_blueprint_cqrs/AGENTS.md`
8. `backend/app/api/_mission_cqrs/base.py`
9. `backend/app/api/_blueprint_cqrs/base.py`

Minimum files for `audit_domain_agent`:
1. `backend/app/services/agent_service.py`
2. `backend/app/services/agent_registry_service.py`
3. `backend/app/services/domain_agents/base_domain_agent.py`
4. `backend/app/services/nexus/capability_registry.py`
5. `backend/app/services/unified_tools/tool_registry.py`
6. `backend/app/api/v1/agent.py`
7. `backend/app/api/v2/agents.py`

Minimum files for `audit_data_async`:
1. `backend/app/models/mission_models.py`
2. `backend/app/models/substrate_models.py`
3. `backend/app/services/substrate/event_log.py`
4. `backend/app/services/substrate/executor.py`
5. `backend/app/tasks/celery_app.py`
6. `backend/app/tasks/tasks.py`
7. `backend/app/workers/celery_app.py`
8. `backend/app/migrations/versions/` top files by modification date

Minimum files for `audit_report`:
1. `Docs/FLOWMANNER-COMPLETE-SPEC-FOR-GPT.md`
2. `Docs/FLOWMANNER_ARCHITECTURAL_ANALYSIS.md`
3. `docs/REBUILD-ROADMAP.md`
4. `Docs/FLOWMANNER-ROADMAP.md`
5. `backend/H2-SUBSTRATE-HARDENING-REPORT.md`
6. This file

## 17. Report Writing Checklist

When producing the final architecture audit:
- Use actual line references for every claim.
- Distinguish verified current state from prior-doc claims.
- Include diagrams:
  - three-machine topology
  - API version split
  - request path
  - execution engine overlap
  - CQRS handler flow
  - substrate event flow
- Include matrices:
  - module map
  - API route counts by version
  - execution concepts and canonical source
  - risk scorecard
- Include scorecard with confidence levels:
  - High: read source and ran import/count/test command.
  - Medium: traced API route but not runtime-tested.
  - Low: inferred from docs or names only.
- Do not overclaim production behavior unless verified live.

## 18. Current Verified Facts From This Session

- `git status --short` was clean at session start.
- Current branch: `main`.
- Current HEAD: `f0c34fb`.
- Backend Python file count: 745.
- FastAPI import route count: 726 API routes, 1 websocket route.
- FastAPI route split:
  - `/api/v1-legacy`: 538
  - `/api/v2`: 151
  - `/api/v3`: 31
  - root: 6
- Import logged `Router not available: triggers`.
- v1 CRITICAL routers: `auth`, `users`, `mission`, `chat`, `graph`, `browser`.
- v1 has tiered router import handling and includes v1 routes under `/api`.
- v2 includes Blueprint+Run and regression endpoints.
- v3 includes auth/workspaces/invitations/teams/workspace activity/workspace billing/OIDC/auth webhooks.
- Domain-agent audit completed in this guide:
  - `agent_service.py`, `agent_registry_service.py`, `domain_agents/*`, `agent_parser.py`, `nexus/agent_templates.py`, `nexus/capability_registry.py`, `unified_tools/tool_registry.py`, and `capability_engine.py` were inspected.
  - `backend/agent_definitions` currently has **185** parseable markdown agent definitions with **0 YAML parse errors**.
  - Agent definitions/templates/capabilities/tools are overlapping but not yet unified into one runtime source of truth.
