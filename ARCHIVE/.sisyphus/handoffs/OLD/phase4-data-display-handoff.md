# Handoff: Phase 4 — Data display (TanStack Table, Recharts, date-fns)

> **Phase 4 of the awesome-react adoption plan.**
> Source plan: `/opt/flowmanner/.sisyphus/plans/frontend-awesome-react-adoption.md` (Phase 4, §2).
> **Owner:** Frontend sub-agent or human. **Status:** READY to run.
> **Repo:** `/home/glenn/FlowmannerV2-frontend` (`master`, remote `glennguilloux/flowmanner`).
> **Current baseline checked:** `cec891f (HEAD -> master, origin/master, origin/HEAD) Phase 3 — Radix primitives + shadcn wrappers`.
> **Do not edit:** `/opt/flowmanner/frontend/` or the VPS directly. Source changes belong in the frontend repo; deploy only after user approval.

---

## 0. Critical pre-decisions

### 0.1 Phase 4 is a data-display phase, not a form or motion phase

Phase 4 migrates sortable/filterable/paginated/virtualized lists, charts, and date formatting. Keep the scope separate:

- Do **not** rewrite Phase 2 form state just because a table or chart component is touched.
- Do **not** start Phase 5 motion, kbar, DnD, or Storybook work.
- Do **not** add new backend API contracts unless the current frontend data already needs a missing field for sorting/filtering.

### 0.2 Current repo is already dirty from earlier work

As of the baseline check, the frontend working tree is not clean. It includes existing Phase 2/Phase 3 evidence and unrelated modified/untracked files. Stage only files that belong to Phase 4.

Before editing or committing:

```bash
cd /home/glenn/FlowmannerV2-frontend
git status --short
git fetch origin
git log -1 --oneline --decorate
```

If the baseline is not `cec891f` anymore, re-read this handoff and adjust for any newer Phase 3/Phase 4 changes.

### 0.3 Pin exact library versions, but do not leave the app unbuilt

Add only the Phase 4 libraries needed by the plan:

- `@tanstack/react-table`
- `recharts`
- `date-fns`

`@tanstack/react-virtual` is already present in `package.json` at `^3.13.26`. Reuse it for virtualized table rows instead of adding another virtualization library.

After install, verify the lockfile changed intentionally:

```bash
pnpm install
grep -E '"(@tanstack/react-table|recharts|date-fns|@tanstack/react-virtual)"' package.json pnpm-lock.yaml
```

### 0.4 TanStack Table is headless; accessibility comes from Phase 3 primitives

The Phase 4 success criteria require sort + filter + pagination + virtualization. Because TanStack Table does not provide UI, reuse Phase 3 Radix/shadcn primitives:

- Sort/filter controls: `Button`, `Select`, `DropdownMenu`, `Popover`, `Tooltip`.
- Row actions: `DropdownMenu`.
- Column visibility: `DropdownMenuCheckboxItem` or a Phase 3-style wrapper.
- Pagination: existing `components/ui/pagination.tsx` can be reused or rebased.

Do not render raw `<div role="row">` tables without keyboard/focus behavior. If you need a table shell, add a small wrapper in `components/ui/table.tsx` with proper `role`, `scope`, and focus-safe button controls.

### 0.5 Recharts must be lazy-loaded and hydration-safe

`recharts` is SVG-heavy. Lazy-load chart wrappers on dashboard routes with `next/dynamic`, and keep all Recharts imports out of server components:

```ts
"use client";

import dynamic from "next/dynamic";

export const CostTrendChart = dynamic(
  () => import("./CostTrendChart").then((mod) => mod.CostTrendChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
```

Prefer a shared `src/components/charts/` wrapper layer so chart internals do not leak Recharts imports into feature pages.

### 0.6 Centralize dates through `src/lib/date.ts`

The plan calls for `date-fns` with locale pulled from `next-intl`. Create a central date module and migrate user-facing relative/absolute date formatting to it.

Do not keep one-off `new Date(...).toLocaleString()` or hand-rolled `s/m/h/d ago` formatting in feature components when Phase 4 touches that surface.

