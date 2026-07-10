# Handoff: Phase 2 Slice 9 — PropertiesPanel.tsx RHF Migration

> **Slice 9 of Phase 2 (Forms) of the awesome-react adoption plan.**
> Source plan: `/opt/flowmanner/.sisyphus/plans/frontend-awesome-react-adoption.md` (Phase 2, §2).
> **Owner:** Frontend sub-agent (or human). **Status:** READY to run.
> **Slices 9 → 10 → Phase 3 are sequential**; this doc delivers 9, the next two are
> pre-scoped at the bottom so the orchestrator doesn't lose them between commits.

---

## 0. 30-second decisions BEFORE the sub-agent starts

### 0.1 Evidence directory location — **frontend slice evidence lives in the frontend repo**

`/home/glenn/FlowmannerV2-frontend/.sisyphus/evidence/frontend-phase2-sliceN/`

**Rationale.** The frontend is a separate git repo (branch `master`, remote
`glennguilloux/flowmanner`); the plan/evidence should travel with the code
commits. Slices 5 and 7 evidence already lives in the frontend repo
(`.sisyphus/evidence/slice5-verify/`, `.sisyphus/evidence/frontend-phase2-slice7/`).
The single misplacement is `/opt/flowmanner/.sisyphus/evidence/phase2-slice8/`
(slice 8 evidence was committed in the backend repo by accident — it's
untracked there). Going forward, use the `frontend-phase2-sliceN/` form.

