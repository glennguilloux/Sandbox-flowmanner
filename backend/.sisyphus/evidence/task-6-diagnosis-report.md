# Backend Log Bridge Diagnosis Report

**Date**: 2026-04-18
**Scope**: Diagnosis only — no implementation performed
**Mission IDs tested**: `014da489-b7f5-44f7-9e89-046a05a5ab56`, `0e895d3d-a073-4d62-91d6-094e46431ef7`

---

## Confirmed Facts

1. **Mission list (`GET /api/missions/`) works** — returns 200 with correct user-owned missions.
2. **Mission detail (`GET /api/missions/{id}`) works when accessed WITHOUT trailing slash** — returns 200 with full mission data.
3. **Mission detail (`GET /api/missions/{id}/`) returns 404 WITH trailing slash** — FastAPI route mismatch.
4. **`/status/` endpoint returns 500** — caused by `mission_tasks.updated_at` column missing from database.
5. **`/improvements` endpoint returns 500** — caused by `mission_improvements` table not existing in database.
6. **`/stream` endpoint returns 404** — route was never implemented.
7. **`/analytics` works WITHOUT trailing slash** — returns 200; WITH trailing slash returns 404.
8. **Bridge backend is a reverse proxy** to `workflows.glennguilloux.com`, not a separate code deployment.
9. **Both environments share the same database bugs.** Behavioral differences are caused by trailing-slash handling.

---

## Ruled-Out Hypotheses

| Hypothesis | Status | Why Ruled Out |
|---|---|---|
| Ownership mismatch | DISPROVED | DB confirms mission.user_id=60 matches authenticated user id=60; direct test returns 200 |
| Mission lookup failure | DISPROVED | get_mission() succeeds (proven by 200 response on /{id} without slash) |
| Stale mission IDs | DISPROVED | Mission exists in DB with correct ownership and status='pending' |
| Separate environment drift | DISPROVED | Bridge is a proxy, not separate deployment; same DB bugs in both |
| Serialization/runtime bug in MissionExecutionStatus | DISPROVED | The 500 occurs BEFORE serialization — it's a SQL query failure |

---

## Root Causes (Ranked by Impact)

### RC-1: Missing `updated_at` column in `mission_tasks` table (causes 500s)
- **What**: SQLAlchemy model `MissionTask` inherits `TimestampMixin` which adds `updated_at`. The database table has only 22 columns — no `updated_at`.
- **Where**: `app/models/__init__.py:20-24` (TimestampMixin), `app/models/mission_models.py:41` (MissionTask inherits it)
- **Effect**: Any endpoint calling `get_mission_tasks()` throws `UndefinedColumnError` → 500
- **Affected endpoints**: `/status`, `/plan`, `/execute`, `/tasks` (GET and POST)
- **Evidence**: `.sisyphus/evidence/task-1-main-backend-raw.log` (full traceback), live test confirming 500

### RC-2: Missing `mission_improvements` table (causes 500s)
- **What**: SQLAlchemy model `MissionImprovement` references table `mission_improvements`. The table does not exist in the database.
- **Where**: `app/models/mission_models.py:84-93`
- **Effect**: Any endpoint calling `SelfImprovementEngine.get_improvements()` throws `UndefinedTableError` → 500
- **Affected endpoints**: `/improvements` (GET and POST)
- **Evidence**: `.sisyphus/evidence/task-1-main-backend-raw.log` (UndefinedTableError traceback)

### RC-3: Trailing-slash route mismatch (causes 404s via bridge)
- **What**: Frontend/bridge sends URLs with trailing slashes. Most mission detail-family routes are defined WITHOUT trailing slash variants. Only `/status/` has both variants.
- **Where**: `app/api/v1/mission.py` — routes at lines 92, 142, 209, 320, 364 lack trailing-slash variants
- **Effect**: Requests with trailing slashes return 404 even though the route exists
- **Affected endpoints**: `/{id}/`, `/{id}/tasks/`, `/{id}/logs/`, `/{id}/improvements/`, `/{id}/analytics/`
- **Evidence**: Live testing confirms 200 without slash vs 404 with slash

### RC-4: `/stream` route not implemented (causes 404)
- **What**: Frontend requests `GET /api/missions/{id}/stream` but no such route exists in `mission.py`
- **Where**: Not defined — absent from `app/api/v1/mission.py`
- **Effect**: Always returns 404
- **Evidence**: Grep of codebase confirms no mission stream route; live test confirms 404

---

## Evidence Links

| Evidence File | Contents |
|---|---|
| `task-1-main-backend-raw.log` | Full main backend docker logs (71,376 lines) |
| `task-1-main-backend-filtered.log` | Filtered for mission ID, endpoints, and errors |
| `task-2-bridge-backend-raw.log` | Full bridge backend docker logs (2,912 lines) |
| `task-2-bridge-backend-filtered.log` | Filtered for same criteria |
| `task-3-codepath-map.md` | Complete route→handler→service mapping |
| `task-3-error-classification.md` | 404 vs 500 source classification |
| `task-4-404-hypotheses.md` | Ranked 404 hypotheses with evidence |
| `task-5-status-500-analysis.md` | 500 root cause analysis |
| `task-5-environment-drift.md` | Environment parity assessment |

---

## Next Fix Targets (file/function locations only)

1. **RC-1 fix target**: `app/models/mission_models.py:41` (MissionTask) and `app/models/__init__.py:20-24` (TimestampMixin) — model defines `updated_at` but DB table `mission_tasks` lacks it
2. **RC-2 fix target**: `app/models/mission_models.py:84-93` (MissionImprovement) — model references table that doesn't exist in DB
3. **RC-3 fix target**: `app/api/v1/mission.py` lines 92, 142, 209, 320, 364 — routes missing trailing-slash variants
4. **RC-4 fix target**: `app/api/v1/mission.py` — `/stream` route not defined

---

**This report is diagnosis-only. No code changes, deployments, or database mutations were performed.**