Current known hand-rolled date surfaces to audit:

- `src/components/memory-inspector/ClaimRow.tsx` — `formatRelativeTime()`
- `src/components/memory-inspector/WhyDrawer.tsx` — `toLocaleString()`
- `src/components/memory-inspector/EditClaimDialog.tsx` — date input formatting
- `src/components/critiques/CritiqueRow.tsx` — `formatRelativeTime()`
- `src/components/observatory/mission-observatory.tsx` — timestamp formatting
- `src/components/analytics/usage-chart.tsx` — `toLocaleDateString()`

### 0.7 Preserve existing API-driven marketplace behavior

`src/app/[locale]/(dashboard)/marketplace/marketplace-page-content.tsx` already fetches listings with server-side `search`, `type`, `sort`, `page`, and `per_page`. Do not accidentally turn this into a client-only full-list filter if the API supports server-side filtering.

A safe split is:

- Keep server-side `fetchListings({ search, type, sort, page, per_page })` for marketplace result loading.
- Use TanStack Table for the current page's column layout, sorting metadata, row rendering, and optional client-side column filters.
- If adding client-side filters, document whether they refine the current page or trigger a new server request.

### 0.8 Bundle budget is part of the acceptance criteria

The plan says combined Phase 4 bundle impact should stay under **60KB gzipped**. Keep Recharts out of non-dashboard routes and avoid importing all chart types globally. If `next-bundle-analyzer` is available, run it for `/evaluation`, `/marketplace`, `/missions/:id`, `/memory-inspector`, and `/costs`.

---

## 1. Goal

Add the Phase 4 data-display layer:

1. `@tanstack/react-table` for sortable/filterable/paginated/virtualized data surfaces.
2. `recharts` for evaluation, cost, and mission analytics charts.
3. `date-fns` for centralized absolute and relative date formatting using `next-intl` locale.
4. Shared chart wrappers in `src/components/charts/` with dark/light theme support and lazy loading.
5. Tests for column visibility, sort behavior, virtualization, and date format helpers.

Concrete outcomes:

- Evaluation dashboard uses TanStack Table for run history / leaderboard-style rows.
- Marketplace results use a table/list rendering path with controlled filters, sorting, pagination, and virtualization where appropriate.
- Program run history uses TanStack Table instead of hand-rolled row mapping.
- Cost dashboard and memory inspector charts use Recharts wrappers, not hand-rolled DOM bars.
- User-facing dates use `src/lib/date.ts` instead of scattered `Intl.DateTimeFormat`, `toLocaleString()`, or local relative-time helpers.
- `/evaluation`, `/marketplace`, `/missions/:id`, `/memory-inspector`, and `/costs` build cleanly with no hydration warnings.

---

## 2. Source files to read first

Read these before editing:

1. `/opt/flowmanner/.sisyphus/plans/frontend-awesome-react-adoption.md` — Phase 4 section.
2. `/home/glenn/FlowmannerV2-frontend/package.json` — current scripts/deps; note `@tanstack/react-virtual` is already installed.
3. `/home/glenn/FlowmannerV2-frontend/src/components/evaluation/evaluation-dashboard.tsx` — current evaluation data state and table rendering.
4. `/home/glenn/FlowmannerV2-frontend/src/components/evaluation/__tests__/evaluation-dashboard.test.tsx` — existing mocks and test IDs.
5. `/home/glenn/FlowmannerV2-frontend/src/app/[locale]/(dashboard)/marketplace/marketplace-page-content.tsx` — current server-side marketplace filters/sort/page.
6. `/home/glenn/FlowmannerV2-frontend/src/components/marketplace/listing-card.tsx` — current grid/list card rendering.
7. `/home/glenn/FlowmannerV2-frontend/src/components/mission-builder/ProgramRunHistory.tsx` — current program run history rows and auto-animate behavior.
8. `/home/glenn/FlowmannerV2-frontend/src/components/mission-builder/__tests__/ProgramRunHistory.test.tsx` — existing expectations.
9. `/home/glenn/FlowmannerV2-frontend/src/hooks/mission-builder/useMissionVersions.ts` — version history data shape and current virtualization/sorting gaps.
10. `/home/glenn/FlowmannerV2-frontend/src/components/mission-builder/VersionHistoryPanel.tsx` — current version history UI.
11. `/home/glenn/FlowmannerV2-frontend/src/components/costs/cost-dashboard.tsx` — current hand-rolled cost chart and selectors.
12. `/home/glenn/FlowmannerV2-frontend/src/components/costs/CostTimeline.tsx` — current timeline chart surface.
13. `/home/glenn/FlowmannerV2-frontend/src/components/memory-inspector/MemoryInspector.tsx` — memory inspector composition.
14. `/home/glenn/FlowmannerV2-frontend/src/components/memory-inspector/ClaimRow.tsx` — hand-rolled relative date formatting.
15. `/home/glenn/FlowmannerV2-frontend/src/lib/utils.ts` — existing `formatShortDate`/`formatDateTime` helpers.
16. `/home/glenn/FlowmannerV2-frontend/src/i18n/routing.ts` and `/src/i18n/request.ts` — locale source for date-fns locale mapping.
17. `/home/glenn/FlowmannerV2-frontend/src/components/ui/select.tsx`, `dropdown-menu.tsx`, `pagination.tsx`, `button.tsx` — Phase 3 primitives to reuse.

