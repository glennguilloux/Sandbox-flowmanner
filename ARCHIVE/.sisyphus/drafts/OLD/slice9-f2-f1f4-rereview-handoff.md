# F1-F4 Final-QA Re-Review: Slice 9 F2 Fix (commit `3f27850`)

> **Re-review of the F2 fix on top of slice 9.** The original F1-F4 review (kanban `t_7af285a6`, blocked 2026-06-15 17:32) returned **F1 PASS / F2 FAIL / F3 PASS / F4 PASS** on `9a623d0`. This review re-runs the F1-F4 gate on the F2 fix commit `3f27850`. If F2 is now clear, the user's call is to merge + push + deploy. If F2 still has findings, block and report.
>
> **Owner:** `default` profile (same as the prior F1-F4 review).
> **Workspace:** `dir:/home/glenn/FlowmannerV2-frontend`.

---

## 0. Commit under review

- Repo: `/home/glenn/FlowmannerV2-frontend`
- Branch: `master` (local = `origin/master`, 0/0 drift expected — F2 fix is NOT pushed)
- Commit: `3f27850` — "Slice 9 F2 fix — remove 2 as any + fix Rules of Hooks"
- Parent: `358d4b8` (Phase 2 Slice 10) — wait, that's wrong. Let me check: `3f27850` should be on top of `9a623d0` (slice 9), not `358d4b8` (slice 10). Verify with `git log --oneline -5` — slice 10 (358d4b8) is on master because the F2 fix was committed locally on the same branch.
- Worker self-report: 0 new lint errors, 56/56 PropertiesPanel tests pass, 698/698 full suite, build exit 0, Rules of Hooks violation gone.
- Evidence dir: `/home/glenn/FlowmannerV2-frontend/.sisyphus/evidence/slice9-f2-fix/` (7 files: 01-explicit-any, 02-rules-of-hooks, 03-eslint, 04-tsc, 05-vitest-focused, 06-vitest-full, 07-build)
- Handoff: `/opt/flowmanner/.sisyphus/drafts/slice9-f2-fix-handoff.md` (the spec the F2 fix worker followed)
- Prior F1-F4 report: kanban `t_7af285a6` comment thread (6295 bytes, F2 FAIL details)

## 1. What F2 reported (verbatim, for context)

> "F2 FAIL — 2 new `as any` eslint errors at __tests__/PropertiesPanel.test.tsx:678,683 in new "resets form state" test; pre-existing Rules of Hooks violation at PropertiesPanel.tsx:145 (useState after `if (!node) return null;` early return on L141) carried through from pre-slice9 and not fixed during the rewrite. Functional behavior correct, work otherwise complete."

F1, F3, F4 all PASS on `9a623d0` — those should still pass on `3f27850` since the F2 fix only touched the 2 files F2 called out.

## 2. Read FIRST (do not skip)

1. `git -C /home/glenn/FlowmannerV2-frontend show 3f27850` — the F2 fix diff (2 files only)
2. `/opt/flowmanner/.sisyphus/drafts/slice9-f2-fix-handoff.md` — the spec the worker followed
3. `t_7af285a6` comment thread on the kanban board — the prior F1-F4 report (full F1/F2/F3/F4 detail)
4. The 7 evidence files in `/home/glenn/FlowmannerV2-frontend/.sisyphus/evidence/slice9-f2-fix/` — review, don't re-run unless missing or non-zero exit
5. `src/components/mission-builder/PropertiesPanel.tsx` — read the full function (around L141-170) to verify the Rules of Hooks fix is correct: all hooks called unconditionally, then the early return, then the rendering block. Check that `useEffect` deps handle the null case.
6. `src/components/mission-builder/__tests__/PropertiesPanel.test.tsx` L670-690 — the "resets form state" test. Verify the new typing (`as Node`, `as unknown as Node`, or `mockNode`-based) is correct and that all 56 tests pass.

