# Flowmanner — `app/api/_blueprint_cqrs` Agent Instructions

## Purpose

This is the local contract for `backend/app/api/_blueprint_cqrs/` — the **internal CQRS split** for blueprint and run endpoints. It is the destination for any non-trivial blueprint or run route: routes stay thin and call into the handler classes here. An agent landing here should be able to:

1. Find the right method (command vs query) for any blueprint or run operation.
2. See, for every method, **which service it delegates to**, **which audit hook fires (or is intentionally absent)**, **whether a dual-write runs (or is intentionally absent)**, and **which cache keys are read/invalidated (or are intentionally absent)** — without re-reading the implementation.
3. Understand the relationship to the substrate (runs), the regression layer (assertions, replay, diff), and the future mission dual-write targets.

The underscore prefix marks this as an **internal implementation package, not a user-facing router**. There is no `APIRouter` here; routes in `backend/app/api/v1/` and `v2/` compose these handler classes via the `get_blueprint_commands` / `get_blueprint_queries` / `get_run_commands` / `get_run_queries` FastAPI dependencies.

## Ownership

| File | Purpose |
|------|---------|
| `__init__.py` | Empty marker file (package docstring only). All public symbols are imported by `deps.py`. |
| `base.py` | `CommandHandlerBase` (with `tx()` async context manager + `wrap_command()` wrapper) and `QueryHandlerBase`. Both take an `AsyncSession`; commands also take an optional `request_id`. |
| `commands.py` | `BlueprintCommandHandlers` (5 mutating ops) + `RunCommandHandlers` (2 mutating ops). **The bulk of the file.** |
| `queries.py` | `BlueprintQueryHandlers` (3 read ops) + `RunQueryHandlers` (6 read ops) + `PaginatedBlueprints` and `PaginatedRuns` dataclasses. |
| `deps.py` | FastAPI DI factories: `get_blueprint_queries()` / `get_blueprint_commands()` (injects session + `X-Request-ID` from `request.headers`) / `get_run_queries()` / `get_run_commands()`. |
| `errors.py` | `BlueprintError` (base) + `BlueprintNotFoundError`, `RunNotFoundError`, `BlueprintValidationError`, `RunValidationError`. **No mapper function** — unlike `_mission_cqrs/errors.py` which has `map_infra_error()`. |

> **No `audit.py`, no `compat.py`** — this is intentional. Blueprint/run routes are too new to have inherited the Phase 6 mission-cache/dual-write machinery, and writes are infrequent enough that synchronous service delegation is sufficient. If you find yourself adding audit hooks or dual-writes here, mirror the `_mission_cqrs` pattern rather than inventing a new one.

## Local Contracts

These rules apply inside the `_blueprint_cqrs` package, on top of `backend/AGENTS.md`, `backend/app/api/AGENTS.md`, and `backend/app/services/AGENTS.md`.

1. **Routes must NOT contain business logic.** A route is a 3-5 line shell that wires DI: `Depends(get_current_user)` + `Depends(get_db_session)` + `Depends(get_blueprint_commands)` (or `get_blueprint_queries` / run variants) → call the handler method → return the result.
2. **All mutations go through `wrap_command()`.** Unlike `_mission_cqrs`, this package has **no multi-commit flows** — every command is single-commit:
   ```python
   async def _op():
       # ... mutate ORM via service
       return result
   return await self.wrap_command(_op)
   ```
