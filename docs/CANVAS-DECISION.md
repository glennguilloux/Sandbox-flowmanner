# ADR: Canvas Tile System Architecture

**Status:** Accepted
**Date:** 2026-07-05
**Decision makers:** Phase 3 planning

## Context

The chat interface needs to evolve from a single-stream linear layout into a multi-tile canvas where chat, code sandbox, browser sandbox, and agent traces coexist as dockable, resizable tiles. We need a layout strategy that supports drag-and-drop reordering, responsive resizing, and future extensibility (6 tile kinds planned).

## Decision

Use `@dnd-kit/core` + `@dnd-kit/sortable` (already installed: `@dnd-kit/core ^6.3.1`, `@dnd-kit/sortable ^10.0.0`) with a custom flex layout. `react-grid-layout` is **not** installed and would add a new dependency with React 18/19 compatibility concerns — it is explicitly excluded. Resize is handled via CSS `resize: both` combined with `flex-basis` percentages, trading framework-provided grid snapping for full control and a smaller dependency surface. Tile layout is persisted per-thread in Zustand (localStorage), not backend — this keeps Phase 3 frontend-only. The chat tile is always present and excluded from removal; new tiles dock to the right in a 50/50 split. Maximum 6 tiles, lazy-render inactive tiles. If `@dnd-kit` proves insufficient for complex layouts, `@xyflow/react` (already installed) is the fallback.

## Consequences

- No new dependencies required for Phase 3
- Resize handles are custom CSS (`resize: both` + `overflow: auto` on tile content)
- `SSEChat` (714 lines) renders inside the chat tile without modification — it has no portal usage, no DOM-position-dependent refs, and its key only changes on thread switch (not during streaming)
- Tile state is client-only per-thread (localStorage) — cross-device sync deferred to Phase 5+ with backend persistence
- `@xyflow/react` is used specifically for the agent trace tile's step-tree visualization, not for general layout