## 3. Verification recipe (paste-this, in order, save each to its own file — DO NOT CHAIN WITH &&)

```bash
cd /home/glenn/FlowmannerV2-frontend
pwd  # MUST print /home/glenn/FlowmannerV2-frontend

# 1. Establish the `no-explicit-any` baseline for the test file (must be 1, line 30 pre-existing)
npx eslint --rule '{"@typescript-eslint/no-explicit-any": "error"}' \
  src/components/mission-builder/__tests__/PropertiesPanel.test.tsx 2>&1 \
  > /tmp/f1f4-f2fix-01-explicit-any.txt
echo "explicit-any exit: $?"
grep -c "no-explicit-any" /tmp/f1f4-f2fix-01-explicit-any.txt
# Expected: 1 (only line 30, pre-existing in renderPanel helper)

# 2. Rules of Hooks check on the source file (must be 0 errors)
npx eslint --rule '{"react-hooks/rules-of-hooks": "error"}' \
  src/components/mission-builder/PropertiesPanel.tsx 2>&1 \
  > /tmp/f1f4-f2fix-02-rules-of-hooks.txt
echo "rules-of-hooks exit: $?"
# Expected: exit 0, no rule-of-hooks errors

# 3. Exhaustive-deps check on the source file (NEW WARNING to investigate)
npx eslint --rule '{"react-hooks/exhaustive-deps": "warn"}' \
  src/components/mission-builder/PropertiesPanel.tsx 2>&1 \
  > /tmp/f1f4-f2fix-03-exhaustive-deps.txt
echo "exhaustive-deps exit: $?"
# Expected: review the warning(s) — if the warning is on the useEffect that the
# F2 fix touched (around L159), it may be a real signal that the refactor
# introduced a missing-dep issue. If the warning is on a different, pre-existing
# useEffect, it's pre-existing baseline.

# 4. Full lint
npm run lint > /tmp/f1f4-f2fix-04-lint.txt 2>&1
echo "lint exit: $?"
# Expected: exit 0 or 1 (pre-existing baseline has errors). Compare the error
# count to the worker's 03-eslint.txt in evidence dir. New errors in the 2
# F2 fix files = F2 FAIL.

# 5. Type check
npx tsc --noEmit > /tmp/f1f4-f2fix-05-tsc.txt 2>&1
echo "tsc exit: $?"
# Expected: 0 errors. tsc evidence MAY be 0 bytes (silent pass).

# 6. Focused vitest
npx vitest run src/components/mission-builder/__tests__/PropertiesPanel.test.tsx \
  > /tmp/f1f4-f2fix-06-vitest-focused.txt 2>&1
echo "vitest focused exit: $?"
# Expected: 56/56 tests pass (matches worker self-report)

# 7. Full vitest
npx vitest run > /tmp/f1f4-f2fix-07-vitest-full.txt 2>&1
echo "vitest full exit: $?"
# Expected: 698/698 tests pass, 59 test files (matches worker self-report)

# 8. Build
npm run build > /tmp/f1f4-f2fix-08-build.txt 2>&1
echo "build exit: $?"
# Expected: exit 0, no "value without onChange" warning
```

**Critical: do NOT chain with `&&` — the `kanban-worker` skill says chained commands can hang silently on the last step, hiding the failure. Run each command separately, save to its own file, capture exit code, then move on.**

## 4. Spot-check (read the code, not just the test counts)

### 4.1 PropertiesPanel.tsx — Rules of Hooks fix

Read lines 130-200. Confirm:

- [ ] The function now reads roughly:
  ```ts
  export default function PropertiesPanel({ node, onChange, onClose }: PropertiesPanelProps) {
    // Hooks FIRST — always called
    const data = (node?.data ?? {}) as Record<string, unknown>;
    const nodeType = (data.nodeType as string) ?? "task";
    const [activeTab, setActiveTab] = useState<...>(...);
    const initialRef = useRef(data);
    const debounceRef = useRef<...>(...);
    const form = useZodForm({ schema, defaultValues: buildDefaults(data) });
    useEffect(() => { ... }, [node?.id]);

    // Early return AFTER all hooks
    if (!node) return null;

    // ...rest of rendering using `node` non-null
  }
  ```
