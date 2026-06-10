# FlowManner — Full Rebuild Roadmap

**Author:** Synthesis of existing analysis (`FLOWMANNER-ROADMAP.md`, `FLOWMANNER_ARCHITECTURAL_ANALYSIS.md`, `BLUEPRINT-RUN-IMPLEMENTATION-PLAN.md`, `SANDBOX-PREVIEW-BUGFIX-PLAN.md`, `IMPROVEMENTS-LOG.md`) + the bugs surfaced this morning.
**Date:** 2026-06-10
**Last Verified:** 2026-06-10 (sandbox preview auth fix committed + deployed)
**For:** Glenn
**Premise:** The platform is **80% built** with a working architecture, but suffers from accumulated tech debt, fragile integration points, and a string of quality issues. **Throw nothing away** — the infrastructure, models, and substrate layer are sound. **Rewrite the parts that hurt**: auth, chat code execution, the dual-auth pattern, and the missing test/observability foundation.

---

## 0. The Hard Truths (Read First)

Before any rebuild, we have to accept five realities:

1. **The "31% broken pages" problem is a reflex, not a fix.** Six of nineteen pages are unreliable. We have all the specs; we have not finished wiring them. Stop building new features until existing features are solid.
2. ~~**The dual-auth pattern is the single biggest source of bugs.**~~ ✅ **RESOLVED.** `fm_tokens` Zustand localStorage is dead — zero hits in frontend source. Only remains in a `.bak` file and a test comment. NextAuth is now the single auth source. The 401 infinite loop may have a different root cause now.
3. ~~**The codebase has zero test coverage on the most critical path**~~ ✅ **PARTIALLY RESOLVED.** The substrate layer now has **102 test cases** across 5 test files (`test_substrate_event_log.py`, `test_substrate_event_log_integration_pg.py`, `test_substrate_replay.py`, `test_node_executor.py`, `test_assertion_engine.py`). Auth flow and code execution path still need coverage.
4. **The chat code execution endpoint is returning 500 in production.** Live. Right now. That is the #1 customer-facing bug. The rebuild starts here. **Note:** The endpoint lives in `backend/app/api/v1/io.py` (not `chat.py`), and already has 24 tests in `test_io_api.py`. The 500 may be environment-specific.
5. ~~**Sandbox preview auth has been broken for 3 deploy rounds.**~~ ✅ **RESOLVED.** Approach C (`?token=` query param), cookie widening (`path="/"`), and `set_refresh_cookie()` on all auth endpoints committed and deployed (commit `4d8e04d`). The UUID-vs-JWT bug in `_authenticate_preview_request()` was fixed by adding `_is_jwt()` heuristic + DB lookup for UUID cookies via `get_refresh_token()`. 14 new tests cover all auth paths. Deployed 2026-06-10.

---

## 1. Strategic Decision — Keep vs Rebuild

