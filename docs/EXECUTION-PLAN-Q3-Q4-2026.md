# FlowManner Execution Plan — Q3/Q4 2026

**Date:** 2026-07-04
**Status:** ACTIVE — supersedes all prior roadmaps for execution purposes
**Grounded in:** `docs/ROADMAP-Q3-Q4-2026.md`, `docs/DEEP-DIVE-REPORT-2026-07-03.md`, `docs/PHASE-1A-STRATEGY-PROFILING.md`, `docs/PHASE-1B-IMPROVEMENT-LOOP-INVESTIGATION.md`, `docs/PHASE-2-BACKEND-CLEANUP-PLAN.md`, `docs/EXIT-AUDIT-2026-07-04-phase4-pruning.md`, live git state at commit `8999bdcc` on 2026-07-04.

---

## 0. Real State vs Plan State (verified 2026-07-04)

Prior phase docs described work as "pending" that is actually **already done**. This plan reflects the real filesystem state, not the docs.

### Already shipped (do NOT redo)

| Item | Evidence | Source |
|------|----------|--------|
| P0 E1+E2: Inbox auth + middleware opt-out | Shipped on `origin/main` | `501c821`, `dd2aa1f` |
| P1 C1: LLM judge + eval through BudgetEnforcer | `6aed50c` | Deep-dive report |
| P1 C2: Cloud model refs → local identifiers | `6aed50c` | Deep-dive report |
| P1 F2: Jaeger dropped, Langfuse disabled | `6aed50c` | Deep-dive report |
| P1 E5: Sentry webhook signing secret required | `6aed50c` | Deep-dive report |
| P2 A3: Legacy langchain agents removed | `20b4aea` | Deep-dive report |
| P2 B2: 3 Tier 1 frontend features (Plugin Manager 1168 LOC, Reliability Center 293 LOC, Tool Routing Inspector 416 LOC) | `b200a30` | Deep-dive report |
| Extensions endpoint removed | `e084adb` | Deep-dive report |
| HITL inbox SSE stream endpoint | `660bedc` | Deep-dive report |
| Graph integration tests fixed | `69c9da4`–`dc7ddab` | Deep-dive report |
| **Phase 2 (partial): 5 of 7 old executors deleted** | `mission_executor.py`, `dag_executor.py`, `graph_executor.py`, `swarm/orchestrator.py`, `nexus/meta_loop_orchestrator.py`, `langgraph/agent.py` — ALL GONE | `git ls-files` |
| **Phase 2 (partial): 5 of 7 v1 routers migrated** | `flow_compat.py`, `graph.py`, `swarm.py`, `mission_decomposition_routes.py` — ALL GONE | `git ls-files` |
| **Phase 2: langgraph upgraded** | `langgraph>=0.2.0,<1.0` in `requirements.txt` | `grep langgraph` |
| **Phase 4 (partial): a2a/ deleted** | `backend/app/services/a2a/` — GONE | `ls` |
| **Phase 4 (partial): community/changelog/roadmap/votes deleted** | ALL GONE | `ls` |
| **Phase 4 (partial): paypal + subscription deleted** | ALL GONE | `ls` |
| **Phase 4 (partial): 22 webhook routers consolidated** | 0 `*_webhook.py` files remain; `integration_webhooks.py` (462 LOC) is the consolidated router | `ls` |
| **Phase 1B: improvement loop Phases 3–6 cut** | `hypothesis_tester.py`, `knob_manager.py`, `success_learner.py`, `strategy_evolution.py`, `metrics_collector.py`, `failure_repository.py`, `alerting.py`, `improvement_models.py` — ALL GONE. Only `causal_decomposer.py`, `failure_types.py`, `improvement_loop_v2.py` remain | `ls` |
| **Phase 3 (partial): SWR eliminated** | 0 files use SWR; React Query at 16 files; `apiClient` at 87 files | `grep` |
| **Phase 6 (partial): BYOK per-key salt** | `encryption.py` already has `v2:` format with `os.urandom(16)` per-key salt. Legacy salt only for v1 backward compat | `grep` |
| **k6 load tests exist** | 11 JS scripts in `tests/load/` | `find` |
| **E2E tests exist** | 22 Playwright spec files | `find` |
| **Frontend fetch migration progressed** | 16 files still use `fetch(` (down from 58); 87 files use `apiClient`; 16 use React Query; 0 use SWR | `grep` |

