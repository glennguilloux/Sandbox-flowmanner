# Backend Error Audit — Report for Fix Planning

**Date:** 2026-07-13
**Branch audited:** `agent/2026-07-11-intent-execution-architecture` (head `f6fc3637`)
**Method:** 4 persona-injected (`engineering-code-reviewer`) read-only kanban audits, one per backend slice, run by profiles fmw1/fmw2/fmw3/fmw_synth in isolated worktrees. Workers were told to BLOCK for review (no commit/push). Findings files written to each worktree's `.hermes/audit/`.
**Verification discipline:** every card produced a real findings file; main HEAD unchanged; all 4 worktrees had 0 commits / 0 dirty files (no rogue commits). Cited `file:line` refs spot-checked against the live tree. **Two worker claims were corrected during independent verification (see "VERIFICATION OVERRIDES" below).**

---

## Scope → card map

| Slice | Card | Profile | Findings file | 🔴 / 🟡 |
|-------|------|---------|---------------|---------|
| API / WebSocket / schemas / middleware | `t_bfeb025c` | fmw1 | `.worktrees/t_bfeb025c/.hermes/audit/BE-API-FINDINGS.md` | 4 / 4 |
| Celery tasks / workers / orchestration | `t_7afaeeda` | fmw2 | `.worktrees/t_7afaeeda/.hermes/audit/BE-TASKS-FINDINGS.md` | 10 / 20 |
| services (business logic) + governance | `t_c0f686ea` | fmw3 | `.worktrees/t_c0f686ea/.hermes/audit/BE-SERVICES-FINDINGS.md` | 5 / 5 |
| models / migrations / DB-core | `t_9d182a99` | fmw_synth | `.worktrees/t_9d182a99/.hermes/audit/BE-MODELS-FINDINGS.md` | 3 / 4 |

**Raw total reported by workers: 22 🔴 blockers + 33 🟡 suggestions.** After independent verification (below), treat ~2 🔴 as mischaracterized (still real bugs, but not the catastrophic failure the worker claimed) and confirm the rest as plausible pending a fix-author's own read.

---

## VERIFICATION OVERRIDES (worker claims corrected)

1. **`t_7afaeeda` 🔴 "swarm_tasks.py imports non-existent models — ALL swarm tasks crash on import" — PARTIALLY FALSE.**
   - Verified: `backend/app/models/swarm_models.py` **exists** (3302 bytes, Jun 23). Imports of `SwarmAgent/SwarmTask/SwarmConsensusRound/SwarmProfile` resolve. No import-time crash.
   - **Real bug underneath:** `database.py:61` sets `SessionLocal = AsyncSessionLocal` (async). `swarm_tasks.py` calls `db = SessionLocal()` then `db.query(...)` (sync SQLAlchemy 1.x API) at lines 49/58/126/343/406/472. `.query()` does not exist on an async session → **AttributeError at call-time**, not import-time. So swarm tasks fail when executed, not on import. Reclassify as 🔴 (correct severity) but fix the description: the defect is *sync-ORM-on-async-session*, not *missing models*.
   - Fix direction: replace `db.query(...)` with `select(...)` + `await db.execute(...)`; or make the task async and use the async session properly. This likely affects multiple other tasks too — a fix-author should grep `SessionLocal()` + `.query(`.

2. **`t_9d182a99` 🔴 "DELETE-on-NULL migration" — CONFIRMED REAL** (not a false positive). `alembic/versions/reconcile_schema_001_additions.py:624` runs `DELETE FROM analytics_events WHERE user_id IS NULL` before a NOT-NULL alter. The repo's own `backend/AGENTS.md` (lines 173–197) flags this as a past data-destruction violation. This is historical (already applied), so it cannot be "fixed" in the DB — but it should be flagged in planning as a known data-loss event, and any *future* NOT-NULL migration must use the sentinel-UPDATE pattern. No code change needed unless a sibling migration repeats it.

---

## Confirmed 🔴 blockers (verified against live source)

