# Handoff: Scaffold the 9 Deferred Routes (floating-nav boulder downstream)

**Date:** 2026-06-16
**Boulder:** `flowmanner-nav-after-login-deep-dive` (COMPLETE — F1✓ F2✓ F3✓ F4 APPROVE)
**Branch:** `master` @ `fde54d9`
**Source plan:** `.sisyphus/plans/flowmanner-nav-after-login-deep-dive.md`
**Status:** NOT STARTED. Next "start work" cycle picks this up.

---

## TL;DR

The floating-nav boulder shipped. The signed-in nav works (10/12 e2e pass, 2 react-scan env failures accepted). But 9 hrefs in `nav-config.ts` point to routes that don't exist under `src/app/[locale]/`. Clicking the Build / Run / Market / Tools nav items 404s on the live site. This handoff is the deferred fix.

**9 missing routes (from T4 validator output):**
- `/dashboard/build` (1)
- `/dashboard/run` (1)
- `/dashboard/market` (1)
- `/dashboard/market/{my-installed, my-listings, create-listing}` (3)
- `/dashboard/tools` (1)
- `/dashboard/tools/{hub, memory-inspector}` (2)

**Critical path:** read 2 fix options below → user picks → worker scaffolds OR remaps → re-run `pnpm validate-nav-routes` → re-run e2e test 10 (route validity) → commit + push.

---

## Repo state (verified 2026-06-16)

- Workdir: `/home/glenn/FlowmannerV2-frontend`
- Branch: `master` @ `fde54d9` (pushed to origin)
- Boulder commits: 13 (since baseline `b8e302b`). F1-F4 reports at `.sisyphus/evidence/final-qa/`.
- Deployed: VPS is live with the new nav. 404s reproducible by clicking the affected nav items.
- Backend: `/opt/flowmanner/backend/` — DO NOT TOUCH.

## The 2 fix options

### Option A — Scaffold placeholder routes (keeps nav IA as designed)
Create 9 `page.tsx` files under `src/app/[locale]/dashboard/{build,run,market,market/*,tools,tools/*}/`. Each is a minimal placeholder showing the group label + "Coming soon" or stub content. Future boulder wires the real implementations.

**Pros:** nav IA stays as the plan designed. Future missions/tools work has a landing spot. Tests 6, 7, 8 (Swarm items → /dashboard/swarm, Docs top-level, no-overlap) keep working unchanged.
**Cons:** 9 placeholder files in the tree. Future boulder has to replace them with real content.

### Option B — Remap nav-config.ts hrefs to existing routes (cleaner code)
Change the 9 hrefs in `src/components/layout/nav-config.ts` to point to real existing routes:
- `/dashboard/build` → `/missions/builder` (or `/blueprints`)
- `/dashboard/run` → `/runs`
- `/dashboard/market` → `/marketplace`
- `/dashboard/market/{my-installed, my-listings, create-listing}` → `/marketplace/{my-installed, my-listings, create-listing}`
- `/dashboard/tools` → `/memory-inspector` (or drop the `Tools` group entirely if there's no other real destination)
- `/dashboard/tools/{hub, memory-inspector}` → `/browser`, `/memory-inspector`

**Pros:** zero placeholder files. Nav links go to real working pages.
**Cons:** changes the nav's designed IA. The `Market` group becomes `Marketplace`, `Tools` becomes `Memory Inspector` (or similar). May confuse users who expect the original group names.

**Recommend Option A** — preserves the design, keeps the door open for proper product surfaces later. The 9 routes are clearly the IA targets, so having the landing pages exist (even as stubs) signals the product direction.

## Files the next agent should read first

1. `src/components/layout/nav-config.ts` — the 9 hrefs at lines 130 (build), 135 (run), 155+158+162+166 (market + subs), 174+175+178 (tools + subs)
2. `.sisyphus/evidence/task-4-validator-output.txt` — T4's full validator output (9 MISSING routes)
3. `.sisyphus/evidence/final-qa/f3-manual-qa.md` — test 10 (route validity) baseline; currently passes for the 3 routes it tests but doesn't cover the 9 missing ones
4. `.sisyphus/evidence/final-qa/f4-scope-fidelity.md` — note the F4 contamination override (`8c3f579` PropertiesPanel fix accepted as in-scope)
5. `.sisyphus/handoffs/flowmanner-nav-after-login-boulder-handoff.md` — the full boulder briefing if context is needed

## Verification

```bash
cd ~/FlowmannerV2-frontend
pnpm validate-nav-routes                           # exit 0, 39 [OK], 0 [MISSING]
pnpm test:e2e floating-nav-product-discovery       # test 10 now passes for all 3 clicked routes
git diff --stat                                    # 9 new page.tsx files (Option A) or 1 modified nav-config.ts (Option B)
```

## Out of scope

- No backend changes
- No real implementations of /dashboard/build, /run, /market, /tools — those are separate boulders
- No changes to the floating-nav.tsx component (already complete)
- No changes to nav-config.ts OUTSIDE the 9 hrefs
- No changes to locale files
- No push without user review (per AGENTS.md)

## Handoff notes

- Boulder F4 was REJECTED on a 1-issue contamination (`8c3f579` PropertiesPanel fix, 2 lines, unrelated to nav). User chose Option 1 (override, keep `8c3f579`). F4 verdict = APPROVE. The override is documented in `.sisyphus/evidence/final-qa/f4-scope-fidelity.md`.
- The 9 routes are documented as "downstream blocker, F1-F4 gates" per T4's output. The user accepted that. NOW they want them fixed.
- e2e tests 3 and 5 still fail (react-scan-root overlay in dev mode). Environmental, not a code issue. Don't chase.
- Boulder source tree is clean. Only 78 dirty files, all non-source (`.sisyphus/evidence/`, `test-results/`, `.hermes/`).
