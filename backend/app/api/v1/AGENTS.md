# Flowmanner — `app/api/v1` Agent Instructions

## Purpose

This is the local contract for `backend/app/api/v1/` — the **legacy-stable HTTP surface** of Flowmanner. 80+ router files, mounted under `/api/v1/...` and protected by `APIVersioningMiddleware` (v1 is `DEFAULT_VERSION`, v2 is `CURRENT_VERSION`).

An agent landing here should be able to:

1. Find the right router for a domain (auth, missions, chat, workspaces, integrations, etc.) without listing the directory.
2. See, for each router, **whether it has migrated to `_mission_cqrs`**, **whether it inlines old executor logic** (`MissionExecutor`, `dag_executor`, `graph_executor`, `SwarmOrchestrator`, `langgraph/agent`, `nexus/meta_loop_orchestrator`), or **whether it is executor-free CRUD** (no migration needed).
3. Know the migration paths and the order in which routers should be rewritten.

The companion documents are:

- `backend/app/api/AGENTS.md` — versioning policy, envelope rules, CQRS pattern (read first).
- `backend/app/api/_mission_cqrs/AGENTS.md` — the destination for any non-trivial mission route.

## Ownership

### Import tiering (`v1/__init__.py`)

The `__init__.py` imports every router with one of three tiers (see `RouterTier` enum):

| Tier | Failure mode | Routers |
|------|--------------|---------|
| `CRITICAL` | `logger.critical()` + `raise` (fails startup) | `auth`, `users`, `mission`, `chat`, `graph`, `browser` |
| `STANDARD` | `logger.warning()` (warns, continues) | All routers not listed below |    | `OPTIONAL` | `logger.info()` (expected to be absent in some deployments) | `playground`, `admin_sandboxes`, `agent_personalities`, `community`, `integrations`, `newsletter` |


A few routers are imported inline with `try/except` because they live outside the v1 directory:

- `web_search_enhanced_router` — `app.services.web_search.web_search_routes_enhanced`
- `notification_router` — `app.services.notification_service`

The `substrate_router` (`app.api.v1.substrate`) is imported at the bottom of `__init__.py` and represents the **H5.2 replay-events surface** — not the execution path.

### Router inventory by domain

Grouped by responsibility. **Bold** = has migration status worth tracking. Numbers in [brackets] = approximate line count.

#### Auth & sessions (CRITICAL for auth/users)

| Router | Prefix | Notes |
|--------|--------|-------|
| `auth.py` | `/auth` | Login, logout, refresh, 2FA setup. Standard pattern. |
| `users.py` | `/users` | User CRUD. |
| `sessions.py` | `/auth/sessions` | Auth v3 session listing + revocation. |
| `two_fa.py` | `/auth/2fa` | TOTP 2FA. |
| `oidc.py` | `/auth/oidc` | OIDC SSO. |
| `onboarding.py` | `/onboarding` | Onboarding flow. |
| `audit_log.py` | `/audit/logs` | Audit log reads. |
| `roles.py` | `/roles` | RBAC. |
| `delegations.py` | `/delegations` | Permission delegation. |

#### Missions (CRITICAL for mission.py)

| Router | Prefix | **Migration status** |
|--------|--------|----------------------|
| **`mission.py`** | `/missions` | ✅ **Fully CQRS-delegated** (25 references to `get_mission_commands` / `get_mission_queries`). All 14 commands + 14 queries route through `_mission_cqrs/`. The router is a thin DI shell. |
| `mission_advanced_routes.py` | `/missions/advanced` | ❌ **Inlines DB ops** (templates, node groups, versions, export/import). Does not use CQRS. Migration candidate. |
| `mission_decomposition_routes.py` | `/missions/decomposition` | ❌ **Inlines DAG logic** — calls `app.services.decomposition_service.decompose_mission` and `execute_dag` directly. Old `dag_executor` path. Migration candidate (target: substrate `DAGStrategy`). |
| **`substrate.py`** | `/missions` (H5.2) | ⚠️ **Uses substrate services directly** (event log, replay engine, assertion engine). This is the replay/events API, not an execution path — keep on direct substrate services. |
| `circuit_breaker.py` | `/missions` | Per-mission circuit breaker CRUD. |
| `circuit_breaker_router` registered in `__init__.py` | same as above | — |

