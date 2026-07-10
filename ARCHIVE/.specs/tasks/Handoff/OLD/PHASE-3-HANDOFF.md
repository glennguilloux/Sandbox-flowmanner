# Phase 3 — Canvas v1 (Multi-Tile Surface) — Handoff

**Status:** Frontend complete ✅ | Backend docs-only ✅ | Build verified ✅ | Tests pass ✅
**Date:** 2026-07-05
**Commits:** Frontend `f660636`, Backend `235f6968`
**Spec:** `.specs/tasks/draft/phase-3-canvas-v1.md`

---

## What was done

### Frontend (committed to `/home/glenn/FlowmannerV2-frontend/`)

| File | Action | Details |
|------|--------|---------|
| `src/lib/chat-types.ts` | Modified | Added `TileKind` (7 kinds), `TileState` (live/idle/error), `CanvasTile` interface, `MAX_TILES = 6` |
| `src/stores/chat-store.ts` | Modified | Added `canvasTiles[]` slice with CRUD actions, localStorage per-thread persistence, `recomputeLayouts()`, `createDefaultChatTile()`. Updated `selectThread`/`createThread` to init tiles. |
| `src/components/chat/Canvas.tsx` | **Created** | Multi-tile canvas: `@dnd-kit/core` + `@dnd-kit/sortable`, `SortableTile` wrapper, `TileContent` router, `AddTileButton` dropdown, DragOverlay |
| `src/components/chat/CanvasTileHeader.tsx` | **Created** | Tile header: drag handle, kind icon, title, StateDot, minimize, remove |
| `src/components/chat/AgentTraceTile.tsx` | **Created** | Expandable agent step tree from `message.steps[]` |
| `src/components/chat/ChatLayout.tsx` | Modified | Desktop center column now renders `<Canvas />` instead of `<SSEChat />`. Mobile unchanged. |
| `src/lib/slash-commands.ts` | Modified | `/sandbox` → opens code-sandbox tile, `/trace` → agent-trace tile, `/close` → removes tile, `/browse` → Phase 4 stub |
| `src/components/chat/Canvas.test.tsx` | **Created** | 16 tests: tile CRUD, layout recomputation, limits, reorder, focus |

### Backend (docs only)

| File | Action | Details |
|------|--------|---------|
| `docs/CANVAS-DECISION.md` | **Created** | One-paragraph ADR: `@dnd-kit` + custom flex, why not `react-grid-layout`, fallback to `@xyflow/react` |

---

## Architecture decisions made

1. **`@dnd-kit` + custom flex layout** over `react-grid-layout`. Already installed, no new dependencies. Documented in `docs/CANVAS-DECISION.md`.

2. **Tile layout uses flex-basis percentages**, not fixed pixel widths. `recomputeLayouts()` distributes width equally: `Math.floor(100 / count)` per tile, last tile gets remainder. This ensures responsive behavior without media queries.

3. **Chat tile is pinned** (`isPinned: true`). Cannot be removed or dragged. Always first in the tile array. Other tiles can be added/removed/reordered freely.

4. **localStorage per-thread persistence** for tile state. Key: `flowmanner-canvas-tiles:<threadId>`. On `selectThread`, loads saved tiles or creates default chat tile. On any tile CRUD action, saves to localStorage. No backend changes needed for Phase 3.

5. **SSEChat renders inside the chat tile** without modification. Key finding from 3.3 investigation: SSEChat has no `createPortal` usage, no DOM-position-dependent refs, and its key only changes on thread switch (not during streaming). The `IdleOverlay` moved inside the chat tile.

6. **Mobile bypasses the canvas entirely.** Mobile renders `SSEChat` directly (same as pre-Phase 3). Canvas is a desktop-first feature. Mobile multi-tile is a future concern.

7. **Tile content routing by kind.** `TileContent` component switches on `tile.kind`: chat → `SSEChat` + `IdleOverlay`, code-sandbox → `CodeSandboxPanel`, agent-trace → `AgentTraceTile`, stubs → "coming soon" placeholder.

8. **Slash commands use `useChatStore.getState()`** directly (Zustand). This works because Zustand's `getState()` is synchronous and doesn't require React context. The slash command registry pattern doesn't support dependency injection, so this tight coupling is acceptable.

---

## What was NOT done (deferred to Phase 3b+)

