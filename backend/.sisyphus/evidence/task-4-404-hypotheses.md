# Task 4: 404 Hypothesis Analysis — Correlated with Evidence

## Confirmed 404 Causes (Ranked by Evidence Strength)

### Hypothesis 1: Trailing-slash route mismatch — CONFIRMED, PRIMARY CAUSE
**Evidence**:
- Live test: `GET /api/missions/{id}` (no slash) → **200 OK**
- Live test: `GET /api/missions/{id}/` (with slash) → **404 Not Found**
- Route defined as `@router.get("/{mission_id}")` — NO trailing slash (mission.py:92)
- FastAPI does NOT auto-redirect `/path/` to `/path` by default
- Frontend/bridge sends requests WITH trailing slashes (confirmed in bridge logs: `/{id}/`, `/{id}/improvements/`, etc.)
- Same pattern for improvements: `/{id}/improvements` → 500 (route matched but DB error), `/{id}/improvements/` → 404 (no route)
- Analytics: `/{id}/analytics` → 200, `/{id}/analytics/` → 404

**Why this matters**: The bridge backend proxies requests from the frontend. The frontend adds trailing slashes. FastAPI routes without trailing slashes don't match. This explains the **majority of 404s** on detail-family endpoints.

**Affected endpoints**:
| Endpoint (no slash) | Status | Endpoint (with slash) | Status |
|---|---|---|---|
| `/{id}` | 200 | `/{id}/` | 404 |
| `/{id}/improvements` | 500 (DB bug) | `/{id}/improvements/` | 404 |
| `/{id}/analytics` | 200 | `/{id}/analytics/` | 404 |
| `/{id}/status` | 500 (DB bug) | `/{id}/status/` | 500 (route matched with slash variant) |

**Note**: `/status/` is the ONLY detail-family route defined with trailing slash: `@router.get("/{mission_id}/status/")` at line 299. That's why `/status/` returns 500 (matches route) instead of 404.

### Hypothesis 2: `/stream` route simply does not exist — CONFIRMED
**Evidence**:
- `GET /{id}/stream` → 404 (no slash, would match if route existed)
- `GET /{id}/stream/` → 404
- Grep of mission.py: no `/stream` route defined anywhere
- No streaming endpoint for missions exists in the codebase

**Rank**: Not an ownership or lookup issue. Route was never implemented.

### Hypothesis 3: Ownership mismatch — DISPROVED
**Evidence against**:
- DB query confirms: mission `014da489` has `user_id=60`
- Auth query confirms: authenticated user has `id=60`
- Direct test: `GET /{id}` (no trailing slash) returns 200 with full mission data including `user_id=60`
- `_require_owner()` passes when trailing slash is not used

### Hypothesis 4: Mission lookup failure — DISPROVED
**Evidence against**:
- `get_mission()` succeeds (confirmed by 200 response on `/{id}` without slash)
- The SQL trace in the 500 error shows the `missions` table query executes before `mission_tasks` query fails

### Hypothesis 5: Environment drift between bridge and main — PARTIALLY CONFIRMED
**Evidence**:
- Bridge logs show requests proxied to `workflows.glennguilloux.com` (the main backend)
- Bridge adds trailing slashes to all requests
- Main backend routes don't all support trailing slashes
- This is a **proxy/routing configuration drift**, not a code drift

## DB Verification Checklist (Read-Only)
If further confirmation needed:
```sql
-- Verify mission exists and ownership
SELECT id, user_id, status FROM missions WHERE id::text LIKE '014da489%';
-- Result: id=014da489..., user_id=60, status=pending ✓

-- Verify user exists
SELECT id, email FROM users WHERE id = 60;
-- Result: id=60, email=admin42@glennguilloux.com ✓
```
No further DB verification needed — live endpoint testing proved ownership is correct.
