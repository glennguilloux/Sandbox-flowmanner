# Exit Audit — 2026-07-23

**Agent:** Buffy (moonshotai/kimi-k2.7-code)
**Project:** Flowmanner
**Date:** 2026-07-23
**Commits:**
- `52f45498` — feat(blueprints): add reliability blueprint and extend linter edge semantics
- `6ab4c8fb` — feat(blueprints): add circuit-breaker simulation blueprint

---

## What changed

### `backend/flowmanner-reliability-blueprint.yaml` (new)
- Added a production-style DAG blueprint implementing two reliability patterns:
  - **Self-healing run** — a flaky `sandbox` step is wrapped in a `retry` node with literal `maxRetries`/`backoffMs`, plus a `timeout` node that falls back to an `on_timeout` branch.
  - **Deadline-guarded long mission** — a top-level `timeout` bounds the whole DAG; on timeout a `condition` node routes to a "partial-results summarizer" instead of failing hard.
- Uses literal integers for `timeoutMs` so the linter's positive-integer check passes.
- Uses string conditions (`"true"`, `"false"`, `"on_timeout"`, `"default"`) as required by the DAG executor.
- Crash recovery is left to the replay engine (resume from `run_id`).

### `backend/scripts/lint_blueprints.py`
- Added `"timeout"` to `REQUIRED_NODE_CONFIG` with required key `timeoutMs`.
- Added `timeout` node value validation:
  - `timeoutMs` must be a positive integer (milliseconds).
  - `wrapped_node_id` is optional but, if present, must be a non-empty string.
- Added strategy-aware `validate_edge_semantics()`:
  - DAG `condition` edges must use literal `"true"` / `"false"` conditions.
  - Graph-strategy `condition` edges may still use template expressions or no condition.
  - `timeout` edges may use `"default"`, `"on_timeout"`, or no condition.
  - `validate_schema` edges may use `"default"`, `"on_invalid"`, or no condition.
  - `router` edges must have a non-empty condition (route id).
- Added structural validation for `timeout` nodes:
  - Must specify `config.wrapped_node_id` or have a default outgoing edge.
  - Should have an outgoing `"on_timeout"` edge.
- Added structural validation for DAG `condition` nodes:
  - Must have exactly one outgoing `"true"` edge.
  - Must have exactly one outgoing `"false"` edge.
  - The `"true"` and `"false"` edges must target different nodes.
- Fixed ruff `SIM102` warnings in the timeout/router validation paths and ran `ruff format`.

### `backend/tests/test_lint_blueprints.py`
- Added tests for `timeout` node config validation.
- Added `TestValidateEdgeSemantics` covering:
  - Valid condition/true/false branches routing.
  - Missing `false` branch detection.
  - Duplicate `true` branch detection.
  - Same-target `true`/`false` branch detection.
  - Timeout edge conditions (`"on_timeout"`, `"default"`, no condition).
  - Timeout structural requirements (wrapped_node_id / default edge, on_timeout edge).
- Added end-to-end test that lints the actual `flowmanner-reliability-blueprint.yaml`.

### `backend/docs/substrate-node-types-table.md`
- Regenerated; only change is `timeoutMs` now correctly marked as required (`R`).

### `backend/flowmanner-circuit-breaker-blueprint.yaml` (new)
- Added a DAG blueprint that simulates circuit-breaker semantics using existing node types.
- **Substrate gap analysis** (in `.sisyphus/analysis/2026-07-23-circuit-breaker-substrate-gap.md`) found:
  - No `circuit_breaker`, `lease_reclaim`, or `resume` node types exist.
  - The real circuit breaker is internal (`app/core/circuit_breaker.py` and `app/services/substrate/circuit_breaker.py`); it cannot be manipulated from a blueprint.
  - Lease reclamation runs as a Celery background thread; no cron/DB-admin node exists.
  - Resume validation is automatic in `UnifiedExecutor.execute`; no `resume`/`checkpoint` node exists.
  - **Most feasible option:** simulate the circuit breaker pattern within a single run.
