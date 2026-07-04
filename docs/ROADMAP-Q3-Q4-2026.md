# FlowManner Roadmap — Q3/Q4 2026

**Status:** ACTIVE
**Created:** 2026-07-04
**Owner:** Glenn (decisions), coding agents (execution per phase)
**Grounded in:** `docs/DEEP-DIVE-REPORT-2026-07-03.md` (491-line deep-dive), git log as of 2026-07-04

---

## 0. Already Done (do NOT re-plan)

The deep-dive report listed 30+ recommendations across P0–P5. The following are **shipped**:

| Item | What | Commit(s) |
|------|------|-----------|
| P0 E1+E2 | Inbox auth gap + middleware opt-out | `501c821`, `dd2aa1f` |
| P1 C1 | LLM judge + eval through BudgetEnforcer | `6aed50c` |
| P1 C2 | Cloud model refs → local identifiers | `6aed50c` |
| P1 F2 | Jaeger dropped, Langfuse disabled | `6aed50c` |
| P1 E5 | Sentry webhook signing secret required | `6aed50c` |
| P2 A3 | Legacy langchain agents removed | `20b4aea` |
| P2 B2 | Plugin Manager UI (1168 LOC) | `b200a30` |
| P2 B2 | Reliability Center UI (293 LOC) | `b200a30` |
| P2 B2 | Tool Routing Inspector UI (416 LOC) | `b200a30` |
| — | Extensions endpoint removed | `e084adb` |
| — | HITL inbox SSE stream endpoint | `660bedc` |
| — | Graph integration tests fixed | `69c9da4`–`dc7ddab` |

**Net result:** backend has 6 old executors still in tree, 58 raw `fetch()` calls in frontend, 7 execution strategies untested against the 27B model, and ~15,800 LOC of dead/over-scoped code to prune.

---

## 1. Strategic Position

**Premise 1:** FlowManner's wedge is self-hosted AI workflow orchestration with durable execution, replay-based debugging, and zero-cost inference on consumer GPUs. The differentiator is the substrate, not the breadth of features.

**Premise 2:** The 27B model constraint means only `solo` and `dag` strategies are likely production-quality. Multi-agent swarm, 7-phase pipelines, and recursive meta-improvement are features that shine with frontier models. The product should lean into what the 27B does well.

**Premise 3:** The codebase has more capability than it exposes (~70 unwired endpoints) and more surface area than it can maintain (~15,800 LOC of dead/over-scoped code). The roadmap prioritizes **depth over breadth**: prune what doesn't work, wire what exists, build what differentiates.

**In scope:** Backend cleanup, frontend standardization, AI quality profiling, codebase pruning, product depth features.
**NOT in scope:** New integrations, new execution strategies, marketplace/community features, billing, A2A protocol.

---

## 2. Six-Phase Roadmap

### Phase 1 — Strategy Profiling & AI Quality Gate
**Summary.** Before investing in features that depend on multi-agent strategies, profile which of the 7 execution strategies actually work with the 27B model. Cut or downgrade strategies that degrade. Investigate the improvement loop before deciding whether to keep Phases 3–6.
**Code surface.** `backend/app/services/strategies/` (7 strategy files), `backend/app/services/improvement/` (10,570 LOC), `backend/app/services/plan_scorer.py`, `backend/app/services/evaluation/`
**Dependencies.** None — this is the gate for Phase 5 features.
**Success criteria.**
- 5 missions per strategy type executed with identical prompts; success rate, token usage, latency, output quality (via LLM judge) published in a results doc
- Strategies that fail >40% are marked deprecated in code (`DEPRECATED = True` flag)
- `solo` and `dag` confirmed as production strategies; others gated behind `STRATEGY_EXPERIMENTAL=1`
- Improvement loop: investigation doc written — is it running in production? Is `on_mission_complete` firing? Are the fake p-values blocking real decisions?
- Plan scorer cost model replaced: `estimated_cost_usd` → `estimated_tokens` + `estimated_latency_ms`
**Risk.** Finding that 4/7 strategies don't work → feels like shrinking the product. Mitigation: the strategies remain available for larger models; the 27B profile is documented, not hidden.
**Estimate.** 1.5 weeks

---

