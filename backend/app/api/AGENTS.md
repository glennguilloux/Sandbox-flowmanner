# Flowmanner — `app/api` Agent Instructions

## Purpose

This is the local contract for `backend/app/api/` — the HTTP layer that exposes the FastAPI backend to the Next.js frontend, mobile clients, integrations, and the open web. An agent landing here should be able to:

1. Decide whether a new endpoint belongs in `v1/`, `v2/`, or `v3/` (or whether the underscore-prefixed `_mission_cqrs` / `_blueprint_cqrs` packages are appropriate).
2. Pick the right shared dependency, envelope, and middleware.
3. Understand the CQRS split and the dual-write / feature-flag pattern that backs the Blueprint/Run migration (Phase 10.1).

## Ownership

### Top-level shared modules

| File | Purpose |
|------|---------|
| `deps.py` | FastAPI dependencies: `get_current_user` (v1 JWT), `get_current_session` (v3 httpOnly cookie + Bearer), `get_workspace_context` (H4 replaces tenant), `get_workspace_id` (header → primary), `require_role`, `require_scope`, `require_permission`, `require_tenant_admin` (deprecated alias). |
| `byok.py` | v1 BYOK API key CRUD (encrypted at rest). |
| `envelope.py` | Lightweight v2 envelope helper (`{"data", "meta", "error": null}`). |
| `utils.py` | Request helpers — `get_client_ip`, `get_device_name`, `parse_browser`, `parse_os`. |

### Middleware (`middleware/`)

| File | Purpose |
|------|---------|
| `versioning.py` | `APIVersioningMiddleware` — negotiates version via `Accept-Version` header, path prefix, or `?version=` query param. Adds `X-API-Version` to every response; `Deprecation` + `Sunset` + `Link: </api/v2/docs>; rel="successor-version"` headers on deprecated versions. `SUPPORTED_VERSIONS = {"v1", "v2", "v3"}`, `DEFAULT_VERSION = "v1"`, `CURRENT_VERSION = "v2"`. `deprecated(...)` decorator for per-endpoint deprecation. |
| `security_headers.py` | CSP, HSTS, X-Frame-Options, etc. |
| `audit.py` | `log_event()` — fire-and-forget audit log writes (called from many CQRS handlers). |
| `metrics.py` | Prometheus metrics middleware. |
| `rate_limit.py` | Per-route / per-user rate limits. |

### Version directories

| Directory | Status | Surface | Envelope | Auth | Notes |
|-----------|--------|---------|----------|------|-------|
| `v1/` | Active, legacy | ~80 endpoint files (60+ modules per `backend/AGENTS.md`) | Native FastAPI `JSONResponse` | `get_current_user` (JWT) | Original API. Stable, but no envelope, no GraphQL, no standardized error format. |
| `v2/` | **Current default** (`CURRENT_VERSION`) | 24 files: auth, agents, chat, missions, search, workspaces, dashboard, integrations (+oauth, +actions), openapi, blueprints, runs, regression | Standardized (`ok` / `paginated` / `err` from `v2/base.py`) | `get_current_user` (JWT) | "A genuine redesign, not a wrapper around v1" (per `v2/__init__.py`). Includes Phase 10 blueprint/run endpoints and Phase 0 regression endpoints. |
| `v3/` | Active, focused | 12 files: auth, auth_oidc, auth_webhooks, auth_cookies, teams, workspaces, workspace_activity, workspace_billing, workspace_invitations | Same as v2 (`v3/base.py` adds `trace_id` to error envelope) | `get_current_session` (cookie + Bearer) | Workspace + auth specialty surface. Errors include `trace_id` for log correlation. |

### CQRS packages (underscore prefix = internal)

| Package | Purpose | Notes |
|---------|---------|-------|
| `_mission_cqrs/` | Command/query split for mission endpoints | Used by the next-generation v1/v2 routes that are being migrated. Base classes `CommandHandlerBase` / `QueryHandlerBase` (in `base.py`) wrap mutations in `wrap_command()` with explicit `tx()` commit/rollback. `commands.py` (create/update/delete/execute/plan/abort/pause/resume/retry/batch_abort/create_from_template/improvements) and `queries.py` (list/get/tasks/logs/status/active/analytics/events/substrate_state/SSE stream) split by intent. `audit.py`, `compat.py` (dual-write helpers), `deps.py` (FastAPI DI factories), `errors.py` (exception mapping). |
| `_blueprint_cqrs/` | Command/query split for blueprint endpoints | Same pattern as `_mission_cqrs/` but for the Blueprint/Run data model (Phase 10.1). `commands.py` and `queries.py` only — no `audit.py` yet. |

The underscore prefix is a Python convention marking these as **internal implementation packages, not user-facing routers**. No `APIRouter` here; they are pure handler classes that routes in `v1/` / `v2/` compose into path operations.

## Local Contracts