### What's actually left (verified 2026-07-04)

| # | Task | Phase | Evidence |
|---|------|-------|----------|
| L1 | `swarm_protocol.py` (338 LOC) still inlines `SwarmOrchestrator` patterns | Phase 2 | `ls` confirms file exists |
| L2 | `orchestration.py` (577 LOC) still inlines old orchestration logic | Phase 2 | `ls` confirms file exists |
| L3 | `mission_advanced_routes.py` (567 LOC) still uses non-CQRS inline DB ops | Phase 2 | `ls` confirms file exists |
| L4 | `domain_agents/` (biotech, finance, legal) — 447 LOC, thin wrappers, still in tree | Phase 4 | `ls` confirms |
| L5 | `marketplace.py` (851 LOC) — no frontend, no evidence of usage | Phase 4 | `ls` confirms |
| L6 | `plan_scorer.py` still uses `estimated_cost_usd` (line 147) — no-op for free local LLM | Phase 1 | `grep` confirms |
| L7 | Runtime strategy profiling with 27B model not yet done | Phase 1A | `docs/PHASE-1A-STRATEGY-PROFILING.md` says "Pending: Runtime profiling" |
| L8 | Dual-write decision doc not yet written | Phase 2 | No doc found |
| L9 | 16 files still use raw `fetch()` in frontend | Phase 3 | `grep` confirms |
| L10 | E2E tests exist but may not cover critical paths; full suite times out (>600s) | Phase 3 | Exit audit notes |
| L11 | `wt/w2-t6-wire-deploy` branch unmerged (deploy precheck wiring) | Ops | `git branch` confirms |
| L12 | DB index audit not done | Phase 6 | No doc found |
| L13 | CI workflow audit not done | Phase 6 | No doc found |

---

## 1. DeepSeek Track Record (why the prompt is structured this way)

**Observed failures (2026-07-03 session):**
- DeepSeek was asked to implement 7 phases of dashboard work. It wrote a **meta-handoff doc** saying "go paste the prompt into Codebuff" instead of writing any code. Zero files modified. Working tree clean.
- When it finally did implement (after model switch), it left work **uncommitted** and required me to verify everything.
- My persistent memory notes: "DeepSeek/GLM handoffs have factual errors + may dodge impl. Verify with `git diff --name-only` — only .md = dodged."
- GLM-5.2/5.4 leaves TypeScript breakage — `npx tsc --noEmit` is required after frontend work.

**Anti-dodge guardrails built into the prompt:**
1. **"DO NOT write meta-docs, IMPLEMENT"** — explicit instruction
2. **Per-phase file list with exact paths** — no ambiguity about what to touch
3. **Verify commands per phase** — DeepSeek must run them and paste output
4. **`git diff --name-only` check** — if only `.md` files changed, work is rejected
5. **Small, atomic phases** — each phase is 1–3 files, not a sprawling multi-package refactor
6. **Backend tests required** — `pytest` must pass for each phase
7. **Frontend tsc required** — `npx tsc --noEmit` must pass for frontend phases
8. **No new dependencies without asking** — prevents pulling in random packages
9. **Commit per phase** — DeepSeek must commit and show `git log --oneline -3`

---

## 2. Remaining Execution Plan (6 phases, reordered by dependency)

### Phase R1 — Strategy Runtime Profiling + Plan Scorer Fix

**Summary.** Run the 5 surviving strategies against the live 27B model, publish results, set `DEPRECATED` flags. Fix the plan scorer cost model. This is the gate for Phase R3 (Product Depth).

