# Handoff — 2026-06-24 Sessions 1-5 (full day): PR #16 deletion-guard repair, decision: fix /api/health first

## TL;DR — Next session's task

**Fix `/api/health` perf bug.** Then re-verify k6 thresholds against the fixed endpoint.

The user's call (verbatim from chat): "fix /api/health first (then k6 thresholds need re-verifying anyway)".

Everything else in this handoff is context for the next agent.

---

## Session-by-session summary

### Sessions 1-2: k6 workflow repair
- Diagnosis from 06-23 handoff was correct (APP_ENV → development bypasses
  secret validator) but incomplete.
- Two more bugs in `load-test.yml`:
  - Fixed `sleep 10` racy with uvicorn startup (~11s) → replaced with
    60s polling loop on `/api/health`.
  - k6 install path mismatch: `sudo cp ... /usr/local/bin/k6` vs
    `run-tests.sh` reading `${HOME}/.local/bin/k6` → moved to user's
    local/bin.
- k6 ran to completion. Real threshold violations surfaced:
  `/api/health` p95=7.5s under 500 RPS. Endpoint hits Postgres + Redis +
  Qdrant on every call.
- Rebased PR #16 onto `origin/main` (zero conflicts — PR #18 was cli-only).
- Re-enabled `PR Check` workflow in GitHub UI (was `disabled_manually`).

### Sessions 3-4: deletion-guard repair
The deletion guard has been silently broken since PR #17 wired it.
Three layered bugs:

1. **Synthetic merge commit** (`f4d7563`, `b3bc88b`): runner checks out
   empty-body merge commit. Fixed by fetching `refs/pull/N/head` and
   using `git log BASE..HEAD_SHA`.

2. **`set -o pipefail` + `grep -q` SIGPIPE** (`1f32f49`): even with the
   right commits, `git log | grep -qi 'pattern:'` returns 141 (SIGPIPE),
   not grep's exit. `if` sees failure, falls through. **The fix is to
   capture the body and use a here-string:**
   ```bash
   PR_BODY="$(git log --format=%B "$BASE".."$HEAD_SHA")"
   if grep -qi 'deletion justification:' <<< "${PR_BODY}"; then
       exit 0
   fi
   ```
   Saved as a skill at `~/.hermes/skills/software-development/bash-pipefail-sigpipe-grep-q/SKILL.md`.

3. **Non-fast-forward fetch** (`833f846`): force-pushes broke the fetch
   refspec. Fixed with `git fetch --force`.

Latest CI run (28075171543) on commit `833f846`:
```
[Deletion guard + backend sanity] Deletion justification found in PR commit body — passing guard.
[Deletion guard + backend sanity] 2521 passed, 50 skipped, 707 deselected, 68 warnings in 61.02s
```
✅ Deletion guard passes. ✅ Pytest passes.

### Session 5 (this): decision

The user reviewed the k6 output and chose: **fix /api/health first, then
re-verify k6 thresholds**. Don't merge PR #16 yet. Don't deploy yet.

---

## Final state of PR #16

- Branch: `drop-audio-features-v2` HEAD = `833f846`
- `mergeable_state`: was `unstable` → `clean` after rebase onto
  `origin/main` (`31a82d8`)
- Diff vs origin/main: 13 files, +37/-3542
- Checks on `833f846`:
  - **Deletion guard + backend sanity: ✅ success**
  - Load Tests (k6): ❌ failure (real perf threshold — see below)
  - .github/workflows/ci.yml: ❌ pre-existing mypy baseline drift

PR #16 is CI-clean except k6. The user has chosen NOT to merge it until
/api/health is fixed.

## Today's commits (chronological)

1. `5b1bd85` — k6 workflow: APP_ENV → development + polling retry
   loop + k6 install path fix.
2. `057264d` — chore(sisyphus): rebase marker no-op.
3. `f4d7563` — pr-check.yml: deletion guard checks PR head, not
   synthetic merge commit body.
4. `b3bc88b` — pr-check.yml: fetch refs/pull/N/head (not refs/pull/N/merge).
5. `1f32f49` — pr-check.yml: use here-string to avoid pipefail SIGPIPE.
6. `833f846` — pr-check.yml: --force on the fetch refspec to survive
   force-pushes.

---

## The /api/health perf bug — what to fix

### Source

`backend/app/api/v1/health.py` lines 33-87 (as of session 1 read):

```python
@router.get("/health", response_model=HealthResponse)
async def health():
    # ... try/except blocks for DB, Redis, Qdrant, each runs a real
    # probe on every call. Catches errors and returns status="error"
    # rather than 500. Latency is the sum of all probe latencies.
```

Each call:
- `engine.connect()` + `SELECT 1` (Postgres round-trip)
- `Redis.from_url()` + `PING` (Redis round-trip, also creates a new client)
- `AsyncQdrantClient(url=...)` + `get_collections()` (Qdrant round-trip)

At 500 RPS that saturates. p95 = 7.2s. Budget is 200ms.

### Three fix options, in order of preference

