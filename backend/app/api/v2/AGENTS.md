# backend/app/api/v2 — Local Contract

## Purpose

Document every router in the v2 public platform API, the endpoints it exposes, and the exact response envelope shape each one returns. v2 is the current default — see [`../AGENTS.md`](../AGENTS.md) for the v1/v2/v3 versioning policy that this subtree implements.

## Ownership

- **Owners:** platform/api team
- **Mount point:** `api_v2_router` (FastAPI `APIRouter(prefix="/api/v2")`) — see [`__init__.py`](./__init__.py)
- **Mounted into:** `app.main_fastapi:app` (via `main_fastapi.py`)

## Local Contracts

These contracts apply to **every** file in this subtree.

### Response envelope (universal)

Every v2 endpoint returns one of three shapes, built from helpers in [`base.py`](./base.py):

- **Success** — `{"data": <payload>, "meta": {"request_id": "...", "timestamp": "..."}, "error": null}`
- **Paginated** — `{"data": {"items": [...], "total": N, "page": N, "per_page": N, "pages": N}, "meta": {...}, "error": null}`
- **Cursor-paginated** — `{"data": {"items": [...], "next_cursor": "..." | null, "prev_cursor": "..." | null}, "meta": {...}, "error": null}`
- **Error** — `{"data": null, "error": {"code": "...", "message": "...", "details": {...}}, "meta": {...}}`

Use the `ok()`, `paginated()`, and `err()` helpers — **never** return a raw dict or model from a v2 endpoint.

### Cross-cutting dependencies

| Concern | Dependency | Where it lives |
|---|---|---|
| Idempotency for mutations | `Depends(idempotency())` | [`idempotency.py`](./idempotency.py) |
| Per-user rate limit (free/starter/pro) | `Depends(rate_limit("mission:create"))` | [`rate_limit.py`](./rate_limit.py) |
| Tier-aware rate limit (uses workspace plan) | `Depends(tier_rate_limit("mission:create"))` | [`tier_rate_limit.py`](./tier_rate_limit.py) |
| Cursor pagination | `cp = CursorParams(...)` + `cursor_paginated(...)` | [`cursor_pagination.py`](./cursor_pagination.py) |
| Auth | `Depends(get_current_user)` from `app.api.deps` | external |
| Workspace context | `Depends(get_workspace_id)` from `app.api.deps` | external |

For mutation endpoints in [`missions.py`](./missions.py), the standard chain is: `idempotency()` → `rate_limit("mission:<op>")` → `get_mission_commands` CQRS handler. Both `idempotency` and `rate_limit` may return a `JSONResponse` to short-circuit; the route must check `isinstance(_, JSONResponse)` and return it.

### Error envelope construction

- HTTP exception → [`middleware.py`](./middleware.py) maps status to code via `_STATUS_CODE_MAP` (`400=BAD_REQUEST`, `401=UNAUTHORIZED`, `403=FORBIDDEN`, `404=NOT_FOUND`, `409=CONFLICT`, `422=VALIDATION_ERROR`, `429=RATE_LIMITED`, `500=INTERNAL_ERROR`, `502=BAD_GATEWAY`)
- Mission-domain exceptions → custom codes (`MISSION_NOT_FOUND`, `MISSION_FORBIDDEN`, `MISSION_TRANSITION_CONFLICT`, `MISSION_VALIDATION_ERROR`)
- Unhandled exception → `500 INTERNAL_ERROR` (generic message, full error logged via `structlog`)
- `request_id` for the envelope `meta` is read from `X-Request-ID` header

### Streaming exceptions

`/api/v2/chat/threads/{id}/chat/stream` and `/api/v2/missions/{id}/stream` are **streaming SSE** — `middleware.py` skips them (`_is_streaming_response`). The envelope is **not** applied to SSE bodies; the stream emits `data: <chunk>\n\n` and terminates with `data: [DONE]\n\n`. Do **not** wrap streaming in the v2 envelope.

### Response validation

`validation_middleware.py:StrictValidationMiddleware` recursively walks every v2 JSON response and checks for non-serializable Python objects (raw classes, enums without `.value`, sets, etc.). On failure it returns a `500 RESPONSE_SERIALIZATION_ERROR` envelope with `details.fields` listing the bad paths. Skip if `status_code >= 400` or content-type isn't `application/json`.

### Mutation write semantics

- POST that creates → `201 Created` with `ok(...)` envelope
- DELETE → `204 No Content` (no envelope body)
- PATCH/PUT → `200 OK` with `ok(...)` envelope
- Background-launch endpoints (e.g. `execute-async`) → `200 OK` with the launch token in `data`

## Router Inventory

All routers are mounted under `prefix="/api/v2"` in [`__init__.py`](./__init__.py). Tags in OpenAPI use the `v2-*` prefix so they're easy to filter.

### 1. auth — [`auth.py`](./auth.py) (tag: `v2-auth`)

Endpoints:

| Method | Path | Auth | Response shape |
|---|---|---|---|
| POST | `/auth/register` | none | `ok(TokenResponse)` — `{"access_token", "refresh_token"}` |
| POST | `/auth/login` | none | `ok(TokenResponse)` **or** `ok({"requires_2fa": true, "temp_token": "..."})` when TOTP enabled |
| POST | `/auth/login/2fa` | none | `ok(TokenResponse)` |
| POST | `/auth/refresh` | none | `ok(TokenResponse)` |
| POST | `/auth/logout` | required | `204 No Content` |
| GET | `/auth/me` | required | `ok(UserResponse)` |
| PATCH | `/auth/me` | required | `ok(UserResponse)` |