Do not read every feature file until the table/chart/date migration boundaries are clear.

---

## 3. Scope

### IN

- `package.json` + `pnpm-lock.yaml` — add `@tanstack/react-table`, `recharts`, `date-fns`.
- `src/lib/date.ts` — new date-fns helpers and `next-intl` locale mapping.
- `src/hooks/useTableState.ts` — new shared TanStack Table state helper for sort/filter/pagination/column visibility.
- `src/components/ui/table.tsx` — optional thin table shell if needed, backed by Phase 3 primitives.
- `src/components/charts/` — new shared chart wrappers:
  - theme-aware `ChartContainer` or equivalent
  - tooltip styling
  - empty/loading/skeleton states
  - lazy-loaded Recharts internals
- `src/components/evaluation/evaluation-dashboard.tsx` — TanStack Table for evaluation rows.
- `src/app/[locale]/(dashboard)/marketplace/marketplace-page-content.tsx` — TanStack Table or table-backed list rendering for results.
- `src/components/marketplace/listing-card.tsx` — preserve card behavior while supporting table/list variants.
- `src/components/mission-builder/ProgramRunHistory.tsx` — TanStack Table for program run history.
- `src/hooks/mission-builder/useMissionVersions.ts` and `src/components/mission-builder/VersionHistoryPanel.tsx` — virtualize/sort version rows where applicable.
- `src/components/costs/cost-dashboard.tsx` and `src/components/costs/CostTimeline.tsx` — Recharts replacements for hand-rolled charts.
- `src/components/memory-inspector/ClaimRow.tsx`, `WhyDrawer.tsx`, `EditClaimDialog.tsx` — migrate date formatting to `src/lib/date.ts`.
- `src/hooks/use-session-milestones.ts` and `src/hooks/use-push-notifications.ts` — adopt date-fns where user-facing timestamps/durations are rendered.
- Tests for table sorting, column visibility, date formatting, and chart hydration behavior.

### OUT / deferred

- Phase 2 RHF migrations not needed by Phase 4.
- Phase 5 motion, kbar, DnD, and full Storybook setup.
- Backend API rewrites unless a Phase 4 UI surface is blocked by missing data.
- VPS edits or direct edits under `/opt/flowmanner/frontend/`.
- Replacing `next-intl`, `next-auth`, SWR, React Query, or Zustand.

---

## 4. Critical design details

### 4.1 Shared table helper should be minimal

`src/hooks/useTableState.ts` should not become a giant abstraction. Keep it focused on:

- column visibility state
- sorting state
- global or column filter state
- pagination state
- optional row virtualization metadata

Prefer composable TanStack Table primitives over a custom wrapper that hides column definitions. Feature components should still own their `columns` arrays and data mapping.

### 4.2 Evaluation dashboard migration

