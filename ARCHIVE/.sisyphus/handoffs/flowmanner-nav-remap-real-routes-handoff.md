# Handoff: Remap Floating Nav Hrefs to Real Flowmanner Routes

**Date:** 2026-06-16
**Boulder:** `flowmanner-nav-remap-real-routes` (PLAN APPROVED, NOT STARTED)
**Source plan:** `.sisyphus/plans/flowmanner-nav-remap-real-routes.md`
**Parent handoff (deferred-routes context):** `.sisyphus/handoffs/floating-nav-deferred-routes-handoff.md`
**Root handoff (nav boulder):** `.sisyphus/handoffs/flowmanner-nav-after-login-boulder-handoff.md`
**Status:** User chose Option B (remap) over Option A (scaffold stubs). Plan saved. `/start-work flowmanner-nav-remap-real-routes` will register the boulder and launch Wave 1.

---

## TL;DR

The signed-in floating nav has 9 hrefs that 404 because they point at `/dashboard/{build,run,market/*,tools/*}` routes that were stubbed in local commit `2007fa7` but never backed by real pages. The real product surfaces already exist (`/missions/builder`, `/runs`, `/marketplace`, `/tools`, `/tools/catalog`, `/memory-inspector`). This boulder fixes the nav-config hrefs to point at the real routes, deletes the 9 stub files, and preserves active-route highlighting on `/en/missions`.

**Deliverables (3 source changes):**

1. `src/components/layout/nav-config.ts` — 9 `href` strings remapped
2. `src/components/layout/floating-nav.tsx` — one-line `pathAlias` correction (`/missions` → `/missions/builder`)
3. 9 deleted stub `page.tsx` files under `src/app/[locale]/dashboard/{build,run,market/*,tools/*}/`

**Critical path:** T1 + T2 + T3 (parallel) → T4 (verify + amend local commit `2007fa7`) → F1–F4 → user review → push.

---

## Execution Protocol (read this first — 30 seconds)

```
Wave 1 (parallel, 3 agents):
  T1 nav-config href remap
  T2 floating-nav pathAlias one-liner
  T3 delete 9 stub page.tsx files

Wave 2 (sequential, 1 agent):
  T4 run all 4 verification gates, amend local commit 2007fa7, present diff

Wave FINAL (parallel, 4 agents):
  F1 plan compliance  F2 code quality  F3 manual QA  F4 scope fidelity
→ Wait for user okay on the diff → push
```

**File-ownership rule:** T1 owns `nav-config.ts` only. T2 owns `floating-nav.tsx` (one line in `pathAlias`, no broader edits). T3 owns the 9 stub file deletions. None of them touch each other's files. T4 is the only one that runs the commit + push gate.

**Commit strategy:** ONE local commit — `fix(nav): remap product-discovery hrefs to real routes`. Amend `2007fa7` if it's still the most recent local commit and contains only the 9 stub additions; otherwise replace it. Do NOT push until the user reviews the diff (per AGENTS.md — frontend deploy is user-gated).

---

## The 9 Href Remaps (memorize — this is the work)

| Group    | Old (placeholder)                       | New (real route)                  |
|----------|------------------------------------------|------------------------------------|
| Build    | `/dashboard/build`                       | `/missions/builder`                |
| Run      | `/dashboard/run`                         | `/runs`                            |
| Market   | `/dashboard/market`                      | `/marketplace`                     |
| Market → My Installed   | `/dashboard/market/my-installed`   | `/marketplace/my-installed`        |
| Market → My Listings    | `/dashboard/market/my-listings`    | `/marketplace/my-listings`         |
| Market → Create Listing | `/dashboard/market/create-listing` | `/marketplace/create-listing`     |
| Tools    | `/dashboard/tools`                       | `/tools`                           |
| Tools → Hub              | `/dashboard/tools/hub`              | `/tools/catalog`                   |
| Tools → Memory Inspector | `/dashboard/tools/memory-inspector` | `/memory-inspector`              |

Plus the pathAlias fix:
- `"/missions": "/dashboard/build"` → `"/missions": "/missions/builder"`

This last line is what keeps the Build nav item highlighted when the user is on `/en/missions`. Without it, the active-route test at `src/components/layout/__tests__/floating-nav.test.tsx:395-407` breaks.

---

## The 9 Stub Files to Delete (commit `2007fa7`)

