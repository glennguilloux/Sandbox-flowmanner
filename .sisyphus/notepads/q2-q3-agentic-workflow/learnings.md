# Chunk 9 Notepad — Learnings

## Active Plan
- Plan: `.sisyphus/plans/q2-q3-agentic-workflow.md`
- Current chunk: `9`
- Chunk name: `Lenient Validation Gate (Make the Gate Useful)`
- Plan prompt: `.sisyphus/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md`
- Session: `ses_13f545684ffeNqPhO9GhL39u1F`

## Inherited Wisdom
- The gate must replace strict `alembic check` with a snapshot diff against a committed baseline.
- `backend/scripts/snapshot_model_metadata.py` is the canonical snapshot generator.
- `backend/scripts/model_snapshot.json` is the committed baseline.
- `backend/scripts/snapshot_diff.py` must be pure Python and deterministic.
- `scripts/validate-migration.sh` step 1 must be replaced; step 2 (`alembic upgrade head --sql`) must stay unchanged.
- `deploy-backend.sh` has duplicate inline validation logic and must be updated to use the same gate semantics as the shared script.
- `backend/Dockerfile` copies `scripts/` to `/app/scripts/`, so snapshot artifacts must live under `backend/scripts/`, not root `scripts/`.
- No new migration, no reconciliation migration, no drift fix, no `docker cp`, no `try/except: pass`, and no reference to the nonexistent `test_community_models.py`.
- Evidence must be pasted command output, not summaries.

## Key Constraints
- T1 must not edit `backend/app/models/__init__.py`.
- T2 must not require DB access.
- T3 must not compare `generated_at`, `alembic_version`, or `model_count`.
- T7 must preserve the existing helper infrastructure and step 2 behavior.
- T12 must use a temporary model change and then revert it.
- T13 must verify the running container and health endpoint.

## T1 Import-coverage audit — 2026-06-13T11:29:42.951966+00:00
- Audited 52 `backend/app/models/*.py` modules excluding `__init__.py`.
- Found 12 snapshot coverage gaps: `analytics.py`, `auth_models.py`, `auth_v3_models.py`, `feedback_models.py`, `learning_models.py`, `models.py`, `notification_models.py`, `phase4_models.py`, `roadmap_models.py`, `tool_models.py`, `trigger_models.py`, `webhook_models.py`.
- Decision recorded in `.sisyphus/drafts/q2-q3-chunk9-lenient-validation-gate-prompt.md`: ADD IMPORTS in a later task; T1 must not edit `backend/app/models/__init__.py`.
- `depth_models.py`, `handoff_packet_models.py`, `io_models.py`, and `tool_routing_models.py` were missing from `__init__.py` but do not define SQLAlchemy `Base` subclasses, so they are not snapshot coverage gaps.

## T2 Snapshot import fix — 2026-06-13T12:03:17Z
- Added concrete imports for the 12 T1 Base-subclass coverage-gap modules in `backend/app/models/__init__.py`: analytics, auth_models, auth_v3_models, feedback_models, learning_models, models, notification_models, phase4_models, roadmap_models, tool_models, trigger_models, webhook_models.
- Added `backend/scripts/snapshot_model_metadata.py` as a stdlib-only metadata snapshot generator plus `backend/app/models/__main__.py` so `python3 -m app.models` succeeds locally.
- Verified `python3 -c 'import app.models'`, `python3 -m app.models`, snapshot top-level shape, `model_count == len(tables)`, and byte-identical `tables` JSON across two consecutive snapshot generations.
- Verified 43 required tables from the 12 newly imported modules are present in `Base.metadata`.

