# B3-UX — Mission Builder × Chat: the SEAM (UX brief)

Persona: UX architect. Read-only. Deliverable is a UX brief on the builder↔chat
seam, grounded in real source (file:line cited below). No code edits.

---

## 1. Current seam audit — how a built mission reaches chat today

**Navigation model.** Builder and Chat live in two unrelated branches of the nav.
Chat is a top-level group (`src/components/layout/nav-config.ts:133-136`,
`nav.chat → /chat`). Missions is a separate group whose items are
`/missions`, `/missions/builder`, `/missions` (`nav-config.ts:142-150`). There
is no nav item that points *from* one surface *into* the other — they are
siblings, never linked.

**Entering the builder.** From the Missions landing page the only path in is a
"New Mission" / "Create Mission" button that pushes a *fresh* builder route with
no mission id: `src/app/[locale]/(dashboard)/missions/page-client.tsx:111-117`
and `:148-150` (`router.push('/${locale}/missions/builder')`). The builder page
itself (`src/app/[locale]/(dashboard)/missions/builder/page-client.tsx:5,67`)
mounts `<FlowEditor initialFlow={...} />` with no inbound chat context.

**The only bridge today.** Inside Chat, the canvas can show a `Mission Status`
tile (`src/components/chat/Canvas.tsx:28,66-70,188-189`). It is added from the
"Add tile" menu (`Canvas.tsx:226`) and rendered by
`src/components/chat/tiles/MissionStatusTile.tsx`. That tile does **one thing**:
poll `/api/v2/missions/{missionId}/status` every 5s and show progress
(`MissionStatusTile.tsx:54-80`). It requires a `missionId` already in its
payload (`MissionStatusTile.tsx:49,55-58`) — there is no way to *pick* a mission
from the builder and drop it here. The tile is inert: no link back to the
builder, no "open in builder", no chat context.

**Net result:** a user who built a mission cannot, from the builder, start a
chat about it; and a user in chat cannot, from the status tile, jump back into
the graph. The two surfaces share only an opaque polling widget.

---

## 2. Context-loss points (where meaning leaks)

- **No shared identity.** Missions are addressed by `missionId`
  (`MissionStatusTile.tsx:6-8`); the builder loads via `initialFlow`
  (`FlowEditor.tsx:475-477`). Neither surface knows the other's current object,
  so you cannot "carry" a mission across.
- **Loss of intent on handoff.** The builder has rich *meaning* — node types,
  connection rules (`FlowEditor.tsx:259-400` validate start/end/reachability),
  groups, edge labels. The chat side reduces that to a progress bar + token
  count (`MissionStatusTile.tsx:99-131`). Going builder→chat throws away the
  graph's semantics.
- **No conversational thread per mission.** Chat threads are generic
  (`chat-store.ts` `activeThreadId`; `page-client.tsx:58-61` `selectThread`).
  There is no concept of "this thread is about mission X", so the agent has no
  grounding when you ask "why did node Y fail?".
- **Dead-end tile.** `MissionStatusTile` has no affordance to open the builder,
  re-run, or ask. It is a read-only monitor floating in a canvas of otherwise
  interactive tiles.

---

## 3. Proposed seam — 3 patterns, pick the best effort/love ratio

**(a) "Send graph to chat" — promote the built mission into a grounding object
for a thread.** From the builder, a button "Discuss / Run with agent" creates (or
opens) a chat thread that carries the `missionId` + a compact graph summary as
system context. The `MissionStatusTile` becomes a live, clickable link back into
the builder. *Effort: medium. Love: high* — directly answers "I built this, now
talk to the agent about it."

**(b) "Chat drafts a subgraph inline" — NL → node draft inside the builder.**
Highest effort (needs graph-gen + validation replay), lowest certainty it lands.
*Defer.*

**(c) "Shared context rail" — a persistent panel showing the active mission
across both surfaces.** Heavier (new persistent chrome), more architecture than
UX win for v1.

**Pick: (a).** It is the smallest mental-model-preserving move: the builder
already produces a saveable object (`FlowEditor.missionToBlueprintPayload`,
`FlowEditor.tsx:125-163`), and chat already has a tile slot + thread model. The
seam becomes *bidirectional* with one forward action and one backward link.

**Screen flow (pattern a):** In `FlowEditor`, add a header action "Discuss with
agent" → calls an endpoint that mints/returns a `threadId` bound to the saved
`missionId`, then navigates to `/chat?missionId=...&thread=...`. Chat page reads
the query, pre-seeds the thread's system context with the graph summary, and the
"Add tile → Mission Status" step is replaced/extended so the tile is created
with that `missionId` automatically and is *clickable* back to
`/missions/builder?missionId=...`.

---

## 4. First UX slice — smallest change that makes the seam real

Make the `MissionStatusTile` a **two-way bridge** and wire a one-click
"Discuss" action. Concretely, mapped to files:

1. `MissionStatusTile.tsx` — wrap the card in a link/button to
   `/missions/builder?missionId=<id>` (backward seam) and add a "Discuss" button
   that opens `/chat?missionId=<id>` (forward seam). No new endpoint needed; the
   chat page already reads `activeThreadId` and the tile already holds the id.
2. `Canvas.tsx` `AddTileButton` (`:216-227`) — when adding `mission_status`,
   pre-fill `payload.missionId` from the URL `?missionId=` if present, so the
   tile is useful on arrival instead of showing "No missionId" error
   (`MissionStatusTile.tsx:55-58`).
3. `chat/page-client.tsx` (`:11-98`) — if `?missionId=` is in the URL, auto-open
   the mission-status tile via `addCanvasTile('mission_status', ..., {missionId})`
   (`chat-store.ts:182` `addCanvasTile`).

This turns the inert monitor into a real seam with ~3 file touches, no backend
change, and immediately lets a user hop builder→chat→builder without losing which
mission they were on.

---

**Recommendation Glenn can act on:** ship the bidirectional MissionStatusTile
("Discuss" + click-to-builder) as the v1 seam; defer NL-graph-draft until the
thread↔mission identity exists.
