# Handoff: Budget state correction (Session 2026-06-23, follow-up)

**Date:** 2026-06-23
**Branch:** `feat/cli-v0.1-audit-fixes`
**New commit:** `97c68aa` (AGENTS.md Budget state correction)
**Status:** LOCAL, NOT pushed (CI still degraded; same deferral rule applies).
**Trigger:** Glenn asked: "double check how we work" and pasted the
prior session's exit audit. I (this session) verified the git state
and the commit contents — both match the prior audit. But two factual
claims in the AGENTS.md "Budget state" section did not survive
verification.

## TL;DR

The prior session (commits a7aae7a, b3116ca) added a "Budget state"
section to AGENTS.md that **codified the deferral rule correctly**
but **stated two wrong facts** that the next agent would have
inherited as truth. This session replaces the section with verified
numbers and an honest mechanism. Same deferral rule, no behavior
change for agents.

## What was wrong in the prior commit

### 1. "89.5% failure rate"

Prior text: *"200 runs, 89.5% failure rate (mostly self-hosted Arch
runner campaign)."*

Verified count for 06-14 → 06-22 (202 runs total, paginated):

| conclusion | count |
|------------|-------|
| failure    | 166   |
| cancelled  | 26    |
| success    | 10    |

166/202 = **82.2%** failure. (166+26)/202 = 95% if cancelled counts
as fail. No calculation gives 89.5%. The "200" was also off by 2
(202 actual). Both numbers were approximate/eyeballed, not counted.

### 2. "ubuntu-latest workflows are exempt"

Prior text: *"`cli.yml` and other workflows pinned to `ubuntu-latest`
(not self-hosted) are exempt from the queue-cost concern."*

Evidence on the same hour of 2026-06-23:

- `cli.yml` (ubuntu-latest) → success, 25s, billable UBUNTU: 0 ms.
- `ci.yml` (ubuntu-latest, 5 jobs all on ubuntu-latest) → failure,
  0 jobs, `{"billable":{}}`, started-and-ended same second.

Both workflows are ubuntu-latest. They had opposite outcomes. The
runner type is **not** the differentiator. The ci.yml 0-job failure
looks like a path-filter skip mis-classified as "failure" (zero
billable units, no job entries) — *not* a billing block. A billing
block would surface in the cli run too because both consume the same
Actions allotment.

Self-hosted Deploy workflow (the "Arch runner" the prior audit
blamed) ran 58 fail / 6 success = 90.5% fail, but self-hosted runners
**do not consume Actions minutes** — they consume homelab power. So
the "self-hosted is burning budget" framing was also wrong: it was
burning homelab reliability, not GitHub allotment.

## What this session changed

`AGENTS.md` — replaced the "Budget state" section. Key changes:

- Replaced "CI FREE TIER EXHAUSTED" (unprovable claim) with
  "CI is degraded and untrusted — defer pushes until 2026-07-01"
  (honest characterization).
- Replaced "200 runs, 89.5% failure" with "202 runs, 82.2% failure"
  and added a per-workflow breakdown so the next agent can sanity-
  check the numbers.
- Replaced the "ubuntu-latest exempt" claim with "Runner type is
  NOT the differentiator" + the actual 0-job path-skip mechanism.
- Added an explicit "Do NOT change runner type as a fix" rule
  pointing at the deletion-guard PR where that was already learned
  the hard way.
- Replaced the single-command verify with a 3-step verify that
  distinguishes billing block (Ubuntu billable > 0 + failure) from
  path-skip (billable empty + failure, same second).
- Kept the "defer push, write handoff doc" rule intact — the
  **decision** is the same; only the **justification** is now
  honest.

## What this session did NOT change

- `SESSION-RITUAL.md` — the audit template is fine. CI COST and
  MEMORY WRITES sections are durable additions and apply regardless
  of the budget mechanism.
- The handoff doc structure at `.sisyphus/handoffs/` — that path
  continues to work.
