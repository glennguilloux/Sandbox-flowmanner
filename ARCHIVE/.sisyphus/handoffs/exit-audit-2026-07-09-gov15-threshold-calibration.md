# Exit Audit — GOV-1.5 (threshold calibration instrumentation)

**Date:** 2026-07-09 | **Machine:** homelab `/opt/flowmanner/backend` | **Agent:** Codex
**Continued from:** `.sisyphus/handoffs/exit-audit-2026-07-09-gov14-expiry-audit.md`
**This session:** source-only change (5 `.py` files) → committed `4c749aba` → pushed
to `origin/main`. **NOT deployed** (human review per AGENTS.md).
**Note:** the "Item #5 calibration" handoff from 2026-07-08 is the UNRELATED
plan-selection calibration (`.sisyphus/handoffs/exit-audit-2026-07-08-item5-calibration-item7-oidc-webhooks.md`),
NOT this memory GOV-1.5. Memory GOV-1.5 was genuinely unstarted.

---

## WHAT CHANGED (one bullet per file, what + why)

- `backend/app/services/memory/extraction_thresholds.py` (NEW): GOV-1.5
  calibration knobs. `MEMORY_EXTRACTION_MIN_CONFIDENCE = 0.85` (env-overridable
  via `MEMORY_EXTRACTION_MIN_CONFIDENCE` so it can be recalibrated from
  telemetry without a code change). `TRUSTED_DIRECT_WRITE_SOURCES`,
  `is_trusted_direct_write()`, `passes_confidence_gate()`. The gate is
  **scoped to the trusted direct-write path only** — it must never be
  consulted to de-escalate an externally-derived claim (GOV-1.2 invariant).
- `backend/app/services/chat_service.py` (`_maybe_extract_memory_claims`):
  - C5 fix: dropped (defensive-filter) candidates are now logged with their
    `confidence` score, `claim_type`, `scope`, `subject`, `predicate`, plus a
    summary line with the drop rate. Previously they were dropped silently,
    so the 0.85 gate could never be calibrated from real data.
  - Trusted direct-write path (`user_explicit`) now holds low-confidence
    claims (below the calibrated floor) for human approval instead of writing
    them directly — tagged `metadata.held_reason="confidence_below_gate"`.
    Untrusted sources (`conversation`/`mission`/`program_learning`) are
    NEVER affected by this gate — they still route to approval via the
    provenance policy, regardless of score.
- `backend/app/core/metrics.py` (`record_memory_extraction`): added a
  `claims_dropped` arg + a new `dropped` Prometheus disposition so the drop
  rate is measurable against raw extraction volume (separate from `filtered`,
  which counts per-claim create/stage failures).
- `backend/app/services/personal_memory_extractor.py`: added `source_type`
  field to `CandidateClaim` (defaults to `"conversation"`) so the GOV-1.5
  gate can scope itself to the trusted path. Also moved `Callable` import
  into a `TYPE_CHECKING` block (pre-existing ruff `TCH003` that now surfaces
  because this file is part of the committed diff).
- `backend/app/tests/test_memory_extraction_calibration.py` (NEW): 8
  sandbox-safe (no-DB, all I/O mocked) tests — default gate=0.85, env
  override, boundary, only-`user_explicit`-is-trusted, trusted-low-confidence
  held for approval, trusted-high-confidence direct write, untrusted-never-
  deescalated-by-confidence (GOV-1.2 invariant), defensive-drop logged+counted.

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- No Alembic migration (no schema change). `alembic heads` unchanged:
  `20260709_gov14_memory_review_audit_event`.

## TESTS RUN + RESULT

```
$ .venv/bin/pytest app/tests/test_memory_extraction_calibration.py \
    app/tests/test_memory_drain.py app/tests/test_poison_scan.py \
    app/tests/test_retroactive_memory_sweep.py -q
44 passed, 6 warnings in 2.98s
```

## STATUS (raw output)

```
□ git status
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean

□ git fetch origin && git log --oneline origin/main..main
(empty = pushed)

□ alembic heads
20260709_gov14_memory_review_audit_event (head)

□ pytest tail
44 passed, 6 warnings in 2.98s
```

Pre-commit hooks on commit: trim trailing whitespace ✓, fix end of files ✓,
check yaml (skipped), check for added large files ✓, ruff ✓, ruff-format ✓,
mypy ✓, Detect hardcoded secrets ✓.

mypy note: one pre-existing type error at `chat_service.py:2114`
(`AsyncCompletions.create` messages arg-type) exists at HEAD too; the
pinned pre-commit mypy (`--follow-imports=silent`) does not flag it on
changed files (consistent with prior commit `4fa031b2`). Not introduced by
this change.

## NEXT SESSION HANDOFF

GOV-1.5 (threshold calibration instrumentation) is complete and pushed.
The 0.85 confidence gate now exists and is **calibrate-able at runtime**
(`MEMORY_EXTRACTION_MIN_CONFIDENCE`) with full telemetry: dropped candidates
are logged with scores and counted in a new `dropped` metric disposition.
Critically, the gate is applied ONLY to the trusted `user_explicit`
direct-write path — externally-derived claims are never de-escalated by
confidence, preserving the GOV-1.2 provenance invariant. **Calibration
next step (for Glenn/next session):** watch the `dropped` metric and the
`memory_extraction: dropped (defensive filter)` / `held for approval below
confidence gate` log lines in production, then tune `MEMORY_EXTRACTION_MIN_CONFIDENCE`
from real drop-rate data without a deploy. No migration required.

Next backlog item after 1.5 is **1.6** (close feedback→durable loop — wiring
not building, per C3) → Epics 2-4.

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

- Untracked (gitignored, left for Glenn): `.sisyphus/handoffs/` docs, this
  audit file.
- No deletions made.

## END
