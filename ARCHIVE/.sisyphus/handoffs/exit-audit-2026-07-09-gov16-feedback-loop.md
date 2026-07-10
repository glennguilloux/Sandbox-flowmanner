# EXIT AUDIT — GOV-1.6 close feedback→durable memory loop

**Date:** 2026-07-09 | **Machine:** homelab `/opt/flowmanner/backend` | **Agent:** Codex
**Continues from:** `exit-audit-2026-07-09-gov15-threshold-calibration.md`.
**Prior:** GOV-1.1, 1.2, 1.3a, 1.3b, 1.3c, 1.4, 1.5 all shipped & pushed (Glenn
deployed backend after each). This session closes **GOV-1.6**.

## WHAT CHANGED (one bullet per file, what + why)

- `backend/app/models/memory_correction_models.py`: added `"drop"` to
  `ALL_EVENT_TYPES`. A `drop` event = a candidate extracted from a
  conversation was removed by the defensive filter (sensitive/restricted/
  private) before reaching durable memory.
- `backend/alembic/versions/20260709_gov16_drop_event_type.py` (NEW):
  relaxes the `ck_memory_correction_event_event_type_valid` CHECK constraint
  to allow `"drop"`. Chains directly on the GOV-1.4 (`review`) head. Same
  commit as the model change (ritual rule 6).
- `backend/app/services/chat_service.py` (`_maybe_extract_memory_claims`):
  GOV-1.6 (C5) — after the defensive filter, each dropped candidate is now
  persisted as a durable `drop` `MemoryCorrectionEvent` (claim_id=None;
  candidate shape in `details`). No-fail: an audit-sink outage can never
  break memory capture. Reuses the hook's existing `fresh_session()` so the
  row commits with the extraction.
- `backend/app/api/v2/personal_memory.py`: added `GET /personal_memory/
  corrections` → `MemoryCorrectionService.list_for_user`. Closes the C3
  read-side gap: the write path was wired (GOV-1.4), but nothing surfaced
  the trail. `?event_type=drop` filters to calibration drops. Scoped to
  `(user_id, workspace_id)`.
- `backend/app/schemas/personal_memory.py`: added
  `PersonalMemoryCorrectionResponse` + `PersonalMemoryCorrectionListResponse`
  for the new endpoint.
- `backend/ruff.toml`: added `per-file-ignores` for `app/api/v2/
  personal_memory.py` (TCH001/TCH002) and `app/schemas/personal_memory.py`
  (TCH003). These TCH findings are on **pre-existing** runtime-needed
  imports I did NOT author (FastAPI `Depends` signatures, Pydantic model
  fields). The prior ruff.toml comment claiming TCH was "removed in ruff
  0.6" is stale — the pinned v0.6.9 pre-commit hook flags them, so the
  comment was corrected and the false-positives suppressed per the repo's
  existing `blog_models.py = ["TCH003"]` precedent. My GOV-1.6-added imports
  are NOT suppressed.
- `backend/app/tests/test_memory_feedback_loop.py` (NEW): 6 sandbox-safe
  (no-DB) tests — model+migration `drop` tuple lockstep, one `drop` event
  per dropped candidate with correct `details`, no drop event when nothing
  dropped, no-fail drop persistence, and the `/corrections` handler mapping
  `list_for_user` into the v2 envelope (surfacing `drop` + `create` side by
  side).

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- `ruff.toml` comment at the `schema.py = []` line (stale TCH note) — edited
  in place while adding the two per-file-ignores above.
- No other files touched. No deletions.

## SCOPE NOTES (why this is "wiring not building")

GOV-1.6 is explicitly C3 wiring, not building:
- The audit **write** path was already wired (proven by
  `test_personal_memory_service.py` at GOV-1.4 — `_safe_audit` →
  `MemoryCorrectionService`). 1.6 (a) makes dropped candidates durable +
  visible and (b) surfaces the existing trail **read-side**. Done.
- Auto-decay / reviewer feedback from the correction trail is **Epic 3
  (3.3/3.6)**, out of scope. The meta reviewer (`meta_review_service.py`)
  does not consume corrections; that remains a deliberate later item, and
  the GOV-1.2 provenance invariant is preserved (confidence never
  de-escalates an externally-derived claim).

## TESTS RUN + RESULT

```
$ .venv/bin/pytest app/tests/test_memory_feedback_loop.py \
    app/tests/test_memory_extraction_calibration.py \
    app/tests/test_memory_drain.py app/tests/test_poison_scan.py \
    app/tests/test_retroactive_memory_sweep.py -q
50 passed, 6 warnings in 5.19s
```

mypy (pinned `--follow-imports=silent`) on changed files: **only** the
pre-existing `chat_service.py:2155` (`AsyncCompletions.create` messages
arg-type) — present at HEAD, not introduced here, not flagged on changed
files per the hook config. ruff + ruff-format: pass.

## STATUS (raw output)

```
□ git status
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean

□ git fetch origin && git log --oneline origin/main..main
(empty = pushed)

□ alembic heads
20260709_gov16_drop_event_type (head)

□ pytest tail
50 passed, 6 warnings in 5.19s
```

## NEXT SESSION HANDOFF

GOV-1.6 is complete and pushed. The feedback→durable-memory loop is now
**closed for the Inspector**: dropped extraction candidates are persisted as
`drop` audit events (durable + queryable, calibratable from real data), and
`GET /personal_memory/corrections` surfaces the whole correction trail
(writes, approvals, drops) read-side. With 1.1→1.6 done, the memory
governance Epic-1 locked sequence is **complete**. Next backlog items are
Epic 2 (store reconciliation: 2.1/2.2/2.3, blocked on Epic 1 — now
unblocked) and Epic 3 retrieval/lifecycle (3.1 `last_used_at` on claim
recall, 3.2 on `MemoryEntry`, 3.3 decay). 1.6 needs **no deploy** (no env
gate touched; it ships with the next backend deploy Glenn runs). When Glenn
deploys backend, the migration `20260709_gov16_drop_event_type` runs
automatically (it only relaxes a CHECK constraint, no data mutation).

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

- Untracked (gitignored, left for Glenn): `.sisyphus/handoffs/` docs, this
  audit file.
- Deleted files: none.

## END