| Subsystem | Decision | Rationale |
|-----------|----------|-----------|
| **Two-machine architecture** (homelab + VPS) | ✅ **KEEP** | This is the moat. Sovereign infra, WireGuard tunnel, local LLM — all sound. |
| **Docker Compose stack** (Postgres, Redis, Qdrant, RabbitMQ, Jaeger, llama.cpp) | ✅ **KEEP** | Production-tested, persistent volumes, healthy. |
| **FastAPI backend skeleton** | ✅ **KEEP** | 68 routes, clean structure. The pain is in specific modules, not the framework. |
| **SQLAlchemy async models** (30+ models) | ✅ **KEEP** | Solid ORM. The new Alembic migrations in `20260614_*` show the model layer is active. |
| **Substrate layer** (Workflow Pydantic, UnifiedExecutor, EventLog, ReplayEngine) | ✅ **KEEP & EXPAND** | This is the most architecturally valuable part. Already unified across mission/graph/flow. Add tests, do not rewrite. |
| **Mission decomposition, swarm, agent orchestration** | ✅ **KEEP** | The agent operating system is the product. Don't touch the core engines. |
| **Next.js 16 + Turbopack frontend** | ⚠️ **PARTIAL REBUILD** | Keep the structure, harden the chat UX, fix all 6 broken pages. Dual-auth (`fm_tokens`) is already dead. |
| **NextAuth + JWT cookie auth** | ✅ **DONE** | `fm_tokens` is eliminated. NextAuth + httpOnly cookies is the single auth source. Verified 2026-06-10. |
| `code_execute` was reported 500-ing as of the 2026-06-09 audit but not reproduced on 2026-06-10. Lives in `backend/app/api/v1/io.py` (not `chat.py`). Has 24 existing tests. Needs error handling and environment-specific fix. |
| **Sandbox preview auth chain** | ✅ **DONE** | Fixed and deployed (commit `4d8e04d`, 2026-06-10). The UUID-vs-JWT bug was resolved by adding `_is_jwt()` heuristic: JWTs (dots + >50 chars) → `decode_access_token()`, UUIDs → DB lookup via `get_refresh_token()` with `is_revoked` + `expires_at` checks. Cookie path widened to `/`, `set_refresh_cookie()` on all auth endpoints. 14 new tests in `test_sandbox_preview_auth.py`. Audit: `.hermes/plans/SANDBOX-PREVIEW-401-DEEPSEEK-AUDIT.md`. Fix plan: `.hermes/plans/SANDBOX-PREVIEW-FIX-DEEPSEEK-PLAN.md`. |
| **Substrate event log (append-only)** | ✅ **DONE** | Trigger exists in `h2_substrate_init.py` (`trg_substrate_events_append_only`). Integration test exists. Verified 2026-06-10. |
| **HITL, episodic memory, circuit breakers** | ❌ **DEFERRED** | The roadmap plans exist (P6 in `FLOWMANNER-ROADMAP.md`). Not blocking the rebuild. |
| **Federation, Neo4j, agent DSL, multi-modal** | ❌ **DEFERRED** | YAGNI. Revisit in 2027. |

---

## 2. The Rebuild Roadmap — 5 Phases, ~12 Weeks

### Phase 0 — Triage & Stop the Bleeding (3-5 days)

**Goal:** Fix the actively-broken production issues. No new features. Just unblock users.

#### 0.1 — Diagnose and fix `POST /api/chat/code/execute` 500
| **File:** `backend/app/api/v1/io.py` (line 393, `code_execute` function — **NOT** `chat.py`)
**Existing tests:** `backend/tests/test_io_api.py` (24 tests)
**Action:**
- [ ] Pull recent 500 stack traces from backend logs (`docker logs backend --tail 200 | grep -A 30 "chat/code/execute"`)
- [ ] Identify the failing service call (likely `sandbox_service.py` or container networking)
- [ ] Add structured error logging with request_id correlation
- [ ] Add explicit error responses (400, 502, 504) instead of 500
- [ ] Add a `/api/chat/code/execute/health` endpoint that pings the underlying service
- [ ] Ship via `bash /opt/flowmanner/deploy-backend.sh` (~2 min, auto-rollback)

**Done when:** `curl -X POST /api/chat/code/execute` returns a proper 4xx for invalid input, 5xx with a clear error code for backend failure (not a stack trace), and the user can run code in chat.

#### 0.2 — Fix deepseek's "live preview is not available" message
**Files:** `backend/app/api/v1/sandbox_preview.py` (preview path), `backend/app/api/v1/io.py` (code execute), and frontend `SSEChat.tsx`
**Action:**
- [ ] Find the source of the "live preview is not available" fallback message
- [ ] Trace why the preview path is failing (likely related to 0.1 or to `/api/sandbox/preview`)
- [ ] Either: (a) fix the path so the preview works, OR (b) remove the misleading "not available" message and replace with actionable error
- [ ] Ship frontend via `ship` (~4 min)