#### Chat, agents, AI

| Router | Prefix | Notes |
|--------|--------|-------|
| `chat.py` | `/chat` | CRITICAL. Chat streaming + tool calling. Uses `chat_service` directly. |
| `io.py` | `/chat` | Chat IO. |
| `sandbox.py` | `/chat` | Sandbox-mode chat. |
| `sandbox_preview.py` | `/sandbox` | Sandbox preview API. |
| `playground.py` | `/playground` | OPTIONAL. |
| `admin_sandboxes.py` | `/admin/sandboxes` | OPTIONAL. |
| `browser.py` | `/browser` | CRITICAL. Browser automation. |
| `agent.py` | `/agents` | Agent CRUD. |
| `agent_registry.py` | `/agent-registry` | Runtime agent registry. |
| `agent_capabilities.py` | `/agent-capabilities` | Agent capabilities API. |
| `agent_personalities.py` | `/agent-personalities` | OPTIONAL. |
| `llm.py` | `/ai` (via `__init__.py` prefix override) | LLM inference API. |
| `llm_advanced.py` | `/llm-advanced` | Advanced LLM features. |
| `rag.py` | `/v1/rag` | RAG API. |
| `evaluation.py` | `/evaluation` | LLM-as-judge eval. |
| `memory.py` | `/memory` | Memory reads. |

#### Workflows / execution

| Router | Prefix | **Migration status** |
|--------|--------|----------------------|
| `graph.py` | `/graphs` | CRITICAL. Adds `Deprecation` headers via `_add_deprecation_headers`. Inlines graph logic — migration candidate. |
| `orchestration.py` | `/orchestration` | Inlines orchestration. Migration candidate. |
| **`flow_compat.py`** | `/flow` (via `__init__.py` prefix) | ❌ **Inlines `GraphInterpreter`** from `app.services.graph_executor` (old graph executor). Migration candidate (target: substrate `GraphStrategy`). |
| **`swarm.py`** | `/swarm` | ❌ **Inlines `SwarmOrchestrator`** from `app.services.swarm.orchestrator`. Migration candidate (target: substrate `SwarmStrategy`). |
| **`swarm_protocol.py`** | `/swarm` (prefix `/protocol` then `__init__.py` `/swarm`) | ❌ **Inlines `DebateProtocol` / `EscalationChain` / `HandoffProtocol`** from `app.services.swarm.*`. Migration candidate. |
| `templates.py` | `/templates` | Workflow templates. |
| `triggers.py` | `/triggers` | Cron / event triggers. |
| `webhooks.py` | `/webhooks` | Webhook delivery. |
| **`plugins.py`** | `/plugins` | ⚠️ Imports `ExecutionContext` from `app.services.graph_executor` (type-only import, line 478). Functional logic is plugin-runtime, not graph. Migration is "leave the type import or move it to substrate". |

#### Workspaces (multi-tenant)

| Router | Prefix | Notes |
|--------|--------|-------|
| `workspace.py` | `/workspaces` (+ `/teams`, `/invitations` sub-routers in the same file) | The largest router file. Multi-router: `workspace_router`, `team_router`, `invitation_router`. |
| `workspace_activity.py` | `/workspaces` | Activity log. |
| `workspace_messages.py` | `/workspaces` | Workspace chat. |
| `workspace_shares.py` | `/workspace-shares` | Cross-workspace shares. |
| `presence_api.py` | `/workspaces` (prefix `""` in source, registered as `/workspaces` in `__init__.py`) | Presence. |

#### Files, search, observability