| Item | Phase | Notes |
|------|-------|-------|
| Tile resize (CSS resize + layout coordination) | 3b | `resize: horizontal` fights with flex-basis. Need ResizeObserver + `updateCanvasTileLayout` wiring. |
| `onBranchFromMessage` through Canvas props | 3b | Currently a no-op TODO in Canvas.tsx. Need to thread the prop from ChatLayout through Canvas → TileContent → SSEChat. |
| `@xyflow/react` flow visualization in AgentTraceTile | 3b+ | Current tree is sufficient for v1. `@xyflow` is the fallback for complex step graphs. |
| Mobile canvas | 4+ | Mobile still renders SSEChat directly. |
| Backend `canvas_tiles` table + CRUD endpoints | 5+ | localStorage only for now. Prototype has the schema in `db/schema.ts:143-170`. |
| `canvas_update` SSE event handling | 3b | Backend-driven tile orchestration (open_tile from SSE). |
| `permission_request` SSE event handling | 3b | HITL interrupt integration with PermissionCard. |
| Lazy-render inactive tiles | 3b | Currently `isMinimized` hides content but component stays mounted. True lazy rendering needs `React.lazy` + `Suspense`. |

---

## Key files for context

| File | Why it matters |
|------|---------------|
| `src/stores/chat-store.ts` | `canvasTiles[]` slice — the source of truth for all tile state |
| `src/components/chat/Canvas.tsx` | The main canvas surface — renders all tiles, handles drag-and-drop |
| `src/components/chat/ChatLayout.tsx` | The layout shell — Canvas replaces SSEChat on desktop |
| `src/lib/chat-types.ts` | `CanvasTile`, `TileKind`, `TileState`, `MAX_TILES` |
| `src/lib/slash-commands.ts` | `/sandbox`, `/trace`, `/close`, `/browse` commands |
| `docs/CANVAS-DECISION.md` | ADR documenting the layout architecture decision |
| `.sisyphus/src/components/Canvas.tsx` | Prototype Canvas (conditional stack) — design reference |
| `.sisyphus/src/components/SandboxTile.tsx` | Prototype tab-switcher template for code/browser tiles |
| `.sisyphus/src/lib/types.ts` | Prototype `TileKind` enum, `CanvasTile` type |

---

## Verification steps for next agent

```bash
# 1. Frontend build
cd /home/glenn/FlowmannerV2-frontend
pnpm build
# Expected: Build succeeded

# 2. Frontend tests
npx vitest run src/components/chat/Canvas.test.tsx --reporter=verbose
# Expected: 16 passed

# 3. Backend (no code changes — docs only)
cd /opt/flowmanner
git status
# Expected: 1 unpushed commit (Canvas ADR)

# 4. Push backend ADR commit
git push origin main

# 5. Manual verification
# - Open chat on desktop
# - Verify default full-width chat tile renders SSEChat correctly
# - Click "Add tile" → select "Code Sandbox" → tile appears to the right
# - Click "Add tile" → select "Agent Trace" → tile appears
# - Drag tiles to reorder (drag handle on non-pinned tiles)
# - Click minimize on a tile → content hides, header stays
# - Click remove on a non-pinned tile → tile removed, remaining tiles expand
# - Type /sandbox python → code-sandbox tile opens
# - Type /trace → agent-trace tile opens
# - Type /close code-sandbox → tile removed
# - Type /browse → "coming in Phase 4" message
# - Refresh page → tiles persist (localStorage)
# - Switch thread → tiles reset to default chat tile
```

---

## Gotchas

- **Frontend has 54 modified files and 7 untracked files** from prior work. Only the 8 Phase 3 files listed above were committed in this phase. The rest are from Phase 0/1/2 and other features.
- **Backend has 1 unpushed commit** (Canvas ADR). Push with `git push origin main`.
- **`recomputeLayouts` uses `Math.floor`** which means for 3 tiles: 33%, 33%, 34%. The last tile gets the remainder. This is intentional — exact 100% total.
- **`addCanvasTile` returns empty string on failure** (max tiles reached or duplicate kind). Slash commands check `if (id)` which treats `""` as falsy — this is correct.
- **No resize test in Canvas.test.tsx** — resize was deferred to Phase 3b. The spec said "covers tile add/remove/resize" but only add/remove/reorder/focus are tested. Add a resize test when resize is implemented.
- **`CodeSandboxPanel` is rendered inside a tile** — it was originally a right sidebar panel. Verify it renders correctly in a constrained tile container (smaller width, different overflow behavior).
