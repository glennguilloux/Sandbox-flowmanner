# Hybrid Platform — Reference Prototype Catalog

**Location:** `.sisyphus/src/`
**Status:** Complete standalone Next.js + Drizzle prototype of the hybrid chat/tools/agents/sandbox platform
**Purpose:** The single source of truth for frontend patterns, SSE protocol, and database shapes. Every phase spec references this document.

---

## Why this matters

The `.sisyphus/src/` directory is **not** the production frontend (which lives at `/home/glenn/FlowmannerV2-frontend/`). It is a self-contained reference implementation — a design-exploration prototype that implements the exact target architecture with a mock backend. It runs, it compiles, and its patterns are battle-tested against the real constraints of the hybrid platform UX.

**Every phase spec should treat this prototype as the primary design reference.** The DeepSeek drafts invented patterns from scratch; the prototype already has working versions of those patterns. When a spec says "create component X", check whether the prototype already has it — if it does, adapt rather than reinvent.

---

## File inventory and phase mapping

### Core infrastructure

| File | Role | Informs phases |
|------|------|----------------|
| `lib/types.ts` | SSE event types, streaming state, canvas types, chat message extension — **the type contract for the entire platform** | 1, 2, 3 |
| `lib/store.ts` | Zustand store with SSE event handling, streaming state lifecycle, canvas tile CRUD — **the state management blueprint** | 1, 2, 3 |
| `lib/api.ts` | API client: thread CRUD, message CRUD, SSE stream connection, tool/canvas/sandbox fetchers — **the frontend↔backend contract** | 1, 2, 3, 4 |
| `lib/utils.ts` | `safeStringify`, `cn` class join helper | 1 |
| `db/schema.ts` | Complete Drizzle schema for 8 entities — **the migration reference for all backend Alembic migrations** | 1, 2, 3, 4, 5, 6 |
| `db/index.ts` | Postgres pool + Drizzle init pattern | — |

### Components

| File | Role | Informs phases |
|------|------|----------------|
| `components/Canvas.tsx` | Primary canvas surface: chat tile always present, dynamic tiles auto-appear from SSE events, quick-add buttons, tile min/remove — **the Phase 3 target UX** | 3 |
| `components/ChatLayout.tsx` | 3-column layout (threads / canvas / agent trace), mobile detection, keyboard shortcuts, zen mode — **the production ChatLayout upgrade target** | 0, 3 |
| `components/ChatInput.tsx` | Slash command picker, auto-resize textarea, send/stop toggle, keyboard hints — **already has `id`/`name` on the textarea** | 0 |
| `components/MessageList.tsx` | Message rendering with `AgentStepCard` inline — **the Phase 1 ToolCallCard template** | 1 |
| `components/AgentReasoningTile.tsx` | Auto-appearing reasoning tile, step status icons, reasoning chain visualization | 2, 3 |
| `components/SandboxTile.tsx` | Code sandbox tile with output/preview tab switcher, status badge, browser-chrome-styled preview — **the Phase 4 tile template** | 3, 4 |
| `components/AgentTracePanel.tsx` | Right sidebar: activity feed, tool call history, reasoning, files, branches, cost — collapsible sections | 2, 3 |
| `components/StreamingIndicator.tsx` | Live streaming display: cursor, active tool calls, active steps, citations, error, waiting state | 1, 2 |
| `components/ThreadSidebar.tsx` | Thread list with search, pin, archive, context menu — **existing pattern reference** | 0 |
| `components/TopBar.tsx` | Thread title, model picker dropdown, agent/team picker dropdown, run/stop, settings | 6 |

### API routes (mock backend — the SSE protocol specification)

| File | Role | Informs phases |
|------|------|----------------|
| `app/api/chat/stream/route.ts` | **THE SSE PROTOCOL SPECIFICATION** — mock stream showing every event type, correct ordering, payload shapes | 1, 2 |
| `app/api/tools/route.ts` | Tool discovery endpoint with workspace permission filtering | 1, 5 |
| `app/api/canvas-tiles/route.ts` + `[id]/route.ts` | Canvas tile CRUD | 3 |
| `app/api/threads/route.ts` + `[id]/route.ts` | Thread CRUD | 0 |
| `app/api/threads/[id]/messages/route.ts` | Message CRUD with steps | 1 |
| `app/api/sandboxes/route.ts` + `[id]/route.ts` | Sandbox CRUD | 4 |
| `app/api/agent-teams/route.ts` | Agent team CRUD | 2 |
| `app/api/branches/route.ts` | Branch CRUD | — |
| `app/api/health/route.ts` | Health check | 0 |

