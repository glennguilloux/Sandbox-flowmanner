# Chunk 9 Notepad — Decisions

## Pending Decisions
- T1: whether to add missing imports to `backend/app/models/__init__.py` or document gaps.

## Defaults from Plan
- T1 default: add missing imports so snapshot metadata matches Alembic metadata.
- T6 default: refactor `deploy-backend.sh` to call the shared script.

## T6 Deploy validation decision — 2026-06-13T13:12:11Z
- Chosen **Option A (refactor)**: keep `scripts/validate-migration.sh` as the single source of truth and have `deploy-backend.sh --migrate` delegate real validation to that shared gate.
- Rationale: safer for FlowManner deploy behavior because the Makefile path and deploy path will enforce the same lenient snapshot-diff semantics, avoiding duplicated inline drift between `make validate-migration` and `deploy-backend.sh --migrate`.
- Deploy flow remains conservative: `run_validation()` still sits between `build_and_deploy` and `run_migrations`; a non-zero shared-script exit still aborts before migrations while preserving existing `--no-validate` and dry-run handling.
