# Handoff: Phase 2 Slice 10 — ExportImportDialog.tsx (Tests + Cleanup, RHF Deferred)

> **Slice 10 of Phase 2 (Forms) of the awesome-react adoption plan.**
> Source plan: `/opt/flowmanner/.sisyphus/plans/frontend-awesome-react-adoption.md` (Phase 2, §2).
> **Owner:** Frontend sub-agent. **Status:** READY to run.
> **Predecessor:** Slice 9 (`9a623d0` — PropertiesPanel.tsx RHF migration, F1-F4 review in progress via `t_7af285a6`).

---

## 0. Critical pre-decisions

### 0.1 RHF migration is DEFERRED — explicit call

The slice-9 handoff §9 pre-warned: *"Most of the dialog is not form state ... The RHF migration is for the file input (filename field, optional mission metadata override) only. Or: defer the RHF part entirely if the dialog's 'form' surface is too thin. Document the call."*

**Reading `ExportImportDialog.tsx` (300 lines) confirms the dialog has effectively zero form surface:**
- No controlled text input (the only `<input type="file">` is uncontrolled; value reset via ref in `finally`)
- No submit button
- No validation
- No user-editable filename field (the filename is auto-derived from `missionTitle` in the hook: `safeTitle = missionTitle.replace(/[^a-z0-9]/gi, "_").toLowerCase()`)
- All `useState` is UI/transient: `activeTab`, `importSuccess`, `importingFile`, `dragging`

**Decision: defer RHF migration for this dialog.** Slice 10 = tests + dead-prop cleanup + synthetic-event refactor + i18n. This is a 0.5-1 day chunk, not the 1-2 days the slice-9 handoff §9 estimated for a full RHF migration.

The slice-9 handoff §9 also said: *"Pre-Phase cleanup: pre-write an empty test file so the diff for slice 10 is 'add test + migrate' not 'add test dir + add test + migrate'."* — **we did NOT pre-create the test dir.** Don't worry about that — `__tests__/` already exists at `src/components/mission-builder/__tests__/` (slice 7/8/9 convention). Just add the test file there.

### 0.2 i18n is IN scope (against the slice-9 baseline)

Every other user-facing dialog in the codebase uses `useTranslations` (CritiquesPage, AlternativesDrawer, EditClaimDialog, ForgetConfirmDialog). **ExportImportDialog does NOT.** It has ~20 hardcoded English strings ("Download mission as JSON", "Import mission from file", "Click to browse or drag a file here.", etc.).

**This is a slice-10 deliverable, not deferred.** Reasons:
- Aligns with the slice 7/8/9 i18n convention (en real, de/es/fr/ja TODO placeholders)
- The dialog is user-facing and shipping without i18n is a real UX gap for non-en locales
- It's a 30-min incremental addition once you're already in the file

Add `missionBuilder.exportImport` namespace to en.json with ~20 strings, TODO placeholders in de/es/fr/ja per the §5.5 recipe below. Use `useTranslations("missionBuilder.exportImport")` in the component.

### 0.3 Pre-slice housekeeping — NOT required

The §0.2 housekeeping from slice 9 (sandboxd files, plans dir, etc.) still hasn't been committed, but **slice 10 is in the frontend repo and does not block on it.** The sub-agent can run slice 10 in parallel with housekeeping.

### 0.4 DO NOT touch unless asked

