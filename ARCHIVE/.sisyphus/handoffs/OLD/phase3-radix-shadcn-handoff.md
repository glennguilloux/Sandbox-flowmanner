# Handoff: Phase 3 — Radix UI primitives + shadcn-ui adoption

> **Phase 3 of the awesome-react adoption plan.**
> Source plan: `/opt/flowmanner/.sisyphus/plans/frontend-awesome-react-adoption.md` (Phase 3, §2).
> **Owner:** Frontend sub-agent or human. **Status:** READY to run.
> **Repo:** `/home/glenn/FlowmannerV2-frontend` (`master`, remote `glennguilloux/flowmanner`).
> **Do not edit:** `/opt/flowmanner/frontend/` or the VPS directly. Source changes belong in the frontend repo; deploy only after user approval.

---

## 0. Critical pre-decisions

### 0.1 Phase 3 is a component-primitive phase, not another form-migration phase

Phase 2 migrates form state to `react-hook-form` + `zod`. Phase 3 migrates accessibility-critical widgets to Radix primitives and shadcn-style wrappers. Keep the scopes separate:

- Do **not** rewrite form state just because a component is touched by Phase 3.
- Do **not** add new zod schemas unless a Phase 2 form site explicitly needs a Radix Select/Combobox contract.
- Do **not** migrate all Phase 2 form sites before starting Phase 3. Phase 3 only depends on the form sites it touches.

### 0.2 shadcn must be pinned, not `latest`

The plan explicitly says `components.json` should pin an upstream commit SHA, not `latest`.

Recommended setup:

```bash
cd /home/glenn/FlowmannerV2-frontend
pwd  # MUST print /home/glenn/FlowmannerV2-frontend
pnpm dlx shadcn@latest init --defaults
pnpm dlx shadcn@latest add button dialog dropdown-menu popover tooltip select tabs switch radio-group accordion slider scroll-area separator label checkbox
```

Then edit `/home/glenn/FlowmannerV2-frontend/components.json` to pin the upstream commit SHA you actually installed from. Do not leave `latest` as the only pin.

### 0.3 Radix imports stay behind `components/ui/*` wrappers

Phase 3 success criteria says Radix wrappers live in `components/ui/` and no Radix imports leak into feature folders.

Use this rule:

- Feature components import `@/components/ui/dialog`, `@/components/ui/select`, etc.
- Only `components/ui/*` imports `@radix-ui/react-*`.
- If a feature needs a new primitive, add the wrapper first, then update the feature.

### 0.4 Do not delete `confirm-dialog.tsx` until all call sites are migrated

`src/components/ui/confirm-dialog.tsx` is still used broadly. Delete it only after every import is gone.

Known call sites to migrate or audit before deletion:

- `src/components/rag/DocumentList.tsx` — `useConfirm()`
- `src/components/mission-builder/MissionProgramView.tsx` — direct `<ConfirmDialog />`
- `src/app/[locale]/mission-dashboard/page-client.tsx` — `useConfirm()`
- `src/app/[locale]/dashboard/settings/integrations/integrations-page-content.tsx` — `useConfirm()`
- `src/app/[locale]/(dashboard)/graphs/page-client.tsx` — `useConfirm()`
- `src/app/[locale]/(dashboard)/files/files-page-content.tsx` — `useConfirm()`
- `src/app/[locale]/(dashboard)/admin/users/admin-users-page-content.tsx` — `useConfirm()`
- `src/app/[locale]/(dashboard)/missions/node-groups/page-client.tsx` — `useConfirm()`
- `src/app/[locale]/(dashboard)/admin/features/admin-features-page-content.tsx` — `useConfirm()`
- `src/app/[locale]/(dashboard)/admin/maintenance/admin-maintenance-page-content.tsx` — `useConfirm()`
- `src/app/[locale]/(dashboard)/team/team-management-page-content.tsx` — `useConfirm()`
- `src/app/[locale]/(dashboard)/marketplace/my-listings/my-listings-page-content.tsx` — `useConfirm()`
- `src/app/[locale]/(dashboard)/marketplace/my-installed/my-installed-page-content.tsx` — `useConfirm()`

