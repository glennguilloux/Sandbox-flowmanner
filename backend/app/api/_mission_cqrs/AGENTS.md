# Flowmanner — `app/api/_mission_cqrs` Agent Instructions

## Purpose

This is the local contract for `backend/app/api/_mission_cqrs/` — the **internal CQRS split** for mission endpoints. It is the destination for any non-trivial mission route: routes stay thin and call into the handler classes here. An agent landing here should be able to:

1. Find the right method (command vs query) for any mission operation.
2. See, for every method, **which audit hook fires**, **which dual-write runs**, and **which cache keys are invalidated** — without re-reading the implementation.
3. Understand the transaction-bounding rules (which methods are wrapped in `wrap_command()` and which commit inline) and why.

The underscore prefix marks this as an **internal implementation package, not a user-facing router**. There is no `APIRouter` here; routes in `backend/app/api/v1/` and `v2/` compose these handler classes via the `get_mission_commands` / `get_mission_queries` FastAPI dependencies.

## Ownership

| File | Purpose |
|------|---------|
| `__init__.py` | Public re-exports: `AuditService`, `CommandHandlerBase`, `QueryHandlerBase`, `MissionCommandHandlers`, `MissionQueryHandlers`, `PaginatedMissions`, `get_mission_commands`, `get_mission_queries`, `map_infra_error`. |
| `base.py` | `CommandHandlerBase` (with `tx()` async context manager + `wrap_command()` wrapper), `QueryHandlerBase`, `_make_execution_status()`, `_schedule_fire_and_forget()` helper. |
| `commands.py` | `MissionCommandHandlers` — all 14 mutating operations. **The bulk of the file.** |
| `queries.py` | `MissionQueryHandlers` — all 10 read operations + `PaginatedMissions` dataclass + SSE `stream_status()`. |
| `audit.py` | `AuditService` with the 9 convenience helpers (`mission_created`, `mission_updated`, `mission_deleted`, `mission_executed`, `mission_aborted`, `mission_paused`, `mission_resumed`, `mission_retried`) + the generic `record()`. Failures are logged and swallowed — auditing MUST NOT break business flow. |
| `compat.py` | Phase 6 read-from-Blueprint/Run compat layer: `use_new_reads()` feature flag, `list_missions_from_blueprints`, `get_mission_from_blueprint`, `list_active_from_blueprints`, `active_missions_from_blueprints`, `MissionShim` dataclass, and the three `dual_write_*` helpers. |
| `deps.py` | FastAPI DI factories: `get_mission_commands()` (injects session + `AuditService` + `X-Request-ID` from `request.headers`), `get_mission_queries()`. |
| `errors.py` | `map_infra_error()` — translates `IntegrityError` → `MissionValidationError`, transient `DBAPIError` → `RetryableMissionError`, anything else → `PermanentMissionError`. |

## Local Contracts

These rules apply inside the `_mission_cqrs` package, on top of `backend/AGENTS.md`, `backend/app/api/AGENTS.md`, and `backend/app/services/AGENTS.md`.

1. **Routes must NOT contain business logic.** A route is a 3-5 line shell that wires DI: `Depends(get_current_user)` + `Depends(get_db_session)` + `Depends(get_mission_commands)` → call the handler method → return the result.
2. **Single-commit mutations go through `wrap_command()`.** The pattern:
   ```python
   async def _op():
       # ... mutate ORM, audit, dual-write fire-and-forget, etc.
       return result
   return await self.wrap_command(_op)
   ```
