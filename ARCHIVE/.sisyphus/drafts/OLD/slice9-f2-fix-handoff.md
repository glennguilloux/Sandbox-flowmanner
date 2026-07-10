# Handoff: Slice 9 F2 Fix — `as any` removal + Rules of Hooks

> **Fix the F2 FAIL items from the slice-9 F1-F4 final-QA review.**
> Source review: kanban task `t_7af285a6` (blocked 2026-06-15 17:32, F1-F4 report in comment thread).
> Slice 9 commit: `9a623d0` on `glennguilloux/flowmanner` (master).
> **Status:** READY to run. Slice 10 (`t_a49ac612`) and slice-9 task (`t_f4117252`) are blocked behind this.

---

## 0. Goal

Fix exactly the items the F1-F4 review flagged as F2 FAIL, no scope creep:

1. **Remove 2 NEW `as any` errors** at `src/components/mission-builder/__tests__/PropertiesPanel.test.tsx:678,683` (introduced by slice 9 in the new "resets form state" test).
2. **Fix the Rules of Hooks violation** at `src/components/mission-builder/PropertiesPanel.tsx:145` (`useState` after the `if (!node) return null;` early return on L141). Pre-existing, but the review called it out as a slice-9 cleanup miss.

**Out of scope (do NOT touch):**
- The pre-existing `as any` at `PropertiesPanel.test.tsx:29` (in `renderPanel` helper, introduced by `0bc17ce8` 2026-05-28 — not a slice-9 regression, not flagged by F1-F4). Leave it. If you accidentally fix it, that expands scope and the user will block.
- Any other lint errors in the project (the eslint baseline has 264 pre-existing errors / 374 warnings — the F2 review is specifically about *new* errors and the Rules of Hooks).
- The slice 9 commit message / commit history. You will produce a new commit on top of `9a623d0`.
- Slice 10 (`t_a49ac612`) — separate task, separate worker.

---

## 1. Context — what the F1-F4 review said verbatim

> "F2 FAIL — 2 new `as any` eslint errors at __tests__/PropertiesPanel.test.tsx:678,683 in new "resets form state" test; pre-existing Rules of Hooks violation at PropertiesPanel.tsx:145 (useState after `if (!node) return null;` early return on L141) carried through from pre-slice9 and not fixed during the rewrite. Functional behavior correct, work otherwise complete."

F1, F3, F4 already PASS. This is a minimal patch to clear F2.

---

## 2. Current state of the violations (verified 2026-06-15 18:11 CEST)

### 2.1 The 2 new `as any` errors

**File:** `src/components/mission-builder/__tests__/PropertiesPanel.test.tsx`
**Lines 675-685** (the "resets form state" test, added in `9a623d0`):
```ts
const { rerender } = render(
  <PropertiesPanel node={nodeA as any} onChange={onChange} onClose={onClose} />,  // L678 — NEW
);
expect(screen.getByText("Node A")).toBeTruthy();
// Switch to node B
rerender(
  <PropertiesPanel node={nodeB as any} onChange={onChange} onClose={onClose} />,  // L683 — NEW
);
```

`nodeA` and `nodeB` are typed via `as const` and have the right shape; the `as any` was used because the helper type for `PropertiesPanel`'s `node` prop is stricter than what the test wants. Read `PropertiesPanelProps` to see what `node` expects, and either:

(a) **Best fix:** type `nodeA` / `nodeB` as the actual prop type. Look at the test file's `mockNode` helper (lines 1-100) and the imports — there's a `Node` import somewhere. Cast: `const nodeA: Node = { id: "node-a", type: "task" as const, ... }` or pass through the `mockNode` helper.

