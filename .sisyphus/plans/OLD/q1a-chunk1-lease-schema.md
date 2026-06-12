# Q1-A Chunk 1: Worker Lease Schema + Claim Middleware

## TL;DR

> **Quick Summary**: Implement the first substrate worker-lease foundation for FlowManner backend: an Alembic migration, async lease service functions, substrate exports, and focused async tests. This chunk deliberately stops at schema + claim/release/renew/query middleware and does not integrate heartbeat, Celery, UnifiedExecutor, or stale-lease cleanup.
>
> **Deliverables**:
> - Alembic migration for `substrate_worker_leases`
> - Async lease service in `backend/app/services/substrate/leases.py`
> - Public exports from `backend/app/services/substrate/__init__.py`
> - Async pytest coverage in `backend/tests/test_substrate_worker_leases.py`
> - Evidence from pytest and Alembic verification
>
> **Estimated Effort**: Short
> **Parallel Execution**: YES - 4 implementation/test tasks + final verification wave
> **Critical Path**: T1 schema/LeaseRecord → T2/T3 lease operations → T4 exports/tests → T5 verification → F1-F4

---

## Context

### Original Request

The user provided `/opt/flowmanner/.hermes/plans/q1a-chunk1-lease-schema.md`, an implementation prompt for FlowManner backend Q1-A chunk 1. The request is to plan a scoped backend change for worker task leasing: schema, claim middleware/service functions, exports, tests, and verification.

### Interview Summary

**Key Discussions**:
- User chose to discuss before plan generation.
- User selected tighter scope guardrails rather than a lean plan.
- User left the test fixture strategy to the executor after codebase inspection.

**Research Findings**:
- Current Alembic head is `align_playground_template_with_v1_api_001` in `/opt/flowmanner/backend/alembic/versions/20260611_align_playground_template_with_v1_api.py`.
- Likely next migration file: `/opt/flowmanner/backend/alembic/versions/20260612_worker_leases.py`.
- Recommended revision ID: `worker_leases_001`.
- Recent Alembic style uses `YYYYMMDD_snake_case.py`, explicit metadata, `op.create_table`, `op.create_index`, and reverse downgrade.
- Pytest config uses `asyncio_mode = "auto"`, `testpaths = ["tests"]`, and an `integration` marker.
- Existing substrate unit tests use mocked `AsyncSession` and `asyncio.run(...)`; real Postgres integration tests use `AsyncSessionLocal` with manual cleanup and no transaction rollback fixture.
- Substrate services accept `AsyncSession`; request/execution-path services should not open their own sessions or commit.
- `EventLog` uses `db.add()` + `await db.flush()`; `TriggerBridge` is the background-session exception.
- Substrate public exports live in `backend/app/services/substrate/__init__.py`; public lease APIs must be added there if intended for external import.
- No existing substrate tests were found despite AGENTS references.

### Metis Review

**Identified Gaps** (addressed):
- Claim contract ambiguity resolved by default: expired leases are reclaimable; duplicate same-worker claim is idempotent.
- Scope creep guardrails added: no heartbeat, stale reclaimer, Celery config, UnifiedExecutor integration, HITL, multi-tenant scoping, HTTP API surfaces, or generic locking abstractions.
- Migration QA added: Alembic upgrade/downgrade verification in addition to pytest.
- Edge cases added: concurrent duplicate claims, expired lease claim, non-owner release/renew, missing lease, expired renew, timezone/clock skew, partial unique indexes, DB rollback, and migration downgrade.

---

## Work Objectives

### Core Objective

Add a durable, async substrate worker-lease foundation that lets the backend represent and query active worker leases for execution runs without integrating the lease lifecycle into Celery, UnifiedExecutor, or heartbeat cleanup yet.

### Concrete Deliverables

- `/opt/flowmanner/backend/alembic/versions/20260612_worker_leases.py`
- `/opt/flowmanner/backend/app/services/substrate/leases.py` with `LeaseRecord` dataclass/Pydantic model
- `/opt/flowmanner/backend/app/services/substrate/__init__.py`
- `/opt/flowmanner/backend/tests/test_substrate_worker_leases.py`
- Evidence under `/opt/flowmanner/.sisyphus/evidence/`

### Definition of Done

- [ ] Alembic migration advances from `align_playground_template_with_v1_api_001` to `worker_leases_001`.
- [ ] `substrate_worker_leases` table exists with expected columns, constraints, and indexes.
- [ ] Lease functions are async, accept `AsyncSession`, and follow substrate session conventions.
- [ ] Lease functions are exported from `backend/app/services/substrate/__init__.py` if they are part of the public substrate surface.
- [ ] `backend/tests/test_substrate_worker_leases.py` passes with the project pytest configuration.
- [ ] No files outside the planned scope are modified.
- [ ] No deployment, push, or VPS edit occurs.

### Must Have

- Alembic migration for the worker lease table.
- Async lease service functions for claim, release, renew, and active-lease lookup.
- Owner-only release and renew behavior.
- Reclaimable expired leases.
- Idempotent duplicate claim by the same worker.
- Tests covering claim, release, renew, expiry, non-owner behavior, missing leases, and active-lease lookup.
- Agent-executed QA evidence for every task.

### Must NOT Have (Guardrails)