3. **Multi-commit flows are explicit.** When a handler must commit state → log → dispatch side effects (Celery, WS, analytics, dual-write), do the commits inline and add a `# NOTE: not wrapped in wrap_command — ...` comment explaining the commit boundaries. **Do not** "fix" these by adding an outer wrapper — the multi-commit ordering is load-bearing (see `execute_async`, `abort_mission`, `pause_mission`, `resume_mission`, `retry_mission`, `batch_abort`, `create_from_template`, `create_improvement`, `apply_improvement`).
4. **Audit calls are no-fail and non-blocking at the session level.** `AuditService.record()` does `session.add()` but never `flush()` or `commit()` — the surrounding transaction owns the commit. Audit failures are caught and logged inside `record()`.
5. **Cache invalidation is fire-and-forget via `_schedule_fire_and_forget()`.** The cache helpers come from `app.services.mission_cache` (`invalidate_mission_cache`, `invalidate_user_caches`). Failures are logged inside the helper, never re-raised.
6. **Dual-writes are fire-and-forget via `_schedule_fire_and_forget()`.** The helpers in `compat.py` (`dual_write_sync_run_status`, `dual_write_sync_blueprint`, `dual_write_soft_delete_blueprint`) open their own `AsyncSessionLocal` and silently log failures. The legacy `Mission` table is the source of truth during the transition; Blueprint/Run is the future.
7. **Read routing respects the `USE_NEW_READS=1` env flag.** When set, query handlers call into `compat.py` (`list_missions_from_blueprints`, `get_mission_from_blueprint`, etc.) and return `MissionShim` / `MissionResponse` DTOs. Without the flag, the legacy `Mission` table is queried. The flag is read by `use_new_reads()` at the top of each query method.
8. **Workspace-aware access checks are mandatory.** Any handler that takes a `mission_id` calls `require_mission_access(self.session, mission_id, user.id)` first. The check accepts both user-owned missions (no workspace) and workspace-owned missions (verified membership).
9. **All mission executions go through the substrate.** `execute_mission()` and `execute_async()` both use `get_unified_executor()` + `mission_to_workflow()`. `MissionExecutor` is no longer the execution path (post-Phase-8.1).
10. **Subscription tier limits are checked for create + execute.** `check_mission_create_allowed()` and `check_mission_execute_allowed()` (in `app.services.subscription_service`) gate the operation. Failures raise `MissionValidationError(limit_check.reason)`.
11. **Analytics tracking is fire-and-forget** inside `execute_mission()` via `app.services.analytics_service.track_event`. Failures are logged and swallowed.
12. **Abort signals propagate to the substrate.** `abort_mission` calls `get_unified_executor().abort(run_id, reason)` for any `substrate_run_id` stored in `mission.plan`, and also by `mission_id` directly. The signal is `asyncio.Event`-based (see `backend/app/services/substrate/AGENTS.md`).
13. **The `_schedule_fire_and_forget()` helper replaces the deprecated `asyncio.ensure_future`.** Use it for every fire-and-forget task. Tasks register a `_on_done` callback that logs (not raises) on failure.

## Work Guidance

### Method map — `MissionCommandHandlers` (commands.py)

