# Q2-Q3 Chunk 9 — Lenient Validation Gate (Snapshot Diff)

## TL;DR

> **Quick Summary**: Replace the strict `alembic check` step in FlowManner's pre-migration validation gate with a snapshot-based diff. A committed baseline `model_snapshot.json` captures the 559 pre-existing drift items; a freshly-generated snapshot of `Base.metadata` is diffed against it. Only NEW drift introduced by a chunk triggers a failure. The 559 grandfathered items stay silent. Step 2 (`alembic upgrade head --sql`) is unchanged.
>
> **Deliverables**:
> - `backend/scripts/snapshot_model_metadata.py` — deterministic JSON serializer of `Base.metadata`
> - `backend/scripts/model_snapshot.json` — committed baseline (~50–200KB)
> - `backend/scripts/snapshot_diff.py` — pure-stdlib diff helper (or inline in shell)
> - `scripts/validate-migration.sh` — step 1 replaced with snapshot diff
> - `Makefile` — adds `snapshot-refresh` target; updates help text
> - `deploy-backend.sh` — `run_validation()` refactored to call shared logic (or duplicate)
> - `backend/tests/test_validate_migration_gate.py` — 4+ new tests
> - `.sisyphus/evidence/chunk-9-lenient-gate-valid.txt` — evidence file
> - `.sisyphus/evidence/pre_existing_drift_inventory.txt` — categorized drift inventory
> - `.sisyphus/boulder.json` — chunk 9 entry marked complete (or `complete-with-bugfix-by-orchestrator`)
>
> **Estimated Effort**: Short (1–2 sessions)
> **Parallel Execution**: YES — 3 implementation waves + 1 final verification wave
> **Critical Path**: T1 (decision) → T2 (snapshot script) → T3 (snapshot baseline) → T6 (validate-migration.sh) → T10 (tests) → T13 (commit) → F1–F4

---

## Context

### Original Request

Modify FlowManner's pre-migration validation gate so it catches **NEW drift introduced by a chunk** without failing on **559 pre-existing historical drift items**. `make validate-migration` is currently red on every clean deploy; the noise drowns out real new damage. After this chunk, the gate is silent on grandfathered items and loud on anything introduced by a future chunk.

### Interview Summary

**Key Discussions** (from the paused handoff at `.sisyphus/handoffs/q2-q3-chunk9-lenient-validation-gate-prompt.md`):
- **Approach**: snapshot-based diff, replacing strict `alembic check` in step 1. Step 2 unchanged.
- **Baseline capture**: commit `model_snapshot.json` at chunk-9 commit time; from then on, the 559 items are silent.
- **Critical correction from handoff**: `deploy-backend.sh run_validation()` has DUPLICATE inline validation (lines 222–280) that does NOT call `scripts/validate-migration.sh`. Plan must update both, or refactor deploy to call shared logic.
- **Critical correction from handoff**: backend Dockerfile copies `backend/scripts/` to `/app/scripts/` (line 81) but does NOT copy root `scripts/`. Snapshot script must live in `backend/scripts/`, not root `scripts/`.
- **Critical correction from handoff**: source plan references `test_community_models.py` but that file does NOT exist. Use `test_substrate_replay.py` as the regression anchor.

**Research Findings**:
- `scripts/validate-migration.sh` is 146 lines: Step 1 `alembic check`, Step 2 `alembic upgrade head --sql`, Step 3 `--clone` unwired.
- `Makefile` line 211: `bash $(PROJECT_ROOT)/scripts/validate-migration.sh`. Help text on line 209 still says "alembic check + offline SQL render".
- `deploy-backend.sh` line 222: `run_validation()` duplicates validation inline. Called from line 417.
- `backend/app/models/__init__.py` (221 lines) imports ~30 model modules. May not import all SQLAlchemy model modules; a verification task must enumerate the gap before snapshot script is written.
- `backend/alembic/env.py` does `from app.models import Base; target_metadata = Base.metadata` — Alembic sees the same import set as `import app.models`.
- `backend/tests/test_substrate_replay.py` exists. Substrate baseline is 151 pass / 10 pre-existing failures (locked in `.sisyphus/plans/substrate-baseline-v1.md`).
- No `backend/scripts/snapshot*.py` or `backend/scripts/model_snapshot.json` exists.

### Metis Review

**Identified Gaps** (addressed in plan):
- **Deploy validation duplication** → Task T7 explicitly refactors `deploy-backend.sh run_validation()` to call shared script (preferred) or duplicates snapshot-diff logic inline.
- **Container path mismatch** → Snapshot script and committed baseline live in `backend/scripts/`, baked into Docker image at `/app/scripts/`. No `docker cp` workarounds.
- **Incomplete model imports** → Task T1 (decision) + T2 (snapshot script) require import-coverage audit. If `app/models/__init__.py` misses any model module, add the import before snapshotting.
- **Test file path error in source plan** → All test references use `backend/tests/test_validate_migration_gate.py` (new) and `backend/tests/test_substrate_replay.py` (existing). No reference to nonexistent `test_community_models.py`.
- **Determinism of snapshot** → Snapshot script uses `sort_keys=True`, alphabetical sort of tables/columns/indexes, normalizes types via `str(col.type)`. Idempotency verified by `git diff` being empty after two consecutive `make snapshot-refresh` runs.
- **Human-readable diff output** → Task T3 (`snapshot_diff.py`) outputs line-by-line `+`/`-`/`~` markers with paths. Caps at 50 lines + "and N more" to avoid noise.
- **Evidence** → Task T12 pastes command outputs (not summaries) into `.sisyphus/evidence/chunk-9-lenient-gate-valid.txt`. Task T11 categorizes the 559 drift items.
- **Boulder tracking** → Task T14 updates `.sisyphus/boulder.json` per existing chunk pattern.

---

## Work Objectives

### Core Objective

Convert the noisy 559-item `alembic check` failure into a focused, signal-only gate that distinguishes new damage from historical debt.

### Concrete Deliverables

| Path | Type | Purpose |
|------|------|---------|
| `backend/scripts/snapshot_model_metadata.py` | NEW | Deterministic JSON serializer of `Base.metadata` |
| `backend/scripts/model_snapshot.json` | NEW (committed) | Baseline snapshot capturing current 559 drift items |
| `backend/scripts/snapshot_diff.py` | NEW | Pure-stdlib diff helper (or inline in shell) |
| `scripts/validate-migration.sh` | MODIFIED | Step 1 replaced with snapshot diff; Step 2 unchanged |
| `Makefile` | MODIFIED | Adds `snapshot-refresh` target; updates help text |
| `deploy-backend.sh` | MODIFIED | `run_validation()` refactored to shared logic OR duplicates inline |
| `backend/tests/test_validate_migration_gate.py` | NEW | 4+ new tests (snapshot shape, idempotency, diff detection, step 2) |
| `.sisyphus/evidence/chunk-9-lenient-gate-valid.txt` | NEW | Pasted command outputs |
| `.sisyphus/evidence/pre_existing_drift_inventory.txt` | NEW | Categorized 559-item inventory |
| `.sisyphus/boulder.json` | MODIFIED | Chunk 9 entry added |

### Definition of Done

- [ ] `make validate-migration` exits 0 against the running container.
- [ ] `make snapshot-refresh` is idempotent (two consecutive runs produce identical JSON; `git diff` is empty).
- [ ] `make validate-migration` exits non-zero with a clear error message when a new column is added to any model in a test.
- [ ] `make validate-migration` is silent on the 559 pre-existing drift items.
- [ ] `deploy-backend.sh --migrate` (or the user-initiated dry-run equivalent) uses the SAME snapshot diff as `make validate-migration`.
- [ ] 4+ new tests pass; substrate baseline unchanged (151 pass / 10 pre-existing failures).
- [ ] `alembic current == alembic heads` (no migration in this chunk).
- [ ] `git diff --check HEAD~N..HEAD` clean.
- [ ] Evidence file contains pasted command outputs (not summaries).
- [ ] `pre_existing_drift_inventory.txt` exists with categorized 559 items.