---

## 1. SSE Event Protocol (the critical contribution)

**Source:** `lib/types.ts:14-28`, `lib/store.ts:289-368`, `app/api/chat/stream/route.ts`

The prototype defines **14 event types**. The DeepSeek drafts only knew about 3 (`tool_call_start`, `tool_call_result`, `agent_step`). The full set:

```typescript
type SSEEventType =
  | "text_delta"              // Streaming token
  | "tool_call_start"          // Tool invocation begins
  | "tool_call_delta"          // Tool args streaming incrementally
  | "tool_call_result"         // Tool invocation completes
  | "agent_step_start"         // Agent reasoning/action step begins (PAIRED with _end)
  | "agent_step_end"           // Agent step completes (PAIRED with _start)
  | "reasoning_delta"          // Reasoning text streaming incrementally
  | "citation"                 // RAG citation
  | "permission_request"       // HITL approval needed
  | "canvas_update"            // Backend instructs frontend to open/modify a tile
  | "sandbox_event"            // Sandbox lifecycle event (creating → running → expired)
  | "handoff"                  // Agent-to-agent handoff
  | "error"                    // Stream error
  | "done";                    // Stream complete (carries messageId, tokenCount, cost)
```

### Event ordering (from the mock stream)

The mock at `chat/stream/route.ts` shows the canonical event sequence for a chat turn:

```
1. canvas_update     → { tools: [...], model }           (initial context)
2. tool_call_start   → { toolCallId, toolName, args }     (if tools needed)
3. tool_call_result  → { toolCallId, toolName, result }   (after execution)
4. agent_step_start  → { stepId, stepType, name }         (reasoning begins)
5. text_delta        → { content }                        (streamed in chunks)
6. agent_step_end    → { stepId, status }                 (reasoning complete)
7. canvas_update     → { action: "open_tile", tileKind }  (open tile if needed)
8. citation          → { sources: [...] }                 (RAG sources)
9. done              → { messageId, tokenCount, cost }    (stream end)
```

### Why paired `agent_step_start`/`agent_step_end` beats a single `agent_step`

The drafts proposed a single `agent_step` event. The prototype uses paired events because:
- **Streaming state uses a Map:** `activeSteps: Map<stepId, AgentStepEvent>` — `start` adds to the map, `end` removes from it. The frontend shows active steps with spinners in real-time.
- **No duplicates:** `finalizeStream()` runs on `done` and collapses the Maps into `message.steps[]`. A single-event approach would require deduplication logic.
- **Status transitions are explicit:** `start` → status `running`, `end` → status `completed` or `failed`. The frontend doesn't have to infer transitions.

### `canvas_update` — the missing orchestration layer

The drafts had no mechanism for the backend to tell the frontend "open a tile." The prototype's `canvas_update` event does exactly this:

```json
{
  "type": "canvas_update",
  "data": {
    "action": "open_tile",
    "tileKind": "code_sandbox",
    "config": { "language": "python", "code": "..." },
    "timestamp": 1234567890
  }
}
```

This means the **backend decides tile lifecycle**, not just the user via slash commands. When the LLM's response involves code execution, the backend sends `canvas_update` with `action: "open_tile"` and the frontend opens the tile automatically. This is the key UX innovation the drafts missed.

---

## 2. Streaming State Architecture

**Source:** `lib/types.ts:93-105`, `lib/store.ts:21-35`, `lib/store.ts:289-424`