| Method | Transaction | Audit hook | Dual-write | Cache invalidation | Notes |
|--------|-------------|------------|------------|--------------------|-------|
| `create_mission(user, payload, workspace_id)` | `wrap_command()` | `audit.mission_created()` | `_dual_write_blueprint()` (fire-and-forget) → `BlueprintService.create()` | `invalidate_user_caches(user.id)` | Phase 8.4 subscription check first. Dual-write creates linked Blueprint with `_source_mission_id` in `definition`. |
| `update_mission(user, mission_id, payload)` | `wrap_command()` | `audit.mission_updated()` | `dual_write_sync_run_status(...)` + `dual_write_sync_blueprint(**sync_fields)` (fire-and-forget) | `invalidate_mission_cache(user.id, str(mission_id))` | Only `title` / `description` are dual-written; status is dual-written via the run-status helper. |
| `delete_mission(user, mission_id)` | `wrap_command()` | `audit.mission_deleted()` (level=`warning`) | `dual_write_soft_delete_blueprint(...)` | `invalidate_user_caches(user.id)` + `invalidate_mission_cache(user.id, str(mission_id))` | Soft delete (sets `deleted_at`, `deleted_by`). |
| `create_task(user, mission_id, payload)` | `wrap_command()` | — (no audit hook) | — | — | Pure task insert. |
| `update_task(user, mission_id, task_id, payload)` | `wrap_command()` | — (no audit hook) | — | — | Mutates task fields inline. |
| `create_log(user, mission_id, payload)` | `wrap_command()` | — (the log row IS the audit) | — | — | Direct `create_mission_log()`. |
| `plan_mission(user, mission_id)` | `wrap_command()` | — (MissionExecutor logs internally) | — | — | Delegates to `MissionExecutor.plan_mission()`. Status changes logged inside the executor. |
| `execute_mission(user, mission_id, payload)` | `wrap_command()` | `audit.mission_executed()` | `_dual_write_run()` → finds linked Blueprint by `_source_mission_id`, creates a Run, copies `started_at` / `status` / `tokens` / `cost` / `error_message` / `output_data` | — | Phase 8.1: execution goes through `substrate.UnifiedExecutor` + `mission_to_workflow()`. Fire-and-forget analytics. |
| `execute_async(user, mission_id, payload)` | **Multi-commit (NOT wrapped)** | — (transition log written inline) | `dual_write_sync_run_status("queued")` | — | Three commits: (1) `mission.status = QUEUED`, (2) transition log, (3) Celery dispatch (`dispatch_mission_execution`) with fallback to `asyncio.create_task(_run_execution())`. |
| `abort_mission(user, mission_id, reason_str)` | **Multi-commit (NOT wrapped)** | `audit.mission_aborted()` (level=`warning`, with `abort_reason`) | `dual_write_sync_run_status("aborted", error_message, completed_at)` | — | Uses `SELECT ... FOR UPDATE` for TOCTOU safety. Signals UnifiedExecutor abort by `substrate_run_id` then by `mission_id`. Fire-and-forget WS emit + analytics. |
| `pause_mission(user, mission_id)` | **Multi-commit (NOT wrapped)** | `audit.mission_paused()` | `dual_write_sync_run_status("paused")` | — | Only valid from `RUNNING`. Resets all `RUNNING` tasks → `PENDING`. |
| `resume_mission(user, mission_id)` | **Multi-commit (NOT wrapped)** | `audit.mission_resumed()` | `dual_write_sync_run_status("queued")` | — | Only valid from `PAUSED`. |
| `retry_mission(user, mission_id)` | **Multi-commit (NOT wrapped)** | `audit.mission_retried()` | `dual_write_sync_run_status("pending", error_message=None)` | — | Only valid from `FAILED`. Calls `MissionExecutor.plan_mission()` to re-plan. |
| `batch_abort(user, mission_ids, reason)` | **Multi-commit (NOT wrapped, single final commit)** | `audit.mission_aborted()` (per mission) | `dual_write_sync_run_status("aborted", ...)` (per aborted mission) | — | `SELECT ... FOR UPDATE` on all missions. Pre-fetches workspace memberships in one query (N+1 prevention). |
| `create_from_template(user, template_id)` | **Multi-commit (NOT wrapped)** | — | — | — | Flushes to obtain `mission.id` for FK references, then commits. `wrap_command` would skip the flush. |
| `create_improvement(user, mission_id, payload)` | **Multi-commit (NOT wrapped)** | — | — | — | `SelfImprovementEngine` manages its own persistence. |
| `apply_improvement(user, mission_id, improvement_id)` | **Multi-commit (NOT wrapped)** | — | — | — | `SelfImprovementEngine.apply_strategy()` mutates + commits internally. |

### Method map — `MissionQueryHandlers` (queries.py)

| Method | Read flag aware? | Cache (read) | Cache (populate) | Notes |
|--------|------------------|--------------|------------------|-------|
| `list_missions(user_id, page, per_page, workspace_id)` | ✅ `use_new_reads()` → `list_missions_from_blueprints()` | `cache_list(user_id, page, per_page, workspace_id)` | `cache_set_list(...)` (fire-and-forget) | Cache miss falls through to DB. Returns `PaginatedMissions`. |
| `get_mission(user_id, mission_id)` | ✅ `use_new_reads()` → `get_mission_as_shim()` → `MissionShim` | — | `cache_set(user_id, str(mission_id), ...)` (fire-and-forget) | ORM-style return. Use this for internal callers that need real `.status` / `.workspace_id`. |
| `get_mission_response(user_id, mission_id)` | ✅ `use_new_reads()` → `get_mission_from_blueprint()` | `cache_get(user_id, str(mission_id))` | `cache_set(...)` (fire-and-forget) | DTO-style. Use this for HTTP responses. **Validates ownership on cache hit** (`cached.user_id != user_id` → 404). |
| `list_tasks(user_id, mission_id)` | ❌ (legacy path only) | — | `cache_set_tasks(...)` (fire-and-forget) | Calls `get_mission()` for ownership check. |
| `list_logs(user_id, mission_id)` | ❌ (legacy path only) | `cache_get_logs(user_id, str(mission_id))` | `cache_set_logs(...)` (fire-and-forget) | — |
| `get_status(user_id, mission_id)` | ❌ (legacy path only) | `cache_get_status(user_id, str(mission_id))` | `cache_set_status(...)` (fire-and-forget) | Calls `get_mission()` first. |
| `list_active(user_id, workspace_id)` | ✅ `use_new_reads()` → `list_active_from_blueprints()` | `cache_active(user_id, workspace_id)` | `cache_set_active(...)` (fire-and-forget) | Cache stores `active_ids` (not full rows) when `USE_NEW_READS=1`; full `missions` list otherwise. |
| `active_missions(user_id, user_role, is_pro, workspace_id)` | ✅ `use_new_reads()` → `active_missions_from_blueprints()` | `cache_active(user_id, workspace_id)` | `cache_set_active(...)` (fire-and-forget) | Requires `pro` role. N+1 prevention via single aggregate subquery for task stats. |
| `list_improvements(user_id, mission_id)` | ❌ (legacy path only) | `cache_get_improvements(user_id, str(mission_id))` | `cache_set_improvements(...)` (fire-and-forget) | Calls `get_mission()` for ownership check. |
| `mission_analytics(user_id, mission_id, days)` | ❌ (legacy path only) | — | — | Aggregates summary + over_time + token_usage + failure_analysis. |
| `global_analytics(user_id)` | ❌ (legacy path only) | — | — | Just `get_mission_analytics()`. |
| `get_events(user_id, mission_id, from_sequence, limit)` | ❌ (legacy path only) | — | — | Reads `substrate_events` directly via `AsyncSessionLocal` to avoid locking the request session. Returns up to 10 most recent runs, sorted by `(timestamp, sequence)`. |
| `get_substrate_state(user_id, mission_id)` | ❌ (legacy path only) | — | — | Replays the latest run via `ReplayEngine.rebuild_state()`. Uses a separate `AsyncSessionLocal` for the replay. |
| `stream_status(user_id, mission_id, initial_mission)` | ❌ (legacy path only) | — | — | SSE generator — 150 × 2s polls until terminal state. Ownership check must be done by the caller before invocation. |

