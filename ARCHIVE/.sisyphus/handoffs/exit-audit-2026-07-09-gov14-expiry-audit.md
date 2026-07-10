# Exit Audit — GOV-1.4 (expiry-as-decision audit)

**Date:** 2026-07-09 | **Machine:** homelab `/opt/flowmanner/backend` | **Agent:** Codex
**Continued from:** `.sisyphus/handoffs/exit-audit-2026-07-09-gov13c-retroactive-store-sweep.md`
**Backend status:** Glenn reported "Backend deployed ok!" for the prior (1.3c) state.
**This session:** source-only change (6 `.py` files) → committed `4fa031b2` → pushed to `origin/main`. **NOT deployed** (human review per AGENTS.md).

---

## WHAT CHANGED (one bullet per file, what + why)

- `backend/app/models/memory_correction_models.py`: added `"review"` to `ALL_EVENT_TYPES` so the model CHECK constraint permits the new audit event type. Same commit as its migration (ritual rule 6).
- `backend/alembic/versions/20260709_gov14_memory_review_audit_event.py`: **NEW** migration extending `ck_memory_correction_event_event_type_valid` to include `review`. Rewritten this session to use raw `op.execute` DDL (the prior `batch_alter_table` + check-constraint form failed `alembic upgrade head --sql` with `TypeError: Additional arguments should be named <dialectname>_<argument>, got 'type_'`).
- `backend/app/services/memory/background_review_service.py`: added `_NoOpMemoryAudit` (default, records nothing — backwards compatible), `_MemoryCorrectionReviewAudit` (in-session sink writing a `review` `MemoryCorrectionEvent`), a `BackgroundReviewService.audit` attr, `decided_by: str = "user"` param on `resolve_pending_write`, and `_audit_review_decision()` wired into `resolve_pending_write`. Audit commits with the caller's txn (not fire-and-forget) because expiry/drain callers own the commit.
- `backend/app/services/hitl_service.py`: the MEMORY_APPROVAL expiry branch now injects `_MemoryCorrectionReviewAudit()` and calls `resolve_pending_write(..., decided_by="hitl_expiry")`, persisting expiry-as-decision. Still hardcodes `approve=False` (no auto-approve after 7 days) and never dispatches executor/resume signals (C4 satisfied).
- `backend/app/api/v1/hitl.py`: human approve/reject injects `_MemoryCorrectionReviewAudit()` before `resolve_pending_write` so the decision persists in the memory-domain trail.
- `backend/app/tests/test_memory_drain.py`: +5 tests (approve→review, reject→review, noop default no audit, expiry→review, never-auto-approve) and updated 2 C4 assertions to expect `decided_by="hitl_expiry"`. Total 36 in the run subset.

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- `__pycache__` for the migration regenerated; not committed (ignored).

## TESTS RUN + RESULT

```
$ .venv/bin/pytest app/tests/test_memory_drain.py app/tests/test_poison_scan.py app/tests/test_retroactive_memory_sweep.py -q
36 passed, 5 warnings in 2.91s
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
36 passed, 5 warnings in 2.91s
```

Pre-commit hooks on commit: trim trailing whitespace ✓, fix end of files ✓,
check yaml (skipped), check for added large files ✓, ruff ✓, ruff-format ✓,
mypy ✓, Detect hardcoded secrets ✓.

mypy note: one pre-existing error remains at `background_review_service.py:1072`
(the 1.7 reviewer-retry `last_exc`/TransportError vs TimeoutException — NOT
part of this change, left as-is per checkpoint).

## NEXT SESSION HANDOFF

GOV-1.4 (expiry-as-decision audit) is complete and pushed. C4 (no sweeper race,
auto-reject only) was already satisfied with no code change; C3 (audit path
persists) is now fixed: memory-approval expiry and human approve/reject both
write a durable `review` row to `memory_correction_events`, regardless of
`run_id` (inbox items have `run_id=None`). The migration + model change shipped
in one commit (`4fa031b2`). To deploy, Glenn runs
`bash /opt/flowmanner/deploy-backend.sh --migrate` (the migration must run
because it alters the CHECK constraint). Next backlog item after 1.4 is **1.5**
(threshold calibration) → **1.6** (close feedback→durable loop) → Epics 2-4.

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

- Untracked (gitignored, left for Glenn): `.sisyphus/handoffs/` docs, this audit file.
- No deletions made.

## END
