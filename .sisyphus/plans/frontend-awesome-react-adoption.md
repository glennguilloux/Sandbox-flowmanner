# Frontend Stack Upgrade — Awesome-React Adoption for FlowManner

**Status:** DRAFT — strategic direction for closing the gap between
[enaqx/awesome-react](https://github.com/enaqx/awesome-react) and what
`FlowmannerV2-frontend/` actually ships today.
**Created:** 2026-06-15 from an awesome-react cross-reference of
`/home/glenn/FlowmannerV2-frontend/package.json` and `src/`.
**Owner:** Glenn (decisions), coding agents (execution per chunk).
**Supersedes:** nothing — new track. Existing rebuild roadmap remains
evidence at `.sisyphus/plans/OLD/REBUILD-ROADMAP-2026-06-12.md`.
**Companion research:** `.sisyphus/plans/frontend-awesome-react-research.md` (per-phase deep-dive, version-pinned library tables, code examples).

---

## 1. Strategic Position

FlowManner's frontend is mature in graph/diagram substrate (@xyflow, elkjs,
mermaid), in data/markdown (react-markdown, rehype-*, dompurify), and in
auth/i18n (next-auth 5, next-intl). It is **not** mature in the four most
common SaaS primitives: forms with validation, real component primitives
(Radix/shadcn), data tables, and animations. The `engineering-rapid-prototyper`
agent definition already lists `shadcn-ui`, `react-hook-form`, and
`framer-motion` as standard tooling
(`backend/agent_definitions/engineering/engineering-rapid-prototyper.md:73-77`),
so the gap is also a documentation-vs-source contradiction.

**Premise.** Adopt libraries in 5 dependency-ordered phases. Each phase
is a self-contained chunk with concrete file lists, success criteria,
and a stop rule. No phase touches the VPS directly; everything goes
through `deploy-frontend.sh` and existing CI.

**Premise.** Do not adopt everything awesome-react lists. Skip preact,
gatsby, remotion, react-three-fiber, react-figma, react-native, rescript,
fulcro, styled-components, redux, apollo, vite, parcel, cypress, jest.

---

## 2. Five-Phase Roadmap

### Phase 1 — Defensive polish (no behavior change)

**Summary.** Add `react-error-boundary`, `react-scan`, and `auto-animate`.
None touch existing component contracts. One-day installs that improve
crash UX, dev-time render profiling, and list-reorder polish.

**Code surface.**
- `frontend/src/app/{layout,error,global-error}.tsx` — wrap in `ErrorBoundary` with branded fallback (`components/ui/error-fallback.tsx`, new).
- `frontend/src/app/(auth)/layout.tsx`, `(dashboard)/layout.tsx` — per-segment boundaries.
- `frontend/src/providers/query-provider.tsx` — init `react-scan` in dev only; exclude from prod via `vitest.config.ts` analysis.
- `frontend/src/components/{marketplace/featured-carousel,notifications/notification-bell,mission-builder/ProgramRunHistory}.tsx` — wrap lists in `useAutoAnimate`.

**Dependencies.** None.

**Success criteria.** Throwing in a child shows the fallback, not a white screen.
`react-scan` overlay appears in dev only, absent in `next build`. Auto-animate
visible on the three target lists with no layout-shift regression.
`pnpm lint && pnpm test && pnpm build` pass; `deploy-frontend.sh` completes;
`/`, `/marketplace`, `/missions` smoke green.

**Risk.** Error boundaries can swallow errors Sentry never sees — call
`Sentry.captureException` in `componentDidCatch` before showing fallback.
`react-scan` adds dev overhead — gate on `NODE_ENV === 'development'` and
verify tree-shake.

**Estimate:** 3-5 days.

---

### Phase 2 — Forms + validation (react-hook-form + zod)

**Summary.** Introduce `react-hook-form` + `zod` + `@hookform/resolvers`
as the standard form stack. Migrate the highest-traffic forms first, not
all 215 sites at once. The backend already speaks Pydantic; zod schemas
are a parallel TS-side source of truth and (later) a FastAPI mirror via
`zod-to-openapi`.

**Code surface.** Form-by-form migration (priority order, not exhaustive):
- `frontend/src/components/auth/{signin-password-input,password-input}.tsx` (highest traffic).
- `frontend/src/components/settings/{two-factor-modal,BillingSettings}.tsx` (12 + 7 patterns).
- `frontend/src/components/memory-inspector/{EditClaim,ForgetConfirm}Dialog.tsx` (11 + 4 patterns).
- `frontend/src/components/marketplace/review-component.tsx` (19 patterns).
- `frontend/src/components/rag/{SearchBar,DocumentUploader}.tsx` (8 + 5 patterns).
- `frontend/src/components/evaluation/evaluation-dashboard.tsx` (19 patterns).
- ~~`frontend/src/hooks/mission-builder/*.ts`~~ — see Plan corrections #4. All 5 hooks are data-fetching wrappers (loading/error/data[]/page/total CRUD). Form-state in mission-builder lives in the **components** (MissionProgramCreate, PropertiesPanel), not the hooks. Slice 8 = MissionProgramCreate.