- Blueprint structure:
  - `condition` node branches on `inputs['circuit_state'] == 'open'`.
  - `retry` node wraps a `sandbox` that performs the protected HTTP call and returns a structured `{success: bool}` payload.
  - On success: `variable_set` resets `failure_count` to 0 and `circuit_state` to `"closed"`, then logs.
  - On failure: `variable_set` increments `failure_count`, `condition` checks the threshold, and if reached the circuit is opened; logs and webhook alert fire.
  - Open branch: fail-fast log, `delay` cooldown, transition to `"half_open"`, then re-enters the protected call for a probe.
- Uses literal integers for `retry.maxRetries`, `retry.backoffMs`, and `delay.delayMs` (required by the linter/substrate).
- Uses valid Python subscript expressions in `condition`/`variable_set` (e.g. `inputs['failure_count'] >= inputs['failure_threshold']`).

---

## What did not change but was inspected

- No Alembic migrations were created or modified.
- No frontend source was changed.
- No deploy was attempted.
- `backend/app/services/substrate/node_executor.py` and `dag.py` were inspected to confirm handler config keys and branching semantics.

---

## Tests run + result

```
cd /opt/flowmanner/backend && python -m pytest tests/test_lint_blueprints.py tests/test_docs_drift.py -q
```

```
181 passed in 0.22s
```

```
cd /opt/flowmanner && make lint-blueprints
```

```
Scanning 10 YAML file(s) for blueprints...
✅ backend/flowmanner-ab-arena.yaml
✅ backend/flowmanner-cache-warmer.yaml
✅ backend/flowmanner-circuit-breaker-blueprint.yaml
✅ backend/flowmanner-institutional-memory.yaml
✅ backend/flowmanner-multi-repo-audit.yaml
✅ backend/flowmanner-rag-report.yaml
✅ backend/flowmanner-reliability-blueprint.yaml
✅ blueprints/auth-flow-tester.yaml
✅ blueprints/scrape-diff-alert.yaml
✅ blueprints/web-recon.yaml
All 10 blueprint(s) passed validation.
```

```
cd /opt/flowmanner/backend && python scripts/generate_node_type_table.py
```

```
Generated table matches committed table (no diff)
```

```
cd /opt/flowmanner/backend && ruff check scripts/lint_blueprints.py tests/test_lint_blueprints.py
```

```
All checks passed.
```

```
cd /opt/flowmanner/backend && ruff format --check scripts/lint_blueprints.py tests/test_lint_blueprints.py
```

```
All checks passed.
```

---

## Status

```
□ git status
```

```
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

```
□ git fetch origin && git log --oneline origin/main..main
```

```
(nothing — working branch is even with origin/main)
```

```
□ docker compose exec backend alembic current
```

Not run; no Alembic migrations were created or modified in this session.

```
□ docker compose exec backend bash -c "pytest -q"
```

Not run inside Docker; the relevant test subset was run directly against the backend directory and passed (181/181).

---

## Next session handoff

The reliability blueprint, linter edge-semantics validation, and circuit-breaker simulation blueprint are now committed and pushed to `origin/main`. The linter now guards timeout-node config, edge conditions for condition/timeout/validate_schema/router nodes, and DAG condition-node branch structure. All 10 project blueprints pass validation and the linter/docs test suite is green (181 tests).

Potential next work:

1. **Add a dedicated `circuit_breaker` substrate node type** backed by the existing `circuit_breaker_state` table, so blueprints can share real circuit-breaker state across runs instead of simulating it per-run.
2. **Extend the linter** — e.g., validate that router nodes emit route ids matching their outgoing edge conditions, or that validate_schema nodes have both `default` and `on_invalid` branches.
3. **Run the full backend test suite in a properly provisioned environment** to separate pre-existing environment failures from real regressions.
4. **Deploy** — no deploy was attempted. Glenn can deploy manually after review.

---

## Files this agent did not touch but exist

- `.sisyphus/handoff/TODO-03.md` — still untracked; it described work already completed by earlier commits and was left as a stub.
- `.sisyphus/handoff/TODO-05.md` — the task list for the linter extension; left untracked.