| Router | Prefix | Notes |
|--------|--------|-------|
| `file.py` | `/file` + `/files` (sub-router) | File CRUD. |
| `search.py` | `/search` | Cross-collection search. |
| `tools.py` | `/tools` | Tool catalog. |
| `data_export.py` | `/data-export` | GDPR export. |
| `feature_flags.py` | `/feature-flags` | Feature flags. |
| `analytics.py` | `/analytics` (via `__init__.py` prefix) | Analytics rollups. |
| `stats.py` | (no prefix) | Top-level stats. |
| `dashboard.py` | `/dashboard` | Dashboard data. |
| `observability.py` | (no prefix) | Metrics + traces. |
| `reliability.py` | (no prefix) | Reliability checks. |
| `rate_limits.py` | `/rate-limits` | Admin: rate limit CRUD. |
| `usage.py` | `/v1/usage` | Usage API. |

#### Integrations & external

| Router | Prefix | Notes |
|--------|--------|-------|
| `integrations.py` | `/integrations` | OPTIONAL. |
| `linear.py` | `/linear` | Linear sync API. |
| `community.py` | `/community` | OPTIONAL. |
| `newsletter.py` | `/newsletter` | OPTIONAL. |
| `byok.py` | `/byok` (via `__init__.py` prefix) | BYOK API key CRUD. |
| `api_keys.py` | `/api-keys` + `/user/keys` | Workspace + user API keys. |
| `subscription.py` | `/subscription` | Subscription. |
| `cost_attribution.py` | `/costs` | Cost attribution. |
| `webhooks.py` | (already in workflows) | — |
| `changelog.py` | `/changelog` | Product changelog. |
| `roadmap.py` | `/roadmap` | Public roadmap. |
| `votes.py` | `/votes` | Roadmap voting. |

#### HITL / notifications / governance

| Router | Prefix | Notes |
|--------|--------|-------|
| `hitl.py` | `/inbox` | Human-in-the-loop inbox. |
| `circuit_breaker.py` | (already in missions) | — |

#### Admin

| Router | Prefix | Notes |
|--------|--------|-------|
| `admin.py` | `/admin` | Admin surface. |
| `admin_sandboxes.py` | `/admin/sandboxes` | OPTIONAL. |
| `playground.py` | (already in chat) | — |

## Audit results — migration status (May 2026)

This is the load-bearing section. **Bolded** entries are the ones that still need work.

### ✅ Delegated to `_mission_cqrs` (the target pattern)

| Router | Coverage | Notes |
|--------|----------|-------|
| `mission.py` | 100% | All 14 commands + 14 queries route through `MissionCommandHandlers` / `MissionQueryHandlers`. The router is a 3-5 line DI shell per endpoint. **Reference implementation.** |

### ⚠️ Direct substrate access (correct, NOT a CQRS target)

| Router | What it does | Why it stays on substrate services directly |
|--------|--------------|----------------------------------------------|
| `substrate.py` | Replay events, rebuild state, single-event lookup, assertion results | These are read-only substrate primitives; the CQRS package is for mission mutations, not substrate introspection. Keep `get_event_log()` / `get_replay_engine()` / `get_assertion_engine()` direct. |

### ❌ Inlines old executor logic — migration candidates

