# Exit Audit — Builder v2 Blueprint Round-Trip, Execution Overlays & Blueprints Migration

**Date:** 2026-06-29
**Machine:** Homelab (172.16.1.1)
**Repo:** FlowmannerV2-frontend
**Branch:** main (8 uncommitted files)
**TypeScript:** ✅ 0 errors
**Tests:** ✅ 98/98 FlowEditor tests pass | 834/837 full suite (3 pre-existing WhyDrawer `next-intl` failures)

---

## WHAT CHANGED

| File | Δ | Description |
|------|---|-------------|
| `src/lib/api/runs.ts` | +8 | Added `fetchBlueprintById(id)`, `deleteBlueprint(id)` → v2 blueprint API |
| `src/app/.../missions/builder/page.tsx` | +10 | Reads `?blueprint=` and `?graph=` search params (backwards compat), passes `blueprintId` to page-client |
| `src/app/.../missions/builder/page-client.tsx` | +47 | Fetches blueprint by ID, converts to MissionFlow via imported `blueprintToMissionFlow`, shows loading state, falls back to empty canvas on error |
| `src/components/mission-builder/FlowEditor.tsx` | +154 | Extracted `missionToBlueprintPayload` + `blueprintToMissionFlow` as exported pure functions; `handleStop` now calls `abortRun(executionId)` (best-effort); removed dead code and unused imports |
| `src/components/mission-builder/FlowEditor.test.tsx` | +352 | 18 new tests: 8 for `missionToBlueprintPayload`, 10 for `blueprintToMissionFlow` (incl. full round-trip test) |
| `src/hooks/mission-builder/useExecutionPoll.ts` | +88 | v2 events polling (`task.started`/`completed`/`failed`); `node_id`/`task_id` fallback; configurable `v2PollingIntervalMs` option (default 2500ms) |
| `src/app/.../graphs/page-client.tsx` | +106 | Full rename: `GraphWorkflow` → `Blueprint`, `Graphs` SDK → v2 API (`fetchBlueprints`, `startRun`, `deleteBlueprint`), UI text updated |
| `src/app/.../graphs/[id]/executions/page-client.tsx` | +5 | Swapped `Graphs.runGraphApiGraphs...` → `startRun()` from v2 API |

**Total:** 8 files, +660 / -110

---

## WHAT WAS IMPLEMENTED

### 1. Round-Trip Load Path
- `fetchBlueprintById(id)` added to `runs.ts` calling `GET /api/v2/blueprints/${id}`
- Builder `page.tsx` reads both `?blueprint=` and `?graph=` params (backward compat with existing nav links)
- `page-client.tsx` fetches blueprint, converts to `MissionFlow` via `blueprintToMissionFlow`, passes as `initialFlow` to FlowEditor
- Loading spinner shown during fetch, error logged and empty canvas on failure

### 2. Exported Pure Functions for v1↔v2 Conversion
- **`missionToBlueprintPayload(name, description, mNodes, mEdges, mGroups)`** — Converts MissionEditor nodes/edges/groups → v2 BlueprintCreate payload. Visual layout (positions, data) stored in `config` fields; groups and edge metadata in `definition.config`.
- **`blueprintToMissionFlow(bp: Blueprint)`** — Inverse of above. Reconstructs MissionFlow from v2 Blueprint with position/data from `config`, edge id/type from `config.edgeMeta`, groups from `config.groups`.
- Both extracted to FlowEditor.tsx alongside existing `flowToMission`/`validateFlow`, following file conventions (no `export` keyword, exported via block).

### 3. v2 Abort Endpoint Wired
- `handleStop` is now async: calls `abortRun(executionId)` best-effort (silently catches errors if run is already terminal), then clears local state and shows "Execution stopped" toast.
- Removed stale TODO comment.

### 4. v2 Events Polling for Visual Overlays
- Polling hook fetches incremental events via `fetchRunEvents(runId, { fromSequence })` on each poll tick for v2 runs
- `task.started` → status `"running"` (clay-colored Loader2 spinner in FlowEditor)
- `task.completed` → status `"completed"` (green check overlay)
- `task.failed` → status `"failed"` (red X overlay)
- Accumulated states persist across poll ticks; merged with v1 `node_states` if present
- `lastSequenceRef` tracks incremental fetch cursor, reset on `startPolling`/`clearState`
- `nodeId` extraction uses `(payload?.node_id ?? payload?.task_id)` fallback (backend uses `task_id` for `task.started`)

### 5. Configurable Polling Interval
- v2 runs: configurable via `v2PollingIntervalMs` option (default 2500ms)
- v1 legacy runs: always 1s (unchanged)
- Stored in `v2IntervalRef` to avoid stale closures
- Consumers can pass `{ v2PollingIntervalMs: 3000 }` to customize

### 6. Builder Navigation Update
- Graphs list page Edit button: `?graph=` → `?blueprint=` (only `?graph=` reference in codebase)

### 7. Graphs → Blueprints Full Migration
- `GraphWorkflow` interface removed, replaced with `Blueprint` type from `runs.ts`
- Local `PaginatedResponse` interface removed, using generic `PaginatedResponse<Blueprint>` from `runs.ts`
- All v1 `Graphs.*` SDK calls replaced with v2 API: `fetchBlueprints`, `startRun`, `deleteBlueprint`
- `deleteBlueprint(id)` → `DELETE /api/v2/blueprints/${id}` (backend endpoint already existed)
- Component renamed `GraphsClient` → `BlueprintsClient`, state `graphs` → `blueprints`
- All UI text updated: "Graphs" → "Blueprints", "Execute" → "Run", `name` → `title`
- Executions detail page: `runGraphApiGraphs...` → `startRun(workflowId)`
- Executions page retains `Graphs` SDK for list/get endpoints (no v2 equivalent yet)

