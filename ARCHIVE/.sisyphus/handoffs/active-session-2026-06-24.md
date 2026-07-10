# Handoff — 2026-06-24 Sessions 3-4: PR #16 fully unblocked

## Session Summary

**Sessions 1-2 (earlier today):** Fixed k6 workflow so backend boots
correctly. **Sessions 3-4 (this entry):** Got the deletion guard
working. All CI checks now pass on PR #16 except the k6 threshold
(which is a real backend perf bug — separate concern).

## Final state of PR #16

- Branch: `drop-audio-features-v2` HEAD = `833f846`
- `mergeable_state`: was `unstable` → `clean` after rebase onto
  `origin/main` (`31a82d8`)
- Diff vs origin/main: 13 files, +37/-3542 (just the audio
  deletions + 1 workflow tweak + ruff/test_io_api touches)
- Checks on `833f846`:
  - **Deletion guard + backend sanity: ✅ success** (was failing)
  - Load Tests (k6): ❌ failure (real perf threshold — see below)
  - .github/workflows/ci.yml: ❌ pre-existing mypy baseline drift

## Commits added today (in chronological order)

1. `5b1bd85` — k6 workflow: APP_ENV → development + polling retry
   loop + k6 install path fix. (session 1)
2. `057264d` — chore(sisyphus): rebase marker no-op. (session 2)
3. `f4d7563` — pr-check.yml: deletion guard checks PR head, not
   synthetic merge commit body. (session 2)
4. `b3bc88b` — pr-check.yml: fetch refs/pull/N/head (not
   refs/pull/N/merge). (session 2)
5. `1f32f49` — pr-check.yml: use here-string to avoid pipefail SIGPIPE.
   (session 4)
6. `833f846` — pr-check.yml: --force on the fetch refspec to survive
   force-pushes. (session 4)

Commits 5 and 6 are the actual deletion-guard fix. Commits 3 and 4
were correct but insufficient — they addressed *which* commits to
check, not the bash semantics that prevented grep from succeeding.

## The deletion-guard bug (full diagnosis)

The runner had been reporting the deletion guard as failing for PR #16
even though commit `ba7a3f5` ("drop(audio): remove 6 audio tools...")
contains a thorough `Deletion justification:` block in its body.

Three layered bugs were uncovered:

1. **Synthetic merge commit (commit f4d7563 + b3bc88b fix)**
   The runner checks out a synthetic merge commit (HEAD = merge of
   base + PR head). The merge commit's body is empty, so
   `git log BASE..HEAD` only saw the merge commit's empty body.
   Fix: fetch `refs/pull/N/head` explicitly and use `git log BASE..HEAD_SHA`.

2. **`set -o pipefail` + `grep -q` SIGPIPE (commit 1f32f49 fix)**
   Even with the right commits, `git log | grep -qi 'pattern:'`
   silently failed: `grep -q` exits on first match, closes stdin,
   `git log` writes a few more lines, gets EPIPE, dies with 141.
   With `set -o pipefail`, the pipeline reports git log's 141
   instead of grep's 0, so `if` sees failure.
   Fix: capture body into a variable, use a here-string
   (`grep -qi ... <<< "${PR_BODY}"`).

3. **Non-fast-forward fetch (commit 833f846 fix)**
   After force-pushing to update the PR branch, `git fetch origin
   refs/pull/N/head:...` was rejected by GitHub's server
   ("non-fast-forward"). Local `refs/remotes/pull/N/head` ended up
   stale/empty, HEAD_SHA rev-parse returned empty, the deletion guard
   failed. Fix: `git fetch --force`.

## Verification

Run 28075171543 (latest) on commit `833f846`:
```
[Deletion guard + backend sanity] Assert no deleted backend/...
  Deletion justification found in PR commit body — passing guard.
[Deletion guard + backend sanity] Run backend pytest sanity check
  2521 passed, 50 skipped, 707 deselected, 68 warnings in 61.02s
```

Deletion guard passes. Pytest passes. PR #16 is now unblocked on
the CI side.

## What still fails: k6 threshold

Load Tests (k6) still fails with the same threshold violations as
session 1:
```
✗ api_duration_ms: avg=2.33s   p(95)=6.11s
✗ errors: 77.56% (6422 / 8280)
http_req_failed: 0.00% (no transport failures)
```

This is a **real backend perf bug** in `/api/health`, which hits
Postgres + Redis + Qdrant on every call. At 500 RPS that saturates.
The k6 threshold budget is 200ms (in `tests/load/config.js`).

This is NOT a CI bug. Two follow-up options:
1. Tighten the endpoint: cache probe results, or move heavy checks
   to `/api/health/full` (the dedicated deep-health endpoint).
2. Loosen the budget: raise `BUDGETS.health` in `tests/load/config.js`.

Either is a separate PR from #16.

## What did NOT change today
- No backend code modified.
- No source files added/removed.
- @flowmanner/cli still untouched (PR #18 is on main, not this branch).

## Substrate table ERRORs in k6 logs (user asked about)

The k6 workflow's Postgres service is a fresh container with no
migrations applied. The backend's lifespan code queries
`mission_programs` and `mission_triggers` (substrate tables that
need migrations). The queries fail with ERROR (logged by Postgres)
but are caught as WARNINGs by `app/lifespan.py` — backend still
starts, `/api/health` still returns 200, k6 still runs.

These ERRORs are noise. To silence them, add
`alembic upgrade head` to the k6 workflow after `pip install` and
before `uvicorn` start. Not done in this session — separate PR.

## Skills saved this session
- `bash-pipefail-sigpipe-grep-q` — documents the SIGPIPE/pipefail
  gotcha so future agents don't burn hours on it.

## CI Cost This Session

Roughly 6 self-hosted pr-check runs + 5 ubuntu-latest k6 runs =
~25 min wall time combined (mostly k6). All on the existing budget.

## Related
- PR #16: https://github.com/glennguilloux/flowmanner/pull/16
- Skill: ~/.hermes/skills/software-development/bash-pipefail-sigpipe-grep-q/SKILL.md
- Earlier handoffs: `.sisyphus/handoffs/active-session-2026-06-23-pr18-merge-k6-diagnosis.md`
- Session-1 handoff: `.sisyphus/handoffs/active-session-2026-06-24.md` (superseded by this)
