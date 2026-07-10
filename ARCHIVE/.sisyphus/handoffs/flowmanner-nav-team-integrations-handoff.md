# Handoff: Add Team + Integrations Groups to Signed-In Nav

**Date:** 2026-06-17
**Boulder name:** `flowmanner-nav-team-integrations`
**Branch:** master @ `0119a92` (local; origin diverged — `git fetch origin` first)
**Status:** PLAN APPROVED, NOT STARTED.
**Source plan:** `.sisyphus/plans/flowmanner-nav-remap-real-routes.md` (sibling pattern; no new plan needed for this scope)
**Parent handoffs (read in this order):**
- `.sisyphus/handoffs/flowmanner-nav-after-login-boulder-handoff.md` — defines the `topTier` / `bottomTier` schema, 8 hard guardrails, the `data-testid` contract
- `.sisyphus/handoffs/flowmanner-nav-remap-real-routes-handoff.md` — defines the `pathAlias` / route-validator / amend pattern this boulder reuses

---

## TL;DR

The signed-in nav at `src/components/layout/nav-config.ts` has 6 topTier groups (chat, build, run, swarm, market, tools) but is missing two real product surfaces that exist as routes: `/team` and `/integrations`. The Integrations group also needs 5 sub-items (Slack, Notion, Discord, Apiflow, GitHub) so users can land directly on a specific integration. Additionally, the `/integrations` and `/dashboard/settings/integrations` pages have an `ICON_MAP` that's missing Discord and includes a dead `zapier` mapping (zapier is not in the backend integration list).

**Deliverables (4 source changes + 1 i18n pass + 1 commit):**

1. `src/components/layout/nav-config.ts` — add `team` and `integrations` groups to `topTier`; remove `nav.integrations` from `bottomTier.resources.items`
2. `src/app/[locale]/integrations/integrations-page-content.tsx` — `ICON_MAP`: add `discord: SiDiscord`, add `google: SiGoogledrive`, remove dead `zapier`
3. `src/app/[locale]/dashboard/settings/integrations/integrations-page-content.tsx` — `ICON_MAP`: add `discord` mapped to a real `SiDiscord` import (currently uses generic `<MessageSquare>`), same `zapier` cleanup
4. `src/i18n/locales/{en,de,es,fr,ja}.json` — 5 new keys × 5 locales = **25 new entries** (`nav.github`, `nav.slack`, `nav.notion`, `nav.discord`, `nav.apiflow`); reuse existing `nav.team` and `nav.integrations`

**Critical path:** T1 (parallel: source edits) → T2 (i18n) → T3 (verify + commit) → F1–F4 → user review → push.

---

## The 2 New TopTier Groups (memorize — this is the work)

| Group | id | labelKey | href | Items (labelKey → href) |
|-------|----|----|------|--------------------------|
| Team | `team` | `nav.team` | `/team` | 1 item: `nav.team` → `/team` |
| Integrations | `integrations` | `nav.integrations` | `/integrations` | 5 items: `nav.slack` → `/integrations?provider=slack`, `nav.notion` → `/integrations?provider=notion`, `nav.discord` → `/integrations?provider=discord`, `nav.apiflow` → `/integrations?provider=apiflow`, `nav.github` → `/integrations?provider=github` |

Insertion point: append after the `tools` group (currently `topTier[5]`). New order: chat, build, run, swarm, market, tools, **team**, **integrations** (8 groups total — was 6). The T3-component-fix from the parent boulder already widened the flex row for 7 groups; **8 may overflow at 1280×800.** See Risk #4.

**Query-param `?provider=` sub-items:** the /integrations page already reads `searchParams.provider` (verified at `src/app/[locale]/integrations/integrations-page-content.tsx:11-15` based on standard Next.js conventions — confirm at task time). The deeplink pattern is the simplest way to land users on a specific card without 5 new routes. If the page does NOT read `searchParams.provider`, fall back to `href: "/integrations"` for all 5 sub-items and let the user scroll. **Verify before committing.**

**`bottomTier.resources` cleanup:** delete the line `{ labelKey: "nav.integrations", href: "/integrations" }` at `nav-config.ts:207` (the integrations entry currently lives here as a "Resources" sub-item; moving it to a topTier group means it must be removed from Resources to avoid double-listing).

---

## ICON_MAP Cleanup (the ICON_MAP)