### Phase 2 — Backend Cleanup & Executor Removal
**Summary.** Migrate the 6 v1 routers that inline old executor logic to substrate strategies, then delete the 6 dead executors. Decide the dual-write fate (end it or commit to it). Upgrade langgraph.
**Code surface.**
- `backend/app/api/v1/flow_compat.py` (→ `GraphStrategy`)
- `backend/app/api/v1/graph.py` (→ `GraphStrategy`)
- `backend/app/api/v1/swarm.py` + `swarm_protocol.py` (→ `SwarmStrategy`)
- `backend/app/api/v1/orchestration.py` (→ substrate)
- `backend/app/api/v1/mission_decomposition_routes.py` (→ `DAGStrategy`)
- `backend/app/api/v1/mission_advanced_routes.py` (→ CQRS)
- Delete after migration: `mission_executor.py` (57K), `dag_executor.py`, `graph_executor.py`, `swarm/orchestrator.py`, `nexus/meta_loop_orchestrator.py`, `langgraph/agent.py` (29K)
- `backend/requirements.txt` (langgraph 0.0.40 → 0.2+)
**Dependencies.** Phase 1 (knowing which strategies are production-quality informs the migration targets).
**Success criteria.**
- 6 routers migrated: zero direct imports of old executors; all execution goes through `UnifiedExecutor`
- 6 old executors deleted; `test_event_sourced_state.py` + chaos suite pass
- langgraph upgraded to 0.2+; `test_langgraph_strategy.py` passes
- Dual-write decision doc: Glenn said "DeepSeek started too early." Options: (a) Mission is canonical, Blueprint+Run is optional → remove dual-write, keep Blueprint+Run as read model; (b) Blueprint+Run is canonical → Mission becomes a view. Doc recommends one, Glenn decides.
**Risk.** Breaking v1 routes during migration. Mitigation: migrate one router at a time, run the full test suite after each.
**Estimate.** 3 weeks

---

