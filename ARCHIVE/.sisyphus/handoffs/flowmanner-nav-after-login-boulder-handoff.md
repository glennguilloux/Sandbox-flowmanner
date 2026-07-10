# Handoff: Flowmanner Post-Login Nav (Two-Tier Product Discovery)

**Date:** 2026-06-16
**Boulder name:** `flowmanner-nav-after-login-deep-dive`
**Branch:** main @ `8b28546`
**Status:** PLAN APPROVED, NOT STARTED. `/start-work flowmanner-nav-after-login-deep-dive` will register the boulder and launch Wave 1.
**Source plan (Sisyphus format, 939 lines):** `.sisyphus/plans/flowmanner-nav-after-login-deep-dive.md`
**Sibling plan (earlier, narrower scope — superseded by this boulder):** `.sisyphus/plans/flowmanner-nav-two-tier-product-discovery.md`

---

## TL;DR

Reframe Flowmanner's signed-in nav from "public nav with right-side actions" into a dedicated two-tier product-discovery nav. Anonymous users keep the current public nav. Loading state renders the public shell to avoid signed-out flicker. Right-side account actions collapse into one account menu to fit 1280×800.

**Deliverables (6 files):**

1. `src/components/layout/nav-config.ts` — typed schema (`NavConfig`), `publicNav`, `authenticatedNav`, route constants
2. `src/components/layout/floating-nav.tsx` — auth-state branching, two-tier signed-in rendering, account-menu collapse, drag disable for signed-in, deterministic active-route highlighting
3. `messages/{en,de,es,fr,ja}.json` — 16+ new nav keys, full parity, REAL translations in non-EN files
4. `scripts/validate-nav-routes.ts` + `package.json` script entry
5. `src/components/layout/__tests__/floating-nav.test.tsx` — extended Vitest
6. `e2e/floating-nav-product-discovery.spec.ts` — new Playwright spec at 1280×800

**Critical path:** T1 → T3 → T5 → F1–F4

---

## Execution Protocol (read this first — 30 seconds)

`/start-work flowmanner-nav-after-login-deep-dive` runs this. Do not skip waves; dependencies are real.

```
Wave 1 (parallel, 2 agents):  T1 nav-config      T2 i18n parity
Wave 2 (parallel, 2 agents):  T3 FloatingNav     T4 route validator
Wave 3 (parallel, 2 agents):  T5 Vitest          T6 Playwright
Wave FINAL (parallel, 4 agents): F1 plan compliance  F2 code quality  F3 manual QA  F4 scope fidelity
→ Present consolidated F1–F4 → wait for user okay → mark complete
```