- No heartbeat loop.
- No stale-lease reclaimer worker.
- No chaos tests.
- No `UnifiedExecutor.execute()` integration.
- No Celery config changes.
- No HITL pause-release integration.
- No multi-tenant workspace scoping.
- No VPS edits.
- No backend deploy.
- No push to origin.
- No sync SQLAlchemy in new substrate code.
- No generic distributed-locking abstraction.
- No changes to files outside the planned scope.

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.
> Acceptance criteria requiring "user manually tests/confirms" are FORBIDDEN.

### Test Decision

- **Infrastructure exists**: YES - pytest, pytest-asyncio, and backend tests exist.
- **Automated tests**: YES - tests-after within each implementation task.
- **Framework**: `pytest` with `pytest-asyncio`, `asyncio_mode = "auto"`.
- **Fixture strategy**: Executor decides by inspecting `/opt/flowmanner/backend/tests/test_substrate_event_log.py` and `/opt/flowmanner/backend/tests/conftest.py`; default to mocked `AsyncSession` for unit-level behavior, but use a deterministic real-Postgres integration fixture if exact `ON CONFLICT ... WHERE expires_at < now()` SQL semantics require DB execution.
- **TDD**: Not required by source prompt; each task must still add or update tests before marking complete.

### QA Policy

Every task MUST include agent-executed QA scenarios. Evidence is saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend/API/Library**: Use Bash/pytest with exact test file paths and assertions.
- **Alembic**: Use `alembic -c alembic.ini upgrade/downgrade` against a safe test DB or documented dry-run path.
- **Imports**: Use `python -c "from app.services.substrate import ..."` from the backend root.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation - sequential dependency):
├── Task 1: Worker lease schema + model + migration [unspecified-high]

Wave 2 (Core lease behavior - parallel after T1):
├── Task 2: Claim + active-lease lookup service [unspecified-high]
└── Task 3: Release + renew service [unspecified-high]

Wave 3 (Surface + coverage - after T2/T3):
├── Task 4: Substrate exports + import smoke tests [quick]
└── Task 5: Focused lease test suite + edge-case coverage [unspecified-high]

