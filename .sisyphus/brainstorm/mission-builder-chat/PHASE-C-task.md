# Phase C — Frontend: one-click Run→Chat handoff (the payoff)

You are injected as a FRONTEND DEVELOPER persona. Implement the FINAL piece of
the deep-dive plan at
`/opt/flowmanner/.sisyphus/brainstorm/mission-builder-chat/DEEP-DIVE-PLAN.md`
(section 2, Phase C). Phases A (backend Run→Mission link) and B
(bidirectional MissionStatusTile) are ALREADY landed and verified. Phase C
closes the loop: click **Run** in the Builder → land in a Chat thread
pre-wired to that run's mission, with the tile already polling.

## State you inherit (do NOT re-implement these)
- **Backend (Phase A, verified):** `POST /api/v2/blueprints/{id}/run`
  now returns a `Run` whose `mission_id` is non-null and matches a
  `missions` row (`backend/app/schemas/blueprint.py:143` + `run_service.py`
  `create_from_blueprint` links a Mission inline).
- **Frontend tile (Phase B, verified):** `MissionStatusTile` auto-populates
  from `?missionId=<id>` on the chat page (`chat/page-client.tsx` B2 hook),
  and has "Open in Builder" + "Discuss" nav seams. It reads the v2
  envelope correctly (apiClient.get already unwraps `ok()`).

## The gap Phase C fills
In `FlowEditor.tsx`, `handleRun` (line 1333) calls
`startRun(savedId, {})` (`runs.ts:128`) and gets `run.id`, then
`startPolling(run.id, "pending")` (line 1347-1351). It NEVER opens
Chat and NEVER carries the `mission_id` anywhere. So after a run, the
user is stuck in the Builder with no handoff. Phase C wires that handoff.

## Tasks (implement, in order)

**C0 — Extend the frontend `Run` type (required, or C1 won't typecheck).**
File: `/home/glenn/f/src/lib/api/runs.ts`
- The `Run` interface (line 18) has NO `mission_id` field. Phase A added it
  to the backend `RunResponse` but the frontend type was not updated.
- Add `mission_id?: string | null;` to the `Run` interface (near line 25,
  the other optional fields). This matches the now-populated backend field so
  `run.mission_id` compiles.

**C1 — `FlowEditor.tsx`: after `handleRun` succeeds, open Chat.**
File: `/home/glenn/f/src/components/mission-builder/FlowEditor.tsx`
- Add `import { useRouter } from "next/navigation";` (the file has NO router
  import today — verified). Add `const router = useRouter();` near the other
  hooks (the file uses `useCallback`/`useState` from react already, line 3).
- In `handleRun` (line 1333), AFTER `const run = await startRun(savedId, {})`
  (line 1347) succeeds: capture `run.mission_id` and navigate to chat with
  the mission id so Phase B's auto-populate hook fires:
  ```ts
  if (run?.mission_id) {
    router.push(`/chat?missionId=${encodeURIComponent(run.mission_id)}`);
  }
  ```
  Keep the existing `setExecutionId(run.id)` + `startPolling(run.id, "pending")`
  (lines 1348-1351) — the user should STILL see the local canvas
  poll AND get the chat handoff. The chat thread's tile (Phase B) will
  show the same mission live.
- Do NOT change `handleRunFromHere` (line 1359, sub-graph execution)
  unless it also should hand off — leave it as-is unless trivially safe.

**C2 (optional, only if it reduces duplication) — `chat-store.ts` helper.**
File: `/home/glenn/f/src/stores/chat-store.ts`
- Phase B already calls `store.addCanvasTile("mission_status", "Mission Status",
  { missionId })` from `chat/page-client.tsx` (the B2 hook). C1 navigates
  to `/chat?missionId=` which triggers that. So a separate
  `openThreadWithMissionTile` helper is NOT required — do NOT add one
  unless you find C1's navigation does not reliably trigger B2. If you add
  it, it must be a thin wrapper over the existing `addCanvasTile`
  (`chat-store.ts:390`) + the thread create. Prefer the simpler C1-only path.

## Acceptance (you must PROVE these)
1. `Run` interface in `runs.ts:18` has `mission_id?` and `run.mission_id`
   compiles in `handleRun`.
2. After a successful Builder Run, the app navigates to `/chat?missionId=<id>`
   (cite the line). Phase B's hook then auto-adds the populated tile — verify
   the URL + tile wiring by reading `chat/page-client.tsx` B2 hook.
3. `npx tsc --noEmit` passes in the frontend worktree. If `node_modules`
   is missing, symlink: `ln -sfn /home/glenn/FlowmannerV2-frontend/node_modules <wt>/node_modules`.
4. The existing `FlowEditor.test.tsx` + `MissionStatusTile.test.tsx` (Phase B)
   still pass via the repo's `npm test` (vitest). Adjust any call site you
   touched; do not break them.
5. (Manual reasoning, stated in your report) the handoff is one-click:
   Builder Run → Chat thread with live mission tile, no manual ID copy.

## Hard rules for this card
- **NO `--skill`** — frontend cards must not pass a skill (stale gateway
  catalog crash). All conventions are in this body + the existing code.
- **Frontend repo symlink:** worktree is under `/home/glenn/f`
  (`/home/glenn/FlowmannerV2-frontend`, double-N, single-P — never `Flowmapper`).
- Do NOT edit backend files (Phase A owns those; do NOT touch `runs.py`,
  `run_service.py`, `blueprint_models.py`, `blueprint.py`).
- Do NOT re-add the `res.data` envelope change to `MissionStatusTile` —
  Phase B verified apiClient.get already unwraps `ok()`; double-unwrapping
  would BREAK it.
- Commit on your exclusive branch. Block-for-review when done
  (`hermes kanban block <id>`). Do NOT push/merge/deploy.
- Report: the exact lines changed in `FlowEditor.tsx` + `runs.ts`, the tsc
  result, and the test result. Cite file:line for every change.