```
src/app/[locale]/dashboard/build/page.tsx
src/app/[locale]/dashboard/run/page.tsx
src/app/[locale]/dashboard/market/page.tsx
src/app/[locale]/dashboard/market/my-installed/page.tsx
src/app/[locale]/dashboard/market/my-listings/page.tsx
src/app/[locale]/dashboard/market/create-listing/page.tsx
src/app/[locale]/dashboard/tools/page.tsx
src/app/[locale]/dashboard/tools/hub/page.tsx
src/app/[locale]/dashboard/tools/memory-inspector/page.tsx
```

These came from local commit `2007fa7`. Verify with `git show --stat 2007fa7` before deleting — if the commit touched anything else, the amend strategy needs to be reassessed. Do NOT delete the real route pages: `/tools/catalog`, `/integrations`, `/missions/builder`, `/team`, `/graphs`, `/memory-inspector` (the last three live under `(dashboard)` route group, which is URL-transparent).

---

## The 7 Hard Guardrails (F1 and F4 will REJECT on any of these)

1. **NO backend changes.** Frontend-only boulder. `backend/app/**` is off-limits.
2. **NO VPS edits and NO `deploy-frontend.sh`.** Source edits on homelab, deploy is user-gated per AGENTS.md.
3. **NO locale file changes.** The remap is href-only; labels stay the same.
4. **NO changes to `floating-nav.tsx` beyond the one-line `pathAlias` correction.** No refactor, no testid changes, no auth-store/provider edits.
5. **NO new `More` / `Menu` bucket.** Tiers stay as the nav boulder set them.
6. **NO adding orphaned routes** (Team, Graphs, Blueprints, Templates, Triggers, Analytics, Costs, RAG, Workflows, Files) into the nav. The plan explicitly locks this — that work is a separate boulder.
7. **NO push before user reviews the diff.** Local commit only; the user triggers the deploy.

---

## Verification Gates (run in T4, sequential)

```bash
cd ~/FlowmannerV2-frontend

pnpm validate-nav-routes
# Expected: All routes valid: 39 [OK], 0 [MISSING]

pnpm tsc --noEmit
# Expected: exit 0

pnpm test -- floating-nav.test.tsx
# Expected: exit 0; Build active-route test passes via the new pathAlias

pnpm test:e2e floating-nav-product-discovery -g "route validity"
# Expected: 1 passed; test 10 reports 200 for /dashboard, /documentation, /dashboard/swarm
```

All 4 evidence files go to `.sisyphus/evidence/task-4-{gate}.txt` per the plan's QA scenarios. F1 and F2 will check that the files exist.

---

## Evidence Files (MUST capture per task)

T1:
- `.sisyphus/evidence/task-1-validator-after-remap.txt`
- `.sisyphus/evidence/task-1-no-placeholder-hrefs.txt`

T2:
- `.sisyphus/evidence/task-2-vitest-floating-nav.txt`
- `.sisyphus/evidence/task-2-pathalias-check.txt`

T3:
- `.sisyphus/evidence/task-3-stub-deletion-check.txt`
- `.sisyphus/evidence/task-3-validator-after-deletion.txt`

T4:
- `.sisyphus/evidence/task-4-validate-nav-routes-final.txt`
- `.sisyphus/evidence/task-4-tsc-final.txt`
- `.sisyphus/evidence/task-4-vitest-final.txt`
- `.sisyphus/evidence/task-4-e2e-route-validity-final.txt`
- `.sisyphus/evidence/task-4-git-diff-scope-clean.txt`

If a task ships without its evidence, F1/F2 will bounce it back. Skipping the evidence is not an optimization.

---

## Files the Next Agent Should Read First

