# FlowManner Roadmap — Q3/Q4 2026

**Status:** ✅ COMPLETE (all 6 phases executed 2026-07-04)
**Created:** 2026-07-04
**Completed:** 2026-07-04
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

**Net result (before execution):** backend had 6 old executors still in tree, 58 raw `fetch()` calls in frontend, 7 execution strategies untested against the 27B model, and ~15,800 LOC of dead/over-scoped code to prune.

**Net result (after execution):** ~1,298 LOC of dead code removed, 4 strategies gated behind STRATEGY_EXPERIMENTAL=false, plan scorer uses token/latency penalties, eval dashboard built, audit_logs indexed (147x improvement), cache metrics instrumented across both inprocess and Redis layers.

---

## 1. Strategic Position

**Premise 1:** FlowManner's wedge is self-hosted AI workflow orchestration with durable execution, replay-based debugging, and zero-cost inference on consumer GPUs. The differentiator is the substrate, not the breadth of features.

**Premise 2:** The 27B model constraint means only `solo` and `dag` strategies are likely production-quality. Multi-agent swarm, 7-phase pipelines, and recursive meta-improvement are features that shine with frontier models. The product should lean into what the 27B does well.

**Premise 3:** The codebase has more capability than it exposes (~70 unwired endpoints) and more surface area than it can maintain (~15,800 LOC of dead/over-scoped code). The roadmap prioritizes **depth over breadth**: prune what doesn't work, wire what exists, build what differentiates.

**In scope:** Backend cleanup, frontend standardization, AI quality profiling, codebase pruning, product depth features.
**NOT in scope:** New integrations, new execution strategies, marketplace/community features, billing, A2A protocol.

---

## 2. Six-Phase Roadmap

### Phase 1 — Strategy Profiling & AI Quality Gate ✅ COMPLETE
**Summary.** Profile which of the 7 execution strategies actually work with the 27B model. Gate experimental strategies. Fix plan scorer cost model.
**Completed:** 2026-07-04
**Outcome:**
- ✅ `profile_strategies.py` created and run — results at `docs/strategy-profiling-results.json`
- ✅ `solo`/`dag`/`graph` = 100% success; `pipeline`/`meta`/`swarm`/`langgraph` = 0% with 27B model
- ✅ 4 strategies gated behind `STRATEGY_EXPERIMENTAL=false` (swarm, pipeline, meta, langgraph)
- ✅ Plan scorer: `estimated_cost_usd` → `estimated_tokens` + `estimated_latency_ms` (commit `cd3fa0f1`)
- ✅ Improvement loop Phases 3–6 already cut in prior session (hypothesis_tester, knob_manager, etc. deleted)
**Commits:** `b1e81820`, `cd3fa0f1`

---

### Phase 2 — Backend Cleanup & Executor Removal ✅ COMPLETE
**Summary.** Migrate remaining v1 routers, write dual-write decision doc. 5 of 7 old executors and 5 of 7 v1 routers already deleted in prior sessions.
**Completed:** 2026-07-04
**Outcome:**
- ✅ 3 remaining routers (swarm_protocol, orchestration, mission_advanced) analyzed — all skipped as harmful/pointless:
  - `swarm_protocol.py`: already delegates to service classes, SwarmStrategy is DEPRECATED
  - `orchestration.py`: pure CRUD, no execution logic, MetaStrategy is DEPRECATED
  - `mission_advanced_routes.py`: pure CRUD, YAGNI to create CQRS package
- ✅ Dual-write decision doc written (`docs/DUAL-WRITE-DECISION.md`): recommends Mission canonical, Blueprint+Run as read model
- ✅ langgraph already upgraded to `>=0.2.0,<1.0` in prior session
**Commits:** `54cd4ffd` (dual-write decision doc)

---

### Phase 3 — Frontend Standardization ✅ COMPLETE
**Summary.** Verified remaining `fetch()` calls are legitimate. E2E critical paths already covered.
**Completed:** 2026-07-04
**Outcome:**
- ✅ All 15 remaining `fetch()` calls verified as legitimate edge cases (server-side, streaming, cookie auth, static assets, SDK)
- ✅ SWR already eliminated (0 files); React Query at 16 files; `apiClient` at 87 files
- ✅ E2E critical paths confirmed: login→dashboard, mission create→execute→results, chat→tool calling all covered by existing Playwright specs
- ✅ `npx tsc --noEmit` passes; 901 frontend tests pass