Best migration path:

1. Add `src/components/ui/alert-dialog.tsx` from shadcn.
2. Keep `ConfirmDialog` + `useConfirm()` temporarily, but implement them on top of Radix AlertDialog.
3. Migrate direct `<ConfirmDialog />` sites to `<AlertDialog>` where that is clearer.
4. Delete `confirm-dialog.tsx` only when `grep -R "@/components/ui/confirm-dialog" src` returns no matches.

### 0.5 Storybook is a Phase 5 item unless explicitly expanded

The plan says every new primitive gets a `.stories.tsx` placeholder, but this repo currently has no `.storybook/` directory and `package.json` has no Storybook deps/scripts.

Do one of these, and document which one:

- **Minimal Phase 3:** create plain `.stories.tsx` files that only render the component with no Storybook-specific imports. This avoids adding Storybook deps but does not fully satisfy the plan's Storybook criterion.
- **Scope expansion:** add Storybook config/deps in Phase 3, then create real stories. This is a larger chunk and should be called out before committing.

---

## 1. Goal

Add Radix UI primitives for accessibility-critical widgets and stand up shadcn-ui as the copy/paste wrapper layer matching the existing `cva + tailwind-merge + clsx` recipe already in `components/ui/`.

Concrete outcomes:

1. `components.json` exists and pins shadcn/upstream versions.
2. `@radix-ui/*` packages are installed and used only through `components/ui/*` wrappers.
3. `button.tsx` supports `asChild` via `@radix-ui/react-slot` while preserving existing variants.
4. `confirm-dialog.tsx` is replaced by shadcn/Radix AlertDialog.
5. `pagination.tsx` is rebased on Radix or at least gets proper focus/ARIA behavior.
6. TTS controls are migrated to accessible Radix primitives:
   - `tts-speed-slider.tsx` → Radix Slider
   - `voice-selector.tsx` → Radix Select
   - `tts-button.tsx` remains a button but keeps state transitions and cleanup behavior
7. `ForgetConfirmDialog`, `EditClaimDialog`, and `two-factor-modal` use the new primitives.
8. Toaster and button styling remain visually unchanged.

---

## 2. Source files to read first

Read these before editing:

1. `/opt/flowmanner/.sisyphus/plans/frontend-awesome-react-adoption.md` — Phase 3 section.
2. `/home/glenn/FlowmannerV2-frontend/package.json` — scripts, deps, lockfile state.
3. `/home/glenn/FlowmannerV2-frontend/tsconfig.json` — Storybook/type inclusion implications.
4. `/home/glenn/FlowmannerV2-frontend/src/components/ui/button.tsx` — current Button API and variants.
5. `/home/glenn/FlowmannerV2-frontend/src/components/ui/confirm-dialog.tsx` — current imperative confirmation API.
6. `/home/glenn/FlowmannerV2-frontend/src/components/ui/pagination.tsx` — current keyboard/focus behavior.
7. `/home/glenn/FlowmannerV2-frontend/src/components/ui/tts-speed-slider.tsx` — raw range input.
8. `/home/glenn/FlowmannerV2-frontend/src/components/ui/voice-selector.tsx` — custom dropdown quirks.
9. `/home/glenn/FlowmannerV2-frontend/src/components/ui/tts-button.tsx` — audio lifecycle.
10. `/home/glenn/FlowmannerV2-frontend/src/components/memory-inspector/ForgetConfirmDialog.tsx`
11. `/home/glenn/FlowmannerV2-frontend/src/components/memory-inspector/EditClaimDialog.tsx`
12. `/home/glenn/FlowmannerV2-frontend/src/components/settings/two-factor-modal.tsx`

