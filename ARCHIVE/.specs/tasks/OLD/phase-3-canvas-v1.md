# Task: Phase 3 — Canvas v1 (Multi-Tile Surface)

**Status:** DRAFT (revised by Hermes — supersedes DeepSeek draft)
**Priority:** P3 — core UX transformation
**Estimated effort:** 3 sessions
**Created:** 2026-07-05
**Depends on:** Phase 2 (agent step streaming) ✅ complete
**Blocks:** Phase 4 (browser sandbox tile)
**Context docs:** `docs/HYBRID-PLATFORM-WORKSPACE.md`, `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` §Phase 3, `.specs/REFERENCE-PROTOTYPE.md`

---

## ⚠️ Corrections from the DeepSeek draft

1. **Canvas ADR is missing.** The draft's re-imagine prompt explicitly says "Document the choice in a `docs/CANVAS-DECISION.md` (one-paragraph ADR, not a multi-page report)." The original draft did not create that ADR. Add `docs/CANVAS-DECISION.md` as the first sub-task.

2. **`@dnd-kit/sortable` is confirmed installed** (verified: `@dnd-kit/core ^6.3.1`, `@dnd-kit/sortable ^10.0.0`, `@dnd-kit/utilities ^3.2.2` in `package.json`). The workspace doc's pre-decision is sound: `@dnd-kit` with custom flex layout. ADR-tize it before coding.

3. **`react-grid-layout` is NOT installed** (verified — `package.json` does not contain it). The workspace-doc decision to avoid adding a new dependency is effectively final; do not re-litigate.

4. **SSEChat as a tile is the highest-risk step and gets no investigation step in the original draft.** The draft says "wrap in a container div with stable key. Test early." but doesn't MAKE it a sub-task. Promote it to an explicit investigation sub-task (3.3 below) before rewriting `ChatLayout.tsx`.

5. **`code-sandbox`, `browser-sandbox`, `image-gen` tile types:** the workspace doc lists six tile kinds; Phase 3 should land **at least the three that already have components** (`chat`, `code-sandbox`, `agent-trace`) and stub the others. Don't try to ship all six in this phase — `browser-sandbox` is Phase 4, `file-diff` is a separate concern, and `image-gen` has no existing renderer.