| Router | Old executor inlined | Target substrate strategy | Migration complexity |
|--------|----------------------|---------------------------|----------------------|
| `mission_decomposition_routes.py` | `app.services.decomposition_service.decompose_mission` + `execute_dag` (uses `dag_executor`) | `DAGStrategy` + `dag.SoloStrategy` decomposition | Medium — needs to convert request body to `Workflow` + `WorkflowNode` list, call `UnifiedExecutor.execute()` |
| `flow_compat.py` | `app.services.graph_executor.GraphInterpreter` | `GraphStrategy` | Medium-High — graph nodes have `{{node_id.output.field}}` interpolation that needs to map to substrate context |
| `graph.py` | `graph_executor` (via `graph_service`) | `GraphStrategy` | Medium |
| `swarm.py` | `app.services.swarm.orchestrator.SwarmOrchestrator` | `SwarmStrategy` | High — swarm has its own debate/escalation/handoff protocols that need substrate-level mapping |
| `swarm_protocol.py` | `app.services.swarm.{debate,escalation,handoff}_protocol` | `SwarmStrategy` (or new strategy) | High — protocol semantics need preservation |
| `orchestration.py` | `nexus/orchestrator.py` (nexus subsystem) | `MetaStrategy` (or new orchestration strategy) | High — orchestration has its own memory + observability integration |
| `mission_advanced_routes.py` | Pure CRUD on `MissionTemplate`, `NodeGroup`, `MissionVersion` | Not executor-related; should become a v2 router with a CQRS-style split, or stay as standalone CRUD | Low (no executor to migrate, just needs an envelope + better tests) |

### ✅ Executor-free CRUD (no migration needed)

The remaining ~70 routers are CRUD endpoints that don't touch any executor. They are fine as-is unless they need new features:

- All auth/session routers (`auth`, `users`, `sessions`, `two_fa`, `oidc`, `onboarding`, `audit_log`, `roles`, `delegations`)
- Workspace routers (`workspace`, `workspace_activity`, `workspace_messages`, `workspace_shares`, `presence_api`)
- File + search + tools (`file`, `search`, `tools`, `data_export`, `feature_flags`)
- Analytics + observability (`analytics`, `stats`, `dashboard`, `observability`, `reliability`, `rate_limits`, `usage`)
- Integrations + external (`integrations`, `linear`, `community`, `newsletter`, `byok`, `api_keys`, `subscription`, `cost_attribution`, `webhooks`, `changelog`, `roadmap`, `votes`)
- HITL + circuit breaker + admin (`hitl`, `circuit_breaker`, `admin`, `admin_sandboxes`, `playground`)
- AI service routers (`chat`, `io`, `sandbox`, `sandbox_preview`, `browser`, `agent`, `agent_registry`, `agent_capabilities`, `agent_personalities`, `llm`, `llm_advanced`, `rag`, `evaluation`, `memory`)
- Templates + triggers + webhooks (`templates`, `triggers`, `webhooks`)
- Sandbox + admin-sandboxes (`sandbox`, `admin_sandboxes`, `playground`)

These routers may need **envelope migration** (v1 un-enveloped → v2 standardized envelope) if they are intended to be exposed via v2, but they don't need executor migration.

## Local Contracts

These rules apply to the v1 router layer, on top of `backend/AGENTS.md`, `backend/app/api/AGENTS.md`, and `backend/app/api/_mission_cqrs/AGENTS.md`.

1. **v1 routes are immutable in shape.** Do not change v1 response bodies. If a v1 contract is wrong, freeze v1 and add a v2 endpoint.
2. **v1 routes for missions MUST be DI shells calling `_mission_cqrs` handlers.** No route may inline `MissionExecutor`, `mission_service.create_mission`, or any direct ORM mutation on `Mission` / `MissionTask` / `MissionLog` / `MissionTemplate`. The single exception is `mission_advanced_routes.py`, which is on the migration backlog (see audit table).
3. **Mission v1 routes inject `_add_deprecation_headers` as a router-level dependency.** This is what makes the v1 → v2 deprecation visible to clients (`Deprecation: true`, `Sunset: 2026-09-01`, `Link: </api/v2/blueprints>; rel="successor-version"`). New v1 mission routes should inherit the same `dependencies=[Depends(_add_deprecation_headers)]` declaration.
4. **Graph v1 routes also add deprecation headers** (see `graph.py:46` `_add_deprecation_headers`).
5. **The 6 CRITICAL routers (`auth`, `users`, `mission`, `chat`, `graph`, `browser`) MUST import on startup.** Any import error in these is fatal. If you add a new CRITICAL router, register it in `_import_router(... tier=RouterTier.CRITICAL)` and add the include line at the top of the registration list in `__init__.py`.
6. **Prefix overrides happen in `__init__.py`.** A few routers declare their own prefix (e.g. `swarm_protocol_router` has `/swarm/protocol`); `__init__.py` may strip and re-prefix them. When changing a router's internal prefix, check that the `include_router(...)` call in `__init__.py` still resolves correctly.
7. **WebSocket endpoints live in `app.websocket/`, not here.** v1 routers only mount HTTP/SSE. (See `substrate.py:147` for the SSE-emitter pattern if you need to add one.)
8. **v1 routes do NOT use the v2 envelope.** They return native FastAPI `JSONResponse` / Pydantic models. The `APIVersioningMiddleware` sets `X-API-Version: v1` automatically. The deprecation headers come from the route-level `dependencies` not from the middleware.
9. **Workspace access checks are mandatory for any mission route.** Even if you delegate to `_mission_cqrs`, the handler's `require_mission_access()` runs first (already enforced in every CQRS command/query method). Do not add a parallel check in the route.
10. **Audit log writes go through `_mission_cqrs.audit.AuditService`** (for missions) or `app.api.middleware.audit.log_event()` (for everything else). Do not write to `MissionLog` directly from a route.