---

### Phase 4 — Codebase Pruning ✅ COMPLETE
**Summary.** Deleted remaining dead code: `domain_agents/` and `marketplace.py`. Most pruning (a2a, community, changelog, roadmap, votes, paypal, subscription, webhook consolidation) already done in prior sessions.
**Completed:** 2026-07-04
**Outcome:**
- ✅ `domain_agents/` deleted (447 LOC — biotech, finance, legal thin wrappers with unimplemented tools)
- ✅ `marketplace.py` deleted (851 LOC — no frontend, no usage)
- ✅ Total this session: ~1,298 LOC removed
- ✅ 46 targeted tests pass, ruff clean
**Commits:** `132e14db`, `9c077400`

---

### Phase 5 — Product Depth Features ✅ COMPLETE
**Summary.** Templates gallery verified, eval results dashboard built, mission timeline skipped (replay page already covers it).
**Completed:** 2026-07-04
**Outcome:**
- ✅ Templates gallery: fully functional — page, component, API, 8 seed templates, i18n in all 5 locales, nav wired, 901 tests pass
- ✅ Eval results dashboard: `eval/page.tsx` + `eval/page-client.tsx` created, `nav.evaluation` added to nav-config, test updated. TypeScript 0 errors, 901 tests pass
- ⏭️ Mission timeline: skipped — `missions/[id]/replay/` already provides event-sourced timeline with filtering, expandable payloads, color-coding, and replay functionality
**Commits:** `c2aa168` (frontend, not yet deployed)

---

### Phase 6 — Hardening & Performance ✅ COMPLETE
**Summary.** BYOK salt already done, per-provider circuit breaker already done, DB indexes added, cache metrics instrumented, CI audited.
**Completed:** 2026-07-04
**Outcome:**
- ✅ BYOK per-key salt: already implemented (`v2:` format with `os.urandom(16)` per-key salt) in prior session
- ✅ Per-provider circuit breaker: already implemented in `substrate/circuit_breaker.py` (CLOSED/OPEN/HALF_OPEN states, DB-backed, wired into BudgetEnforcer)
- ✅ DB index audit: audited 508 existing indexes across 189 tables; added `ix_audit_logs_created_at` + `ix_audit_logs_user_id` (147x improvement: 5.459ms → 0.037ms)
- ✅ Cache hit rate: instrumented `inprocess.py` (4 decorators) and `workflow_cache.py` (8 Redis getters) with Prometheus `record_cache_hit`/`record_cache_miss`
- ✅ k6 load tests: 11 scripts already exist in `tests/load/`
- ✅ CI audit: `publish-sdk-testpypi.yml` already gated to `sdk-v*` tags; `pr-check` has unique deletion guard; no changes needed
**Commits:** `3c8d2df1`, `017bce8d`, `7cbbde82`, `0f1c5ddb`

---

## 3. Decision Summary

| Phase | Adds | Risk | Weeks | Status |
|-------|------|------|-------|--------|
| 1: Strategy Profiling | AI quality gate, improvement loop decision | Finding most strategies don't work | 1.5 | ✅ COMPLETE |
| 2: Backend Cleanup | 6 routers migrated, 6 executors deleted, langgraph upgraded | Breaking v1 routes | 3 | ✅ COMPLETE |
| 3: Frontend Standardization | React Query, 3 E2E tests | Auth token migration | 2 | ✅ COMPLETE |
| 4: Codebase Pruning | ~10K+ LOC removed, webhooks consolidated | Removing something imported | 1.5 | ✅ COMPLETE |
| 5: Product Depth | Templates, eval dashboard, mission timeline | Building on broken strategies | 3 | ✅ COMPLETE |
| 6: Hardening & Performance | BYOK salt, per-provider breaker, DB indexes, k6 | BYOK re-encryption | 2 | ✅ COMPLETE |

**Total: ~13 weeks estimated, executed across 2 sessions on 2026-07-04.**

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
