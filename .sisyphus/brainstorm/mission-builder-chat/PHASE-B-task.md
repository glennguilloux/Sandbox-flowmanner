# Phase B — Frontend: bidirectional MissionStatusTile (the v1 seam)

You are injected as a FRONTEND DEVELOPER persona. Implement the frontend half of
the deep-dive plan at
`/opt/flowmanner/.sisyphus/brainstorm/mission-builder-chat/DEEP-DIVE-PLAN.md`
(section 2, Phase B: tasks B1–B3). This is a REAL implementation card
(frontend-only; Phase A already landed the backend Run→Mission link).

## The verified problem (fix these, don't re-litigate)
The ONLY bridge between the Mission Builder and Chat is `MissionStatusTile`, and
it is broken TWICE (confirmed live 2026-07-19):

1. **Empty payload dead-end.** The tile reads `missionId` from its canvas-tile
   payload (`MissionStatusTile.tsx:49`). The only way to add the tile is the
   "Add tile" dropdown (`Canvas.tsx:226`), which calls
   `onAdd(kind, label)` with NO payload (`Canvas.tsx:252`) →
   `handleAddTile` → `addCanvasTile(kind, label)` (`Canvas.tsx:314`) →
   the tile renders *"No missionId in tile payload."* (`MissionStatusTile.tsx:55-58`).
   A normal user can NEVER get a working tile.
2. **Wrong envelope read.** `GET /api/v2/missions/{id}/status` returns
   `ok(...)` → `{data:{...}, meta, error}` (`backend/app/api/v2/missions.py:358-363`).
   But the tile does `setData(res as MissionStatusData)` (`MissionStatusTile.tsx:66`),
   treating the WHOLE envelope as data. So `res.mission_id` (`MissionStatusTile.tsx:102`)
   is always `undefined`. **The tile has never worked, even with a valid id.**

Phase A already made `POST /api/v2/blueprints/{id}/run` return a non-null
`mission_id` in the `Run` object (`backend/app/schemas/blueprint.py:143` now has
`mission_id`; `RunService.create_from_blueprint` links a Mission). So now there IS
something to poll — Phase B wires the frontend to it.

## Tasks (implement, in order)

**B1 — Fix + make `MissionStatusTile` a two-way bridge.**
File: `/home/glenn/f/src/components/chat/tiles/MissionStatusTile.tsx`
- **Fix envelope:** change `setData(res as MissionStatusData)` (line 66) to
  `setData(res.data as MissionStatusData)` so `mission_id`/`status`/`total_tasks`
  etc. read from the unwrapped payload. (The v2 contract ALWAYS wraps in `ok()` —
  see `backend/app/api/v2/AGENTS.md` envelope section. Do not change the endpoint.)
- **Backward seam:** wrap the card (or add a button) that links to the builder
  for this mission: navigate to `/missions/builder?missionId=<id>`. The tile
  already holds `missionId` (`MissionStatusTile.tsx:49`). Use `next/navigation`
  `useRouter()` (or the app's existing nav helper — check `Canvas.tsx` imports).
- **Forward seam:** add a "Discuss" button → navigate to `/chat?missionId=<id>`.
  (Phase C's `chat/page-client.tsx` will auto-open the tile from that URL; this
  button is the user-facing trigger.)

**B2 — `chat/page-client.tsx` auto-opens the tile from URL.**
File: `/home/glenn/f/src/app/[locale]/(dashboard)/chat/page-client.tsx`
- On mount, if the URL has `?missionId=<id>`, call
  `store.addCanvasTile("mission_status", "Mission Status", { missionId })` (existing
  action at `/home/glenn/f/src/stores/chat-store.ts:390`). This makes the tile
  arrive PRE-POPULATED instead of showing "No missionId" (`MissionStatusTile.tsx:55`).
- Read the query param via `useSearchParams()` (or the app's router helper).
  Guard so it only adds once (the store de-dupes by `kind` at `chat-store.ts:396`,
  but avoid re-adding on every render — use a ref or effect dependency).

**B3 — `Canvas.tsx` "Add tile" pre-fills payload from URL.**
File: `/home/glenn/f/src/components/chat/Canvas.tsx`
- The `AddTileButton` signature is `onAdd: (kind, label) => void` (line 216)
  and it calls `onAdd(k.kind, k.label)` (line 252). `handleAddTile` (line 314)
  calls `addCanvasTile(kind, label)` with no payload.
- Extend the chain so that when `kind === "mission_status"` AND a
  `?missionId=` is present in the URL, the tile is added with
  `payload: { missionId }`. Minimal change:
  - `AddTileButton` prop becomes `onAdd: (kind, label, payload?) => void`;
    pass `payload` through at line 252.
  - `handleAddTile` (line 314) becomes `addCanvasTile(kind, label, payload)`;
    compute the payload for `mission_status` from the URL `missionId`.
- This is defensive (B2 is the main entry); implement it so the manual
  "Add tile" path also yields a working tile when a missionId is in the URL.

## Acceptance (you must PROVE these)
1. `MissionStatusTile` reads `res.data` (envelope fix) — cite the line.
2. With a real `mission_id`, the tile polls `GET /api/v2/missions/{id}/status`
   and shows live status (not the "No missionId" error). Prove by rendering or by
   unit-testing the fetch path with a mocked `ok({data:{...}})` response.
3. Clicking the tile (or its button) opens `/missions/builder?missionId=<id>`;
   the "Discuss" button opens `/chat?missionId=<id>`.
4. `?missionId=<id>` on the chat page auto-adds a populated `mission_status` tile.
5. `npx tsc --noEmit` passes in the frontend worktree. If `node_modules`
   is missing in the worktree, symlink the main repo's:
   `ln -sfn /home/glenn/FlowmannerV2-frontend/node_modules <wt>/node_modules`
   (the worktree is under `/home/glenn/FlowmannerV2-frontend/.worktrees/<id>`).
6. Existing `*.test.tsx` for `MissionStatusTile` / `Canvas` still pass (adjust them
   if you changed the `onAdd`/`addCanvasTile` signature — update call sites, don't
   break them).

## Hard rules for this card
- **NO `--skill`** — frontend cards must not pass a skill (stale gateway catalog
  crash). All conventions live in this body + the existing code.
- **Frontend repo symlink:** the worktree is under `/home/glenn/f`
  (`/home/glenn/FlowmannerV2-frontend`). The brand dir is `FlowmannerV2-frontend`
  (double-N, single-P) — never `Flowmapper`.
- Do NOT edit backend files (Phase A owned those).
- Do NOT implement Phase C (the Builder `FlowEditor.handleRun` → chat handoff);
  that is a separate card. You may ADD the `/chat?missionId=` consumer hook in B2
  (it's needed for the tile), but leave `FlowEditor.tsx` alone.
- Commit on your exclusive branch. Block-for-review when done (`hermes kanban block <id>`).
  Do NOT push/merge/deploy.
- Report: the exact lines changed in each file, the tsc result, and the test result.