## Work Guidance

### The migration order (priority queue)

When picking the next router to migrate off inline executor logic, work in this order:

1. **`mission_advanced_routes.py`** — Lowest risk. Pure CRUD. Promote to v2 envelope + split into a `_mission_advanced_cqrs` package mirroring `_mission_cqrs/`. No executor to migrate. This builds the muscle for the rest.
2. **`mission_decomposition_routes.py`** — The DAG path. Migrate to `substrate.DAGStrategy` by:
   - Convert request body to `Workflow(type=DAG, nodes=[...], edges=[...])` using `decomposition_service` to produce the node list, then hand off to `UnifiedExecutor.execute()`.
   - The `decomposition_service` itself stays (it's the planner); only the executor path moves.
3. **`flow_compat.py` + `graph.py`** — Graph path. Both inline `GraphInterpreter` / `graph_executor`. The `{{node_id.output.field}}` interpolation needs to be reproduced in substrate context. Migrate together (or in one PR) so the interpolation semantics are consistent.
4. **`swarm.py` + `swarm_protocol.py`** — Swarm path. The debate / escalation / handoff protocols may need to live as substrate strategy helpers (mirroring the way `swarm_pipeline/phases/*.py` are preserved as helpers for `PipelineStrategy` in the H5.1 design).
5. **`orchestration.py`** — Nexus orchestration. Last because it has the deepest integration with `nexus/` memory + observability.

### Migration recipe — `mission_advanced_routes.py` (the easiest first)

1. Create `backend/app/api/_mission_advanced_cqrs/` with `base.py`, `commands.py`, `queries.py`, `deps.py` mirroring `_mission_cqrs/`.
2. Move the templates / node-groups / versions / export-import logic into handler methods.
3. Rewrite the v1 routes as 3-5 line DI shells.
4. Add `v2/mission_advanced.py` that re-exports the same handlers under the v2 envelope.
5. Keep v1 response shape unchanged.

### Migration recipe — `mission_decomposition_routes.py` (DAG)

1. Build a `Workflow(type=DAG, nodes=..., edges=...)` from the request body. Use the existing `decomposition_service` to compute the node list.
2. Call `get_unified_executor().execute(db, workflow)`.
3. Map `StrategyResult` → existing response shape (`ExecuteDAGResponse` with `completed` / `failed` / `skipped` / `errors`).
4. Keep the v1 response shape unchanged. Add v2 endpoint later with a richer shape.

### Promoting a v1 inline route to the CQRS path

See `backend/app/api/_mission_cqrs/AGENTS.md` → "Promoting a v1 inline route to the CQRS path" for the full recipe. Short version:

1. Add a `MissionCommandHandlers` / `MissionQueryHandlers` method (or create a sibling CQRS package if the domain isn't mission).
2. Rewrite the route to a thin DI shell.
3. Keep the v1 path / method / response shape unchanged.
4. If the v1 shape is unkeepable, freeze v1 and add a v2 endpoint.

### Adding a new v1 route (last resort)

If you must add a v1 route (e.g., quick bugfix before a v2 cutover), follow `backend/app/api/AGENTS.md` v1 rules + the local contracts above. Do NOT inline executor logic; delegate to `_mission_cqrs` for missions, or to substrate services directly for replay/event APIs.

### The deprecation timeline

- v1 mission endpoints: `Deprecation: true`, `Sunset: 2026-09-01` (per `mission.py:34`).
- v1 graph endpoints: same deprecation, sunset not pinned in code.
- All other v1 endpoints: no deprecation yet. Start adding headers in any router you touch.

## Verification

```bash
# Run the v1 mission endpoint tests (the reference CQRS-delegated router)
docker compose exec backend pytest app/tests/test_mission_api.py \
                                 app/tests/test_mission_advanced_api.py \
                                 app/tests/test_mission_execution_api.py \
                                 app/tests/test_mission_decomposition_routes.py -v

# Run the substrate (H5.2 replay) tests
docker compose exec backend pytest app/tests/test_substrate_event_log.py \
                                 app/tests/test_substrate_event_log_integration_pg.py \
                                 app/tests/test_substrate_replay.py -v

# Run the per-router tests (auth, chat, workspace, etc.)
docker compose exec backend pytest app/tests/test_auth_api.py \
                                 app/tests/test_chat_streaming.py \
                                 app/tests/test_io_api.py \
                                 app/tests/test_marketplace_v2.py \
                                 app/tests/test_workspace_overview.py \
                                 app/tests/test_workspace_activity_logging.py \
                                 app/tests/test_workspace_settings.py -v

# Full backend suite
docker compose exec backend pytest app/tests/ -v --timeout=30

# Lint
docker compose exec backend ruff check app/api/v1/
docker compose exec backend ruff format app/api/v1/

# Confirm the deprecation headers are present on mission + graph
curl -I http://localhost:8000/api/v1/missions/ | grep -i deprecation
curl -I http://localhost:8000/api/v1/graphs/ | grep -i deprecation

# Confirm the import tiers
docker compose exec backend python -c "
from app.api.v1 import RouterTier, _import_router
r = _import_router('mission', tier=RouterTier.CRITICAL)
assert r is not None
print('mission critical router OK')
"
```

## Child DOX Index

| Path | DOX coverage | Notes |
|------|--------------|-------|
| `__init__.py` | ❌ (mapped above) | The router registry. Promote to its own AGENTS.md if the import tier rules grow past `CRITICAL` / `STANDARD` / `OPTIONAL`. |
| `mission.py` | ❌ | The reference CQRS-delegated router. Worth a child AGENTS.md if the deprecation timeline gets more complex. |
| `mission_advanced_routes.py` | ❌ | Pure CRUD, migration backlog. Promote after it has a CQRS split. |
| `mission_decomposition_routes.py` | ❌ | DAG migration candidate. Promote after substrate migration. |
| `flow_compat.py` | ❌ | Graph migration candidate. Promote after substrate migration. |
| `graph.py` | ❌ | Same. |
| `swarm.py` + `swarm_protocol.py` | ❌ | Swarm migration candidates. Promote together (or in one PR). |
| `orchestration.py` | ❌ | Nexus orchestration migration candidate. Promote after the substrate has a `MetaStrategy`. |
| `substrate.py` | ❌ | The replay/events API. Stable, no migration needed. Promote only if a new substrate read primitive is added. |
| `plugins.py` | ❌ | Imports `ExecutionContext` from `graph_executor` (type-only). Promote to AGENTS.md if the type import is moved. |
| All other ~70 routers | ❌ | CRUD, no migration needed. Group-promote only if a v1 → v2 envelope migration is run. |