```typescript
interface StreamingState {
  isStreaming: boolean;
  content: string;                                    // Accumulated text_delta
  reasoning: string;                                  // Accumulated reasoning_delta
  activeToolCalls: Map<string, ToolCallStart>;        // In-flight tool calls
  toolResults: Map<string, ToolCallResult>;           // Completed tool results
  activeSteps: Map<string, AgentStepEvent>;           // In-flight agent steps
  citations: { source: string; excerpt: string; score: number }[];
  pendingPermissions: PermissionRequest[];            // HITL queue
  sandboxEvents: { sandboxId: string; status: string; previewUrl?: string }[];
  error: string | null;
  messageId: string | null;                           // Set by 'done' event
}
```

### Lifecycle: `handleSSEEvent` → `finalizeStream`

1. **During streaming:** `handleSSEEvent(type, data)` mutates the `streaming` state. Tool calls go into Maps keyed by `toolCallId`. Steps go into Maps keyed by `stepId`. Text and reasoning are appended to strings.
2. **On `done`:** `finalizeStream()` takes the streaming state, builds an assistant `ChatMessage` with `steps[]` derived from `toolResults`, persists it, resets streaming state to initial.

This is the correct architecture: **streaming state is ephemeral (Maps for O(1) updates), message state is persisted (arrays for rendering)**. The drafts' "append to steps[] on every event" would create race conditions and duplicates.

---

## 3. Database Schema Reference (migration source of truth)

**Source:** `db/schema.ts` — complete Drizzle definitions. Map directly to SQLAlchemy models + Alembic migrations.

### `agent_steps` table (Phase 1 migration reference)

```
id              UUID PK
message_id      UUID FK → messages.id (CASCADE)
step_type       ENUM: tool | reasoning | handoff | sandbox | permission
status          ENUM: pending | running | completed | failed | awaiting_approval | cancelled
name            TEXT NOT NULL
display_name    TEXT
args            JSONB
result          JSONB
error           TEXT
agent_name      TEXT
capability_token TEXT
tool_call_id    TEXT
started_at      TIMESTAMPTZ
ended_at        TIMESTAMPTZ
created_at      TIMESTAMPTZ DEFAULT NOW()
INDEX: (message_id)
```

### `canvas_tiles` table (Phase 3 migration reference)

```
id          UUID PK
thread_id   UUID FK → threads.id (CASCADE)
tile_kind   ENUM: chat | code_sandbox | browser_sandbox | agent_reasoning | file_diff | image_gen | mission_status
title       TEXT
layout      JSONB: { x, y, w, h, minW?, minH?, maxW?, maxH? }
config      JSONB (kind-specific payload)
is_minimized BOOLEAN DEFAULT FALSE
is_pinned    BOOLEAN DEFAULT FALSE
sort_order   INTEGER DEFAULT 0
created_at   TIMESTAMPTZ DEFAULT NOW()
updated_at   TIMESTAMPTZ DEFAULT NOW()
INDEX: (thread_id)
```

### `tool_definitions` table (Phase 1 + 5 migration reference)

```
id                  UUID PK
name                TEXT UNIQUE NOT NULL
display_name        TEXT NOT NULL
description         TEXT
category            TEXT DEFAULT 'utility'
input_schema        JSONB
required_scopes     JSONB (string[])
rate_limit_per_min  INTEGER
requires_sandbox    BOOLEAN DEFAULT FALSE
requires_approval   BOOLEAN DEFAULT FALSE
is_enabled          BOOLEAN DEFAULT TRUE
created_at          TIMESTAMPTZ DEFAULT NOW()
```

### `workspace_tool_permissions` table (Phase 5 migration reference)

```
id            UUID PK
workspace_id  TEXT NOT NULL
tool_id       UUID FK → tool_definitions.id (CASCADE)
is_allowed    BOOLEAN DEFAULT TRUE
granted_by    TEXT
granted_at    TIMESTAMPTZ DEFAULT NOW()
INDEX: (workspace_id, tool_id)
```

### `sandboxes` table (Phase 4 migration reference)

```
id            UUID PK
sandbox_type  TEXT DEFAULT 'code'   -- "code" | "browser"
language      TEXT DEFAULT 'python'
thread_id     UUID FK → threads.id (SET NULL)
message_id    UUID FK → messages.id (SET NULL)
container_id  TEXT
preview_url   TEXT
preview_token TEXT
status        TEXT DEFAULT 'creating'  -- creating|running|stopped|expired
files         JSONB
expires_at    TIMESTAMPTZ
created_at    TIMESTAMPTZ DEFAULT NOW()
INDEX: (thread_id)
```