### Cache key map (for invalidation logic)

| Cache helper (from `app.services.mission_cache`) | Key shape | Populated by | Invalidated by |
|----------------------------------------------|-----------|--------------|----------------|
| `cache_list` | `mission_list:{user_id}:{page}:{per_page}[:{workspace_id}]` | `list_missions` | `create_mission`, `delete_mission` (via `invalidate_user_caches`) |
| `cache_get` | `mission:{user_id}:{mission_id}` | `get_mission`, `get_mission_response` | `update_mission`, `delete_mission` (via `invalidate_mission_cache`) |
| `cache_get_status` | `mission_status:{user_id}:{mission_id}` | `get_status` | implicitly via mission mutations |
| `cache_get_logs` | `mission_logs:{user_id}:{mission_id}` | `list_logs` | on log creation |
| `cache_get_improvements` | `mission_improvements:{user_id}:{mission_id}` | `list_improvements` | on improvement mutation |
| `cache_set_tasks` | `mission_tasks:{user_id}:{mission_id}` | `list_tasks` | on task mutation |
| `cache_active` | `mission_active:{user_id}[:{workspace_id}]` | `list_active`, `active_missions` | on mission create / status change |
| `invalidate_user_caches(user_id)` | clears all per-user keys | — | `create_mission`, `delete_mission` |
| `invalidate_mission_cache(user_id, mission_id)` | clears `mission:*` + `mission_status:*` + `mission_logs:*` + `mission_tasks:*` | — | `update_mission`, `delete_mission` |

### Dual-write map (fire-and-forget, from `compat.py`)

| Dual-write helper | Mutates | Called by |
|-------------------|---------|-----------|
| `dual_write_sync_run_status(mission_id, user_id, status, error_message, completed_at)` | Latest `Run.status` (+ optional `error_message` / `completed_at`). Maps MissionStatus → RunStatus. | `update_mission`, `execute_async`, `abort_mission`, `pause_mission`, `resume_mission`, `retry_mission`, `batch_abort` |
| `dual_write_sync_blueprint(mission_id, user_id, **kwargs)` | Blueprint fields (title, description) + `updated_at`. | `update_mission` (only when `title` or `description` changed) |
| `dual_write_soft_delete_blueprint(mission_id, user_id)` | `Blueprint.deleted_at` + `Blueprint.deleted_by`. | `delete_mission` |
| `_dual_write_blueprint()` (in `create_mission`) | Creates a new Blueprint with `_source_mission_id` in `definition`. | `create_mission` |
| `_dual_write_run()` (in `execute_mission`) | Creates a new Run under the linked Blueprint, copies `started_at` / `status` / `tokens` / `cost` / `error_message` / `output_data`. | `execute_mission` |

All dual-write helpers open their own `AsyncSessionLocal` and silently log + swallow failures — the legacy `Mission` table is the source of truth during the transition.

### Adding a new command method

