# DEEPSEEK LONG JOB — Backend H2 Substrate Hardening + Test Coverage

TASK: H2-LONGJOB — Make the event-sourced backend substrate production-ready with real tests and targeted hardening
PHASE: P2 + P3 (from FLOWMANNER-ROADMAP)
PROJECT: FlowManner
REPO ROOT: /opt/flowmanner/backend

## Mission
You are working on FlowManner backend (FastAPI + SQLAlchemy async). The substrate architecture is mostly built, but test coverage and hardening are incomplete. Your job is to close that gap with a focused, high-signal backend sprint.

Do not do broad refactors. Do not touch frontend. Do not deploy to VPS.

## Ground Truth (already verified)
The following files exist and are the canonical substrate path:
- /opt/flowmanner/backend/app/models/substrate_models.py
- /opt/flowmanner/backend/app/services/substrate/event_log.py
- /opt/flowmanner/backend/app/services/substrate/replay_engine.py
- /opt/flowmanner/backend/app/services/substrate/executor_v2.py
- /opt/flowmanner/backend/app/services/substrate/trigger_bridge.py
- /opt/flowmanner/backend/alembic/versions/h2_substrate_init.py

Related orchestration/budget files:
- /opt/flowmanner/backend/app/services/nexus/failure_analyzer.py
- /opt/flowmanner/backend/app/services/nexus/meta_loop_orchestrator.py

Known gap:
- Dedicated substrate test suite is missing in /opt/flowmanner/backend/tests (except generic chaos suite).

## Hard Constraints
- Respond in English only.
- Scope only backend files under /opt/flowmanner/backend.
- No new external dependencies unless absolutely required. Prefer existing stack.
- Do not edit unrelated modules.
- Do not deploy to VPS.
- If you create new .py files, run chmod 644 on them.
- Avoid fix→build→fail loops. Batch changes, then validate.

## Primary Deliverables
Create the following test files (or update if already present):
1. /opt/flowmanner/backend/tests/test_substrate_event_log.py
2. /opt/flowmanner/backend/tests/test_substrate_replay.py
3. /opt/flowmanner/backend/tests/test_substrate_executor_v2.py
4. /opt/flowmanner/backend/tests/test_failure_analyzer_budgets.py
5. /opt/flowmanner/backend/tests/test_meta_loop_orchestrator_budgets.py
6. /opt/flowmanner/backend/tests/test_trigger_bridge.py
7. /opt/flowmanner/backend/tests/chaos/test_kill_worker_mid_mission.py

Then add a report file:
8. /opt/flowmanner/backend/H2-SUBSTRATE-HARDENING-REPORT.md

## What Each Test Must Cover

### A) test_substrate_event_log.py
- append() writes sequential events for same run_id
- get_latest_sequence() correctness
- run_exists() behavior before/after append
- get_events() filtering (from_sequence, to_sequence, event_type)
- safety limit behavior (MAX_EVENTS_PER_RUN guard)
- append-only semantics verification strategy:
  - If DB trigger test is feasible in current environment, include an integration test that UPDATE/DELETE on substrate_events fails.
  - If not feasible in unit mode, include explicit test note + migration assertion fallback.

### B) test_substrate_replay.py
- rebuild_state() correctness on mission/task lifecycle
- rebuild_state_at_sequence() time-travel correctness
- verify_determinism() true for stable event stream
- checkpoint sequence extraction correctness

### C) test_substrate_executor_v2.py
- new run path vs resume path
- terminal state short-circuit behavior on resume
- no-tasks failure path
- mission/task projection updates in relational tables
- abort signal path

Use focused mocking for DB/session/event_log/replay_engine where needed. Keep tests deterministic.

### D) test_failure_analyzer_budgets.py
- per-error-class budget initialization
- retry budget exhaustion
- wall-clock budget exhaustion behavior
- cost budget exhaustion behavior
- analyze_failure() returns non-recoverable when class budget exhausted
- reset_budgets() semantics