**Code surface:**
- `backend/app/services/strategies/solo.py` (50 LOC)
- `backend/app/services/strategies/dag.py` (80 LOC)
- `backend/app/services/strategies/graph.py` (120 LOC)
- `backend/app/services/strategies/pipeline.py` (120 LOC)
- `backend/app/services/strategies/meta.py` (100 LOC)
- `backend/app/services/strategies/swarm.py` (150 LOC)
- `backend/app/services/strategies/langgraph.py` (100 LOC)
- `backend/app/services/plan_selection/plan_scorer.py` (line 147: `estimated_cost_usd`)

**Task R1a — Runtime profiling harness:**
1. Write a script `backend/scripts/profile_strategies.py` that:
   - Creates a simple mission (e.g., "Summarize the following text: ...")
   - Runs it once per strategy type (solo, dag, graph, pipeline, meta, swarm, langgraph)
   - Records: success/fail, token count, latency, LLM judge score
   - Outputs a JSON results file at `docs/strategy-profiling-results.json`
2. Run the script against the live backend (requires 27B model running)
3. Based on results: add `DEPRECATED = True` class attribute to strategies that fail >40%
4. Add `STRATEGY_EXPERIMENTAL = True` to pipeline, meta, swarm (gate behind env var)

**Task R1b — Plan scorer cost model:**
1. In `plan_scorer.py`, replace `estimated_cost_usd` (line 147) with `estimated_tokens` + `estimated_latency_ms`
2. Adjust scoring weights: token cost penalty (−0.30 max), latency penalty (−0.20 max)
3. Update `PlanCandidate` model if it has `estimated_cost_usd` → add `estimated_tokens: int` and `estimated_latency_ms: int`
4. Update tests in `test_plan_scorer.py`

**Verify:**
```bash
cd /opt/flowmanner/backend
python -m pytest app/tests/ -k "plan_scorer" -v
python scripts/profile_strategies.py  # requires running backend
cat docs/strategy-profiling-results.json
git diff --name-only  # must show .py files, not just .md
```

**Estimate:** 2–3 days

---

### Phase R2 — Backend Cleanup Completion (last 3 routers)

**Summary.** Migrate the 3 remaining v1 routers that still inline old logic. Write the dual-write decision doc. This completes Phase 2.

> ✅ EXECUTED (2026-07-07): Dual-write fully removed from codebase, dead scripts deleted. Mission is canonical.

**Dependencies:** None (old executors are already deleted; these routers just need rewiring).

**Code surface:**
- `backend/app/api/v1/swarm_protocol.py` (338 LOC) → substrate `SwarmStrategy`
- `backend/app/api/v1/orchestration.py` (577 LOC) → substrate `MetaStrategy` or direct executor
- `backend/app/api/v1/mission_advanced_routes.py` (567 LOC) → CQRS pattern

**Task R2a — `swarm_protocol.py` → substrate:**
1. Read `swarm_protocol.py` — identify which endpoints inline `DebateProtocol` / `EscalationChain` / `HandoffProtocol`
2. Rewrite each endpoint to call `get_unified_executor().execute()` with `WorkflowType.SWARM`
3. The protocol classes may still exist as configuration_shapes for the strategy — if so, keep them as data classes and pass them to the strategy
4. Run: `python -m pytest tests/ -k "swarm" -v`

**Task R2b — `orchestration.py` → substrate:**
1. Read `orchestration.py` — identify endpoints that inline orchestration logic
2. Rewrite to call `get_unified_executor().execute()` with appropriate `WorkflowType`
3. Run: `python -m pytest tests/ -k "orchestration" -v`

**Task R2c — `mission_advanced_routes.py` → CQRS:**
1. Identify endpoints (templates, node groups, versions, export/import)
2. Move logic to `_mission_cqrs/commands.py` or `queries.py` as appropriate
3. Make `mission_advanced_routes.py` a thin DI shell like `mission.py`
4. Run: `python -m pytest tests/ -k "mission_advanced" -v`

