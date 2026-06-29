# Exit Audit — /graphs vs /blueprints Route Consolidation

**Date:** 2026-06-29
**Options applied:** 1 (import fix) + 2 (route consolidation)
**Commits:** `f93ef84` (Option 1), `7fb39c7` (Option 2)

---

## WHAT CHANGED

### Option 1 (commit `f93ef84`)

| File | Δ | Description |
|------|---|-------------|
| `src/app/[locale]/(dashboard)/graphs/page.tsx` | +2/-2 | Renamed import + JSX from `GraphsClient` → `BlueprintsClient` |

### Option 2 (commit `7fb39c7`)

| File | Δ | Description |
|------|---|-------------|
| `src/app/[locale]/(dashboard)/graphs/` | -954 | **Deleted** entire route directory (4 files) |
| `src/app/[locale]/(dashboard)/blueprints/[id]/executions/page.tsx` | +14 | **Created** — moved from `/graphs/[id]/executions/` |
| `src/app/[locale]/(dashboard)/blueprints/[id]/executions/page-client.tsx` | +940 | **Created** — moved from `/graphs/[id]/executions/`, back-nav updated |
| `src/lib/command-palette/actions.ts` | -2 | Removed `/graphs` entry (line 50-51) |
| `next.config.ts` | +4/-4 | Redirects: `/graphs` → `/blueprints` (was → `/missions`) |
| `src/i18n/locales/{en,de,es,fr,ja}.json` | -2 each | Removed `graphs.*` i18n keys from all 5 locales |

---

## WHAT WAS IMPLEMENTED

### Option 1: Fixed misnamed import
- `graphs/page.tsx` imported `GraphsClient` but `./page-client.tsx` exports `BlueprintsClient`
- 2-line fix aligning import name with actual export

### Option 2: Consolidated /graphs into /blueprints
1. **Moved** `/graphs/[id]/executions/` → `/blueprints/[id]/executions/`
2. **Updated** executions page back-nav: `/${locale}/graphs` → `/${locale}/blueprints`
3. **Removed** `/graphs` entry from command palette
4. **Replaced** `next.config.ts` redirects: `/graphs` → `/blueprints` and `/graphs/:id/executions` → `/blueprints/:id/executions`
5. **Removed** `graphs.*` i18n keys from all 5 locales
6. **Deleted** entire `/graphs/` route directory via `git rm -r`

---

## CODE REVIEWER NOTES

Two functional concerns raised (both are expected trade-offs of Option 2):

1. **"My Blueprints" management UI deleted.** The `graphs/page-client.tsx` (432 lines) had CRUD features: delete, sort, pagination, edit-to-mission-builder. The surviving `blueprints/page-client.tsx` (270 lines) is a public catalog without these. This was an intentional trade-off — the user chose to consolidate.

2. **Executions page has no inbound links.** The new `/blueprints/[id]/executions/` route exists and the redirect from `/graphs/[id]/executions` works, but nothing in the app navigates to it anymore. The only links were in the deleted `graphs/page-client.tsx`. The `/blueprints` page-client doesn't link to executions. This is a known gap for a follow-up.

---

## VERIFICATION

| Gate | Result |
|------|--------|
| `tsc --noEmit` | ✅ Clean (after `.next` cache clean — stale validator.ts had references to deleted `/graphs` routes) |
| `eslint` on touched files | ✅ Clean (2 pre-existing `react-hooks/set-state-in-effect` warnings in moved executions page) |
| `vitest run` | 846/849 pass — 3 pre-existing failures in `WhyDrawer` (unrelated `useTranslations` context) |
| `next build` | ✅ Compiled successfully, exit code 0 |

## NUMSTAT (Option 2 only)

```
 0   2  src/app/[locale]/(dashboard)/graphs/[id]/executions/page-client.tsx
 0   2  src/app/[locale]/(dashboard)/graphs/[id]/executions/page.tsx
 0 432  src/app/[locale]/(dashboard)/graphs/page-client.tsx
 0  14  src/app/[locale]/(dashboard)/graphs/page.tsx
940   0  src/app/[locale]/(dashboard)/blueprints/[id]/executions/page-client.tsx
 14   0  src/app/[locale]/(dashboard)/blueprints/[id]/executions/page.tsx
 4   8  src/i18n/locales/de.json
 4   8  src/i18n/locales/en.json
 4   8  src/i18n/locales/es.json
 4   8  src/i18n/locales/fr.json
 4   8  src/i18n/locales/ja.json
 2   4  src/lib/command-palette/actions.ts
```

## COMMITS

```
f93ef84 fix(nav): rename misnamed GraphsClient import to BlueprintsClient in /graphs route
7fb39c7 fix(nav): consolidate /graphs into /blueprints, add redirects
```

## NEXT SESSION HANDOFF

Both options applied and pushed to `origin/master`. The `/graphs` route no longer exists — all blueprint content lives under `/blueprints`. Next.js redirects handle legacy `/graphs` URLs. Two known gaps remain:
1. The "My Blueprints" management features (CRUD, sort, delete) from the old `graphs/page-client.tsx` are not ported to `blueprints/page-client.tsx`
2. No in-app navigation reaches `/blueprints/[id]/executions/` (the executions page exists but nothing links to it)

Neither requires a deploy. The user decides when to deploy.

## FILES THIS AGENT DID NOT TOUCH

- Backend code
- Deploy scripts (`deploy-frontend.sh`, etc.)
- `src/lib/sdk/services/GraphsService.ts` (generated SDK, out of scope)
- `src/components/mission-builder/FlowEditor.tsx` (API calls to `/api/v1/graphs/...` are out of scope)
- `src/hooks/__tests__/useExecutionPoll.test.ts` (no `/graphs` references, verified)