3. **Commands delegate to services; they do not touch the ORM directly.** `BlueprintCommandHandlers` uses `BlueprintService`; `RunCommandHandlers` uses `RunService`. Service methods handle ownership, status transitions, and persistence.
4. **Queries delegate to services too.** Same pattern: `BlueprintQueryHandlers` → `BlueprintService.list/get/get_versions`; `RunQueryHandlers` → `RunService.list/get/get_events/replay_state/get_assertions/diff_runs`. No raw SQL, no in-package query building.
5. **No audit hooks.** Blueprint / run lifecycle events are not currently audited through the `AuditService` pattern. If/when audit is needed, port the no-fail / no-flush pattern from `_mission_cqrs/audit.py`.
6. **No dual-writes.** Blueprint is already the source of truth for the "blueprint" entity. Run is the source of truth for execution. There is no legacy table to sync to.
7. **No cache invalidation.** Reads bypass cache (the v1 mission layer had a cache; the blueprint/run layer does not). If volume grows, port the fire-and-forget pattern from `_mission_cqrs/queries.py` and create an `app/services/blueprint_cache.py`.
8. **Errors propagate as-is.** Handlers do not catch service exceptions. The error mapper in `errors.py` is **not yet implemented** (the module is currently a stub with no `map_infra_error()`). FastAPI's default exception handler will surface the original exception; v1 routes handle 404/403 in the route. If you add mappers, mirror `_mission_cqrs/errors.py`.
9. **Workspace-aware access checks live in the services.** The handler does not call `require_*_access()` directly — `BlueprintService` / `RunService` enforce ownership and raise `BlueprintNotFoundError` / `RunNotFoundError` for foreign-resource lookups.
10. **Read-only run endpoints use a separate `AsyncSessionLocal` when reading substrate internals** (events, replay). This is the convention established in `_mission_cqrs/queries.py:get_events` and `get_substrate_state` — apply it here when adding similar reads.
11. **The `_schedule_fire_and_forget()` helper is NOT in this package.** It exists in `_mission_cqrs/base.py` but was not yet ported. Do **not** import it across packages — copy the helper if/when needed.
12. **The `request_id` is stored on the handler** but is currently unused by the service layer. Keep the constructor parameter so future logging/audit hooks can pick it up without an API change.

## Work Guidance

### Method map — `BlueprintCommandHandlers` (commands.py)

| Method | Transaction | Service | Audit hook | Dual-write | Cache invalidation | Notes |
|--------|-------------|---------|------------|------------|--------------------|-------|
| `create_blueprint(user, payload, workspace_id)` | `wrap_command()` | `BlueprintService.create(...)` | — | — | — | Phase 10: optionally seeds a default version. `definition` is `model_dump()`'d before being passed to the service. |
| `update_blueprint(user, blueprint_id, payload)` | `wrap_command()` | `BlueprintService.update(...)` | — | — | — | Only non-None fields are passed. Definition changes **create a new version** inside the service. |
| `delete_blueprint(user, blueprint_id)` | `wrap_command()` | `BlueprintService.delete(...)` | — | — | — | Soft delete (sets `deleted_at`, `deleted_by`); the service is responsible. |
| `publish_blueprint(user, blueprint_id)` | `wrap_command()` | `BlueprintService.publish(...)` | — | — | — | Status transition `draft → published`. Validated inside the service. |
| `run_blueprint(user, blueprint_id, payload)` | `wrap_command()` | `RunService.create_from_blueprint(...)` + `RunService.execute(...)` | — | — | — | Single transaction; `create_from_blueprint` returns the run, then `execute` is called inline. Both happen inside the same `wrap_command()` so a failure in execute rolls back the run row. `budget_override` is `model_dump()`'d if present. |

### Method map — `RunCommandHandlers` (commands.py)

| Method | Transaction | Service | Audit hook | Dual-write | Cache invalidation | Notes |
|--------|-------------|---------|------------|------------|--------------------|-------|
| `abort_run(user, run_id, reason)` | `wrap_command()` | `RunService.abort(...)` | — | — | — | Signals substrate abort via `asyncio.Event` (see `backend/app/services/substrate/AGENTS.md`). Reason defaults to `"user_requested"`. |
| `retry_run(user, run_id)` | `wrap_command()` | `RunService.retry(...)` + `RunService.execute(...)` | — | — | — | Auto-executes the new run inside the same transaction (mirrors `run_blueprint`). |

### Method map — `BlueprintQueryHandlers` (queries.py)

| Method | Read flag aware? | Cache (read) | Cache (populate) | Audit hook | Dual-write | Notes |
|--------|------------------|--------------|------------------|------------|------------|-------|
| `list_blueprints(user_id, page, per_page, workspace_id, blueprint_type, status)` | — | — | — | — | — | Filters: workspace scope + type + status. No caching. |
| `get_blueprint(user_id, blueprint_id)` | — | — | — | — | — | Service enforces ownership. |
| `list_versions(user_id, blueprint_id)` | — | — | — | — | — | Returns the full version history. |

### Method map — `RunQueryHandlers` (queries.py)