## T2 Snapshot schema correction — 2026-06-13T12:22:28Z
- Added concrete imports for the 12 T1 Base-subclass coverage-gap modules in `backend/app/models/__init__.py`: analytics, auth_models, auth_v3_models, feedback_models, learning_models, models, notification_models, phase4_models, roadmap_models, tool_models, trigger_models, webhook_models.
- Added `backend/scripts/snapshot_model_metadata.py` as a stdlib-only metadata snapshot generator plus `backend/app/models/__main__.py` so `python3 -m app.models` succeeds locally.
- Verified importability, exact schema assertions, deterministic `tables` JSON across two generations, `ALEMBIC_VERSION`, `ruff check`, and clean LSP diagnostics without editing `backend/app/models/__init__.py`.

## T3 Snapshot diff helper — 2026-06-13T12:48:05Z
- Created `backend/scripts/snapshot_diff.py` as a stdlib-only, pure Python helper for the T2 snapshot schema.
- `diff_snapshots(old, new)` validates snapshot dictionaries, ignores `generated_at`, `alembic_version`, and `model_count`, and emits deterministic added/removed/changed lines for tables, columns, indexes, unique constraints, and foreign keys.
- Unique constraints and foreign keys are labeled with `json.dumps(..., sort_keys=True)`.
- Malformed snapshots raise `ValueError`; CLI usage exits `0` for no diff, `1` for diff, and `2` for usage or malformed input.
- Verified identical snapshots, introduced column, removed table, changed column, added index, added unique constraint, added foreign key, 50-line output cap, env-var CLI, malformed CLI, `ruff check`, and clean LSP diagnostics.


## T5 Dockerfile COPY verification — 2026-06-13T13:10:26.004042+00:00
- Confirmed `backend/Dockerfile:81` contains `COPY scripts/ /app/scripts/`.
- Because `backend/scripts/snapshot_model_metadata.py` and `backend/scripts/snapshot_diff.py` exist in the backend build context, the image will contain `/app/scripts/snapshot_model_metadata.py` and `/app/scripts/snapshot_diff.py`.
- Evidence written to `.sisyphus/evidence/chunk-9-dockerfile-copy.txt`.

## T4 Pre-existing drift inventory — 2026-06-13T13:17:59.072695+00:00
- Ran `docker compose exec -T backend alembic check` with `set +e` from `/opt/flowmanner` so the failing command could be captured.
- Raw output exit status was `255`; raw output was preserved at `.sisyphus/evidence/t4_alembic_check_raw.txt` and `.sisyphus/evidence/pre_existing_drift_raw_alembic_check.txt`.
- Categorized inventory written to `.sisyphus/evidence/pre_existing_drift_inventory.txt`.
- Alembic reported 588 `Detected ...` lines. Excluded 29 PostgreSQL SERIAL sequence ownership notices, leaving 559 pre-existing drift items.
- Drift count by type: tables 82 (added 10, removed 72), columns 185 (added 23, removed 25, type_change 11, NOT NULL 113, NULL 2, comment 11), indexes 241 (added 48, removed 186, changed 7), unique constraints 14 (added 1, removed 13), foreign keys 37 (added 8, removed 29), unknown 0.
- No migrations, model definitions, or validation scripts were modified for T4.

## T7 Validate migration step 1 replacement — 2026-06-13T15:37:32+02:00
- Replaced `scripts/validate-migration.sh` Step 1 with snapshot-diff logic while preserving Step 2 (`alembic upgrade head --sql`) and helper infrastructure.
- Step 1 now resolves `SNAPSHOT_FILE` to `${COMPOSE_DIR}/backend/scripts/model_snapshot.json`, generates a fresh container snapshot via `python /app/scripts/snapshot_model_metadata.py`, diffs with `python /app/scripts/snapshot_diff.py "$SNAPSHOT_FILE" "$FRESH_SNAPSHOT"`, and treats exit `1` as a clear validation failure.
- Verified with `bash -n scripts/validate-migration.sh` and a temporary fake `docker` shim covering missing snapshot, clean diff, diff-found, and snapshot-generation-failure branches without touching the live container.
- Evidence saved to `.sisyphus/evidence/chunk-9-validate-migration-step1.txt`.