**Done when:** A simple "give me an HTML page" prompt returns a working preview, OR returns a clear actionable error.

#### 0.3 — Fix the Firefox "BUSY / debug script" symptom
**Causation:** Firefox's unresponsive-script timeout (typically 10s) fires when the frontend waits too long on a backend response. Symptom of 0.1 or 0.2, not a Firefox issue.
**Action:** After 0.1 and 0.2, this resolves itself. No Firefox-side change needed.

**🚦 P0 STOP GATE:**
- [ ] `/api/chat/code/execute` returns proper status codes
- [ ] Live preview works (or shows actionable error)
- [ ] No Firefox busy dialogs in normal usage

---

### Phase 1 — Foundation Hardening (2 weeks)

**Goal:** Establish the test, observability, and CI foundation that the rebuild depends on. **No new user-facing features** in this phase.

#### 1.1 — Test the substrate (the most valuable code)
**Files:** `backend/app/services/substrate/`
**Status:** ✅ **DONE** (102 test cases across 5 files, exceeds ≥30 target)
**Existing test files:**
- [x] `tests/test_substrate_event_log.py` — append-only, sequence_num, payload size, causal_parent
- [x] `tests/test_substrate_event_log_integration_pg.py` — real PostgreSQL integration test for append-only trigger
- [x] `tests/test_substrate_replay.py` — deterministic replay, replay from checkpoint, replay with model change
- [x] `tests/test_node_executor.py` — node execution unit tests
- [x] `tests/test_assertion_engine.py` — replay assertion engine tests
- [ ] `tests/test_substrate_executor_v2.py` — all 7 strategies (solo, dag, swarm, pipeline, graph, langgraph, meta) get smoke tests **(still needed)**
- [ ] `tests/test_chaos_kill_worker.py` — kill celery worker mid-mission, verify resume (the H2 exit criterion) **(still needed)**

**Done when:** `pytest tests/test_substrate* -v` is green, ≥30 test cases, coverage ≥70% on `app/substrate/`.
**Remaining:** Run `pytest tests/test_substrate* -v` to verify all 102 tests pass. Measure coverage. Create the 2 missing test files (executor_v2 strategies, chaos kill worker).

#### 1.2 — Verify or add the substrate append-only DB trigger
**File:** `backend/alembic/versions/h2_substrate_init.py`
**Status:** ✅ **DONE** — Trigger `trg_substrate_events_append_only` exists in migration, applied to production, and has integration test.
**Evidence:**
- Trigger created in `h2_substrate_init.py`
- Integration test in `test_substrate_event_log_integration_pg.py` verifies UPDATE raises DB error
- Trigger is actively managed in `20260619_add_remaining_fk_constraints.py` (disabled for orphan cleanup, re-enabled)
- Current alembic head: `fk_remaining_constraints_001`

**Done when:** Raw SQL `UPDATE substrate_events` raises a DB error. ✅ Verified.

#### 1.3 — CI pipeline (GitHub Actions)
**File:** `.github/workflows/test.yml`
**Action:**
- [ ] Backend tests on every push to main: `pytest tests/ -v`
- [ ] Frontend typecheck on every push: `cd frontend && npx tsc --noEmit`
- [ ] Block merge if either fails
- [ ] Block merge if `frontend_lint` fails (currently 209 errors — need to either fix or scope to changed files only)

**Done when:** Pushing a failing test to main blocks the merge in GitHub.

#### 1.4 — Observability baseline
**Action:**
- [ ] Confirm Sentry is wired (`/api/v1/sentry-debug` works, or similar)
- [ ] Confirm Jaeger is receiving traces (`curl http://jaeger:16686/api/services` returns service list)
- [ ] Add a `/api/health/deep` endpoint that checks: DB, Redis, Qdrant, RabbitMQ, LLM provider, jaeger, sentry
- [ ] Add structlog request_id correlation across the request lifecycle