New files: `frontend/src/lib/schemas/{auth,settings,marketplace,memory,rag,evaluation,programs}.ts`,
`frontend/src/lib/forms/use-zod-form.ts`, plus its vitest. (Renamed `mission-builder` → `programs`: the schema scope is the `ProgramCreate` payload, not the wider mission-builder surface.)

**Dependencies.** None blocking. Phase 1 boundaries are nice-to-have.

**Success criteria.** New forms use `useZodForm({ schema })`; the schema
lives in `lib/schemas/`. Invalid data shows field-level errors; focus
moves to first error. Forms re-render only the changed field (verify
with `react-scan`). Auth, 2FA, billing, memory-edit, marketplace-review,
RAG search, and evaluation-dashboard forms all migrated with no behavior
regression. 90% reduction in `useState` calls tied to form state in the
migrated files. All migrated files have a vitest test asserting the
schema rejects bad input and accepts good input. Backend Pydantic ↔
frontend zod contract test exists for at least `auth` and `settings`.

**Risk.** Big-bang migration creates a long unstable period — migrate
one form at a time, ship each. `react-hook-form` + `react-dropzone`
controller pattern confusion — write a tested `useDropzoneField` helper.
Bundle bloat — import from `react-hook-form` top-level only (tree-shaking
works for the main entry).

**Estimate:** 2-3 weeks.

### Plan corrections (false-positive audits)

The "Code surface" bullet list above is the priority order from the original audit, but the pattern counts ("N patterns") were `useState` counts, not form-element counts. Four targets were assessed as **not** RHF candidates. They are kept here as historical context; the migration is a no-op for them.

