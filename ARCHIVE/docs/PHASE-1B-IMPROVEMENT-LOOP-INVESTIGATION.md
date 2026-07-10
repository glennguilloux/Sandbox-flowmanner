# Phase 1B — Improvement Loop Investigation

**Date:** 2026-07-04
**Status:** COMPLETE
**Verdict:** 🔴 The improvement loop is **NOT running** in production. It's ~10,500 LOC of dead code.

---

## Executive Summary

The improvement loop subsystem (`backend/app/services/improvement/`) is a 6-phase autonomous self-improvement architecture comprising ~10,500 LOC across 12+ files. **None of it is actually executing.** The code exists, is importable, and would technically run — but it's never triggered, never initialized, and has no persistent state.

**Recommendation: Cut Phases 3–6 of the improvement subsystem (~7,000 LOC). Keep Phases 1–2 (failure classification + causal decomposition) as library code for the strategy profiling harness in Phase 1A.**

---

## Wiring Analysis

### Call Chain 1: Legacy MissionExecutor → Improvement Loop

```
MissionExecutor.execute_mission()
  → ... task loop ...
  → analytics, audit, Linear sync, learning recording
  → ❌ _trigger_improvement_analysis() is NEVER CALLED
```

**`_trigger_improvement_analysis`** is defined at `mission_executor.py:870` but **never invoked** from `execute_mission()`. The method exists as dead code. It calls `get_improvement_loop()` → `on_mission_complete()`, and also chains to `_trigger_critique_analysis()` (CriticAgent + ImprovementGenerator). None of this runs.

### Call Chain 2: UnifiedExecutor → Improvement Loop

```
UnifiedExecutor.execute()
  → _execute_inner()
    → strategy.execute()
  → _finalize_run()
  → _run_post_hooks()                    ← line 859
    → get_improvement_loop()             ← lazy singleton, never initialized
    → improvement.on_mission_complete()  ← THIS IS THE ONLY LIVE CALL SITE
```

**This is the only path that actually calls `on_mission_complete`.** But there's a catch: `initialize_improvement_loop()` is never called at startup (not in `main.py`, `lifespan.py`, or anywhere else), so the singleton is created fresh on first use without default knobs.

### Call Chain 3: Background Review (Celery)

```
improvement_loop_v2.on_mission_complete()
  → ... improvement analysis (see below) ...
  → asyncio.create_task(_dispatch_background_review())
    → review_mission.delay(mission_id)   ← Celery task
      → BackgroundReviewService          ← LLM-based memory writing
```

The **background review Celery task** IS dispatched from `on_mission_complete` for every mission. This is a separate concern from the improvement loop — it's an LLM-based memory writer that reviews completed missions and proposes memory writes. **This is the only component that might actually be working**, but it depends on the Celery worker being configured and the `BackgroundReviewService` being functional.

---

## Production Evidence (live DB query 2026-07-04)

```
Missions: 107 total, 80 completed, 16 failed
mission_improvements: 0 rows
critiques: 0 rows
improvement_knobs: NOT FOUND (no migration)
```

**107 missions executed. 16 failed. Zero improvement data recorded.** The subsystem has never fired in production.

---

## Database State

| Table | Status | Evidence |
|-------|--------|----------|
| `mission_improvements` | EXISTS, EMPTY | `SELECT count(*) FROM mission_improvements` → 0 rows |
| `improvement_sessions` | DOES NOT EXIST | No Alembic migration created it |
| `improvement_knobs` | DOES NOT EXIST | No Alembic migration created it |
| `hypothesis_tests` | DOES NOT EXIST | No Alembic migration created it |
| `failure_contexts` | DOES NOT EXIST | No Alembic migration created it |
| `applied_improvements` | DOES NOT EXIST | No Alembic migration created it |
| `critiques` | DOES NOT EXIST | No Alembic migration created it |

**Only `mission_improvements` exists** (likely from an early migration), and it has zero rows. The rest of the improvement subsystem's data model was never migrated to the database.

---

## In-Memory State Problems

1. **`_failure_buffer`** (`improvement_loop_v2.py`): A plain Python list that accumulates `FailureContext` objects. Resets to `[]` on every container restart. Since `initialize_improvement_loop()` is never called, and the singleton is created fresh, this buffer is always empty when `on_mission_complete` fires.

2. **`_active_sessions`**: Dict of in-memory `ImprovementSession` objects. Lost on restart.

3. **`knowledge`** (`ImprovementKnowledge`): In-memory knowledge graph of strategy effectiveness, knob effectiveness, and failure-strategy mappings. Lost on restart.