Current evaluation dashboard owns local state for tabs, datasets, runs, templates, and benchmark results. The Phase 4 target is the tabular surfaces inside it, not a full data-layer rewrite.

Keep existing test IDs where possible. If a test ID moves from a `<tr>` to a `<tbody>` or row wrapper, update the test intentionally and document it.

Recommended migration order:

1. Add TanStack Table column definitions for run history.
2. Add sorting for model/status/score/date columns.
3. Add column visibility if the UI already has a toolbar or can support a compact control.
4. Add pagination with the existing UI style.
5. Add virtualization only after basic table behavior passes.

### 4.3 Marketplace migration

The marketplace page currently handles:

- server-side `search`
- server-side `type`
- server-side `sort`
- server-side `page`
- client-side `viewMode`

Do not lose server-side pagination. A table-backed marketplace view should keep the existing fetch contract and only use TanStack Table for the rows returned for the current page.

If adding column filters, make the ownership explicit:

- **server filter:** changes call `fetchListings(...)` with new query params.
- **client filter:** filters only the already-fetched page and is labeled accordingly.

### 4.4 Program run history and version history

`ProgramRunHistory` currently renders run rows directly and is covered by tests. Keep the same visible behavior while migrating internals to TanStack Table.

For `useMissionVersions.ts` / `VersionHistoryPanel`, be careful with the existing version data shape. If the current hook is not yet the primary data source for the visible panel, do not force a migration until you know which component consumes it.

### 4.5 Recharts wrappers should hide Recharts imports

Create a shared wrapper pattern like:

- `ChartCard` — border, background, title slot, loading/empty state.
- `LineChart`, `BarChart`, `AreaChart` wrappers — Recharts-specific internals.
- `ChartTooltip` — theme-aware tooltip.

Feature pages should import from `@/components/charts`, not from `recharts` directly.

### 4.6 Date-fns locale mapping

`next-intl` locales are currently `en`, `fr`, `es`, `de`, and `ja`. Map those to date-fns locale modules dynamically where possible, with `en-US` as a safe fallback.

Suggested helper shape:

```ts
export async function getDateLocale(locale?: string): Promise<Locale> {
  switch (locale) {
    case "fr":
      return import("date-fns/locale/fr").then((m) => m.fr);
    case "es":
      return import("date-fns/locale/es").then((m) => m.es);
    case "de":
      return import("date-fns/locale/de").then((m) => m.de);
    case "ja":
      return import("date-fns/locale/ja").then((m) => m.ja);
    default:
      return import("date-fns/locale/en-US").then((m) => m.enUS);
  }
}
```

Keep client-facing helpers synchronous if they do not need dynamic locale chunks. For client components, prefer a stable `useCurrentDateLocale()` hook or pass locale from the page if needed.

### 4.7 Do not regress dark/light theme tokens

Charts must use CSS variables or Tailwind theme tokens from the app, not hard-coded white/black backgrounds. Recharts tooltips and axis labels should adapt to both themes.

Verify with a quick visual check in both light and dark mode if available.

### 4.8 Keep existing tests stable

Existing focused tests cover:

- `src/components/evaluation/__tests__/evaluation-dashboard.test.tsx`
- `src/components/mission-builder/__tests__/ProgramRunHistory.test.tsx`
- `src/components/memory-inspector/__tests__/MemoryInspector.test.tsx`
- `src/components/memory-inspector/__tests__/EditClaimDialog.test.tsx`

Add new tests rather than rewriting old ones unless the UI contract changed.

---

## 5. Verification recipe

Run these in order after the implementation:

```bash
cd /home/glenn/FlowmannerV2-frontend
pwd  # MUST print /home/glenn/FlowmannerV2-frontend

# Dependency sanity
pnpm install
grep -E '"(@tanstack/react-table|recharts|date-fns|@tanstack/react-virtual)"' package.json pnpm-lock.yaml

# Type-check
npx tsc --noEmit > /tmp/phase4-tsc.txt 2>&1; echo "tsc exit: $?"

# Lint
npm run lint > /tmp/phase4-lint.txt 2>&1; echo "lint exit: $?"

# Focused tests
npm test -- src/components/evaluation/__tests__/evaluation-dashboard.test.tsx src/components/mission-builder/__tests__/ProgramRunHistory.test.tsx src/components/memory-inspector/__tests__/MemoryInspector.test.tsx > /tmp/phase4-vitest-focused.txt 2>&1; echo "vitest focused exit: $?"

# Full tests
npm test > /tmp/phase4-vitest-full.txt 2>&1; echo "vitest full exit: $?"

# Build
npm run build > /tmp/phase4-build.txt 2>&1; echo "build exit: $?"
```