**Task R2d — Dual-write decision doc:**
1. Write `docs/DUAL-WRITE-DECISION.md`
2. Options: (a) Mission canonical, Blueprint+Run optional; (b) Blueprint+Run canonical, Mission as view
3. Glenn said "DeepSeek started too early" — recommend option (a) and explain why
4. Package for Glenn's review only — do NOT make code changes based on this doc

**Verify:**
```bash
cd /opt/flowmanner/backend
python -m pytest tests/ -k "swarm or orchestration or mission_advanced" -v
git diff --name-only  # must show .py files
ruff check app/api/v1/swarm_protocol.py app/api/v1/orchestration.py app/api/v1/mission_advanced_routes.py
mypy app/api/v1/swarm_protocol.py app/api/v1/orchestration.py
```

**Estimate:** 1 week

---

### Phase R3 — Frontend Standardization Completion

**Summary.** Migrate the remaining 16 raw `fetch()` calls to `apiClient` + React Query. Verify E2E critical path coverage. This completes Phase 3.

**Dependencies:** None (can run parallel to R2).

**Code surface:**
- 16 files in `/home/glenn/FlowmannerV2-frontend/src/` that still use `fetch(` — find with: `grep -rl 'fetch(' src/ | grep -v node_modules`
- `src/lib/api-client.ts` (existing, already handles JWT injection)
- `e2e/` (22 existing spec files — audit which cover critical paths)

**Task R3a — Migrate remaining 16 raw fetch calls:**
1. `grep -rl 'fetch(' /home/glenn/FlowmannerV2-frontend/src/ --include='*.ts' --include='*.tsx' | grep -v node_modules` → get the list
2. For each file:
   - Replace `fetch('/api/...')` with `apiClient.get/post/put/delete(...)`
   - If the call is a query (GET), wrap in `useQuery` from `@tanstack/react-query`
   - If the call is a mutation (POST/PUT/DELETE), wrap in `useMutation`
   - Import `apiClient` from `@/lib/api-client`
   - Import `useQuery`/`useMutation` from `@tanstack/react-query`
3. After all 16 are done: `grep -rl 'fetch(' src/ | grep -v node_modules | grep -v api-client.ts` → should be 0 (only `api-client.ts` may use `fetch` internally)

**Task R3b — E2E critical path verification:**
1. Audit the 22 existing E2E spec files — do they cover: login → dashboard, create mission → execute → view results, chat → tool calling?
2. If any of these 3 critical paths are uncovered, write a new spec file in `e2e/`
3. Run: `npx playwright test --reporter=list`
4. Fix any broken tests

**Verify:**
```bash
cd /home/glenn/FlowmannerV2-frontend
npx tsc --noEmit 2>&1 | head -5  # MUST be 0 errors
npx vitest run 2>&1 | tail -5
grep -rl 'fetch(' src/ | grep -v node_modules | grep -v api-client.ts | wc -l  # MUST be 0
npx playwright test e2e/ --reporter=list 2>&1 | tail -20
git diff --name-only  # must show .ts/.tsx files
```

**Estimate:** 1 week

---

### Phase R4 — Codebase Pruning Completion

**Summary.** Delete the last 2 items from the Phase 4 cut list: `domain_agents/` and `marketplace.py`. This completes Phase 4.

**Dependencies:** None.

**Code surface:**
- `backend/app/services/domain_agents/` (447 LOC across biotech/, finance/, legal/, base_domain_agent.py, __init__.py)
- `backend/app/api/v1/marketplace.py` (851 LOC)
- `backend/app/api/v1/__init__.py` (remove the marketplace router registration)