### Must Have

- Snapshot script produces deterministic JSON (sort keys, stable ordering, normalized types).
- Committed baseline JSON captures the current state of `Base.metadata`.
- Diff logic flags only NEW drift items; grandfathered items are silent.
- Diff output is human-readable: `+ table.users: columns.foo (added)` style, not a raw 559-item dump.
- `make snapshot-refresh` target exists; `make validate-migration` help text is updated.
- `deploy-backend.sh` uses the same snapshot-diff logic (refactored or duplicated).
- Step 2 (`alembic upgrade head --sql`) is UNCHANGED — the asyncpg/sa.inspect/env.py bug catch stays.
- 4+ new tests in `backend/tests/test_validate_migration_gate.py`.
- Pre-existing drift inventory is categorized and committed to evidence dir.

### Must NOT Have (Guardrails)

- ❌ No new migration. This chunk is purely script/test/snapshot work.
- ❌ No reconciliation migration (Option 2 from issue #2 — risky).
- ❌ No drift fix (Option 3 from issue #2 — multi-week separate initiative).
- ❌ No change to step 2 (`alembic upgrade head --sql`) behavior.
- ❌ No `docker cp` workarounds — fix must be baked into the Docker image.
- ❌ No `try/except: pass` to make tests pass — diff logic raises on bad input.
- ❌ No reference to nonexistent `test_community_models.py` — use `test_substrate_replay.py` for regression.
- ❌ No silent fallthrough when the snapshot file is missing — gate exits 1 with a clear "Run `make snapshot-refresh`" message.
- ❌ No per-chunk drift tracking — snapshot is global, not per-feature.

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — All verification is agent-executed. No exceptions. Acceptance criteria requiring "user manually tests/confirms" are FORBIDDEN.

### Test Decision

- **Infrastructure exists**: YES (pytest in `backend/pyproject.toml` with `asyncio_mode="auto"`, `integration` marker, `backend/tests/conftest.py` sets env/mocks before app imports).
- **Automated tests**: YES (tests-after — 4+ new tests added in Wave 3 after the snapshot script is committed).
- **Framework**: pytest.
- **TDD/Tests-after**: Tests-after. The snapshot script and gate must be implemented first (Wave 1 + 2) to know what the tests assert against.

### QA Policy

Every task MUST include agent-executed QA scenarios. Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}` (test/CLI/API tasks) or `.sisyphus/evidence/chunk-9-*.txt` (chunk-level evidence).

- **Library/Module (snapshot script, diff helper)**: Use Bash (Python REPL) — Import module, call `build_snapshot(Base.metadata)`, compare to baseline, assert no diff.
- **Shell script (validate-migration.sh, deploy-backend.sh)**: Use Bash (exit code + stdout) — Run the script, capture exit code and stdout, assert both.
- **API/Backend (in-container exec)**: Use Bash (docker compose exec) — Run `python /app/scripts/snapshot_model_metadata.py` inside the container, capture stdout, compare to committed baseline.
- **Tests (pytest)**: Use Bash (pytest) — Run `docker compose exec backend pytest /app/tests/test_validate_migration_gate.py -v --tb=short`, assert all pass.
- **Regression (chunk 7 anchor)**: Use Bash (pytest) — Run `docker compose exec backend pytest /app/tests/test_substrate_replay.py -q`, assert 27 pass.

### Required Evidence Files

| File | Contents | Task |
|------|----------|------|
| `.sisyphus/evidence/chunk-9-lenient-gate-valid.txt` | `make validate-migration` output; `alembic current/heads`; `pytest -q` tail; `git diff --check` output | T12 |
| `.sisyphus/evidence/pre_existing_drift_inventory.txt` | Categorized 559-item inventory (e.g., "removed indexes: N, missing tables: M, ...") | T11 |
| `.sisyphus/evidence/chunk-9-snapshot-refresh-idempotent.txt` | Two consecutive `make snapshot-refresh` runs + empty `git diff` output | T3 |
| `.sisyphus/evidence/chunk-9-introduced-drift-fails.txt` | Test column added to `CommunityTemplate`, gate exits non-zero with error naming the column | T10 |

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundation + decision):
├── Task T1: Import-coverage audit + decision [quick]
├── Task T2: Snapshot script backend/scripts/snapshot_model_metadata.py [deep]
├── Task T3: Snapshot diff helper backend/scripts/snapshot_diff.py [quick]
├── Task T4: Generate pre-existing drift inventory [quick]
├── Task T5: backend/Dockerfile — no change needed (verify COPY semantics) [quick]
└── Task T6: Decision: refactor deploy-backend.sh vs duplicate inline [quick]

Wave 2 (After Wave 1 — gate replacement, MAX PARALLEL):
├── Task T7: scripts/validate-migration.sh step 1 replacement [deep]
├── Task T8: Makefile snapshot-refresh target + help text update [quick]
├── Task T9: deploy-backend.sh run_validation() update per T6 decision [deep]
└── Task T10: Commit baseline backend/scripts/model_snapshot.json [quick]

Wave 3 (After Wave 2 — tests + evidence + boulder):
├── Task T11: backend/tests/test_validate_migration_gate.py (4+ tests) [deep]
├── Task T12: Evidence files (chunk-9-lenient-gate-valid.txt, snapshot-refresh, introduced-drift) [quick]
├── Task T13: Run gate against running container, capture pasted outputs [unspecified-high]
└── Task T14: Update .sisyphus/boulder.json — chunk 9 entry [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit (oracle) — Must Haves / Must NOT Haves
├── Task F2: Code quality review (unspecified-high) — Build/lint/tests/AI slop
├── Task F3: Real manual QA (unspecified-high + playwright if UI) — all QA scenarios end-to-end
└── Task F4: Scope fidelity check (deep) — 1:1 against plan, no contamination

Critical Path: T1 → T2 → T10 → T7 → T9 → T11 → T13 → F1–F4 → user okay
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 6 (Wave 1)
```

### Dependency Matrix

- **T1 (decision)**: None — start immediately.
- **T2 (snapshot script)**: T1 — depends on import-coverage decision.
- **T3 (diff helper)**: T2 — needs the snapshot shape.
- **T4 (drift inventory)**: None — independent.
- **T5 (Dockerfile verify)**: None — independent.
- **T6 (deploy decision)**: None — independent.
- **T7 (validate-migration.sh)**: T1, T2, T3 — needs snapshot + diff.
- **T8 (Makefile)**: T7 — needs the snapshot-refresh command name.
- **T9 (deploy-backend.sh)**: T6, T7 — depends on shared decision and gate.
- **T10 (commit baseline)**: T2 — needs snapshot script to produce JSON.
- **T11 (tests)**: T2, T3, T7, T10 — needs the whole pipeline.
- **T12 (evidence)**: T7, T8, T9, T10 — needs the gate working.
- **T13 (gate against container)**: T7, T8, T9, T10, T11 — needs everything.
- **T14 (boulder)**: T13 — needs verification.

### Agent Dispatch Summary

- **Wave 1 (6 tasks)**: T1 → `quick`; T2 → `deep`; T3 → `quick`; T4 → `quick`; T5 → `quick`; T6 → `quick`.
- **Wave 2 (4 tasks)**: T7 → `deep`; T8 → `quick`; T9 → `deep`; T10 → `quick`.
- **Wave 3 (4 tasks)**: T11 → `deep`; T12 → `quick`; T13 → `unspecified-high`; T14 → `quick`.
- **Final (4 tasks)**: F1 → `oracle`; F2 → `unspecified-high`; F3 → `unspecified-high`; F4 → `deep`.

---

## TODOs

> Implementation + Test = ONE Task where it makes sense; pure infrastructure tasks (Makefile, deploy) are separate.
> EVERY task MUST have: Recommended Agent Profile + Parallelization info + QA Scenarios.
> **A task WITHOUT QA Scenarios is INCOMPLETE. No exceptions.**

- [x] T1. **Import-coverage audit + decision**

  **What to do**:
  - List all `*.py` files in `backend/app/models/` (excluding `__init__.py`).
  - Grep `backend/app/models/__init__.py` for each module's stem. Report which are NOT imported.
  - Cross-reference: any module that defines a `Base` subclass (DeclarativeBase child) but is not imported is a SNAPSHOT COVERAGE GAP.
  - Decision: add missing imports to `__init__.py` OR document the gap and accept that some SQLAlchemy tables will not be in the snapshot. **Default: add missing imports** so snapshot metadata == Alembic metadata.
  - Write the decision to `.sisyphus/drafts/q2-q3-chunk9-lenient-validation-gate-prompt.md` (update Open Questions section).

  **Must NOT do**:
  - Do not modify `backend/app/models/__init__.py` in this task — that's T2's or a follow-up's job.
  - Do not modify any model file's class definitions.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple file enumeration and grep; no code logic.
  - **Skills**: `[]`
  - **Skills Evaluated but Omitted**:
    - `code-review`: not needed for a grep task.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T2–T6)
  - **Blocks**: T2 (snapshot script must use complete imports)
  - **Blocked By**: None

  **References**:
  - `backend/app/models/__init__.py:1-221` — current import list.
  - `backend/alembic/env.py:1-50` — Alembic's `target_metadata = Base.metadata` import pattern.
  - `.sisyphus/handoffs/q2-q3-chunk9-lenient-validation-gate-prompt.md:101-113` — handoff's "potentially unimported" list (may be stale).

  **Acceptance Criteria**:
  - [ ] List of all `*.py` files in `backend/app/models/` produced.
  - [ ] For each file, grep result for its import in `__init__.py` produced.
  - [ ] Coverage gap (if any) reported with file paths.
  - [ ] Decision recorded: ADD IMPORTS or DOCUMENT GAP.
  - [ ] Draft updated with the decision.

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Enumerate model files
    Tool: Bash (ls + grep)
    Preconditions: Working dir = /opt/flowmanner
    Steps:
      1. ls backend/app/models/*.py | wc -l
      2. For each .py file, grep "from app.models.${stem} import" backend/app/models/__init__.py
    Expected Result: All 30+ model files accounted for; any missing import flagged.
    Evidence: .sisyphus/evidence/chunk-9-import-coverage-audit.txt
  ```

  **Commit**: NO (research only; output goes to draft + evidence).

---

- [x] T2. **Snapshot script — `backend/scripts/snapshot_model_metadata.py`**

  **What to do**:
  - Create `backend/scripts/snapshot_model_metadata.py` (new file) at the path the Docker image copies to `/app/scripts/`.
  - The script must:
    - Import `app.models` (side effect: register all model modules with `Base.metadata`).
    - Import `Base` from `app.models`.
    - Iterate `Base.metadata.tables` sorted by table name.
    - For each table, capture:
      - `columns`: dict of `{col_name: str(col.type)}` sorted by col name.
      - `indexes`: sorted list of index names (skip anonymous indexes — those without `.name`).
      - `unique_constraints`: sorted list of `[col_names]` lists (one per UniqueConstraint).
      - `foreign_keys`: sorted list of `[source_col_name, target_fullname]` pairs.
    - Wrap the result in a top-level dict with `generated_at` (UTC ISO with `Z` suffix), `alembic_version` (env var `ALEMBIC_VERSION` or empty string), `model_count` (len(tables)).
    - Emit JSON to stdout via `json.dump(..., indent=2, sort_keys=True)`.
    - Exit 0 on success.
  - Expose two pure-Python helpers (importable from tests):
    - `build_snapshot(metadata) -> dict` — returns the snapshot dict (no I/O).
    - `_get_alembic_version() -> str` — returns env var or `""`.
  - Add a docstring with usage: `python /app/scripts/snapshot_model_metadata.py > /app/scripts/model_snapshot.json`.

  **Must NOT do**:
  - Do not add dependencies; use stdlib only (`json`, `sys`, `datetime`).
  - Do not require a DB connection — the script must work in any environment where `app.models` is importable.
  - Do not use `repr()` or any non-deterministic ordering.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: SQLAlchemy introspection; needs care to avoid non-deterministic output.
  - **Skills**: `[]`
  - **Skills Evaluated but Omitted**:
    - `python-expert`: helpful but not required for stdlib + SQLAlchemy.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (after T1)
  - **Blocks**: T3, T7, T10, T11
  - **Blocked By**: T1 (import-coverage decision)

  **References**:
  - `backend/app/models/__init__.py:1-221` — model registration side effect.
  - `backend/alembic/env.py:1-50` — Alembic's import pattern to mirror.
  - `.hermes/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md:124-181` — source plan's design spec (sketch, refine).
  - Handoff correction: `backend/Dockerfile:81` — `COPY scripts/ /app/scripts/` confirms path.

  **Acceptance Criteria**:
  - [ ] File created at `backend/scripts/snapshot_model_metadata.py`.
  - [ ] `docker compose exec backend python /app/scripts/snapshot_model_metadata.py` produces valid JSON to stdout.
  - [ ] JSON shape: `{"generated_at": str, "alembic_version": str, "model_count": int, "tables": {...}}`.
  - [ ] All `model_count` keys match the count of `tables`.
  - [ ] Two consecutive runs produce byte-identical output (deterministic).

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Run snapshot script inside container
    Tool: Bash (docker compose exec)
    Preconditions: backend container running; T1 completed
    Steps:
      1. docker compose exec -T backend python /app/scripts/snapshot_model_metadata.py > /tmp/snap1.json
      2. docker compose exec -T backend python /app/scripts/snapshot_model_metadata.py > /tmp/snap2.json
      3. diff /tmp/snap1.json /tmp/snap2.json
    Expected Result: Empty diff (snapshot is deterministic).
    Evidence: .sisyphus/evidence/chunk-9-snapshot-script-deterministic.txt

  Scenario: Snapshot has expected shape
    Tool: Bash (python -c)
    Preconditions: /tmp/snap1.json exists
    Steps:
      1. python3 -c "import json; d = json.load(open('/tmp/snap1.json')); assert {'generated_at','alembic_version','model_count','tables'} <= set(d); assert d['model_count'] == len(d['tables']); assert isinstance(d['tables'], dict); print('OK', d['model_count'], 'tables')"
    Expected Result: stdout contains "OK N tables" with N >= 30.
    Evidence: same file as above.

  Scenario: Import build_snapshot in pytest
    Tool: Bash (python -c)
    Preconditions: T2 file written
    Steps:
      1. cd /opt/flowmanner/backend && python3 -c "from app.models import Base; from scripts.snapshot_model_metadata import build_snapshot; snap = build_snapshot(Base.metadata); print(len(snap['tables']))"
    Expected Result: Prints integer >= 30 without ImportError.
    Evidence: .sisyphus/evidence/chunk-9-snapshot-importable.txt
  ```

  **Commit**: NO (lands in commit 2 with the rest of the gate).

---

- [x] T3. **Snapshot diff helper — `backend/scripts/snapshot_diff.py`**

  **What to do**:
  - Create `backend/scripts/snapshot_diff.py` (new file, same dir as snapshot script).
  - Provide a pure-Python function `diff_snapshots(old: dict, new: dict) -> list[str]` that:
    - Recursively walks `old.tables` and `new.tables`.
    - Emits a list of human-readable lines:
      - `+ tables.<name> (added)` — table only in new
      - `- tables.<name> (removed)` — table only in old
      - `+ tables.<name>.columns.<col> = <type> (added)` — column only in new
      - `- tables.<name>.columns.<col> (removed)` — column only in old
      - `~ tables.<name>.columns.<col>: <old_type> -> <new_type>` — type changed
      - `+ tables.<name>.indexes.<idx> (added)` / `- ... (removed)`
      - `+ tables.<name>.unique_constraints.<uc> (added)` / `- ... (removed)`
      - `+ tables.<name>.foreign_keys.<fk> (added)` / `- ... (removed)`
    - Returns `[]` if no diff.
  - Provide a `main()` that:
    - Reads `old_path` and `new_path` from sys.argv (or env vars `OLD_SNAPSHOT` / `NEW_SNAPSHOT`).
    - Loads both JSON, calls `diff_snapshots`, prints each line to stdout.
    - Exits 0 if no diff, exits 1 if any diff.
  - Cap output at 50 lines; if more, append `... and N more` line.

  **Must NOT do**:
  - Do not compare `generated_at` — exclude from diff.
  - Do not compare `alembic_version` — exclude from diff.
  - Do not compare `model_count` — derived from `len(tables)`, automatically consistent.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Pure recursive dict walk; stdlib only.
  - **Skills**: `[]`
  - **Skills Evaluated but Omitted**:
    - `python-expert`: not needed for stdlib recursion.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (after T2)
  - **Blocks**: T7, T11
  - **Blocked By**: T2 (needs the snapshot shape)

  **References**:
  - `.hermes/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md:185-253` — source plan's sketch of the diff logic.
  - `.hermes/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md:31-39` — desired human-readable diff output.

  **Acceptance Criteria**:
  - [ ] File created at `backend/scripts/snapshot_diff.py`.
  - [ ] `from scripts.snapshot_diff import diff_snapshots` works in pytest.
  - [ ] Two identical snapshots → `[]` (no diff).
  - [ ] A snapshot with one new column → exactly one diff line referencing the new column.
  - [ ] A snapshot with one removed table → exactly one diff line referencing the table.

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Diff detects introduced column
    Tool: Bash (python -c)
    Preconditions: T2 file written, T3 file written
    Steps:
      1. cd /opt/flowmanner/backend && python3 -c "
         from app.models import Base
         from scripts.snapshot_model_metadata import build_snapshot
         from scripts.snapshot_diff import diff_snapshots
         old = build_snapshot(Base.metadata)
         new = build_snapshot(Base.metadata)
         new['tables']['users']['columns']['__test_introduced'] = 'VARCHAR(50)'
         diff = diff_snapshots(old, new)
         assert len(diff) == 1, diff
         assert '__test_introduced' in diff[0], diff
         print('OK:', diff[0])
         "
    Expected Result: stdout contains "OK: + tables.users.columns.__test_introduced = VARCHAR(50) (added)".
    Evidence: .sisyphus/evidence/chunk-9-diff-detects-introduced.txt

  Scenario: Empty diff for identical snapshots
    Tool: Bash (python -c)
    Preconditions: T2 file written, T3 file written
    Steps:
      1. cd /opt/flowmanner/backend && python3 -c "
         from app.models import Base
         from scripts.snapshot_model_metadata import build_snapshot
         from scripts.snapshot_diff import diff_snapshots
         snap = build_snapshot(Base.metadata)
         diff = diff_snapshots(snap, snap)
         assert diff == [], diff
         print('OK: empty diff for identical snapshots')
         "
    Expected Result: stdout contains "OK".
    Evidence: same file as above.
  ```

  **Commit**: NO (lands in commit 2 with the rest of the gate).

---

- [x] T4. **Generate pre-existing drift inventory**

  **What to do**:
  - Run `docker compose exec -T backend alembic check 2>&1 > /tmp/alembic-check-output.txt` (this WILL fail with ~559 items; capture the full stderr+stdout).
  - Parse the output to count:
    - Number of missing tables (lines matching `Can't locate revision identified by` or similar table-not-found errors).
    - Number of removed indexes (lines matching `index` + `not found` or `removed`).
    - Number of removed unique constraints.
    - Number of column type mismatches.
    - Other categories as they appear.
  - Categorize the 559 items into a text report at `.sisyphus/evidence/pre_existing_drift_inventory.txt`:
    - Header: date, total count, container's alembic head.
    - One section per category with example error lines (anonymized; first 3–5 per category).
    - Note: "These items are grandfathered in `backend/scripts/model_snapshot.json` committed at chunk-9. Future chunks must run `make snapshot-refresh` to update the baseline whenever a model change is intentional."
  - Copy the raw output of `alembic check` to `.sisyphus/evidence/chunk-9-alembic-check-raw-output.txt` for reproducibility.

  **Must NOT do**:
  - Do not attempt to fix any of the drift — that's Option 3 (deferred).
  - Do not generate a reconciliation migration — that's Option 2 (rejected).
  - Do not categorize as anything other than "pre-existing historical drift."

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Capture + parse + categorize text output; no code logic.
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (independent)
  - **Blocks**: T12 (chunk-9 evidence file references the inventory)
  - **Blocked By**: None (just needs the running container)

  **References**:
  - `.hermes/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md:54-57` — source plan's process-gate requirement for the inventory.
  - `backend/alembic/versions/` — current head (for inventory header).

  **Acceptance Criteria**:
  - [ ] `.sisyphus/evidence/pre_existing_drift_inventory.txt` exists.
  - [ ] Inventory has a header with date, total count, current alembic head.
  - [ ] At least 3 categories enumerated with example error lines.
  - [ ] Total item count == 559 (or whatever the actual alembic check reports — record the actual number in the header).
  - [ ] Raw output preserved at `.sisyphus/evidence/chunk-9-alembic-check-raw-output.txt`.

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Raw output captured
    Tool: Bash (docker compose exec + file)
    Preconditions: backend container running
    Steps:
      1. ls -la .sisyphus/evidence/chunk-9-alembic-check-raw-output.txt
      2. wc -l .sisyphus/evidence/chunk-9-alembic-check-raw-output.txt
    Expected Result: File exists; line count >= 100.
    Evidence: same file (counted lines).

  Scenario: Inventory has all categories
    Tool: Bash (grep)
    Preconditions: inventory file written
    Steps:
      1. grep -c '^## ' .sisyphus/evidence/pre_existing_drift_inventory.txt
    Expected Result: >= 3 (one per category header).
    Evidence: same file (header count).
  ```

  **Commit**: NO (lands in commit 3 with evidence).

---

- [x] T5. **Verify backend/Dockerfile — no change needed**

  **What to do**:
  - Read `backend/Dockerfile` and confirm:
    - `COPY scripts/ /app/scripts/` (line 81) is present.
    - The COPY uses `scripts/` (relative to the build context, which is `backend/`), so `backend/scripts/snapshot_model_metadata.py` becomes `/app/scripts/snapshot_model_metadata.py` inside the image.
  - Verify by reading the file and grepping for `COPY scripts/`.
  - If `COPY scripts/ /app/scripts/` is NOT present:
    - Add it after the other `COPY` directives (alembic, mcp_gateway, etc.).
    - Document the addition in this task's evidence.
  - If it IS present: write a one-line confirmation to evidence file.

  **Must NOT do**:
  - Do not modify the Dockerfile if `COPY scripts/` is already there.
  - Do not add volume mounts (the handoff is explicit: no volume mounts).

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single-file read + grep; one-line conditional edit.
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (independent)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `backend/Dockerfile:1-100` — verify the COPY directive.
  - `AGENTS.homelab.md` — "Backend has NO volume mounts. All code is baked into the image."

  **Acceptance Criteria**:
  - [ ] `COPY scripts/ /app/scripts/` is present in `backend/Dockerfile` (or added).
  - [ ] Evidence file confirms the verification.

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Confirm COPY directive
    Tool: Bash (grep)
    Preconditions: backend/Dockerfile exists
    Steps:
      1. grep -n 'COPY scripts' backend/Dockerfile
    Expected Result: At least one match, e.g., `81:COPY scripts/ /app/scripts/`.
    Evidence: .sisyphus/evidence/chunk-9-dockerfile-verify.txt
  ```

  **Commit**: Conditional (only if Dockerfile was modified).

---

- [x] T6. **Decision: refactor `deploy-backend.sh run_validation()` or duplicate inline**

  **What to do**:
  - Read `deploy-backend.sh` lines 222–280 (`run_validation()` function) and lines 410–420 (call site).
  - Analyze the trade-off:
    - **Option A (preferred)**: Refactor `run_validation()` to call `bash ${COMPOSE_DIR}/scripts/validate-migration.sh` via `docker compose exec`. Single source of truth. Risk: changes the deploy flow's behavior; if the script's behavior is subtly different from inline, deploy-time validation may catch new things.
    - **Option B**: Duplicate the snapshot-diff logic inline in `deploy-backend.sh`. No coupling to the script. Risk: two places to maintain; future drift between the two implementations.
  - **Default decision**: Option A (refactor to call shared script). This is consistent with the existing `Makefile validate-migration` target.
  - Write the decision to the draft file. The executor of T9 will follow the decision.
  - If Option A is blocked (e.g., `run_validation()` needs dry-run behavior that the script doesn't expose), document the blocker and fall back to Option B with explicit duplication.

  **Must NOT do**:
  - Do not modify `deploy-backend.sh` in this task — that's T9.
  - Do not skip the decision — T9 needs it.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Read + analyze + decide; no code change.
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (independent)
  - **Blocks**: T9
  - **Blocked By**: None

  **References**:
  - `deploy-backend.sh:222-280` — current `run_validation()` inline implementation.
  - `deploy-backend.sh:410-420` — call site.
  - `scripts/validate-migration.sh:1-146` — the shared script that T7 will update.

  **Acceptance Criteria**:
  - [ ] Decision recorded in draft (Option A or Option B with rationale).
  - [ ] If Option B chosen, the duplicated code block is sketched (rough, not final).

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Decision recorded in draft
    Tool: Bash (grep)
    Preconditions: draft exists
    Steps:
      1. grep -A2 'deploy-backend.sh decision' .sisyphus/drafts/q2-q3-chunk9-lenient-validation-gate-prompt.md
    Expected Result: Shows Option A or Option B with rationale.
    Evidence: .sisyphus/evidence/chunk-9-deploy-decision.txt
  ```

  **Commit**: NO (decision only; lands in T9's commit).

---

- [x] T7. **`scripts/validate-migration.sh` — step 1 replacement (snapshot diff)**

  **What to do**:
  - Open `scripts/validate-migration.sh` (the on-host shell script).
  - Replace the current `Step 1/2: alembic check` block (lines 105–114) with a snapshot-diff block:
    - Resolve `SNAPSHOT_FILE` to `backend/scripts/model_snapshot.json` (relative to `$COMPOSE_DIR`).
    - If `SNAPSHOT_FILE` does NOT exist:
      - `log_error "Snapshot file not found: $SNAPSHOT_FILE"`
      - `log_error "Run 'make snapshot-refresh' to generate it, then commit the result."`
      - `exit 1`
    - Generate a fresh snapshot via `docker compose exec -T $BACKEND_CONTAINER python /app/scripts/snapshot_model_metadata.py > $FRESH_SNAPSHOT 2>/dev/null`. If exec fails, `log_error "Snapshot generation failed inside the container"` and `exit 1`.
    - Diff the fresh snapshot against the committed one by invoking `docker compose exec -T $BACKEND_CONTAINER python /app/scripts/snapshot_diff.py "$SNAPSHOT_FILE" "$FRESH_SNAPSHOT"` and capturing both stdout and exit code.
    - On diff exit 0: `log_success "No new drift since snapshot"`.
    - On diff exit 1: `log_error "Snapshot drift detected:"`, echo the diff output, `log_error "If this drift is intentional, run 'make snapshot-refresh' to update the baseline."`, `exit 1`.
  - KEEP Step 2 (`alembic upgrade head --sql`) UNCHANGED — do not touch lines 116–132.
  - KEEP all other infrastructure (colors, log_*, helpers, pre-flight, trap, cleanup) UNCHANGED.
  - Update the script's header comment block to reflect the new Step 1 (replace "alembic check" with "snapshot diff against scripts/model_snapshot.json").
  - Clean up `$FRESH_SNAPSHOT` in the existing `cleanup` trap.

  **Must NOT do**:
  - Do not change step 2 (`alembic upgrade head --sql`) behavior.
  - Do not change the script's external interface (exit codes 0/1, log prefix style, `--clone` flag still parsed but unwired).
  - Do not change `set -euo pipefail` or the trap.
  - Do not require any new shell dependencies (no `jq`, no `yq` — Python 3 is the diff engine).

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Shell scripting with strict mode; needs care to preserve existing behavior.
  - **Skills**: `[]`
  - **Skills Evaluated but Omitted**:
    - `code-review`: post-commit review, not in-task.

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T2, T3; gates T8, T9, T10)
  - **Parallel Group**: Wave 2 (FIRST — blocks T8, T9)
  - **Blocks**: T8, T9, T11, T12
  - **Blocked By**: T1, T2, T3

  **References**:
  - `scripts/validate-migration.sh:1-146` — full current script.
  - `scripts/validate-migration.sh:105-114` — exact lines to replace.
  - `scripts/validate-migration.sh:116-132` — DO NOT TOUCH (step 2).
  - `scripts/validate-migration.sh:41-103` — preserve all helpers (colors, log_*, trap, cleanup, pre-flight).
  - `.hermes/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md:185-253` — source plan's diff sketch (refine).
  - `Makefile:208-211` — caller; T7 changes the called script.

  **Acceptance Criteria**:
  - [ ] `scripts/validate-migration.sh` modified.
  - [ ] Step 1 block is the snapshot diff; step 2 block is unchanged.
  - [ ] `bash scripts/validate-migration.sh` (assuming container is running) exits 0.
  - [ ] `bash scripts/validate-migration.sh` with `SNAPSHOT_FILE` removed (temporarily) exits 1 with a "Snapshot file not found" message.
  - [ ] Script header comment reflects the new step 1.

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Gate passes on clean deploy
    Tool: Bash (make)
    Preconditions: backend container running; baseline snapshot committed; T8 may not be merged yet
    Steps:
      1. cd /opt/flowmanner && bash scripts/validate-migration.sh 2>&1 | tee /tmp/validate-on-clean.txt
    Expected Result: Exit 0; output contains "[OK] No new drift since snapshot" AND "[OK] Offline render OK".
    Evidence: .sisyphus/evidence/chunk-9-gate-on-clean.txt

  Scenario: Gate fails on missing snapshot
    Tool: Bash (mv + make)
    Preconditions: baseline snapshot exists; container running
    Steps:
      1. mv backend/scripts/model_snapshot.json /tmp/snapshot-bak.json
      2. bash scripts/validate-migration.sh 2>&1 | tee /tmp/validate-missing.txt
      3. mv /tmp/snapshot-bak.json backend/scripts/model_snapshot.json
    Expected Result: Exit 1; output contains "Snapshot file not found".
    Evidence: .sisyphus/evidence/chunk-9-gate-missing-snapshot.txt
  ```

  **Commit**: YES (commit 2 along with Makefile, deploy-backend.sh, baseline JSON).

---

- [x] T8. **Makefile — add `snapshot-refresh` target + update help text**

  **What to do**:
  - In `Makefile`:
    - Update the `validate-migration` help text (line 209) from "Pre-deploy migration validation gate: alembic check + offline SQL render" to "Pre-deploy migration validation gate: snapshot diff + offline SQL render".
    - Add a new `snapshot-refresh` target near the `validate-migration` target (after line 211):
      ```makefile
      .PHONY: snapshot-refresh
      snapshot-refresh: ## Refresh backend/scripts/model_snapshot.json from current Base.metadata
      	docker compose exec -T backend python /app/scripts/snapshot_model_metadata.py > backend/scripts/model_snapshot.json
      	@echo "Snapshot refreshed. Run 'git diff backend/scripts/model_snapshot.json' to review."
      ```
    - Confirm the new target appears in the `help` target's auto-generated list (most Makefile `help` targets are pattern-based and will pick it up automatically).
  - Verify by running `make help` and grepping for `snapshot-refresh`.

  **Must NOT do**:
  - Do not add other targets.
  - Do not change the `validate-migration` target's command line — only its help text.
  - Do not introduce new variables.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Two-line Makefile change.
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (after T7)
  - **Blocks**: None
  - **Blocked By**: T7 (target name + script path must be settled)

  **References**:
  - `Makefile:208-211` — current `validate-migration` target.
  - `Makefile:1-50` — `help` target pattern (verify auto-pickup).

  **Acceptance Criteria**:
  - [ ] `Makefile` updated.
  - [ ] `make help` shows `snapshot-refresh` with the new description.
  - [ ] `make validate-migration` help text says "snapshot diff + offline SQL render".
  - [ ] `make snapshot-refresh` runs the script and writes JSON to the right path.

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Makefile help includes new target
    Tool: Bash (make help + grep)
    Preconditions: Makefile updated
    Steps:
      1. make help | grep -i snapshot
    Expected Result: Line containing "snapshot-refresh" and "Refresh backend/scripts/model_snapshot.json".
    Evidence: .sisyphus/evidence/chunk-9-makefile-help.txt

  Scenario: snapshot-refresh runs the script
    Tool: Bash (make)
    Preconditions: container running; T2 script exists
    Steps:
      1. make snapshot-refresh 2>&1 | tee /tmp/refresh.txt
      2. head -5 backend/scripts/model_snapshot.json
    Expected Result: Refresh succeeds; first 5 lines of JSON are `{"alembic_version": ..., "generated_at": ..., "model_count": ..., "tables": {`.
    Evidence: .sisyphus/evidence/chunk-9-snapshot-refresh-output.txt
  ```

  **Commit**: YES (commit 2).

---

- [x] T9. **`deploy-backend.sh run_validation()` — update per T6 decision**

  **What to do**:
  - If T6 decided **Option A (refactor to call shared script)**:
    - In `deploy-backend.sh`, replace the body of `run_validation()` (lines 222–280) with a single call to the shared script:
      ```bash
      run_validation() {
        # Snapshot diff + offline render (single source of truth)
        bash "${COMPOSE_DIR}/scripts/validate-migration.sh"
      }
      ```
    - Preserve the function signature, the `set -e` propagation, the dry-run handling, and the success/failure logging.
  - If T6 decided **Option B (duplicate inline)**:
    - Replace the existing Step 1 `alembic check` block (line 244) with a snapshot-diff block that mirrors T7's logic.
    - Keep step 2 (`alembic upgrade head --sql` at line 255) unchanged.
    - Add a comment: `# Mirrors scripts/validate-migration.sh step 1; keep in sync.`
  - Whichever option, preserve:
    - The function name `run_validation()`.
    - The call site at line 417 (unchanged).
    - The `--dry-run` handling (the script's `--clone` flag does not exist; the deploy script's dry-run shows the command but does not execute).

  **Must NOT do**:
  - Do not change `run_validation()`'s caller (line 417).
  - Do not change deploy-backend.sh's flags or other functions.
  - Do not introduce a new dependency on `python3` being on the host PATH (the script already requires it for the diff, per T7).

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Deploy-script modification; touches production flow.
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T6, T7)
  - **Parallel Group**: Wave 2 (after T7)
  - **Blocks**: T11, T13
  - **Blocked By**: T6, T7

  **References**:
  - `deploy-backend.sh:222-280` — current `run_validation()` body to replace.
  - `deploy-backend.sh:410-420` — call site; do not change.
  - `scripts/validate-migration.sh:1-146` — target script (Option A) or source of duplication (Option B).
  - `.sisyphus/drafts/q2-q3-chunk9-lenient-validation-gate-prompt.md` — T6's decision.

  **Acceptance Criteria**:
  - [ ] `deploy-backend.sh run_validation()` updated per T6.
  - [ ] `bash deploy-backend.sh --dry-run --migrate` (if exposed) shows the validation step using the new logic.
  - [ ] Manual review: `run_validation()` and `validate-migration.sh` use the same gate semantics.

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: dry-run shows updated validation
    Tool: Bash (deploy-backend.sh --dry-run)
    Preconditions: deploy-backend.sh updated
    Steps:
      1. bash deploy-backend.sh --dry-run --migrate 2>&1 | grep -A2 -i 'validation'
    Expected Result: Shows "snapshot diff" or equivalent new wording; does NOT show "alembic check" as the only step.
    Evidence: .sisyphus/evidence/chunk-9-deploy-dry-run.txt
  ```

  **Commit**: YES (commit 2).

---

- [x] T10. **Generate + commit baseline `backend/scripts/model_snapshot.json`**

  **What to do**:
  - Run `make snapshot-refresh` (which is T8's target; T7's script in the container produces the JSON).
  - Verify the file is created at `backend/scripts/model_snapshot.json` and is valid JSON.
  - Verify the file size is in the 50–200KB range (hundreds of tables with dozens of columns each).
  - Verify two consecutive `make snapshot-refresh` runs produce identical output (idempotency).
  - Commit the file (it goes into commit 2).

  **Must NOT do**:
  - Do not hand-edit the JSON.
  - Do not commit if the file is empty or invalid.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single command + verification.
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T7, T8)
  - **Parallel Group**: Wave 2 (LAST)
  - **Blocks**: T11, T12, T13
  - **Blocked By**: T7, T8

  **References**:
  - `Makefile:208-211+` — `make snapshot-refresh` target (T8).
  - `backend/scripts/snapshot_model_metadata.py` — script that produces the JSON (T2).

  **Acceptance Criteria**:
  - [ ] `backend/scripts/model_snapshot.json` exists.
  - [ ] File is valid JSON.
  - [ ] File size in 50–200KB range.
  - [ ] `make snapshot-refresh && make snapshot-refresh && git diff backend/scripts/model_snapshot.json` produces empty diff.

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Baseline exists and is valid
    Tool: Bash (ls + python -c)
    Preconditions: T7, T8, T9 complete; container running
    Steps:
      1. ls -la backend/scripts/model_snapshot.json
      2. python3 -c "import json; d = json.load(open('backend/scripts/model_snapshot.json')); assert d['model_count'] == len(d['tables']); print('OK', d['model_count'], 'tables', len(json.dumps(d)), 'bytes')"
    Expected Result: File exists; stdout contains "OK N tables M bytes" with N >= 30 and M in 50_000–200_000.
    Evidence: .sisyphus/evidence/chunk-9-baseline-exists.txt

  Scenario: Refresh is idempotent
    Tool: Bash (make + git diff)
    Preconditions: baseline exists
    Steps:
      1. make snapshot-refresh
      2. git diff --stat backend/scripts/model_snapshot.json
    Expected Result: Empty output (file unchanged).
    Evidence: .sisyphus/evidence/chunk-9-snapshot-refresh-idempotent.txt
  ```

  **Commit**: YES (commit 2).

---

- [x] T11. **`backend/tests/test_validate_migration_gate.py` (4+ new tests)**

  **What to do**:
  - Create `backend/tests/test_validate_migration_gate.py` (new file).
  - Add 4 tests (source plan calls for "4+"; deliver 5 for safety):
    1. `test_snapshot_file_exists_and_is_valid_json`: load `backend/scripts/model_snapshot.json` from the host, assert it exists, assert it's valid JSON, assert the expected top-level keys (`generated_at`, `alembic_version`, `model_count`, `tables`), assert `model_count == len(tables)`.
    2. `test_snapshot_matches_current_metadata`: import `app.models` and `scripts.snapshot_model_metadata.build_snapshot`, build a fresh snapshot, compare `tables` field to the committed one. Assert equal. (This is the "I changed a model and forgot to refresh" regression.)
    3. `test_snapshot_diff_catches_introduced_column`: build fresh snapshot, add a synthetic `__test_introduced: VARCHAR(50)` column to the `users` table, diff against committed baseline, assert exactly one diff line referencing the new column.
    4. `test_step_2_offline_render_still_works`: subprocess `docker compose exec -T backend alembic upgrade head --sql` from `/opt/flowmanner`, assert returncode 0 and "CREATE" or "ALTER" or "BEGIN" in stdout. **Mark with `@pytest.mark.integration`** so it can be skipped in dev envs without Docker.
    5. `test_snapshot_diff_silent_on_identical`: call `diff_snapshots(snap, snap)` on a fresh build, assert `== []`.
  - The first three tests must be FAST and PURE (no Docker, no DB). They are the regression coverage.
  - The fourth test is the integration check.
  - All tests must pass in `pytest /app/tests/test_validate_migration_gate.py -v`.

  **Must NOT do**:
  - Do not create `test_community_models.py` (it does not exist; the source plan's reference is wrong).
  - Do not introduce a `conftest.py` change — use the existing one.
  - Do not mark the pure tests as `@pytest.mark.integration` (they must run in dev).

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Pytest patterns; integration test boundaries; SQLAlchemy-aware.
  - **Skills**: `[]`
  - **Skills Evaluated but Omitted**:
    - `python-expert`: helpful but not required for stdlib pytest.

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T2, T3, T7, T10)
  - **Parallel Group**: Wave 3 (FIRST)
  - **Blocks**: T13
  - **Blocked By**: T2, T3, T7, T10

  **References**:
  - `backend/tests/conftest.py` — existing fixtures; do not duplicate.
  - `backend/pyproject.toml` — pytest config (`testpaths=["tests"]`, `asyncio_mode="auto"`, `integration` marker).
  - `backend/tests/test_substrate_replay.py` — reference test structure (existing).
  - `.hermes/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md:262-330` — source plan's test sketches (refine; the `build_snapshot` import path is the same as the executor's path: `from scripts.snapshot_model_metadata import build_snapshot`).

  **Acceptance Criteria**:
  - [ ] File created at `backend/tests/test_validate_migration_gate.py`.
  - [ ] 5 tests defined, all passing.
  - [ ] No reference to `test_community_models.py`.
  - [ ] `pytest -v` shows all 5 with PASSED.

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: New tests pass
    Tool: Bash (pytest in container)
    Preconditions: T11 file written; container running; baseline committed
    Steps:
      1. docker compose exec backend pytest /app/tests/test_validate_migration_gate.py -v --tb=short 2>&1 | tee /tmp/validate-tests.txt
    Expected Result: 5 passed (or 4 passed + 1 skipped if integration marker skipped).
    Evidence: .sisyphus/evidence/chunk-9-new-tests-pass.txt

  Scenario: Substrate regression unchanged
    Tool: Bash (pytest in container)
    Preconditions: T11 complete
    Steps:
      1. docker compose exec backend pytest /app/tests/test_substrate_replay.py -q 2>&1 | tee /tmp/substrate-replay.txt
    Expected Result: 27 passed (chunk 7 anchor; unchanged from baseline).
    Evidence: .sisyphus/evidence/chunk-9-substrate-regression.txt
  ```

  **Commit**: YES (commit 3).

---

- [x] T12. **Evidence files (chunk-9-lenient-gate-valid.txt, snapshot-refresh, introduced-drift)**

  **What to do**:
  - Create `.sisyphus/evidence/chunk-9-lenient-gate-valid.txt` containing the pasted outputs (not summaries) of:
    - `make validate-migration` (full stdout, exit 0).
    - `docker compose exec -T backend alembic current` (one line).
    - `docker compose exec -T backend alembic heads` (one line).
    - `docker compose exec backend pytest /app/tests/test_validate_migration_gate.py -v` tail (5+ lines).
    - `docker compose exec backend pytest -q` tail (10 lines).
    - `git diff --check HEAD~N..HEAD` output (where N = number of commits in this chunk; should be 0).
    - `curl -fsSL http://127.0.0.1:8000/health` output (one line, `{"status":"ok"}` or similar).
  - Add to T10's evidence file: `.sisyphus/evidence/chunk-9-snapshot-refresh-idempotent.txt` (already done in T10, just confirm it's complete).
  - Add `.sisyphus/evidence/chunk-9-introduced-drift-fails.txt`:
    - Temporarily add `__test_introduced: Mapped[str] = mapped_column(String(50))` to ONE model (e.g., `CommunityTemplate` in `backend/app/models/community_models.py`).
    - Run `bash scripts/validate-migration.sh` (DO NOT regenerate snapshot).
    - Capture the gate's exit-1 output naming the new column.
    - Revert the model change.
    - Re-run `make snapshot-refresh` (to keep the committed baseline in sync — DO NOT commit the regen).
    - Confirm gate is green again.
  - All evidence files: each is a text file with command + output, no commentary beyond brief headers.

  **Must NOT do**:
  - Do not summarize — paste raw output.
  - Do not commit the temporary model change.
  - Do not commit the regenerated snapshot from the introduced-drift test.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Capture + write text files.
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T11; consumes outputs from T7, T8, T9, T10)
  - **Parallel Group**: Wave 3 (after T11)
  - **Blocks**: T14
  - **Blocked By**: T7, T8, T9, T10, T11

  **References**:
  - `.hermes/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md:54-57` — process-gate requirements.
  - `.hermes/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md:366-404` — exact commands to run and paste.
  - `backend/app/models/community_models.py` — model used for the introduced-drift test.

  **Acceptance Criteria**:
  - [ ] `.sisyphus/evidence/chunk-9-lenient-gate-valid.txt` exists with pasted outputs.
  - [ ] `.sisyphus/evidence/chunk-9-introduced-drift-fails.txt` exists with the captured exit-1 output.
  - [ ] `.sisyphus/evidence/chunk-9-snapshot-refresh-idempotent.txt` exists (T10 deliverable).
  - [ ] `.sisyphus/evidence/pre_existing_drift_inventory.txt` exists (T4 deliverable).
  - [ ] Temporary model change has been reverted (working tree is clean except for the planned changes).

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: All evidence files exist
    Tool: Bash (ls)
    Preconditions: T12 complete
    Steps:
      1. ls -la .sisyphus/evidence/chunk-9-*.txt .sisyphus/evidence/pre_existing_drift_inventory.txt
    Expected Result: All 4 files exist with non-trivial size (>= 100 bytes each).
    Evidence: .sisyphus/evidence/chunk-9-evidence-inventory.txt (this file's output)
  ```

  **Commit**: YES (commit 3 with boulder update).

---

- [x] T13. **Run gate against running container, capture pasted outputs**

  **What to do**:
  - Confirm the backend container is running: `docker compose ps backend`.
  - Run `make validate-migration` from `/opt/flowmanner`. Capture full stdout/stderr.
  - Run `docker compose exec -T backend alembic current` and `alembic heads`. Confirm they match (no migration in this chunk).
  - Run the substrate regression: `docker compose exec backend pytest /app/tests/test_substrate_replay.py -q`. Expect 27 pass.
  - Run the new tests: `docker compose exec backend pytest /app/tests/test_validate_migration_gate.py -v --tb=short`. Expect 5 pass.
  - Run the full backend pytest (tail only): `docker compose exec backend pytest -q 2>&1 | tail -10`. Expect 164+ pass, 3 pre-existing failures, no NEW failures.
  - Run the health check: `curl -fsSL http://127.0.0.1:8000/health`. Expect 200 OK.
  - All outputs go into the T12 evidence file.
  - If any check fails: STOP, fix the underlying issue (not by papering over with `try/except: pass`), re-run.

  **Must NOT do**:
  - Do not paper over failures.
  - Do not skip the substrate regression.
  - Do not run the full backend pytest to completion (just the tail).

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Multi-command orchestration; needs to recognize failure modes.
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T7, T8, T9, T10, T11, T12)
  - **Parallel Group**: Wave 3 (after T12)
  - **Blocks**: T14
  - **Blocked By**: T7, T8, T9, T10, T11, T12

  **References**:
  - `.hermes/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md:366-404` — exact commands to run.
  - `.sisyphus/plans/substrate-baseline-v1.md:18-32` — canonical command for the full baseline.

  **Acceptance Criteria**:
  - [ ] All commands in T13 ran without error.
  - [ ] Substrate regression: 27 pass.
  - [ ] New tests: 5 pass.
  - [ ] Alembic head unchanged.
  - [ ] Health endpoint returns 200.
  - [ ] Outputs pasted into T12's evidence file.

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: All stop-gate commands pass
    Tool: Bash (sequential)
    Preconditions: T13 setup complete
    Steps:
      1. make validate-migration; echo "EXIT=$?"
      2. docker compose exec -T backend alembic current
      3. docker compose exec -T backend alembic heads
      4. docker compose exec backend pytest /app/tests/test_substrate_replay.py -q 2>&1 | tail -3
      5. docker compose exec backend pytest /app/tests/test_validate_migration_gate.py -v --tb=short 2>&1 | tail -10
      6. docker compose exec backend pytest -q 2>&1 | tail -10
      7. curl -fsSL http://127.0.0.1:8000/health
    Expected Result: All steps succeed; 27 + 5 pass; same alembic head; 200 OK.
    Evidence: .sisyphus/evidence/chunk-9-lenient-gate-valid.txt (T12's file)
  ```

  **Commit**: NO (already in commit 2 + 3; this is verification).

---

- [x] T14. **Update `.sisyphus/boulder.json` — chunk 9 entry**

  **What to do**:
  - Read `.sisyphus/boulder.json` and find the boulder entries (it's a list of chunks).
  - Add a new entry for chunk 9 with:
    - `id`: "q2-q3-chunk-9-lenient-validation-gate"
    - `name`: "Lenient validation gate (snapshot diff)"
    - `status`: "complete" (if all T13 checks pass) or "complete-with-bugfix-by-orchestrator" (if any task required a workaround — most chunks end up here per the handoff's prior pattern).
    - `chunks_completed_at`: today's date (ISO 8601).
    - `evidence_files`: list of paths to T12's evidence files.
    - `test_summary`: `{ "validate_migration_gate": "5 passed", "substrate_replay": "27 passed", "pre_existing_failures": 3 }`.
    - `plan_path`: ".sisyphus/plans/q2-q3-chunk9-lenient-validation-gate-prompt.md".
  - Verify the JSON is valid after the edit: `python3 -c "import json; json.load(open('.sisyphus/boulder.json')); print('OK')"`.

  **Must NOT do**:
  - Do not remove or modify existing entries.
  - Do not invent fields not present in other entries.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: JSON append + verify.
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T12, T13)
  - **Parallel Group**: Wave 3 (LAST)
  - **Blocks**: F1–F4
  - **Blocked By**: T12, T13

  **References**:
  - `.sisyphus/boulder.json` — read first; match the schema of existing entries.
  - `.sisyphus/plans/OLD/q2-q3-agentic-workflow.md` (or its current location) — chunk status conventions.

  **Acceptance Criteria**:
  - [ ] `.sisyphus/boulder.json` has a new chunk 9 entry.
  - [ ] `python3 -c "import json; json.load(open('.sisyphus/boulder.json'))"` exits 0.
  - [ ] `status` is `complete` or `complete-with-bugfix-by-orchestrator` (not `pending`, not `in-progress`).

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Boulder JSON is valid and has new entry
    Tool: Bash (python -c)
    Preconditions: T14 complete
    Steps:
      1. python3 -c "import json; d = json.load(open('.sisyphus/boulder.json')); assert any('chunk-9' in str(e) or 'lenient' in str(e).lower() for e in (d if isinstance(d, list) else d.get('chunks', []))); print('OK')"
    Expected Result: stdout "OK".
    Evidence: .sisyphus/evidence/chunk-9-boulder-updated.txt
  ```

  **Commit**: YES (commit 3).

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
>
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1–F4 as checked before getting user's okay.** Rejection or user feedback → fix → re-run → present again → wait for okay.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command, curl endpoint). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `ruff check backend/scripts/ backend/tests/test_validate_migration_gate.py` + `pytest /app/tests/test_validate_migration_gate.py -v`. Review all changed files for: `as any`/`@ts-ignore`-style `type: ignore`, empty catches, `print()` in production paths, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names (data/result/item/temp).
  Output: `Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration: snapshot script produces JSON that diff-helper reads, diff output flows into gate exit code, gate's exit code controls deploy-backend.sh's behavior. Test edge cases: missing snapshot file, malformed JSON, empty model metadata. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (`git log --stat -p HEAD~N..HEAD` or `git diff HEAD~N..HEAD -- backend/scripts/ scripts/ Makefile deploy-backend.sh backend/tests/ .sisyphus/boulder.json`). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination: Task N touching Task M's files. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Commit 1** (after Wave 1): `chore(deps): add snapshot script + diff helper for lenient validation gate` — `backend/scripts/snapshot_model_metadata.py`, `backend/scripts/snapshot_diff.py`. (No deploy needed — script is not yet wired in.)
- **Commit 2** (after Wave 2 + baseline generation): `feat(gate): replace alembic check with snapshot diff; commit baseline` — `scripts/validate-migration.sh`, `Makefile`, `deploy-backend.sh`, `backend/scripts/model_snapshot.json`. **REBUILD + DEPLOY** (backend + frontend scripts change) before commit 2 lands.
- **Commit 3** (after Wave 3): `test(gate): add lenient validation gate tests; update boulder` — `backend/tests/test_validate_migration_gate.py`, `.sisyphus/boulder.json`.
- **Push to origin/main** at end of session per SESSION-RITUAL rule.

Per `AGENTS.md` rule 3: "**Frontend deploy:** `bash /opt/flowmanner/deploy-frontend.sh`" — N/A, this is a backend-only chunk.
Per `AGENTS.homelab.md` rule 4: "**Backend rebuild:** `bash /opt/flowmanner/deploy-backend.sh`" — use this for the rebuild between commit 2 and commit 3.

---

## Success Criteria

### Verification Commands

```bash
# 1. The gate (headline win)
make validate-migration
# Expected: PASSED. Step 1 silent. Step 2 passes.

# 2. Snapshot idempotency
make snapshot-refresh
git diff backend/scripts/model_snapshot.json
# Expected: empty diff

# 3. Drift catch
# (manual: add `foo: Mapped[str] = mapped_column(String(50))` to a model,
#  do NOT regenerate snapshot, run gate, observe failure, revert model change)
make validate-migration
# Expected: exit 1, error names the introduced column

# 4. New tests
docker compose exec backend pytest /app/tests/test_validate_migration_gate.py -v --tb=short
# Expected: 4+ tests pass

# 5. Substrate regression (chunk 7 anchor)
docker compose exec backend pytest /app/tests/test_substrate_replay.py -q
# Expected: 27 pass (unchanged)

# 6. Alembic head unchanged
docker compose exec -T backend alembic current
docker compose exec -T backend alembic heads
# Expected: both match the same revision

# 7. Full backend suite tail
docker compose exec backend pytest -q 2>&1 | tail -10
# Expected: 164+ pass, 3 pre-existing failures, no NEW failures

# 8. Health
curl -fsSL http://127.0.0.1:8000/health
# Expected: 200 OK
```

### Final Checklist

- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass (new + substrate baseline)
- [ ] Evidence file contains pasted outputs, not summaries
- [ ] `pre_existing_drift_inventory.txt` exists with categorized 559 items
- [ ] `make snapshot-refresh` is idempotent
- [ ] `make validate-migration` is silent on the 559 items
- [ ] `make validate-migration` fails on a freshly introduced column
- [ ] `deploy-backend.sh` uses the same snapshot-diff logic
- [ ] `git diff --check HEAD~N..HEAD` clean
- [ ] `.sisyphus/boulder.json` updated
- [ ] Pushed to origin/main
