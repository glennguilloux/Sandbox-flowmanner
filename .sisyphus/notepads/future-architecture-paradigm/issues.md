# future-architecture-paradigm issues

## Open issues
- None yet.


## Resolved issue - 2026-06-11T15:00:51.971433+00:00 Task 5 substrate-critical gate
- Symptom: substrate-critical gate failed in `tests/test_nexus_orchestrator_singleton.py` after `tests/test_meta_loop_orchestrator_budgets.py` polluted `sys.modules["app.services.nexus.orchestrator"]` with a MagicMock.
- Exact failing tests before fix:
  - `tests/test_nexus_orchestrator_singleton.py::TestOrchestratorModuleImport::test_get_nexus_orchestrator_returns_singleton`
  - `tests/test_nexus_orchestrator_singleton.py::TestOrchestratorModuleImport::test_singleton_recreation_after_none`
- Root cause: stale pre-mock in `backend/tests/test_meta_loop_orchestrator_budgets.py` was no longer necessary because `backend/app/services/nexus/orchestrator.py` already defines `_nexus_orchestrator` at module level.
- Fix: removed the `sys.modules` injection and kept the local `_mock_nexus_orch_instance` only for `MetaLoopOrchestrator` tests.
- Verification: `cd /opt/flowmanner/backend && python -m pytest tests/test_substrate_event_log.py tests/test_substrate_replay.py tests/test_failure_analyzer_budgets.py tests/test_meta_loop_orchestrator_budgets.py tests/test_trigger_bridge.py tests/test_nexus_orchestrator_singleton.py tests/chaos/test_kill_worker_mid_mission.py tests/chaos/test_kill_worker_mid_mission_process.py -v --tb=short` passed with `139 passed in 2.89s`.