**Action as part of housekeeping (next bullet):** move the misnamed
`phase2-slice8` dir into the frontend repo as
`.sisyphus/evidence/frontend-phase2-slice8/`, then `git add` it on the
frontend repo (it travels with slice 8's commit `8d0f0f2`).

### 0.2 Pre-slice housekeeping (commit BEFORE slice 9 starts)

The backend repo `/opt/flowmanner/` has **3 modified + 2 untracked + 1 misnamed
evidence dir** that SESSION-RITUAL says should be committed at session end
but the sub-agent shouldn't drag them into the slice 9 diff:

| File | Status | Why it's here | What to do |
|------|--------|---------------|------------|
| `sandboxd/Dockerfile.sandboxd-base` | modified | previous sandboxd work, not slice 9 | commit as housekeeping |
| `sandboxd/entrypoint-wrapper.sh` | modified | ditto | commit as housekeeping |
| `.sisyphus/plans/frontend-awesome-react-adoption.md` | modified | today's draft work (the plan this handoff is part of) | commit as housekeeping |
| `.sisyphus/plans/flowmanner-nav-two-tier-product-discovery.md` | untracked | DeepSeek-authored companion track, 937 lines | commit as housekeeping |
| `.sisyphus/plans/sandboxd-runtimed-socket-handoff-prompt.md` | untracked | sandboxd handoff, deferred | commit as housekeeping |
| `.sisyphus/evidence/phase2-slice8/` | untracked, misnamed | belongs in FE repo (see 0.1) | `mv` into FE repo, then `git add` on slice 8 commit |

**Suggested housekeeping commit (one shot, in the backend repo):**
```bash
cd /opt/flowmanner
mv .sisyphus/evidence/phase2-slice8 /home/glenn/FlowmannerV2-frontend/.sisyphus/evidence/frontend-phase2-slice8
cd /home/glenn/FlowmannerV2-frontend
git add .sisyphus/evidence/frontend-phase2-slice8
git commit -m "chore(evidence): attach slice 8 verification to slice 8 commit"
git push origin master
cd /opt/flowmanner
git add sandboxd/Dockerfile.sandboxd-base sandboxd/entrypoint-wrapper.sh \
        .sisyphus/plans/frontend-awesome-react-adoption.md \
        .sisyphus/plans/flowmanner-nav-two-tier-product-discovery.md \
        .sisyphus/plans/sandboxd-runtimed-socket-handoff-prompt.md
git commit -m "chore(sisyphus): housekeeping — sandboxd files + adoption/nav plans

- sandboxd/Dockerfile.sandboxd-base, entrypoint-wrapper.sh: carried over from
  prior session; not slice 9 work
- .sisyphus/plans/frontend-awesome-react-adoption.md: today's plan source
- .sisyphus/plans/flowmanner-nav-two-tier-product-discovery.md: companion
  track, deferred
- .sisyphus/plans/sandboxd-runtimed-socket-handoff-prompt.md: sandboxd
  handoff, deferred

Slice 8 evidence was moved to FE repo as frontend-phase2-slice8."
git push origin main
```

**Slice 9 is in a different repo** (frontend). It does not block on the
housekeeping — the sub-agent can run the slice in parallel.

---

## 1. Goal

Migrate `PropertiesPanel.tsx` (789 lines, 8 form sub-sections) from raw
`useState` + `<input value={data.foo} onChange={...}>` controls to
`react-hook-form` + `zod` via the existing `useZodForm` helper. The
migration has **two visible outcomes**:

1. **Kills the React "value without onChange" warnings** that fire on
   the controlled inputs in `RouterConfigSection` (the `color` picker)
   and `TransformationConfigSection` (the `nlPrompt` textarea) — see
   `git log` on the slice 8 audit notes, the warning is real.
2. **Aligns with the Phase 2 standard** so the form-state surface in
   the mission builder is type-checked, validated, and a-z-tested like
   the other 8 already-migrated forms (slices 1-8).

**Definition of done.** All 50 existing tests in
`PropertiesPanel.test.tsx` still pass after migration (test moves to
`__tests__/PropertiesPanel.test.tsx` per slice 7/8 convention). React
warning no longer appears in the test run. New schema tests cover each
of the 8 sub-section schemas. `npx tsc --noEmit` + `npm run lint` are
clean. Deploy succeeds, `/en/missions/...` panel still renders.

---

## 2. Context — what changed since slice 8

Slice 8 (`8d0f0f2`) shipped `MissionProgramCreate.tsx` RHF migration.
Slices 1-8 cumulative pattern:

- `useZodForm({ schema, defaultValues })` is the standard wrapper
  (`src/lib/forms/use-zod-form.ts`, 41 lines).
- One zod schema per form subtree, in `src/lib/schemas/<domain>.ts`,
  with matching test at `src/lib/schemas/__tests__/<domain>.test.ts`.
- i18n: schema error messages pulled from
  `missionBuilder.validation.<key>` (en gets real strings, de/es/fr/ja
  get `TODO` placeholders per slice 7 convention).
- Tests: RTL + `vi.hoisted` for fetch mocks + `useTranslations: (k) => k` mock.
- Commit: `Phase 2 Slice N — <path> RHF migration`.
- Evidence: `.sisyphus/evidence/frontend-phase2-sliceN/{01-tsc,02-eslint,03-vitest,04-vitest-full,05-build}.txt`.

**Files already in the FE repo that you MUST NOT recreate:**
- `src/lib/forms/use-zod-form.ts` (the helper)
- `src/lib/forms/__tests__/use-zod-form.test.tsx`
- `src/lib/forms/use-dropzone-field.ts` (NOT needed for slice 9, no
  file upload in PropertiesPanel)
- `src/lib/schemas/{auth,2fa,memory,marketplace,rag,evaluation,programs}.ts`

**PropertiesPanel-specific:**
- The component is rendered by the mission-builder canvas as a slide-in
  panel on node selection. Its `onChange` prop is a `Partial<NodeDataExtra>`
  patch callback. **RHF migration must preserve the `onChange` patch
  contract** — the parent canvas merges the patch into `node.data`, it
  does NOT swap out the whole node. The migration uses
  `useZodForm` with a form that has no submit button (no `<form>`
  element); `handleSubmit(onValid)` is replaced by `watch()` + an
  effect that emits the patch on change.
- 8 sub-section components: `LoopConfigSection`, `ApprovalConfigSection`,
  `TransformNodeConfigSection`, `DelayConfigSection`,
  `TransformationConfigSection`, `RouterConfigSection`,
  `InputSchemaSection_Simple`, `OutputSchemaSection`.
- Plus 3 tab-level containers: `DefineTab`, `TestTab`, `AdvancedTab` and
  the `NLAcceleratorBar` (in DefineTab) that needs its own textarea
  binding.
- Tabs (`activeTab` state) and visual scaffolding (`TabButton`,
  `FieldGroup`, `SchemaDisplay`, `SchemaEditor`, `nextRouteColor`)
  stay as `useState`/helpers — they are not form state.

---

## 3. Read these files (then STOP)

The sub-agent gets ~6 file reads. Pick these in order:

1. `src/components/mission-builder/PropertiesPanel.tsx` (789 lines) —
   the component to migrate. Read the whole file once.
2. `src/components/mission-builder/PropertiesPanel.test.tsx` (611
   lines, 50 tests across 8 `describe` blocks) — the existing test
   surface. Confirms the 8 sub-sections and the test conventions.
3. `src/lib/mission-types.ts` — types `NodeDataExtra`,
   `TransformationConfig`, `RouterNodeConfig`, `RouterRoute`,
   `NodeType`. The schema needs to mirror these.
4. `src/lib/forms/use-zod-form.ts` — the helper, 41 lines. The
   constraints are noted in its docblock (no `z.coerce.*`).
5. `src/lib/schemas/programs.ts` (38 lines) — closest precedent for a
   multi-section schema, written in slice 8. Read for the shape.
6. `src/components/mission-builder/MissionProgramCreate.tsx` — read
   ONLY if you need a working example of `useZodForm` inside an
   existing onChange-patch parent (it's the only one — most other
   RHF forms submit). Read 1-100, then stop.
7. (Optional) `src/components/mission-builder/__tests__/MissionProgramCreate.test.tsx`
   (194 lines) — pattern for vi.hoisted mocks + useTranslations mock.

**DO NOT read unless you have a specific question:** the other 8 already-
migrated forms (`review-component.tsx`, `verify-form.tsx`, `password-and-code-form.tsx`,
`credentials-form.tsx`, `SearchBar.tsx`, `EditClaimDialog.tsx`,
`2fa-modal`, `evaluation-dashboard.tsx`). They use `<form>` + `handleSubmit`
which is **not** the pattern here — PropertiesPanel is a patch-streamed
form, not a submit form. Reading them will send you down the wrong path.

---

## 4. Scope

### IN
- `src/components/mission-builder/PropertiesPanel.tsx` — full rewrite of
  the 8 sub-sections + `NLAcceleratorBar` to use `useZodForm`. Tab
  state, scroll handling, route color helper, and visual scaffolding
  stay as-is.
- `src/lib/schemas/properties-panel.ts` (new) — one zod schema per
  sub-section (8 total) plus a top-level `nodePropertiesSchema` that
  composes them. Exported types `NodePropertiesInput` and the 8
  per-section input types.
- `src/lib/schemas/__tests__/properties-panel.test.ts` (new) — schema
  tests, ~30 cases (4 per sub-section).
- `src/components/mission-builder/__tests__/PropertiesPanel.test.tsx`
  (moved from `PropertiesPanel.test.tsx`, then updated) — keep the
  50 existing tests passing + add ~6 new tests asserting the warning
  is gone and the patch-emit contract is preserved.
- `src/i18n/locales/{en,de,es,fr,ja}.json` — add
  `missionBuilder.validation.<key>` strings (en real, others TODO).
  Audit first per skill P10b — the existing `missionBuilder` key is
  currently empty (`{[]}`), so this is a clean add, not a backfill.
- Evidence: `.sisyphus/evidence/frontend-phase2-slice9/{01-tsc,02-eslint,03-vitest,04-vitest-full,05-build}.txt`.

### OUT (deferred — name each so the sub-agent doesn't drift)

- **Slice 10 — `ExportImportDialog.tsx` RHF migration.** Separate chunk.
  Do NOT touch this file in slice 9. (Outline at bottom.)
- **Phase 3 — Radix UI primitives + shadcn-ui.** Separate phase. Do NOT
  add Radix imports, do NOT install shadcn-ui, do NOT delete
  `confirm-dialog.tsx`. (Outline at bottom.)
- **The `hooks/mission-builder/*.ts` files** — they are pure data-
  fetching CRUD wrappers (per plan-correction #4 in the awesome-react
  plan). No `<form>`, no schema, no RHF candidate. Do NOT touch.
- **Mission-types.ts** — the schema mirrors `NodeDataExtra` but does
  NOT modify it. Adding fields to the schema beyond what
  `NodeDataExtra` already has is a separate task.
- **Backend Pydantic ↔ zod contract test** for the
  `programs`/`properties-panel` schemas — Phase 2 plan success
  criterion is "at least `auth` and `settings`" (both done). The
  properties-panel contract test is a follow-up if any field
  diverges; current schemas use plain string/number/boolean, no
  contract drift expected.
- **The `colorIndex` module-level let.** It's a non-form helper that
  cycles through `ROUTE_COLORS` for new routes. Keep as-is. Migrating
  to React state would be a drive-by refactor; do NOT.

---

## 5. Critical design details

### 5.1 Patch-streamed form, not a submit form

PropertiesPanel's contract is `onChange: (patch: Partial<NodeDataExtra>) => void`.
The parent canvas reads the patch and merges it into `node.data`. There is
**no submit**, no `<form>` element, no `handleSubmit(onValid)`. The
migration pattern is:

```ts
// Top-level in PropertiesPanel
const form = useZodForm({
  schema: nodePropertiesSchema,
  defaultValues: buildDefaultsFromNode(node),
});

// Watch the form, emit patches on change
useEffect(() => {
  const subscription = form.watch((value) => {
    const patch = diffAgainstNodeData(value, node.data);
    if (Object.keys(patch).length > 0) onChange(patch);
  });
  return () => subscription.unsubscribe();
}, [form, node, onChange]);
```

`form.watch(callback)` fires on every field change. The diff helper
(against the original `node.data` snapshot) keeps the patch minimal
and prevents the feedback loop where `onChange` → parent re-renders
with new `node.data` → re-initializes the form → re-fires `watch`.

**`form.reset(buildDefaultsFromNode(node))` MUST be called on
`node.id` change** (e.g. user selects a different node). The default
behavior of `useForm` keeps the old values across prop changes;
without `reset`, switching nodes shows stale data.

### 5.2 8 sub-section schemas compose into one

```ts
// src/lib/schemas/properties-panel.ts
import { z } from "zod";

export const loopConfigSchema = z.object({
  loopMode: z.enum(["count", "foreach", "while"]),
  maxIterations: z.number().int().min(1).max(1000).optional().nullable(),
  // ...
});

export const approvalConfigSchema = z.object({ /* ... */ });
// ... 6 more

export const nodePropertiesSchema = z.object({
  description: z.string().optional().or(z.literal("")),
  label: z.string().min(1, { message: "Label is required" }),
  nodeType: z.string(),
  loopConfig: loopConfigSchema.partial().optional(),
  approvalConfig: approvalConfigSchema.partial().optional(),
  // ... other sub-section configs as partial() — each sub-section
  // only sends its own keys
});
```

**The sub-section components register against the sub-schema**, not
the top-level one. The sub-section schema's `Output` type is what
RHF's `register` uses. Use `Controller` for non-`<input>` widgets
(the color picker, the schema-key editor rows).

### 5.3 Number fields use Controller, not register

`maxIterations`, `delayMs`, `approvalTimeout`, `temperature` are
`<input type="number">`. RHF's `register` returns them as **strings**
by default, which fails zod's `z.number()`. The pattern from
`programs.ts` is:

```tsx
<Controller
  name="loopConfig.maxIterations"
  control={form.control}
  render={({ field }) => (
    <input
      type="number"
      value={field.value ?? ""}
      onChange={(e) => field.onChange(e.target.value === "" ? null : Number(e.target.value))}
    />
  )}
/>
```

The conversion happens at the field boundary; the schema stays
`z.number()`. This is the convention. **Do NOT use `z.coerce.number()`** —
`useZodForm`'s docblock explicitly forbids it (FieldValues constraint).

### 5.4 The color picker is the warning site

`RouterConfigSection` line ~331 (per the grep above) has:
```tsx
<input type="color" value={...} onChange={...} />
```
React logs `You provided a 'value' prop to a form field without an 'onChange'`
when the controlled value comes from a default and onChange is missing in
a render branch. The warning fires intermittently when a new route is
added (the color is auto-assigned via `nextRouteColor()` but the input
re-renders before `onChange` is wired). **Migrating to `Controller` /
`register` wires both, killing the warning.** Verify by adding a test
that mounts the panel with 2 routes and asserts no console.warn was
called (use `vi.spyOn(console, "warn")`).

### 5.5 i18n audit FIRST (skill P10b)

The current `missionBuilder` namespace in en.json is `{}` (per
`python3 -c "import json; ..."` above — it exists as a key but has
no children). Slice 8 added `programs.validation` and slice 7 added
`evaluation.validation`. Use the **same key naming** (`validation`):
- `en.json`: real English strings
- `de.json`, `es.json`, `fr.json`, `ja.json`: `["TODO: de", ...]`
  placeholders (per slice 7 convention; native speaker sweep is a
  separate chunk).

Run this one-liner BEFORE writing the prompt response, to confirm
no surprises:
```bash
for loc in en de es fr ja; do
  echo -n "$loc: "
  python3 -c "import json; d=json.load(open('/home/glenn/FlowmannerV2-frontend/src/i18n/locales/$loc.json')); print('OK' if 'missionBuilder' in d else 'MISSING namespace')"
done
```

### 5.6 Test file relocation + new tests

The current test is at `src/components/mission-builder/PropertiesPanel.test.tsx`
(611 lines, 50 tests). Move to
`src/components/mission-builder/__tests__/PropertiesPanel.test.tsx` per
slice 7/8 convention. The vitest config picks up both `*.test.tsx`
and `__tests__/*.test.tsx` patterns (slice 7/8 evidence confirms),
so this is purely a directory convention.

Add these new tests on top of the 50 existing ones:
- `it("does not emit 'value without onChange' warning when adding a router route")`
  — uses `vi.spyOn(console, "warn")` + 2 routes + assert no warn fired.
- `it("emits minimal patch on field change (only changed keys)")` — types
  in the label field, asserts `onChange` called once with `{label: "..."}`.
- `it("resets form state when node.id changes")` — mount with node A,
  change label, switch to node B (different id), assert form shows B's
  data, not the dirty A state.
- `it("fires patch after blur, not on every keystroke")` — if you
  implement debounced emit (recommended, see 5.7). Otherwise assert
  emit happens within 1 frame.
- 2 more covering sub-section validation errors (e.g. invalid
  `maxIterations` shows error text from `missionBuilder.validation.*`).

### 5.7 Emit-on-blur vs emit-on-change — pick one, document

Two reasonable options:
- **(a) Watch + diff on every change** — simple, no debounce, but
  fires `onChange` for every keystroke. Parent canvas re-renders are
  cheap (RHF is fast + `node.data` reference changes once per change
  anyway), but typing in the label field will emit 5-10 patches for
  "My Node" if the user types 5 characters.
- **(b) `form.handleSubmit(onValid)` on `onBlur` per field** — uses
  RHF's `register` `onBlur` callback. Cleaner UX, fewer patches, but
  adds boilerplate (need an onBlur wrapper per field) and means the
  parent doesn't see intermediate state.

**Recommendation: (a) with a 150ms debounce.** Use `setTimeout` in
the watch effect to coalesce keystrokes; clean up on unmount. This
keeps the parent canvas reactive (live preview works) without firing
on every keystroke.

Document the choice in a comment in the component file.

### 5.8 Tabs are not form state

`activeTab` ("define" | "test" | "advanced") stays as `useState`. It's
UI navigation, not a form field. Migrating it would be a drive-by
refactor and inflate the schema with an unused field. Do NOT add it
to `nodePropertiesSchema`.

### 5.9 `useDropzoneField` is not for slice 9

`src/lib/forms/use-dropzone-field.ts` (slice 6 helper) is for the
RAG document uploader. PropertiesPanel has no file upload. Do NOT
import it. Do NOT create a similar helper here.

---

## 6. Output expectations

### 6.1 Files

```
src/lib/schemas/properties-panel.ts                        (new, ~150 lines)
src/lib/schemas/__tests__/properties-panel.test.ts         (new, ~200 lines, 25-30 cases)
src/components/mission-builder/PropertiesPanel.tsx         (rewrite, target 700-800 lines)
src/components/mission-builder/PropertiesPanel.test.tsx    (delete after move)
src/components/mission-builder/__tests__/PropertiesPanel.test.tsx  (move + +6 new tests)
src/i18n/locales/en.json                                   (+missionBuilder.validation, ~15 strings)
src/i18n/locales/de.json                                   (+TODO placeholders)
src/i18n/locales/es.json                                   (+TODO placeholders)
src/i18n/locales/fr.json                                   (+TODO placeholders)
src/i18n/locales/ja.json                                   (+TODO placeholders)
```

### 6.2 Verification runs (paste-this recipe, in order)

```bash
cd /home/glenn/FlowmannerV2-frontend
pwd  # MUST print /home/glenn/FlowmannerV2-frontend. If it prints
     # /opt/flowmanner/frontend, you are about to edit the rsync
     # target — STOP.

# 1. i18n parity sanity (must be 5 OK, one per locale)
for loc in en de es fr ja; do
  python3 -c "import json; d=json.load(open('src/i18n/locales/$loc.json')); assert 'missionBuilder' in d, 'missing namespace'; assert 'validation' in d['missionBuilder'], 'missing validation'; print('$loc OK')"
done

# 2. Lint (fastest signal of bad imports)
npm run lint                                              # 0 errors

# 3. Type check
npx tsc --noEmit                                          # 0 errors

# 4. Unit tests (focused)
npx vitest run src/lib/schemas/__tests__/properties-panel.test.ts
npx vitest run src/components/mission-builder/__tests__/PropertiesPanel.test.tsx

# 5. Full suite
npx vitest run                                            # all green, count = 50 prior + 6 new + 25-30 schema + 17 prior slices = ~95-105 total

# 6. Build (catches SSR import errors)
npm run build                                             # success, no warnings about "value without onChange"

# 7. Save evidence
mkdir -p .sisyphus/evidence/frontend-phase2-slice9
npx tsc --noEmit > .sisyphus/evidence/frontend-phase2-slice9/01-tsc.txt 2>&1
npm run lint > .sisyphus/evidence/frontend-phase2-slice9/02-eslint.txt 2>&1
npx vitest run src/lib/schemas/__tests__/properties-panel.test.ts \
              src/components/mission-builder/__tests__/PropertiesPanel.test.tsx \
              > .sisyphus/evidence/frontend-phase2-slice9/03-vitest.txt 2>&1
npx vitest run > .sisyphus/evidence/frontend-phase2-slice9/04-vitest-full.txt 2>&1
npm run build > .sisyphus/evidence/frontend-phase2-slice9/05-build.txt 2>&1
```

### 6.3 Commit + push

```bash
cd /home/glenn/FlowmannerV2-frontend
git status                                                # only slice 9 files
git add src/lib/schemas/properties-panel.ts \
        src/lib/schemas/__tests__/properties-panel.test.ts \
        src/components/mission-builder/PropertiesPanel.tsx \
        src/components/mission-builder/__tests__/PropertiesPanel.test.tsx
git rm src/components/mission-builder/PropertiesPanel.test.tsx
git add src/i18n/locales/{en,de,es,fr,ja}.json
git commit -m "Phase 2 Slice 9 — mission-builder/PropertiesPanel.tsx RHF migration

Migrate the 8 form sub-sections (LoopConfigSection, ApprovalConfigSection,
TransformNodeConfigSection, DelayConfigSection, TransformationConfigSection,
RouterConfigSection, InputSchemaSection_Simple, OutputSchemaSection) plus
NLAcceleratorBar to react-hook-form + zod via the existing useZodForm helper.

- NEW src/lib/schemas/properties-panel.ts: 8 sub-section schemas compose
  into nodePropertiesSchema. Number fields use Controller, not register,
  to avoid string coercion (per useZodForm docblock — no z.coerce.*).
- MOD src/components/mission-builder/PropertiesPanel.tsx: ~789 → ~750
  lines (slight reduction from removing per-section onChange prop drilling).
  Patch-streamed form pattern: form.watch() with 150ms debounce, diff
  against node.data, emit onChange({ ...minimalPatch }).
- MOVE + EXTEND test: PropertiesPanel.test.tsx → __tests__/. 50 prior tests
  pass, 6 new tests added (warning regression, patch minimality, node.id
  reset, schema validation feedback, number coercion).
- i18n: add missionBuilder.validation array (15 strings) to en, TODO
  placeholders to de/es/fr/ja per slice 7 convention.
- React 'value without onChange' warning eliminated (verified via
  console.warn spy test).
- Evidence: .sisyphus/evidence/frontend-phase2-slice9/"

git push origin master
```

### 6.4 Deploy (frontend is a baked image — source edits have no effect until rebuilt)

```bash
bash /opt/flowmanner/deploy-frontend.sh                     # ~4 min, timeout=300
ssh root@74.208.115.142 'docker ps --filter "name=flowmanner-frontend" --format "{{.Names}}: {{.Status}}"'
# Expected: flowmanner-frontend: Up X minutes (healthy)
# If unhealthy, do NOT retry — check `docker compose logs flowmanner-frontend` first.
curl -sSf https://flowmanner.com/en/missions | head -c 500  # 200, HTML body
```

### 6.5 Expected test counts

| Suite | Tests | Status |
|-------|------:|--------|
| `src/lib/schemas/__tests__/properties-panel.test.ts` (new) | 25-30 | NEW, all green |
| `src/components/mission-builder/__tests__/PropertiesPanel.test.tsx` | 56 (50 prior + 6 new) | MOVED, all green |
| `src/lib/forms/__tests__/use-zod-form.test.tsx` (existing) | unchanged | green |
| Prior slices (1-8) | 17 schema + 60+ component | green, no regression |
| **Total baseline after slice 9** | **~158-180** | **all green** |

---

## 7. Hard rules + failure modes (merged per skill P7)

### Hard rules (copy from AGENTS.md + chunk-specific)

- **`pwd` MUST print `/home/glenn/FlowmannerV2-frontend` before
  ANY edit.** If it prints `/opt/flowmanner/frontend`, STOP — that
  is the rsync target on the VPS, edits there are silently
  overwritten by the next deploy. (Skill P13.)
- **No backend file changes. No `app/` edits, no alembic, no
  `docker compose build backend`.** Slice 9 is frontend-only.
- **No edits to `src/hooks/mission-builder/*.ts`.** These are
  data-fetching CRUD wrappers (plan-correction #4); zero form state,
  zero RHF candidate.
- **Do NOT use `z.coerce.*`** — `useZodForm`'s docblock explicitly
  forbids it (FieldValues constraint). Use Controller + manual
  `Number(e.target.value)` for numeric inputs.
- **No Radix imports, no shadcn-ui, no `components.json`.** Those
  are Phase 3. Do NOT install `@radix-ui/react-*` in slice 9 even
  for the color picker / dialog. Use the existing controlled-input
  patterns.
- **Do NOT touch `confirm-dialog.tsx` or any `components/ui/*`.**
  Phase 3 deletes it; slice 9 leaves it alone.
- **Do NOT delete `useDropzoneField` or any RHF helper.** Slice 6
  shipped it for `DocumentUploader`; slice 9 doesn't need it but
  must not break it.
- **`PRE_COMMIT_ALLOW_NO_CONFIG=1` for commits** (no
  `.pre-commit-config.yaml` in FE repo → silent abort otherwise;
  `--no-verify` is forbidden by AGENTS.md).
- **No push without `git fetch origin` first** (other agents force-
  push silently). `git log -1` after.
- **TDD-first per task.** Write the test, run it (RED), write the
  impl, run again (GREEN), commit. Save RED/GREEN evidence to
  `.sisyphus/evidence/frontend-phase2-slice9/task-N-<slug>.txt`
  if the sub-agent follows per-task TDD.

### Failure modes (anti-patterns from prior slices)

- **F1: Migrating the `<form>` element wrapper.** PropertiesPanel has
  NO `<form>`. Don't add one. `handleSubmit(onValid)` is for submit
  forms; PropertiesPanel is a patch-streamed form using `form.watch()`.
- **F2: Adding `activeTab` to the schema.** It's UI state, not form
  state. Stays as `useState`.
- **F3: Using `defaultValue` instead of `defaultValues`.** RHF
  expects plural. `useZodForm` passes `defaultValues` through to
  `useForm({ defaultValues })`.
- **F4: Forgetting `form.reset()` on `node.id` change.** Without
  it, switching nodes shows stale form data. This is the #1 visible
  regression users will spot.
- **F5: Number coercion via `z.coerce.number()`.** Forbidden by the
  `useZodForm` docblock. Use Controller + `Number(e.target.value)`.
- **F6: Re-importing `zod` from a non-standard path.** Use
  `import { z } from "zod"` (top-level). zod 4 + @hookform/resolvers
  5.x + react-hook-form 7.79 — these are the pinned majors.
- **F7: Mocking `useZodForm` instead of letting it run.** Tests
  must exercise the real helper. Mock the parent `onChange` prop,
  not the form. The slice 8 test pattern is the reference.
- **F8: `git add .`** in the FE repo. Use `git add <specific paths>`
  to avoid dragging in untracked scratch files. The FE repo has
  several (`.hermes/`, scratch plans, etc.) per the current
  `git status` output.
- **F9: Skipping the i18n audit one-liner.** If a locale's
  `missionBuilder.validation` is missing, the import-side string
  fallback is `"validation.required"` instead of the localized
  message, and the user sees raw key names. Run the one-liner in
  §6.2 step 1 BEFORE writing the schema.
- **F10: Not re-running the prior slices' tests.** A schema helper
  change (e.g. `useZodForm`) can break slices 1-8. Re-run
  `npx vitest run` to catch regressions before claiming done.
- **F11: Treating the React warning as a render bug.** It's a
  controlled-input contract violation — RHF's `register` and
  `Controller` fix it by wiring both `value` AND `onChange` from
  one source. Do NOT "fix" the warning by removing `value=` (it
  becomes uncontrolled and you lose the live preview).

---

## 8. Output format (what the sub-agent reports back)

The sub-agent's final message should be a structured report:

```
## Slice 9 — DONE

**Files changed:**
- src/lib/schemas/properties-panel.ts (new, NNN lines)
- src/lib/schemas/__tests__/properties-panel.test.ts (new, NN tests)
- src/components/mission-builder/PropertiesPanel.tsx (rewrite, NNN lines)
- src/components/mission-builder/__tests__/PropertiesPanel.test.tsx (move + extend, NN tests)
- src/i18n/locales/{en,de,es,fr,ja}.json (missionBuilder.validation)

**Verification (paste real output, not summary):**
- npx tsc --noEmit: 0 errors
- npm run lint: 0 errors
- npx vitest run: X test files, Y tests, all green
- New tests added: NN (schema) + 6 (component)
- React 'value without onChange' warning: GONE (verified via console.warn spy)
- Evidence: .sisyphus/evidence/frontend-phase2-slice9/

**Commit:** <SHA> — "Phase 2 Slice 9 — mission-builder/PropertiesPanel.tsx RHF migration"
**Push:** origin/master confirmed via `git log origin/master -1`
**Deploy:** bash /opt/flowmanner/deploy-frontend.sh completed in N seconds
**Live check:** curl -sSf https://flowmanner.com/en/missions → 200, panel renders

**Ready for user approval.** Awaiting F1-F4 final-QA gate.

**Slice 10 / Phase 3:** not started (NEXT chunks, separate handoffs).
```

Per the project convention (slices 1-8), the sub-agent does **not** auto-
approve. The user (Glenn) reviews the F1-F4 final-QA gate before
declaring slice 9 done.

---

## 9. Next Up — Slice 10 outline (NOT this handoff)

**`ExportImportDialog.tsx` RHF migration (300-line component).**
- **Trigger:** no test file exists; sub-agent must write the
  `__tests__/ExportImportDialog.test.tsx` from scratch (~150 lines,
  ~12 tests covering export filename, import via file input, import
  via drop, error/success states, the `dragging` UI state, the
  `importingFile` loading state, the `importSuccess` message).
- **Schema:** `importMissionSchema` in
  `src/lib/schemas/export-import.ts` — a thin zod wrapper around the
  hook's `importMissionData` return shape. Most of the dialog is
  **not** form state — `loading`, `error`, `importSuccess`,
  `importingFile`, `dragging`, `activeTab` are all UI/transient
  state and stay as `useState`. The RHF migration is for the file
  input (filename field, optional mission metadata override) only.
  - Or: defer the RHF part entirely if the dialog's "form" surface
    is too thin. Document the call.
- **Pre-Phase cleanup: pre-write an empty test file** so the
  diff for slice 10 is "add test + migrate" not "add test dir +
  add test + migrate". The slice 9 handoff pre-creates the dir
  structure expectation.
- **Estimated effort:** 1-2 days.
- **Separate handoff doc** to be written after slice 9 is verified
  and committed.

---

## 10. Next Up — Phase 3 outline (NOT this handoff)

**Radix UI primitives + shadcn-ui CLI (14 wrappers, ~2 weeks per plan).**

### Pre-Phase cleanup (do FIRST, ~1 day)
1. **Verify `lucide-react@1.14.0` provenance.** Real upstream
   `lucide-react` is on 0.x. Determine whether 1.14.0 is a private
   fork, a typo, or a React 19 compat package. Fix the version
   pin in `package.json` BEFORE any other lucide work. The plan
   flags this as Risk R6 (Med/High).
2. **Audit `swr` vs `@tanstack/react-query` usage.** Pick one.
   Likely: keep react-query for client mutations + cache, retire
   SWR if only used in legacy server-component fetches. Separate
   cleanup PR. Risk R7.
3. **Decide on shadcn-ui version pin strategy.** Once Phase 3
   starts, set `components.json` to a pinned upstream commit SHA,
   not `latest`. Add `pnpm dlx shadcn@latest diff` to CI.

### Phase 3 deliverables
- `frontend/components.json` (new) — shadcn config, pinned SHA.
- `frontend/src/components/ui/button.tsx` — rebase on
  `@radix-ui/react-slot` for `asChild`.
- `frontend/src/components/ui/confirm-dialog.tsx` — **delete** in
  favor of shadcn AlertDialog.
- `frontend/src/components/ui/{dialog,dropdown-menu,popover,tooltip,select,tabs,switch,radio-group,accordion,slider,scroll-area,separator,label,checkbox}.tsx`
  — all from `npx shadcn@latest add <name>`.
- Migrate `ForgetConfirmDialog`, `EditClaimDialog`, `two-factor-modal`
  to use the new primitives.
- `frontend/src/components/ui/{tts-button,tts-speed-slider,voice-selector}.tsx`
  — refactor onto Radix Select/Slider/RadioGroup.
- `frontend/src/components/ui/pagination.tsx` — rebase on Radix.

### Phase 3 success criteria
- `components.json` exists; `npx shadcn@latest add` works.
- `confirm-dialog.tsx` is deleted. No `grep -r "confirm-dialog"
  src/` results.
- All Radix wrappers in `components/ui/`; no Radix imports leak
  into feature folders.
- TTS controls pass a keyboard-only smoke test (Tab, Enter/Space,
  arrow keys for slider).
- Lighthouse a11y on `/settings` and `/memory-inspector` improves
  measurably.
- Toaster (sonner) and button styling unchanged.

### Sequencing note (user decision 2026-06-15)
- The nav slice (`flowmanner-nav-two-tier-product-discovery.md`)
  runs LAST, after all 5 phases. Phase 3's Radix work migrates the
  CURRENT 4-dropdown `floating-nav.tsx` to
  `@radix-ui/react-dropdown-menu`; the nav slice then restructures
  to the 9-group two-tier layout. The Phase 3 Radix work is not
  wasted — it proves the pattern on a real component.
- The 300-line plan stop-rule cap is aspirational, enforced at the
  end of all phases, not per addition (user decision 2026-06-15).
  The "archive finished phases to OLD/" half still applies.

**Separate handoff doc** to be written after slice 10 is verified
and committed.

---

## 11. Provenance + references

- **Source plan:** `/opt/flowmanner/.sisyphus/plans/frontend-awesome-react-adoption.md`
  — Phase 2 (lines 67-120), Phase 3 (lines 122-159), Plan corrections
  (lines 109-120, especially #4 for the `hooks/mission-builder/*`
  no-op).
- **Sibling slices 1-8:** commits
  `8d0f0f2`, `601daa7`, `a03fbda`, `dfefe24`, `92af008`, `dc7c371`,
  `9c82be8`, `314744a` — all in `glennguilloux/flowmanner` (master).
- **Slice 8 evidence pattern reference:**
  `/opt/flowmanner/.sisyphus/evidence/phase2-slice8/` (5 files,
  to be moved to FE repo as
  `frontend-phase2-slice8/` per §0.1).
- **Canonical frontend-chunk pattern:**
  `/opt/flowmanner/.sisyphus/plans/OLD/stage-3-frontend-streaming-citations.md`
  — read for the TL;DR + Work Objectives + Definition of Done
  shape; do NOT copy the i18n/streaming sections (not relevant to
  slice 9).
- **Skill reference:**
  `~/.hermes/skills/subagent-implementation-handoff/` — 11-section
  prompt template, P10 (code-surface correction), P10b (i18n
  audit), P13 (frontend workdir warning), P14 (F1-F4 final-QA
  gate).
- **Conventions enforced:**
  - `useZodForm` docblock (no `z.coerce.*`).
  - Slice 7 i18n sweep (en real, de/es/fr/ja TODO).
  - Slice 8 commit message format ("Phase 2 Slice N — <path> RHF migration").
  - Evidence: `.sisyphus/evidence/frontend-phase2-sliceN/` in FE repo.

---

**End of handoff. Slice 9 is ready to run after the §0 housekeeping
commit lands (or in parallel — different repo). The sub-agent's
deliverable is the structured report in §8 plus the F1-F4 final-QA
gate. Slice 10 and Phase 3 are next-up; separate handoffs to follow.**