Wave FINAL (After ALL tasks - 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit [oracle]
├── Task F2: Code quality review [unspecified-high]
├── Task F3: Real QA execution [unspecified-high]
└── Task F4: Scope fidelity check [deep]
```

### Dependency Matrix

- **1**: - → 2, 3
- **2**: 1 → 4, 5
- **3**: 1 → 4, 5
- **4**: 2, 3 → 5
- **5**: 2, 3, 4 → F1-F4
- **F1-F4**: 5 → user approval required; do not mark final verification complete without explicit user okay

### Agent Dispatch Summary

- **Wave 1**: T1 → `unspecified-high`
- **Wave 2**: T2 → `unspecified-high`, T3 → `unspecified-high`
- **Wave 3**: T4 → `quick`, T5 → `unspecified-high`
- **FINAL**: F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [ ] 1. Worker lease schema + LeaseRecord + Alembic migration

  **What to do**:
  - Confirm current Alembic head is `align_playground_template_with_v1_api_001` before writing.
  - Create `/opt/flowmanner/backend/alembic/versions/20260612_worker_leases.py`.
  - Use `revision = "worker_leases_001"` and `down_revision = "align_playground_template_with_v1_api_001"`.
  - Add the exact table schema from the source prompt:
    - `id BIGSERIAL PRIMARY KEY`
    - `worker_id TEXT NOT NULL`
    - `run_id TEXT NOT NULL UNIQUE`
    - `acquired_at TIMESTAMPTZ NOT NULL DEFAULT now()`
    - `expires_at TIMESTAMPTZ NOT NULL`
    - `renewed_count INT NOT NULL DEFAULT 0`
    - `generation INT NOT NULL DEFAULT 1`
    - index `ix_substrate_worker_leases_expires` on `expires_at`
  - Add reverse downgrade that drops the index and table.
  - Add `LeaseRecord` dataclass or Pydantic model in `leases.py` matching the table fields.
  - Do not add heartbeat, cleanup, executor wiring, Celery config, or API routes.

  **Must NOT do**:
  - Do not invent a different schema.
  - Do not add an ORM model unless required by the selected implementation approach.
  - Do not modify files outside the migration, `leases.py`, `__init__.py`, and tests.
  - Do not run backend deploy.

  **Recommended Agent Profile**:
  > Select category + skills based on task domain. Justify each choice.
  - **Category**: `unspecified-high`
    - Reason: Backend database schema work with migration and test implications.
  - **Skills**: [`flowmanner`]
    - `flowmanner`: Required for deployment/source-location constraints and backend conventions.
  - **Skills Evaluated but Omitted**:
    - `write-tests`: Covered by implementation task; no separate test-only task.

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 (sequential foundation)
  - **Blocks**: Tasks 2, 3, 4, 5
  - **Blocked By**: None

  **References** (CRITICAL - Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `/opt/flowmanner/backend/alembic/versions/20260611_align_playground_template_with_v1_api.py` - Current head and metadata style to copy.
  - `/opt/flowmanner/backend/alembic/versions/20260615_mission_sandboxes.py` - Recent `op.create_table` and `op.create_index` style.
  - `/opt/flowmanner/backend/alembic/versions/h2_substrate_init.py` - Substrate table/index/server-default style.
  - `/opt/flowmanner/backend/app/services/substrate/AGENTS.md` - Substrate ownership map and hard rules.

  **API/Type References** (contracts to implement against):
  - Source prompt schema in `/opt/flowmanner/.hermes/plans/q1a-chunk1-lease-schema.md:65-76` - Exact table DDL to preserve.
  - `/opt/flowmanner/backend/app/models/substrate_models.py` - Existing substrate model naming, if an ORM model is added.

  **Test References** (testing patterns to follow):
  - `/opt/flowmanner/backend/tests/test_substrate_event_log.py` - Existing substrate test style and mocked `AsyncSession` pattern.
  - `/opt/flowmanner/backend/tests/conftest.py` - Main backend fixtures.
  - `/opt/flowmanner/backend/pyproject.toml` - Pytest config and `asyncio_mode = "auto"`.

  **External References** (libraries and frameworks):
  - Alembic operations docs: `https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.create_table` - `op.create_table` syntax.
  - Alembic index docs: `https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.create_index` - `op.create_index` syntax.

  **WHY Each Reference Matters** (explain the relevance):
  - Current head file prevents branch conflicts and gives the exact `down_revision`.
  - Recent migration files show the project's preferred metadata and DDL style.
  - Substrate AGENTS enforces scope and prevents accidental executor/Celery changes.
  - Source prompt schema is authoritative and must not be altered.

  **Acceptance Criteria**:

  > **AGENT-EXECUTABLE VERIFICATION ONLY** - No human action permitted.
  > Every criterion MUST be verifiable by running a command or using a tool.

  - [ ] Migration file exists at `/opt/flowmanner/backend/alembic/versions/20260612_worker_leases.py`.
  - [ ] Migration metadata reads exactly: `revision = "worker_leases_001"` and `down_revision = "align_playground_template_with_v1_api_001"`.
  - [ ] Migration creates `substrate_worker_leases` with the exact columns and `ix_substrate_worker_leases_expires` index from the source schema.
  - [ ] Downgrade drops `ix_substrate_worker_leases_expires` then `substrate_worker_leases`.
  - [ ] `LeaseRecord` dataclass or Pydantic model exists in `/opt/flowmanner/backend/app/services/substrate/leases.py` with fields for `id`, `worker_id`, `run_id`, `acquired_at`, `expires_at`, `renewed_count`, and `generation`.

  **QA Scenarios (MANDATORY - task is INCOMPLETE without these)**:

  ```
  Scenario: Migration head resolves to worker lease migration
    Tool: Bash
    Preconditions: Working directory `/opt/flowmanner/backend`; safe test DB or Alembic offline mode available.
    Steps:
      1. Run `.venv/bin/alembic -c alembic.ini heads`.
      2. Assert output contains `worker_leases_001`.
      3. Run `.venv/bin/python - <<'PY' ... assert down_revision == "align_playground_template_with_v1_api_001" ... PY`.
    Expected Result: Alembic graph head is `worker_leases_001`; down revision is current head.
    Failure Indicators: Multiple heads, wrong parent, missing migration file, or import error.
    Evidence: .sisyphus/evidence/task-1-alembic-head.txt

  Scenario: Migration upgrade/downgrade path succeeds
    Tool: Bash
    Preconditions: Safe test DB available; no production deploy command run.
    Steps:
      1. Run `.venv/bin/alembic -c alembic.ini upgrade head`.
      2. Query `information_schema.tables` and assert `substrate_worker_leases` exists.
      3. Query `pg_indexes` and assert `ix_substrate_worker_leases_expires` exists.
      4. Run `.venv/bin/alembic -c alembic.ini downgrade -1`.
      5. Query `information_schema.tables` and assert `substrate_worker_leases` is absent.
      6. Run `.venv/bin/alembic -c alembic.ini upgrade head` to restore test state.
    Expected Result: Upgrade creates table/index; downgrade removes table/index; re-upgrade succeeds.
    Failure Indicators: SQL error, missing table/index, downgrade leaves table, or deploy command appears in shell history/output.
    Evidence: .sisyphus/evidence/task-1-alembic-up-down.txt
  ```

  **Evidence to Capture**:
  - [ ] Alembic head output.
  - [ ] Upgrade/downgrade command output.
  - [ ] SQL verification output for table/index presence.

  **Commit**: YES
  - Message: `feat(substrate): add worker lease schema`
  - Files: `backend/alembic/versions/20260612_worker_leases.py`, `backend/app/services/substrate/leases.py`
  - Pre-commit: `cd /opt/flowmanner/backend && .venv/bin/alembic -c alembic.ini heads`

- [ ] 2. Claim and active-lease query service

  **What to do**:
  - Implement async `try_claim_lease(db: AsyncSession, worker_id: str, run_id: str, ttl_seconds: int = 300) -> bool`.
  - Implement async `get_active_lease(db: AsyncSession, run_id: str) -> LeaseRecord | None`.
  - Use exact SQL semantics from the source prompt:
    - insert with `now() + interval '<ttl> seconds'`
    - `ON CONFLICT (run_id) DO UPDATE`
    - update only when existing `expires_at < now()`
    - bump `generation`
    - treat empty `RETURNING generation` as claim failure
  - Return `True` only when a row is returned.
  - Return `False` when the lease is held by another worker or not expired.
  - Treat duplicate same-worker claim as idempotent success if the lease is still active.
  - `get_active_lease()` returns `None` for missing or expired leases.
  - Add tests for happy path, already-held lease, expiry reclaim, duplicate same-worker claim, and active lookup.

  **Must NOT do**:
  - Do not commit inside the service function.
  - Do not integrate with `UnifiedExecutor.execute()`.
  - Do not add Celery signal handling.
  - Do not add stale-lease cleanup.

  **Recommended Agent Profile**:
  > Select category + skills based on task domain. Justify each choice.
  - **Category**: `unspecified-high`
    - Reason: Async database service logic with concurrency-sensitive SQL semantics.
  - **Skills**: [`flowmanner`]
    - `flowmanner`: Required for backend conventions and no-deploy/no-VPS constraints.
  - **Skills Evaluated but Omitted**:
    - `performance-engineer`: Concurrency is important, but this is a small SQL primitive; no separate performance pass needed.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 with Task 3
  - **Blocks**: Tasks 4, 5
  - **Blocked By**: Task 1

  **References** (CRITICAL - Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `/opt/flowmanner/backend/app/services/substrate/event_log.py` - Async service style and `AsyncSession` usage.
  - `/opt/flowmanner/backend/app/services/substrate/replay_engine.py` - Async read-only service style.
  - `/opt/flowmanner/backend/app/api/_mission_cqrs/commands.py` - Existing TOCTOU-safe DB transition pattern.
  - `/opt/flowmanner/backend/app/database.py` - Async session factory and no-implicit-commit behavior.

  **API/Type References** (contracts to implement against):
  - Source prompt SQL semantics `/opt/flowmanner/.hermes/plans/q1a-chunk1-lease-schema.md:78-89` - Authoritative claim/update behavior.
  - Source prompt function signatures `/opt/flowmanner/.hermes/plans/q1a-chunk1-lease-schema.md:41-45` - Required async function names and return behavior.
  - `/opt/flowmanner/backend/app/models/substrate_models.py` - Existing substrate naming if any shared constants are reused.

  **Test References** (testing patterns to follow):
  - `/opt/flowmanner/backend/tests/test_substrate_event_log.py` - Existing substrate test style.
  - `/opt/flowmanner/backend/tests/test_substrate_event_log_integration_pg.py` - Real Postgres integration pattern if exact SQL requires DB execution.
  - `/opt/flowmanner/backend/pyproject.toml` - Pytest async configuration.

  **External References** (libraries and frameworks):
  - SQLAlchemy PostgreSQL upsert docs: `https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-do-update` - `on_conflict_do_update(where=...)`.
  - SQLAlchemy async session docs: `https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html` - `AsyncSession.execute()` patterns.

  **WHY Each Reference Matters** (explain the relevance):
  - `event_log.py` and `replay_engine.py` show the substrate service conventions.
  - Mission CQRS shows how existing code handles state transition races.
  - Source prompt SQL is the acceptance contract for claim behavior.
  - Real Postgres integration tests are the closest pattern for verifying exact `ON CONFLICT ... WHERE expires_at < now()` semantics.

  **Acceptance Criteria**:

  > **AGENT-EXECUTABLE VERIFICATION ONLY** - No human action permitted.
  > Every criterion MUST be verifiable by running a command or using a tool.

  - [ ] `try_claim_lease()` is async and returns `bool`.
  - [ ] `get_active_lease()` is async and returns `LeaseRecord | None`.
  - [ ] Claiming an unclaimed run returns `True` and creates exactly one active lease.
  - [ ] Claiming the same run by another worker while active returns `False` and leaves the existing lease unchanged.
  - [ ] Claiming after expiry by another worker returns `True` and bumps `generation`.
  - [ ] Duplicate claim by the same active worker returns `True` and does not create a duplicate row.
  - [ ] `get_active_lease()` returns the active lease for an active run.
  - [ ] `get_active_lease()` returns `None` after expiry or release.

  **QA Scenarios (MANDATORY - task is INCOMPLETE without these)**:

  ```
  Scenario: Claim happy path and active lookup
    Tool: Bash/pytest
    Preconditions: Test DB has migrated `substrate_worker_leases`; working directory `/opt/flowmanner/backend`.
    Steps:
      1. Run `.venv/bin/python -m pytest tests/test_substrate_worker_leases.py::test_try_claim_happy_path -q`.
      2. Assert test passes and asserts `try_claim_lease("worker-a", "run-1", 300) is True`.
      3. Assert `get_active_lease("run-1").worker_id == "worker-a"`.
    Expected Result: Claim succeeds and active lookup returns worker A.
    Failure Indicators: False return, missing row, wrong worker_id, or SQL error.
    Evidence: .sisyphus/evidence/task-2-claim-happy.txt

  Scenario: Active lease blocks other worker
    Tool: Bash/pytest
    Preconditions: Test DB has migrated table; no active lease for `run-2`.
    Steps:
      1. Run `.venv/bin/python -m pytest tests/test_substrate_worker_leases.py::test_try_claim_when_already_held -q`.
      2. Assert worker A claim returns True.
      3. Assert worker B claim returns False.
      4. Assert `get_active_lease("run-2").worker_id == "worker-a"`.
    Expected Result: Worker B cannot claim active worker A lease.
    Failure Indicators: Worker B succeeds, generation changes, or active lookup returns worker B.
    Evidence: .sisyphus/evidence/task-2-claim-blocked.txt

  Scenario: Expired lease can be reclaimed
    Tool: Bash/pytest
    Preconditions: Test DB has migrated table; deterministic TTL/wait helper available.
    Steps:
      1. Run `.venv/bin/python -m pytest tests/test_substrate_worker_leases.py::test_try_claim_after_expiry -q`.
      2. Assert worker A claim with TTL 1 returns True.
      3. Wait until lease expires using deterministic sleep or DB-time helper.
      4. Assert worker B claim returns True and `generation == 2`.
    Expected Result: Expired lease is reclaimable and generation increments.
    Failure Indicators: Worker B claim returns False or generation remains 1.
    Evidence: .sisyphus/evidence/task-2-claim-expired.txt
  ```

  **Evidence to Capture**:
  - [ ] Pytest output for claim happy path.
  - [ ] Pytest output for blocked claim.
  - [ ] Pytest output for expired reclaim.

  **Commit**: YES
  - Message: `feat(substrate): add lease claim and query service`
  - Files: `backend/app/services/substrate/leases.py`, `backend/tests/test_substrate_worker_leases.py`
  - Pre-commit: `cd /opt/flowmanner/backend && .venv/bin/python -m pytest tests/test_substrate_worker_leases.py::test_try_claim_happy_path tests/test_substrate_worker_leases.py::test_try_claim_when_already_held tests/test_substrate_worker_leases.py::test_try_claim_after_expiry -q`

- [ ] 3. Release and renew service

  **What to do**:
  - Implement async `release_lease(db: AsyncSession, worker_id: str, run_id: str) -> None`.
  - Implement async `renew_lease(db: AsyncSession, worker_id: str, run_id: str, ttl_seconds: int = 300) -> bool`.
  - `release_lease()` is idempotent and owner-only:
    - if the active lease is held by `worker_id`, release it
    - if held by another worker or missing, do nothing
    - no exception for non-owner/no-op cases
  - `renew_lease()` extends `expires_at` only when the active lease is held by `worker_id`.
  - `renew_lease()` returns `False` if the lease is missing, expired, or held by another worker.
  - Add tests for happy-path release, idempotent release, owner-only release, happy-path renew, and renew after reclaim.

  **Must NOT do**:
  - Do not commit inside the service function.
  - Do not delete rows.
  - Do not add stale-lease cleanup.
  - Do not change Celery or executor behavior.

  **Recommended Agent Profile**:
  > Select category + skills based on task domain. Justify each choice.
  - **Category**: `unspecified-high`
    - Reason: Async DB mutation logic with owner-only and idempotency edge cases.
  - **Skills**: [`flowmanner`]
    - `flowmanner`: Required for backend conventions and hard deployment/source constraints.
  - **Skills Evaluated but Omitted**:
    - `security-engineer`: Owner-only checks are simple DB predicates; no separate security review needed for this small primitive.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 with Task 2
  - **Blocks**: Tasks 4, 5
  - **Blocked By**: Task 1

  **References** (CRITICAL - Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `/opt/flowmanner/backend/app/services/substrate/event_log.py` - Async substrate service style and flush convention.
  - `/opt/flowmanner/backend/app/services/substrate/replay_engine.py` - Async read pattern for active lease lookup.
  - `/opt/flowmanner/backend/app/api/_mission_cqrs/commands.py` - Owner/state transition pattern with row-level safety.
  - `/opt/flowmanner/backend/app/models/playground_models.py` - Expiry/claimed-state pattern, not sync middleware behavior.

  **API/Type References** (contracts to implement against):
  - Source prompt function signatures `/opt/flowmanner/.hermes/plans/q1a-chunk1-lease-schema.md:42-44` - Required release/renew behavior.
  - Source prompt exact schema `/opt/flowmanner/.hermes/plans/q1a-chunk1-lease-schema.md:65-76` - Fields used by release/renew.
  - `/opt/flowmanner/backend/app/database.py` - `AsyncSession` behavior and no implicit commit.

  **Test References** (testing patterns to follow):
  - `/opt/flowmanner/backend/tests/test_substrate_event_log.py` - Existing substrate test style.
  - `/opt/flowmanner/backend/tests/test_substrate_event_log_integration_pg.py` - Real Postgres integration pattern if exact SQL behavior needs DB execution.
  - `/opt/flowmanner/backend/tests/conftest.py` - Mock fixtures if unit tests are used for non-SQL paths.

  **External References** (libraries and frameworks):
  - SQLAlchemy async session docs: `https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html` - `AsyncSession.execute()` and `flush()` patterns.
  - PostgreSQL `UPDATE ... WHERE` semantics: `https://www.postgresql.org/docs/current/sql-update.html` - owner-only predicate behavior.

  **WHY Each Reference Matters** (explain the relevance):
  - Existing substrate services show how to accept and use `AsyncSession`.
  - Mission CQRS and expiry models show how to protect owner/state transitions.
  - Source prompt defines the required release/renew API and return behavior.

  **Acceptance Criteria**:

  > **AGENT-EXECUTABLE VERIFICATION ONLY** - No human action permitted.
  > Every criterion MUST be verifiable by running a command or using a tool.

  - [ ] `release_lease()` is async and returns `None`.
  - [ ] Owner release succeeds and active lease is no longer returned by `get_active_lease()`.
  - [ ] Releasing twice is idempotent and does not raise.
  - [ ] Non-owner release does not mutate the lease.
  - [ ] `renew_lease()` is async and returns `bool`.
  - [ ] Owner renew returns `True` and moves `expires_at` forward.
  - [ ] Non-owner renew returns `False` and leaves `expires_at` unchanged.
  - [ ] Renew after reclaim returns `False` for the old worker.
  - [ ] Missing-lease renew returns `False`.

  **QA Scenarios (MANDATORY - task is INCOMPLETE without these)**:

  ```
  Scenario: Owner release is idempotent
    Tool: Bash/pytest
    Preconditions: Test DB has migrated table; run `run-release-1` is unclaimed.
    Steps:
      1. Run `.venv/bin/python -m pytest tests/test_substrate_worker_leases.py::test_release_idempotent -q`.
      2. Assert worker A claims `run-release-1`.
      3. Assert `release_lease("worker-a", "run-release-1")` returns None.
      4. Assert calling `release_lease("worker-a", "run-release-1")` again returns None.
      5. Assert `get_active_lease("run-release-1") is None`.
    Expected Result: Release succeeds once and remains a no-op on second call.
    Failure Indicators: Exception, duplicate row, or active lease still returned.
    Evidence: .sisyphus/evidence/task-3-release-idempotent.txt

  Scenario: Non-owner release is no-op
    Tool: Bash/pytest
    Preconditions: Test DB has migrated table; run `run-release-2` is unclaimed.
    Steps:
      1. Run `.venv/bin/python -m pytest tests/test_substrate_worker_leases.py::test_release_only_owner -q`.
      2. Assert worker A claims `run-release-2`.
      3. Assert `release_lease("worker-b", "run-release-2")` returns None.
      4. Assert `get_active_lease("run-release-2").worker_id == "worker-a"`.
    Expected Result: Worker B cannot release worker A's lease.
    Failure Indicators: Active lease becomes None or worker_id changes.
    Evidence: .sisyphus/evidence/task-3-release-owner.txt

  Scenario: Owner renew succeeds; stale worker renew fails after reclaim
    Tool: Bash/pytest
    Preconditions: Test DB has migrated table; deterministic TTL/wait helper available.
    Steps:
      1. Run `.venv/bin/python -m pytest tests/test_substrate_worker_leases.py::test_renew_happy_path -q`.
      2. Assert worker A claim returns True.
      3. Assert `renew_lease("worker-a", "run-renew-1", 300)` returns True.
      4. Run `.venv/bin/python -m pytest tests/test_substrate_worker_leases.py::test_renew_after_reclaim -q`.
      5. Assert worker A claim with TTL 1, wait expiry, worker B claim succeeds.
      6. Assert `renew_lease("worker-a", "run-reclaim-1", 300)` returns False.
    Expected Result: Owner renew extends lease; old worker cannot renew after reclaim.
    Failure Indicators: Renew returns True for old worker or generation is not bumped after reclaim.
    Evidence: .sisyphus/evidence/task-3-renew.txt
  ```

  **Evidence to Capture**:
  - [ ] Pytest output for idempotent release.
  - [ ] Pytest output for owner-only release.
  - [ ] Pytest output for renew happy path and renew after reclaim.

  **Commit**: YES
  - Message: `feat(substrate): add lease release and renew service`
  - Files: `backend/app/services/substrate/leases.py`, `backend/tests/test_substrate_worker_leases.py`
  - Pre-commit: `cd /opt/flowmanner/backend && .venv/bin/python -m pytest tests/test_substrate_worker_leases.py::test_release_idempotent tests/test_substrate_worker_leases.py::test_release_only_owner tests/test_substrate_worker_leases.py::test_renew_happy_path tests/test_substrate_worker_leases.py::test_renew_after_reclaim -q`

- [ ] 4. Substrate exports and import smoke tests

  **What to do**:
  - Update `/opt/flowmanner/backend/app/services/substrate/__init__.py` to export the lease API if it is part of the public substrate surface.
  - Export at minimum:
    - `LeaseRecord`
    - `try_claim_lease`
    - `release_lease`
    - `renew_lease`
    - `get_active_lease`
  - Add import smoke test ensuring `from app.services.substrate import try_claim_lease, release_lease, renew_lease, get_active_lease` works from backend root.
  - Keep unrelated existing exports intact.
  - Do not export internal helper functions.

  **Must NOT do**:
  - Do not remove existing substrate exports.
  - Do not add unrelated public API functions.
  - Do not import heavy modules at substrate package import time.
  - Do not change executor, Celery, or API routes.

  **Recommended Agent Profile**:
  > Select category + skills based on task domain. Justify each choice.
  - **Category**: `quick`
    - Reason: Small export/import surface change with narrow test scope.
  - **Skills**: [`flowmanner`]
    - `flowmanner`: Required for backend path conventions and no-deploy constraints.
  - **Skills Evaluated but Omitted**:
    - `frontend-design`: No frontend work.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 with Task 5
  - **Blocks**: Task 5 final import verification
  - **Blocked By**: Tasks 2 and 3

  **References** (CRITICAL - Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `/opt/flowmanner/backend/app/services/substrate/__init__.py` - Current public export list and `__all__` pattern.
  - `/opt/flowmanner/backend/app/services/substrate/AGENTS.md` - Public surface rules and smoke-test expectations.
  - `/opt/flowmanner/backend/app/services/substrate/event_log.py` - Avoid importing heavy runtime dependencies at package import.

  **API/Type References** (contracts to implement against):
  - Source prompt `/opt/flowmanner/.hermes/plans/q1a-chunk1-lease-schema.md:94-102` - Required public lease functions and `LeaseRecord`.
  - `/opt/flowmanner/backend/app/services/substrate/__init__.py` - Existing export shape.

  **Test References** (testing patterns to follow):
  - `/opt/flowmanner/backend/tests/test_substrate_event_log.py` - Existing substrate test style.
  - `/opt/flowmanner/backend/pyproject.toml` - Pytest config.

  **External References** (libraries and frameworks):
  - Python import docs: `https://docs.python.org/3/reference/import.html` - Package import behavior.

  **WHY Each Reference Matters** (explain the relevance):
  - `__init__.py` is the only correct place for public substrate exports.
  - AGENTS documents public surface expectations and smoke-test behavior.
  - Source prompt explicitly requires imports like `from app.services.substrate import try_claim_lease`.

  **Acceptance Criteria**:

  > **AGENT-EXECUTABLE VERIFICATION ONLY** - No human action permitted.
  > Every criterion MUST be verifiable by running a command or using a tool.

  - [ ] `LeaseRecord` is exported from `app.services.substrate`.
  - [ ] `try_claim_lease`, `release_lease`, `renew_lease`, and `get_active_lease` are exported from `app.services.substrate`.
  - [ ] Existing exports remain importable.
  - [ ] Import smoke test passes from `/opt/flowmanner/backend`.
  - [ ] No unrelated files are modified.

  **QA Scenarios (MANDATORY - task is INCOMPLETE without these)**:

  ```
  Scenario: Public lease API imports from substrate package
    Tool: Bash
    Preconditions: Working directory `/opt/flowmanner/backend`; dependencies available.
    Steps:
      1. Run `.venv/bin/python -c "from app.services.substrate import LeaseRecord, try_claim_lease, release_lease, renew_lease, get_active_lease; print('ok')"`.
      2. Assert stdout is exactly `ok`.
      3. Run `.venv/bin/python -m pytest tests/test_substrate_worker_leases.py::test_substrate_lease_exports -q`.
    Expected Result: Lease API imports successfully from the public substrate package.
    Failure Indicators: ImportError, missing export, or unrelated import side effects.
    Evidence: .sisyphus/evidence/task-4-export-import.txt
  ```

  **Evidence to Capture**:
  - [ ] Import command stdout.
  - [ ] Export smoke test output.

  **Commit**: YES
  - Message: `chore(substrate): export worker lease API`
  - Files: `backend/app/services/substrate/__init__.py`, `backend/tests/test_substrate_worker_leases.py`
  - Pre-commit: `cd /opt/flowmanner/backend && .venv/bin/python -c "from app.services.substrate import LeaseRecord, try_claim_lease, release_lease, renew_lease, get_active_lease; print('ok')"`

- [ ] 5. Focused lease test suite and edge-case coverage

  **What to do**:
  - Create or complete `/opt/flowmanner/backend/tests/test_substrate_worker_leases.py`.
  - Coordinate with Tasks 2 and 3 so claim/release/renew tests are not overwritten or duplicated unintentionally.
  - Use async pytest style consistent with project config (`asyncio_mode = "auto"`).
  - Cover the source-prompt minimum cases:
    - `test_try_claim_happy_path`
    - `test_try_claim_when_already_held`
    - `test_try_claim_after_expiry`
    - `test_release_idempotent`
    - `test_release_only_owner`
    - `test_renew_happy_path`
    - `test_renew_after_reclaim`
    - `test_get_active_lease_after_release`
  - Add focused edge-case coverage for:
    - duplicate same-worker claim idempotency
    - missing-lease renew returns False
    - expired lease is not returned by `get_active_lease()`
    - generation increments after reclaim
  - Aim for about 10 tests total.
  - Use the existing test fixture strategy after inspecting `test_substrate_event_log.py` and `tests/conftest.py`; if exact SQL requires Postgres, follow the existing `*_integration_pg.py` cleanup pattern or a deterministic rollback fixture if one is added safely.

  **Must NOT do**:
  - Do not add chaos tests.
  - Do not add heartbeat or stale-reclaimer tests.
  - Do not test Celery or UnifiedExecutor integration.
  - Do not modify unrelated tests.

  **Recommended Agent Profile**:
  > Select category + skills based on task domain. Justify each choice.
  - **Category**: `unspecified-high`
    - Reason: Test suite must cover concurrency-sensitive DB behavior and exact SQL semantics.
  - **Skills**: [`flowmanner`, `write-tests`]
    - `flowmanner`: Required for backend test path and no-deploy constraints.
    - `write-tests`: Relevant for systematic pytest coverage and edge-case design.
  - **Skills Evaluated but Omitted**:
    - `playwright`: No browser/UI work.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 with Task 4
  - **Blocks**: Final verification wave
  - **Blocked By**: Tasks 2, 3, 4

  **References** (CRITICAL - Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `/opt/flowmanner/backend/tests/test_substrate_event_log.py` - Existing substrate test style.
  - `/opt/flowmanner/backend/tests/test_substrate_event_log_integration_pg.py` - Real Postgres integration cleanup pattern.
  - `/opt/flowmanner/backend/tests/test_entity_versioning_integration_pg.py` - Manual rollback and cleanup pattern.
  - `/opt/flowmanner/backend/tests/conftest.py` - Mock DB and TestClient fixtures.
  - `/opt/flowmanner/backend/app/tests/conftest.py` - Legacy mock DB session fixture pattern.

  **API/Type References** (contracts to implement against):
  - Source prompt required tests `/opt/flowmanner/.hermes/plans/q1a-chunk1-lease-schema.md:123-132` - Minimum test cases.
  - `/opt/flowmanner/backend/pyproject.toml` - Pytest config and `asyncio_mode = "auto"`.
  - `/opt/flowmanner/backend/app/database.py` - Async session behavior.

  **Test References** (testing patterns to follow):
  - `/opt/flowmanner/backend/tests/test_substrate_event_log.py` - Existing substrate unit style.
  - `/opt/flowmanner/backend/tests/test_substrate_event_log_integration_pg.py` - Real Postgres integration style.
  - `/opt/flowmanner/backend/tests/test_entity_versioning_integration_pg.py` - Manual cleanup after expected failures.

  **External References** (libraries and frameworks):
  - pytest-asyncio docs: `https://pytest-asyncio.readthedocs.io/en/latest/` - async test patterns.
  - SQLAlchemy async session docs: `https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html` - async DB test helpers.

  **WHY Each Reference Matters** (explain the relevance):
  - Existing substrate tests define the expected local style.
  - Integration tests show how to handle real Postgres and manual cleanup.
  - Source prompt lists the required acceptance tests.

  **Acceptance Criteria**:

  > **AGENT-EXECUTABLE VERIFICATION ONLY** - No human action permitted.
  > Every criterion MUST be verifiable by running a command or using a tool.

  - [ ] Test file exists at `/opt/flowmanner/backend/tests/test_substrate_worker_leases.py`.
  - [ ] Test file contains the 8 required source-prompt tests.
  - [ ] Test file contains about 10 tests total.
  - [ ] Tests are async or use `asyncio.run(...)` consistently with existing substrate tests.
  - [ ] Tests assert exact fields: `worker_id`, `run_id`, `expires_at`, `generation`, and `renewed_count`.
  - [ ] Full lease test command passes: `.venv/bin/python -m pytest tests/test_substrate_worker_leases.py -v --tb=short`.
  - [ ] No heartbeat, Celery, UnifiedExecutor, or chaos test is added.

  **QA Scenarios (MANDATORY - task is INCOMPLETE without these)**:

  ```
  Scenario: Full lease test suite passes
    Tool: Bash/pytest
    Preconditions: Working directory `/opt/flowmanner/backend`; migration applied to safe test DB or deterministic fixtures available.
    Steps:
      1. Run `.venv/bin/python -m pytest tests/test_substrate_worker_leases.py -v --tb=short`.
      2. Assert exit code is 0.
      3. Assert output includes all required test names and no failures/errors.
    Expected Result: Full lease suite passes with all required cases green.
    Failure Indicators: Any failure, error, skipped required test, or missing required test name.
    Evidence: .sisyphus/evidence/task-5-full-lease-suite.txt

  Scenario: Edge-case coverage is present
    Tool: Bash/pytest
    Preconditions: Working directory `/opt/flowmanner/backend`.
    Steps:
      1. Run `.venv/bin/python -m pytest tests/test_substrate_worker_leases.py::test_duplicate_same_worker_claim_is_idempotent tests/test_substrate_worker_leases.py::test_renew_missing_lease_returns_false tests/test_substrate_worker_leases.py::test_get_active_lease_excludes_expired -q`.
      2. Assert exit code is 0.
      3. Assert output contains 3 passed.
    Expected Result: Focused edge-case tests pass.
    Failure Indicators: Missing test names, failures, or incorrect assertions.
    Evidence: .sisyphus/evidence/task-5-edge-cases.txt
  ```

  **Evidence to Capture**:
  - [ ] Full lease test suite output.
  - [ ] Edge-case test output.
  - [ ] Test file path and line count if requested by reviewer.

  **Commit**: YES
  - Message: `test(substrate): cover worker lease behavior`
  - Files: `backend/tests/test_substrate_worker_leases.py`
  - Pre-commit: `cd /opt/flowmanner/backend && .venv/bin/python -m pytest tests/test_substrate_worker_leases.py -v --tb=short`

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
>
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, pytest, Alembic command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `cd /opt/flowmanner/backend && .venv/bin/python -m pytest tests/test_substrate_worker_leases.py -v --tb=short` plus relevant Alembic verification. Review changed files for sync DB access in substrate, accidental Celery/executor changes, unused imports, broad exceptions, or AI slop.
  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real QA Execution** — `unspecified-high`
  Start from a clean test state. Execute every QA scenario from every task, capture evidence to `.sisyphus/evidence/final-qa/`, and test edge cases: duplicate claim, expired claim, non-owner release, non-owner renew, missing lease, export import, and Alembic downgrade/upgrade.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built and nothing beyond spec was built. Check "Must NOT do" compliance. Flag any Celery, UnifiedExecutor, heartbeat, stale-reclaimer, HITL, multi-tenant, deployment, or VPS-related changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **1**: `feat(substrate): add worker lease schema` - migration and LeaseRecord
- **2**: `feat(substrate): add lease claim and query service` - leases.py
- **3**: `feat(substrate): add lease release and renew service` - leases.py
- **4**: `chore(substrate): export worker lease API` - substrate/__init__.py
- **5**: `test(substrate): cover worker lease behavior` - tests
- **No push**: do not push to origin unless explicitly requested after review.

---

## Success Criteria

### Verification Commands

```bash
cd /opt/flowmanner/backend
.venv/bin/python -m pytest tests/test_substrate_worker_leases.py -v --tb=short
.venv/bin/python -c "from app.services.substrate import try_claim_lease, release_lease, renew_lease, get_active_lease"
```

Alembic verification, if a safe test DB is available:

```bash
cd /opt/flowmanner/backend
.venv/bin/alembic -c alembic.ini upgrade head
.venv/bin/alembic -c alembic.ini downgrade -1
.venv/bin/alembic -c alembic.ini upgrade head
```

### Final Checklist

- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] Alembic upgrade/downgrade verified or explicitly skipped with evidence of blocker
- [ ] No deployment, push, VPS edit, or out-of-scope file modification occurred