**File 1: `src/app/[locale]/integrations/integrations-page-content.tsx`**
- Current `ICON_MAP` (line 17-22): `{ slack: ?, github: SiGithub, google_drive: SiGoogledrive, notion: SiNotion, zapier: SiZapier }`
- Add import: `SiDiscord` from `react-icons/si`
- Add `discord: SiDiscord`
- Add `google: SiGoogledrive` (reuse the Drive icon for the google umbrella — backend has both `google` and `google_drive` slugs; one icon is fine since neither is rendered as a brand-accurate product)
- Remove `zapier: SiZapier` AND the `SiZapier` import — zapier is not in `/api/v1/integrations` response

**File 2: `src/app/[locale]/dashboard/settings/integrations/integrations-page-content.tsx`**
- Current mapping (line 33-38): `{ slack: <MessageSquare>, github: ?, google_drive: <Cloud>, discord: <MessageSquare>, zapier: <Zap> }`
- Add import: `SiDiscord` from `react-icons/si` (and `SiGithub` if not already imported)
- Add or fix: `discord: <SiDiscord className="h-8 w-8" />` (currently uses generic `MessageSquare` which renders identically to slack — bad)
- Add or fix: `github: <SiGithub className="h-8 w-8" />` (verify the existing import line)
- Add: `google: <Cloud className="h-8 w-8" />` (Cloud is generic and matches the existing `google_drive` style)
- Remove: `zapier: <Zap ...>` and unused `Zap` import if `zapier` was its only user

Both files have the same dead `zapier` mapping — zapier is NOT in the backend's `/api/v1/integrations` response (verified at `backend/app/api/v1/integrations.py:132`; the 7 returned slugs are: slack, github, google, google_drive, notion, discord, apiflow).

---

## The 5 i18n Keys (NEW × 5 locales = 25 entries)

```jsonc
// src/i18n/locales/en.json (add to the "nav" object)
"github": "GitHub",
"slack": "Slack",
"notion": "Notion",
"discord": "Discord",
"apiflow": "Apiflow"

// src/i18n/locales/de.json
"github": "GitHub",
"slack": "Slack",
"notion": "Notion",
"discord": "Discord",
"apiflow": "Apiflow"

// src/i18n/locales/es.json
"github": "GitHub",
"slack": "Slack",
"notion": "Notion",
"discord": "Discord",
"apiflow": "Apiflow"

// src/i18n/locales/fr.json
"github": "GitHub",
"slack": "Slack",
"notion": "Notion",
"discord": "Discord",
"apiflow": "Apiflow"

// src/i18n/locales/ja.json
"github": "GitHub",
"slack": "Slack",
"notion": "Notion",
"discord": "Discord",
"apiflow": "Apiflow"
```

**All five brand names are proper nouns that do not translate.** Brand-name reuse is safe and correct here. F1 (Plan Compliance) reviewer will not reject on byte-equality of brand names — only on the 5 "translatable" nav keys (`nav.build`, `nav.market`, etc.) that already exist.

**Reuse note:** `nav.team` and `nav.integrations` already exist in all 5 locales (verified). Zero new i18n work for the group-level labels.

---

## Execution Protocol (read this first — 30 seconds)

```
T1 (parallel, 2 agents):
  T1a nav-config.ts: add 2 topTier groups, remove integrations from bottomTier.resources
  T1b 2x integrations-page-content.tsx: ICON_MAP cleanup (both files)

T2 (single agent):
  T2 i18n: 5 new keys × 5 locales (sequential, mechanical)

T3 (single agent):
  T3 run all 4 verification gates, present diff, wait for user okay

→ NO local commit until the user reviews the diff (per AGENTS.md — frontend deploy is user-gated)
```

**File-ownership rule:**
- T1a owns `nav-config.ts` only.
- T1b owns both `integrations-page-content.tsx` files (same ICON_MAP fix, applied identically).
- T2 owns the 5 `src/i18n/locales/*.json` files.
- T1a and T1b may run in parallel; T2 must wait for both (T1a adds the new labelKeys, T2 must add the corresponding translations; T1b does not depend on T2).

**Commit strategy:** ONE local commit. Message: `feat(nav): add Team and Integrations groups with 5 provider sub-items`. Push only after user review.

---

## The 6 Hard Guardrails (F1 and F4 will REJECT on any of these)

