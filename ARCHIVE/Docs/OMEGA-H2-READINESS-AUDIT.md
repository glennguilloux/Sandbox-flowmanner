# Omega Roadmap: H2 (Q4 2026 – Q1 2027) Readiness Audit

*Audited: 2026-06-01*

**Goal:** *"Introduce an event-sourced substrate behind a feature flag. Old missions use the old path; new missions use the new path."*

---

## H2.1 — Event-Sourced Substrate Behind a Feature Flag ⚠️ MOSTLY IMPLEMENTED

| Requirement | Status | Evidence |
|---|---|---|
| `SubstrateEvent` model with all required fields | ✅ | `substrate_models.py`: sequence, run_id, timestamp, type, payload, causal_parent, actor — all present |
| `EventLog` with append-only API | ✅ | `event_log.py`: `append()` method with SERIALIZABLE isolation, claims DB-level trigger enforcement |
| `RunState` projection | ✅ | `SubstrateRunState` in `substrate_models.py`, used by `ReplayEngine` |
| `ReplayEngine` with deterministic replay | ✅ | `replay_engine.py`: "replay from any checkpoint with the same model+seed" |
| `ExecutorV2` runs alongside `mission_executor.py` | ✅ | `executor_v2.py`: explicitly states coexistence, writes events per state transition |
| `FLOWMANNER_SUBSTRATE_V2=run` feature flag | ✅ | Wired in `lifespan.py`: gates `TriggerBridge` vs legacy `TriggerScheduler` at startup/shutdown |
| All 7 strategies ported to substrate | ✅ | `substrate/strategies/` contains: solo, dag, swarm, pipeline, graph, langgraph, meta |
| DB-level `BEFORE UPDATE OR DELETE` trigger on `substrate_events` | ⚠️ | Claimed in `event_log.py:10` comment; **no Alembic migration or SQL definition found** |
| Substrate tests exist | ❌ | **Zero substrate tests** — no `test_substrate*`, `test_event*`, `test_executor*` files |
| 1000-node mission performance benchmark | ❓ | Unverifiable without tests |

**Verdict: IMPLEMENTED BUT UNTESTED.** The full substrate module exists with models, event log, replay engine, ExecutorV2, all 7 strategies, and feature flag wiring. However, the DB-level append-only enforcement is unverified (no migration found), and there are zero tests — no integration tests, no performance benchmarks, no chaos tests.

---

## H2.2 — The 9 Error Classes Get Budgets ✅ COMPLETE

| Requirement | Status | Evidence |
|---|---|---|
| Each error class has retry budget | ✅ | All 9 classes in `failure_analyzer.py:106-114` with `max_retries` (0–5) |
| Each error class has wall-clock budget | ✅ | All 9 classes with `max_wall_clock_seconds` (0.0–600.0) |
| Each error class has cost budget | ✅ | All 9 classes with `max_cost_usd` ($0.00–$0.50) |
| `MetaLoopOrchestrator` consults budget before retrying | ⚠️ | Orchestrator imports `FailureAnalyzer` but **does not call `can_retry`/`check_budget` methods** — budget enforcement exists in `failure_analyzer.py` but isn't wired into the orchestrator loop yet |
| Self-improvement strategy only applied within budget | ✅ | `failure_analyzer.py` H2.2 docs confirm this constraint |

**Error Class Budgets:**

| Error Class | Max Retries | Wall-Clock | Max Cost |
|---|---|---|---|
| TIMEOUT | 5 | 600s | $0.50 |
| VALIDATION | 1 | 60s | $0.10 |
| RESOURCE | 3 | 120s | $0.25 |
| LOGIC | 1 | 30s | $0.10 |
| NETWORK | 5 | 300s | $0.50 |
| PERMISSION | 0 | 0s | $0.00 |
| NOT_FOUND | 2 | 60s | $0.10 |
| RATE_LIMIT | 5 | 600s | $0.50 |
| UNKNOWN | 1 | 120s | $0.25 |

