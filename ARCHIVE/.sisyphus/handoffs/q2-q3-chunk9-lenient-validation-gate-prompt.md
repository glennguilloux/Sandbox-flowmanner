# Handoff: Q2-Q3 Chunk 9 — Lenient Validation Gate

## Current Status

The planning session is paused because the initial plan-generation flow stalled while preparing an executable `.sisyphus/plans/*.md` plan from:

- Source plan: `/opt/flowmanner/.hermes/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md`
- Draft notes: `/opt/flowmanner/.sisyphus/drafts/q2-q3-chunk9-lenient-validation-gate-prompt.md`

No source code has been edited.

## Goal

Modify Flowmanner’s pre-migration validation gate so it catches **new drift introduced by a chunk** without failing on **pre-existing historical drift**.

Expected outcome:

- `make validate-migration` passes on a clean deploy.
- The gate fails only when a future chunk introduces new SQLAlchemy metadata drift.
- The 559 pre-existing drift items are grandfathered into a committed snapshot baseline.

## Chosen Approach

Use a snapshot-based diff:

1. Generate deterministic JSON snapshot of current `Base.metadata`.
2. Commit `scripts/model_snapshot.json` as the baseline at chunk-9 commit time.
3. Replace strict `alembic check` in Step 1 with a snapshot diff.
4. Keep Step 2 unchanged: `alembic upgrade head --sql`.
5. Add tests and evidence showing the gate is silent on grandfathered drift and loud on introduced drift.

## Files / Areas Already Inspected

### Source plan

- `/opt/flowmanner/.hermes/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md`

### Draft notes

- `/opt/flowmanner/.sisyphus/drafts/q2-q3-chunk9-lenient-validation-gate-prompt.md`

### Current gate

- `/opt/flowmanner/scripts/validate-migration.sh`

Current behavior:

- Step 1: strict `alembic check`
- Step 2: `alembic upgrade head --sql`
- Requires Docker and running backend container named `backend`
- Optional `--clone` exists but is not implemented

### Makefile

- `/opt/flowmanner/Makefile`

Current behavior:

- `validate-migration` target exists at approximately lines 208-211.
- It shells out to `bash $(PROJECT_ROOT)/scripts/validate-migration.sh`.
- No `snapshot-refresh` target exists yet.
- Help text still says “alembic check + offline SQL render”.

### Deploy validation

- `/opt/flowmanner/deploy-backend.sh`

Important finding:

- `deploy-backend.sh` does **not** call `scripts/validate-migration.sh`.
- It duplicates validation inline in `run_validation()` around lines 222-268.

Implication:

- Changing only `scripts/validate-migration.sh` will change `make validate-migration`, but **will not** change `deploy-backend.sh --migrate`.
- The executable plan should include both:
  - standalone gate update
  - deploy validation update or refactor to shared validation

### SQLAlchemy metadata / Alembic pattern

- `/opt/flowmanner/backend/app/models/__init__.py`
- `/opt/flowmanner/backend/alembic/env.py`

Current behavior:

- `backend/app/models/__init__.py` defines `Base`, `TimestampMixin`, and `UUIDMixin`.
- It imports many model modules, but not all.
- `backend/alembic/env.py` does:

```python
from app.models import Base
target_metadata = Base.metadata
```

Important implication:

- A snapshot script that only imports `app.models` will mirror Alembic’s current import coverage.
- It may miss SQLAlchemy model modules that are not imported by `backend/app/models/__init__.py`.

Detected unimported SQLAlchemy model modules include:

- `backend/app/models/analytics.py`
- `backend/app/models/auth_models.py`
- `backend/app/models/auth_v3_models.py`
- `backend/app/models/feedback_models.py`
- `backend/app/models/learning_models.py`
- `backend/app/models/models.py`
- `backend/app/models/notification_models.py`
- `backend/app/models/phase4_models.py`
- `backend/app/models/roadmap_models.py`
- `backend/app/models/tool_models.py`
- `backend/app/models/trigger_models.py`
- `backend/app/models/webhook_models.py`

Decision needed before implementation:

- Should the snapshot represent only Alembic-visible metadata, or all SQLAlchemy DB model modules?

### Existing snapshot files