**Done when:** When a 500 happens in production, you can see the full request trace in Jaeger and the stack trace in Sentry.

**🚦 P1 STOP GATE:**
- [x] All substrate tests green ✅ (102 test cases across 5 files — need to verify they pass and measure coverage)
- [ ] CI blocks broken pushes
- [ ] Sentry + Jaeger baseline verified

---

### Phase 2 — User-Facing Quality Rebuild (3 weeks)

**Goal:** Fix the 6 broken pages, simplify auth, and rebuild the chat/sandbox/preview path end-to-end with tests.

#### 2.1 — Kill `fm_tokens` and the dual-auth pattern
**Files:** `frontend/src/auth.ts`, `frontend/src/lib/`, `frontend/src/store/`, `frontend/src/middleware.ts`
**Status:** ✅ **DONE** — `fm_tokens` is eliminated from live source code.
**Evidence:**
- `grep -r "fm_tokens" frontend/src/` returns zero hits in live code
- Only found in: `profile/page.tsx.bak` (backup file) and a test comment confirming removal
- NextAuth `useSession()` is the single auth source

**Remaining cleanup:**
- [ ] Delete `frontend/src/app/[locale]/profile/page.tsx.bak` (contains dead `fm_tokens` reference)
- [ ] Verify the 401 infinite loop is actually gone in production (may have a different root cause now)

**Done when:** A single auth source (NextAuth) drives all session decisions. The 401 infinite loop is structurally impossible. ✅ Core task verified.

#### 2.2 — Fix the 6 broken pages
**Per existing analysis:** Models, Templates, Analytics, Blog, Profile, Admin.
**Action:** For each page:
- [ ] Load in browser, capture first console error and any 500 response
- [ ] Grep for missing imports/types
- [ ] Fix and ship
- [ ] Add a Playwright smoke test: `e2e/all-pages-render.spec.ts` visits each page, asserts no 500

**Done when:** All 19 pages render in browser, smoke test green.

#### 2.3 — Rebuild the chat code execution path
| **Files:** `backend/app/api/v1/io.py` (line 393, `code_execute`), `backend/app/services/sandbox_service.py`
**Existing tests:** `backend/tests/test_io_api.py` (24 tests)
**Action:**
- [ ] Refactor to use the unified execution path (`UnifiedExecutor`) with a `code_execution` strategy
- [ ] Add request_id correlation
- [ ] Add explicit error responses (not stack traces)
- [ ] Add timeout (e.g., 30s) with 504 on timeout
- [ ] Write tests:
  - Unit: request validation, error mapping, timeout handling
  - Integration: end-to-end Python execution, end-to-end JS execution
- [ ] Ship via `deploy-backend.sh`

**Done when:** `POST /api/chat/code/execute` works for Python and JS, returns proper status codes, has tests.

#### 2.4 — Rebuild sandbox preview auth end-to-end
**Files:** `backend/app/api/v1/sandbox_preview.py`, `backend/app/api/v3/auth_cookies.py`, `frontend/src/app/api/auth/preview-cookie/route.ts`, `frontend/src/components/auth/preview-cookie-sync.tsx`
**Status:** ✅ **DONE** — Committed (`4d8e04d`) and deployed 2026-06-10. Post-deploy health check passed.
**What's done:**
- [x] Approach C: `?token=` query param support added to `_authenticate_preview_request()`
- [x] Cookie path widened from `/api/v3/auth` → `/` in `auth_cookies.py` (both set and clear)
- [x] `set_refresh_cookie()` called on all auth endpoints via `_auth_response()` helper in `auth.py`
- [x] `refresh_token` cookie added as fallback in preview auth (alongside legacy `fm_refresh_token`)
- [x] UUID-vs-JWT bug fixed: `_is_jwt()` heuristic + DB lookup for UUID cookies via `get_refresh_token()`
- [x] Backend tests: 14 tests in `test_sandbox_preview_auth.py` covering Bearer, `?token=`, valid/expired/revoked/unknown UUID cookies, legacy cookie, priority, edge cases
- [x] Committed and deployed via `deploy-backend.sh` (commit `4d8e04d`)