These rules apply across `app/api/`, on top of `backend/AGENTS.md` and `backend/app/services/AGENTS.md`.

1. **v1 stays backward-compatible forever.** Do not change v1 response shapes. Add v2 endpoints for new behavior.
2. **v2 is the default for new client features.** New endpoints default to `v2/` unless they need v3's workspace/cookie/session capabilities. When in doubt, ask the user.
3. **v3 is for workspace + auth surface only.** Use `get_current_session` (cookie + Bearer) and the v3 envelope (which adds `trace_id` to errors). Anything else goes in v2.
4. **All v2 responses use the envelope.** Import helpers from `app.api.v2.base`:
   ```python
   from app.api.v2.base import ok, paginated, err
   return ok({"key": "value"})
   return paginated(items=..., total=..., page=..., per_page=...)
   return err("validation_error", "title is required", details={"field": "title"})
   ```
   v1 responses are un-enveloped (native FastAPI). Do not mix the two within a single router.
5. **Auth dependency choice is version-driven.**
   - v1 / v2 routes → `Depends(get_current_user)` (JWT, OAuth2PasswordBearer).
   - v3 routes → `Depends(get_current_session)` (httpOnly cookie + Bearer fallback) and/or `Depends(require_scope(...))`.
6. **CQRS handlers are the destination for any non-trivial mission/blueprint route.** Routes stay thin; logic lives in `_mission_cqrs/commands.py` or `_mission_cqrs/queries.py` (or the blueprint equivalents). The route just wires DI:
   ```python
   @router.post("/missions/{mission_id}/abort")
   async def abort_mission(
       mission_id: UUID,
       session: AsyncSession = Depends(get_db),
       user: User = Depends(get_current_user),
       commands: MissionCommandHandlers = Depends(get_mission_commands),
   ):
       return await commands.abort_mission(user, mission_id, reason_str="user_requested")
   ```
7. **Multi-commit flows are explicit, not wrapped in `wrap_command()`.** When a handler must commit state → log separately → dispatch side effects (Celery, WS, analytics, dual-write), the `wrap_command()` comment explains why. Do not "fix" those by adding an outer wrapper — the multi-commit ordering is load-bearing.
8. **All LLM calls in CQRS routes go through `substrate.UnifiedExecutor` + `mission_to_workflow()`.** This is post-Phase-8.1 — `MissionExecutor` is no longer the execution path. The CQRS command handler `_op()` does:
   ```python
   from app.services.substrate.adapters import mission_to_workflow
   from app.services.substrate.executor import get_unified_executor
   workflow = mission_to_workflow(mission, tasks)
   strategy_result = await get_unified_executor().execute(self.session, workflow)
   ```
9. **Dual-writes to Blueprint/Run are fire-and-forget, not transactional.** The Phase 10.1 dual-write helpers (`dual_write_sync_run_status`, `dual_write_sync_blueprint`, `dual_write_soft_delete_blueprint` in `_mission_cqrs/compat.py`) run via `_schedule_fire_and_forget()` and log + swallow failures. The legacy `Mission` table is the source of truth during the transition; Blueprint/Run is the future.
10. **Read routing respects the `USE_NEW_READS=1` feature flag.** When the flag is on, queries hit Blueprint/Run tables (`use_new_reads()` check at the top of each query handler). Without the flag, the legacy `Mission` table is queried. Test both paths.
11. **The audit log is fire-and-forget, never blocking.** `self.audit.mission_created(...)` / `mission_updated()` / `mission_aborted()` / `mission_executed()` / `mission_paused()` / `mission_resumed()` / `mission_retried()` / `mission_deleted()` are no-fail calls. Do not wrap them in try/except in routes.
12. **Soft-delete via `deleted_at` is universal.** All list/get queries must filter `WHERE deleted_at IS NULL`. Hard deletes are a code smell.
13. **The versioning middleware (`APIVersioningMiddleware`) is the single source of truth for `X-API-Version` headers.** Do not set `X-API-Version` manually in routes.

## Work Guidance

### Versioning policy in one sentence

> v1 = legacy stable surface · v2 = current default, envelope + GraphQL · v3 = workspace/auth specialty with cookie+Bearer sessions.

Add a new endpoint in v2 unless you need v3's session/workspace capabilities. Migrate an existing v1 endpoint to v2 only when its schema needs to break — otherwise v1 stays. There is no v4 yet.

### Adding a new v2 endpoint (the common case)

1. Pick or create a router file under `backend/app/api/v2/`. Group by domain (e.g. `missions.py`, `chat.py`, `workspaces.py`).
2. Import the envelope helpers: `from app.api.v2.base import ok, paginated, err`.
3. Use `Depends(get_current_user)` for auth and `Depends(get_db)` for the session.
4. For non-trivial mission/blueprint logic, call into the CQRS package: `Depends(get_mission_commands)` or `Depends(get_mission_queries)`.
5. Return `ok(...)` / `paginated(...)` / `err(...)` — never raw dicts.
6. Add a test in `backend/app/tests/test_<endpoint>.py` covering the success + the 401 + the 403 + the 404 paths.