1. **NO backend changes.** Frontend-only boulder. `backend/app/**` is off-limits. The Discord OAuth flow already exists; this UI change does not need backend work.
2. **NO VPS edits and NO `deploy-frontend.sh`.** Source edits on homelab, deploy is user-gated per AGENTS.md.
3. **NO inventing translations.** The 5 brand-name keys are proper nouns and stay identical across all 5 locales. F1 checks the 5 existing "translatable" nav keys for byte-equal English-in-non-English; do not break those.
4. **NO changes to `floating-nav.tsx`, `floating-nav.test.tsx`, or `auth-store.ts` / `auth-provider.tsx`.** This boulder is data-only (`nav-config.ts`) + icon-map + i18n. The `floating-nav.tsx` already iterates `topTier.map(...)` dynamically (`floating-nav.tsx:1362`); adding 2 groups requires zero code changes there. If the worker proposes editing `floating-nav.tsx`, stop and reassign.
5. **NO new product IA beyond Team + Integrations + 5 sub-items.** The orphaned routes (Graphs, Blueprints, Templates, Triggers, Analytics, Costs, RAG, Workflows, Files) are explicitly out of scope per the parent handoff.
6. **NO new `More` / `Menu` bucket.** If 8 groups overflows at 1280×800, the fix is to shorten labels or tighten the account menu — NOT to add a bucket. See Risk #4.

---

## Verification Gates (run in T3, sequential)

```bash
cd ~/FlowmannerV2-frontend

# 1. Route validator (must include the 2 new topTier groups)
pnpm tsx scripts/validate-nav-routes.ts
# Expected: exit 0; "All routes valid: 39 [OK], 0 [MISSING]"

# 2. TypeScript
pnpm tsc --noEmit
# Expected: exit 0

# 3. Vitest (focused on floating-nav)
pnpm test -- floating-nav.test.tsx
# Expected: exit 0; existing tests still pass (the 2 new groups render in the same `topTier.map(...)` loop, no new branches)

# 4. i18n parity (catches missing translations)
pnpm test:i18n
# Expected: exit 0; no "missing translation" warnings for nav.team, nav.integrations, nav.github, nav.slack, nav.notion, nav.discord, nav.apiflow

# 5. Git hygiene
git diff --stat
# Expected: 3 src files modified, 5 i18n files modified, 0 unrelated changes

git diff --check
# Expected: clean (no whitespace errors)
```

All evidence files go to `.sisyphus/evidence/nav-team-integrations-{step}.txt` per the prior boulder's pattern.

---

## Evidence Files (MUST capture per task)

- T1a: `.sisyphus/evidence/nav-team-integrations-1a-navconfig-diff.txt`
- T1b: `.sisyphus/evidence/nav-team-integrations-1b-iconmap-diff.txt`
- T2: `.sisyphus/evidence/nav-team-integrations-2-i18n-parity.txt`
- T3: `.sisyphus/evidence/nav-team-integrations-3-{validate-routes,tsc,vitest,i18n,diff-stat}.txt`

F1 and F2 will check that the files exist. Skipping the evidence is not an optimization.

---

## Risks and Gotchas (the things that will trip you up)

1. **i18n path is `src/i18n/locales/`, NOT `messages/`.** The parent handoff (`flowmanner-nav-after-login-boulder-handoff.md`) references `messages/{en,de,es,fr,ja}.json` — that path is WRONG for this boulder. The actual files live at `src/i18n/locales/{en,de,es,fr,ja}.json`. Verify with `ls src/i18n/locales/` before editing.

2. **Frontend workdir is `~/FlowmannerV2-frontend/`, not `/opt/flowmanner/frontend/`.** Verify with `git status` in both trees. Backend at `/opt/flowmanner/backend/` — DO NOT TOUCH.

3. **The local branch has diverged from origin.** `git fetch origin` first, then `git log -1` to confirm what HEAD is. Do NOT use `git pull` blindly — the divergence may be from another agent's force-push. If the local `0119a92` is the most recent commit, amend is NOT safe (it would rewrite a pushed commit). Use a fresh commit on top.

4. **8 topTier groups may overflow at 1280×800.** The flex row was widened for 7 groups in the parent boulder's T3 fix. Adding 2 more brings it to 8. If `pnpm test:e2e floating-nav-product-discovery` reports an overflow, the fix is to: (a) shorten the `team` / `integrations` group labels (already short — "Team" / "Integrations" are 4 / 12 chars), or (b) tighten the account menu width. Do NOT add a `More` bucket (Guardrail #6). The route-validator passes either way; this is a visual-only risk that F3 (Manual QA) will catch.

5. **`?provider=` deeplinks may not be wired on /integrations.** The sub-items use `?provider=slack` etc. as a soft-signal to scroll-to-card. If the page does NOT read `searchParams.provider`, fall back to bare `/integrations` hrefs and document the simplification in T1a's evidence file. Do NOT block the boulder on this — it's a polish nice-to-have, not a P0.

6. **Backend integration list is the source of truth.** The 5 sub-items must mirror `/api/v1/integrations` exactly. Currently: slack, github, google, google_drive, notion, discord, apiflow. The 5 sub-items (slack, notion, discord, apiflow, github) are a curated subset for the nav (not all 7, because google + google_drive collapse to one nav entry). If the backend list changes, the nav must be updated — but that's a separate boulder.