**File-ownership rule (will get violated if not enforced):** T3 owns `floating-nav.tsx` EXCLUSIVELY in Wave 2. T4 must NOT touch it. T4 may run `pnpm validate-nav-routes` to verify, but only against the new `nav-config.ts` (T1's file). If you see a wave-2 agent also editing `nav-config.ts` outside of T1, that's a bug — stop and reassign.

**Commit order matters:** T1, T2, T4, T5, T6 can commit independently in their respective waves. T3 should be the LAST commit of Wave 2 because T5 + T6 import the new render output. Don't rebase the wave order.

---

## The 8 Hard Guardrails (these WILL get violated unless the executor reads them)

These are the "Must NOT Have" items. F1 and F4 reviews will reject if any are present. Each is non-negotiable:

1. **NO** generic `More` or `Menu` bucket in the signed-in nav. Tiers are: top = `Chat`, `Build`, `Run`, `Swarm`, `Market`, `Tools`; bottom = `Docs`, `Resources`, `Company`. Period.
2. **NO** invented Swarm routes. All 5 Swarm items (`Swarm Orchestration`, `Executions`, `Debate`, `Handoffs`, `Escalation`) point to `/dashboard/swarm`. Deep-link query params are deferred. Do NOT create `/swarm/debate` etc.
3. **NO** English strings dropped into non-English locale files. T2 must add real DE/ES/FR/JA translations. F1 rejects on byte-identical English in `de.json` for `nav.build` / `nav.market` / `nav.company`.
4. **NO** drag/reorder for signed-in product nav. Public nav keeps its existing drag.
5. **NO** personalization, recommendations, or analytics. Out of scope.
6. **NO** changes to public nav structure for anonymous users.
7. **NO** admin as a product nav bucket. Admin stays in the account menu, gated on `user.is_admin`.
8. **NO** changes to `auth-store.ts` or `auth-provider.tsx`. They are consumed, not modified. F4 will grep for any diff to those files and reject.

The TypeScript schema in the plan is also locked — implementers MUST use the exact interface names (`NavConfig`, `NavItem`, `NavGroup`, `PublicNavConfig`, `AuthenticatedNavConfig`, `NavTier`). Inventing a new shape = rejection.

---

## Active-Route Matching Rule (deterministic, no fuzzy)

An item is active when `pathname === item.href` OR `pathname.startsWith(item.href + "/")`. A group is active when any child is active. Apply via `data-active="true"` attribute (Playwright selectors depend on this). Use `usePathname()` from `next/navigation`.

## Width Budget (1280×800 is the target viewport)

`max-w-6xl` content (~1152px) → with `px-6` → inner ~1104px. Two rows of triggers + visible Workspace + NotificationBell + compact account menu. F1 expects `boundingBox.width <= 1104` for the nav container. If first pass is too wide: shorten labels or tighten account menu — DO NOT add a `More` bucket, DO NOT change the product IA.

## Loading State

`isLoading === true` from `useAuth()` → render the public nav shell. NO signed-in actions visible. This is the flicker fix. `src/stores/auth-store.ts:141-158` defines `isLoading`; `src/providers/auth-provider.tsx:36-45` exposes it via `useAuth()`.

## data-testid Contract (Playwright + Vitest depend on these)

- `data-testid="nav-tier-top"` and `data-testid="nav-tier-bottom"` on tier container rows
- `data-testid="account-menu"` on the account menu trigger
- `data-testid="notification-bell"` and `data-testid="workspace-button"` on those actions
- `data-nav-group="<group-id>"` on each group trigger (ids: `build`, `run`, `swarm`, `market`, `tools`, `docs`, `resources`, `company`)
- `data-active="true"` on currently-active item/group

T3 MUST add these. T5 and T6 MUST query them. If T3 ships without them, T5/T6 will fail with selector timeouts.

---

## Files the Next Agent Should Read First

In order:

1. `.sisyphus/plans/flowmanner-nav-after-login-deep-dive.md` — the playbook. Read sections "Context → Route Inventory" and "Design Decisions" first; task details are below.
2. `src/components/layout/floating-nav.tsx:49-87` — current hardcoded nav data; T1 extracts this verbatim into `publicNav`.
3. `src/components/layout/floating-nav.tsx:423-424` and `710-775` — current `useAuth()` call site + signed-in right-side actions. T3 refactors these.
4. `src/stores/auth-store.ts:141-158` — `isLoading` semantics. T3 must consume; do NOT modify.
5. `src/providers/auth-provider.tsx:36-45` — `useAuth()` return shape. T3, T5, T6 all depend on this.
6. `src/types/auth.ts:11` — `User.is_admin`. T1 conditionally includes `Admin` in account menu.
7. `src/components/layout/__tests__/floating-nav.test.tsx` — existing Vitest patterns. T5 extends, do not rewrite.
8. `e2e/` — pick 2 existing specs to match the auth-fixture / page-object style for T6.
9. `package.json` scripts section — for the `validate-nav-routes` script entry (T4).
10. `messages/en.json` — existing `nav.*` key naming convention. T2 mirrors to de/es/fr/ja.

---

## Risks and Gotchas (the things that bit us before)

1. **Frontend workdir is `~/FlowmannerV2-frontend/`, not `/opt/flowmanner/frontend/`.** The plan's file paths are relative to `~/FlowmannerV2-frontend/`. Backend source edits are at `/opt/flowmanner/backend/` (this boulder touches frontend only — no backend changes). Verify with `git status` in BOTH trees before assuming where you are.

2. **No backend changes — the deploy is frontend-only.** Do NOT touch `backend/app/**`. Do NOT run `deploy-backend.sh`. The frontend ships via `bash /opt/flowmanner/deploy-frontend.sh` from the homelab, takes ~4 minutes, NEVER retry a deploy that timed out — check `docker compose ps` on VPS first.

3. **VPS is read-only.** All source edits happen on the homelab. The VPS rule from `AGENTS.md` is absolute: never edit files on the VPS directly.

4. **i18n translation discipline.** Non-English locale files MUST contain real translations. T2 verifier (F1) checks byte-equality on `nav.build` / `nav.market` / `nav.company` in de/es/fr/ja against the English source. If the executor uses DeepSeek/Claude for translations, it sometimes falls back to English — verify before committing. The F1 rejection evidence in similar past chunks has been "non-English value identical to English source string" — this is not a stylistic complaint, it's a hard fail.

5. **The route validator is static.** T4 walks `src/app/[locale]/` and checks every href in `nav-config.ts`. Dynamic segments `[locale]` and `[slug]` should be ignored for matching. Route groups `(...)` should be followed only if they contribute to the URL. If the validator reports `[MISSING] /chat` after the plan is correctly implemented, the walker is wrong — fix the walker, not the nav.

6. **The Swarm group has 5 items → 1 route.** The validator must report this as OK, not flag 4 duplicates. T1's QA scenario asserts `allSame: true` and `count: 5` for the swarm group.

7. **Drag-disabled assertion is a Vitest test.** T5 includes a regression check that the `Build` group does NOT have `draggable="true"` when signed in, and the public nav DOES (regression on the other side). Don't skip this — it guards a design decision.

8. **The "no More bucket" assertion is a Playwright test.** T6 must fail loudly if any element with text "More" or "Menu" appears in the signed-in nav container. Don't relax this assertion to make the test pass.

9. **Evidence files are required.** Every task has a `MUST` QA scenario that produces a file under `.sisyphus/evidence/task-{N}-*.{png,txt,log}`. F1, F2, F3 reviews check that the evidence exists. Implementer that skips the evidence and reports "tests pass" will be sent back to capture it.

10. **Pre-commit gate requires `PRE_COMMIT_ALLOW_NO_CONFIG=1`.** There is no `.pre-commit-config.yaml` in this repo, so the hook silently aborts without that env var. (Also: do not use `--no-verify` — it bypasses the lint and tests.)

---

## Verification (run after all waves complete)

```bash
# Frontend lint + build + unit tests + e2e
cd ~/FlowmannerV2-frontend
pnpm lint                                                       # clean
pnpm build                                                      # success
pnpm test -- floating-nav.test.tsx                              # all green
pnpm test:e2e floating-nav-product-discovery                    # all green at 1280×800

# Route validator
pnpm tsx scripts/validate-nav-routes.ts                         # exit 0, "All routes valid"

# Git hygiene — only nav + locale + test files should be touched
git diff --stat
```

The boulder is complete when F1, F2, F3, F4 all APPROVE and the user gives explicit okay.

---

## Out of Scope (deferred — do NOT pull in)

- Swarm deep links with `?tab=` query params. All 5 items → `/dashboard/swarm`. Period.
- Personalization, recommendations, analytics on the nav.
- Any backend changes. The plan is frontend-only.
- Changes to `auth-store.ts` / `auth-provider.tsx`. Consumed only.
- Public nav structure for anonymous users.
- A `deploy-frontend.sh` automation. Use the existing script per AGENTS.md.
- Lighthouse / INP / CLS regression testing. Not in the DoD.

---

## Handoff Notes

- The plan is the source of truth for task detail. This document is the operational briefing — read the plan for the "What to do" and "QA scenarios" sections per task; use this doc for the cross-task rules, guardrails, and risks.
- The `flowmanner-nav-two-tier-product-discovery.md` plan in the same dir is an EARLIER, narrower-scope artifact. It was superseded by the deep-dive plan. Don't use it; if a task references it, redirect to the deep-dive plan.
- Boulder registration updates `.sisyphus/boulder.json`. After F1–F4 all APPROVE and the user gives okay, mark the boulder `complete` in `boulder.json` and append evidence file paths to `boulder.json:evidence_files`. (Pattern from prior chunks — see `boulder.json` for shape.)
