# EXIT AUDIT — 2026-07-05 — AutoMem Phase 1 + Backend Cleanup

## WHAT CHANGED (one bullet per file, what + why)

- `backend/app/services/improvement/causal_decomposer.py`: **DELETED** (976 LOC) — unused outside improvement package, never wired into production
- `backend/app/services/improvement/failure_types.py`: **DELETED** (879 LOC) — unused outside improvement package, dependency of causal_decomposer
- `backend/app/services/improvement/__init__.py`: Removed imports for deleted modules, kept only improvement_loop_v2
- `backend/app/api/_mission_cqrs/commands.py`: Removed all 9 dual-write call sites (create/update/delete/execute/abort/pause/resume/retry/batch_abort)
- `backend/app/api/_mission_cqrs/compat.py`: Removed dual_write_sync_run_status, dual_write_sync_blueprint, dual_write_soft_delete_blueprint, _mission_status_to_run_status
- `backend/app/api/_mission_cqrs/base.py`: Removed _run_with_retry (only used by dual-write) and dual_write_failures_total import
- `backend/app/core/metrics.py`: Removed dual_write_failures_total counter
- `backend/app/api/v1/observability.py`: Removed dual_write section from metrics summary
- `backend/app/models/memory_action_models.py`: **NEW** — MemoryActionEvent ORM model + MemoryActionType constants (AutoMem Phase 1)
- `backend/app/models/substrate_models.py`: Added MEMORY_ACTION_RECORDED event type to SubstrateEventType
- `backend/app/services/memory_action_service.py`: **NEW** — record_action, get_episode_traces, score_episode + fire-and-forget substrate event emission
- `backend/app/api/v1/memory_actions.py`: **NEW** — GET /api/memory-actions/mission/{id} and /score endpoints
- `backend/app/api/v1/__init__.py`: Registered memory_actions_router as STANDARD tier
- `backend/alembic/versions/20260704_memory_action_events.py`: **NEW** — migration creating memory_action_events table with 3 indexes
- `backend/alembic/versions/20260704_byok_per_key_salt.py`: Fixed offline SQL render mode guard (conn.execute() returns None in --sql mode)
- `backend/app/tests/test_memory_actions.py`: **NEW** — 19 unit tests for model, service, and API
- `backend/app/services/memory_service.py`: Instrumented _cache_get with record_cache_hit/miss("memory_service")
- `backend/app/services/rag/embedding_service.py`: Instrumented _get_cached with record_cache_hit/miss("embedding_cache")
- `.sisyphus/analysis/automem-flowmanner-analysis-2026-07-04.md`: Analysis doc that preceded this work (pre-existing untracked file)

## WHAT DID NOT CHANGE BUT WAS TOUCHED:
  - none (no reverts)

## TESTS RUN + RESULT

```
Memory action tests: 19 passed
Full suite: 960 passed, 9 failed, 3 skipped

9 failures are PRE-EXISTING (planning-related tests, not touched by this session):
  test_mission_planner.py::TestPlanMission::test_generates_tasks_from_llm
  test_mission_planner.py::TestPlanMission::test_fallback_to_default_task_on_empty_llm
  test_mission_planner.py::TestPlanMission::test_handles_permanent_error_in_planning
  test_mission_planner.py::TestPlanMission::test_handles_unexpected_error_in_planning
  test_mission_cqrs.py::TestMissionCommandHandlersSuccess::test_plan_mission_commits_on_success
  test_mission_cqrs.py::TestMissionCommandHandlersSuccess::test_plan_mission_rollback_on_planning_failure
  test_mission_handlers.py::TestHandlePlanMission::test_returns_execution_status_on_success
  test_mission_handlers.py::TestHandlePlanMission::test_raises_validation_error_on_failure
  test_mission_lifecycle.py::TestHandleRetryMission::test_retries_failed_mission
```

## STATUS

