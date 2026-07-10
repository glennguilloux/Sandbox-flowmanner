# Task: Migrate Builder from v1 Graphs API to v2 Blueprints API

**Date:** 2026-06-29
**Estimated effort:** 2-4 hours
**Priority:** High — completes Track A parallel work (60-day plan §3.1)

---

## The Thesis

The FlowManner builder (`FlowEditor.tsx`) still saves workflows to the legacy v1 `/api/graphs/` endpoint. The v2 `/api/v2/blueprints/` API already exists and is used by the runs page, listing, and publishing. This task migrates the builder's save and run paths to v2, completing the frontend side of the Blueprint/Run data model transition.

---

## What Needs to Change

### File: `src/components/mission-builder/FlowEditor.tsx`

**Five API calls to migrate (plus one in the polling hook):**

| # | Current (v1) | Target (v2) | Location |
|---|---|---|---|
| 1 | `POST /api/graphs/` (create) | `POST /api/v2/blueprints/` | FlowEditor.tsx ~line 950 |
| 2 | `PATCH /api/graphs/{id}` (update) | `PATCH /api/v2/blueprints/{id}` | FlowEditor.tsx ~line 948 |
| 3 | `POST /api/graphs/{id}/execute` (run) | `POST /api/v2/blueprints/{id}/run` | FlowEditor.tsx ~line 1249 |
| 4 | `POST /api/graphs/{id}/execute` (run from node) | `POST /api/v2/blueprints/{id}/run` | FlowEditor.tsx ~line 1267 |
| 5 | `POST /api/graphs/{id}/resume/{execId}` (resume) | ❌ No v2 equivalent yet | FlowEditor.tsx ~line 1291 |
| 6 | `GET /api/graphs/{id}/executions/{execId}` (poll) | `GET /api/v2/runs/{runId}` | useExecutionPoll.ts ~line 92 |

**⚠️ API call #5 (resume):** The v2 runs API has `POST /runs/{run_id}/abort` and `POST /runs/{run_id}/retry` but NO resume endpoint. Leave this on v1 and add a `// TODO: migrate to v2 when resume endpoint is available` comment.

**⚠️ API call #6 (polling):** The v2 path is `GET /api/v2/runs/{run_id}` (not nested under blueprints). The `run_id` comes from the run creation response (call #3), not the blueprint ID. You'll need to store the `run_id` separately from the `blueprint_id`.

**Payload mapping:**

```typescript
// Current v1 payload (line ~937):
const payload = {
  name: missionName,
  description: missionDescription,
  nodes: mNodes,
  edges: mEdges,
  groups: mGroups,
};

// New v2 payload:
const payload = {
  title: missionName,           // name → title
  description: missionDescription,
  definition: {                 // wrap nodes/edges/groups into definition
    nodes: mNodes,
    edges: mEdges,
    groups: mGroups,
    blueprint_type: "solo",     // default type
  },
};
```

**Run payload** (currently `{ input_data: {} }`): stays the same — `RunCreate` accepts `{ input_data: {} }`.

**Response handling:** The `apiClient` already auto-unwraps the v2 envelope (`{data, meta, error}` → returns `data`) at `src/lib/api-client.ts:190-194`. No change needed for response parsing.

---

## What Already Exists (DO NOT REBUILD)

- `src/lib/api/runs.ts` — already calls `POST /api/v2/blueprints/{id}/run`
- `src/lib/api-client.ts:190-194` — auto-unwraps v2 envelope
- `backend/app/api/v2/blueprints.py` — full CRUD + run endpoints
- `backend/app/schemas/blueprint.py` — `BlueprintCreate`, `BlueprintUpdate`, `RunCreate`
- `backend/app/schemas/blueprint.py:59` — `BlueprintDefinition` has `nodes`, `edges`, `budget`, `config`

---

## Execution Plan

### Step 1: Read and understand the current code (15 min)
- Read `FlowEditor.tsx` around lines 935-960 (handleSave) and 1245-1255 (handleRun)
- Read `src/lib/api/runs.ts` to see the existing v2 blueprint call pattern
- Read `backend/app/schemas/blueprint.py` to confirm the `BlueprintCreate` shape

### Step 2: Write a failing test or verify with manual test (15 min)
- The builder doesn't have unit tests for the API calls (they're in a React component)
- Manual verification: open the builder, save a workflow, check network tab shows `/api/v2/blueprints/`