### Adding a new v3 endpoint

Same as v2 except:
1. Use `from app.api.v3.base import ok, paginated, err` (which adds `trace_id` on error).
2. Use `Depends(get_current_session)` (not `get_current_user`) for auth.
3. For scope-gated routes, use `Depends(require_scope("workspaces:write", ...))`.

### Adding a new CQRS command/query

1. Add the method to `MissionCommandHandlers` or `MissionQueryHandlers` in the corresponding `commands.py` / `queries.py`.
2. Single-commit mutations: wrap in `async def _op(): ...; return await self.wrap_command(_op)`.
3. Multi-commit flows: do the commits inline and add a `# NOTE: not wrapped in wrap_command — ...` comment explaining the commit boundaries.
4. Audit-log every state-changing command via `self.audit.<event>(...)`.
5. Invalidate Redis caches via `_schedule_fire_and_forget(invalidate_*(...))`.
6. Fire-and-forget dual-write to Blueprint/Run via `dual_write_*` helpers.
7. Register DI factory in `_mission_cqrs/deps.py` if it isn't there already.

### Promoting a v1 route to the CQRS path

1. Add a corresponding `MissionCommandHandlers` / `MissionQueryHandlers` method.
2. Rewrite the route to be a thin DI shell.
3. Keep the v1 path/method/response shape unchanged for backward compatibility.
4. If the v1 shape is too poor to preserve, freeze it and add a v2 route instead.

### Adding a new mission/blueprint node type, executor, or migration

See `backend/app/services/substrate/AGENTS.md` and `backend/app/services/AGENTS.md` — the API layer only adapts; the substrate owns execution.

## Verification

```bash
# Run v1 endpoint tests
docker compose exec backend pytest app/tests/test_auth_api.py \
                                 app/tests/test_mission_api.py \
                                 app/tests/test_mission_advanced_api.py \
                                 app/tests/test_mission_execution_api.py \
                                 app/tests/test_chat_streaming.py \
                                 app/tests/test_io_api.py -v

# Run v2 endpoint tests (Phase 0 regression + Phase 10 blueprint/run)
docker compose exec backend pytest app/tests/test_regression.py \
                                 app/tests/test_marketplace_v2.py \
                                 app/tests/test_classify_route_workflow.py -v

# Run v3 / auth v3 tests
docker compose exec backend pytest app/tests/test_auth_v3_unit.py \
                                 app/tests/test_auth_v3_integration.py \
                                 app/tests/test_cross_workspace_shares.py \
                                 app/tests/test_workspace_activity_logging.py \
                                 app/tests/test_workspace_settings.py \
                                 app/tests/test_workspace_native.py -v

# Run CQRS-specific tests
docker compose exec backend pytest app/tests/ -v -k "cqrs or mission_cqrs or blueprint_cqrs"

# Test versioning middleware end-to-end
curl -H "Accept-Version: v2" http://localhost:8000/api/v2/missions
curl -H "Accept-Version: v3" http://localhost:8000/api/v3/workspaces  # v3 cookie+session
curl -H "Accept-Version: bogus" http://localhost:8000/api/v1/missions  # expect 400

# Lint
docker compose exec backend ruff check app/api/
docker compose exec backend ruff format app/api/

# OpenAPI sanity
curl http://localhost:8000/openapi.json | jq '.info.version'
```

## Child DOX Index

| Path | DOX coverage | Notes |
|------|--------------|-------|
| `v1/` | ❌ | 80+ endpoint files, 60+ domains. A child AGENTS.md would be valuable but large; capture the per-module list in `backend/AGENTS.md` and add a per-router contract only for the largest routers (`missions.py`, `auth.py`, `workspace.py`, `chat.py`). |
| `v2/` | ❌ | Clean redesign with a small surface (24 files) — good candidate for a short child AGENTS.md enumerating each router and the response shape it returns. |
| `v3/` | ❌ | 12 files, focused on workspace + auth. Worth a child AGENTS.md if the workspace surface grows past Phase 6. |
| `_mission_cqrs/` | ❌ | The largest non-router package. A child AGENTS.md mapping every command + query method to its audit hook, dual-write, and cache invalidation would be a high-leverage write. |
| `_blueprint_cqrs/` | ❌ | Small today but growing as Phase 10.1 expands. Promote to AGENTS.md once it has more than 5 command methods. |
| `middleware/` | ❌ | Five middlewares. Each is small enough to live in the api AGENTS.md (see Ownership table); promote to per-file AGENTS.md only when a middleware's behavior grows past a few rules. |

When promoting a child, link it from the root `AGENTS.md` Child DOX Index.
