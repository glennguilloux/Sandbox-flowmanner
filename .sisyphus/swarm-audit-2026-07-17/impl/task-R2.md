# R2 — Fail-close the v3 auth middleware (CRITICAL)

**Context:** Swarm audit REPORT.md §3 C1. `backend/app/middleware/scope_validator.py`
is the only pre-route gate for `/api/v3/*` but is **fail-open**:
- `:25-26` — missing/non-`Bearer ` Authorization header → `call_next` passes through (no 401).
- `:33-36` — any JWT decode error (`except Exception`) → `call_next` passes through.
Its scope logic is dead code (no route calls `register_scope_requirement`). One
forgotten `Depends(get_current_user)` on a v3 route = silent unauthenticated endpoint.

**Your task:**
1. Make the middleware **fail closed**: missing/invalid `Bearer` token on
   `/api/v3/*` must return `401 Unauthorized` (do NOT call `call_next`).
2. Keep the legitimate path: a valid token still proceeds and scope checks still apply.
3. Add a test asserting `GET /api/v3/...` (any unauthenticated v3 path) returns 401.
4. Note in the PR: v3 routes should ALSO gain a mandatory `Depends(get_current_session)`
   at the router mount as defense-in-depth (you may add that mount-level dependency
   if low-risk; otherwise file it as a follow-up).

**Constraints:** Surgical security fix. Do not change unrelated middleware. Commit to
this branch. Do NOT push, deploy, or merge. Stop and await review when done.
