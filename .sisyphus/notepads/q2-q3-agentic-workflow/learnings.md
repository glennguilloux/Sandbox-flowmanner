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