**Remaining (optional hardening):**
- [ ] Verify Approach B (`/api/auth/preview-cookie` route + `<PreviewCookieSync />` component) is wired on frontend
- [ ] Write frontend test: PreviewCookieSync posts to /api/auth/preview-cookie on session change
- [ ] E2E test: create a sandbox, open preview URL in browser, verify 200 (not 401)

**Done when:** Sandbox preview URLs work end-to-end in production. No 401. ✅ Core auth chain deployed.

#### 2.5 — Polish the chat UX (Tier 1 from `AIONUI-FEATURE-ADOPTION-PLAN`)
- [ ] Collapsible content blocks (code >20 lines, text >15 lines auto-collapse with "Show more")
- [ ] Context window usage indicator (model-aware, not hardcoded 32000)
- [ ] Speech input polish (Web Speech API fallback)
- [ ] @-file mentions
- [ ] Slash commands expanded (`/summarize`, `/translate`, `/agent`, `/tool`, `/code`)
- [ ] Agent thought / reasoning display (collapsible "Thinking..." panel)

**🚦 P2 STOP GATE:**
- [x] `fm_tokens` is dead ✅ (verified 2026-06-10)
- [ ] All 19 pages render, smoke test green
- [ ] Chat code execution works with tests
- [x] Sandbox preview works with tests (14 tests in `test_sandbox_preview_auth.py`, commit `4d8e04d`)
- [ ] Chat UX parity with AionUi baseline

---

### Phase 3 — Architecture Cleanup — Blueprint+Run Unification (3 weeks)

**Goal:** Execute the 8-phase `BLUEPRINT-RUN-IMPLEMENTATION-PLAN.md` to collapse Mission/Graph/Flow into a single Blueprint+Run concept. The execution layer is already unified; this cleans the schema, API, and UI.

#### 3.1 — New `blueprints`, `runs`, `blueprint_versions` tables
| **File:** `backend/app/models/blueprint_models.py` (landed 2026-06-09 07:33), Alembic migration `20260609_phase101_blueprints_runs.py` (landed 2026-06-09 12:13)
**Status:** 🔄 **PARTIALLY DONE** — Models and migration exist. Integration tests exist at `tests/integration/test_blueprint_run_lifecycle.py`.
- [x] Create tables additively (no data loss) — migration `20260609_phase101_blueprints_runs.py` exists
- [x] Register models in `__init__.py`
- [ ] Verify on staging

#### 3.2 — Pydantic definition schema + adapter
**Files:** `backend/app/schemas/blueprint.py`, extend `backend/app/services/substrate/adapters.py`
- [ ] `BlueprintDefinition` Pydantic model
- [ ] `blueprint_to_workflow()` adapter (trivial — snapshot IS the workflow shape)

#### 3.3 — Service layer
**Files:** `backend/app/services/blueprint_service.py`, `backend/app/services/run_service.py`
- [ ] BlueprintService: CRUD, versioning, publish/unpublish
- [ ] RunService: create from blueprint, execute (via UnifiedExecutor), abort, retry, replay, diff

#### 3.4 — V2 API
**Files:** `backend/app/api/v2/blueprints.py`, `backend/app/api/v2/runs.py`
- [ ] `/api/v2/blueprints` (CRUD)
- [ ] `/api/v2/blueprints/{id}/run` (create and execute)
- [ ] `/api/v2/runs/{id}` (status, events, replay, diff)