Note: registers also create a default `Workspace` + `WorkspaceMember(owner)` for the new user inside the same transaction. On 2FA-enabled accounts, `login` returns a 5-minute `2fa_temp` JWT — the client must immediately call `/auth/login/2fa` with the TOTP code or backup code to get real tokens.

### 2. missions — [`missions.py`](./missions.py) (tag: `v2-missions`)

Every endpoint is a **thin wrapper** over `_mission_cqrs.commands.MissionCommandHandlers` or `_mission_cqrs.queries.MissionQueryHandlers` (see [`../_mission_cqrs/AGENTS.md`](../_mission_cqrs/AGENTS.md)). Mutations have idempotency + per-user rate limit. Path params are `uuid.UUID` everywhere.

| Method | Path | CQRS method | Idempotency | Rate limit | Response |
|---|---|---|---|---|---|
| GET | `/missions` | `q.list_missions` (offset) **or** keyset if `?cursor=` | – | – | `paginated(MissionResponse[])` **or** `cursor_paginated(...)` |
| POST | `/missions/` | `c.create_mission` | ✓ | `mission:create` (30/min) | `ok(MissionResponse)` |
| GET | `/missions/active` | `q.list_active` | – | – | `ok(MissionResponse[])` |
| GET | `/missions/{id}` | `q.get_mission_response` | – | – | `ok(MissionResponse)` |
| PATCH | `/missions/{id}` | `c.update_mission` | ✓ | `mission:update` (30/min) | `ok(MissionResponse)` |
| DELETE | `/missions/{id}` | `c.delete_mission` | ✓ | `mission:delete` (15/min) | `204` |
| GET | `/missions/{id}/tasks` | `q.list_tasks` | – | – | `ok(MissionTaskResponse[])` |
| POST | `/missions/{id}/tasks` | `c.create_task` | – | – | `ok(MissionTaskResponse)` |
| PATCH | `/missions/{id}/tasks/{task_id}` | `c.update_task` | – | – | `ok(MissionTaskResponse)` |
| GET | `/missions/{id}/logs` | `q.list_logs` | – | – | `ok(MissionLogResponse[])` |
| POST | `/missions/{id}/logs` | `c.create_log` | – | – | `ok(MissionLogResponse)` |
| POST | `/missions/{id}/plan` | `c.plan_mission` | – | – | `ok(...)` |
| POST | `/missions/{id}/execute` | `c.execute_mission` | ✓ | `mission:execute` (20/min) | `ok(ExecutionResult)` |
| POST | `/missions/{id}/execute-async` | `c.execute_async` | – | – | `ok(LaunchToken)` |
| POST | `/missions/{id}/abort` | `c.abort_mission` | ✓ | `mission:abort` (15/min) | `ok(MissionResponse)` |
| GET | `/missions/{id}/status` | `q.get_status` | – | – | `ok(StatusSnapshot)` |
| GET | `/missions/{id}/stream` | `q.stream_status` | – | – | SSE stream (`text/event-stream`) |
| POST | `/missions/{id}/pause` | `c.pause_mission` | – | – | `ok(MissionResponse)` |
| POST | `/missions/{id}/resume` | `c.resume_mission` | – | – | `ok(MissionResponse)` |
| POST | `/missions/{id}/retry` | `c.retry_mission` | – | – | `ok(MissionResponse)` |
| POST | `/missions/batch-abort` | `c.batch_abort` | – | – | `ok({"aborted": [...], "failed": [...]})` |
| POST | `/missions/from-template/{template_id}` | `c.create_from_template` | – | – | `ok(MissionResponse)` |
| GET | `/missions/{id}/improvements` | `q.list_improvements` | – | – | `ok(Improvement[])` |
| POST | `/missions/{id}/improvements` | `c.create_improvement` | – | – | `ok(Improvement)` |
| POST | `/missions/{id}/improvements/{imp_id}/apply` | `c.apply_improvement` | – | – | `ok(ApplyResult)` |
| GET | `/missions/{id}/analytics` | `q.mission_analytics` | – | – | `ok(AnalyticsReport)` |
| GET | `/missions/analytics` | `q.global_analytics` | – | – | `ok(GlobalAnalytics)` |
| POST | `/missions/{id}/tasks/{task_id}/approve` | inline (HITL) | – | – | `ok({"status": "approved", "interrupt_id": "..."})` |
| POST | `/missions/{id}/tasks/{task_id}/reject` | inline (HITL) | – | – | `ok({"status": "rejected", "interrupt_id": "..."})` |

The two `approve`/`reject` routes bypass CQRS because they need to manipulate `approval_required` and re-queue the mission atomically with the HITL manager; they should be migrated to CQRS once the HITL module exposes a typed `resolve(task_id, decision, resolved_by)` API.

### 3. agents — [`agents.py`](./agents.py) (tag: `v2-agents`)

CRUD over the agent registry. Owner-scoped — every operation checks `agent.owner_id == user.id` via `_require_owner()` and 404s otherwise (never 403, to avoid leaking existence).