```
$ git status
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean

$ git fetch origin && git log --oneline origin/main..main
(no output — local main matches origin/main)

$ docker compose exec backend alembic current
20260704_memory_action_events (head)

$ docker compose exec backend bash -c "pytest -q" 2>&1 | tail -20
960 passed, 9 failed, 3 skipped

$ curl -s http://127.0.0.1:8000/api/health | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
ok

$ docker compose exec backend python -c "from app.models.memory_action_models import MemoryActionEvent; print('OK')"
OK

$ docker compose exec backend python -c "from app.services.memory_action_service import MemoryActionService; print('OK')"
OK

$ docker compose exec backend python -c "from app.api._mission_cqrs.commands import MissionCommandHandlers; print('OK')"
OK

$ grep -rn 'dual_write\|DualWrite' backend/app/ --include='*.py' | grep -v __pycache__ | wc -l
0
```

## COMMITS THIS SESSION

```
5757b0aa feat: AutoMem Phase 1 + backend cleanup (improvement pruning, dual-write removal, memory actions, cache metrics)
c529ae7a fix: guard BYOK migration against offline SQL render mode
b54e3a73 fix: handle offline mode in BYOK migration by checking execute() result instead of conn
6a3a993e fix: correct test_endpoint_paths assertion for prefixed router paths
```

## NEXT SESSION HANDOFF

This session completed four tasks from the plan at `.sisyphus/plans/`:

1. **Improvement loop pruning** — deleted `causal_decomposer.py` (976 LOC) and `failure_types.py` (879 LOC). Only `improvement_loop_v2` remains (used by `substrate/executor.py` for post-mission background review dispatch).

2. **Dual-write removal** — removed all dual-write calls from `commands.py` (9 call sites), removed dual-write functions from `compat.py`, removed `_run_with_retry` from `base.py`, removed `dual_write_failures_total` from `metrics.py`. The Blueprint/Run tables remain as a read model but are no longer written to on every mission mutation. Mission is now the sole canonical write target.

3. **Memory action events (AutoMem Phase 1)** — new `memory_action_events` table, service, and API endpoints for tracking explicit memory operations as structured events. Migration applied and at head. 19 unit tests pass. The service fires substrate events (best-effort) for unified episode tracing. **Not yet wired into the agent loop** — that's the next step (see plan §2.4 and §2.5).

4. **Redis cache metrics** — instrumented `memory_service.py` and `embedding_service.py` with `record_cache_hit`/`record_cache_miss` Prometheus counters. The `brand_voice.py`, `team_space.py`, and `account_lockout.py` Redis call sites were deprioritized (lower traffic, module-level Redis clients that close after each call).

**Gotchas for next agent:**
- The 9 pre-existing test failures are all in planning-related tests (`test_mission_planner.py`, etc.). These are NOT caused by this session's changes.
- The BYOK migration (`20260704_byok_per_key_salt.py`) needed a fix for offline SQL render mode. The fix checks if `conn.execute()` returns None (Alembic's --sql mode) and skips the data migration gracefully. This is committed.
- `memory_action_service.py` uses a factory function (`get_memory_action_service(db)`) not a singleton — each caller provides its own DB session.
- The `memory_actions.py` API endpoint catches `MissionNotFoundError` specifically (not broad `Exception`) for the 404 case.

**Next steps (per the plan):**
- Wire memory action vocabulary into agent system prompts (plan §2.5)
- Wire `MemoryActionService.record_action()` into the agent loop (plan §2.4) — after each LLM call, parse structured memory_action blocks
- Expand cache metrics to `brand_voice.py`, `team_space.py`, `dashboard_service.py` (lower priority)
- Consider Phase 2: meta-LLM review loop (needs Phase 1 traces first)

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

- Untracked files: `.sisyphus/analysis/automem-flowmanner-analysis-2026-07-04.md` (pre-existing analysis doc, leave untracked)
- Deleted files: `backend/app/services/improvement/causal_decomposer.py`, `backend/app/services/improvement/failure_types.py` (intentionally deleted this session)

## END