- `src/hooks/mission-builder/useMissionExportImport.ts` (the hook) — leave as-is. The hook surface is `[loading, error, downloadExport, importMissionData, setError]` and the dialog uses all four. No changes needed. (Plan-correction #4 from the awesome-react plan: hooks in `src/hooks/mission-builder/*` are pure data-fetching CRUD wrappers, no form state, no RHF candidate. Same rule applies here.)
- `src/lib/mission-builder/api.ts` — leave as-is. The `exportMission` / `importMission` endpoints are not changing.
- `src/lib/mission-builder/types.ts` — leave as-is. `MissionExport` and `ImportResult` types are correct.

---

## 1. Goal

Make `ExportImportDialog.tsx` test-covered, dead-prop-free, synthetic-event-free, and i18n-ready. Document the RHF deferral in the component as a JSDoc note so future readers don't re-litigate.

---

## 2. Context — what changed since slice 9

Slice 9 (`9a623d0`) shipped `PropertiesPanel.tsx` RHF migration. The patch-stream pattern (`form.watch() + 150ms debounce + deepDiff + form.reset(node.id)`) was validated end-to-end. 684/684 vitest, 0 tsc, 0 new eslint, deploy live, HTTP 200.

**Slice 10 is in a different shape.** No RHF schema, no `<form>` element, no `handleSubmit`. Just a file picker + tab toggle + status display. The 0.5-1 day estimate reflects this.

The dialog is mounted from somewhere in the mission-builder canvas (likely `MissionProgramView.tsx` or `FlowEditor.tsx` — verify before writing the test, but DON'T modify the parent). Search for `<ExportImportDialog` to find the call site.

---

## 3. Files already in the FE repo that you MUST NOT recreate

- `src/lib/forms/use-zod-form.ts` (the helper) — not needed for slice 10, no RHF
- `src/lib/forms/use-dropzone-field.ts` (NOT needed, no file upload via RHF)
- `src/lib/forms/__tests__/use-zod-form.test.tsx` (the helper's tests)
- `src/lib/schemas/{auth,2fa,memory,marketplace,rag,evaluation,programs,properties-panel}.ts` — all prior slice schemas; do NOT add a new schema file for slice 10 (no form state to validate)

---

## 4. Read these files (then STOP)

1. `src/components/mission-builder/ExportImportDialog.tsx` (300 lines) — the component. Read the whole file once. Note: 4 useState hooks (activeTab, importSuccess, importingFile, dragging), 1 ref (fileInputRef), the hook integration, the drop handler's synthetic event.
2. `src/hooks/mission-builder/useMissionExportImport.ts` (65 lines) — the hook. Read for the API surface. The hook returns `loading, error, downloadExport, importMissionData, setError`.
3. `src/lib/mission-builder/types.ts` — types `MissionExport` and `ImportResult`. The dialog's import path parses `MissionExport.mission.nodes/edges` and accepts a flat `{ nodes, edges }` shape too.
4. `src/lib/mission-builder/api.ts` — `exportMission` and `importMission` endpoints. Read for the URL shape (`/api/missions/advanced/...`).
5. `src/components/mission-builder/__tests__/PropertiesPanel.test.tsx` (739 lines) — the slice-9 test pattern. Use `mockNode` / `renderPanel` helper style. Note: `vi.hoisted` + `useTranslations: () => (key) => key` mock per `__tests__/PropertiesPanel.test.tsx` (if it uses one) or `__tests__/MissionProgramCreate.test.tsx` (slice 8).
6. `src/components/mission-builder/__tests__/MissionProgramCreate.test.tsx` (194 lines) — slice-8 test pattern. Read 1-100 for the `vi.hoisted` + `useTranslations` + `useRouter` mock setup. Slice 10 needs the same `useTranslations` mock.
7. **Find the parent that mounts `<ExportImportDialog`** via `grep -rn "<ExportImportDialog" src/`. Read the call site to know the prop shape (especially: is `currentNodes` / `currentEdges` actually passed? if so, your prop-removal will need to touch the parent too — DECIDE based on this read).

**DO NOT read** unless you have a specific question: the other 8 already-migrated RHF forms. They use `<form>` + `handleSubmit` which is **not** the pattern here.

---

## 5. Scope

### IN

#### 5.1 New test file
`src/components/mission-builder/__tests__/ExportImportDialog.test.tsx` (~150-200 lines, ~12 tests).

Mock pattern (from slice 8/9):
```ts
const mocks = vi.hoisted(() => ({
  downloadExport: vi.fn(),
  importMissionData: vi.fn(),
}));

vi.mock("@/hooks/mission-builder/useMissionExportImport", () => ({
  useMissionExportImport: () => ({
    loading: false,
    error: null,
    downloadExport: mocks.downloadExport,
    importMissionData: mocks.importMissionData,
    setError: vi.fn(),
  }),
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => "en",
}));
```

Test coverage (12+ tests):
- **Export tab (4 tests):**
  - "shows export panel by default (activeTab=export)"
  - "calls downloadExport with missionId and missionTitle on Download click"
  - "disables Download button when missionId is missing"
  - "shows 'Save the mission first to enable export' hint when missionId is missing"
- **Import tab (4 tests):**
  - "switches to import tab on click"
  - "imports via file input change (mock file with JSON content)"
  - "imports via drop (use DataTransfer mock or fire drop event with files)"
  - "shows error when JSON is invalid"
- **State (2 tests):**
  - "shows error from hook.error"
  - "clears error when switching tabs"
- **Auto-close (1 test):**
  - "calls onClose after 1500ms when import succeeds" (use `vi.useFakeTimers()`)

**Mock the File API** for the import tests. The cleanest way: create a `File` with `new File([JSON.stringify(mockExport)], "test.json", { type: "application/json" })` and pass it via `fireEvent.change` on the file input, or via a `DataTransfer` object in the drop event.

#### 5.2 Dead-prop cleanup
`ExportImportDialogProps` declares `currentNodes: Node[]` and `currentEdges: Edge[]` (lines 21-22) but the component never destructures or uses them. **Remove them from the interface and the call site** (or destructure and use them — but the dialog doesn't actually need them since `onImport({ nodes, edges })` is the only consumer). Find the parent call site (per step 7 of the Read list) and remove the prop from the JSX.

**If removing the prop would break the call site** (e.g. parent needs them for some reason), just remove them from the interface but keep the destructuring as `_currentNodes, _currentEdges` with eslint-disable. **Document the call** in the handoff report.

#### 5.3 Synthetic-event refactor
`handleDrop` (lines 50-58) builds a synthetic `React.ChangeEvent<HTMLInputElement>` to call `handleFileSelect`:
```ts
const syntheticEvent = { target: { files: [file] } } as unknown as React.ChangeEvent<HTMLInputElement>;
await handleFileSelect(syntheticEvent);
```

Refactor: `handleFileSelect` should accept a `File | undefined` directly:
```ts
const handleFileSelect = async (file: File | undefined) => {
  if (!file) return;
  setImportingFile(true);
  setImportSuccess(null);
  setError(null);
  try {
    const text = await file.text();
    // ... rest of the parsing logic
  }
  // ...
};
```

The `<input onChange>` becomes `onChange={(e) => handleFileSelect(e.target.files?.[0])}` and `handleDrop` becomes `await handleFileSelect(e.dataTransfer.files?.[0])`.

**Verify:** the `fileInputRef.current.value = ""` reset still works (it's in the `finally` block, not the synthetic event).

#### 5.4 i18n keys
Add `missionBuilder.exportImport` namespace to all 5 locale files. ~20 strings. Use `useTranslations("missionBuilder.exportImport")` in the component.

Strings (rough count; verify by reading the component):
- `title`: "Export / Import"
- `exportTab`: "Export"
- `importTab`: "Import"
- `export.heading`: "Download mission as JSON"
- `export.description`: "Export includes your mission configuration, flow structure (nodes & edges), and all associated tasks. Perfect for backups or sharing."
- `export.button`: "Download JSON"
- `export.exporting`: "Exporting..."
- `export.disabledHint`: "Save the mission first to enable export"
- `import.heading`: "Import mission from file"
- `import.description`: "Select a Flowmanner export JSON file to load its nodes and edges into the current canvas."
- `import.button`: "Choose JSON file"
- `import.importing`: "Importing..."
- `import.dropHint`: "Click to browse or drag a file here."
- `import.errorNoData`: "No nodes or edges found in the file. Expected a Flowmanner mission export."
- `import.errorInvalidJson`: "Invalid JSON file. Please select a valid Flowmanner export."
- `import.errorGeneric`: "Failed to parse file"
- `import.success`: "Imported {nodes} node(s) and {edges} edge(s)" (use ICU placeholders)

Add the strings to en.json (real values), de/es/fr/ja.json (TODO placeholders per slice 7 convention). For `import.success`, use ICU: `"imported {count, plural, =0 {no nodes} =1 {1 node} other {# nodes}} and {edges, plural, =0 {} =1 {1 edge} other {# edges}}"` — or simpler: separate keys for the static text and use template literals in the component. **Pick the simpler approach** (separate keys).

#### 5.5 JSDoc note on RHF deferral
Add a JSDoc block at the top of the component (after the `use client` directive and imports):
```ts
/**
 * Export/Import dialog for missions.
 *
 * Phase 2 slice 10 — RHF migration DEFERRED.
 *
 * The dialog has no real form surface (no controlled text input, no
 * submit, no validation, no user-editable filename field — the filename
 * is auto-derived from missionTitle in useMissionExportImport). All
 * useState is UI/transient (activeTab, importSuccess, importingFile,
 * dragging). Migrating to RHF would add a schema and useZodForm wrapper
 * for zero validation or submit behavior — net negative.
 *
 * If a future feature adds a user-editable filename field or mission
 * metadata override, revisit RHF at that point.
 */
```

### OUT (deferred)

- **RHF migration of the dialog body** — deferred; documented in JSDoc. No schema file, no `useZodForm`, no `<form>` element.
- **`src/lib/schemas/export-import.ts`** — NOT created. No schema needed if no RHF.
- **Backend Pydantic ↔ frontend zod contract test** — Phase 2 plan success criterion is "at least `auth` and `settings`" (both done). The export-import contract test is a follow-up if any field diverges; current types use plain `Record<string, unknown>` for the mission field, no contract drift expected.
- **The `useMissionExportImport` hook** — do NOT touch (plan-correction #4).

---

## 6. Hard rules + failure modes (merged per skill P7)

### Hard rules (copy from AGENTS.md + chunk-specific)

- **`pwd` MUST print `/home/glenn/FlowmannerV2-frontend` before ANY edit.** If it prints `/opt/flowmanner/frontend`, STOP — that is the rsync target on the VPS.
- **No backend file changes. No `app/` edits, no alembic, no `docker compose build backend`.**
- **No edits to `src/hooks/mission-builder/*.ts`.** Pure data-fetching CRUD wrappers (plan-correction #4).
- **No Radix imports, no shadcn-ui, no `components.json`.** Phase 3 only.
- **Do NOT touch `confirm-dialog.tsx` or any `components/ui/*`.**
- **Do NOT delete `useDropzoneField` or any RHF helper.** Slice 6 shipped it for `DocumentUploader`; slice 10 doesn't need it but must not break it.
- **`PRE_COMMIT_ALLOW_NO_CONFIG=1` for commits** (no `.pre-commit-config.yaml` in FE repo → silent abort otherwise; `--no-verify` is forbidden by AGENTS.md).
- **No push without `git fetch origin` first** (other agents force-push silently). `git log -1` after.
- **TDD-first per task.** Write the test, run it (RED), write the impl, run again (GREEN), commit. Save RED/GREEN evidence to `.sisyphus/evidence/frontend-phase2-slice10/task-N-<slug>.txt`

### Working tree (pre-existing dirty files — NOT yours)

When the worker starts, the FE repo's working tree will have:
- `M e2e/.auth/user.json` — Playwright auth state (regenerates every run)
- `M e2e/mission-builder.spec.ts` — recent e2e work
- `?? .hermes/`, `?? .sisyphus/evidence/...`, `?? .sisyphus/plans/...` — sisyphus scratch

**Do NOT touch these.** `git add` only the 4-6 files slice 10 creates or modifies.

---

## 7. Output expectations

### 7.1 Files

```
src/components/mission-builder/__tests__/ExportImportDialog.test.tsx   (new, ~150-200 lines, 12+ tests)
src/components/mission-builder/ExportImportDialog.tsx                  (modify, 300 → ~330 lines, +i18n +JSDoc +refactor)
src/i18n/locales/en.json                                               (+missionBuilder.exportImport, ~20 strings)
src/i18n/locales/de.json                                               (+TODO placeholders)
src/i18n/locales/es.json                                               (+TODO placeholders)
src/i18n/locales/fr.json                                               (+TODO placeholders)
src/i18n/locales/ja.json                                               (+TODO placeholders)
```

Plus, if you removed the dead props from `ExportImportDialogProps`, the parent call site in (likely) `MissionProgramView.tsx` or `FlowEditor.tsx`. **Only if** the prop was actually being passed — verify with `grep -rn "currentNodes\|currentEdges" src/` before editing the parent.

### 7.2 Verification runs (paste-this recipe, in order)

```bash
cd /home/glenn/FlowmannerV2-frontend
pwd  # MUST print /home/glenn/FlowmannerV2-frontend. If it prints
     # /opt/flowmanner/frontend, you are about to edit the rsync
     # target — STOP.

# 1. i18n parity sanity (must be 5 OK, one per locale)
for loc in en de es fr ja; do
  python3 -c "import json; d=json.load(open('src/i18n/locales/$loc.json')); assert 'missionBuilder' in d, 'missing namespace'; assert 'exportImport' in d['missionBuilder'], 'missing exportImport'; print('$loc OK')"
done

# 2. Lint
npm run lint > /tmp/slice10-lint.txt 2>&1; echo "lint exit: $?"

# 3. Type check
npx tsc --noEmit > /tmp/slice10-tsc.txt 2>&1; echo "tsc exit: $?"

# 4. Unit tests (focused)
npx vitest run src/components/mission-builder/__tests__/ExportImportDialog.test.tsx \
  > /tmp/slice10-vitest-focused.txt 2>&1; echo "vitest focused exit: $?"

# 5. Full suite
npx vitest run > /tmp/slice10-vitest-full.txt 2>&1; echo "vitest full exit: $?"

# 6. Build
npm run build > /tmp/slice10-build.txt 2>&1; echo "build exit: $?"

# 7. Save evidence
mkdir -p .sisyphus/evidence/frontend-phase2-slice10
npx tsc --noEmit > .sisyphus/evidence/frontend-phase2-slice10/01-tsc.txt 2>&1
npm run lint > .sisyphus/evidence/frontend-phase2-slice10/02-eslint.txt 2>&1
npx vitest run src/components/mission-builder/__tests__/ExportImportDialog.test.tsx \
  > .sisyphus/evidence/frontend-phase2-slice10/03-vitest.txt 2>&1
npx vitest run > .sisyphus/evidence/frontend-phase2-slice10/04-vitest-full.txt 2>&1
npm run build > .sisyphus/evidence/frontend-phase2-slice10/05-build.txt 2>&1
```

### 7.3 Commit + push

```bash
cd /home/glenn/FlowmannerV2-frontend
git status   # ONLY slice 10 files
git add src/components/mission-builder/__tests__/ExportImportDialog.test.tsx \
        src/components/mission-builder/ExportImportDialog.tsx \
        src/i18n/locales/en.json \
        src/i18n/locales/de.json \
        src/i18n/locales/es.json \
        src/i18n/locales/fr.json \
        src/i18n/locales/ja.json
# Plus the parent call site if you removed the dead props.
git add <parent-file>  # ONLY if you actually removed the prop

git commit -m "Phase 2 Slice 10 — mission-builder/ExportImportDialog.tsx tests + i18n + cleanup

- NEW src/components/mission-builder/__tests__/ExportImportDialog.test.tsx:
  12+ tests covering export tab, import tab (file input + drop), state
  (error, tab switch clears error), auto-close after 1500ms success.
  Mock pattern: vi.hoisted for useMissionExportImport, useTranslations,
  useLocale per slice 8/9 convention.
- MOD src/components/mission-builder/ExportImportDialog.tsx: 300 → ~330 lines.
  - Add useTranslations(\"missionBuilder.exportImport\") and i18n keys.
  - Refactor handleFileSelect to accept File | undefined directly (no
    synthetic React.ChangeEvent in handleDrop).
  - Remove unused currentNodes, currentEdges from ExportImportDialogProps
    AND the parent call site (verify with grep first).
  - Add JSDoc explaining why RHF is deferred (no form surface).
- i18n: missionBuilder.exportImport added to en (real strings), TODO
  placeholders to de/es/fr/ja per slice 7 convention.
- NO RHF migration: dialog has no controlled text input, no submit, no
  validation, no user-editable filename. Schema file
  src/lib/schemas/export-import.ts NOT created.
- Evidence: .sisyphus/evidence/frontend-phase2-slice10/"

git push origin master
```

### 7.4 Deploy (frontend is a baked image — source edits have no effect until rebuilt)

```bash
bash /opt/flowmanner/deploy-frontend.sh   # ~4 min, timeout=300
ssh root@74.208.115.142 'docker ps --filter "name=flowmanner-frontend" --format "{{.Names}}: {{.Status}}"'
# Expected: flowmanner-frontend: Up X minutes (healthy)
# If unhealthy, do NOT retry — check `docker compose logs flowmanner-frontend` first.
curl -sSf https://flowmanner.com/en/missions | head -c 500   # 200, HTML body
```

### 7.5 Expected test counts

| Suite | Tests | Status |
|-------|------:|--------|
| `src/components/mission-builder/__tests__/ExportImportDialog.test.tsx` (new) | 12+ | NEW, all green |
| Prior slices (1-9) | 684 | green, no regression |
| **Total baseline after slice 10** | **~696+** | **all green** |

---

## 8. Output format (what the sub-agent reports back)

```
## Slice 10 — DONE

**Files changed:**
- src/components/mission-builder/__tests__/ExportImportDialog.test.tsx (new, NN lines, NN tests)
- src/components/mission-builder/ExportImportDialog.tsx (modify, 300 → NN lines)
- src/i18n/locales/{en,de,es,fr,ja}.json (missionBuilder.exportImport, NN strings)
- <parent-file> (modify, removed dead props) — OR "(no parent changes, dead props were already unused at the call site)"

**RHF deferral:** Documented in JSDoc at top of ExportImportDialog.tsx. No schema file created.

**Verification (paste real output, not summary):**
- npx tsc --noEmit: 0 errors
- npm run lint: 0 errors (note any pre-existing baseline that remained)
- npx vitest run: X test files, Y tests, all green
- New tests added: NN
- Dead props removed: currentNodes, currentEdges (or: "already unused, just removed from interface")
- Synthetic event refactor: handleFileSelect now accepts File | undefined directly
- i18n: 5 locales updated with missionBuilder.exportImport namespace
- Evidence: .sisyphus/evidence/frontend-phase2-slice10/

**Commit:** <SHA> — "Phase 2 Slice 10 — mission-builder/ExportImportDialog.tsx tests + i18n + cleanup"
**Push:** origin/master confirmed via `git log origin/master -1`
**Deploy:** bash /opt/flowmanner/deploy-frontend.sh completed in N seconds
**Live check:** curl -sSf https://flowmanner.com/en/missions → 200, dialog renders

**Ready for user approval.** Awaiting F1-F4 final-QA gate (parallel to slice 9 review).

**Slice 11 / Phase 3:** not started (NEXT chunks, separate handoffs).
```

Per the project convention (slices 1-9), the sub-agent does **not** auto-approve. The user (Glenn) reviews the F1-F4 final-QA gate before declaring slice 10 done.

---

## 9. Next Up — Phase 3 outline (NOT this handoff)

**Radix UI primitives + shadcn-ui CLI (14 wrappers, ~2 weeks per plan).**

Pre-Phase cleanup first: verify `lucide-react@1.14.0` provenance, audit `swr` vs `@tanstack/react-query`, decide on shadcn-ui version pin strategy. Then shadcn add for button/dialog/dropdown-menu/popover/tooltip/select/tabs/switch/radio-group/accordion/slider/scroll-area/separator/label/checkbox, migrate ForgetConfirmDialog/EditClaimDialog/two-factor-modal/tts-button/tts-speed-slider/voice-selector/pagination, delete `confirm-dialog.tsx`.

**Separate handoff doc** to be written after slice 10 is verified and committed.

---

## 10. Provenance + references

- **Source plan:** `/opt/flowmanner/.sisyphus/plans/frontend-awesome-react-adoption.md` — Phase 2 (lines 67-120), hook audit (plan-correction #4).
- **Predecessor:** Phase 2 Slice 9 — commit `9a623d0` on `glennguilloux/flowmanner` (master), `/opt/flowmanner/.sisyphus/handoffs/phase2-slice9-properties-panel-rhf-handoff.md` (the spec).
- **Slice 9 evidence pattern reference:** `/opt/flowmanner/.sisyphus/evidence/phase2-slice8/` (5 files, to be moved to FE repo as `frontend-phase2-slice8/` per slice 9 handoff §0.1).
- **Skill reference:** `~/.hermes/skills/subagent-implementation-handoff/` — 11-section prompt template, P10 (code-surface correction), P10b (i18n audit), P13 (frontend workdir warning), P14 (F1-F4 final-QA gate).
- **Conventions enforced:**
  - Test pattern: `vi.hoisted` + `useTranslations: () => (key) => key` mock per slice 8/9
  - i18n: en real, de/es/fr/ja TODO placeholders per slice 7
  - Slice 8/9 commit message format: `"Phase 2 Slice N — <path> <description>"`
  - Evidence: `.sisyphus/evidence/frontend-phase2-sliceN/` in FE repo (per §0.1 of slice-9 handoff)

**End of handoff. Slice 10 is ready to run after slice 9's F1-F4 review passes (kanban task `t_7af285a6`). Slice 10 will be dispatched as a new kanban task once the F1-F4 worker reports PASS.**