### `prompt_versions` table (Phase 6 migration reference)

```
id          UUID PK
name        TEXT NOT NULL
content     TEXT NOT NULL
version     INTEGER DEFAULT 1
is_active   BOOLEAN DEFAULT TRUE
created_at  TIMESTAMPTZ DEFAULT NOW()
INDEX: (name)
```

### `agent_teams` table (Phase 2 — agent teams)

```
id                  UUID PK
name                TEXT NOT NULL
description         TEXT
members             JSONB: [{ name, role, systemPrompt }]
protocol            TEXT DEFAULT 'sequential'  -- sequential|debate|swarm|escalation
max_turns           INTEGER DEFAULT 10
escalation_policy   JSONB
created_at          TIMESTAMPTZ DEFAULT NOW()
```

---

## 4. Component Templates

### ToolCallCard = AgentStepCard (`MessageList.tsx:268-346`)

The prototype's `AgentStepCard` is the exact `ToolCallCard` Phase 1 needs:
- Collapsible header with status icon (Check for completed, X for failed, animated pulse for running, static dot for pending)
- `stepType` prefix labels: "Tool:", "Reasoning:", "Handoff:", "Sandbox:"
- `displayName || name` for the title
- `agentName` shown on the right
- Expand/collapse chevron
- Expanded body: `result` as pretty JSON via `safeStringify`, `error` in red

### Canvas tile auto-appearance (`Canvas.tsx`)

The prototype canvas doesn't use `@dnd-kit` — it uses conditional rendering:
- Chat tile is always present
- `SandboxTile` appears when `streaming.sandboxEvents.length > 0`
- `AgentReasoningTile` appears when `streaming.activeSteps.size > 0`
- Quick-add buttons at the bottom let the user manually add tiles
- Custom tiles can be minimized and removed

**This is a viable Phase 3a** (ship conditional tiles first, add DnD in Phase 3b). The prototype proves the simpler approach works for the core UX. The phase spec should note this as an option.

### SandboxTile tab switcher (`SandboxTile.tsx`)

The code sandbox tile has an Output/Preview tab switcher — the exact UX the browser sandbox tile needs:
- Output tab: terminal-style monospace output
- Preview tab: browser-chrome-styled frame with traffic-light dots, URL bar, "open in new tab" button
- Status badge (running/stopped)
- Reload and close buttons

### AgentTracePanel (`AgentTracePanel.tsx`)

The right sidebar shows the agent observability surface:
- **Activity** section: live tool calls and steps from the streaming Maps
- **Tool Calls** section: historical tool calls from `message.steps[]`
- **Reasoning** section: `streaming.reasoning` text
- **Files Touched** section: sandbox events
- **Branches** section: placeholder for branching UI
- **Cost** section: token count rollup from messages

Each section is collapsible with a badge counter.

---

## 5. Slash Commands (`ChatInput.tsx:16-24`)

The prototype defines 7 slash commands:
```
/sandbox           → Open code sandbox
/sandbox python    → Python sandbox
/sandbox js        → JavaScript sandbox
/spawn mission     → Create autonomous mission
/team engineering  → Activate engineering team
/browser           → Open browser sandbox
/search            → Web search with RAG
```

The slash command picker has:
- Arrow-key navigation with selected index
- Tab/Enter to apply
- Escape to close
- Icon + command + description in each row

---

## How to use this document

When implementing a phase:
1. Find the relevant prototype files in the table above
2. Read them — they are short (the entire prototype is ~3,500 lines across 33 files)
3. Adapt the pattern to the production codebase (different paths, different dependencies, real backend)
4. The prototype's types and shapes are authoritative — match them unless there's a documented reason not to

**Do NOT copy prototype files verbatim into the production frontend.** The production frontend uses different dependencies (it has `@dnd-kit`, `motion`, `@xyflow/react`, `react-markdown`, `react-hook-form`, `zod` — the prototype uses none of these). Adapt the patterns, use the prototype as the design reference.
