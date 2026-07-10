# Handoff: @flowmanner/cli v0.1.0 — P0 Audit Fixes (PR #18)

**Date:** 2026-06-23
**Branch:** `feat/cli-v0.1-audit-fixes` @ `6847b5a`
**Status:** PR #18 OPEN. 4 commits pushed, CI green (build-test-lint, 25s). Awaiting Glenn's merge.
**Source plan:** `.sisyphus/plans/cli-v0.1-audit-fix-plan.md` (locked 2026-06-23)

## TL;DR

Landed Priority-1 release blockers from the CLI audit as 4 logical commits on
a single PR. Initial drop of `@flowmanner/cli` v0.1.0 (was net-new in this
monorepo — never previously committed). 21/21 tests pass, lint clean
(0 errors, 0 warnings), CI green.

**4 commits:**
1. `a32cfd0` feat(cli): initial drop of @flowmanner/cli v0.1.0 + CI workflow
2. `0bf8b65` fix(cli): init --here actually scaffolds into cwd (#1.2)
3. `1bc81db` fix(cli): RunEvent timestamps + actor fields render correctly (#1.4)
4. `6847b5a` fix(cli): delete dead code paths flagged by eslint + audit (#1.5 #2.3)

**Follow-up issues filed (#19, #20):**
- #19 — make `tests/types.test.ts` typecheck guard actually compile-time
- #20 — add CLI Smoke step to `cli.yml` so the bin is exercised in CI

## Files this agent DID touch

- `cli/eslint.config.js` (new)
- `cli/package.json` — devDeps for ESLint v9 line
- `cli/package-lock.json`
- `cli/src/commands/init.ts` — #1.2 fix (--here)
- `cli/src/commands/login.ts` — #2.3 fix (dead code delete)
- `cli/src/commands/logs.ts` — #1.4 fix (timestamp + actor)
- `cli/src/commands/run.ts` — #1.4 fix (timestamp + actor)
- `cli/src/commands/whoami.ts` — #1.5 fix (dead code delete)
- `cli/src/commands/publish.ts` — lint cleanup (unused import)
- `cli/src/commands/config.ts` — lint cleanup (unused arg prefix)
- `cli/src/types.ts` — #1.4 fix (RunEvent fields)
- `cli/tests/init.test.ts` — +2 tests (--here + refusal regression)
- `cli/tests/types.test.ts` (new) — RunEvent contract drift guard
- `cli/tests/whoami.test.ts` (new) — 3 tests including drift-warning-absent invariant
- `.github/workflows/cli.yml` (new) — ubuntu + Node 20, scoped to cli/**

## Files this agent did NOT touch

- Backend: nothing. Backend changes for SSE (#1.1) are out of scope and
  filed at `.sisyphus/plans/backend-run-events-sse.md`.
- Frontend: nothing.
- AGENTS.md / CLAUDE.md: deliberately not written. Draft text provided in
  session output for Glenn to paste himself.

## Verification (pasted from session output, do not paraphrase)

```
$ cd cli && rm -rf dist templates
$ npm run build        → exit 0 (clean tsc + copy-templates)
$ npm test             → tests 21, pass 21, fail 0
$ npm run lint         → exit 0 (0 errors, 0 warnings)
$ node bin/flowmanner.js --version                   → 0.1.0
$ node bin/flowmanner.js --help | head -15           → all 14 commands listed
$ node bin/flowmanner.js whoami                      → exit 1, "Not logged in."
$ node bin/flowmanner.js config path                 → ~/.flowmanner/config.json
$ mkdir /tmp/x && cd /tmp/x
$ node .../cli init x --here && ls flowmanner.yaml   → exists in cwd ✓
$ mkdir -p /tmp/y/y && cd /tmp/y
$ node .../cli init y                                → refuses "already exists"
```

CI on PR #18: `build-test-lint` pass, 25s wall time.

## Next session

**For you (Glenn):**
1. Merge PR #18 when ready. Triggering mechanism is the `push` event on
   main from the merge commit (path filter matches cli/**), NOT a
   `pull_request` re-run. One ~25s run. Tier is already dead, marginal
   cost is $0.
2. Add the "Budget state" section to root AGENTS.md if you want the
   constraint as a project-level invariant. Draft text in this session's
   transcript; one edit: "any branch on the flowmanner repo" not "any
   branch". This prevents the next agent from re-burning your free tier.
3. If you want the memory entry in CLAUDE.md, paste it yourself (agents
   shouldn't write their own memory).

**For the next agent session (when tier resets 2026-07-01):**
1. Resolve #1.1 (SSE fiction). Three options per the plan's decision rule:
   (a) wait for backend SSE ticket, (b) CLI long-poll fallback, (c) honest
   README downgrade. Pick per the priority order in §1.1 of the audit plan.
2. Land #2.1 (refresh-token interceptor with `refreshInFlight` module-
   scoped promise), #2.2 (X-Workspace-Id header), #2.3 already done.
3. Address #19 (typecheck guard) and #20 (Smoke step) — both are <30 line
   PRs and CI-gated.
4. Backfill the 12 remaining untested commands. The capture pattern from
   `tests/whoami.test.ts` is reusable; extract to `tests/support/run-command.ts`.

## Gotchas for the next agent

- `cli/tsconfig.json` excludes `tests/` from tsc. If you write a
  `@ts-expect-error` drift guard, ALSO add `tsconfig.test.json` + a
  `typecheck` script and run it in CI. Otherwise the guard is fiction.
- `tests/whoami.test.ts:58` types `process.exitCode` as `number | undefined`
  but node types it `string | number | null | undefined`. The test passes
  at runtime; a stricter typecheck step would catch it. Widen the local
  type or cast at read site.
- `cli/.gitignore` is in the initial drop. Don't re-add the standard
  Node ignores — it's already covered.
- Pre-commit hooks target backend/ (ruff + mypy). They don't run on cli/
  TypeScript. No pre-commit install needed for CLI work.
- The self-hosted Arch runner is configured in pr-check.yml and is what
  burned the budget. cli.yml correctly uses `ubuntu-latest`. Don't migrate
  cli.yml to self-hosted.