| Method | Path | Response |
|---|---|---|
| GET | `/agents` (offset `?page=&per_page=`) **or** `?cursor=&direction=after&limit=` | `paginated(AgentResponse[])` **or** `cursor_paginated(...)` |
| POST | `/agents/` | `ok(AgentResponse)` |
| GET | `/agents/{agent_id}` | `ok(AgentResponse)` |
| PATCH | `/agents/{agent_id}` | `ok(AgentResponse)` |
| DELETE | `/agents/{agent_id}` | `204` |
| GET | `/agents/templates/list` | `paginated(AgentTemplateResponse[])` |
| POST | `/agents/templates` | `ok(AgentTemplateResponse)` |
| PATCH | `/agents/templates/{template_id}` | `ok(AgentTemplateResponse)` |
| DELETE | `/agents/templates/{template_id}` | `204` |

### 4. chat — [`chat.py`](./chat.py) (tag: `v2-chat`)

Covers folders, threads, messages, files, branches, and LLM invocation (sync + SSE stream). Uses `X-User-API-Key` and `X-User-Base-URL` headers for BYOK override of the user's saved LLM key.

| Method | Path | Response |
|---|---|---|
| GET | `/chat/folders` | `ok(ChatFolderResponse[])` |
| POST | `/chat/folders` | `ok(ChatFolderResponse)` |
| PATCH | `/chat/folders/{folder_id}` | `ok(ChatFolderResponse)` |
| DELETE | `/chat/folders/{folder_id}` | `204` (also nulls `folder_id` on all member threads) |
| GET | `/chat/threads` (offset **or** cursor) | `paginated(...)` **or** `cursor_paginated(...)` |
| POST | `/chat/threads` | `ok(ChatThreadResponse)` |
| GET | `/chat/threads/{thread_id}` | `ok(ChatThreadResponse)` |
| PATCH | `/chat/threads/{thread_id}` | `ok(ChatThreadResponse)` |
| DELETE | `/chat/threads/{thread_id}` | `204` |
| GET | `/chat/threads/{thread_id}/messages` | `ok(ChatMessageResponse[])` |
| POST | `/chat/threads/{thread_id}/messages` | `ok(ChatMessageResponse)` |
| GET | `/chat/threads/{thread_id}/files` | `ok(ChatFileResponse[])` |
| POST | `/chat/threads/{thread_id}/files` | `ok(ChatFileResponse)` |
| PATCH | `/chat/messages/{message_id}` (user msgs only) | `ok(ChatMessageResponse)` |
| DELETE | `/chat/messages/{message_id}` (user msgs only; 409 if branched) | `204` |
| POST | `/chat/threads/{thread_id}/branches` | `ok(ChatBranchResponse)` |
| GET | `/chat/threads/{thread_id}/branches` | `ok(ChatBranchResponse[])` |
| GET | `/chat/branches/{branch_id}` | `ok(ChatBranchResponse)` |
| DELETE | `/chat/branches/{branch_id}` | `204` |
| POST | `/chat/threads/{thread_id}/chat` | `ok({"content", "model", "token_count", "message_id"})` |
| POST | `/chat/threads/{thread_id}/chat/stream` | SSE `text/event-stream` (**not** wrapped) |

### 5. workspaces — [`workspaces.py`](./workspaces.py) (tag: `v2-workspaces`)

Self-contained CRUD; no CQRS (volume too low to justify). PATCH/DELETE on a workspace require `owner`/`admin`/`owner` respectively — enforced via `membership.role` check.

| Method | Path | Min role | Response |
|---|---|---|---|
| GET | `/workspaces` | any member | `ok(WorkspaceResponse[])` |
| POST | `/workspaces/` | – | `ok(WorkspaceResponse)` (auto-creates an `owner` WorkspaceMember) |
| GET | `/workspaces/{workspace_id}` | any member | `ok(WorkspaceResponse)` |
| PATCH | `/workspaces/{workspace_id}` | owner/admin | `ok(WorkspaceResponse)` |
| DELETE | `/workspaces/{workspace_id}` | owner | `204` |
| GET | `/workspaces/{workspace_id}/members` | any member | `ok(MemberResponse[])` |
| GET | `/workspaces/{workspace_id}/teams` | any member | `ok(TeamResponse[])` |
| POST | `/workspaces/{workspace_id}/teams` | owner/admin | `ok(TeamResponse)` |

### 6. search — [`search.py`](./search.py) (tag: `v2-search`)

| Method | Path | Response |
|---|---|---|
| GET | `/search?q=&type=&limit=` | `ok({"missions": [...], "agents": [...], "knowledge": [...]})` (entity-keyed dict, not list) |
| GET | `/search/suggestions?q=` | `ok({"suggestions": [...]})` |

`type` is a comma-separated list of entity types. Empty / missing = search all.

### 7. dashboard — [`dashboard.py`](./dashboard.py) (tag: `v2-dashboard`)

User-facing execution history, cost analytics, log search, aggregate stats. All cost calculations go through `app.observability.cost_engine.CostAttributionEngine` (read-only API — never writes to `LLMCallRecord`).

