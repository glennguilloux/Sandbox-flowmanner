# DEEPSEEK LONG JOB — H2 Final Mile: Container Parity + asyncpg Event-Loop Stability

TASK: H2-FINAL-MILE
PROJECT: FlowManner Backend
REPO ROOT: /opt/flowmanner/backend

## Why this task exists
Current state is strong (167 pass), but 2 PostgreSQL integration tests still fail in container runs with:
- RuntimeError: Future attached to a different loop

Root-cause indicators already verified in repo:
1) /opt/flowmanner/backend/pyproject.toml contains pytest asyncio config (asyncio_mode=auto)
2) /opt/flowmanner/backend/Dockerfile does NOT copy pyproject.toml into runtime image
3) /opt/flowmanner/backend/.dockerignore excludes tests/ (so runtime image also lacks tests unless mounted)

Goal: make integration test execution deterministic and environment-parity-safe.

## Hard constraints
- English only.
- Backend only.
- No VPS operations.
- Keep production runtime image lean.
- Do not break existing backend startup.
- If adding new .py file(s), chmod 644.

## Required deliverables

### 1) Add explicit test-capable container target (preferred)
Patch /opt/flowmanner/backend/Dockerfile to support BOTH:
- runtime/prod target (existing behavior preserved)
- test target (includes pytest config + tests)

Minimum requirements:
- Ensure pyproject.toml is present at container workdir for pytest discovery
- Ensure tests are available in test target at /app/tests
- Keep default runtime image not bloated by unnecessary test assets

If multi-target is too invasive, acceptable fallback:
- copy pyproject.toml into runtime image
- and run integration tests from host against live PostgreSQL service
But preferred is explicit test target.

### 2) Add/adjust compose path for deterministic test runs
Use one of:
- dedicated compose service (e.g., backend-test)
- or `docker run` command using `--target` test image

Requirement:
- command must be reproducible and documented
- no hidden host assumptions

### 3) Fix asyncpg loop-boundary instability robustly
Keep pytest asyncio_mode=auto, and make event loop behavior deterministic for DB integration tests.

Acceptable technical options (pick smallest safe fix):
- configure pytest-asyncio loop scope appropriately (if needed)
- ensure integration tests use one consistent loop for pooled asyncpg connections
- or isolate engine/pool usage in integration test fixture to avoid cross-loop pool reuse

Do NOT silence/xfail the two failing tests.

### 4) Verify the two failing tests now pass
Target tests:
- tests/test_substrate_event_log_integration_pg.py::TestAppendOnlyTriggerIntegration::test_update_rejected_by_trigger
- tests/test_substrate_event_log_integration_pg.py::TestAppendOnlyTriggerIntegration::test_trigger_exists_in_database

Also rerun full file:
- tests/test_substrate_event_log_integration_pg.py

### 5) Final report
Create:
- /opt/flowmanner/backend/H2-FINAL-MILE-CONTAINER-PARITY-REPORT.md

Include:
1. exact files changed
2. exact commands run
3. before/after results for the 2 failing tests
4. proof that pytest config is active in execution context
5. whether test execution path is now parity-safe (host vs container)
6. final recommendation: "H2 Exit Gate Ready: YES/NO"

## Allowed file scope
- /opt/flowmanner/backend/Dockerfile
- /opt/flowmanner/backend/pyproject.toml (only if needed)
- /opt/flowmanner/backend/.dockerignore (only if needed and justified)
- /opt/flowmanner/docker-compose.yml (only if adding dedicated test service)
- /opt/flowmanner/backend/tests/test_substrate_event_log_integration_pg.py (minimal, only if required)
- /opt/flowmanner/backend/H2-FINAL-MILE-CONTAINER-PARITY-REPORT.md

If any other file is required, stop and explain first.

## Execution order (strict)
Step 1 — Inspect current Dockerfile/compose/pytest config
Step 2 — Apply minimal patch wave for parity + loop stability
Step 3 — Rebuild image(s)
Step 4 — Run targeted failing tests
Step 5 — Run full integration test file
Step 6 — Write final evidence report

## Required final chat output format
Return exactly:
- STATUS: SUCCESS | PARTIAL | BLOCKED
- FILES:
- TESTS:
- EVIDENCE:
- RISKS:
- H2_EXIT_GATE_READY: YES | NO
- NEXT:

No vague claims. Every success statement must be backed by command output evidence.