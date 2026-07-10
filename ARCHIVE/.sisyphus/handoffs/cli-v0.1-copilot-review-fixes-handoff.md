# Handoff: @flowmanner/cli v0.1.0 — Copilot review fixes (PR #18 follow-up)

**Date:** 2026-06-23
**Branch:** `feat/cli-v0.1-audit-fixes` @ `b995a53` (4 commits ahead of origin)
**Status:** PR #18 OPEN. 4 commits, all local. **Push deferred to 2026-07-01** per
AGENTS.md Budget state (CI exhausted, ~82% failure rate, 89.5% is uncorrected).

## TL;DR

Took gpt-5.4 Copilot review feedback on PR #18 and landed it as a single new
commit at the head of `feat/cli-v0.1-audit-fixes` (chose option 1 from the
clarify — separate "review fixes" commit preserves audit trail).

**New commit:** `b995a53 fix(cli): address Copilot review on PR #18 — drift guard, ts plumbing, concurrency`

## What landed

### BLOCKING (fixed)
- **`cli/tests/types.test.ts:32-33`** — the advertised "compile-time drift
  guard" was a no-op. `(sample as Record<string, unknown>).created_at` is
  always type-valid, so `@ts-expect-error` never checked RunEvent.
  **Fix:** removed the cast. Guard now actually fails to compile if
  `created_at` is re-added. Verified: TS2578 fires on simulation.

### WARNING (fixed)
- **`cli/tsconfig.json:24-25`** — tests were excluded from the TS program
  entirely. `npm run build` never ran tsc against them, so the drift guard
  was never evaluated by tsc. **Fix:** split into `tsconfig.json` (production
  build, `src/` only) + `tsconfig.test.json` (`noEmit`, includes tests/).
  Added `npm run typecheck` script and a `Typecheck (tests)` step in cli.yml
  before Build. Tests are now part of the CI typecheck gate.

- **`.github/workflows/cli.yml:12-53`** — no concurrency block (the other 4
  workflows all have one). **Fix:** added PR-scoped concurrency with
  `cancel-in-progress: true` so force-pushes don't burn hosted minutes.

### WARNING (not addressed, noted)
- `cli/package.json` dependency ranges use `^` rather than exact pins. Flag
  stays open; not a blocker for this PR.

### Surfaced by widening the TS program (fixed)
Two pre-existing test-side type errors that were hidden by the old
`exclude: ["tests"]`:
- `cli/tests/blueprint.test.ts:44` — indexed access on `Record<string, unknown>`
  failed under strict mode. **Fix:** narrowed cast to `Record<string, { type: string }>`.
- `cli/tests/whoami.test.ts:58` — `process.exitCode` is wider than `number | undefined`
  in node types (`number | string | null | undefined`). **Fix:** narrowed at
  read site with a typeof guard, preserving the original `undefined`-when-clean
  contract used by the assertions.

## Verification (all locally on homelab)

```
npm run typecheck  → clean. AND: re-adding created_at to RunEvent produces
                     TS2578: Unused '@ts-expect-error' directive (drift guard works)
npm run build      → clean
npm test           → 21/21 pass
npm run lint       → clean
```

## Issues touched

- **#19** (will close via PR #18 push): "make tests/types.test.ts typecheck
  guard actually compile-time" — this commit is the implementation. The issue
  body specified the exact `tsconfig.test.json` shape we used.
- **#20** (still open): "add CLI Smoke step to cli.yml so the bin is exercised
  in CI" — separate concern, not addressed here.

## Files changed in b995a53

```
.github/workflows/cli.yml       | +13 (concurrency block + Typecheck step)
cli/package.json                |  +1 (typecheck script)
cli/tsconfig.json               |  ±2 (dropped tests/ from exclude)
cli/tsconfig.test.json          |  NEW (noEmit, includes tests/)
cli/tests/types.test.ts         |  ±3 (removed dead cast)
cli/tests/blueprint.test.ts     |  ±8 (narrowed cast on input_schema)
cli/tests/whoami.test.ts        |  ±6 (typeof guard on process.exitCode)
```

## What blocks push (per AGENTS.md Budget state)

The 2026-06-14 → 2026-06-22 billing cycle on `glennguilloux/flowmanner`:
166 fail / 26 cancelled / 10 success out of 202 runs = **82.2% failure rate**
(not 89.5% — that figure was uncorrected; see commit 97c68aa). Self-hosted
Deploy runs failed at 90.5%. We can't prove a push will succeed vs waste a
slot, and red CI on the open PR #16 / #18 makes the queue look worse.

**Verify before pushing (homelab, in order):**
1. `gh api repos/glennguilloux/flowmanner/actions/runs --jq '.total_count'` —
   plateaus = still constrained.
2. `gh api repos/glennguilloux/flowmanner/actions/runs --jq '.workflow_runs |
   sort_by(.created_at) | reverse | .[0:5] | .[] | [.created_at, .name,
   .conclusion, .event, .head_branch] | @tsv'` — read 5 most recent.
3. After 2026-07-01: push to non-main branch, watch for real `billable.UBUNTU`
   minutes, then push to main.

## Next agent / Glenn

After 2026-07-01:
1. Push `feat/cli-v0.1-audit-fixes` (4 commits: `0bf8b65` `1bc81db` `6847b5a` `b995a53`)
2. Watch CI go green on cli.yml (should be 25-30s — ubuntu, narrow path filter)
3. Close issue #19 (this commit implements it) and #20 (separate)
4. Merge PR #18

If CI fails after the budget reset: capture the run id + conclusion + billable
shape, do NOT auto-retry. Edit budget section of AGENTS.md with new evidence
and re-defer.

## Source artifacts

- Review prompt (gpt-5.4 Copilot): saved in this session's transcript
- Source plan: `.sisyphus/plans/cli-v0.1-audit-fix-plan.md` §1.4
- Audit: `.sisyphus/plans/SANDBOX-PREVIEW-401-DEEPSEEK-AUDIT.md` (related but
  separate — sandbox chain, also closed 2026-06-10)
