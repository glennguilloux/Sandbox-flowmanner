# DEEPSEEK LONG JOB — H2 Exit Gate Integration + Reliability Horizon

TASK: H2-EXIT-GATE — Convert substrate unit success into production-grade integration confidence
HORIZON: H2 completion gate (durability + correctness + CI realism)
PROJECT: FlowManner Backend
REPO ROOT: /opt/flowmanner/backend

## Objective
The substrate hardening pass reported 144 tests passing. Now close the remaining confidence gaps so H2 can be considered truly production-ready, not only unit-tested.

You must complete all items below in one focused batch.

## Verified Inputs
- Existing hardening report: /opt/flowmanner/backend/H2-SUBSTRATE-HARDENING-REPORT.md
- Existing new tests exist under /opt/flowmanner/backend/tests/
- Known issues from report:
  1) app/services/nexus/orchestrator.py singleton indentation bug
  2) trigger_bridge tests mock trigger_service because croniter import path is fragile in host env
  3) append-only trigger enforcement still needs real DB integration verification
  4) some get_events tests risk becoming dead tests due to over-mocking

## Hard Constraints
- Respond in English only.
- Backend only. No frontend changes.
- No VPS deploy steps.
- No broad refactors.
- Prefer existing dependencies.
- If creating/editing new .py files, chmod 644 them.
- If one step fails, report root cause with evidence before moving on.

## Required Deliverables

### 1) Fix orchestrator singleton bug
Patch:
- /opt/flowmanner/backend/app/services/nexus/orchestrator.py

Requirement:
- `_nexus_orchestrator: NexusOrchestrator | None = None` must be at module scope (not inside a method body).
- `get_nexus_orchestrator()` must work without NameError and return a stable singleton.

Add tests (new file):
- /opt/flowmanner/backend/tests/test_nexus_orchestrator_singleton.py

Must verify:
- module imports cleanly
- get_nexus_orchestrator() returns singleton
- distributed_mode path does not break singleton initialization

### 2) Remove dead-test risk in EventLog filtering
Patch or add tests in:
- /opt/flowmanner/backend/tests/test_substrate_event_log.py
- optional helper fixtures in same file or local test module

Requirement:
- At least one test path must hit real SQLAlchemy query behavior (not only mocked returns) for:
  - from_sequence
  - to_sequence
  - event_type
- Keep tests deterministic.

### 3) Real PostgreSQL integration test for append-only trigger
Create integration test file:
- /opt/flowmanner/backend/tests/test_substrate_event_log_integration_pg.py

Requirement:
- Use real DB session from project stack (containerized test execution is acceptable and preferred).
- Insert substrate_events row(s), then attempt UPDATE and DELETE.
- Assert DB rejects both due to append-only trigger behavior.
- Include cleanup logic or transaction rollback strategy.

### 4) Trigger bridge integration realism
Patch tests:
- /opt/flowmanner/backend/tests/test_trigger_bridge.py

Requirement:
- Keep fast unit tests, but add one integration-flavored path that imports real app.services.trigger_service when possible.
- If environment lacks croniter in host mode, test must gracefully skip with explicit reason (not silent mock masking).
- Add clear test docstring explaining host-vs-container behavior.

### 5) Add true crash-boundary chaos test
Create:
- /opt/flowmanner/backend/tests/chaos/test_kill_worker_mid_mission_process.py

Requirement:
- Use multiprocessing/subprocess boundary to simulate worker death mid-run.
- Validate recovery logic from persisted substrate events.
- If SIGKILL semantics are platform-limited in CI, mark with explicit skip condition and provide fallback assertion path.

### 6) Pytest asyncio configuration
If no pytest config exists, create one minimal config file:
- /opt/flowmanner/backend/pyproject.toml (or pytest.ini; choose one canonical approach)

Requirement:
- Configure asyncio_mode=auto
- Do not break existing tool config.
- If pyproject.toml already exists, patch safely rather than overwrite unrelated sections.

### 7) Final evidence report
Create:
- /opt/flowmanner/backend/H2-EXIT-GATE-INTEGRATION-REPORT.md

Must include:
1. Exact files changed
2. Exact commands run
3. Test result table with pass/fail/skip counts
4. Proof snippets for:
   - orchestrator singleton fix
   - append-only trigger DB rejection
   - chaos crash-boundary behavior
5. Remaining risks (if any)
6. Recommendation: "H2 Exit Gate Ready: YES/NO" with reason

## Allowed File Change Scope
You may edit only:
- /opt/flowmanner/backend/app/services/nexus/orchestrator.py
- /opt/flowmanner/backend/tests/test_substrate_event_log.py
- /opt/flowmanner/backend/tests/test_trigger_bridge.py
- /opt/flowmanner/backend/tests/test_nexus_orchestrator_singleton.py (new)
- /opt/flowmanner/backend/tests/test_substrate_event_log_integration_pg.py (new)
- /opt/flowmanner/backend/tests/chaos/test_kill_worker_mid_mission_process.py (new)
- /opt/flowmanner/backend/pyproject.toml or /opt/flowmanner/backend/pytest.ini
- /opt/flowmanner/backend/H2-EXIT-GATE-INTEGRATION-REPORT.md (new)

Do not edit other files unless absolutely required to make tests valid; if required, stop and explain.

## Execution Steps (strict order)

Step 1 — Read current implementations
- Read orchestrator.py, substrate event_log/replay/executor, trigger_bridge, and relevant tests.

Step 2 — Apply code + test changes in one batch
- Implement all required modifications and new tests.
- chmod 644 new Python files.

Step 3 — Run fast targeted suite (host)
- cd /opt/flowmanner/backend
- PYTHONPATH=/opt/flowmanner/backend pytest -q \
  tests/test_nexus_orchestrator_singleton.py \
  tests/test_substrate_event_log.py \
  tests/test_trigger_bridge.py \
  tests/chaos/test_kill_worker_mid_mission_process.py

Step 4 — Run integration suite (containerized, real DB)
- cd /opt/flowmanner
- docker build -t workflows-backend:restored /opt/flowmanner/backend/
- docker compose up -d --no-deps --force-recreate backend
- docker compose exec backend pytest -q \
  /app/tests/test_substrate_event_log_integration_pg.py

Step 5 — If failures happen
- Diagnose all failures first.
- Apply one consolidated patch wave.
- Re-run exactly the failing commands once.

Step 6 — Write final report
- Produce H2-EXIT-GATE-INTEGRATION-REPORT.md with hard evidence.

## Required Final Chat Output Format
Return exactly:
- STATUS: SUCCESS | PARTIAL | BLOCKED
- FILES:
- TESTS:
- EVIDENCE:
- RISKS:
- H2_EXIT_GATE_READY: YES | NO
- NEXT:

No vague claims. Every success statement must be backed by command output evidence.