Do not read every feature file until you know exactly which primitives you need.

---

## 3. Scope

### IN

- `components.json` — new shadcn config, pinned upstream commit SHA.
- `package.json` + lockfile — add Radix/shadcn dependencies only.
- `src/components/ui/button.tsx` — add `asChild` support using `@radix-ui/react-slot`.
- `src/components/ui/confirm-dialog.tsx` — migrate to AlertDialog, then delete when no call sites remain.
- `src/components/ui/pagination.tsx` — improve Radix/focus/ARIA behavior.
- `src/components/ui/tts-speed-slider.tsx` — Radix Slider.
- `src/components/ui/voice-selector.tsx` — Radix Select.
- `src/components/ui/{dialog,dropdown-menu,popover,tooltip,select,tabs,switch,radio-group,accordion,slider,scroll-area,separator,label,checkbox}.tsx` — shadcn/Radix wrappers as needed.
- `src/components/memory-inspector/ForgetConfirmDialog.tsx` — migrate dialog shell to Radix Dialog/AlertDialog.
- `src/components/memory-inspector/EditClaimDialog.tsx` — migrate dialog shell to Radix Dialog.
- `src/components/settings/two-factor-modal.tsx` — migrate dialog shell to Radix Dialog.
- Optional lightweight `.stories.tsx` placeholders if Storybook is already configured or if you explicitly add Storybook.

### OUT / deferred

- Phase 2 RHF migrations not directly needed by Phase 3.
- Phase 4 data-display work (`@tanstack/react-table`, Recharts, date-fns).
- Phase 5 motion, kbar, DnD, Storybook.
- VPS edits or direct rsync target edits under `/opt/flowmanner/frontend/`.
- Backend changes, model changes, or Docker rebuilds.
- Replacing `next-intl` or `next-auth`.
- New microservices.

---

## 4. Critical design details

### 4.1 Button `asChild` must be additive

Current `Button` is a plain `<button>` with variants:

- `clay`
- `moss`
- `ghost`
- `outline`
- `destructive`

Add `asChild` support via Radix Slot:

```ts
interface ButtonProps extends React.ComponentPropsWithoutRef<"button"> {
  variant?: "clay" | "moss" | "ghost" | "outline" | "destructive";
  size?: "sm" | "default" | "lg" | "icon";
  asChild?: boolean;
}
```

When `asChild` is true, render `<Slot className={...} ref={ref} {...props} />`; otherwise render `<button ... />`.

Verify Link/button consumers still type-check.

### 4.2 AlertDialog replacement for `confirm-dialog.tsx`

Keep the existing `useConfirm()` API during migration if it reduces risk:

```ts
const { confirm, dialog } = useConfirm();

if (!(await confirm({ title: "Delete?", variant: "destructive" }))) return;
await deleteSomething();
```

The dialog implementation can move from hand-written DOM to shadcn/Radix `AlertDialog`. The imperative API is useful because many pages currently rely on it.

### 4.3 TTS controls should expose keyboard behavior

Acceptance behavior:

- Tab reaches the voice selector trigger.
- Enter/Space opens Select.
- Arrow keys move through voices.
- Slider can be focused and changed with arrow keys.
- Slider label says what it controls.
- Speed persists through the existing `tts-api` preference helpers.

Also audit `voice-selector.tsx`: the current click-outside overlay is `fixed inset-0 z-40` but does not set `pointer-events-none`; if it remains, it may block clicks. Radix Select should remove that workaround.

### 4.4 Dialog shells should not rewrite form logic

For `EditClaimDialog`, `ForgetConfirmDialog`, and `two-factor-modal`, keep the existing state machines and submit behavior. Only replace the outer modal primitives and visual shell where safe.

Special notes:

- `EditClaimDialog` is already RHF + zod. Do not change schema behavior.
- `ForgetConfirmDialog` has soft/hard forget radio choices. If using Radix RadioGroup, keep the same mutation semantics.
- `two-factor-modal` has setup → verify → backup-codes → manage → disable/regenerate state. Do not split or merge states unless a bug forces it.