- [ ] All 4 hook types (useState, useRef ×2, useZodForm, useEffect) are called unconditionally, in the same order, on every render.
- [ ] The early return is now AFTER the last hook call, BEFORE the rendering block.
- [ ] The useEffect dependency is `[node?.id]` (or `[node]`) and the effect body handles the null case.
- [ ] The diff is small (3-5 lines moved/changed). If the diff is larger, the worker may have done more than the F2 fix asked for.

### 4.2 PropertiesPanel.test.tsx — `as any` removal

Read lines 670-690. Confirm:

- [ ] The 2 `as any` casts at L678 and L683 are replaced with typed equivalents.
- [ ] The new type is one of: `as Node` (with `Node` imported from `@xyflow/react`), `as unknown as Node`, or use of the `mockNode` helper. The pre-existing `as any` at L30 is LEFT ALONE (out of scope per the F1-F4 review's frame).
- [ ] The test still asserts the same behavior: render with nodeA, switch to nodeB, expect "Node A" / "Node B" text to appear.
- [ ] The diff is small (~2-4 lines changed). Anything more is scope creep.

### 4.3 The `react-hooks/exhaustive-deps` warning

The F2 fix introduced (or revealed) a new warning at `PropertiesPanel.tsx:159` about missing dependencies in a useEffect. Determine:

- [ ] **Is the warning on the useEffect the F2 fix touched?** If yes, the warning is a direct consequence of the Rules of Hooks fix (the effect now closes over `data` and `form` which are referenced but not in the dep array). This is a **real finding**: the eslint rule is flagging that the effect's behavior depends on values not in the deps.
  - Severity: medium. The risk is the effect re-firing on stale closures, OR the effect not re-firing when it should (e.g., when `data` changes but `node.id` doesn't — switching between two `task` nodes would NOT re-run the form-reset effect).
  - The proper fix is one of: (a) use `useEffectEvent` (React 19+), (b) use a ref to hold the latest `data`/`form` and depend on `[node?.id]`, (c) `// eslint-disable-next-line react-hooks/exhaustive-deps` with a justification comment.
  - **If this warning is present and unaddressed, F2 is still FAIL.** Block and report.
- [ ] **Is the warning on a DIFFERENT useEffect (pre-existing)?** If yes, it's pre-existing baseline noise. Note in the report, don't block.

### 4.4 The 7 evidence files

- [ ] All 7 files exist in `/home/glenn/FlowmannerV2-frontend/.sisyphus/evidence/slice9-f2-fix/`
- [ ] `01-explicit-any.txt` shows exactly 1 error (line 30)
- [ ] `02-rules-of-hooks.txt` shows 0 errors
- [ ] `03-eslint.txt` exit code + error count match the worker's report
- [ ] `04-tsc.txt` is 0 bytes (silent pass) — verify exit code was 0
- [ ] `05-vitest-focused.txt` shows 56/56 tests pass
- [ ] `06-vitest-full.txt` shows 698/698 tests pass
- [ ] `07-build.txt` shows exit 0, build success

## 5. F1-F4 structured report (write as your final summary in the comment, then block with the verdict)

```
## F1-F4 Final-QA Re-Review — Slice 9 F2 Fix (commit 3f27850)

## F1 — Plan Compliance (vs F2 fix handoff §0, §1)
- [ ] 2 NEW `as any` errors removed at __tests__/PropertiesPanel.test.tsx:678,683
- [ ] Pre-existing Rules of Hooks violation fixed at PropertiesPanel.tsx:145 (early return moved after all hook calls)
- [ ] Pre-existing `as any` at __tests__/PropertiesPanel.test.tsx:30 LEFT ALONE (out of scope)
- [ ] No edits to: src/hooks/mission-builder/*.ts, components/ui/*, slice-10 files, backend, package.json
- [ ] No Radix/shadcn imports
- [ ] No new dependencies

## F2 — Code Quality
- [ ] `no-explicit-any` count: 3 → 1 (only L30 pre-existing)
- [ ] `react-hooks/rules-of-hooks`: 0 errors
- [ ] `react-hooks/exhaustive-deps`: <describe — PASS if no new warning on the F2-touched useEffect; FAIL if a new warning appeared there>
- [ ] 0 NEW eslint errors in the 2 F2-fix files (pre-existing baseline OK)
- [ ] 0 tsc errors
- [ ] No dead props / unused vars introduced
- [ ] PropertiesPanel tests: 56/56 green, including "resets form state"
- [ ] Full vitest: 698/698 green
- [ ] Build: exit 0

## F3 — Real Manual QA
- [ ] npm run build succeeds
- [ ] Frontend container status (verify on VPS — `ssh root@74.208.115.142 'docker ps --filter "name=flowmanner-frontend" --format "{{.Names}}: {{.Status}}"'`) — should show Up X minutes (built at 15:47 UTC). The F2 fix is LOCAL only, NOT deployed.
- [ ] HTTP 200 on https://flowmanner.com/en/missions (after 307→/signin redirect) — should still be the slice-10 deploy from 17:47, NOT the F2 fix.

## F4 — Scope Fidelity
- [ ] Diff in 3f27850 contains ONLY: PropertiesPanel.tsx, __tests__/PropertiesPanel.test.tsx
- [ ] No backend changes
- [ ] No edits to slice-10 files
- [ ] No edits to src/hooks/mission-builder/*.ts
- [ ] No new dependencies
- [ ] No deleted files

## VERDICT
PASS / FAIL (with findings)
```

## 6. Hard rules

- **DO NOT commit, push, or deploy.** Your job is review, not ship.
- **DO NOT modify any source files.** If you find a bug, BLOCK and report — don't fix.
- **DO NOT re-run `deploy-frontend.sh`.** The F2 fix is local-only, not deployed. The user's "you say" report on the slice-10 deploy is still valid.
- **English only** in your report.
- **If a verify step exits non-zero, do NOT keep running the next step.** Block immediately with the failing command and exit code.
- **The exhaustive-deps warning IS in F2 scope.** Do not wave it through as "pre-existing baseline" without reading the code to confirm it's on a pre-existing useEffect, not the one the F2 fix touched.

## 7. Block pattern

After running all 8 verify steps and writing the F1-F4 report as a comment, call:

```
kanban_block(reason="review-required: F1-F4 final-QA re-review — <PASS|FAIL> on commit 3f27850")
```

If PASS: also include "slice 9 ready to merge + push + deploy" in the comment.
If FAIL: include the specific finding (file:line, expected vs actual, severity) in the comment body, not just the reason string.

**Do NOT call `kanban_complete`.** The orchestrator (user) decides next.

## 8. Provenance + references

- Source review request: user message 2026-06-15 18:32
- Prior F1-F4 review: kanban `t_7af285a6` (blocked 17:32, FAIL on F2)
- F2 fix handoff: `/opt/flowmanner/.sisyphus/drafts/slice9-f2-fix-handoff.md`
- F2 fix commit: `3f27850` on `glennguilloux/flowmanner` (master, local, NOT pushed)
- Slice 9 commit: `9a623d0` (parent of F2 fix)
- Slice 10 commit: `358d4b8` (parallel branch, not affected by F2 fix)
- Skill reference: `~/.hermes/skills/subagent-implementation-handoff/`, `~/.hermes/skills/devops/kanban-worker/`

# Begin.