---

## TESTS RUN + RESULT

```bash
cd /home/glenn/FlowmannerV2-frontend
npx vitest run src/components/mission-builder/FlowEditor.test.tsx
```

| Suite | Tests | Result |
|-------|-------|--------|
| `validateFlow` | 16 | ✅ |
| `flowToMission` | 10 | ✅ |
| `missionToBlueprintPayload` | 8 | ✅ NEW |
| `blueprintToMissionFlow` | 10 | ✅ NEW |
| `EdgeLabelEditor` | 8 | ✅ |
| `FlowActions` | 6 | ✅ |
| `ExecutionStatusPanel` | 12 | ✅ |
| `ValidationBadge` | 4 | ✅ |
| `FlowEditorInner` | 24 | ✅ |
| **Total** | **98** | **✅ All pass** |

**Full suite:** 834/837 pass. 3 failures are pre-existing WhyDrawer `next-intl` context errors (unrelated).

---

## VERIFICATION CHECKLIST

- [x] `npx tsc --noEmit` — 0 errors
- [x] `npx vitest run FlowEditor.test.tsx` — 98/98 pass
- [x] Round-trip test: `missionToBlueprintPayload` → `blueprintToMissionFlow` preserves all data
- [x] Empty inputs handled gracefully
- [x] `as any` casts limited to test fixtures only (2 instances)
- [x] `abortRun` call is best-effort with silent catch
- [x] Events fetch is best-effort with silent catch (overlays catch up on next tick)
- [x] Ref cleanup in both `startPolling` and `clearState`
- [x] No circular dependencies (page-client imports from FlowEditor, not vice versa)
- [x] `?graph=` param still works via builder `page.tsx` fallback (`params?.blueprint ?? params?.graph`)
- [x] Code reviewed by code-reviewer-mimo-pro — no issues found

---

## NOT DONE / DEFERRED

| Item | Reason |
|------|--------|
| Unit tests for `useExecutionPoll` v2 events logic | Requires mocking `fetchRunEvents` and `setInterval` — deferred to next session |
| `task.skipped` event support | Out of scope; would need backend verification of payload shape |
| Running node tooltip (task_title, attempt number) | Enhancement; `task.started` payload includes these fields but output not stored |
| Migrate executions page `Graphs` SDK calls to v2 | `listExecutions`, `getExecution`, `getItem` have no v2 equivalents yet |
| Commit & push | All 8 files are uncommitted — needs human review first |

---

## DEPLOY INSTRUCTIONS

```bash
# From homelab — frontend only (no backend changes)
bash /opt/flowmanner/deploy-frontend.sh

# Verify
curl -s https://flowmanner.com/api/health | jq .
```

**Note:** No backend deploy needed. The v2 events endpoint and blueprint fetch endpoint already exist. This session only changed frontend code.

---

## KNOWN RISKS

1. **`task.started` payload uses `task_id` not `node_id`** — The `??` fallback handles this, but if the backend ever changes the field name, overlays would silently break for running nodes only (completed/failed would still work).
2. **Events fetch runs on every poll tick (2.5s)** — Two HTTP requests per tick (status + events). Acceptable for now but could be optimized by only fetching events when status is non-terminal.
3. **`blueprintToMissionFlow` uses `as unknown as NodeDataExtra` cast** — Necessary because API returns `Record<string, unknown>`. The round-trip test verifies data integrity.
4. **3 pre-existing test failures** — WhyDrawer `next-intl` context errors. Unrelated to this session's changes.

---

## SESSION METRICS

| Metric | Value |
|--------|-------|
| Files modified | 8 |
| Lines added | +660 |
| Lines removed | -110 |
| Tests added | 18 (8 `missionToBlueprintPayload` + 10 `blueprintToMissionFlow`) |
| Test pass rate | 98/98 (FlowEditor) · 834/837 (full suite) |
| Code review iterations | 7 (one per major change) |
| TypeScript errors | 0 |

---

## FUTURE NATURAL WORK

1. **Commit & push** — All 8 files are uncommitted. Needs review + `git add` + conventional commit + push.
2. **Add unit tests for `useExecutionPoll` v2 events logic** — Mock `fetchRunEvents`, verify `task.started`/`completed`/`failed` → `NodeExecState` conversion, verify `lastSequenceRef` incremental cursor, verify accumulated states persist across poll ticks.
3. **Add `task.skipped` event support** — Backend emits these; would show a muted/skipped overlay on nodes.
4. **Running node tooltip** — `task.started` payload includes `task_title`, `task_type`, `attempt`. Could show these on hover over the running spinner.
5. **Optimize events fetch** — Only fetch events when status is non-terminal (skip events fetch on terminal poll tick since overlays are already final).
6. **Migrate remaining executions page SDK calls** — `listExecutions`, `getExecution`, `getItem` still use v1 `Graphs` SDK; need v2 equivalents.
7. **Rename `graphs/` route directory to `blueprints/`** — The URL path still says `/graphs/` but the content is now all blueprint terminology.