### E) test_meta_loop_orchestrator_budgets.py
- plan_execute_observe() resets budgets for new mission_id
- _get_effective_max_depth() clamps with capability lattice
- _handle_failure() calls analyzer with wall_clock_ms and cost_usd
- recoverable retry path recurses
- non-recoverable path returns failure with failure_analysis payload

### F) test_trigger_bridge.py
- start/stop lifecycle
- _poll_once() calls process_cron_triggers and commits DB
- error path logging on polling failure
- stats fields correctness
- notify_trigger_due() no-op behavior (currently polling fallback)

### G) chaos/test_kill_worker_mid_mission.py
- Add a realistic chaos-oriented test for crash/recovery logic at substrate level.
- If true process-kill chaos is not practical in CI, simulate crash boundary with persisted events + resume verification and document this clearly in the report.

## Allowed Code Changes (if tests expose real defects)
You may patch ONLY these files if required for tests to pass:
- /opt/flowmanner/backend/app/services/substrate/event_log.py
- /opt/flowmanner/backend/app/services/substrate/replay_engine.py
- /opt/flowmanner/backend/app/services/substrate/executor_v2.py
- /opt/flowmanner/backend/app/services/substrate/trigger_bridge.py
- /opt/flowmanner/backend/app/models/substrate_models.py
- /opt/flowmanner/backend/app/services/nexus/failure_analyzer.py
- /opt/flowmanner/backend/app/services/nexus/meta_loop_orchestrator.py

Do not change API contracts unless strictly necessary and justified.

## Execution Plan (perform in this order)

### Step 1 — Baseline Discovery
- Read all target substrate + nexus files listed above.
- Read test fixtures:
  - /opt/flowmanner/backend/tests/conftest.py
  - /opt/flowmanner/backend/app/tests/conftest.py
- Record assumptions before writing tests.

### Step 2 — Implement Test Suite (batch)
- Write all test files in one pass.
- Keep fixtures local to tests where possible.
- Prefer fast unit tests + targeted integration tests.

### Step 3 — Run Targeted Tests
Run:
- cd /opt/flowmanner/backend
- PYTHONPATH=/opt/flowmanner/backend pytest -q tests/test_substrate_event_log.py tests/test_substrate_replay.py tests/test_substrate_executor_v2.py tests/test_failure_analyzer_budgets.py tests/test_meta_loop_orchestrator_budgets.py tests/test_trigger_bridge.py tests/chaos/test_kill_worker_mid_mission.py

If host env imports fail due missing packages, switch to containerized run:
- cd /opt/flowmanner
- docker build -t workflows-backend:restored /opt/flowmanner/backend/
- docker compose up -d --no-deps --force-recreate backend
- docker compose exec backend pytest -q /app/tests/test_substrate_event_log.py /app/tests/test_substrate_replay.py /app/tests/test_substrate_executor_v2.py /app/tests/test_failure_analyzer_budgets.py /app/tests/test_meta_loop_orchestrator_budgets.py /app/tests/test_trigger_bridge.py /app/tests/chaos/test_kill_worker_mid_mission.py

### Step 4 — If Failures Occur
- Diagnose all failures first.
- Apply one batch of fixes in allowed files.
- Re-run the same test command once.
- Do not loop endlessly.

### Step 5 — Final Report
Write:
- /opt/flowmanner/backend/H2-SUBSTRATE-HARDENING-REPORT.md

Include:
1. Summary of files created/modified
2. Test matrix (each required behavior and PASS/FAIL)
3. Exact commands executed
4. Exact test output summary
5. Any unresolved failures + root cause
6. Follow-up recommendations (max 10 bullet points)

## Final Output Format (in chat)
Return exactly:
- "STATUS: SUCCESS" or "STATUS: PARTIAL" or "STATUS: BLOCKED"
- "FILES:" list
- "TESTS:" list with pass/fail counts
- "RISKS:" concise bullets
- "NEXT:" 3-5 concrete next actions

Be strict, evidence-based, and concise. Do not claim success without test evidence.