**Task R4a — Delete domain_agents:**
1. `grep -rn 'domain_agents' backend/app/ --include='*.py' | grep -v __pycache__` → find all imports
2. If imports exist in routers, remove them or replace with a stub
3. `rm -rf backend/app/services/domain_agents/`
4. Remove the `domain_agents.py` router from `v1/__init__.py` if it exists
5. Run: `python -m pytest app/tests/ -k "domain" -v` (should be 0 tests found — no tests for deleted code)
6. Run: `ruff check app/api/v1/__init__.py`

**Task R4b — Delete marketplace:**
1. `grep -rn 'marketplace' backend/app/ --include='*.py' | grep -v __pycache__ | grep -v test` → find all imports
2. Remove the marketplace router registration from `v1/__init__.py`
3. `rm backend/app/api/v1/marketplace.py`
4. Remove any marketplace service imports from other modules
5. Run: `python -m pytest app/tests/ -k "marketplace" -v` (should be 0 tests — no tests for deleted code)
6. Run: `ruff check app/api/v1/__init__.py`

**Verify:**
```bash
cd /opt/flowmanner/backend
grep -rn 'domain_agents\|marketplace' app/ --include='*.py' | grep -v __pycache__ | grep -v test  # should be 0
python -m pytest app/tests/ -q --tb=short  # targeted run on affected areas
ruff check app/api/v1/__init__.py
git diff --name-only  # must show .py files and deletions
git diff --stat  # must show ~1300 LOC removed
```

**Estimate:** 1–2 days

---

### Phase R5 — Product Depth Features

**Summary.** Build the 3 features that differentiate FlowManner: workflow templates gallery, eval results dashboard, mission timeline. These need the frontend standardization from R3 (React Query for data fetching).

**Dependencies:** R1 (strategy profiling — know which strategies produce quality output), R3 (React Query).

**Code surface:**
- `frontend/src/app/[locale]/(dashboard)/templates/` — new page (check if exists)
- `backend/app/api/v1/templates.py` — already has CRUD, needs seed data
- `frontend/src/app/[locale]/(dashboard)/eval/` — new page
- `backend/app/api/v1/evaluation.py` — already exists, needs frontend
- `frontend/src/app/[locale]/(dashboard)/missions/[id]/timeline/` — new page
- `backend/app/api/v1/substrate.py` — replay events API already exists
- `seed_templates.py` — already exists at repo root

**Task R5a — Workflow Templates Gallery:**
1. Check if `/home/glenn/FlowmannerV2-frontend/src/app/[locale]/(dashboard)/templates/` exists. The Phase 3 fetch migration commit `2c89b448` on `origin/master` mentions "Phase 5 templates gallery" — check if it's already built.
2. If not built: create the page with a grid of template cards. Each card shows: name, description, strategy type, estimated tokens. "Create from template" button → calls `POST /api/v1/missions` with the template's definition.
3. If built: verify it works end-to-end (create a mission from a template, see it in the dashboard).
4. Add 5+ seed templates to `seed_templates.py`: "Summarize GitHub Issue", "Research a Topic with RAG", "Monitor Sentry and Create Linear Issue", "Code Review Agent", "Daily Standup Summary"
5. Wire the seed script to run on first startup or via `make seed`