4. **`_last_improvement`**: Timestamp of last improvement session. Always `None` on fresh singleton, so the "scheduled interval" trigger never fires.

### What happens when `on_mission_complete` fires:

```python
# On success: captures success metrics (in-memory only)
# On failure: should_trigger = True
# On 5+ failures accumulated: should_trigger = True (but buffer is always empty)
# On 6+ hours since last improvement: should_trigger = True (but _last_improvement is None)
```

For a **failed mission**, `should_trigger = True` and `run_improvement_session()` is called. But:
- `_analyze_failures()` finds nothing (empty buffer, DB table empty)
- Returns `("No weak areas identified")`
- Session completes immediately with no action

---

## Fake P-Values

`hypothesis_tester.py:707`:
```python
test.p_value = 0.05 if is_significant else 0.3
```

The hypothesis tester uses a **simplified** (i.e., fake) p-value calculation. It checks if `improvement_delta >= min_improvement` (default 5%), then hardcodes p=0.05 if significant, p=0.3 if not. There is no real statistical testing — no t-test, no confidence intervals, no sample size validation.

The `_complete_test` method also evaluates immediately (no waiting for the configured `duration_minutes`), because the "wait for test to complete" step in `run_improvement_session` calls `_get_current_metrics()` synchronously right after `start_test()`.

---

## Code Surface Summary

| Component | LOC | Status | Verdict |
|-----------|-----|--------|---------|
| `improvement_loop_v2.py` | ~900 | Dead (only live call is background review dispatch) | Cut or gut |
| `causal_decomposer.py` | ~700 | Library code, no DB dependency | **Keep as library** |
| `failure_types.py` | ~200 | Library code, no DB dependency | **Keep as library** |
| `hypothesis_tester.py` | ~750 | Dead (fake p-values, no DB tables) | Cut |
| `knob_manager.py` | ~400 | Dead (DB table doesn't exist) | Cut |
| `success_learner.py` | ~500 | Dead (in-memory only, never called) | Cut |
| `strategy_evolution.py` | ~500 | Dead (depends on knob_manager) | Cut |
| `metrics_collector.py` | ~300 | Dead (never called) | Cut |
| `failure_repository.py` | ~200 | Dead (DB table doesn't exist) | Cut |
| `alerting.py` | ~200 | Dead (never called) | Cut |
| `improvement_models.py` | ~150 | Dead (models for non-existent tables) | Cut |
| `background_review_tasks.py` | ~250 | **Potentially live** (Celery task) | **Keep** |
| `background_review_service.py` | ~400 | **Potentially live** (LLM memory writer) | **Keep** |

**Total cuttable:** ~7,000 LOC (Phases 3–6: hypothesis testing, knob management, success learning, strategy evolution, metrics, alerting)
**Keep:** ~1,550 LOC (Phases 1–2: failure types, causal decomposer, background review)

---

## Background Review — The One Live Component

The `background_review_tasks.review_mission` Celery task is dispatched from `on_mission_complete` via `asyncio.create_task`. It:

1. Re-fetches the mission from DB
2. Applies skip rules: duration < 10s OR turns < 3 → skip
3. Calls `BackgroundReviewService.call_reviewer()` — an LLM call that reviews the mission transcript
4. Parses the reviewer response and proposes memory writes
5. Applies writes (direct or staged) with supersede resolution
6. Sends a notification to the user about pending writes

**This component is architecturally separate from the improvement loop.** It's a memory consolidation system, not a self-improvement system. It should be preserved regardless of the improvement loop decision.

---

## Open Questions for Glenn

1. **Is the Celery worker actually processing `review_mission` tasks?** We'd need to check Celery logs or Flower to confirm. The task is dispatched but we don't know if it succeeds.

2. **Should we keep the background review (memory writer) or cut it too?** It's ~650 LOC and depends on Langfuse (which was disabled per P1 F2). If Langfuse is disabled, the trace spans are no-ops but the task itself doesn't require Langfuse to function.

3. **Improvement loop Phases 1–2 (failure types + causal decomposer)** are useful as library code for the strategy profiling harness. Should they stay as standalone modules or be moved into the strategies package?

---

## Recommendation

| Action | LOC Impact | Risk |
|--------|-----------|------|
| Cut improvement loop Phases 3–6 | -7,000 LOC | Low (dead code, no DB tables) |
| Keep failure_types + causal_decomposer as library | +0 (already exists) | None |
| Keep background_review_tasks + service | +0 (already exists) | None |
| Wire `initialize_improvement_loop` → NOT recommended | +0 | High (would start a broken system) |

**Net result: ~7,000 LOC removed, zero behavioral change.**