No current implementation files exist:

- `/opt/flowmanner/scripts/snapshot_model_metadata.py` — does not exist
- `/opt/flowmanner/scripts/model_snapshot.json` — does not exist
- `/opt/flowmanner/backend/scripts/snapshot*.py` — none found

Only unrelated generated SDK snapshot files exist under `sdk-python/`.

### Test infrastructure

- Backend pytest config: `/opt/flowmanner/backend/pyproject.toml`
- Relevant conftest: `/opt/flowmanner/backend/tests/conftest.py`
- Existing tests already import `app.models` and inspect `Base.metadata.tables`.
- `integration` marker exists.
- Recommended new test file: `/opt/flowmanner/backend/tests/test_validate_migration_gate.py`.

Important correction:

- The source plan references `backend/tests/test_community_models.py`, but that file does **not** currently exist.
- Regression testing should use the actual existing test file names, or skip this reference until the file exists.

## Key Risks / Gaps to Resolve

1. **Deploy validation duplication**
   - `deploy-backend.sh` has inline validation logic.
   - Must update both standalone script and deploy validation, or refactor deploy to call shared logic.

2. **Container path mismatch**
   - `backend/Dockerfile` copies `backend/scripts/` into `/app/scripts/`.
   - Root `/opt/flowmanner/scripts/` is not copied into the backend image.
   - If snapshot generation runs inside the container via `python /app/scripts/snapshot_model_metadata.py`, the script likely belongs under `backend/scripts/`, or Dockerfile must be updated.

3. **Host-vs-container Python**
   - Running snapshot generation on the host may require matching Python dependencies and `PYTHONPATH=/opt/flowmanner/backend`.
   - Running inside the backend container is safer because it matches deployed runtime dependencies.

4. **Incomplete model imports**
   - `app.models.__init__` does not import every SQLAlchemy model module.
   - Need explicit decision:
     - mirror Alembic-visible metadata only, or
     - add missing imports before snapshotting.

5. **Generated timestamp**
   - Snapshot should include `generated_at`, but diff logic should ignore it.

6. **Human-readable diff**
   - Diff output should report only new/removed/changed items since baseline.
   - Avoid raw 559-item dump.

7. **Evidence**
   - Need evidence file with pasted command output, not summaries.
   - Need pre-existing drift inventory categorized.

## Recommended Next Steps

1. Finish Metis gap analysis if continuing the original planning flow.
2. Generate the executable Sisyphus plan at:

   `/opt/flowmanner/.sisyphus/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md`

3. Ensure the plan includes these work streams:

   - Decide import coverage for snapshot baseline.
   - Add deterministic snapshot generator.
   - Add diff helper or inline diff logic.
   - Add committed snapshot JSON baseline.
   - Update standalone `scripts/validate-migration.sh`.
   - Update `deploy-backend.sh run_validation()` or refactor it to shared validation.
   - Add `Makefile snapshot-refresh`.
   - Add `backend/tests/test_validate_migration_gate.py`.
   - Run evidence commands and baseline regression checks.
   - Update `.sisyphus/boulder.json`.

## Suggested Commands for Executor

From `/opt/flowmanner`:

```bash
# Standalone gate after implementation
make validate-migration

# Snapshot refresh / idempotency
make snapshot-refresh
git diff scripts/model_snapshot.json

# Alembic head unchanged
docker compose exec -T backend alembic current
docker compose exec -T backend alembic heads

# New tests
docker compose exec backend pytest /app/tests/test_validate_migration_gate.py -v --tb=short

# Regression tests
docker compose exec backend pytest /app/tests/test_substrate_replay.py -q
# Do not assume test_community_models.py exists; verify actual file path before running.

# Full backend pytest baseline
docker compose exec backend pytest -q

# Git hygiene
git diff --check HEAD~N..HEAD
```

## Handoff Notes

- The source plan is already detailed, but the executable plan should not blindly copy it.
- The biggest correction is that `deploy-backend.sh` must be included because it does not currently call `scripts/validate-migration.sh`.
- The biggest implementation decision is snapshot import coverage: Alembic-visible metadata only vs all SQLAlchemy DB models.
- No code changes have been made in this session.