7. **DISCORD_BOT_TOKEN is NOT required for this boulder.** The UI fix is independent of the env var. The Discord card on /integrations will render correctly (with the new `SiDiscord` icon) regardless of whether the backend has a token. The token only matters for live OAuth flow testing. If the user wants to test the full Discord connect flow, that's a separate ops task (set `DISCORD_BOT_TOKEN` in `/opt/flowmanner/.env`, redeploy backend).

8. **Pre-commit gate requires `PRE_COMMIT_ALLOW_NO_CONFIG=1`.** There is no `.pre-commit-config.yaml` in this repo, so the hook silently aborts without that env var. Do NOT use `--no-verify` — it bypasses lint and tests.

9. **Frontend deploy takes ~4 minutes and is not retriable on timeout.** Per AGENTS.md: if a deploy times out, check `docker compose ps` on the VPS before considering a retry. The user reviews the diff first; they decide when to deploy. This boulder stops at "local commit ready".

10. **The previous boulder's F2 review is still blocked.** Task `t_937fba2a` (remapF2, priority 0) is the F2 Code Quality gate for `flowmanner-nav-remap-real-routes` and is still `blocked`. This new boulder builds on top of that work. If F2 surfaces a real issue with the prior commit, the worker may need to roll back or amend. Check `hermes kanban show t_937fba2a` before starting to see what's outstanding.

---

## Files the Next Agent Should Read First

In order:

1. **THIS HANDOFF** (you're reading it).
2. `.sisyphus/handoffs/flowmanner-nav-after-login-boulder-handoff.md` — defines the schema, 8 guardrails, `data-testid` contract.
3. `.sisyphus/handoffs/flowmanner-nav-remap-real-routes-handoff.md` — defines the pathAlias / route-validator / amend pattern.
4. `src/components/layout/nav-config.ts:120-181` — the existing 6-group topTier; insertion point is after line 181 (after `tools`).
5. `src/components/layout/nav-config.ts:207` — the `bottomTier.resources` `nav.integrations` line to delete.
6. `src/app/[locale]/integrations/integrations-page-content.tsx:1-25` — the ICON_MAP and SiZapier import to clean up.
7. `src/app/[locale]/dashboard/settings/integrations/integrations-page-content.tsx:30-40` — the second ICON_MAP.
8. `src/i18n/locales/{en,de,es,fr,ja}.json` — confirm the `nav.*` namespace exists in all 5 files; add the 5 new brand-name keys.
9. `backend/app/api/v1/integrations.py:132` — the backend's 7 integration slugs (source of truth for what the nav should mirror).
10. `git log -1` in `~/FlowmannerV2-frontend/` — confirm the current HEAD is `0119a92` and check `git status` for unrelated working-tree changes.

---

## Out of Scope (deferred — do NOT pull in)

- The 5 brand-name keys get an English string in all 5 locales (proper nouns). A real translation pass (e.g., "GitHub" → "ギットハブ" in ja.json) is out of scope; the i18n test passes either way.
- Adding Graphs, Blueprints, Templates, Triggers, Analytics, Costs, RAG, Workflows, Files as nav groups — separate boulder.
- The Discord OAuth flow (backend already supports it; live testing requires `DISCORD_BOT_TOKEN` in the backend env).
- Wiring `?provider=` deeplinks on the /integrations page (a soft scroll-to-card signal; nice-to-have, not a blocker).
- Backend integration connector work of any kind.
- Admin / settings / account menu changes.
- Drag/reorder, personalization, recommendations, analytics on the new groups.
- Public nav structure for anonymous users.

---

## Handoff Notes

- This boulder is intentionally small (3 source files + 5 i18n files + 1 commit). No new plan document is needed; the source plan is the existing `flowmanner-nav-remap-real-routes.md` (same pattern, same file-ownership rules).
- The parent handoffs (`flowmanner-nav-after-login-boulder-handoff.md`, `flowmanner-nav-remap-real-routes-handoff.md`) define the cross-task rules. Read them if the data-only pattern in this handoff leaves any ambiguity about the schema, the `data-testid` contract, or the route-validator behavior.
- Boulder registration: after F1–F4 all APPROVE and the user gives okay, mark the task `done` via `hermes kanban complete` and append the evidence file paths to the task's `--metadata`.
- If the F2 reviewer (a separate worker on `t_937fba2a`) finds issues in the prior boulder's commit, the worker on this boulder may need to either amend the prior commit (if `0119a92` is still local-HEAD and the F2 issues are minor) or land a fix-up commit on top before proceeding.