**Verdict: DONE (budgets defined) / PARTIAL (orchestrator integration).** The budget infrastructure is complete. The one gap is that `MetaLoopOrchestrator` doesn't yet call `failure_analyzer` budget checks before retrying — the budgets are defined but not consulted by the orchestrator loop.

---

## H2.3 — Capability Composer's Depth Proof ✅ COMPLETE

| Requirement | Status | Evidence |
|---|---|---|
| Replace `max_depth = 3` constants with `CapabilityLattice` depth invariant | ✅ | `capability_lattice.py` maintains `max_depth` global invariant on every composition |
| Static analysis detects loops that exit on string match | ✅ | String-based exit conditions without type constraints are explicitly rejected |
| Reject unbounded loops at composition time | ✅ | Loop composition requires `termination_condition` in 3 acceptable categories |
| Halting proof sketches for all 4 composition types | ✅ | Sequential, parallel, conditional, loop — each with halting proof in docstring |
| Three acceptable loop termination types | ✅ | 1. Explicit `max_iterations`, 2. Typed field match, 3. Strict subtype check |

**Verdict: DONE.** The capability lattice has depth invariants, static analysis for unbounded loops, and halting proof sketches for all composition types. String-based exit conditions are rejected at composition time.

---

## H2.4 — Trigger Scheduler Goes Event-Driven ⚠️ PARTIAL

| Requirement | Status | Evidence |
|---|---|---|
| Replace 30s asyncio tick | ✅ | `TriggerBridge` exists, replaces old `trigger_scheduler.py` (now deprecated) |
| Redis pubsub or PG LISTEN/NOTIFY | ❌ | Uses **2-second polling**, not pub/sub. Docstring mentions "future hook for event-driven dispatch" |
| Feature-flag gated | ✅ | `FLOWMANNER_SUBSTRATE_V2=run` gates TriggerBridge in `lifespan.py` |
| Triggers fire within 1s of cron boundary | ❌ | 2-second polling interval does not meet the 1s requirement — described as "15x improvement" over 30s |

**Verdict: PARTIAL.** The migration from 30s to 2s polling is a significant improvement and the feature flag infrastructure is in place, but pub/sub dispatch has not been implemented and the 1s boundary target is not met.

---

## H2 Exit Criteria

| Criterion | Status | Detail |
|---|---|---|
| Mission can be killed mid-run and resumed with no state loss | ⚠️ | `ExecutorV2` has `_resume_run()` and crash recovery logic, but **no test proves it works** |
| `test_kill_worker_mid_mission` passes locally | ❌ | **Chaos test does not exist anywhere in the codebase** |

---

## Overall H2 Readiness Summary

| Item | Status | H2 Est. | Remaining Work |
|---|---|---|---|
| H2.1 — Event-sourced substrate | ⚠️ Implemented, untested | 4–6 wks | DB trigger migration + full test suite |
| H2.2 — Error class budgets | ✅ Defined, ⚠️ unwired | 2 wks | Wire MetaLoopOrchestrator → budget checks |
| H2.3 — Capability depth proof | ✅ Complete | 2–3 wks | — |
| H2.4 — Trigger scheduler | ⚠️ 2s polling only | 1–2 wks | Implement PG LISTEN/NOTIFY or Redis pubsub |
| **Exit criteria** | ❌ **Not met** | — | Write `test_kill_worker_mid_mission` + substrate test suite |

**Surprising finding:** H2 is far more implemented than expected for a Q4 2026–Q1 2027 horizon. The entire substrate module — models, event log, replay engine, ExecutorV2, all 7 strategies, feature flag gating, error budgets, and capability depth proofs — already exists in the codebase. This is not "planning" work; it's code that compiles.

**What's blocking H2 from being shippable:**
1. **Zero tests** — No substrate tests, no chaos test, no performance benchmarks
2. **DB trigger unverified** — The `BEFORE UPDATE OR DELETE` trigger is claimed but no migration found
3. **Orchestrator integration gap** — Budgets defined but `MetaLoopOrchestrator` doesn't call them
4. **Trigger sub-second target** — 2s polling doesn't meet the 1s H2.4 criterion
