# Q2-Q3 Chunk 9 — Lenient Validation Gate (Snapshot Diff)

## Open Questions
- Import coverage decision for `backend/app/models/__init__.py`: ADD IMPORTS. T1 audit found 12 unimported model modules defining SQLAlchemy `Base` subclasses: `analytics.py`, `auth_models.py`, `auth_v3_models.py`, `feedback_models.py`, `learning_models.py`, `models.py`, `notification_models.py`, `phase4_models.py`, `roadmap_models.py`, `tool_models.py`, `trigger_models.py`, and `webhook_models.py`. Do not edit `__init__.py` in T1; add imports in the follow-up snapshot/import task so `Base.metadata` matches Alembic metadata.
- `deploy-backend.sh run_validation()` refactor vs duplicate-inline decision: **Option A (refactor) selected** — delegate real validation to `scripts/validate-migration.sh` so Makefile and deploy validation share the same snapshot-diff semantics.

## Notes
- This draft is the canonical place for chunk-9 decisions and follow-up notes.

## T6 Deploy validation decision — 2026-06-13T13:12:11Z
- Decision file: `.sisyphus/evidence/chunk-9-deploy-validation-decision.txt`.
- Chosen **Option A (refactor)**: do not duplicate inline validation in `deploy-backend.sh`; keep `scripts/validate-migration.sh` as the single source of truth and have `run_validation()` call it after preserving deploy-owned `MIGRATE=false`, `VALIDATE=false`, and `DRY_RUN=true` handling.
- Why safer for FlowManner deploy behavior: avoids divergent validation semantics between `make validate-migration` and `deploy-backend.sh --migrate`, while preserving the conservative deploy ordering where validation aborts before migrations if the shared gate exits non-zero.

## T5 Dockerfile COPY verification — 2026-06-13T13:10:26.004042+00:00
- Verified `backend/Dockerfile` copies `scripts/` to `/app/scripts/` at line 81: `COPY scripts/ /app/scripts/`.
- Verified source files exist: `backend/scripts/snapshot_model_metadata.py` and `backend/scripts/snapshot_diff.py`.
- Evidence saved at `.sisyphus/evidence/chunk-9-dockerfile-copy.txt`.

## T4 Pre-existing drift inventory — 2026-06-13T13:17:59.072695+00:00
- Evidence command: `docker compose exec -T backend alembic check` from `/opt/flowmanner`; exit status `255`.
- Raw output preserved in `.sisyphus/evidence/t4_alembic_check_raw.txt` and `.sisyphus/evidence/pre_existing_drift_raw_alembic_check.txt`.
- Inventory file: `.sisyphus/evidence/pre_existing_drift_inventory.txt`.
- Counting decision: treat 29 `Detected sequence named ... assuming SERIAL and omitting` lines as PostgreSQL SERIAL ownership notices, not model/migration drift items. This reduces 588 Alembic `Detected ...` lines to the expected 559 pre-existing drift items.
- Categorization decision: report drift by high-level Alembic object type (tables, columns, indexes, unique constraints, foreign keys, unknown), then break each type into Alembic action/subtype where useful.
- T4 did not fix drift, edit models, edit migrations, or modify validation scripts.

## T7 Validate migration step 1 replacement — 2026-06-13T15:37:32+02:00
- `scripts/validate-migration.sh` Step 1 now uses `${COMPOSE_DIR}/backend/scripts/model_snapshot.json` as the committed baseline, generates a fresh snapshot in the backend container with `python /app/scripts/snapshot_model_metadata.py`, and diffs with `python /app/scripts/snapshot_diff.py "$SNAPSHOT_FILE" "$FRESH_SNAPSHOT"`.
- Missing baseline, container snapshot-generation failure, and diff exit `1` all produce explicit `[FAIL]` messages and exit non-zero.
- Step 2 (`alembic upgrade head --sql`) was preserved unchanged.
- Static verification used `bash -n scripts/validate-migration.sh` plus a temporary fake `docker` shim for the missing-snapshot, clean, diff-found, and generation-failure branches.

## T7 container snapshot path fix — 2026-06-13T15:52:56+02:00
- Corrected the container path contract: the host baseline remains `${COMPOSE_DIR}/backend/scripts/model_snapshot.json`, while the backend container receives `/app/scripts/model_snapshot.json` through explicit `CONTAINER_SNAPSHOT_FILE`.
- The diff command now invokes `/app/scripts/snapshot_diff.py "$CONTAINER_SNAPSHOT_FILE" "$FRESH_SNAPSHOT"`, so no-volume backend images can read the committed baseline copied by `backend/Dockerfile`.
- The missing-snapshot check now runs before the Docker preflight, so a missing baseline exits before any `docker compose` command is executed.
- Re-verified with `bash -n scripts/validate-migration.sh`, the required missing-snapshot command, and a fake Docker clean branch that recorded the expected `/app/scripts/model_snapshot.json` diff argument.




## T8 Makefile snapshot-refresh target — 2026-06-13T13:33:24Z
- Makefile now has a `snapshot-refresh` target and discoverable help entry.
- The target uses the backend container script `/app/scripts/snapshot_model_metadata.py` and writes `/opt/flowmanner/backend/scripts/model_snapshot.json`.
- Verification: `make help` lists the target; `make -n snapshot-refresh` dry-runs the command; the real refresh is deferred to T10 after the backend image is rebuilt with the new scripts.

## T9 Deploy validation delegation — 2026-06-13T14:18:23.742840+00:00
- Implemented T6 Option A in `deploy-backend.sh`: `run_validation()` now delegates to `scripts/validate-migration.sh` as the single source of truth.
- Kept deploy-owned behavior intact: no migration skips validation, `--no-validate` skips validation, and `--dry-run --migrate` shows the delegated validation command and `snapshot diff + offline SQL render`.
- Did not change the `run_validation()` caller, deploy flags, migrations, model definitions, or `scripts/validate-migration.sh`.
- Evidence captured in `.sisyphus/evidence/chunk-9-deploy-dry-run.txt`.