(b) **Acceptable fix:** use a tighter inline type assertion like `as unknown as Node` (preserves the test's intent without violating `no-explicit-any`).

(c) **Last resort:** if the typing fights back, refactor the inline `nodeA` / `nodeB` to use the `mockNode` helper that other tests use. The test name "resets form state" doesn't need bespoke node shapes — the existing `mockNode("task", {...})` should work.

Pick (a) or (b). Do NOT use `// eslint-disable-next-line` — that just hides the lint error and the next worker / F1-F4 will block on it again.

### 2.2 The Rules of Hooks violation

**File:** `src/components/mission-builder/PropertiesPanel.tsx`
**Lines 141-145:**
```ts
export default function PropertiesPanel({ node, onChange, onClose }: PropertiesPanelProps) {
  if (!node) return null;                                              // L141 — early return BEFORE hooks

  const data = (node.data ?? {}) as Record<string, unknown>;
  const nodeType = (data.nodeType as string) ?? "task";
  const [activeTab, setActiveTab] = useState<"define" | "test" | "advanced">("define");  // L145 — hook after early return
  const initialRef = useRef(data);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const form = useZodForm({
    schema: nodePropertiesSchema,
    defaultValues: buildDefaults(data),
  });
  // ...
}
```

**Why this is a violation:** hooks must be called in the same order on every render. When `node` is `null`, the function returns at L141 and **none of the hooks are called**. When `node` becomes truthy again, React sees a "fresh" component (no hook state from the previous null-render), and you have a useState + useRef + useZodForm + useEffect chain initializing from scratch on every `null → node` transition. That isn't a Rules-of-Hooks crash (React will tolerate it via its hook list), but it IS a Rules-of-Hooks lint violation, AND it means the form state is lost every time `node` goes null. Bad pattern.

**The fix:** move the early return AFTER all hook calls. Read the full function first (it's ~80 lines), find the return-`null` rendering block, and reorder:

```ts
export default function PropertiesPanel({ node, onChange, onClose }: PropertiesPanelProps) {
  // Hooks FIRST — always called, in the same order, regardless of node
  const data = (node?.data ?? {}) as Record<string, unknown>;
  const nodeType = (data.nodeType as string) ?? "task";
  const [activeTab, setActiveTab] = useState<"define" | "test" | "advanced">("define");
  const initialRef = useRef(data);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const form = useZodForm({
    schema: nodePropertiesSchema,
    defaultValues: buildDefaults(data),
  });

  useEffect(() => { /* ... */ }, [node?.id]);

  // Early return AFTER all hooks
  if (!node) return null;

  // ... rest of the rendering, using `node` non-null
}
```

**Caveats when refactoring:**
- `useRef(data)` and `useZodForm({ defaultValues: buildDefaults(data) })` need `data` to be defined. Use `node?.data ?? {}` so they're safe to call when `node` is null. The `buildDefaults` helper takes `data: Record<string, unknown>`, so passing `{}` is fine.
- The `useEffect` dependency: change `[node.id]` to `[node?.id]` (or just `[node]` if simpler) so the effect doesn't re-fire on null transitions.
- `form.reset` / `form.watch` calls inside the `useEffect` need to handle the null case: if `!node`, just early-return inside the effect.
- The JSDoc / prop comments don't need to change.
- Behavior is functionally identical: the form mounts/unmounts the same way (well — it now stays mounted across null transitions, which is a tiny behavior change. If the test "resets form state" expects the form to reset on a null-then-back transition, that test may need to assert against `node.id` change, not null. **Read the test to check this.**)

### 2.3 The third `as any` you might see

Line 29 of the test file has a pre-existing `as any` in the `renderPanel` helper. **`eslint` will report 3 errors total** (L29, L678, L683) when you run the lint command. **Do NOT fix L29** — it's pre-existing (`0bc17ce8` 2026-05-28), not in F2 scope. The verification step below is clear about what to check: "0 new errors" relative to a baseline of 1 (L29). If L29's error count goes UP after your patch, something is wrong. If L29's error count stays the same and the new errors are gone, you've succeeded.

---

## 3. Hard rules (copy from AGENTS.md + chunk-specific)

- **`pwd` MUST print `/home/glenn/FlowmannerV2-frontend` before ANY edit.** If it prints `/opt/flowmanner/frontend`, STOP — that is the rsync target on the VPS.
- **No backend file changes. No `app/` edits, no alembic, no `docker compose build backend`.**
- **Do NOT touch `confirm-dialog.tsx` or any `components/ui/*`.**
- **Do NOT touch slice-10 files** (`ExportImportDialog.tsx`, `ExportImportDialog.test.tsx`, `src/i18n/locales/*.json`). Out of scope.
- **`PRE_COMMIT_ALLOW_NO_CONFIG=1` for commits** (no `.pre-commit-config.yaml` in FE repo → silent abort otherwise; `--no-verify` is forbidden by AGENTS.md).
- **No push without `git fetch origin` first** (other agents force-push silently). `git log -1` after.
- **TDD-first per task.** For the `as any` fix, the test is the F2 violation — it already exists, you fix the code. For the Rules of Hooks, no test is strictly needed (the eslint rule enforces it), but **run the existing `PropertiesPanel.test.tsx` after your refactor to confirm no regression** — especially the "resets form state" test, which is the most likely to break if the refactor changes the form-mounting behavior.

---

## 4. Working tree (pre-existing dirty files — NOT yours)

When the worker starts, the FE repo's working tree will have:
- `M e2e/.auth/user.json` — Playwright auth state (regenerates every run)
- `M e2e/mission-builder.spec.ts` — recent e2e work
- `D .sisyphus/evidence/frontend-phase2-slice10/check-i18n.py` — slice-10 cleanup, left by slice-10 worker
- `?? .hermes/`, `?? .sisyphus/evidence/...`, `?? .sisyphus/plans/...`, `?? plans/...` — sisyphus scratch

**Do NOT touch these.** `git add` only the 2 files this fix touches: `PropertiesPanel.tsx` and `PropertiesPanel.test.tsx`.

---

## 5. Output expectations

### 5.1 Files (expected)

```
src/components/mission-builder/PropertiesPanel.tsx         (modify, move early return after hooks)
src/components/mission-builder/__tests__/PropertiesPanel.test.tsx   (modify, replace 2 as any)
```

### 5.2 Verification runs (paste-this recipe, in order)

```bash
cd /home/glenn/FlowmannerV2-frontend
pwd  # MUST print /home/glenn/FlowmannerV2-frontend

# 1. Establish baseline: how many `no-explicit-any` errors exist BEFORE your changes?
npx eslint --rule '{"@typescript-eslint/no-explicit-any": "error"}' \
  src/components/mission-builder/__tests__/PropertiesPanel.test.tsx 2>&1 \
  | grep "no-explicit-any" | wc -l
# Expected BEFORE: 3 (lines 29, 678, 683)

# 2. Apply your changes, then re-check:
npx eslint --rule '{"@typescript-eslint/no-explicit-any": "error"}' \
  src/components/mission-builder/__tests__/PropertiesPanel.test.tsx 2>&1 \
  | grep "no-explicit-any" | wc -l
# Expected AFTER: 1 (only line 29 — pre-existing, out of scope)
# If 0: you fixed the pre-existing one too, scope creep.
# If 2-3: the new ones are still there.

# 3. Rules of Hooks check on the source file:
npx eslint --rule '{"react-hooks/rules-of-hooks": "error"}' \
  src/components/mission-builder/PropertiesPanel.tsx 2>&1
# Expected: 0 errors.

# 4. Full lint, then type-check, then tests, then build
npm run lint > /tmp/slice9-f2fix-lint.txt 2>&1; echo "lint exit: $?"
npx tsc --noEmit > /tmp/slice9-f2fix-tsc.txt 2>&1; echo "tsc exit: $?"
npx vitest run src/components/mission-builder/__tests__/PropertiesPanel.test.tsx \
  > /tmp/slice9-f2fix-vitest-focused.txt 2>&1; echo "vitest focused exit: $?"
npx vitest run > /tmp/slice9-f2fix-vitest-full.txt 2>&1; echo "vitest full exit: $?"
npm run build > /tmp/slice9-f2fix-build.txt 2>&1; echo "build exit: $?"

# 5. Save evidence
mkdir -p .sisyphus/evidence/slice9-f2-fix
npx eslint --rule '{"@typescript-eslint/no-explicit-any": "error"}' \
  src/components/mission-builder/__tests__/PropertiesPanel.test.tsx \
  > .sisyphus/evidence/slice9-f2-fix/01-explicit-any.txt 2>&1
npx eslint --rule '{"react-hooks/rules-of-hooks": "error"}' \
  src/components/mission-builder/PropertiesPanel.tsx \
  > .sisyphus/evidence/slice9-f2-fix/02-rules-of-hooks.txt 2>&1
npm run lint > .sisyphus/evidence/slice9-f2-fix/03-eslint.txt 2>&1
npx tsc --noEmit > .sisyphus/evidence/slice9-f2-fix/04-tsc.txt 2>&1
npx vitest run src/components/mission-builder/__tests__/PropertiesPanel.test.tsx \
  > .sisyphus/evidence/slice9-f2-fix/05-vitest-focused.txt 2>&1
npx vitest run > .sisyphus/evidence/slice9-f2-fix/06-vitest-full.txt 2>&1
npm run build > .sisyphus/evidence/slice9-f2-fix/07-build.txt 2>&1
```

### 5.3 Commit + push

```bash
cd /home/glenn/FlowmannerV2-frontend
git status   # ONLY the 2 slice-9-F2 files
git add src/components/mission-builder/PropertiesPanel.tsx \
        src/components/mission-builder/__tests__/PropertiesPanel.test.tsx

git commit -m "Slice 9 F2 fix — remove 2 as any + fix Rules of Hooks

F1-F4 review (kanban t_7af285a6) F2 FAIL on commit 9a623d0:
- 2 new 'as any' eslint errors at __tests__/PropertiesPanel.test.tsx:678,683
  in the new 'resets form state' test (introduced by 9a623d0).
- Pre-existing Rules of Hooks violation at PropertiesPanel.tsx:145 (useState
  after 'if (!node) return null;' early return on L141) carried through from
  pre-slice9 and not fixed during the rewrite.

Changes:
- __tests__/PropertiesPanel.test.tsx L678,683: type nodeA/nodeB as Node
  (or 'as unknown as Node') instead of 'as any'. The pre-existing as any
  on L29 in renderPanel is NOT in scope and is left alone.
- PropertiesPanel.tsx: move the 'if (!node) return null;' early return
  to AFTER all hook calls (useState, useRef, useZodForm, useEffect).
  This is the only correct Rules-of-Hooks fix — hooks must be called
  unconditionally in the same order on every render.

Verification: 0 new no-explicit-any errors, 0 Rules of Hooks errors,
all PropertiesPanel tests pass, full vitest suite green, build exit 0.
Evidence: .sisyphus/evidence/slice9-f2-fix/"

# Push ONLY after explicit user authorization. Do NOT push.
# The slice 1-9 convention is: worker commits locally, user reviews F1-F4, then push.
# Per AGENTS.md: "No push without explicit user direction."
```

**Do NOT push. Do NOT deploy.** This is a fix that needs another F1-F4 review pass. Commit locally only.

### 5.4 Expected test counts

| Suite | Tests | Status |
|-------|------:|--------|
| `__tests__/PropertiesPanel.test.tsx` (existing) | ~40 | green, no regression — especially "resets form state" |
| Prior slices (1-10) | 708 | green, no regression |
| **Total baseline after F2 fix** | **~708** | **all green** |

If the "resets form state" test fails after the Rules of Hooks refactor, that is a real signal that the refactor changed the form-mounting behavior. **Stop, block with reason, and explain the test failure** — do NOT paper over it with `vi.useFakeTimers()` or similar workarounds.

---

## 6. Output format (what the sub-agent reports back)

```
## Slice 9 F2 Fix — DONE

**Files changed:**
- src/components/mission-builder/PropertiesPanel.tsx (modify, ~3-5 lines changed: moved early return)
- src/components/mission-builder/__tests__/PropertiesPanel.test.tsx (modify, 2 lines: 'as any' → 'as unknown as Node' or typed via Node)

**as any removal:**
- L678, L683: typed via [Node | as unknown as Node | mockNode helper — pick one]
- L29 left alone (pre-existing, out of scope per F1-F4 review)

**Rules of Hooks fix:**
- Moved 'if (!node) return null;' from L141 to AFTER all hook calls (useState, useRef, useZodForm, useEffect).
- Adjusted useEffect dependency from [node.id] to [node?.id] to handle null case.
- Tested behavior: form-mount timing unchanged, all PropertiesPanel tests pass.

**Verification (paste real output, not summary):**
- npx eslint (no-explicit-any): 3 errors BEFORE → 1 error AFTER (L29 only)
- npx eslint (rules-of-hooks): 1 error BEFORE → 0 errors AFTER
- npm run lint: 0 NEW errors (baseline preserved)
- npx tsc --noEmit: 0 errors
- npx vitest run __tests__/PropertiesPanel.test.tsx: NN tests, all green (including "resets form state")
- npx vitest run: 708 tests, all green
- npm run build: exit 0
- Evidence: .sisyphus/evidence/slice9-f2-fix/

**Commit:** <SHA> — "Slice 9 F2 fix — remove 2 as any + fix Rules of Hooks"
**Push:** NOT PUSHED (per AGENTS.md — user reviews first)
**Deploy:** NOT DEPLOYED (frontend is a baked image; user authorizes deploy after F1-F4 re-review)

**Ready for F1-F4 re-review.** Once Glenn unblocks t_7af285a6 and a re-review worker reports PASS, slice 9 + slice 10 unblock.

**Slice 10 / Phase 3:** not started, not affected.
```

---

## 7. Failure modes / things to watch

- **If the "resets form state" test breaks after the refactor:** the form-mount timing changed. Re-read the test carefully — does it assert that form state is reset on `node.id` change, or on `null → node` transition? The hook reorder means the form now stays mounted across null transitions. The test may need to be updated, but that's slice-9-test-scope work, not this F2 fix. **Block with a concrete reason** rather than force-papering the test.
- **If `useZodForm` complains about undefined defaults:** `buildDefaults({})` should return a valid object — check the function (it's in the same file). If the helper requires non-empty data, you'll need to handle the null case inside the hook call (e.g., `useZodForm({ schema, defaultValues: node ? buildDefaults(data) : {} })`).
- **If the eslint `no-explicit-any` count goes from 3 → 0:** you fixed the pre-existing L29. Revert L29.
- **If `npm run lint` shows new errors elsewhere:** the F1-F4 review's F2 frame is "2 new as any + Rules of Hooks". New errors outside that scope are not yours; document them in the summary but don't fix.

---

## 8. Provenance + references

- **Source review:** kanban `t_7af285a6` comment thread, F1-F4 report.
- **Slice 9 commit:** `9a623d0` on `glennguilloux/flowmanner` (master), authored 2026-06-15 16:54 CEST.
- **F1-F4 report file:** in the comment thread of `t_7af285a6` (6295 bytes).
- **Skill reference:** `~/.hermes/skills/subagent-implementation-handoff/` — 11-section prompt template.
- **Slice 9 source handoff:** `/opt/flowmanner/.sisyphus/handoffs/phase2-slice9-properties-panel-rhf-handoff.md` (out-of-date — does not cover F2).

**End of handoff. Fix worker should run in parallel with the slice-10 F1-F4 review (different files, no conflict).**