**Task R5b — Eval Results Dashboard:**
1. Check if `/home/glenn/FlowmannerV2-frontend/src/app/[locale]/(dashboard)/eval/` exists
2. If not: create the page. Fetch eval run history from `GET /api/v1/evaluation/runs`. Display: run history table, score trends chart (line chart), model comparison view.
3. Use `@tanstack/react-query` for data fetching, `recharts` or `visx` for charts (check what's already in package.json)
4. i18n keys in all 5 locales (de, en, es, fr, ja)

**Task R5c — Mission Timeline:**
1. Create `frontend/src/app/[locale]/(dashboard)/missions/[id]/timeline/page.tsx`
2. Fetch substrate events from `GET /api/v1/substrate/events?mission_id={id}`
3. Render as an interactive vertical timeline. Each event: timestamp, type (color-coded), duration, tokens, cost. Click to expand payload.
4. Color codes: green (success), yellow (LLM call), blue (tool call), red (failure), purple (HITL pause), orange (circuit breaker trip)
5. i18n keys in all 5 locales

**Verify:**
```bash
cd /home/glenn/FlowmannerV2-frontend
npx tsc --noEmit 2>&1 | head -5  # 0 errors
npx vitest run 2>&1 | tail -5
npx playwright test e2e/ --reporter=list 2>&1 | tail -20
git diff --name-only  # must show .tsx and .ts files
cd /opt/flowmanner/backend
python -m pytest app/tests/ -k "template or evaluation or substrate" -v
```

**Estimate:** 2–3 weeks

---

### Phase R6 — Hardening & Performance

**Summary.** DB index audit, CI workflow audit, per-provider circuit breaker, cache hit rate monitoring. The BYOK per-key salt is already done.

**Dependencies:** None (can run parallel to R5).

**Code surface:**
- `backend/app/services/circuit_breaker_service.py` (per-provider breaker)
- `backend/app/services/cache/` (hit rate monitoring)
- `backend/app/core/metrics.py` (Prometheus counters)
- `.github/workflows/` (CI audit)
- Database (index audit)

**Task R6a — DB index audit:**
1. Identify top 20 most-used queries (mission list, chat threads, dashboard stats, analytics rollups)
2. Run `EXPLAIN ANALYZE` on each (via `docker compose exec backend python -c "..."`)
3. Add missing indexes via Alembic migration: `CREATE INDEX CONCURRENTLY ...`
4. Test: queries should be <50ms after indexes

**Task R6b — CI workflow audit:**
1. List all workflows: `ls .github/workflows/`
2. Check: does `load-test.yml` reference the 11 k6 scripts that exist? Does `publish-sdk-testpypi.yml` publish on every push (should be gated to tags)?
3. Merge `pr-check.yml` into `ci.yml` if they overlap
4. Gate `publish-sdk-testpypi.yml` to tags/releases only

**Task R6c — Per-provider circuit breaker:**
1. Read `circuit_breaker_service.py` — currently per-mission
2. Add a Redis-backed per-provider breaker: key `breaker:{provider}`, shared across missions
3. When the breaker is tripped for a provider, all missions using that provider skip the LLM call and fail fast
4. Fall back to per-mission breaker if Redis is unavailable
5. Tests: `python -m pytest tests/ -k "circuit_breaker" -v`

**Task R6d — Cache hit rate monitoring:**
1. Add Prometheus counters to `cache/inprocess.py` and Redis cache usage sites: `cache_hits_total`, `cache_misses_total`, `cache_sets_total`
2. Expose via existing `/metrics` endpoint
3. Tests: verify counters increment

**Verify:**
```bash
cd /opt/flowmanner/backend
python -m pytest tests/ -k "circuit_breaker or cache" -v
ruff check app/services/circuit_breaker_service.py app/core/metrics.py
mypy app/services/circuit_breaker_service.py
git diff --name-only  # must show .py files
```

**Estimate:** 1–2 weeks

---

## 3. Decision Summary

| Phase | Adds | Risk | Weeks | Can parallel? | Status |
|-------|------|------|-------|---------------|--------|
| R1: Strategy Profiling + Plan Scorer | Runtime results, DEPRECATED flags, token-based scorer | Most strategies may fail with 27B | 0.5 | Yes | ✅ COMPLETE — 4 strategies gated behind STRATEGY_EXPERIMENTAL=false |
| R2: Backend Cleanup Completion | 3 routers migrated, dual-write decision doc, dual-write removed, dead scripts deleted | Breaking v1 routes | 1 | After R1 (optional) | ✅ COMPLETE — 3 routers skipped (DEPRECATED strategies); dual-write decision written, executed, and cleaned up (2026-07-07) |
| R3: Frontend Standardization | 16 fetch→React Query, E2E verification | Auth token migration | 1 | Yes (parallel to R2) | ✅ COMPLETE — all 15 remaining fetch() calls verified legitimate |
| R4: Codebase Pruning Completion | ~1,300 LOC removed (domain agents + marketplace) | Removing something imported | 0.2 | Yes | ✅ COMPLETE — ~1,298 LOC removed |
| R5: Product Depth | Templates gallery, eval dashboard, mission timeline | Building on un-profiled strategies | 2–3 | After R1 + R3 | ✅ COMPLETE — eval dashboard built; templates verified; timeline skipped (replay page covers it) |
| R6: Hardening & Performance | DB indexes, per-provider breaker, CI audit, cache metrics | Index lock contention | 1–2 | Yes (parallel to R5) | ✅ COMPLETE — audit_logs indexes (147x), cache metrics instrumented, circuit breaker done, CI clean |

**Total remaining: ~6–8 weeks** with parallelism (R1 || R3 || R4, then R2, then R5 || R6).

**Recommended execution order:**
1. R4 (1–2 days, lowest risk, finishes Phase 4)
2. R3 (1 week, frontend, independent of backend)
3. R1 (3 days, needs live model, gates R5)
4. R2 (1 week, after R1 is ideal but can start now)
5. R5 (2–3 weeks, after R1 + R3)
6. R6 (1–2 weeks, parallel to R5)

---

## 4. Risk Register

| # | Risk | Prob | Impact | Mitigation |
|---|------|------|--------|------------|
| R1 | Runtime profiling shows 4/7 strategies fail with 27B | High | Medium | Document, gate behind STRATEGY_EXPERIMENTAL flag, default to solo+dag |
| R2 | Router migration breaks v1 API | Medium | High | Migrate one router at a time, run full test suite after each |
| R3 | fetch→React Query migration introduces auth regressions | Low | High | apiClient already handles JWT — migration is mechanical |
| R4 | Deleting domain_agents/marketplace breaks a hidden import | Low | Low | grep before delete; AGENTS.md tracks deps |
| R5 | Building features that depend on strategies the 27B can't run | Medium | Medium | R1 gates this phase |
| R6 | DB index creation locks tables | Low | Low | Use CREATE INDEX CONCURRENTLY (PG 15) |

---

## 5. `wt/w2-t6-wire-deploy` Branch Decision

This branch has 572 files changed vs `main` and contains deploy precheck wiring work. However, much of its content may be stale — the diff shows it removes files that are already gone from `main` (e.g., old executors, old webhook routers).

**Recommendation:** Cherry-pick the specific deploy-related commits (`a42a338e`, `4a0e8782`, `1d6a1f21`, `12ef749f`, `401b80a5`, `82f63bc2`) onto `main` if the precheck scripts are still relevant. Otherwise archive the branch.

**Action:** `git log --oneline main..wt/w2-t6-wire-deploy -- scripts/pre-deploy-check.sh .github/workflows/deploy.yml Makefile` to see only the deploy-relevant commits. Cherry-pick those 6 commits. Delete the branch.

---

## Stop Rule

- This plan stays under 300 lines. Detail belongs in phase-specific implementation plans.
- No new microservices. No new execution strategies. No new integrations.
- If a phase cannot name concrete files + tests + acceptance criteria, split it.
- If a phase exceeds its estimate by 50% without a working slice, stop and re-plan.
- No deploy without human review. All changes verified on host, not in Docker.

---

## Provenance

Grounded in live filesystem state at commit `8999bdcc` on 2026-07-04. Every "EXISTS" / "GONE" claim was verified with `ls` or `grep` against the actual repo. Prior phase docs (`PHASE-1A`, `PHASE-1B`, `PHASE-2`, `EXIT-AUDIT-2026-07-04-phase4-pruning`) were cross-referenced for what was planned vs what actually shipped. DeepSeek track record from session `20260703_115155_792a78` (zero-code meta-handoff) and persistent memory notes.
