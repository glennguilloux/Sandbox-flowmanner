# B3 — Mission Builder × Chat: UX SEAM (read-only brainstorm)

You are injected as a UX ARCHITECT persona. Deliverable = a UX brief on the seam
between the canvas and the chat. Read-only: do NOT edit any repo file. Write your
deliverable to the stable path
`/opt/flowmanner/.sisyphus/brainstorm/mission-builder-chat/B3-UX.md`.

## The problem
Building a mission (visual node graph) and talking to the agent (chat) are two
separate surfaces with no smooth handoff. Glenn is unhappy with "the whole thing" and
wants a way forward. Focus ONLY on the user-experience seam: how does a person move
between the canvas and the conversation without losing context or mental model?

## Ground yourself in REAL source (cite file:line)
Frontend root (symlink): `/home/glenn/f`
- Builder UI: `/home/glenn/f/src/components/mission-builder/FlowEditor.tsx`,
  `NodePalette.tsx`, `PropertiesPanel.tsx`, `TemplatePicker.tsx`, `ProgramRunHistory.tsx`,
  `CompareRuns.tsx`, `MissionProgramView.tsx`
- Chat UI: `/home/glenn/f/src/components/chat/ChatLayout.tsx`, `SSEChat.tsx`,
  `ChatHeader.tsx`, `ThreadSidebar.tsx`, `ChatRightSidebar.tsx`
- Chat page: `/home/glenn/f/src/app/[locale]/(dashboard)/chat/page-client.tsx`
- Current bridge tile: `/home/glenn/f/src/components/chat/tiles/MissionStatusTile.tsx`
- Nav: where do Builder vs Chat live in the app? Check
  `/home/glenn/f/src/components/layout/floating-nav.tsx` and the route tree under
  `/home/glenn/f/src/app/[locale]/`.

Open these and cite file:line for the navigation model, the canvas interaction model,
and the chat interaction model.

## Your deliverable (write to .../B3-UX.md)
A UX brief, max ~600 words:
1. **Current seam audit** — how a user gets from a built mission to a chat session
   today (if at all). Cite file:line for the nav + the only existing bridge tile.
2. **Context-loss points** — where the user loses state/meaning moving builder↔chat.
3. **Proposed seam** — 3 concrete UX patterns (e.g. "send graph to chat as a live
   agent", "chat drafts a node subgraph inline", "shared context rail"). Pick the one
   with the best effort/love ratio. Describe the screen flow in words.
4. **First UX slice** — the smallest change that makes the seam feel real, mapped to
   the screens/files it touches.

Cite file:line throughout. No code edits. Block-for-review when done (hermes kanban block).