## T7 container snapshot path fix — 2026-06-13T15:52:56+02:00
- Fixed the no-volume backend container path bug by keeping `SNAPSHOT_FILE` as the host-side `${COMPOSE_DIR}/backend/scripts/model_snapshot.json` and adding `CONTAINER_SNAPSHOT_FILE="${CONTAINER_SNAPSHOT_FILE:-/app/scripts/model_snapshot.json}"`.
- The diff command now passes `"$CONTAINER_SNAPSHOT_FILE"` and `"$FRESH_SNAPSHOT"` to `/app/scripts/snapshot_diff.py`; the host path is only used for the preflight existence check.
- Moved the missing-snapshot check before the Docker preflight so `SNAPSHOT_FILE=/tmp/does-not-exist-manual.json scripts/validate-migration.sh` fails before any `docker compose` invocation.
- Re-verified with `bash -n scripts/validate-migration.sh`, the required missing-snapshot check, and a fake Docker clean branch that recorded `python /app/scripts/snapshot_diff.py /app/scripts/model_snapshot.json ...`.




## T8 Makefile snapshot-refresh target — 2026-06-13T13:33:24Z
- Added `.PHONY: snapshot-refresh` in the Makefile database section.
- Target runs `$(COMPOSE_PROD) exec -T backend python /app/scripts/snapshot_model_metadata.py > $(PROJECT_ROOT)/backend/scripts/model_snapshot.json` and echoes refresh status.
- Updated `validate-migration` help text from `alembic check + offline SQL render` to `snapshot diff + offline SQL render`.
- Verified `make help` lists `snapshot-refresh`; `make -n snapshot-refresh` dry-runs the expected container command and exact output path. Did not run the real refresh target.

## T9 Deploy validation delegation — 2026-06-13T14:18:23.742840+00:00
- Refactored `deploy-backend.sh run_validation()` to delegate real validation to `bash "${COMPOSE_DIR}/scripts/validate-migration.sh"`.
- Preserved deploy-owned guards: `MIGRATE=false` returns immediately, `VALIDATE=false` skips with a warning, and `DRY_RUN=true` prints `bash /opt/flowmanner/scripts/validate-migration.sh` plus `snapshot diff + offline SQL render` without executing it.
- Verified with `bash -n deploy-backend.sh`, `bash deploy-backend.sh --dry-run --migrate`, `bash deploy-backend.sh --dry-run`, and `bash deploy-backend.sh --dry-run --migrate --no-validate`.
- Verified the call site remains `if ! run_validation; then`.
- Evidence: `.sisyphus/evidence/chunk-9-deploy-dry-run.txt`.

## T10 Snapshot baseline generation — 2026-06-13T16:48:25+02:00
- Verified the running backend image initially lacked `/app/scripts/snapshot_model_metadata.py` and `/app/scripts/snapshot_diff.py`; rebuilt/restarted with `bash deploy-backend.sh` without `--migrate`, then confirmed both files were present.
- `make snapshot-refresh` generated `backend/scripts/model_snapshot.json` with valid JSON keys `generated_at`, `alembic_version`, `model_count`, `tables`; observed `model_count == len(tables) == 134` and file size `96140` bytes, within the expected 50–200KB range.
- The first idempotency attempt exposed nondeterministic `generated_at`; fixed `backend/scripts/snapshot_model_metadata.py` to use deterministic `generated_at` (`1970-01-01T00:00:00Z` by default, with `SOURCE_DATE_EPOCH`/`SNAPSHOT_GENERATED_AT` overrides).
- Rebuilt/restarted backend again without migrations and verified two consecutive `make snapshot-refresh` runs produced identical SHA-256 `245ba76f98cfb8aa05be33fd0058a923e7176a237eeb350a0c2ac5f0b1a89b86`.
- Evidence captured in `.sisyphus/evidence/chunk-9-snapshot-refresh-output.txt`.