---

## 5. Verification recipe

Run these in order after the implementation:

```bash
cd /home/glenn/FlowmannerV2-frontend
pwd  # MUST print /home/glenn/FlowmannerV2-frontend

# Dependency sanity
pnpm install
grep -R "@radix-ui" src/components | cut -d: -f1 | sort -u
grep -R "@/components/ui/confirm-dialog" src || true

# Type-check
npx tsc --noEmit > /tmp/phase3-tsc.txt 2>&1; echo "tsc exit: $?"

# Lint
npm run lint > /tmp/phase3-lint.txt 2>&1; echo "lint exit: $?"

# Focused UI/component tests if present
npx vitest run src/components/ui > /tmp/phase3-vitest-ui.txt 2>&1; echo "vitest ui exit: $?"

# Full tests
npm test > /tmp/phase3-vitest-full.txt 2>&1; echo "vitest full exit: $?"

# Build
npm run build > /tmp/phase3-build.txt 2>&1; echo "build exit: $?"
```

If Storybook is added:

```bash
npx storybook dev -p 6006 --no-open > /tmp/phase3-storybook-dev.txt 2>&1 &
npx build-storybook > /tmp/phase3-storybook-build.txt 2>&1; echo "storybook build exit: $?"
```

If Storybook is not added, document the gap in the final report and in the handoff.

---

## 6. Evidence

Save verification output to:

```text
/home/glenn/FlowmannerV2-frontend/.sisyphus/evidence/frontend-phase3-radix-shadcn/
```

Suggested files:

```text
01-install.txt
02-radix-import-audit.txt
03-confirm-dialog-call-sites.txt
04-tsc.txt
05-lint.txt
06-vitest-ui.txt
07-vitest-full.txt
08-build.txt
09-storybook.txt  # only if Storybook is added
```

---

## 7. Commit expectations

Commit locally only unless the user explicitly approves push/deploy.

Suggested commit shape:

```bash
git status
git fetch origin
git log -1
git add components.json package.json pnpm-lock.yaml src/components/ui src/components/memory-inspector src/components/settings
git commit -m "Phase 3 — Radix primitives + shadcn wrappers

- Add pinned shadcn config and Radix UI wrappers.
- Migrate confirm dialog, TTS controls, pagination, and selected dialog shells.
- Preserve existing button/toaster styling and form behavior.

Evidence: .sisyphus/evidence/frontend-phase3-radix-shadcn/"
```

Do not push or deploy without explicit user authorization.

---

## 8. Known risks / failure modes

- **shadcn drift:** do not leave `components.json` pointing at `latest` without a pinned commit.
- **Radix version mismatch:** keep all `@radix-ui/*` packages on compatible versions; use `overrides` only if needed.
- **Bundle growth:** audit with `next-bundle-analyzer` if available; do not import heavy primitives globally.
- **Feature-folder Radix leaks:** enforce with grep.
- **Confirm dialog delete too early:** only delete after grep finds no imports.
- **Storybook mismatch:** do not create real `.stories.tsx` files that require Storybook types unless Storybook is actually configured.
- **VPS edits:** never edit `/opt/flowmanner/frontend/` directly.

---

## 9. Definition of done

Phase 3 is done when:

- `components.json` exists and pins shadcn/upstream.
- Radix packages are installed and used only through `components/ui/*`.
- `confirm-dialog.tsx` is gone or clearly marked as temporary with no feature-folder imports.
- Button, dialog, select, slider, and at least one migrated feature component pass type-check + lint.
- TTS controls pass keyboard smoke behavior.
- `/settings` and `/memory-inspector` build cleanly.
- Full frontend `npm run build` passes.
- Evidence files are saved under `.sisyphus/evidence/frontend-phase3-radix-shadcn/`.