| Method | Path | Response |
|---|---|---|
| GET | `/dashboard/missions` (filter: `status`, `search`, `sort_by`, `date_from`, `date_to`) | `paginated(MissionHistoryItem[])` |
| GET | `/dashboard/costs?period=week\|month\|all&workspace_id=` | `ok(CostAnalyticsResponse)` (includes `by_agent[]`, `by_model[]`, `previous_period_cost`, `trend_pct`) |
| GET | `/dashboard/logs?mission_id=&level=&search=` | `paginated(LogEntry[])` |
| GET | `/dashboard/stats` | `ok(DashboardStats)` (totals, success rate, avg duration, total cost, total tokens) |

### 8. integrations (HTTP) — [`integrations.py`](./integrations.py) (tag: `v2-integrations`)

User-defined HTTP outbound integration configs. `auth_config` is JSON-encrypted via `app.utils.encryption.encrypt_api_key` on write; never returns the plaintext in any response.

| Method | Path | Response |
|---|---|---|
| POST | `/integrations/http/` | `ok(HttpIntegrationConfigResponse)` |
| GET | `/integrations/http/` | `ok(HttpIntegrationConfigResponse[])` |
| GET | `/integrations/http/{integration_id}` | `ok(HttpIntegrationConfigResponse)` |
| PATCH | `/integrations/http/{integration_id}` | `ok(HttpIntegrationConfigResponse)` |
| DELETE | `/integrations/http/{integration_id}` | `204` |
| GET | `/integrations/http/{integration_id}/logs` | `paginated(HttpIntegrationLogResponse[])` |

### 9. integrations (OAuth) — [`integrations_oauth.py`](./integrations_oauth.py) (tag: `v2-integrations-oauth`)

User-provided OAuth apps + the standard authorize/callback flow. Providers: any slug in `app.integrations.oauth.OAUTH_PROVIDERS` (github, slack, google_drive, notion, linear). State is a token-encrypted JSON blob (`_build_state` / `_decode_state`) carrying `app_id`, `user_id`, and a nonce — `/callback` is the only public endpoint and validates via the state.

| Method | Path | Auth | Response |
|---|---|---|---|
| POST | `/integrations/oauth/apps` | required | `ok(OAuthAppResponse)` |
| GET | `/integrations/oauth/apps` | required | `ok(OAuthAppResponse[])` |
| GET | `/integrations/oauth/apps/{app_id}` | required | `ok(OAuthAppResponse)` |
| PUT | `/integrations/oauth/apps/{app_id}` | required | `ok(OAuthAppResponse)` |
| DELETE | `/integrations/oauth/apps/{app_id}` | required | `204` (also deletes connections) |
| POST | `/integrations/oauth/initiate` | required | `ok({"authorization_url": "...", "state": "..."})` |
| GET | `/integrations/oauth/callback` | **none** (state-validated) | `ok(OAuthConnectionResponse)` |
| GET | `/integrations/oauth/connections` | required | `ok(OAuthConnectionResponse[])` |
| GET | `/integrations/oauth/connections/{id}` | required | `ok(OAuthConnectionResponse)` |
| DELETE | `/integrations/oauth/connections/{id}` | required | `204` |

### 10. integrations (actions) — [`integrations_actions.py`](./integrations_actions.py) (tag: `v2-integrations-actions`)

Discover and execute pre-built actions (e.g. "send Slack message", "create Linear issue") via the OAuth connections from router 9.

| Method | Path | Response |
|---|---|---|
| GET | `/integrations/actions/available` | `ok(AvailableAction[])` — one row per (connection × action) |
| POST | `/integrations/actions/execute` | `ok(provider_response)` or `400` / `404` on failure |

### 11. blueprints — [`blueprints.py`](./blueprints.py) (tag: `blueprints-v2`)

CQRS via `_blueprint_cqrs`. Every endpoint lists in `get_blueprint_queries` or `get_blueprint_commands`.

| Method | Path | CQRS | Response |
|---|---|---|---|
| GET | `/blueprints` (filter: `blueprint_type`, `status`) | `q.list_blueprints` | `paginated(BlueprintResponse[])` |
| POST | `/blueprints/` | `c.create_blueprint` | `ok(BlueprintResponse)` |
| GET | `/blueprints/{blueprint_id}` | `q.get_blueprint` | `ok(BlueprintResponse)` |
| PATCH | `/blueprints/{blueprint_id}` (definition change → new version) | `c.update_blueprint` | `ok(BlueprintResponse)` |
| DELETE | `/blueprints/{blueprint_id}` (soft delete) | `c.delete_blueprint` | `204` |
| POST | `/blueprints/{blueprint_id}/publish` | `c.publish_blueprint` | `ok(BlueprintResponse)` |
| POST | `/blueprints/{blueprint_id}/run` | `c.run_blueprint` | `ok(RunResponse)` |
| GET | `/blueprints/{blueprint_id}/versions` | `q.list_versions` | `ok(BlueprintVersion[])` |

### 12. runs — [`runs.py`](./runs.py) (tag: `runs-v2`)

CQRS via `_blueprint_cqrs.RunQueryHandlers` / `RunCommandHandlers`. These are the **substrate-native** read endpoints — they are deliberately not behind the v1 → CQRS migration queue because they talk directly to the substrate event log (see [`../services/substrate/AGENTS.md`](../services/substrate/AGENTS.md)).

