# Error Classification: 404 vs 500 Sources

## 404 Sources (INTENTIONAL)

### Source 1: `_require_owner()` (mission.py:53-55)
- **Trigger**: `mission is None` OR `mission.user_id != user.id`
- **Affected endpoints**: ALL detail-family endpoints (/{mission_id}, /status/, /improvements, /analytics, /tasks, /logs, etc.)
- **Why it returns 404**: Security pattern — don't leak existence of other users' missions

### Source 2: Missing route `/stream`
- **Trigger**: Frontend requests `/api/missions/{mission_id}/stream`
- **Why 404**: Route is simply not defined in mission.py. No handler exists.

### Source 3: Route path matching issues
- **Evidence from bridge logs**: `GET /api/missions?per_page=20&page=1` → 404 (no trailing slash)
- **But**: `GET /api/missions/?per_page=20&page=1` → 200 (with trailing slash)
- **Cause**: FastAPI's `@router.get("/")` only matches `/api/missions/` not `/api/missions`
- **Note**: This affects the bridge backend's proxy behavior — requests without trailing slash may not route

## 500 Sources (UNINTENTIONAL / BUG)

### Source 1: `mission_tasks.updated_at` column missing from DB (CONFIRMED)
- **Root cause**: `MissionTask` model inherits `TimestampMixin` which adds `updated_at` column (models/__init__.py:20-24)
- **DB state**: `mission_tasks` table has 22 columns — NO `updated_at` column
- **SQLAlchemy behavior**: Generates `SELECT ... mission_tasks.updated_at ... FROM mission_tasks` → PostgreSQL throws `UndefinedColumnError`
- **Error**: `asyncpg.exceptions.UndefinedColumnError: column mission_tasks.updated_at does not exist`
- **HINT from PostgreSQL**: `Perhaps you meant to reference the column "mission_tasks.created_at"`
- **Affected function**: `get_mission_tasks()` (mission_service.py:162-168)
- **Affected endpoints**: `/status/`, `/plan`, `/execute`, `/tasks` — any endpoint calling `get_mission_tasks()`

### Why 404 and 500 appear on same mission ID
1. `GET /api/missions/{id}` → calls `get_mission()` (only queries `missions` table) → finds mission → `_require_owner()` checks ownership
   - **WAIT**: The main backend logs show the mission IS found (SQL query for mission succeeds in traceback) but then `_require_owner` should pass because mission.user_id=60 matches the authenticated user (user_id=60 from auth logs)
   - **EXPLANATION**: On the bridge backend, the 404 pattern is different. The bridge proxies to `workflows.glennguilloux.com` which is the MAIN backend. So the bridge logs show HTTP responses FROM the main backend, not local processing. The 404s on `/`, `/improvements/`, `/analytics/`, and `/stream` on bridge are actually from the main backend responding.

2. **On the main backend** (local docker): The traceback shows `get_mission()` SUCCEEDS (the SQL for missions table executes fine), but then `get_mission_tasks()` FAILS with `UndefinedColumnError`, which triggers a 500.

3. **But the bridge logs show 404 for detail endpoints**: This means the bridge's proxy is NOT hitting the same code path, OR the main backend is returning 404 for a different reason when accessed through the bridge.

### Revised Understanding
The main backend logs show:
- `GET /api/missions/{id}` → 404 (NOT 500)
- `GET /api/missions/{id}/status/` → 500

This means `get_item()` (line 92-100) returns 404, while `get_mission_status()` (line 299-317) returns 500.

**Why the difference?** Both call `get_mission()` first. But:
- For `get_item()`, the MissionResponse schema includes `updated_at` — if the mission object's `updated_at` can't be loaded, SQLAlchemy may fail silently or the response serialization could fail
- Actually, `missions` table HAS `updated_at` (25 columns). So `get_mission()` should work fine.
- The 404 from `get_item()` means `_require_owner()` is returning 404 — either mission is None or user_id doesn't match.

**Let me check**: The mission `014da489-b7f5-44f7-9e89-046a05a5ab56` has `user_id=60` in the DB. The authenticated user also has `id=60` (from auth queries). So `_require_owner()` should PASS.

**WAIT — critical detail**: The traceback for the 500 shows the SQL query `SELECT missions... WHERE missions.id = '014da489...'` SUCCEEDS. The failure is on `get_mission_tasks()` AFTER that. This means:
1. `get_mission()` returns a valid mission object
2. `_require_owner()` passes (user_id matches)
3. `get_mission_tasks()` then crashes with UndefinedColumnError → 500

So why do OTHER detail endpoints return 404? They should also pass `_require_owner()` and then... what?
- `get_item()` at line 92-100: calls `get_mission()` → `_require_owner()` → `return mission`. No `get_mission_tasks()` call. Should return 200.
- Unless the response serialization of `MissionResponse` fails? `MissionResponse` includes `updated_at`, and the `missions` table HAS `updated_at`, so that should work.

**HYPOTHESIS**: The 404s on non-status endpoints may be happening ONLY on the bridge, not locally. Let me check the main backend logs more carefully.

From the main backend filtered log, I see BOTH 404s AND 500s. The 404s happen for `/{id}/`, `/{id}/improvements/`, `/{id}/analytics/`, `/{id}/stream` — and the 500s happen for `/{id}/status/`.

Actually, re-reading the main backend raw log more carefully — the traceback I captured IS from the main backend container. And it shows the 500 for `/status/`. The 404s for other endpoints must mean `_require_owner()` is failing for some reason.

**KEY INSIGHT**: Maybe there's a TRAILING SLASH issue. The bridge requests `/api/missions/{id}/` (with trailing slash) and `/api/missions/{id}/status/` (with trailing slash). FastAPI's route definitions are:
- `@router.get("/{mission_id}")` — no trailing slash
- `@router.get("/{mission_id}/status/")` — with trailing slash AND `@router.get("/{mission_id}/status")` — without

When the bridge requests `/{id}/` (trailing slash on detail endpoint), FastAPI may not match `/{mission_id}` (no trailing slash) and return 404!

Let me verify this against the route definitions.