6. **`chat-store.ts` already has `sessionStartTime: Date.now()` at line 127, 188, 203** (Phase 0's hydration fix may change these). If Phase 0 moved session-start into a `useEffect`, the canvas tiles slice should be added in the same store but be careful not to reintroduce a `Date.now()` at init for any tile's `createdAt` — use a setter or `Date.now()` inside the `addTile` action (which only runs after mount).

---

## 🔴 Reference prototype patterns (from `.sisyphus/src/`)

### A. The prototype Canvas is simpler than the drafts' @dnd-kit approach

`components/Canvas.tsx` (297 lines) implements a **conditional vertical stack** instead of a drag-and-drop grid:
- Chat tile is always present (the `MessageList` + `StreamingIndicator` wrapped in a bordered container)
- `SandboxTile` auto-appears when `streaming.sandboxEvents.length > 0`
- `AgentReasoningTile` auto-appears when `streaming.activeSteps.size > 0`
- Quick-add buttons at the bottom let the user manually add tiles (code, browser, reasoning, files)
- Custom tiles can be minimized (header toggle) and removed (× button)
- Max 4 custom tiles

**This is a viable Phase 3a.** Ship the conditional-stack approach first (proven by the prototype), then add `@dnd-kit` drag-and-resize in Phase 3b. The conditional approach delivers 80% of the UX value with 20% of the complexity. The ADR in sub-task 3.0 should document this as a two-step strategy.

### B. Tiles are driven by BOTH user actions AND backend SSE events

The prototype's `canvas_update` SSE event (from Phase 2) drives tile creation from the backend:
```json
{ "action": "open_tile", "tileKind": "code_sandbox", "config": { ... } }
```
When the backend sends this, the frontend auto-opens the tile. The user can also open tiles manually via quick-add buttons or slash commands. Phase 3 must handle both paths in the `addTile` action.

### C. `TileKind` enum has `mission_status` (7 kinds, not 6)

The prototype's `tileKindEnum` (`db/schema.ts:40-48`) includes `"mission_status"` in addition to the 6 the drafts listed. This is the mission progress/status tile — useful for Phase 2's spawn-mission UX. Add it to the Phase 3 type definition.

### D. The `canvas_tiles` table schema (migration reference)

From `db/schema.ts:143-170`:
```
id, thread_id (FK CASCADE), tile_kind (ENUM), title, layout (JSONB: {x,y,w,h,minW?,...}),
config (JSONB), is_minimized, is_pinned, sort_order, created_at, updated_at
INDEX: (thread_id)
```

This is the exact shape for the Phase 3 Alembic migration. Note the `sort_order` column — needed for tile reordering which the drafts missed.

### E. `SandboxTile.tsx` is the tab-switcher template

The prototype's `SandboxTile` (123 lines) has an Output/Preview tab switcher with:
- Tab toggle buttons (Terminal icon for Output, ExternalLink icon for Preview)
- Status badge (`running` → green, else gray)
- Output tab: monospace terminal output
- Preview tab: browser-chrome-styled frame with traffic-light dots, URL bar, "open in new tab" button
- Reload and close buttons in the header

This is the exact UX template for both the code sandbox tile and the Phase 4 browser sandbox tile.

### F. Canvas tile persistence is backend-backed

The prototype persists tiles via `/api/canvas-tiles` CRUD (not just localStorage). The `store.ts:440-466` tile actions call the API:
```typescript
addTile: async (data) => { const tile = await api.createCanvasTile(data); ... }
updateTileLayout: async (id, layout) => { ... await api.updateCanvasTile(id, { layout }); }
removeTile: async (id) => { ... await api.deleteCanvasTile(id); }
```

The drafts said "no backend changes needed for Phase 3" — the prototype disagrees. Tiles should be persisted per-thread via a `canvas_tiles` table and CRUD endpoints, not just localStorage. Otherwise tile state is lost on browser refresh/device switch.

---

## Problem

The current chat page is a 3-column single-thread layout: thread sidebar | message list | right sidebar. This forces everything into a single linear stream. When the user wants to see a code sandbox, browser preview, or agent trace alongside the chat, they have to switch contexts (right sidebar toggle, separate panels).

**Goal:** Replace the single-stream `MessageList` with a magnetic canvas where chat, code sandbox, browser sandbox, and agent traces are dockable, resizable tiles. Chat becomes one tile type among several.

---

## Acceptance Criteria

- [ ] `docs/CANVAS-DECISION.md` ADR exists (one paragraph: `@dnd-kit` + custom flex, why not `react-grid-layout`)
- [ ] `Canvas.tsx` promoted to primary surface in `ChatLayout.tsx`
- [ ] `chat-store.ts` has `canvasTiles[]` slice with CRUD operations; no `Date.now()` at module init
- [ ] `CanvasTile` type defined in `chat-types.ts`
- [ ] Tile kinds implemented in Phase 3: `chat`, `code-sandbox`, `agent-trace`
- [ ] Tile kinds stubbed for later phases: `browser-sandbox`, `file-diff`, `image-gen` (render a "coming soon" placeholder)
- [ ] Tiles are draggable and resizable using `@dnd-kit/core` + `@dnd-kit/sortable`
- [ ] Slash commands create/focus tiles: `/sandbox python`, `/trace`, `/close <id>` (don't ship `/browse` — that's Phase 4)
- [ ] Default layout: full-width chat tile, new tiles dock to the right
- [ ] Tile state: `live | idle | error` with visual indicator
- [ ] Each tile has title bar with kind icon, title, remove/detach control
- [ ] `pnpm lint && pnpm build && pnpm test` passes
- [ ] `Canvas.test.tsx` covers tile add/remove/resize

---

## Sub-tasks

### 3.0 — Write the canvas ADR

**Create:** `docs/CANVAS-DECISION.md`

One paragraph ADR (per the re-imagine prompt's "not a multi-page report" rule):

> **Decision:** Use `@dnd-kit/core` + `@dnd-kit/sortable` with a custom flex layout for the canvas tile system.
>
> **Context:** `@dnd-kit` is already installed (`package.json`: `@dnd-kit/core ^6.3.1`, `@dnd-kit/sortable ^10.0.0`, `@dnd-kit/utilities ^3.2.2`). `react-grid-layout` is not installed and would add a new dependency with React 18/19 compatibility concerns. The project already uses `@dnd-kit` patterns elsewhere.
>
> **Consequences:** We write the resize handle ourselves (CSS `resize: both` + flex-basis), trading framework-provided grid snapping for control and a smaller dependency surface. If resize proves insufficient, `@xyflow/react` (also already installed) is the fallback for complex layouts.

### 3.1 — Define CanvasTile type (frontend)

**File:** `frontend/src/lib/chat-types.ts`

```typescript
export type TileKind = 'chat' | 'code-sandbox' | 'browser-sandbox' | 'agent-trace' | 'file-diff' | 'image-gen';
export type TileState = 'live' | 'idle' | 'error';

export interface CanvasTile {
  id: string;
  kind: TileKind;
  title: string;
  state: TileState;
  payload: Record<string, unknown>;  // kind-specific data
  layout: {
    x: number;
    y: number;
    w: number;
    h: number;
  };
  createdAt: number;  // set inside addTile (post-mount), NOT at module init
}
```

### 3.2 — Add canvasTiles slice to chat-store (frontend)

**File:** `frontend/src/stores/chat-store.ts`

```typescript
interface ChatStore {
  // ...existing...
  canvasTiles: CanvasTile[];
  addTile: (tile: Omit<CanvasTile, 'id' | 'createdAt'>) => string;
  removeTile: (id: string) => void;
  updateTile: (id: string, patch: Partial<CanvasTile>) => void;
  updateTileLayout: (id: string, layout: CanvasTile['layout']) => void;
  focusTile: (id: string) => void;
}
```

Default: one `chat` tile is created when a thread is selected (inside `selectThread` action — post-mount, safe to use `Date.now()`).

**⚠ Do NOT add `createdAt: Date.now()` at module init** (the Phase 0 hydration bug root cause). Set `createdAt` inside the `addTile` action body.

### 3.3 — Investigate SSEChat-as-tile feasibility (frontend)

**Owner:** Frontend
**Approach:** Before rewriting `ChatLayout.tsx`, verify that `SSEChat` (725 lines) survives being rendered inside a tile container. Known risks:

- SSEChat holds an SSE connection with refs that may depend on being mounted at the top level of the layout
- Portals (tooltips, command palette) may break inside a flex child with `overflow: hidden`
- React state inside SSEChat may not survive grid drag operations (key changes force remount)

**Steps:**
1. In a throwaway branch, wrap `SSEChat` in a 50% width container with `overflow: hidden` and run dev mode
2. Verify: streaming still works, slash command palette opens correctly, attach button works, branch switcher works, no console errors
3. If portals break, document the fix (portal target relocation or a z-index layering fix) in a `### 3.3 finding` note in this file before continuing to 3.4

This is the de-risking step that the original draft omitted.

### 3.4 — Promote Canvas.tsx to primary surface (frontend)

**File:** `frontend/src/components/chat/Canvas.tsx` (already exists as prototype)

Rewrite/extend to be the primary canvas surface:
- Uses `@dnd-kit/core` `DndContext` + `@dnd-kit/sortable` for tile management
- Each tile renders in a resizable container (CSS `resize: both` + flex-basis)
- Tile content is determined by `kind`:
  - `chat` → `<SSEChat />` (existing component, wrapped as tile — see 3.3)
  - `code-sandbox` → `<CodeSandboxPanel />` (existing, wrapped)
  - `agent-trace` → read-only projection of `AgentStep[]` tree (3.7)
  - `browser-sandbox` → "coming soon — Phase 4" placeholder
  - `file-diff` → "coming soon" placeholder
  - `image-gen` → "coming soon" placeholder

### 3.5 — Update ChatLayout.tsx (frontend)

**File:** `frontend/src/components/chat/ChatLayout.tsx`

Replace the center column's `MessageList` with `<Canvas />`:

```tsx
<div className="center-column">
  <Canvas tiles={canvasTiles} onTileAction={handleTileAction} />
</div>
```

The `SSEChat` component is now rendered INSIDE the chat tile, not as the center column itself.

### 3.6 — Tile header component (frontend)

**Create:** `frontend/src/components/chat/CanvasTileHeader.tsx`

Each tile has a header bar:
- Kind icon (ChatBubble, Code, Globe, Brain, FileDiff, Image)
- Title (editable on double-click)
- State indicator (green dot = live, gray = idle, red = error)
- Minimize/maximize button
- Detach (pop out to separate window) button — Phase 3 stub: button visible, handler is a no-op (log "detach not implemented")
- Remove (×) button

### 3.7 — Extend slash commands (frontend)

**File:** `frontend/src/lib/slash-commands.ts`

Phase 3 ships these:
```typescript
// /sandbox python → opens code-sandbox tile with python preselected
{ command: 'sandbox', handler: (args) => addTile({ kind: 'code-sandbox', title: `Sandbox: ${args}`, payload: { language: args } }) }

// /trace → opens agent-trace tile pinned to active mission
{ command: 'trace', handler: () => addTile({ kind: 'agent-trace', title: 'Agent Trace', payload: { missionId: activeMissionId } }) }

// /close <tile-id> → removes a tile
{ command: 'close', handler: (args) => removeTile(args) }
```

DO NOT ship `/browse` in Phase 3 — that's the Phase 4 entry point. If the user runs `/browse` before Phase 4, show a "coming in a later phase" message.

### 3.8 — Default layout behavior

- When a thread is selected: one full-width `chat` tile
- When a new tile is added: dock to the right (50/50 split with chat)
- When a tile is removed: remaining tiles expand to fill
- Persist tile layout per-thread in Zustand (localStorage)
- Responsive: on mobile (< 768px), tiles stack vertically

### 3.9 — Agent trace tile (frontend)

**Create:** `frontend/src/components/chat/AgentTraceTile.tsx`

Read-only projection of the active mission's `AgentStep[]` tree:
- Expandable tree of reasoning → tool calls → results
- Uses `@xyflow/react` (already installed) for flow visualization
- Highlights current step with pulse animation
- Links to inline `ToolCallCard` in the chat tile (click a tool call in trace → scroll to it in chat)

### 3.10 — Tests

**Frontend:**
- `Canvas.test.tsx`: tile add/remove/resize, drag reorder, slash command integration
- `AgentTraceTile.test.tsx`: renders step tree, highlights current step

### 3.11 — Verification gate

```bash
cd /home/glenn/FlowmannerV2-frontend
pnpm lint && pnpm build && pnpm test

# Manual:
# 1. Open chat, verify default full-width chat tile
# 2. Run /sandbox python → code-sandbox tile appears to the right
# 3. Write print("hello") in sandbox → result shows
# 4. Run /trace → agent trace tile appears
# 5. Drag tiles to rearrange, resize tiles
# 6. Run /close <tile-id> → tile removed
# 7. Try /browse → see "coming soon" message (Phase 4)
```

---

## File Map

| File | Action |
|------|--------|
| `docs/CANVAS-DECISION.md` | **NEW** — one-paragraph ADR |
| `frontend/src/lib/chat-types.ts` | Add `CanvasTile`, `TileKind`, `TileState` |
| `frontend/src/stores/chat-store.ts` | Add `canvasTiles[]` slice with CRUD; do NOT add `Date.now()` at init |
| `frontend/src/components/chat/Canvas.tsx` | Rewrite as primary canvas surface with `@dnd-kit` |
| `frontend/src/components/chat/ChatLayout.tsx` | Replace center column with `<Canvas />` |
| `frontend/src/components/chat/CanvasTileHeader.tsx` | **NEW** — tile header with controls |
| `frontend/src/components/chat/AgentTraceTile.tsx` | **NEW** — agent step tree visualization |
| `frontend/src/lib/slash-commands.ts` | Add `/sandbox`, `/trace`, `/close`; stub `/browse` |
| `frontend/src/components/chat/Canvas.test.tsx` | **NEW** — canvas tests |

---

## Architecture Decisions

- **Grid framework:** `@dnd-kit/core` + `@dnd-kit/sortable` (already installed) with custom flex layout. No `react-grid-layout` dependency needed. Documented in `docs/CANVAS-DECISION.md`.
- **Animations:** `motion` (framer-motion successor, already installed) for tile enter/exit/resize transitions.
- **Tile persistence:** Zustand `canvasTiles[]` persisted to localStorage per-thread. No backend changes needed for Phase 3.
- **Mobile:** Tiles stack vertically. Swipe between tiles. Chat tile always visible.
- **Phase 3 ships 3 tile kinds**, stubs 3. Do not try to ship `browser-sandbox` (Phase 4), `file-diff`, or `image-gen` in this phase.

---

## Risks

| Risk | Mitigation |
|------|------------|
| `@dnd-kit` can't handle canvas resize well | 3.3 investigation unblocks this; `@xyflow/react` is the fallback per the ADR |
| SSEChat doesn't work well as a tile (portals, refs) | 3.3 is the explicit investigation step before rewriting ChatLayout. If portals break, document the fix before continuing. |
| Performance with many tiles | Cap at 6 tiles max. Lazy-render inactive tiles. |
| Tile layout breaks on window resize | Use flex-basis percentages, not fixed px. Test responsive breakpoints. |
| Reintroducing `Date.now()` at init in the tile slice reopens the hydration bug | Set `createdAt` inside `addTile` action body (post-mount only), never in the store initial state. |