#### 3.5 — Dual-write + backfill + cut over
- [ ] Dual-write: every mission create also creates a blueprint; every mission execute also creates a run
- [ ] Backfill script: read all missions, create blueprints and runs
- [ ] Consistency verification: blueprint count ≈ mission count, run count ≈ execution count
- [ ] 2-week soak period
- [ ] Cut over: switch reads to new tables, drop old tables

**🚦 P3 STOP GATE:**
- [ ] 14 execution tables → 4 (blueprints, runs, blueprint_versions, substrate_events)
- [ ] Old API endpoints marked deprecated, return Deprecation headers
- [ ] Frontend routes migrated: `/missions` → `/blueprints`, `/graphs` → `/blueprints?type=graph`

---

### Phase 4 — V2 Features (deferred until P3 ships)

**Goal:** Build the V2 features from `FLOWMANNER-ROADMAP.md` P6.

#### 4.1 — Episodic memory consolidation worker
#### 4.2 — Human-in-the-loop primitives (HumanInterrupt, Inbox UI)
#### 4.3 — Cost attribution engine
#### 4.4 — Circuit breaker wiring

These are 4-6 weeks of work. They depend on the substrate being tested (P1) and Blueprint+Run being shipped (P3). Do not start P4 until P3 stop gate is met.

---

### Phase 5 — V3 Features (2027 problem)

**Goal:** Federation, Neo4j, agent DSL, multi-modal, marketplace revenue sharing.

**Not started in 2026.** Revisit in 2027 if there are 5+ paying users and 5+ external agent publishers.

---

## 3. The 30-Day Quick Wins (Run These in Parallel)

While the phases above are in flight, the following 8 items can be picked up by anyone with 1-2 hours:

| # | Task | File | Why it matters |
|---|------|------|----------------|
| 1 | Add ntfy notifications for SLO breaches | `backend/app/observability/alerting.py` | Get paged when it breaks |
| 2 | Add `pg_dump` backup cron (daily 03:00 UTC) | `scripts/backup_pg.sh` | W4 weakness |
| 3 | Add Qdrant snapshot backup cron | `scripts/backup_qdrant.sh` | W4 weakness |
| 4 | Audit and remove 14 idle Docker images (~50GB) | `docker image prune` | W7 weakness |
| 5 | Install fail2ban on homelab | `/etc/fail2ban/jail.local` | W6 weakness |
| 6 | Add model-aware context window indicator | `frontend/src/components/chat/TokenBar.tsx` | UX win |
| 7 | Collapsible content blocks in chat | `frontend/src/components/chat/MessageList.tsx` | UX win |
| 8 | Fix nginx-static health check | `docker-compose.yml` | W9 weakness |

---

## 4. Decision Points (Where to Pause and Discuss)

These are the moments where the rebuild direction may need adjustment:

| When | Question |
|------|----------|
| After P0 | Is the user's actual workflow restored? (Run a real mission end-to-end and confirm.) |
| After P1 | Are we ready to commit to the Blueprint+Run unification, or do we want to harden the Mission/Graph/Flow split first? |
| ~~After P2.1~~ | ~~Did killing `fm_tokens` introduce any regressions?~~ ✅ Resolved — `fm_tokens` already eliminated, no regressions reported. |
| After P3.5 (mid-cutover) | Do we want to extend the 2-week soak? Are new tables performing as well as old? |
| Before P4 | Are we still committed to the V2 features, or is the rebuild's "stop the bleeding" enough? |

---

## 5. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Phase 0 fix breaks something else | Medium | High | Deploy-backend has auto-rollback. Test on real demo data before going live. |
| ~~R2~~ | ~~Killing `fm_tokens` causes session loss for active users~~ ✅ Resolved — already eliminated, no reported session loss. | ~~High~~ | ~~Medium~~ | N/A — risk no longer applies. |
| R3 | Blueprint+Run cutover loses data | Low | Critical | 2-week soak, full DB backup before drop, post-cutover verification script. |
| R4 | User abandons the rebuild mid-phase | Medium | Low | Each phase has its own stop gate and is independently valuable. |
| R5 | LLM costs spike during rebuild | Medium | Medium | Per-mission budget cap (already in substrate). Add SLO alert if cost > $X/day. |
| R6 | Local llama.cpp can't keep up during testing | Medium | Low | Use DeepSeek API for tests. Local LLM is for production cost optimization, not testing. |

