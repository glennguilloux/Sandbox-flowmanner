# B2 — Mission Builder × Chat: ARCHITECTURE relationship (read-only brainstorm)

You are injected as a SOFTWARE ARCHITECT persona. Deliverable = an architecture
brief + a concrete first build step. Read-only: do NOT edit any repo file. Write your
deliverable to the stable path
`/opt/flowmanner/.sisyphus/brainstorm/mission-builder-chat/B2-ARCH.md`.

## The problem
The Mission Builder (React Flow node graph) and Chat (agent runtime / SSE / threads)
are effectively disconnected. The only bridge is a `MissionStatus` canvas tile polling
`/api/v2/missions/{id}/status`. Glenn wants a way forward for how they should relate,
and specifically what to BUILD FIRST.

## Ground yourself in REAL source (cite file:line)
Frontend root (symlink): `/home/glenn/f`
- Builder graph model + node defs: `/home/glenn/f/src/components/mission-builder/FlowEditor.tsx`
  and `/home/glenn/f/src/components/mission-builder/nodes/*.tsx`
- Builder -> run: `/home/glenn/f/src/lib/api/runs.ts` (`startRun`, `abortRun`)
- Mission types: `/home/glenn/f/src/lib/mission-types.ts`
- Chat runtime: `/home/glenn/f/src/components/chat/SSEChat.tsx`,
  `/home/glenn/f/src/app/[locale]/(dashboard)/chat/page-client.tsx`
- Chat store: `/home/glenn/f/src/stores/chat-store.ts`
- Canvas tiles (where a mission could surface in chat):
  `/home/glenn/f/src/components/chat/tiles/MissionStatusTile.tsx`
- Backend mission/chat APIs (confirm live routes, do not trust memory):
  `/opt/flowmanner/backend/app/api/v2/` — look for `missions*.py`, `chat*.py`.
  Enumerate the real endpoints the frontend actually calls (grep `/home/glenn/f/src`
  for `/api/v2/missions` and `/api/v2/chat`).

Open these and cite file:line. Confirm the backend contract (v2 envelope: ok()/paginated()/err()).

## Your deliverable (write to .../B2-ARCH.md)
An architecture brief, max ~700 words:
1. **Current coupling map** — what the Builder produces (graph JSON? a Blueprint?
   a Mission?), how it is currently launched, and what Chat can consume today.
   Cite file:line. Be precise about data shapes (graph node/edge schema vs mission schema).
2. **The relationship decision** — pick one:
   (a) Chat DRIVES the builder (NL → graph draft, chat edits nodes),
   (b) Builder FEEDS chat (a built mission becomes a chat-runnable agent / thread),
   (c) Shared hub (a third object both reference).
   Justify with the real schemas you found.
3. **Concrete first build step** — the SINGLE smallest high-leverage change that starts
   the relationship. Name the exact files to touch, the endpoint to add or use, and the
   data flow. Must be real (anchored to existing code), not aspirational.
4. **Risks / contract gaps** — any v1→v2 envelope/auth mismatches, missing endpoints,
   or schema drift the first step would hit.

Cite file:line throughout. No code edits. Block-for-review when done (hermes kanban block).