1. Add the method to `MissionCommandHandlers` in `commands.py`.
2. Single-commit: use `wrap_command(_op)`. Multi-commit: do commits inline with a `# NOTE: not wrapped` comment.
3. Call `audit.<event>()` for any state transition.
4. Call `invalidate_*` cache helpers via `_schedule_fire_and_forget()`.
5. Call `dual_write_*` helpers via `_schedule_fire_and_forget()` for any status / title / description / deletion change.
6. Workspace access: `mission = await require_mission_access(self.session, mission_id, user.id)` first.
7. Subscription gate: `check_mission_create_allowed()` / `check_mission_execute_allowed()` where applicable.
8. Add a unit test in `backend/app/tests/test_mission_advanced_api.py` or a new `test_mission_cqrs_*.py`.

### Adding a new query method

1. Add the method to `MissionQueryHandlers` in `queries.py`.
2. Cache-aside: try `cache_get*` first; fall through to DB; populate `cache_set*` (fire-and-forget).
3. Workspace access: `get_mission(user_id, mission_id)` for ownership check (cached or DB).
4. `USE_NEW_READS=1` awareness: branch on `use_new_reads()` at the top.
5. Validate ownership on cache hits (`cached.user_id != user_id` → 404).
6. Add a unit test.

### Promoting a v1 inline route to the CQRS path

1. Add a `MissionCommandHandlers` / `MissionQueryHandlers` method.
2. Rewrite the v1 route to a thin DI shell using `Depends(get_mission_commands)` / `Depends(get_mission_queries)`.
3. Keep the v1 path / method / response shape unchanged.
4. If the v1 shape is unkeepable, freeze v1 and add a v2 endpoint in `backend/app/api/v2/`.

## Verification

```bash
# Run mission CQRS-related unit + integration tests
docker compose exec backend pytest app/tests/test_mission_api.py \
                                 app/tests/test_mission_advanced_api.py \
                                 app/tests/test_mission_execution_api.py \
                                 app/tests/test_close_missions.py \
                                 app/tests/test_mission_circuit_breaker.py \
                                 app/tests/test_mission_executor.py \
                                 app/tests/test_cross_workspace_shares.py \
                                 app/tests/test_phase2_registry_hydration.py \
                                 app/tests/test_workspace_overview.py -v

# Run the integration / chaos suite
docker compose exec backend pytest app/tests/integration/ \
                                 app/tests/chaos/ -v

# Run the full backend test suite
docker compose exec backend pytest app/tests/ -v --timeout=30

# Lint
docker compose exec backend ruff check app/api/_mission_cqrs/
docker compose exec backend ruff format app/api/_mission_cqrs/

# Public surface sanity
docker compose exec backend python -c "
from app.api._mission_cqrs import (
    MissionCommandHandlers, MissionQueryHandlers, PaginatedMissions,
    CommandHandlerBase, QueryHandlerBase,
    AuditService,
    get_mission_commands, get_mission_queries,
    map_infra_error,
    use_new_reads,
)
print('mission_cqrs public surface OK')
"

# Smoke-test the feature flag
USE_NEW_READS=1 docker compose exec backend python -c "
from app.api._mission_cqrs.compat import use_new_reads
assert use_new_reads() is True
print('USE_NEW_READS=1 honored')
"
```

## Child DOX Index

| Path | DOX coverage | Notes |
|------|--------------|-------|
| `commands.py` | ❌ (mapped above) | Largest file in the package (~14 methods, ~600 lines). The method map in this AGENTS.md is the de-facto contract. |
| `queries.py` | ❌ (mapped above) | Second-largest file (~14 methods). Same — the method map in this AGENTS.md is the contract. |
| `audit.py` | ❌ | 9 convenience helpers + a generic `record()`. Self-documenting via the `AuditService.record()` docstring. Promote to its own AGENTS.md if the audit schema grows (e.g. when audit events get a separate table instead of MissionLog). |
| `compat.py` | ❌ | Phase 6 Blueprint/Run compat. The dual-write + `MissionShim` semantics are stable enough that a child AGENTS.md would help when adding more compat adapters. |
| `base.py` | ❌ | `CommandHandlerBase` + `QueryHandlerBase` are small. The `_schedule_fire_and_forget` semantics deserve their own doc — promote if a second helper (e.g. `_schedule_batched`) is added. |
| `deps.py` | ❌ | Three lines. Not worth a child. |
| `errors.py` | ❌ | One function. Not worth a child. |

The package itself is the right child boundary. Do not create per-file AGENTS.md unless one of the above grows past a few hundred lines.