### Phase 3 — Frontend Standardization
**Summary.** Migrate 58 raw `fetch()` calls to `apiClient` + React Query. Add 3–5 Playwright E2E tests for critical user journeys. All 5 locales kept (Glenn's decision).
**Code surface.** `src/lib/api-client.ts`, 58 files using raw `fetch()`, `src/hooks/` (new React Query hooks), `e2e/` (new test files)
**Dependencies.** None — can run parallel to Phase 2.
**Success criteria.**
- Zero raw `fetch()` calls in production code (`grep -r "fetch(" src/ | grep -v node_modules` returns 0)
- React Query adopted as the caching/fetching standard; SWR (5 files) migrated
- 3 E2E tests: login → dashboard, create mission → execute → view results, chat → tool calling
- `npx tsc --noEmit` passes; `npx vitest run` passes
**Risk.** Auth token injection breaks during migration. Mitigation: `apiClient` already handles JWT — just wrapping existing calls in `useQuery` is mechanical.
**Estimate.** 2 weeks

---

### Phase 4 — Codebase Pruning
**Summary.** Remove dead and over-scoped code identified in the deep-dive cut list. Consolidate 21 webhook routers into a generic webhook router (Glenn's decision).
**Code surface.**
- Delete: `domain_agents/` (biotech, finance, legal) — ~600 LOC
- Delete: `marketplace.py`, `community.py`, `changelog.py`, `roadmap.py`, `votes.py` — ~2,000 LOC
- Conditional: improvement loop Phases 3–6 — ~7,000 LOC (gated on Phase 1 investigation)
- Delete: `paypal_service.py` + `subscription_service.py` — ~500 LOC
- Delete: `a2a/` (agent-to-agent protocol) — ~300 LOC
- Consolidate: 21 webhook routers → 1 generic `webhooks.py` with per-provider signature verification
**Dependencies.** Phase 1 (improvement loop decision).
**Success criteria.**
- `git diff --stat` shows ~10,000+ LOC removed (net reduction, after keeping Phases 1–2 if investigation warrants)
- All tests pass; no v1 route returns 404 for a removed module (graceful 503 or removed from router)
- Generic webhook router: per-provider signature verification preserved; test coverage maintained
- `ruff check` + `mypy` clean
**Risk.** Removing a module that something imports. Mitigation: grep for imports before each delete; the AGENTS.md system documents all module dependencies.
**Estimate.** 1.5 weeks

---

### Phase 5 — Product Depth Features
**Summary.** Build the features that differentiate FlowManner: workflow templates gallery (immediate usefulness), eval results dashboard (CI for AI), and mission timeline (agent observability).
**Code surface.**
- `frontend/src/app/[locale]/(dashboard)/templates/` — new page
- `backend/app/api/v1/templates.py` — already has CRUD, needs seed data
- `frontend/src/app/[locale]/(dashboard)/eval/` — new page
- `backend/app/api/v1/evaluation.py` — already exists, needs frontend
- `frontend/src/app/[locale]/(dashboard)/missions/[id]/timeline/` — new page
- `backend/app/api/v1/substrate.py` — replay events API already exists
**Dependencies.** Phase 1 (knowing which strategies produce quality output); Phase 3 (React Query for data fetching).
**Success criteria.**
- Templates gallery: 5+ pre-built workflow templates visible; "create from template" works end-to-end
- Eval dashboard: shows eval run history, score trends, model comparisons; reads from existing eval runner output
- Mission timeline: visualizes substrate event log as interactive timeline — tool calls, LLM calls, HITL pauses, circuit breaker trips, cost accumulation
- All 3 features: i18n keys in all 5 locales; `npx tsc --noEmit` clean
**Risk.** Building features that depend on strategies the 27B can't run. Mitigation: Phase 1 gates this phase.
**Estimate.** 3 weeks

---

### Phase 6 — Hardening & Performance
**Summary.** Fix remaining security findings, add performance monitoring, and prepare the platform for scale beyond a 1-person team.
**Code surface.** `backend/app/core/encryption.py` (BYOK salt), `backend/app/services/circuit_breaker_service.py` (per-provider), `backend/app/services/cache/`, database indexes, `Makefile` (k6 scripts)
**Dependencies.** None — can run parallel to Phase 5.
**Success criteria.**
- BYOK encryption: random per-key salt stored alongside ciphertext; migration script re-encrypts existing keys
- Per-provider circuit breaker: Redis-backed, shared across missions using the same provider
- DB index audit: `EXPLAIN ANALYZE` on top 20 queries; missing indexes added via `CREATE INDEX CONCURRENTLY`
- Cache hit rate: Prometheus counters on all Redis cache gets/sets/misses; dashboard panel
- 3 k6 load test scripts: mission create+execute, chat streaming, dashboard load
- CI audited: `load-test.yml` removed if no k6 scripts; `publish-sdk-testpypi.yml` gated to tags
**Risk.** BYOK re-encryption migration could fail mid-way. Mitigation: decrypt with old salt, re-encrypt with new, store old-salt prefix for rollback.
**Estimate.** 2 weeks

---

## 3. Decision Summary

| Phase | Adds | Risk | Weeks | Can parallel? |
|-------|------|------|-------|---------------|
| 1: Strategy Profiling | AI quality gate, improvement loop decision | Finding most strategies don't work | 1.5 | Yes (independent) |
| 2: Backend Cleanup | 6 routers migrated, 6 executors deleted, langgraph upgraded | Breaking v1 routes | 3 | After Phase 1 |
| 3: Frontend Standardization | React Query, 3 E2E tests | Auth token migration | 2 | Yes (parallel to 2) |
| 4: Codebase Pruning | ~10K+ LOC removed, webhooks consolidated | Removing something imported | 1.5 | After Phase 1 |
| 5: Product Depth | Templates, eval dashboard, mission timeline | Building on broken strategies | 3 | After Phases 1+3 |
| 6: Hardening & Performance | BYOK salt, per-provider breaker, DB indexes, k6 | BYOK re-encryption | 2 | Yes (parallel to 5) |

**Total: ~13 weeks** (sequential). With parallelism (Phase 1 || Phase 3, Phase 2 || Phase 4, Phase 5 || Phase 6): **~9 weeks**.

---

## 4. Risk Register

| # | Risk | Prob | Impact | Mitigation | Owner |
|---|------|------|--------|------------|-------|
| R1 | 4/7 strategies fail with 27B model | High | Medium | Document, gate behind flag, default to `solo` | Glenn |
| R2 | Dual-write decision deferred indefinitely | Medium | Medium | Phase 2 produces a recommendation doc; Glenn decides | Glenn |
| R3 | Pruning breaks a hidden import | Low | Low | grep before delete; AGENTS.md tracks deps | Agent |
| R4 | Frontend migration introduces auth regressions | Medium | High | E2E tests gate the migration; `apiClient` already handles JWT | Agent |
| R5 | Improvement loop investigation reveals it IS used | Low | Medium | Keep Phases 1–2, cut 3–6 only | Glenn |
| R6 | 27B model upgrade changes strategy viability | Medium | High | Re-run Phase 1 profiling when model changes | Glenn |

---

## 5. Open Decisions for Glenn

1. **Dual-write fate** (Phase 2 gate): Mission canonical + Blueprint+Run optional, OR Blueprint+Run canonical + Mission as view? Glenn said "DeepSeek started too early" — needs investigation doc before committing.
2. **Improvement loop** (Phase 1 gate): Is `on_mission_complete` → `improvement_loop_v2.on_mission_complete()` actually firing in production? If yes, keep Phases 1–2 and cut 3–6. If no, cut the whole subsystem.
3. **Extensions vs Plugins** (resolved?): The extensions endpoint was removed (`e084adb`). The plugin manager UI is built (1168 LOC). Are they now unified, or does the extensions concept still exist separately?
4. **Generic webhook router** (Phase 4): Glenn approved consolidating 21 webhook routers into 1 generic router. Confirm: keep per-provider signature verification, remove per-provider routers?

---

## Stop Rule

- This plan stays under 300 lines. Detail belongs in phase-specific implementation plans.
- No new microservices. No new execution strategies. No new integrations.
- If a phase cannot name concrete files + tests + acceptance criteria, split it.
- If a phase exceeds its estimate by 50% without a working slice, stop and re-plan.
- No deploy without human review. All changes verified on host, not in Docker.

---

## Provenance

Grounded in `docs/DEEP-DIVE-REPORT-2026-07-03.md` (491 lines, 8 sections), git log as of 2026-07-04 (commit `20b4aea`), frontend state at `92c77a5` + 8 dirty files, and Glenn's written answers to 8 open questions in the deep-dive report. Valid until: next model change, next deep-dive, or end of Q3 2026.