| # | Slice | Finding | Location | Status |
|---|-------|---------|----------|--------|
| B1 | API | `APIVersioningMiddleware` defined but **never mounted** in `main_fastapi.py` → `Accept-Version` negotiation / deprecation headers silently absent | `app/api/middleware/versioning.py` + `app/main_fastapi.py:109-198` | **Verified** — no `add_middleware(APIVersioningMiddleware)` in the mount list |
| B2 | API | WebSocket connect handler **admits anonymous users** (`user_id=0`) into mission/graph/workspace rooms; handler explicitly does not reject | `app/websocket/mission_ws.py:124-159` | **Verified** — code comment "Don't reject — allow anonymous". May be intentional for public subscriptions → confirm intent before assuming security hole |
| B3 | API | v2/v3 exception handlers overwrite each other (FastAPI dict keyed by class) → v2 errors lose their envelope, v3 wins | `app/main_fastapi.py:262` + `app/api/v2/middleware.py:112` + `app/api/v3/middleware.py:42` | Plausible (registration-order overwrite) — fix-author to confirm |
| B4 | API | (4th API 🔴 — see BE-API-FINDINGS.md; ref e.g. `auth_cookies.py:29` / `auth_v3_service.py:158`) | see file | Not independently re-read this pass |
| B5 | Tasks | sync `.query()` on async session in `swarm_tasks.py` (see override #1) | `app/tasks/swarm_tasks.py:49,58,126,343,406,472` | **Verified real** (call-time AttributeError) |
| B6 | Tasks | 9 other task-layer 🔴 (retry/race/swallow) — see BE-TASKS-FINDINGS.md | per file | Not re-read this pass |
| G1 | Services | **Governance approval bypass** — `_execute_tools_node` runs any tool whose status is `pending` OR `approved`; a tool still `pending` executes without approval | `app/governance/controlflow/agent.py:376-401` | **Verified** — `if tool["status"] in ["pending","approved"]` gates on pending |
| G2 | Services | **Approval flow can deadlock** — `pending_tools` cleared but never re-submitted after rejection/approval; `_check_approval_result` can return `"pending"` forever | `app/governance/controlflow/agent.py:364-401` | **Verified logic present** — deadlock risk real |
| G3–G5 | Services | 3 more services 🔴 — see BE-SERVICES-FINDINGS.md | per file | Not re-read this pass |
| M1 | Models | Migration DELETE-on-NULL data loss (override #2) | `alembic/versions/reconcile_schema_001_additions.py:624` | **Verified / historical** |
| M2–M3 | Models | 2 more models/migrations 🟡→🔴 — see BE-MODELS-FINDINGS.md (incl. `config.py` placeholder secrets accepted when `validate_secrets()` not invoked at startup) | per file | M-placeholder-secret claim plausible, high value |

---

## Highest-risk items to plan first

1. **G1 + G2 (governance approval bypass + deadlock)** — a correctness *and* safety issue in the approval workflow. A `pending` tool executing unapproved is a real authorization gap; the deadlock can stall workflows. **Plan as a single coordinated fix card** touching `app/governance/controlflow/agent.py`.
2. **B5 (sync ORM on async session in swarm_tasks.py)** — breaks swarm execution; likely a class of bug repeated across `app/tasks/`. A fix-author should grep `SessionLocal()` + `.query(` across the whole tasks tree and fix all occurrences in one card.
3. **B1 (APIVersioningMiddleware not mounted)** — broken API-version contract; cheap fix (add the mount) but high surface area for client behavior.
4. **M-placeholder-secret (`config.py`)** — `validate_secrets()` never called at startup; mis-set `APP_ENV` yields silently-insecure JWT/encryption keys. Cheap, high-value hardening.

---

## What I did NOT do (per your instructions)

- **Frontend not touched** — backend-only, as you specified. Frontend audit is a separate session.
- **No commits, no merges, no pushes** — workers blocked for review; the 4 findings files live in their worktrees only.
- **No fixes authored** — this is the planning input, not the remediation.

---

## Suggested next step (for your go-ahead)

Open **one minimal-change fix card per confirmed 🔴 cluster** (governance, swarm-task async, api-versioning mount, config-secret startup validation), each adopting `engineering-minimal-change-engineer`, wired to the exact `file:line` above, verified independently before merge. Tell me which clusters to open as fix cards (or "all"), and whether to proceed with commit/merge on this branch — I won't push/deploy without your explicit say.

**Full unredacted findings:** read the four `BE-*-FINDINGS.md` files under `/opt/flowmanner/.worktrees/<card>/.hermes/audit/`.
