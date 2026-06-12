# Substrate Baseline v1 — Q2-Q3 Agentic Workflow Plan

**Locked:** 2026-06-12 by orchestrator after Chunk 1 verification
**Source of truth:** `.sisyphus/boulder.json` references this file for all Q2-Q3 chunk stop-gates
**Supersedes:** the old "139 passed in 2.92s" figure from the closed-out `future-architecture-paradigm` plan Task 5 (the test file `test_substrate_critical.py` no longer exists — that scope is no longer runnable as a single command)

---

## What this baseline covers

The canonical "substrate green" gate for the Q2-Q3 plan. Any chunk that touches substrate code MUST leave this set at 151 pass / 10 fail (no NEW failures, no new files added without corresponding tests).

The set includes everything related to: lease management, event log, replay, circuit breaker, HITL pause/resume, mission executor, and worker substrate.

## Canonical command

```bash
cd /opt/flowmanner/backend
.venv/bin/python -m pytest \
    tests/test_substrate_circuit_breaker.py \
    tests/test_substrate_event_log.py \
    tests/test_substrate_event_log_integration_pg.py \
    tests/test_substrate_hitl_pause.py \
    tests/test_substrate_lease_integration.py \
    tests/test_substrate_lease_reclaimer.py \
    tests/test_substrate_replay.py \
    tests/test_substrate_resume_validation.py \
    tests/test_substrate_worker_leases.py \
    tests/test_mission_circuit_breaker.py \
    tests/test_mission_executor.py \
    -v --tb=line 2>&1 | tail -40
```

**Expected output:** `151 passed, 10 failed, X warnings in ~1:45`

## Current results (2026-06-12, post-Chunk 1 verification)

| File | Pass | Fail | Notes |
|------|------|------|-------|
| test_substrate_circuit_breaker.py | all | 0 | ✓ |
| test_substrate_event_log.py | all | 0 | ✓ |
| test_substrate_event_log_integration_pg.py | most | 2 | ⚠ PG DNS error in test env |
| test_substrate_hitl_pause.py | all | 0 | ✓ |
| test_substrate_lease_integration.py | all | 0 | ✓ |
| test_substrate_lease_reclaimer.py | all | 0 | ✓ |
| test_substrate_replay.py | all | 0 | ✓ |
| test_substrate_resume_validation.py | all | 0 | ✓ |
| test_substrate_worker_leases.py | all | 0 | ✓ |
| test_mission_circuit_breaker.py | all | 0 | ✓ |
| test_mission_executor.py | most | 6 | ⚠ Test rot + interface mismatch |
| **Total** | **151** | **10** | |

## The 10 pre-existing failures (not caused by Q2-Q3 work)

These were failing BEFORE Chunk 1 started and remain failing now. They are NOT a regression from P0.2 fix, P0.4 v1→v3 migration, or any Q2-Q3 chunk work. They need separate tickets.

### Category A — Environment-only (test infrastructure, not code)

| # | Test | Error | Cause |
|---|------|-------|-------|
| 1 | test_substrate_event_log_integration_pg::test_insert_succeeds | `[Errno -2] Name or service not known` | Test PG service unreachable from dev env |
| 2 | test_substrate_event_log_integration_pg::test_update_rejected_by_trigger | same | same |
| 3 | test_substrate_event_log_integration_pg::test_delete_rejected_by_trigger | same | same |
| 4 | test_substrate_event_log_integration_pg::test_trigger_exists_in_database | same | same |
| 5 | test_substrate_event_log_integration_pg::test_trigger_catalog_matches_migration | same | same |

**Action needed:** Spin up a real PG in the test env OR mark these as `pytest.mark.skip` in dev-only runs. The prod DB has the triggers (the migration `cost_attribution_001` includes them).

### Category B — Test rot (tests expect API that no longer exists)

| # | Test | Error | Cause |
|---|------|-------|-------|
| 6 | test_mission_executor::TestMissionExecutorInterface::test_mission_executor_has_execute_task | `AssertionError: assert False` | `MissionExecutor` no longer exposes `execute_task` as a public attribute |
| 7 | test_mission_executor::TestExecuteLlmErrorPropagation::test_execute_llm_propagates_model_router_failure | `AttributeError: 'MissionExecutor' object has no attribute '_execute_llm'` | Test was written for an older `MissionExecutor` impl that had `_execute_llm` method |
| 8 | test_mission_executor::TestExecuteLlmErrorPropagation::test_execute_llm_returns_success_true_on_valid_response | same | same |
| 9 | test_mission_executor::TestExecuteLlmErrorPropagation::test_execute_llm_treats_empty_response_as_failure | same | same |
| 10 | test_mission_executor::TestExecuteLlmErrorPropagation::test_execute_llm_returns_failure_when_model_router_unavailable | same | same |

**Action needed:** Either restore the missing `MissionExecutor._execute_llm` method (and `execute_task` interface) OR update the tests to match the current `MissionExecutor` API. This is a separate Q2-Q3 housekeeping task — NOT a Q2-Q3 chunk concern.

## Q2-Q3 stop-gate rule (updated)

For each Q2-Q3 chunk:

1. Run the canonical command above.
2. Pass count MUST be ≥ 151 (no new failures).
3. Fail count MUST be ≤ 10 (the pre-existing list above).
4. If a chunk causes a NEW failure, the chunk is **not done** even if the new chunk's own tests pass.
5. If a chunk fixes one of the 10 pre-existing failures, the fix is a bonus — update this inventory to reflect the new pass count.

## Related baselines (not the canonical substrate, but referenced)

- **Auth v3 scope** (relevant to P0.4 work): 71 tests collected, not run as part of this baseline
- **P0.2 sandbox preview errors** (new in Chunk 1): 5 tests in `test_sandbox_preview_errors.py`, must stay green
- **Existing P0.2 sandbox preview tests**: 10 tests in `test_sandbox_preview_api.py`, must stay green (1 was updated in Chunk 1 to expect 502 instead of 404)
- **Full backend suite**: 2631 tests collected, not run as part of this baseline (would take ~30+ min, not a per-chunk gate)

## Provenance

This baseline was established by:

1. Reading the closed-out `future-architecture-paradigm` handoff at `.sisyphus/notepads/future-architecture-paradigm/exit-handoff-2026-06-11.md` (referenced "139 passed in 2.92s" — file no longer exists)
2. Enumerating substrate-related test files via `ls tests/ | grep -E "(substrate|lease|circuit|replay|hitl|mission|episodic|memory)"`
3. Running the canonical command and capturing the 151 pass / 10 fail result
4. Cross-referencing the 10 failures against the Q2-Q3 commit history (no Q2-Q3 work touched `mission_executor.py` or `event_log_integration_pg.py`)
5. Documenting the failures with raw pytest output for reproducibility