| # | File | Why skip | Reference |
|---|------|----------|-----------|
| 1 | `src/components/memory-inspector/ForgetConfirmDialog.tsx` | No `<form>`, single boolean + 2 radios + click handler | Slice 3a assessment |
| 2 | `src/components/settings/BillingSettings.tsx` | No `<form>`, no `<input>`, all `useState` is data fetching | Slice 2 assessment |
| 3 | `src/components/rag/DocumentUploader.tsx` | No `<form>`, no submit, no controlled input. Only `useState` is data state (`uploading`, `progress`). The `useDropzoneField` helper IS the deliverable (Phase 2 risk #2) | Slice 6 handoff |
| 4 | `src/hooks/mission-builder/*.ts` (5 files: `useExecutionPoll`, `useMissionExportImport`, `useMissionVersions`, `useNodeGroups`, `useTemplates`) | Every hook is a `[loading, error, data[], page, total]` CRUD wrapper. Zero `<form>`, zero schema, zero RHF candidate. The real form-state surface is the **components**: `MissionProgramCreate.tsx` (slice 8), `PropertiesPanel.tsx` (slice 9), `ExportImportDialog.tsx` (slice 10) | This assessment, 2026-06-15 |

**Pattern.** The original audit counted `useState` calls, not actual form elements (`<form>`, `<input>`, `<select>`, `<textarea>`, `<button type="submit">`). Three of the four false positives (BillingSettings, DocumentUploader, `hooks/mission-builder/*.ts`) were pure data-fetching code with high `useState` counts. When evaluating future "form" candidates, count form elements first, `useState` second.

---

### Phase 3 — Component primitives (Radix UI + shadcn-ui)

**Summary.** Add `@radix-ui/react-*` primitives for accessibility-critical
widgets (Dialog, Dropdown, Popover, Tooltip, Select, Tabs, Switch,
RadioGroup, Accordion, Slider, ScrollArea, AlertDialog). Stand up
`shadcn-ui` as the copy/paste wrapper matching the existing `cva +
tailwind-merge + clsx` recipe already in `components/ui/`.

**Code surface.**
- `frontend/components.json` (new) — shadcn config, pinned upstream commit SHA.
- `frontend/src/components/ui/button.tsx` — rebase on `@radix-ui/react-slot` for `asChild`.
- `frontend/src/components/ui/confirm-dialog.tsx` — **delete** in favor of shadcn AlertDialog.
- `frontend/src/components/ui/pagination.tsx` — rebase on Radix (or keep custom, add focus/aria).
- `frontend/src/components/ui/{tts-button,tts-speed-slider,voice-selector}.tsx` — refactor onto Radix Select/Slider/RadioGroup.
- `frontend/src/components/ui/{dialog,dropdown-menu,popover,tooltip,select,tabs,switch,radio-group,accordion,slider,scroll-area,separator,label,checkbox}.tsx` — all from `npx shadcn@latest add`.
- Migrate `ForgetConfirmDialog`, `EditClaimDialog`, `two-factor-modal` to use the new primitives.

**Dependencies.** Phase 1 boundaries (soft) and Phase 2 form sites that
need Radix Select/Combobox.

**Success criteria.** `components.json` exists; `npx shadcn@latest add`
works against the project. `confirm-dialog.tsx` is deleted. All Radix
wrappers live in `components/ui/`; no Radix imports leak into feature
folders. TTS controls pass a keyboard-only smoke test (Tab to focus,
Enter/Space to activate, arrow keys for slider). Lighthouse a11y on
`/settings` and `/memory-inspector` improves measurably. Toaster
(sonner) and button styling unchanged. Each new primitive gets a
`.stories.tsx` placeholder.

**Risk.** shadcn copy-paste drifts from upstream — pin in `components.json`.
Bundle size grows ~30KB gzipped — tree-shake at import sites, audit with
`next-bundle-analyzer` quarterly. Radix version mismatches across primitives —
pin all `@radix-ui/react-*` to the same minor, add an `overrides` block
to `package.json` if needed.

**Estimate:** 2 weeks.

---

### Phase 4 — Data display (TanStack Table, Recharts, date-fns)

**Summary.** Add `@tanstack/react-table` for sortable/filterable/virtualized
lists, `recharts` for evaluation + cost + mission analytics, and `date-fns`
for formatting timestamps and timezone math. All three compose with
existing @tanstack/* and zustand stores.

**Code surface.**
- `frontend/src/hooks/useTableState.ts` (new) — shared TanStack Table config (sort, filter, pagination, virtualization via existing `@tanstack/react-virtual`).
- `frontend/src/components/{evaluation/evaluation-dashboard,marketplace/listing-card,mission-builder/ProgramRunHistory}.tsx` — TanStack Table.
- `frontend/src/hooks/mission-builder/useMissionVersions.ts` — virtualize via TanStack Table.
- `frontend/src/hooks/use-cost-tracker.ts` + `frontend/src/components/memory-inspector/*` — Recharts.
- `frontend/src/components/charts/` (new) — shared chart wrappers with theme + tooltip styling, lazy-loaded via `next/dynamic`.
- `frontend/src/lib/date.ts` (new) — central date-fns re-exports + locale config (FR/EN per next-intl).
- `frontend/src/hooks/{use-session-milestones,use-push-notifications}.ts` — adopt `format`, `formatDistanceToNow`.

**Dependencies.** Phase 3 (Radix Select for column visibility, Radix
DropdownMenu for row actions). Phase 2 (zod schemas for filter/column
state). Phase 1 (error boundary).

**Success criteria.** Evaluation dashboard, marketplace table, and program
run history all use TanStack Table with sort + filter + pagination +
virtualization; no hand-rolled `useState<SortKey>`. All chart components
render with no hydration warnings and respect dark/light theme tokens.
All user-facing dates format via `date-fns` with locale pulled from
`next-intl`. Bundle impact <60KB gzipped combined. Existing tests pass;
new tests cover column visibility, sort, and date format helpers.
Lighthouse perf on `/evaluation` and `/marketplace` does not regress.

**Risk.** TanStack Table is headless — a11y gaps likely. Reuse Radix
primitives from Phase 3. Recharts SVG is heavy — lazy-load chart
components on dashboard routes. `date-fns` v3+ is ESM-only — pin to
known-good major, verify `vitest` and `next build` resolve it.

**Estimate:** 2-3 weeks.

---

### Phase 5 — Power features (framer-motion, kbar, @dnd-kit, Storybook)

**Summary.** Add `framer-motion` (now `motion`) for transitions, `kbar`
(or `cmdk`) for the command palette, `@dnd-kit/core` + `@dnd-kit/sortable`
for drag-and-drop in the mission builder and floating nav, and `storybook`
for component documentation. This is the polish phase — the app should
already feel snappy from Phases 1-4; this makes it feel *designed*.

**Code surface.**
- `frontend/src/components/ui/motion/` (new) — `FadeIn`, `SlideUp`, `Stagger`, `AnimatePresence` wrappers; respect `prefers-reduced-motion`.
- `frontend/src/app/layout.tsx` — chat-message transition provider.
- `frontend/src/components/{marketplace/featured-carousel,notifications/notification-bell}.tsx` — animation polish.
- `frontend/src/components/{layout/floating-nav,mission-builder/*}.tsx` — DnD reorder (`KeyboardSensor` required).
- `frontend/src/providers/command-palette-provider.tsx` (new) — kbar config.
- `frontend/src/app/(dashboard)/layout.tsx` — Cmd+K listener.
- `frontend/src/lib/command-palette/actions.ts` (new) — registered actions by role.
- `frontend/.storybook/` (new) — main.ts, preview.ts, manager.ts; stories for every `components/ui/*.tsx`.
- `frontend/package.json` — `storybook`, `build-storybook` scripts.

**Dependencies.** All four prior phases. `cmdk` (paired with kbar in
many awesome-react examples) is the same primitive.

**Success criteria.** Cmd+K opens the palette, searches routes/actions,
navigates without a hard refresh. Mission builder nodes reorder with
keyboard. Floating nav items reorder via drag and persist. Chat message
mount/unmount uses AnimatePresence with `prefers-reduced-motion` respected.
`pnpm storybook` boots; every `components/ui/*.tsx` has a `.stories.tsx`.
CI runs `build-storybook` to catch broken stories on PR. No Lighthouse
perf, CLS, or INP regression on `/missions/:id`, `/marketplace`, `/chat`.

**Risk.** framer-motion bundle ~50KB gzipped — dynamic import for heavy
routes, lazy `MotionConfig` at layout level. dnd-kit + keyboard complexity
— integration tests with `@testing-library/user-event` tab+arrow.
Storybook + Next 16 + React 19 + RSC has known issues — run Storybook
as static export only; never in the production bundle.

**Estimate:** 3-4 weeks.

---

## 3. Decision Summary

| Phase | Adds | Risk | Weeks |
|-------|------|------|------:|
| 1 | react-error-boundary, react-scan, auto-animate | Low | 0.5-1 |
| 2 | zod, react-hook-form, @hookform/resolvers | Med | 2-3 |
| 3 | @radix-ui/*, shadcn-ui CLI | Med | 2 |
| 4 | @tanstack/react-table, recharts, date-fns | Med | 2-3 |
| 5 | framer-motion, kbar, @dnd-kit, storybook | Med-High | 3-4 |
**Total estimate:** 10-13 weeks. Phases 1, 3, 4 can run in parallel by
different subagents if desired. Phase 2 is serial (forms depend on the
existing useState patterns being stable). Phase 5 should not start until
Phase 2 form migrations are complete on the surfaces it touches.

---

## 4. Risk Register

| # | Risk | Prob | Impact | Mitigation | Owner |
|---|------|:---:|---:|---|---|
| R1 | Big-bang form migration creates a long unstable period | High | High | One form at a time, ship each | Frontend lead |
| R2 | shadcn copy-paste components drift from upstream | Med | Med | Pin in `components.json`, periodic `npx shadcn@latest diff` | Frontend lead |
| R3 | Bundle size balloons past 250KB JS budget per route | Med | Med | Per-route `next/dynamic`, quarterly `next-bundle-analyzer` | Frontend lead |
| R4 | TanStack Table headless API leaves a11y gaps | Med | High | Reuse Radix primitives from Phase 3 | Frontend lead |
| R5 | Recharts SSR/hydration warnings on first paint | Med | Med | Lazy-load on dashboard routes, mark `'use client'` | Frontend lead |
| R6 | `lucide-react@1.14.0` is not real upstream; pin may break | Med | High | Verify package source; replace with `lucide-react@0.x` or `@icons-pack/react-simple-icons` (already present) | Frontend lead |
| R7 | swr + @tanstack/react-query duplication is unresolved | Med | Med | 1-day audit: pick one, separate cleanup PR | Frontend lead |
| R8 | Adopted libs ship breaking changes mid-Phase | Med | Med | Pin exact versions; renovate-bot weekly PRs | Frontend lead |

---

## 5. Pre-Phase Cleanup (parallel, ~1 day)

Do these before or during Phase 1 — they remove standing confusion:

1. **Verify `lucide-react@1.14.0` provenance.** Real upstream
   `lucide-react` is on 0.x. Determine whether 1.14.0 is a private fork,
   a typo, or a React 19 compat package. Fix the version pin in
   `package.json` before any other lucide work.
2. **Audit `swr` vs `@tanstack/react-query` usage.** Pick one. Likely:
   keep react-query for client mutations + cache, retire SWR if only
   used in legacy server-component fetches.
3. **Decide on shadcn-ui version pin strategy.** Once Phase 3 starts,
   set `components.json` to a pinned upstream commit SHA, not `latest`.
   Add `pnpm dlx shadcn@latest diff` to CI to flag drift.

---

## 6. Companion Track — Nav Product Discovery

**Plan:** `.sisyphus/plans/flowmanner-nav-two-tier-product-discovery.md`
(937 lines, DeepSeek-authored 2026-06-15).

**Relationship to Phase 2:** parallel, not sequential. The nav restructure
adds product-discovery categories (Missions, Hub, Marketplace, Swarm, Tools)
that the Phase 2 form migrations target — `marketplace/review-component.tsx`
(slice 4 done), `rag/SearchBar.tsx` (slice 5 done), `evaluation-dashboard.tsx`
(slice 7 done), `mission-builder/MissionProgramCreate.tsx` (slice 8 next).
**Not** `hooks/mission-builder/*.ts` — that was plan-correction #4; the
form-state surface is the components, not the hooks. Constraints adopted: one slice per concern,
i18n parity across `en/de/es/fr/ja`, full vitest + tsc + eslint + build +
Playwright geometry at 1280×800 gate.

**Ordering — nav slice runs LAST, after all 5 phases (user decision
2026-06-15).** Not before Phase 3 as originally suggested. Implication:
Phase 3 (Radix/shadcn) migrates the CURRENT 4-dropdown `floating-nav.tsx`
to `@radix-ui/react-dropdown-menu`; the nav slice then restructures to a
9-group two-tier layout, replacing the Radix dropdowns with the new IA.
The Phase 3 Radix work is not wasted — it proves the Radix + shadcn
pattern on a real component — but the specific dropdowns it produces
will be replaced by the nav slice. Phase 5 (DnD for the nav items, kbar)
also runs on the current nav; the nav slice lands after Phase 5.

**Stop Rule cap deferred (user decision 2026-06-15).** The 300-line cap
is aspirational; it is enforced at the end of all phases, not per
addition. §6 brought the plan from 300 → 336 lines; further additions
(more companion tracks, phase retros, slices) are permitted until the
phase work concludes. The Stop Rule's "archive finished phases to
OLD/" half still applies for any phase marked complete.

**Issues flagged in the DeepSeek plan (2026-06-15 review) and resolved:**
1. **Swarm dropdown 5 items, 1 real route — RESOLVED (option a).** Add
   `?tab=executions|debate|handoffs|escalation` query-param support to
   `SwarmDashboard` and its `page.tsx`. This change lands with the nav
   slice, not before. Verified: `/en/swarm` → 404, `/en/dashboard/swarm`
   → 200. The nav slice must also assert
   `/en/dashboard/swarm?tab=debate` → 200 and renders the Debate tab as
   active.
2. **Two-tier height unspecified.** Current nav is 72px single-row;
   two tiers need ~96–120px. Pages use `pb-24` (96px) — a taller nav
   risks overlapping content. Implementer must pick a new height and
   recheck the bottom-padding contract when the nav slice runs.
3. **Unused i18n keys in Task 2's "Recommended new keys" list** (costs,
   developer, feedback, nps, onboarding) are not in the recommended IA.
   Trim to only-used keys per the plan's own "Must NOT add unused
   keys" rule.

---

## Stop Rule

- This plan stays under 300 lines. If it grows, archive the finished
  phase to `.sisyphus/plans/OLD/` and reference from the live plan.
- No phase touches the VPS directly. All deploys via `deploy-frontend.sh`.
- No phase introduces a new microservice on the backend.
- No phase replaces `next-intl` or `next-auth`. Those are stable substrate.
- If a phase cannot name concrete files + tests + acceptance criteria, split it.
- If a phase exceeds its estimate by 50% without a working slice, stop and re-plan.
---

## Provenance

Created from a cross-reference of `https://github.com/enaqx/awesome-react`
(raw README, 262 lines, fetched 2026-06-15), the current
`/home/glenn/FlowmannerV2-frontend/package.json`, the `components/ui/`
directory listing (10 hand-rolled files), and `search_files` results
showing 215 form-related patterns with zero matches for `react-hook-form`,
`zod`, `@radix-ui`, `@dnd-kit`, `framer-motion`, `date-fns`, `recharts`,
`@tanstack/react-table`. The engineering-rapid-prototyper agent
definition already assumes shadcn-ui + react-hook-form + framer-motion,
making this a documentation-vs-source gap. Plan structure mirrors
`.sisyphus/plans/q2-q3-agentic-workflow.md`. Most surprising finding:
the `lucide-react@1.14.0` version pin does not match upstream
`lucide-react` (0.x) — worth a 5-minute audit before any icon work.
