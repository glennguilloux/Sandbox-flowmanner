# F3 Final Verification Wave — Real Manual QA

Session: current F3 manual QA for chunk 9 lenient validation gate.
Evidence source commands were run from `/opt/flowmanner`; raw command captures are stored at:
- `/tmp/f3_manual_qa_results.json`
- `/tmp/f3_manual_qa_results_wrapper.json`

## Scenario 1 — snapshot script produces JSON that diff-helper reads

Command:

```bash
docker compose exec -T backend python /app/scripts/snapshot_model_metadata.py > /tmp/f3-qa-snapshot.json
docker compose exec -T backend python /app/scripts/snapshot_diff.py /tmp/f3-qa-snapshot.json /tmp/f3-qa-snapshot.json
```

Excerpt:

```text
snapshot_model_metadata.py: OK 134 tables, 67157 bytes baseline shape
snapshot_diff.py identical-input exit: 0
```

Result: PASS. The snapshot generator emits JSON and `snapshot_diff.py` reads it successfully.

## Scenario 2 — diff output flows into gate exit code

Simulated introduced drift used a non-destructive container-side `PYTHON_BIN` wrapper. It did not edit model files or committed snapshot JSON; it only changed the fresh snapshot generated for the validation run and was removed afterward.

Command:

```bash
PYTHON_BIN=/tmp/f3-python-wrapper.sh bash scripts/validate-migration.sh
```

Excerpt:

```text
>>> Step 1/2: snapshot diff (model/migration drift)
[FAIL]    Snapshot drift detected:
[FAIL]    + tables.users.columns.__qa_wrapper_introduced = VARCHAR(50) (added)
[FAIL]    If this drift is intentional, run 'make snapshot-refresh' to update the baseline.
script exit code: 1
```

Direct diff-helper check:

```text
+ tables.users.columns.__qa_single_introduced = VARCHAR(50) (added)
diff-helper exit code: 1
```

Result: PASS. Diff output is visible and maps to a failing validation gate.

## Scenario 3 — gate exit code controls `make validate-migration`

Missing snapshot path command:

```bash
SNAPSHOT_FILE=/tmp/f3-missing-snapshot.json make validate-migration
```

Excerpt:

```text
[FAIL]    Snapshot file not found: /tmp/f3-missing-snapshot.json
[FAIL]    Run 'make snapshot-refresh' to generate it, then commit the result.
make: *** [Makefile:211: validate-migration] Error 1
make exit code: 2
```

Introduced-drift command:

```bash
PYTHON_BIN=/tmp/f3-python-wrapper.sh make validate-migration
```

Excerpt:

```text
[FAIL]    Snapshot drift detected:
[FAIL]    + tables.users.columns.__qa_wrapper_introduced = VARCHAR(50) (added)
make: *** [Makefile:211: validate-migration] Error 1
make exit code: 2
```

Note: `make` reports exit code 2 when a recipe exits 1; the underlying validation script still exits 1.

Cleanup/green command:

```bash
make validate-migration
```

Excerpt:

```text
[OK]      No new drift since snapshot
[OK]      Offline render OK — 3713 lines / 146765 bytes
>>> Validation gate PASSED
make exit code: 0
```

Result: PASS. `make validate-migration` is controlled by the validation gate and returns green after cleanup.

## Scenario 4 — introduced drift fails and cleanup/gate green

Cleanup command:

```bash
docker compose exec -T backend sh -lc 'rm -f /tmp/f3-python-wrapper.sh'
```

Excerpt:

```text
f3_wrapper_absent
```

Post-cleanup gate:

```text
[OK]      No new drift since snapshot
[OK]      Offline render OK — 3713 lines / 146765 bytes
>>> Validation gate PASSED
```

Result: PASS. Simulated drift was cleaned up and the gate returned green.

## Scenario 5 — snapshot refresh idempotency

Commands:

```bash
make snapshot-refresh
make snapshot-refresh
git diff -- backend/scripts/model_snapshot.json
```

Excerpt:

```text
make snapshot-refresh exit code: 0
make snapshot-refresh exit code: 0
git diff -- backend/scripts/model_snapshot.json exit code: 0
git diff output: <empty>
```