| Method | Path | CQRS | Response |
|---|---|---|---|
| GET | `/runs` (filter: `blueprint_id`, `status`) | `q.list_runs` | `paginated(RunResponse[])` |
| GET | `/runs/{run_id}` | `q.get_run` | `ok(RunResponse)` |
| POST | `/runs/{run_id}/abort` | `c.abort_run` | `ok(RunResponse)` |
| POST | `/runs/{run_id}/retry` | `c.retry_run` | `ok(RunResponse)` |
| GET | `/runs/{run_id}/events?from_sequence=&limit=` | `q.get_events` | `ok({"run_id", "events": [...], "count"})` |
| GET | `/runs/{run_id}/replay?at_sequence=` | `q.replay_state` | `ok(ReplayState)` |
| GET | `/runs/{run_id}/assertions` | `q.get_assertions` | `ok(AssertionReport)` |
| GET | `/runs/{run_id}/diff/{other_run_id}` | `q.diff_runs` | `ok(DiffReport)` |

### 13. regression — [`regression.py`](./regression.py) (tag: `v2-regression`)

Phase 0.6 regression: assert that a mission run matches the expected behaviors frozen on its template.

| Method | Path | Response |
|---|---|---|
| GET | `/regression/{mission_id}/compare?run_id=` | `ok({"results": AssertionResult[], "summary": {...}, "template_version"})` (or `err("no_substrate_run")` / `err("no_template")` envelopes) |
| POST | `/regression/{mission_id}/freeze-baseline?run_id=&cost_headroom=&latency_headroom=` | `ok({"template_id", "extracted": BehaviorAssertion[]})` |
| GET | `/regression/{mission_id}/expected-behaviors` | `ok({"mission_id", "template_id", "expected_behaviors": [...]})` |
| PUT | `/regression/{mission_id}/expected-behaviors` (body: `{"expected_behaviors": [...]}`, validated as a list) | `ok(...)` |

### 14. openapi — [`openapi.py`](./openapi.py) (tag: `v2-openapi`, not in OpenAPI spec)

| Method | Path | Response |
|---|---|---|
| GET | `/openapi.json` (excluded from schema) | `JSONResponse` of the v2-only OpenAPI 3.1 spec (cached on first build; `Cache-Control: public, max-age=300`) |
| GET | `/openapi-tiers.json` (excluded from schema) | `JSONResponse` of `_TIER_DOCS` |

The v2 OpenAPI spec is **filtered from the full app schema**: only paths starting with `/api/v2` are kept, schemas are transitively collected via `$ref` walking, and security schemes + tier limits are injected via the `info` extensions.

## GraphQL surface — REMOVED 2026-07-09 (dry-run executed 2026-06-09)

> **Status:** The /api/v2/graphql endpoint and its Strawberry schema were removed as part of the 5-step removal procedure in this section. The code below is preserved as a historical reference / changelog only. No GraphQL endpoint is currently served by this subtree. `settings.GRAPHQL_ENABLED` defaults to `False`. The original `schema.py` was deleted; the GraphQLDeprecationMiddleware and the `_DEPRECATION_REGISTRY` in `openapi.py` were also removed.

[`schema.py`](./schema.py) ~~defines a Strawberry GraphQL schema mounted at `/api/v2/graphql` by [`app/main_fastapi.py`](../../main_fastapi.py) via `strawberry.fastapi.GraphQLRouter`. The schema covered a subset of the v2 REST surface: missions, agents, chat threads/messages, workspaces, and usage analytics.~~

### Mount point + load-bearing assessment