**Option A (preferred): split /api/health from /api/health/full**
- `/api/health`: lightweight — return `app` + `env` + maybe a cached
  `last_full_check` timestamp. Sub-millisecond.
- `/api/health/full`: existing heavy probe logic. Documented as
  "use for deep diagnostics, not liveness checks".
- k6 only hits `/api/health`, so it gets the cheap version.
- Existing line 139-`@router.get("/health/full")` already exists — just
  need to redirect its content from the heavy path, and make
  `/health` cheap.

**Option B (if A is too invasive): cache the probe results**
- Wrap the heavy probe in a 5s-TTL cache (Redis or in-memory with
  `functools.lru_cache`-like TTL).
- Cheap on warm cache; first call still slow (acceptable for k6 which
  ramps up).
- Risk: cache invalidation if a component actually goes down — but
  k6's failure mode would still catch it within 5s.

**Option C (cheapest, last resort): raise BUDGETS.health**
- `tests/load/config.js` line 33: `health: 200` → something like
  `health: 8000` (matches current p95).
- Doesn't fix the perf bug — just hides it from k6.
- Don't do this without telling the user. They'd want to know we're
  lowering the bar instead of raising it.

### Substrate table ERRORs in k6 logs (incidental)

The k6 workflow's Postgres service is a fresh container with no
migrations applied. The backend's lifespan code queries
`mission_programs` and `mission_triggers`. The queries fail with ERROR
(logged by Postgres) but are caught as WARNINGs by `app/lifespan.py` —
backend still starts, `/api/health` still returns 200, k6 still runs.

These ERRORs are noise. To silence: add `alembic upgrade head` to
`load-test.yml` after `pip install` and before `uvicorn` start.

Not blocking. Do it if convenient while you're in the workflow.

### Verification after the fix

1. Local: hit `/api/health` directly with a load tool (`hey`,
   `wrk`, or just `for i in {1..100}; do curl ...; done`).
   Latency should be sub-10ms.
2. CI: re-push to PR #16's branch (or a new branch if you want a
   separate PR) and watch k6 thresholds:
   ```
   ✓ health duration < budget
   ✓ errors
   ✓ api_duration_ms
   ✓ http_req_duration
   ```
3. If still failing, the endpoint isn't the only bottleneck — check
   if there's a connection pool issue or N+1 query.

---

## Sub-tasks for next session (ordered)

1. **Open a new branch off `origin/main`** for the `/api/health` fix.
   Suggested name: `fix/api-health-probe-caching` or `perf/health-endpoint-lightweight`.
2. **Read `backend/app/api/v1/health.py` in full** before editing.
   The 06-23 session only read lines 33-87 — there's more (the
   `/health/full` endpoint, the LLM probe, etc.).
3. **Apply Option A** (preferred): move the heavy probe to `/health/full`,
   make `/health` cheap. Keep backward compatibility — any existing
   caller hitting `/health` for liveness still gets a 200 with
   `status: ok` (use cached probe results from the last full check).
4. **Local verify with `hey` or similar** before pushing.
5. **Push, watch k6** on the new branch. Threshold should pass.
6. **Once k6 passes**, revisit whether to merge PR #16. If you do,
   the user (Glenn) deploys manually per session ritual — no agent
   deploys.
7. **After PR #16 merges + deploys**, move to PR #18 work (per
   user's plan from session 1).

---

## Things NOT to do

- **Don't run `deploy-backend.sh --migrate` yet.** Nothing on main
  needs migrating that we know of. Wait for PR #16 to merge.
- **Don't merge PR #16.** User explicitly chose to fix /api/health
  first.
- **Don't push the local `560e3ff` (substrate commit on main).**
  Memory rule: defer pushes to glennguilloux/flowmanner until
  2026-07-01. That's a user-driven decision they haven't reversed.
- **Don't push the `833f846` workflow fixes as a standalone PR.**
  They belong with PR #16 — keep them on `drop-audio-features-v2`.
  If the user wants a separate PR for the pr-check workflow fixes
  later, that's a rebase/squash discussion, not for this session.

---

## Files in the repo right now

- `.sisyphus/handoffs/active-session-2026-06-24-end-of-session.md` (this file)
- `.sisyphus/handoffs/active-session-2026-06-24.md` (superseded — session 1
  version, kept for history)
- `.sisyphus/exit-audit-2026-06-24-pr16-load-test-repair.md` (final exit
  audit, accurate)
- `.sisyphus/PR16_REBASE_VERIFIED.md` (committed on the branch — safe
  to keep or revert)
- `~/.hermes/skills/software-development/bash-pipefail-sigpipe-grep-q/SKILL.md`
  (new skill, documents the bash gotcha from sessions 3-4)

## CI cost today

~6 self-hosted pr-check runs + 5 ubuntu-latest k6 runs ≈ 25 min wall
time. Within budget. No billable self-hosted minutes.

## Related

- PR #16: https://github.com/glennguilloux/flowmanner/pull/16
- PR #18: https://github.com/glennguilloux/flowmanner/pull/18 (merged)
- 06-23 handoff: `.sisyphus/handoffs/active-session-2026-06-23-pr18-merge-k6-diagnosis.md`
