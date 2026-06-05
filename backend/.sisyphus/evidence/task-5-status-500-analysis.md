# Task 5: 500 Status Failure Analysis — Runtime/Schema Hypotheses

## Root Cause: Missing Database Migrations (Schema Drift)

### Bug 1: `mission_tasks.updated_at` column missing — CONFIRMED
**Error**: `asyncpg.exceptions.UndefinedColumnError: column mission_tasks.updated_at does not exist`

**Code path**:
1. `get_mission_status()` (mission.py:301-317) calls `get_mission()` → succeeds
2. `_require_owner()` → passes
3. `get_mission_tasks()` (mission_service.py:162-168) executes `SELECT MissionTask...`
4. SQLAlchemy generates SQL including `mission_tasks.updated_at` because `MissionTask` inherits `TimestampMixin`
5. `TimestampMixin` (models/__init__.py:20-24) defines `updated_at` column
6. PostgreSQL rejects: column doesn't exist in `mission_tasks` table
7. Unhandled exception → 500

**DB state**: `mission_tasks` has 22 columns — no `updated_at`
**Model expects**: 23+ columns including `updated_at`

**Why this hits `/status/` but not `/{id}`**:
- `GET /{id}` only queries the `missions` table (HAS `updated_at` — 25 columns)
- `GET /{id}/status` queries `missions` THEN `mission_tasks` (MISSING `updated_at`)

### Bug 2: `mission_improvements` table missing — CONFIRMED
**Error**: `asyncpg.exceptions.UndefinedTableError: relation "mission_improvements" does not exist`

**Code path**:
1. `list_improvements()` (mission.py:320-329) calls `get_mission()` → succeeds
2. `_require_owner()` → passes
3. `SelfImprovementEngine.get_improvements()` queries `mission_improvements` table
4. PostgreSQL rejects: table doesn't exist
5. Unhandled exception → 500

**DB state**: `mission_improvements` table does not exist
**Model expects**: `MissionImprovement` (models/mission_models.py:84-93) with `__tablename__ = "mission_improvements"`

### Why Status 500 Differs from Detail 404

| Endpoint | Without trailing slash | With trailing slash | Root cause |
|---|---|---|---|
| `/{id}` | 200 ✓ | 404 | Trailing slash route mismatch |
| `/{id}/status` | 500 | 500* | `mission_tasks.updated_at` missing |
| `/{id}/improvements` | 500 | 404 | `mission_improvements` table missing (+ slash issue) |
| `/{id}/analytics` | 200 ✓ | 404 | Trailing slash route mismatch |
| `/{id}/stream` | 404 | 404 | Route not implemented |

*`/status/` has BOTH route variants defined (lines 299-300), so it matches with or without slash — always hits the DB bug.

### Environment Drift Assessment

**Main backend** (local docker):
- `mission_tasks` table: missing `updated_at` column
- `mission_improvements` table: does not exist
- Both 500s reproduced locally

**Bridge backend** (VPS):
- Acts as a proxy to `workflows.glennguilloux.com` (main backend)
- Same 500s visible in bridge logs
- Bridge adds trailing slashes → additional 404s on top of DB bugs
- **Verdict**: NOT separate environment drift. Bridge and main share the same DB bugs. The bridge's extra 404s are caused by its trailing-slash behavior.

### Likely Future Fix Targets

1. **Alembic migration** to add `updated_at` column to `mission_tasks` table
2. **Alembic migration** to create `mission_improvements` table
3. **Route fix** to add trailing-slash variants for all detail-family routes (or configure FastAPI redirect)
4. **Route addition** for `/stream` endpoint if frontend needs it
