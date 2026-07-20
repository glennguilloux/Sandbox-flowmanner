# B2 — Mission Builder × Chat: Architecture Relationship

> Read-only brainstorm. No repo files edited. All claims cite file:line.
> Frontend root inspected: `/home/glenn/FlowmannerV2-frontend/.worktrees/t_b1499055`
> Backend confirmed live: `/opt/flowmanner/backend/app/api/v2/`

## 1. Current coupling map

**Builder produces a Blueprint, not a Mission.**
`FlowEditor.handleSave` (FlowEditor.tsx:1038-1059) serializes the graph with `flowToMission` (FlowEditor.tsx:217) → `missionToBlueprintPayload` (FlowEditor.tsx:125) and POSTs/PATCHes `/api/v2/blueprints/` (FlowEditor.tsx:1046-1048). The payload shape is `{title, description, definition:{blueprint_type:"solo", nodes:[{id,type,title,config:{position,data}}], edges:[{source,target,label}], config:{groups, edgeMeta}}}` (FlowEditor.tsx:132-162). Visual layout is stuffed into `config` because the backend `Blueprint` schema has no position/data columns (runs.ts:8-16). Reverse mapping `blueprintToMissionFlow` (FlowEditor.tsx:172) reconstructs the graph.

**Builder launches a Run, not a chat session.**
`handleRun` (FlowEditor.tsx:1333-1356) calls `startRun(savedId, {})` → `POST /api/v2/blueprints/{id}/run` (runs.ts:128-133). A `Run` (runs.ts:18-26) returns `id, status, snapshot, output_data, ...` — a workflow execution record, unrelated to chat threads. `useExecutionPoll` (imported FlowEditor.tsx:52) polls `/api/v2/runs/{id}/events`. There is **no mission_id in the Run**, and **no blueprint→mission or blueprint→thread link** anywhere in the save/run path.

**Chat consumes only two things from the Builder today.**
1. A `mission_status` canvas tile (chat-types.ts:428) that renders `MissionStatusTile` and polls `GET /api/v2/missions/{id}/status` (MissionStatusTile.tsx:64) every 5s. That endpoint returns `{mission_id, status, total_tasks, completed_tasks, failed_tasks, ...}` wrapped in the v2 envelope `ok(...)` (missions.py:358-363; base.py envelope at base.py:3-7).
2. The SSE chat runtime: `POST /api/v2/chat/threads/{thread_id}/chat/stream` (chat.py:471-520) takes only `{content, model, attachments, system_prompt, web_search}` — **no blueprint_id / mission_id field** (chat.py:241-254 `ChatMessageCreate`).

**The gap is concrete:** the Builder emits a `Blueprint` + `Run`; Chat can only attach a `missionId` to a canvas tile and watch its status. There is no path for a built graph to become a chat-runnable agent, and no path for chat (NL) to author the graph. The only live wire is one-directional read-only polling of an already-existing mission.

## 2. Relationship decision — (b) Builder FEEDS chat

Pick **Builder FEEDS chat**: a saved Blueprint becomes a chat-runnable agent / thread. Rationale grounded in the real schemas:

- The Builder already owns a durable, versioned object (`Blueprint`, runs.ts:8) with a stable `id` and definition. Chat already owns durable threads (`ChatThread`, chat-types.ts:41) and a tile system keyed by `kind` (`TileKind`, chat-types.ts:421-428). The seams exist; they just aren't connected.
- Option (a) "chat drives the builder" would require the LLM to emit the full `definition` schema (FlowEditor.tsx:132) including `config.groups` / `edgeMeta` round-trip fidelity — high risk, the reverse-map already relies on fragile index-order assumptions (FlowEditor.tsx:197-205). Defer.
- Option (c) "shared hub" is over-engineering for a system at this scale (one team, modular monolith). It adds a third aggregate to keep in sync with no current payoff.

So: the smallest honest relationship is **Blueprint → Run → Mission reference surfaced in the chat thread that launched it**, with the existing `mission_status` tile as the consumption endpoint.

## 3. Concrete first build step

**Goal:** let a Builder user open a chat thread pre-wired to a just-run workflow, and see that run's mission_status tile live — no new backend model, no schema migration.

**Files to touch (all frontend):**
- `src/components/mission-builder/FlowEditor.tsx` — after `handleRun` succeeds (FlowEditor.tsx:1347-1351), capture `run.id` and call a new helper `openChatForRun(runId, missionName)`.
- `src/lib/api/runs.ts` — confirm `Run` already carries `mission_id?` (runs.ts:29 `RunEvent.mission_id` exists on events, but `Run` itself at runs.ts:18-26 does **not**). If the backend `startRun` response includes a `mission_id`, read it; otherwise fall back to polling `GET /api/v2/runs/{id}` to fetch it.
- `src/stores/chat-store.ts` — add one action `openThreadWithMissionTile(threadId, missionId)` that creates/selects a thread and calls `addCanvasTile("mission_status", title, { missionId })` (existing action at chat-store.ts:390-428; tile already renders via MissionStatusTile.tsx:49).
- A new tiny module `src/lib/chat-launch.ts` — `createThread(launch blueprint run)` → `POST /api/v2/chat/threads` (chat.py:178-185, envelope `ok(...)`) then `addCanvasTile("mission_status", ...)` with the `missionId`.

**Data flow:** Builder `handleRun` → `startRun` returns `Run{id}` → fetch `mission_id` (from run response or `/api/v2/runs/{id}`) → `POST /api/v2/chat/threads` → `addCanvasTile("mission_status",{missionId})` → user lands in chat with the live `MissionStatusTile` already polling `/api/v2/missions/{id}/status`. This reuses 100% of existing endpoints and the existing tile renderer. Zero backend changes.

## 4. Risks / contract gaps

- **Run→Mission link is the weak seam.** `Run` (runs.ts:18-26) has no `mission_id`; only `RunEvent.mission_id` (runs.ts:29) does. The first step must establish where the `mission_id` comes from. Confirm the v2 `POST /api/v2/blueprints/{id}/run` response actually populates a mission, or the tile will have no `missionId` to poll (MissionStatusTile.tsx:55-57 errors "No missionId in tile payload").
- **Auth parity:** both `/api/v2/chat/threads` (chat.py:182) and `/api/v2/missions/{id}/status` (missions.py:360) use `get_current_user` — same JWT, same `fm_tokens` key the frontend already sends (AGENTS.md auth section). No auth gap.
- **Envelope drift:** chat endpoints return `ok(data)` (data at top level); `MissionStatusTile` reads `res` directly as `MissionStatusData` (MissionStatusTile.tsx:66) — it currently assumes the raw object, NOT `res.data`. If the status route returns the envelope `{data:{...}}`, the tile's destructure breaks. **Confirm the FE `apiClient` unwraps `.data` centrally** before relying on it; this is the most likely silent contract bug.
- **Envelope exemption on SSE:** `/chat/stream` is a `StreamingResponse`, envelope-exempt (chat.py:496-520). Not in scope for step 3 but relevant if step 3 later injects blueprint context into the prompt.
- **Tile idempotency:** `addCanvasTile` de-dupes by `kind` (chat-store.ts:396-407) — a second run in the same thread updates the existing `mission_status` tile's `payload`, which is the desired behavior, but means one thread shows only the latest mission, not a history. Acceptable for v1.

**Verdict:** Build step 3 as described. It is reversible (frontend-only, no migration), leverages the existing v2 envelope + tile system, and establishes the one missing link (Run→Mission id) that every future Builder×Chat feature will need.