- **Mounted at:** `/api/v2/graphql` (POST for queries/mutations, GET serves GraphiQL in dev only)
- **Gating:** soft — `try: from strawberry.fastapi import GraphQLRouter ... except ImportError: log warning("strawberry-graphql not installed — GraphQL endpoint disabled")`. If the `strawberry-graphql` package is missing, the endpoint simply does not register (no error, no 404 — it just isn't there).
- **Load-bearing for the frontend?** **No.** The Next.js frontend (see `frontend/src/`) exclusively hits the REST routers documented above. The GraphQL endpoint exists primarily for ad-hoc / one-off queries (operator scripting, BI tools, internal curl-based smoke tests) and is **not** covered by any contract test, rate-limit dependency, idempotency layer, or feature flag.
- **Can it be removed?** **Yes — done.** The 5-step removal procedure was executed as a dry-run on 2026-06-09 (the deploy of the deprecation headers had failed earlier in the same session, so traffic data was unavailable, and the user opted to proceed with the cleanup as a staging exercise). The actual sunset date in the procedure was 2026-07-09.

### Type hierarchy

All types live in `schema.py`. Every type is a `@strawberry.type` Pydantic-shaped class — no `ABC` base, no shared mixin.

**Object types:**

| Type | Mirrors | Notable fields |
|---|---|---|
| `PageInfo` | (helper) | `total, page, per_page, pages` |
| `UserType` | `User` ORM | `id, email, username, full_name, role, is_admin, is_active, avatar_url, created_at` |
| `MissionType` | `Mission` ORM | 16 fields including `plan, results, tokens_used, actual_cost, started_at, completed_at` |
| `MissionTaskType` | `MissionTask` ORM | `id, mission_id, title, task_type, status, input_data, output_data, tokens_used, error_message` |
| `AgentType` | `Agent` ORM | `id, name, owner_id, system_prompt, model_preference, config` |
| `AgentTemplateType` | `AgentTemplate` ORM | `template_id, name, agent_type, system_prompt, model_config, is_active` |
| `ChatThreadType` | `ChatThread` ORM | `id, user_id, username, title, folder_id, is_archived, message_count` |
| `ChatMessageType` | `ChatMessage` ORM | `id, thread_id, user_id, role, content, created_at` |
| `WorkspaceType` | `Workspace` ORM | `id, name, slug, owner_id, plan, created_at, updated_at` |
| `TeamType` | `Team` ORM | `id, workspace_id, name, description, created_at` |
| `UsageAnalyticsType` | (flat summary) | `total_missions, success_rate, avg_completion_time, total_tokens_used` |

**Connection wrappers** (offset pagination only — no cursor variant):

- `MissionConnection` — `{items: list[MissionType], page_info: PageInfo}`
- `AgentConnection` — `{items: list[AgentType], page_info: PageInfo}`
- `ChatThreadConnection` — `{items: list[ChatThreadType], page_info: PageInfo}`

**Input types:** `MissionCreateInput`, `MissionUpdateInput`, `AgentCreateInput`, `ChatThreadCreateInput`, `ChatMessageCreateInput` — all `@strawberry.input` with the same field names as the matching REST schemas.

### Query / Mutation map

**Queries** (defined in `Query` class):

| Field | Returns | Service | Notes |
|---|---|---|---|
| `me` | `UserType` | (direct `user` access) | Returns the authenticated user. |
| `missions(page=1, per_page=20)` | `MissionConnection` | `app.services.mission_service.list_missions` | Offset pagination only. |
| `mission(id: str)` | `MissionType` | `app.services.mission_service.get_mission` | 404-via-`ValueError` if foreign. |
| `agents(page=1, per_page=20)` | `AgentConnection` | `app.services.agent_service.list_agents` | Owner-scoped. |
| `agent(id: str)` | `AgentType` | `app.services.agent_service.get_agent` | Owner-scoped. |
| `chat_threads(page=1, per_page=20)` | `ChatThreadConnection` | `app.services.chat_service.list_chat_threads` | User-scoped. |
| `chat_thread(id: int)` | `ChatThreadType` | `app.services.chat_service.get_chat_thread` | User-scoped. |
| `chat_messages(thread_id: int)` | `list[ChatMessageType]` | `app.services.chat_service.get_chat_messages` | Loads the thread first for the ownership check. |
| `workspaces` | `list[WorkspaceType]` | `Workspace` + `WorkspaceMember` (inline query) | Two queries: memberships → workspaces. |
| `workspace(id: str)` | `WorkspaceType` | `Workspace` + `WorkspaceMember` (inline query) | Membership check first. |
| `usage_analytics` | `UsageAnalyticsType` | `app.services.mission_analytics.get_mission_analytics` | Flat summary only — no time series. |

**Mutations** (defined in `Mutation` class):

| Field | Returns | Service | Notes |
|---|---|---|---|
| `create_mission(input)` | `MissionType` | `app.services.mission_service.create_mission` | No idempotency, no rate limit, no CQRS layer. |
| `update_mission(id, input)` | `MissionType` | `app.services.mission_service.update_mission` | 10 positional args forwarded to the service. |
| `delete_mission(id)` | `bool` | `app.services.mission_service.delete_mission` | Returns the boolean result. |
| `create_agent(input)` | `AgentType` | `app.services.agent_service.create_agent` | Owner-scoped on `user.id`. |
| `delete_agent(id)` | `bool` | `app.services.agent_service.delete_agent` | Owner-scoped. |
| `create_chat_thread(input)` | `ChatThreadType` | `app.services.chat_service.create_chat_thread` | — |
| `delete_chat_thread(id)` | `bool` | `app.services.chat_service.delete_chat_thread` | — |

There are **no subscriptions** and **no mutations** for blueprint, run, regression, search, dashboard, or integrations.

### Per-field `info.context` resolution

`info.context` is populated by `_gql_context_getter` in [`main_fastapi.py`](../../main_fastapi.py) (lines ~313-329). The getter:

1. Reads `Authorization: Bearer <token>` from the request headers.
2. Decodes the JWT with `JWT_SECRET_KEY` + `HS256`.
3. If valid and the user is `is_active`, opens a fresh `AsyncSessionLocal()` and loads the user via `app.services.auth_service.get_user_by_id`.
4. Returns `{"user": user, "db": session}` — the same session used to load the user is then **reused for the entire GraphQL request**.
5. **Failures are silent** — bad token, missing user, inactive user → returns `{}` (empty dict). No 401 is raised; the GraphQL field is expected to enforce auth.

Inside the schema, the helpers are:

```python
def _get_user(info: Info):
    user = info.context.get("user")
    if not user:
        raise ValueError("Authentication required")
    return user

def _get_db(info: Info):
    db = info.context.get("db")
    if not db:
        raise ValueError("Database session not available")
    return db
```

Every Query / Mutation calls `_get_user(info)` first and raises `ValueError("Authentication required")` if the user is missing. Strawberry surfaces that as a GraphQL `errors[].message`. There is **no permission check** beyond "is the request authenticated" — workspace membership, role checks, and ownership enforcement are the responsibility of the service layer. For example, `chat_thread(id: int)` does:

```python
thread = await get_chat_thread(db, thread_id)
if thread is None or thread.user_id != user.id:
    raise ValueError("Thread not found")
```

This **404-via-`ValueError`** pattern matches the REST layer's "never 403, always 404" rule. Strawberry does not preserve the HTTP semantic — it just surfaces the message.

**Caveat — session lifecycle:** the DB session from the context getter is reused for the entire request (including follow-up loads). This works because the getter opens its own session and the schema doesn't open a second one. If you add a Mutation that needs to write, wrap the operation in `try/except` and explicitly `await db.commit()` (the getter does not auto-commit; the session is closed when the request ends).

### Notable absences (and where to look instead)

The GraphQL surface is **strictly a subset** of the REST v2 surface. It does **not** expose:

| Feature | REST surface | GraphQL |
|---|---|---|
| Cursor pagination | `cursor_paginated(...)` everywhere | ❌ — only offset `page=` / `per_page=` |
| v2 envelope (`{data, meta, error}`) | every REST endpoint | ❌ — GraphQL has its own `data` / `errors` format |
| Idempotency keys | `idempotency()` dependency | ❌ — no `Idempotency-Key` support |
| Rate limiting | `rate_limit` / `tier_rate_limit` | ❌ — only global IP rate limit in `auth.py` |
| Trace IDs in errors | n/a (v3 has them) | ❌ — `ValueError` → `errors[].message` with no trace |
| Streaming | SSE on `/missions/{id}/stream` | ❌ — no subscriptions |
| Blueprint / Run CRUD | `blueprints.py` + `runs.py` | ❌ — no GraphQL types for these |
| Dashboard analytics | `dashboard.py` | ❌ — only `usage_analytics` |
| Search | `search.py` | ❌ |
| Integrations | `integrations.py` + `integrations_oauth.py` | ❌ |
| Regression | `regression.py` | ❌ |

If you need any of these features on a GraphQL surface, **port the REST handler into a new GraphQL field and apply the v2 envelope as an `extensions` payload**. Do not try to make GraphQL look like the v2 envelope — clients will get confused and the envelope semantics (`request_id`, `trace_id`, `code`) are not part of the GraphQL spec.

### Verification

```bash
# Query the schema
curl -s -X POST http://localhost:8000/api/v2/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOK" \
  -d '{"query":"{ me { id email username } }"}' | jq

# List missions
curl -s -X POST http://localhost:8000/api/v2/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOK" \
  -d '{"query":"{ missions(page:1, per_page:5) { items { id title status } pageInfo { total pages } } }"}' | jq

# Create + delete in one round-trip
curl -s -X POST http://localhost:8000/api/v2/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOK" \
  -d '{"query":"mutation { create_mission(input:{title:\"smoke\"}) { id } }"}'

# Auth failure (no token → empty context → ValueError)
curl -s -X POST http://localhost:8000/api/v2/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"{ me { id } }"}' | jq '.errors[0].message'
# → "Authentication required"
```

There is **no dedicated pytest target** for the GraphQL schema — `tests/api/v2/` covers the REST routes only. If you add a GraphQL field, add a test that POSTs to `/api/v2/graphql` with a valid JWT and asserts on the JSON `data` payload.

## Work Guidance

### Adding a new v2 endpoint

1. Pick the right router file. If unsure, add to an existing one — don't fragment the surface.
2. Use the helpers from `base.py` — `ok(payload)`, `paginated(items, total, page, per_page)`, `err(code, message, status_code)`. **Do not** return a raw dict or Pydantic model directly.
3. For mutations, add `idempotency()` and either `rate_limit(...)` or `tier_rate_limit(...)` (the latter reads workspace plan).
4. For list endpoints, support **both** offset (`?page=&per_page=`) and cursor (`?cursor=&direction=after&limit=`) — see `agents.py:list_items` or `chat.py:list_threads_route` for the canonical pattern.
5. For 404s on owner-scoped resources, raise `_not_found()` (HTTP 404) — never 403, to avoid leaking existence.
6. Run `uv run python -c "from app.main_fastapi import app; print(len(app.routes))"` to confirm the route registered, then `curl http://localhost:8000/api/v2/openapi.json | jq '.paths | keys'` to confirm the spec picks it up.

### Adding a new CQRS-backed route (e.g. for `blueprints` or `runs`)

1. Add the handler method to `_blueprint_cqrs.commands.BlueprintCommandHandlers` / `RunCommandHandlers` (or to `_mission_cqrs` for missions).
2. In the v2 route, `Depends(get_blueprint_commands)` (or equivalent) and call the handler.
3. Pass `user` as the first argument so the handler can enforce ownership.

### Adding a new streaming endpoint

SSE is supported via `fastapi.responses.StreamingResponse`. Do **not** wrap in the v2 envelope; just emit `data: <chunk>\n\n` and finish with `data: [DONE]\n\n`. The validation middleware and the error-envelope middleware both skip `StreamingResponse`.

### Working with rate limits

- `rate_limit("mission:create")` → reads from `app.config.settings` (`MISSION_RATE_LIMIT_CREATE`, etc.). Default 30/min, burst 2×.
- `tier_rate_limit("mission:create")` → multiplies the base by `_TIER_MULTIPLIERS[tier]` (free=1.0, starter=2.0, pro=5.0, business=10.0, enterprise=20.0). The tier is resolved from `UserSubscription` first, then `Workspace.plan`, then `free`.
- Both populate `request.state.rate_limit_limit` / `_remaining` / `_reset`, which `rate_limit_headers.py` reads to inject `X-RateLimit-*` headers.
- When using a factory dependency that may return a `JSONResponse`, the route must check `isinstance(_, JSONResponse)` and return it: the dependency short-circuits but doesn't actually short-circuit the response.

### Working with idempotency

`idempotency()` is opt-in via the `Idempotency-Key` header. Scoped lookup is `(user_id, method, endpoint, key)` so a key reused for `/missions` and `/agents` will not collide. The middleware persists the response body, status, and safe headers (content-type, x-*, idempotency-replay) for replay — bodies over `204` are not persisted.

Replayed responses set `Idempotency-Replay: cache`. Mismatched hash for the same key returns `409 IDEMPOTENCY_CONFLICT`. Keys must match `^[\w\-]{1,255}$`.

## Verification

Smoke tests:

```bash
# Spec generation
curl -s http://localhost:8000/api/v2/openapi.json | jq '.paths | keys | length'
# Should be > 60 paths

# Auth round-trip
curl -s -X POST http://localhost:8000/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username_or_email":"you@example.com","password":"..."}' | jq

# Cursor pagination
curl -s "http://localhost:8000/api/v2/missions?cursor=$(curl -s .../missions | jq -r '.data.next_cursor')&direction=after&limit=20" | jq

# Rate limit headers
curl -si http://localhost:8000/api/v2/missions -H "Authorization: Bearer $TOK" | grep -i x-ratelimit

# Streaming (don't pipe to jq)
curl -N -X POST http://localhost:8000/api/v2/chat/threads/1/chat/stream \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"content":"hi"}'
```

Targeted pytest invocations (run from `backend/`):

```bash
# v2 envelope + routing
uv run pytest tests/api/v2/ -v

# Cursor pagination
uv run pytest tests/api/v2/test_pagination.py -v

# Idempotency
uv run pytest tests/api/v2/test_idempotency.py -v

# Rate limiting (free + tier)
uv run pytest tests/api/v2/test_rate_limit.py -v
uv run pytest tests/api/v2/test_tier_rate_limit.py -v

# CQRS delegation for missions
uv run pytest tests/api/_mission_cqrs/ -v

# Substrate-backed runs
uv run pytest tests/api/v2/test_runs.py -v
uv run pytest tests/api/v2/test_blueprints.py -v

# Regression / assertions
uv run pytest tests/api/v2/test_regression.py -v

# OpenAPI v2 spec
uv run pytest tests/api/v2/test_openapi.py -v
```

Lint & types:

```bash
uv run ruff check app/api/v2/
uv run mypy app/api/v2/
```

## Child DOX Index

| Path | Purpose | Status |
|---|---|---|
| `./__init__.py` | Mounts 13 sub-routers under `/api/v2` | ✅ stable |
| `./base.py` | `ok` / `paginated` / `err` envelope helpers + `ResponseMeta` / `ErrorDetail` / `PaginatedData` | ✅ stable |
| `./middleware.py` | Maps HTTPException + domain exceptions to v2 error envelopes | ✅ stable |
| `./validation_middleware.py` | Pydantic v2 strict response validation (catches leaked Python objects) | ✅ stable |
| `./idempotency.py` | `Idempotency-Key` dependency + `IdempotencyFinalizationMiddleware` (opt-in) | ✅ stable |
| `./rate_limit.py` | Per-user Redis-or-in-memory sliding-window rate limit dependency | ✅ stable |
| `./tier_rate_limit.py` | Tier-aware variant; uses `UserSubscription` or `Workspace.plan` | ✅ stable |
| `./rate_limit_headers.py` | Injects `X-RateLimit-*` headers from `request.state` | ✅ stable |
| `./cursor_pagination.py` | Cursor encoder/decoder + `cursor_paginated(...)` envelope builder | ✅ stable |
| `./schema.py` | ~~Strawberry GraphQL schema (legacy subset of v2 REST). Mounted at `/api/v2/graphql`.~~ | 🗑️ **removed 2026-07-09** (sunset window complete) |
| [`../_mission_cqrs/AGENTS.md`](../_mission_cqrs/AGENTS.md) | Maps every method in `MissionCommandHandlers` / `MissionQueryHandlers` to its audit hook + dual-write + cache invalidation | ✅ exists |
| [`../_blueprint_cqrs/AGENTS.md`](../_blueprint_cqrs/AGENTS.md) | Blueprint + Run CQRS handlers | ⏳ needed |
| [`../v1/AGENTS.md`](../v1/AGENTS.md) | v1 router surface (legacy stable; v1 is forward-compatible forever) | ✅ exists |
| [`../v3/AGENTS.md`](../v3/AGENTS.md) | v3 routers (workspace-scoped + cookie+Bearer sessions) | ⏳ needed |

## Open DOX Gaps

- `_blueprint_cqrs/AGENTS.md` — should document the per-method audit/dual-write/cache contract for `BlueprintCommandHandlers` / `RunCommandHandlers` / `BlueprintQueryHandlers` / `RunQueryHandlers`, mirroring the `_mission_cqrs` contract.
- `v3/AGENTS.md` — v3 routers exist; once they're feature-complete they need the same treatment as v2.