If bundle analysis is available, also run:

```bash
npm run build -- --profile > /tmp/phase4-build-profile.txt 2>&1; echo "profile build exit: $?"
```

If the project has no bundle analyzer script, document that gap and inspect the build output manually for unexpected Recharts/table chunks on non-dashboard routes.

### Hydration / runtime smoke checks

After build, smoke-test these routes if the dev server is available:

- `/en/dashboard/evaluation`
- `/en/(dashboard)/marketplace`
- `/en/missions/:id` or the closest mission builder route available
- `/en/memory-inspector`
- `/en/costs` if exposed

Look for:

- no hydration mismatch warnings
- no broken table controls
- no chart blank states in dark/light theme
- no date formatting regressions

---

## 6. Evidence

Save verification output to:

```text
/home/glenn/FlowmannerV2-frontend/.sisyphus/evidence/frontend-phase4-data-display/
```

Suggested files:

```text
01-install.txt
02-dependency-audit.txt
03-tsc.txt
04-lint.txt
05-vitest-focused.txt
06-vitest-full.txt
07-build.txt
08-bundle-analysis.txt  # only if available
09-smoke-notes.txt
```

---

## 7. Commit expectations

Commit locally only unless the user explicitly approves push/deploy.

Suggested commit shape:

```bash
git status
git fetch origin
git log -1 --oneline --decorate
git add package.json pnpm-lock.yaml src/lib/date.ts src/hooks/useTableState.ts src/components/ui/table.tsx src/components/charts src/components/evaluation src/components/marketplace src/components/mission-builder src/components/costs src/components/memory-inspector src/hooks/use-session-milestones.ts src/hooks/use-push-notifications.ts
git commit -m "Phase 4 — TanStack Table, Recharts, and date-fns

- Add TanStack Table support for evaluation, marketplace, and program run history surfaces.
- Add shared chart wrappers backed by Recharts with theme-aware styling.
- Centralize date formatting through date-fns and next-intl locale mapping.
- Preserve existing API-driven marketplace pagination and filters.
- Add focused tests for table state, date helpers, and migrated UI surfaces.

Evidence: .sisyphus/evidence/frontend-phase4-data-display/"
```

Do not push or deploy without explicit user authorization.

---

## 8. Known risks / failure modes

- **TanStack Table a11y gaps:** do not ship raw div-tables without keyboard/focus behavior.
- **Marketplace server/client filter confusion:** keep the existing server-side fetch contract unless explicitly changing it.
- **Recharts hydration warnings:** lazy-load Recharts and keep imports client-only.
- **Bundle bloat:** Recharts must not be imported into non-dashboard routes.
- **date-fns ESM/locale resolution issues:** pin a known-good major and verify `tsc` + `next build`.
- **Virtualization layout jumps:** measure row heights and keep stable keys.
- **Test drift:** do not delete old test IDs without updating tests intentionally.
- **VPS edits:** never edit `/opt/flowmanner/frontend/` directly.

---

## 9. Definition of done

Phase 4 is done when:

- `@tanstack/react-table`, `recharts`, and `date-fns` are installed and locked.
- `src/lib/date.ts` exists and user-facing dates on touched surfaces use it.
- Evaluation dashboard, marketplace results, and program run history use TanStack Table with sort + filter + pagination.
- Virtualization is present where row counts justify it and does not regress layout.
- Recharts chart wrappers render without hydration warnings and respect theme tokens.
- Existing focused tests and full frontend tests pass.
- `npm run build` passes.
- Evidence files are saved under `.sisyphus/evidence/frontend-phase4-data-display/`.
