# Exit Audit — 2026-06-26: Dual-Write Reliability, Verifier Fix, Backfill

## TL;DR

**Dual-write is now reliable.** All 5 dual-write sites refactored with retry + structured logging,
verifier fixed, 70 orphaned missions backfilled to 100% parity, Prometheus counter added.

Commits: `5964c61` + `3ae7197` on `main`. Both pushed to origin.

---

## What was done

### 1. DB Identity Confirmation

Confirmed the DB is production config (`APP_ENV=production`, `workflow-postgres` container)
but contains only dev/test data (71 missions with titles like "Sandboxd Smoke Test",
"cons-placeholder"). No separate production DB exists.

### 2. Dual-Write Dissection

Traced the complete dual-write code path:

- `commands.py::_dual_write_blueprint` — fire-and-forget, opens own session via
  `AsyncSessionLocal()`, creates Blueprint with `definition={"_source_mission_id": str(mission.id)}`
- `compat.py::dual_write_sync_run_status` — updates Run status on mission mutation
- `compat.py::dual_write_sync_blueprint` — updates Blueprint fields on mission update
- `compat.py::dual_write_soft_delete_blueprint` — soft-deletes Blueprint on mission deletion

**Finding:** 70/71 missions had NO blueprint. The dual-write was silently failing — bare
`try/except` caught everything and logged at WARNING with no structured context.

### 3. `_run_with_retry` Helper (base.py)

Added reusable retry helper:
- 3 attempts, exponential backoff (1s → 2s, capped at 30s)
- Structured logging via structlog: WARNING on retry, ERROR on final failure
- Context fields: `operation`, `mission_id`, `user_id`, etc.
- Prometheus counter `dual_write_failures_total{site}` incremented on final failure
- Never re-raises (CancelledError propagates naturally)

### 4. All 5 Dual-Write Sites Refactored

- `commands.py::_dual_write_blueprint` — uses `_run_with_retry(_op, operation="create_blueprint", ...)`
- `commands.py::_dual_write_run` — uses `_run_with_retry(_op, operation="create_run", ...)` (**fixed in 3ae7197**)
- `compat.py::dual_write_sync_run_status` — uses `_run_with_retry(_op, operation="sync_run_status", ...)`
- `compat.py::dual_write_sync_blueprint` — uses `_run_with_retry(_op, operation="sync_blueprint", ...)`
- `compat.py::dual_write_soft_delete_blueprint` — uses `_run_with_retry(_op, operation="soft_delete_blueprint", ...)`

### 5. Verifier Fix (prove_dual_write_complete.py)

**Bug:** Verifier checked `Mission.id == Blueprint.id` (direct ID equality) but
`BlueprintService.create()` generates fresh `uuid4()` IDs — so `matched_by_id` was always 0.

**Fix:** Now fetches ALL non-deleted blueprints, indexes by `_source_mission_id` (primary)
and direct ID (secondary), matches missions via `_source_mission_id` first.

### 6. Backfill Script (backfill_dual_write.py)

Created idempotent backfill script:
- Finds missions without a `_source_mission_id`-linked blueprint
- Creates blueprints with `uuid4()` IDs (matching dual-write behavior)
- Creates Run records for missions with execution results
- Creates BlueprintVersion snapshots
- Supports `--dry-run` and `--batch-size`

**Ran against live DB:** 70 blueprints + 64 runs created. Verifier confirms 100% parity.

### 7. Prometheus Counter (metrics.py)

Added `flowmanner_dual_write_failures_total{site}` counter to `app/core/metrics.py`.
Verified it appears in `/metrics` endpoint output.

### 8. Metrics Summary (observability.py)

Added `dual_write.failures` parsing to `/observability/metrics-summary` endpoint,
keyed by `site` label.

### 9. Tests

- **12 new unit tests** for `_run_with_retry` (`test_run_with_retry.py`):
  first-try success, all-fail, fail-then-succeed, CancelledError propagation,
  custom max_attempts, log context, exponential backoff, delay cap, never-raises,
  return value, error truncation
- **Rewrote B4 tests** to use `structlog.testing.capture_logs` (project uses
  PrintLoggerFactory, not stdlib integration — `caplog` can't capture structlog)
- **Fixed lifecycle tests** — moved captured coroutine awaiting inside `with` blocks
  so patches are active when dual-write code runs
- All 15 dual-write tests pass

---

## Commits

```
5964c61 feat(dual-write): retry with structured logging, verifier fix, backfill, and Prometheus counter
3ae7197 fix(dual-write): refactor _dual_write_run to use _run_with_retry
```

Both pushed to origin/main. All pre-commit hooks passed.

---

## Files modified

| File | Change |
|------|--------|
| `backend/app/api/_mission_cqrs/base.py` | Added `_run_with_retry` helper + Prometheus import |
| `backend/app/api/_mission_cqrs/commands.py` | `_dual_write_blueprint` + `_dual_write_run` both use `_run_with_retry` |
| `backend/app/api/_mission_cqrs/compat.py` | All 3 `dual_write_*` functions use `_run_with_retry` |
| `backend/app/core/metrics.py` | Added `dual_write_failures_total` counter |
| `backend/app/api/v1/observability.py` | Added dual_write failures to metrics-summary |
| `backend/scripts/prove_dual_write_complete.py` | Fixed to use `_source_mission_id` linkage |
| `backend/scripts/backfill_dual_write.py` | **NEW** — idempotent backfill script |
| `backend/tests/test_run_with_retry.py` | **NEW** — 12 unit tests for `_run_with_retry` |
| `backend/tests/test_dual_write_failure_logged_at_warning_b4.py` | Rewritten for structlog |
| `backend/tests/integration/test_blueprint_run_lifecycle.py` | Fixed coroutine awaiting |

---

## Status

- ✅ Both commits pushed to `origin/main`.
- **Don't rebuild/deploy yet.** Awaiting deploy decision.
- **The backfill has already been run** against the live DB. Don't re-run it — it's
  idempotent so re-running is safe but unnecessary.

---

## Next session priorities

1. **Deploy** the backend after review (`bash deploy-backend.sh`).
2. **Monitor `dual_write_failures_total`** in Prometheus after deploy — if it spikes,
   the retry mechanism is catching real failures.
3. **`mypy [valid-type]` at `run_service.py:287`** is a pre-existing issue unrelated to
   this session — needs a separate fix.

---

## Test verification

```
tests/test_run_with_retry.py                          12 passed
tests/test_dual_write_failure_logged_at_warning_b4.py  3 passed
tests/integration/test_blueprint_run_lifecycle.py       4 passed (dual_write subset)
────────────────────────────────────────────────────────────────────
Total                                                  19 passed
```

---

## Parity verification (post-backfill)

```
Missions live: 71
Blueprints live: 86 (16 original + 70 backfilled)
Matched by _source_mission_id: 71
Orphan missions: 0
Parity: 100.0%
Verdict: PASS
```
