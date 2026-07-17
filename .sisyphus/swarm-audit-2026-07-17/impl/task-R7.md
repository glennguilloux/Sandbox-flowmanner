# R7 — Data-layer tenancy backstop + IDOR sweep test: DESIGN + safe slice (block-for-review)

**Context:** Swarm audit REPORT.md §3 H3 (Security Engineer). Tenant isolation is
opt-in per call site: `backend/app/services/mission_service.py:53-92` falls back to
`user_id` ownership when `workspace_id` is null; `get_workspace_id`
(`backend/app/api/deps.py:366`) is caller-supplied from a header. No data-layer
backstop → IDOR risk on any endpoint that forgets the membership join. L-effort.

**Your task (plan + the safe, reviewable slice — no full schema refactor):**
1. Write an ADR proposing a mandatory `workspace_id` (or explicit `is_global=True`)
   constraint + a query helper that ALWAYS ANDs the caller's workspace membership,
   so a missing join fails closed.
2. Implement ONLY: a regression test suite asserting `Mission` / `MemoryEntry` /
   `ChatThread` GET-by-id returns 404 for a non-member workspace, AND a first
   draft of the shared membership helper (no call-site migration yet).
3. **DO NOT** alter every endpoint or run a schema migration in this card.

**Constraints:** Design + test + helper draft only. No mass edit. Commit to this
branch. Do NOT push, deploy, or merge. Stop and block-for-review (full rollout needs
human approval).