### Step 3: Migrate handleSave (30 min)
- Change `POST /api/graphs/` → `POST /api/v2/blueprints/`
- Change `PATCH /api/graphs/${savedId}` → `PATCH /api/v2/blueprints/${savedId}`
- Map `name` → `title`
- Wrap `nodes/edges/groups` into `definition: { nodes, edges, groups, blueprint_type: "solo" }`
- The response `{ id }` should still work (v2 envelope auto-unwraps to the blueprint object which has `id`)

### Step 4: Migrate handleRun (15 min)
- Change `POST /api/graphs/${savedId}/execute` → `POST /api/v2/blueprints/${savedId}/run`
- Keep `{ input_data: {} }` as-is
- The response should return a run object with `id` — verify the polling still works

### Step 5: Check for other `/api/graphs/` references (15 min)
- Search the entire frontend for `/api/graphs/` references
- The `GraphsService` in the SDK (`src/lib/sdk/services/GraphsService.ts`) is auto-generated — do NOT modify it
- The `sdk-client.ts` exports `Graphs = SDK.GraphsService` — leave it (legacy compat)
- Only change the direct `apiClient` calls in `FlowEditor.tsx`

### Step 6: Verify (30 min)
- TypeScript: `npx tsc --noEmit` — must pass with zero errors
- Manual test: open builder → create a workflow → save → verify it appears in the blueprints list
- Manual test: click Run → verify execution starts → verify status polling works
- Check that the old `/missions` page still works (reads via compat layer)

---

## Key Risks

1. **Response shape difference.** v1 returns `{ id }` directly. v2 returns `{ data: { id, title, ... }, meta: {...}, error: null }` which `apiClient` auto-unwraps to `{ id, title, ... }`. The `data.id` access should still work, but verify `data.id` is a string (UUID), not an integer.

2. **`definition` vs flat `nodes/edges/groups`.** The v1 API accepted `nodes`, `edges`, `groups` as top-level fields. The v2 API wraps them in `definition`. If the backend's `BlueprintCreate` schema doesn't accept `groups` inside `definition`, you may need to check `BlueprintDefinition` for a `groups` field or omit it.

3. **Polling after run.** The current code polls `/api/graphs/${savedId}/execute` — after migration, the polling endpoint may need to change too. Check `startPolling()` to see what endpoint it polls.

4. **Auto-save.** There's an auto-save mechanism (`lastSavedSnapshotRef`). Make sure the payload shape change doesn't break the dirty-check logic.

---

## Files to Check (read-only, do not modify unless needed)

| File | Why |
|---|---|
| `src/components/mission-builder/FlowEditor.tsx` | **PRIMARY** — the 5 API calls to migrate |
| `src/hooks/mission-builder/useExecutionPoll.ts` | **SECONDARY** — polling endpoint (line 92) |
| `src/lib/api/runs.ts` | Reference: existing v2 blueprint calls |
| `src/lib/api-client.ts` | Reference: v2 envelope auto-unwrap |
| `backend/app/schemas/blueprint.py` | Reference: `BlueprintCreate`, `BlueprintDefinition` |
| `backend/app/api/v2/blueprints.py` | Reference: endpoint signatures |

---

## Verification Checklist

- [ ] `npx tsc --noEmit` passes (frontend)
- [ ] Builder save creates a blueprint visible at `/api/v2/blueprints`
- [ ] Builder update (re-save) works
- [ ] Builder run starts execution via `/api/v2/blueprints/{id}/run`
- [ ] Status polling works after run
- [ ] Auto-save still detects dirty state correctly
- [ ] No remaining `apiClient` calls to `/api/graphs/` in FlowEditor.tsx
- [ ] Old `/missions` page still works (compat layer reads from blueprints)
- [ ] TypeScript clean

---

## Commit Message

```
feat(builder): migrate save/run from v1 /api/graphs to v2 /api/v2/blueprints

Switches the FlowEditor's three API calls (create, update, execute) from
the legacy v1 graphs endpoint to the v2 blueprints endpoint. Payload
mapped: name→title, nodes/edges/groups wrapped in definition object.

The apiClient's v2 envelope auto-unwrap handles response parsing.
```