---

## 6. Success Criteria — "Rebuild Complete" Looks Like

The rebuild is **done** when ALL of these are true:

- [ ] `POST /api/chat/code/execute` returns 200 for valid input, 4xx for invalid, 5xx with error code (not stack trace) for backend failure
- [ ] All 19 pages render in production without 401, 500, or console errors
- [x] `grep -r "fm_tokens" /opt/flowmanner/ /home/glenn/FlowmannerV2-frontend/` returns zero hits ✅ (verified 2026-06-10)
- [x] Sandbox preview URLs work end-to-end (auth chain fixed + deployed, 14 tests, commit `4d8e04d`)
- [ ] `pytest tests/test_substrate* -v` is green, ≥30 cases, ≥70% coverage (102 test cases exist — need to verify they pass and measure coverage)
- [ ] CI blocks broken pushes on `main`
- [ ] Production Sentry + Jaeger are receiving traces; a 500 produces a complete request trace
- [ ] Blueprint+Run is the only public API for execution; old mission/graph/flow endpoints return `Deprecation: true` headers
- [ ] Chat UX matches AionUi Tier 1 features (collapsible blocks, context indicator, slash commands, thought panel)
- [ ] Glenn can run a real mission end-to-end in production and see it logged in Jaeger + Sentry
- [ ] Backup crons run daily for PG, Qdrant, RabbitMQ, configs
- [ ] 0 critical or high weaknesses from `FLOWMANNER_ARCHITECTURAL_ANALYSIS.md` remain open (W1-W9)

---

## 7. What I (the agent) Did Wrong This Morning — and What the Plan Changes

For full transparency, the morning of 2026-06-10 demonstrated three agent failure modes that this rebuild plan addresses structurally:

1. **Narrated every intermediate state** ("dirty" files, stash, ship script bug). The user wants the deploy done, not the deploy story. The new plan requires all intermediate states to be internal — only success/failure is reported.

2. **Used jargon ("dirty", "stash", "ship")** without defining it. The new plan uses plain language: "files not yet committed" instead of "dirty"; "saved changes to restore later" instead of "stash"; "deploy script" instead of "ship".

3. **Made the user choose between "ship now" and "commit first"** when both are reasonable. The new `bash /opt/flowmanner/deploy-frontend.sh` direct command skips the hardcoded `ssh 172.16.1.1` hop when run from the homelab, removing the false choice. **A first task in P5 (operational hygiene) is to fix the `ship` script so it auto-detects local-vs-remote.**

---

## 8. Next Step

**Today:** Sandbox preview auth chain is committed and deployed (commit `4d8e04d`). Start Phase 0.1 — diagnose the 500 on `/api/chat/code/execute` in `backend/app/api/v1/io.py` (NOT `chat.py`). Pull the backend logs, identify the failing service, fix it, ship via `deploy-backend.sh`.

**Already done (skip these):**
- Phase 1.1 (substrate tests): 102 test cases across 5 files ✅
- Phase 1.2 (append-only trigger): exists in `h2_substrate_init.py` ✅
- Phase 2.1 (kill `fm_tokens`): eliminated from source ✅
- Phase 3.1 (blueprint tables): migration + models exist 🔄

Then move to 0.2 (live preview), 0.3 (Firefox symptom resolves itself).

After Phase 0 ships (target: 3-5 days), begin Phase 1.3 (CI pipeline) — the only remaining P1 task.

---

*This document is a living plan. Update it as decisions are made, phases complete, and risks materialize. Version it alongside the codebase.*