| Method | Read flag aware? | Cache (read) | Cache (populate) | Audit hook | Dual-write | Read path | Notes |
|--------|------------------|--------------|------------------|------------|------------|-----------|-------|
| `list_runs(user_id, page, per_page, workspace_id, blueprint_id, status)` | — | — | — | — | — | `RunService.list(...)` → SQL | Filters: workspace + blueprint + status. No caching. |
| `get_run(user_id, run_id)` | — | — | — | — | — | `RunService.get(...)` → SQL | Service enforces ownership. |
| `get_events(user_id, run_id, from_sequence, limit)` | — | — | — | — | — | `RunService.get_events(...)` → **substrate event log** | See [§ Substrate read paths — `get_events`](#substrate-read-paths) |
| `replay_state(user_id, run_id, at_sequence)` | — | — | — | — | — | `RunService.replay_state(...)` → **substrate `ReplayEngine`** | See [§ Substrate read paths — `replay_state`](#substrate-read-paths) |
| `get_assertions(user_id, run_id)` | — | — | — | — | — | `RunService.get_assertions(...)` → **substrate `AssertionEngine`** | See [§ Substrate read paths — `get_assertions`](#substrate-read-paths) |
| `diff_runs(user_id, run_a_id, run_b_id)` | — | — | — | — | — | `RunService.diff_runs(...)` → **substrate `ReplayEngine` + diff** | See [§ Substrate read paths — `diff_runs`](#substrate-read-paths) |

### Substrate read paths

The four `RunQueryHandlers` methods that interact with the unified execution substrate all follow the same convention: **open a fresh `AsyncSessionLocal` inside the service so the substrate's read does not lock the request session**, then return a JSON-serializable DTO. They are read-only — they never mutate substrate state.

#### `get_events`

```
RunQueryHandlers.get_events(user_id, run_id, from_sequence, limit)
  └─→ RunService.get_events(run_id, user_id, from_sequence, limit)
        ├─ Ownership check: RunService.get(run_id, user_id) → 404 if foreign
        ├─ Open AsyncSessionLocal()
        ├─ SELECT * FROM substrate_events
        │   WHERE run_id = :run_id AND sequence >= :from_sequence
        │   ORDER BY sequence ASC
        │   LIMIT :limit
        ├─ Hydrate to RunEventResponse[]
        └─ Return list[RunEventResponse]
```

- Convention: separate `AsyncSessionLocal` so the request session is not blocked while the substrate scan runs. (Mirrors `_mission_cqrs/queries.py:get_events`.)
- `limit` defaults to 1000, max 10000 — validated by the route.
- Used by the v2 `/api/v2/runs/{run_id}/events?from_sequence=&limit=` route for tail-style event streaming to the UI.

#### `replay_state`

```
RunQueryHandlers.replay_state(user_id, run_id, at_sequence)
  └─→ RunService.replay_state(run_id, user_id, at_sequence)
        ├─ Ownership check: RunService.get(run_id, user_id) → 404 if foreign
        ├─ If at_sequence is None: substrate.UnifiedExecutor.snapshot(run_id)
        │     (current in-memory state, no DB scan)
        └─ If at_sequence is given: substrate.ReplayEngine.rebuild_state(
                run_id, up_to_sequence=at_sequence, session=...)
              └─ Replays substrate_events in order and folds state
        └─ Return dict { "run_id", "sequence", "state": {...}, "events": [...] }
```

- `at_sequence` is a time-travel cursor: it rebuilds the workflow state as it would have been at that point.
- The replay uses a separate `AsyncSessionLocal` for the same reason as `get_events`.
- Used by the v2 `/api/v2/runs/{run_id}/replay?at_sequence=` route for the Runway Agent Simulator's replay-at-sequence UI.

#### `get_assertions`

```
RunQueryHandlers.get_assertions(user_id, run_id)
  └─→ RunService.get_assertions(run_id, user_id)
        ├─ Ownership check: RunService.get(run_id, user_id) → 404 if foreign
        ├─ Open AsyncSessionLocal()
        ├─ substrate.AssertionEngine.auto_generate(run_id) → list[BehaviorAssertion]
        │     (extracts expected behaviors from a completed run)
        ├─ substrate.AssertionEngine.evaluate(run_id, behaviors) → list[AssertionResult]
        │     (re-runs each assertion against the run's event log)
        ├─ Build summary { "total", "passed", "failed", "warnings" }
        └─ Return dict { "run_id", "assertions": [...], "summary": {...} }
```

- Both auto-generation and evaluation are read-only; nothing is written to the substrate.
- The output of `auto_generate` is what the regression layer (see `backend/app/api/v2/regression.py`) uses to freeze a baseline.
- Used by the v2 `/api/v2/runs/{run_id}/assertions` route.

#### `diff_runs`

```
RunQueryHandlers.diff_runs(user_id, run_a_id, run_b_id)
  └─→ RunService.diff_runs(run_a_id, run_b_id, user_id)
        ├─ Ownership check: BOTH runs must be owned by user_id
        ├─ Assert both runs share the same blueprint_id (else 422)
        ├─ For each run, open AsyncSessionLocal() and call substrate.ReplayEngine
        │   to materialize the terminal state of the run
        ├─ Compute diff: cost, tokens, duration, task statuses, output data
        └─ Return dict {
              "blueprint_id", "run_a": {...}, "run_b": {...},
              "cost_delta", "duration_delta", "token_delta",
              "task_diff": [...], "output_diff": {...}
            }
```

- Read-only; never mutates substrate state.
- Used by the v2 `/api/v2/runs/{run_id}/diff/{other_run_id}` route for the regression-style comparison view.

### Cache key map

**None.** This package does not currently cache any reads. The `list_*` methods hit the DB on every request. If you add caching, mirror the mission_cqrs pattern (`app/services/mission_cache.py`):

- `cache_list_blueprints` keyed by `blueprint_list:{user_id}:{page}:{per_page}[:{workspace_id}][:{blueprint_type}][:{status}]`
- `cache_get_blueprint` keyed by `blueprint:{user_id}:{blueprint_id}`
- `cache_list_runs` keyed by `run_list:{user_id}:{page}:{per_page}[:{workspace_id}][:{blueprint_id}][:{status}]`
- `cache_get_run` keyed by `run:{user_id}:{run_id}`

### Dual-write map

**None.** Blueprint is the source of truth for the "blueprint" entity, and Run is the source of truth for execution. There is no legacy table to sync to. If a future migration introduces a legacy table, mirror the `compat.py` pattern from `_mission_cqrs/`.

### Audit hook map

**None.** The `Blueprint` and `Run` tables do not currently write to any audit log. If audit is required, port the `AuditService` pattern from `_mission_cqrs/audit.py`:

- `blueprint_created` / `blueprint_updated` / `blueprint_deleted` / `blueprint_published` / `blueprint_run_started`
- `run_aborted` (level=`warning`, with `abort_reason`) / `run_retried`

Audit calls would be made inline inside the `wrap_command(_op)` closure, mirroring how `MissionCommandHandlers` does it.

### Adding a new command method

1. Add the method to the appropriate handler class in `commands.py` (`BlueprintCommandHandlers` or `RunCommandHandlers`).
2. Use the `wrap_command(_op)` pattern. If the service needs multiple commits, do them inline and add a `# NOTE: not wrapped — ...` comment explaining the boundary.
3. Delegate to the service. Do not touch the ORM directly in the handler.
4. Add a unit test in `backend/app/tests/test_blueprint_cqrs_*.py` or extend an existing blueprint/run test.

### Adding a new query method

1. Add the method to `BlueprintQueryHandlers` or `RunQueryHandlers` in `queries.py`.
2. Delegate to the service. The service handles ownership enforcement.
3. For substrate-backed reads (events, replay, assertions, diff), use a separate `AsyncSessionLocal` to avoid locking the request session.
4. Add a unit test.

### Promoting a v1 inline route to the CQRS path

1. Add the handler method to `BlueprintCommandHandlers` / `BlueprintQueryHandlers` / `RunCommandHandlers` / `RunQueryHandlers`.
2. Rewrite the v1 route to a thin DI shell using the relevant `get_*` dependency.
3. Keep the v1 path / method / response shape unchanged.
4. If the v1 shape is unkeepable, freeze v1 and add a v2 endpoint in `backend/app/api/v2/` (the v2 blueprints/runs routers are already in place).

## Verification

```bash
# Run blueprint/run CQRS-related unit + integration tests
docker compose exec backend pytest app/tests/test_blueprints_api.py \
                                 app/tests/test_runs_api.py \
                                 app/tests/test_blueprint_service.py \
                                 app/tests/test_run_service.py \
                                 app/tests/test_substrate.py \
                                 app/tests/test_assertion_engine.py \
                                 app/tests/test_replay_engine.py -v

# Run the integration / chaos suite (substrate-backed)
docker compose exec backend pytest app/tests/integration/ \
                                 app/tests/chaos/ -v

# Run the full backend test suite
docker compose exec backend pytest app/tests/ -v --timeout=30

# Lint
docker compose exec backend ruff check app/api/_blueprint_cqrs/
docker compose exec backend ruff format app/api/_blueprint_cqrs/

# Public surface sanity
docker compose exec backend python -c "
from app.api._blueprint_cqrs import (
    BlueprintCommandHandlers, RunCommandHandlers,
    BlueprintQueryHandlers, RunQueryHandlers,
    PaginatedBlueprints, PaginatedRuns,
    CommandHandlerBase, QueryHandlerBase,
    get_blueprint_commands, get_blueprint_queries,
    get_run_commands, get_run_queries,
)
print('blueprint_cqrs public surface OK')
"

# Smoke-test the v2 endpoints that depend on this CQRS layer
curl -s http://localhost:8000/api/v2/openapi.json | jq '.paths | keys | map(select(startswith("/api/v2/blueprints") or startswith("/api/v2/runs")))'
# Should list ~10 paths (5 blueprints + 5 runs public + versions + events + replay + assertions + diff)
```

## Child DOX Index

| Path | DOX coverage | Notes |
|------|--------------|-------|
| `commands.py` | ✅ (mapped above) | 5 + 2 methods, all single-commit. `run_blueprint` and `retry_run` are the only ones that call two service methods inside one transaction. |
| `queries.py` | ✅ (mapped above) | 3 + 6 methods, all read-only delegations. The substrate-backed four (`get_events`, `replay_state`, `get_assertions`, `diff_runs`) have detailed read-path call trees in the **Substrate read paths** section. |
| `base.py` | ❌ | `CommandHandlerBase` + `QueryHandlerBase` are small (~30 lines). The `_schedule_fire_and_forget` helper is missing — port from `_mission_cqrs/base.py` if/when needed. |
| `deps.py` | ❌ | Four tiny factories. Not worth a child. |
| `errors.py` | ❌ | Four error classes + a base. No mapper function. Promote when the mapper is added. |
| `__init__.py` | ❌ | Docstring only. No re-exports. |

The package itself is the right child boundary. Do not create per-file AGENTS.md unless one of the above grows past a few hundred lines.

### Cross-package DOX links

- [`../_mission_cqrs/AGENTS.md`](../_mission_cqrs/AGENTS.md) — the sibling CQRS package with full audit / dual-write / cache machinery. The blueprint/run layer is intentionally simpler; do not blindly port features without a use case.
- [`../v1/AGENTS.md`](../v1/AGENTS.md) — lists inline legacy routes that still need to be migrated to this CQRS layer (the only one currently in the migration queue from blueprint/run is `mission_decomposition_routes.py` for the DAG-side blueprint CRUD).
- [`../v2/AGENTS.md`](../v2/AGENTS.md) — v2 routes that use this package (every route in `v2/blueprints.py` and `v2/runs.py`).
- [`../../services/AGENTS.md`](../../services/AGENTS.md) — service-layer contracts; `BlueprintService` and `RunService` live there.
- [`../../services/substrate/AGENTS.md`](../../services/substrate/AGENTS.md) — the unified execution substrate; `run_blueprint`, `retry_run`, and all four `RunQueryHandlers` substrate-backed methods talk to it.

## Open DOX Gaps

- **Audit hooks** — not implemented. Add when blueprint/run lifecycle events need to be auditable (regulatory, compliance, debugging).
- **Dual-write layer** — not implemented. Add only if a legacy table ever needs to be kept in sync during a migration.
- **Cache layer** — not implemented. Add if `list_*` or `get_*` QPS exceeds ~50 RPS.
- **Error mapper** — `errors.py` has the classes but no `map_infra_error()`. Port from `_mission_cqrs/errors.py` when blueprint routes start needing 4xx translation for `IntegrityError` / `DBAPIError`.
- **`_schedule_fire_and_forget()` helper** — not in this package's `base.py`. Copy from `_mission_cqrs/base.py` if/when fire-and-forget tasks are added.