Result: PASS. Snapshot refresh is idempotent.

## Scenario 6 — substrate regression

Command:

```bash
docker compose exec backend pytest /app/tests/test_substrate_replay.py -q
```

Excerpt:

```text
27 passed, 1 warning in 0.56s
```

Result: PASS.

## Scenario 7 — validation-gate tests

Command:

```bash
docker compose exec backend pytest /app/tests/test_validate_migration_gate.py -v --tb=short
```

Excerpt:

```text
tests/test_validate_migration_gate.py::test_snapshot_file_exists_and_is_valid_json PASSED
tests/test_validate_migration_gate.py::test_snapshot_matches_current_metadata PASSED
tests/test_validate_migration_gate.py::test_snapshot_diff_catches_introduced_column PASSED
tests/test_validate_migration_gate.py::test_step_2_offline_render_still_works SKIPPED
tests/test_validate_migration_gate.py::test_snapshot_diff_silent_on_identical PASSED
4 passed, 1 skipped, 1 warning in 2.28s
```

Result: PASS. The skipped test is the container-side Docker integration skip already present in the test.

## Scenario 8 — health endpoint

Command:

```bash
curl -fsSL http://127.0.0.1:8000/health
```

Excerpt:

```json
{"status":"ok","app":"workflows-backend","env":"production","components":{"database":{"status":"ok"},"redis":{"status":"ok"},"langfuse":{"status":"healthy"},"llm_provider":{"status":"healthy"}}}
```

Result: PASS.

## Integration checks

1. Snapshot script -> diff helper: PASS.
2. Diff helper -> validation script exit code: PASS.
3. Validation script -> `make validate-migration`: PASS.
4. Deploy script dry-run -> shared validation command: PASS.

Deploy dry-run excerpt:

```text
>>> Migration validation gate (snapshot diff + offline SQL render)
[DRY-RUN] bash /opt/flowmanner/scripts/validate-migration.sh
[DRY-RUN]   snapshot diff + offline SQL render
```

## Edge cases tested

### Missing snapshot path

Command:

```bash
SNAPSHOT_FILE=/tmp/f3-missing-snapshot.json make validate-migration
```

Excerpt:

```text
[FAIL]    Snapshot file not found: /tmp/f3-missing-snapshot.json
```

Result: tested.

### Malformed JSON

Command:

```bash
docker compose exec -T backend python /app/scripts/snapshot_diff.py /tmp/f3-qa-malformed.json /tmp/f3-qa-new.json
```

Excerpt:

```text
snapshot diff error: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
exit code: 2
```

Result: tested.

### Empty model metadata

Command:

```bash
docker compose exec -T backend python /app/scripts/snapshot_diff.py /tmp/f3-qa-empty_old.json /tmp/f3-qa-empty_new.json
```

Excerpt:

```text
exit code: 0
```

Result: tested.

## Additional plan stop-gates rechecked

### Backend container

```text
backend   workflows-backend:restored   Up 2 hours (healthy)
```

### Alembic current/heads

```text
alembic current: handoff_packets_001 (head)
alembic heads:   handoff_packets_001 (head)
```

### Direct validation script green

```text
[OK]      No new drift since snapshot
[OK]      Offline render OK — 3713 lines / 146765 bytes
>>> Validation gate PASSED
```

### Full backend pytest tail

Command run:

```bash
docker compose exec backend pytest -q
```

Result: still blocked by inherited legacy suite failures. Representative tail:

```text
E       AttributeError: 'FastAPI' object has no attribute 'response_class'

/opt/venv/lib/python3.11/site-packages/pytest_flask/plugin.py:77: AttributeError
```

This blocker was documented and does not mask the chunk-specific QA results above.

## Temporary file cleanup and working-tree check

Container cleanup check:

```text
f3_wrapper_absent
```

Key-path status check:

```text
 M backend/app/models/__init__.py
?? .sisyphus/evidence/final-qa/
?? backend/app/models/__main__.py
```

No `backend/scripts/model_snapshot.json` diff was reported after snapshot refresh. F3 simulated drift used only container temp files and was removed.

## Final verdict line

Scenarios [8/8 pass] | Integration [4/4] | Edge Cases [3 tested] | VERDICT: APPROVE