1. **THIS HANDOFF** (you're reading it).
2. `.sisyphus/plans/flowmanner-nav-remap-real-routes.md` — the playbook. Read "Context → Research Findings" and "Work Objectives" first; task details are in the TODOs section.
3. `.sisyphus/handoffs/floating-nav-deferred-routes-handoff.md` — the parent handoff that framed this work; explains why `2007fa7` was the wrong fix and the Option A vs B decision.
4. `.sisyphus/handoffs/flowmanner-nav-after-login-boulder-handoff.md` — the root boulder; defines the active-route rule, data-testid contract, and the 8 hard guardrails (5 of which still apply to this boulder).
5. `src/components/layout/nav-config.ts:120-181` — the authenticated nav data; the 9 hrefs live here.
6. `src/components/layout/floating-nav.tsx:710-725` — the `pathAlias` map; the one-line edit.
7. `git show --stat 2007fa7` — confirms the 9 stub files; the deletion list is derived from this.
8. `scripts/validate-nav-routes.ts:65-124` — the static route walker; the validator gates everything.
9. `src/components/layout/__tests__/floating-nav.test.tsx:395-407` — Build active-route test; must pass after the pathAlias change.
10. `e2e/floating-nav-product-discovery.spec.ts:268-294` — route validity test 10; confirms the 3 static routes (`/dashboard`, `/documentation`, `/dashboard/swarm`) still return 200.

---

## Risks and Gotchas (the things that will trip you up)

1. **Frontend workdir is `~/FlowmannerV2-frontend/`, not `/opt/flowmanner/frontend/`.** Verify with `git status` in both trees. Backend at `/opt/flowmanner/backend/` — DO NOT TOUCH.

2. **Local commit `2007fa7` shape matters for the amend.** If `2007fa7` is still the most recent local commit AND it only added the 9 stub files, T4 can `git commit --amend` cleanly with the new fixes on top. If `2007fa7` has been touched, mixed with other changes, or is no longer HEAD, T4 must create a fresh local fix commit instead. Check with `git show --stat 2007fa7` first.

3. **The pathAlias update is NOT optional.** Remapping Build to `/missions/builder` makes the `pathAlias` map the only thing keeping the Build nav item highlighted when the user is on `/en/missions`. Skip the pathAlias line → test 11 fails → F2 rejects.

4. **The route validator is static — it walks the filesystem, not runtime.** After deletion, the 9 stub paths no longer appear in the route tree, and the nav-config no longer points at them, so the validator reports 39 [OK], 0 [MISSING]. If the validator reports MISSING for any of the 9 NEW target routes (`/missions/builder`, `/runs`, etc.), the walker is wrong — fix the walker, do NOT change the nav.

5. **Pre-commit hook needs `PRE_COMMIT_ALLOW_NO_CONFIG=1`.** There is no `.pre-commit-config.yaml` in this repo, so the hook silently aborts without that env var. Do NOT use `--no-verify` — it bypasses lint and tests.

6. **9 deletions, 2 edits, 1 commit.** The diff stat for the amend should be: 1 file modified (`nav-config.ts`), 1 file modified (`floating-nav.tsx`), 9 files deleted. Anything else = scope creep = F4 reject.

7. **Real route pages live under `(dashboard)` route group, which is URL-transparent.** When checking "did we accidentally delete a real page", look for the path WITHOUT the `(dashboard)` segment: `src/app/[locale]/(dashboard)/missions/builder/page.tsx` is the file for `/missions/builder`. The route group is invisible in URLs.

8. **Evidence files are required.** Same rule as the parent boulder — F1, F2, F3 reviews grep for the evidence file paths. Don't ship without them.

9. **Frontend deploy takes ~4 minutes and is not retriable on timeout.** Per AGENTS.md: if a deploy times out, check `docker compose ps` on the VPS before considering a retry. The user reviews the diff first; they decide when to deploy. This boulder stops at "local commit ready".

---

## Out of Scope (deferred — do NOT pull in)

- Adding orphaned nav entries (Team, Graphs, Blueprints, Templates, Triggers, Analytics, Costs, RAG, Workflows, Files) — separate boulder.
- Real product surface implementations (e.g., the marketplace's My Installed view actually fetching data) — those pages exist, but their business logic is not this boulder's concern.
- Backend changes of any kind.
- Public nav structure for anonymous users.
- Drag/reorder, personalization, recommendations, analytics.
- Auth-store / auth-provider edits. Consumed only.
- Lighthouse / INP / CLS regression testing.

---

## Handoff Notes

- The plan at `.sisyphus/plans/flowmanner-nav-remap-real-routes.md` is the source of truth for per-task detail. This document is the operational briefing — read the plan for "What to do" + "QA scenarios" per task; use this doc for cross-task rules, guardrails, and risks.
- The parent handoffs (`flowmanner-nav-after-login-boulder-handoff.md`, `floating-nav-deferred-routes-handoff.md`) frame why this boulder exists. Read the deferred-routes handoff first if you want the full context on the Option A vs B decision and the `2007fa7` commit.
- Metis was unavailable during planning (tool quota), so the plan was self-reviewed with an explicit gap log. The guardrails above compensate.
- After F1–F4 all APPROVE and the user gives okay, register the boulder as complete in `.sisyphus/boulder.json` and append evidence file paths to `boulder.json:evidence_files` (pattern from prior chunks).