- The push-deferral rule itself — still in effect, still pointing
  at the "Budget state" section, still conditional on its content.
- Any code, test, or CI workflow files.

## Verification

```
$ git diff b3116ca -- AGENTS.md
(shows the section replacement — see commit for the exact diff)

$ gh api repos/glennguilloux/flowmanner/actions/runs \
    --jq '.workflow_runs
    | sort_by(.created_at) | reverse | .[0:5]
    | .[] | [.created_at, .name, .conclusion, .event, .head_branch]
    | @tsv'
2026-06-23T04:15:07Z  cli   success  pull_request  feat/cli-v0.1-audit-fixes
2026-06-23T04:14:51Z  CI    failure  push          feat/cli-v0.1-audit-fixes
2026-06-22T06:02:57Z  Load Tests  failure  pull_request  drop-audio-features-v2
2026-06-22T06:02:57Z  PR Check   failure  pull_request  drop-audio-features-v2
2026-06-22T06:00:59Z  Deploy     success  push          main

$ gh api repos/glennguilloux/flowmanner/actions/runs/28001732017/timing
{"billable":{}}                    # ← path-skip signature, not billing block
```

## Gotchas for the next agent

- The deferral rule is still active. Do not push this branch.
- When the budget resets on 2026-07-01, follow the 3-step verify
  in AGENTS.md before pushing. The first push should go to a non-main
  branch (or to a branch that doesn't change `cli/**` or workflow
  files) so ci.yml's branch/path filters don't surprise us again.
- The 0-job path-skip on ci.yml is a separate bug worth investigating
  after 2026-07-01 — not a budget issue, but it'll keep showing
  red on every PR until it's understood.
- The "mostly self-hosted Arch runner" framing in the original
  memory was wrong. Self-hosted runners failed often but didn't
  burn Actions minutes. The minute-burner is the ubuntu-latest
  jobs, and the question of why ci.yml's ubuntu jobs are failing
  is open.

## Exit audit per the new template

=== CI COST THIS SESSION ===
- 0 workflow runs triggered this session (no pushes, no PR events).
- Verified prior session's claim of "0 minutes" — still true.
- This session's verification reads (`gh api .../actions/runs`) are
  read-only and do not trigger CI.
- Total: 0 minutes this session.

=== MEMORY WRITES THIS SESSION ===
- None. The "budget-trigger rule" memory from the prior session
  still drives the deferral decision; it remains accurate as
  written. The two errors caught this session were in the doc
  text, not in the memory itself.
- This is per-machine on homelab only — not visible on ops/VPS
  per the per-machine warning in AGENTS.md.

=== STATUS ===
```
$ git status
On branch feat/cli-v0.1-audit-fixes
Your branch is ahead of 'origin/feat/cli-v0.1-audit-fixes' by 3 commits.
nothing to commit, working tree clean

$ git log --oneline -4
97c68aa docs(agents): correct Budget state numbers + remove ubuntu-latest exemption
b3116ca docs(agents): add Budget state section + amend push rule to defer on exhaustion
a7aae7a docs(ritual): add CI COST + MEMORY WRITES sections to exit audit template
6847b5a fix(cli): delete dead code paths flagged by eslint + audit (#1.5 #2.3)

$ git fetch origin && git log --oneline origin/feat/cli-v0.1-audit-fixes..HEAD
97c68aa docs(agents): correct Budget state numbers + remove ubuntu-latest exemption
b3116ca docs(agents): add Budget state section + amend push rule to defer on exhaustion
a7aae7a docs(ritual): add CI COST + MEMORY WRITES sections to exit audit template
```

(3 commits ahead of origin. All deferred per AGENTS.md "Budget state"
rule. The new commit 97c68aa is a doc-only correction — see this
handoff for what it fixed.)

=== PUSH DECISION ===
DEFERRED. Same reasoning as the prior session: CI is degraded
and untrusted, defer until 2026-07-01, then verify with the
3-step procedure in the corrected AGENTS.md section before
pushing.

=== END ===
