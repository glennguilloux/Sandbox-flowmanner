# Task: Phase 2 — Agent Step Streaming (Chat + Missions Unified)

**Status:** DRAFT (revised by Hermes — supersedes DeepSeek draft)
**Priority:** P2 — enables autonomous agent visibility in chat
**Estimated effort:** 2 sessions
**Created:** 2026-07-05
**Depends on:** Phase 1 (tool registry + inline cards) ✅ complete
**Blocks:** Phase 3 (canvas v1)
**Context docs:** `docs/HYBRID-PLATFORM-WORKSPACE.md`, `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` §Phase 2, `.specs/REFERENCE-PROTOTYPE.md`

---

## ⚠️ Corrections from the DeepSeek draft

The original draft invented several APIs that do not exist in the codebase. Verified against the actual files on 2026-07-05:

1. **`UnifiedExecutor` does NOT have a `subscribe(mission_id)` method.** The draft's `async for event in executor.subscribe(mission_id):` pattern is fabricated. `grep -n "subscribe" substrate/executor.py` returns nothing. The `EventLog` class (`substrate/event_log.py`) has `append`, `get_events`, `get_latest_sequence`, `run_exists`, `_count_events`, `get_event_log` — there is no `subscribe()` anywhere in the substrate stack. The correct pattern is to **poll `event_log.get_events(db, run_id, after_seq=N)`** with a cursor (sequence number) and yield new events on the SSE stream. This is exactly the pattern the existing `_mission_cqrs/queries.py:stream_status()` uses — read it first.

2. **There is no `POST /api/v2/missions/{id}/approve` endpoint.** The draft's `POST /api/v2/missions/{id}/deny` is also invented. Verified against `v2/missions.py` on 2026-07-05: the only approve route is **`POST /{mission_id}/tasks/{task_id}/approve`** (`v2/missions.py:465`), which calls `hitl.resolve_interrupt(db, interrupt_id, "approved", resolved_by=str(user.id))`. There is **no mission-level approve endpoint** — approvals are per-task, per-interrupt via HITL. The frontend `PermissionCard` Approve button must therefore POST to `POST /api/v2/missions/{mission_id}/tasks/{task_id}/approve?interrupt_id=...` (the actual hitl interrupt resolution path), not a fabricated `/missions/{id}/approve`. Read the v2 missions router before writing the backend hook.

3. **There is no `spawn-mission` endpoint today.** `grep "spawn.mission\|spawn_mission" backend/app/api/v2/` returns zero hits. The v2 chat router (`v2/chat.py`) already has `/threads/{id}/chat/stream` (`:454`), but the spawn path is genuinely new.

4. **The substrate event log is correctly named `EventLog`, not `executor.subscribe`.** `substrate/__init__.py:12` re-exports `EventLog, get_event_log`. Use `get_event_log()` to get the singleton, then `event_log.get_events(db, run_id, after_seq=current_seq)` to poll the append-only log. The substrate AGENTS.md rule #2 codifies this: "The event log is the source of truth for workflow state."

5. **`_mission_cqrs.commands.create_mission` exists** with the right shape (`commands.py` CQRS handler `create_mission(user, payload, workspace_id=...)`), per the `_mission_cqrs/AGENTS.md` map. However, the draft's `parent_thread_id` and `source='chat'` parameters are **not in the existing signature**. You will likely need to either (a) accept extra payload fields in the existing `MissionCreate` schema and have the handler thread them through, or (b) introduce a chat-specific facade that creates the Mission and then writes a side link (e.g. a `chat_threads.mission_id` column or a join table). Read `commands.py:create_mission` and `MissionCreate` schema before deciding; do not invent a parameter that isn't there.

6. **`socket.io-client: ^4.8.3` is already in `package.json`** (confirmed). The workspace doc's decision to add Socket.IO is sound, but Phase 2 can ship with pure SSE + POST `/cancel` per the re-imagine prompt's explicit instruction. Socket.IO can be a follow-up for cancel/pause/inject — don't over-build in this phase.

---

## 🔴 Reference prototype patterns (from `.sisyphus/src/`)

### A. The mock SSE stream is the backend contract specification

`app/api/chat/stream/route.ts` (314 lines) is a working simulation of the **entire** event protocol. It shows the canonical event ordering for a chat turn that involves tools and reasoning:

```
1. canvas_update     → { tools: [...], model, timestamp }              (initial context)
2. tool_call_start   → { toolCallId, toolName, args, timestamp }        (if tools needed)
3. tool_call_result  → { toolCallId, toolName, result, status, timestamp }
4. agent_step_start  → { stepId, stepType, agentName, name, displayName, timestamp }
5. text_delta        → { content, timestamp }                           (streamed in chunks)
6. agent_step_end    → { stepId, stepType, status, agentName, timestamp }
7. canvas_update     → { action: "open_tile", tileKind, config, timestamp }
8. citation          → { sources: [...], timestamp }
9. done              → { messageId, tokenCount, cost, timestamp }
```

The Phase 2 backend `mission_event_stream` proxy must emit this same sequence — translating substrate `EventLog` events into these chat-compatible frames.

### B. Paired `agent_step_start` / `agent_step_end` events

The prototype uses **paired events** (not a single `agent_step` event):
- `agent_step_start` → adds to `streaming.activeSteps: Map<stepId, AgentStepEvent>` with status `running`
- `agent_step_end` → removes from the Map (the step is now complete)

The frontend `StreamingIndicator.tsx` renders active steps with spinners during streaming. On `done`, `finalizeStream()` collapses the accumulated state into `message.steps[]`.

The substrate event log emits `substrate.node_started` and `substrate.node_completed` events — map these directly to `agent_step_start` and `agent_step_end`.

### C. `canvas_update` — backend-driven tile orchestration

The prototype introduces a `canvas_update` SSE event that lets the **backend** instruct the frontend to open tiles:

```json
{
  "type": "canvas_update",
  "data": {
    "action": "open_tile",
    "tileKind": "code_sandbox",
    "config": { "language": "python", "code": "print('hello')" },
    "timestamp": 1234567890
  }
}
```

This is the missing orchestration layer the DeepSeek drafts didn't have. When the LLM's response involves code execution, the backend sends `canvas_update` with `action: "open_tile"` and the frontend opens the tile automatically. This means tile creation is driven by **both** the user (via slash commands) **and** the backend (via SSE events). Phase 3 must handle both paths.

### D. `sandbox_event` — sandbox lifecycle in the stream

```json
{
  "type": "sandbox_event",
  "data": {
    "sandboxId": "sbx_demo_001",
    "status": "running",
    "previewUrl": "/sandbox-preview/demo",
    "language": "python",
    "timestamp": 1234567890
  }
}
```

Collected into `streaming.sandboxEvents[]` and rendered by `SandboxTile.tsx` when non-empty.

### E. `reasoning_delta` — streaming reasoning text

Separate from `text_delta` — the prototype accumulates reasoning text in `streaming.reasoning` and renders it in the `AgentTracePanel` right sidebar. This maps to the substrate's reasoning events.

### F. Slash command vocabulary

`ChatInput.tsx:16-24` defines 7 slash commands with an autocomplete picker (arrow-key navigation, Tab/Enter to apply, Escape to close). Phase 2 adds `/spawn mission` from this set.

---

## Problem

Chat and missions are completely separate surfaces. When the LLM calls tools in chat, the user sees inline tool cards (Phase 1). But when a full autonomous agent mission runs via `substrate.UnifiedExecutor` (DAG/Swarm/Graph/etc. strategies), the user has to navigate to the `/missions` page to see progress. There's no way to spawn a mission from chat and watch it execute inline.

**Goal:** A chat message can spawn a "mini-mission" whose reasoning, tool calls, and handoffs render inline in the chat as `AgentStep[]`. One event stream turns the substrate run into chat-compatible SSE frames (`tool_call_start`, `tool_call_result`, `agent_step`, `permission_request`), all sourced from the substrate `EventLog`.

---

## Acceptance Criteria

- [ ] `POST /api/v2/chat/threads/{thread_id}/spawn-mission` creates a mission linked to the thread (read `_mission_cqrs/commands.py:create_mission` first — likely add a `parent_thread_id`/`source` field via a new `SpawnMissionRequest` schema rather than changing the existing `MissionCreate`)
- [ ] Mission events are produced as chat-compatible SSE frames by polling the substrate `EventLog` (`get_event_log().get_events(db, run_id, after_seq=N)`)
- [ ] The SSE proxy translates substrate event types (`substrate.tool_call`, `substrate.node_started`, `substrate.checkpoint`, `substrate.permission_request` — read `event_log.py:append` to confirm the actual event type strings before coding) into the chat frames `tool_call_start`, `tool_call_result`, `agent_step`, `permission_request`
- [ ] `agent_step` SSE events are parsed in `useStreaming.ts` and appended to `message.steps[]`
- [ ] Reasoning steps render as collapsible monospace blocks (inline, not side panel)
- [ ] `permission_request` events render as inline cards with Approve/Deny buttons
- [ ] Approve button POSTs to the actual existing endpoint: `POST /api/v2/missions/{mission_id}/tasks/{task_id}/approve?interrupt_id=<id>` (per `v2/missions.py:465`, **not** a fabricated `/missions/{id}/approve`)
- [ ] `pnpm lint && pnpm build` passes
- [ ] Backend tests pass: `test_spawn_mission_from_chat.py`

---

## Sub-tasks

### 2.1 — Add spawn-mission endpoint (backend)

**File:** `backend/app/api/v2/chat.py`

Add:

```python
class SpawnMissionRequest(BaseModel):
    prompt: str
    agent_team: str | None = None
    sandbox_required: bool = False

@router.post("/threads/{thread_id}/spawn-mission", status_code=201)
async def spawn_mission_from_chat(
    thread_id: int,
    body: SpawnMissionRequest,
    user = Depends(get_current_user),
    commands: MissionCommandHandlers = Depends(get_mission_commands),
):
    # Call commands.create_mission with appropriate payload.
    # ⚠️ The existing MissionCreate schema likely does not have a parent_thread_id
    # field. Options:
    #   (a) Extend MissionCreate (cross-cutting; affects all callers) — preferred for cleanliness
    #   (b) Create the mission first, then write a side link to the thread (additional table
    #       or a column on chat_threads) — preferred if you don't want to widen MissionCreate
    # Choose (a) only if you read MissionCreate first and confirm it's safe. Otherwise (b).
    ...
    return ok({
        "mission_id": str(mission.id),
        "stream_url": f"/api/v2/chat/threads/{thread_id}/mission-stream/{mission.id}",
    })
```

### 2.2 — Add mission SSE proxy endpoint (backend)

**File:** `backend/app/api/v2/chat.py`

**⚠️ The draft's `async for event in executor.subscribe(mission_id):` is fabricated** — that method does not exist. Use the `EventLog.get_events(db, run_id, after_seq=N)` polling pattern instead.

```python
@router.get("/threads/{thread_id}/mission-stream/{mission_id}")
async def mission_event_stream(
    thread_id: int,
    mission_id: str,
    user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE proxy: polls the substrate EventLog and translates events into chat-compatible frames."""
    from app.services.substrate import get_event_log

    async def event_generator():
        event_log = get_event_log()
        current_seq = 0
        # The run_id may differ from mission_id — read substrate/executor.py to find
        # the canonical run_id lookup (mission.plan.substrate_run_id per _mission_cqrs abort path).
        run_id = await _resolve_run_id(db, mission_id)

        while True:
            events = await event_log.get_events(db, run_id, after_seq=current_seq)
            for evt in events:
                current_seq = max(current_seq, evt.sequence)
                frame = _translate_substrate_event_to_chat_frame(evt, mission_id)
                if frame:
                    yield frame
            if await _is_run_terminal(db, run_id):
                break
            await asyncio.sleep(0.5)  # polling cadence — tune for responsiveness

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**Read first** — `substrate/event_log.py:append` and `node_executor.py` (which calls `event_log.append(event_type="substrate.node_started"|"substrate.tool_call"|...)` extensively). The event type strings and payload shapes are already defined; `_translate_substrate_event_to_chat_frame` must map the actual `evt.event_type` strings, not invented ones. Per `substrate/AGENTS.md` rule #1 every state transition emits a substrate event with a known type — enumerate those types by reading the `event_log.append(` call sites in `node_executor.py` before writing the translator.

### 2.3 — Parse agent_step events in useStreaming.ts (frontend)

**File:** `frontend/src/hooks/useStreaming.ts`

Add parsing for the new `agent_step` SSE event type:

```typescript
case 'agent_step':
  const step: AgentStep = {
    type: event.data.type,    // 'reasoning' | 'tool' | 'handoff' | 'sandbox'
    name: event.data.name,
    status: event.data.status,
    reasoning: event.data.reasoning,
    startedAt: event.data.startedAt,
  };
  appendStepToMessage(currentMessageId, step);
  break;

case 'permission_request':
  const permStep: AgentStep = {
    type: 'permission_request',
    name: event.data.tool,
    status: 'running',
    startedAt: Date.now(),
    tool_invocation: {
      call_id: event.data.call_id,
      tool: event.data.tool,
      arguments: {},
      status: 'awaiting_approval',
      startedAt: Date.now(),
    },
  };
  appendStepToMessage(currentMessageId, permStep);
  break;
```

### 2.4 — Render reasoning steps inline (frontend)

**File:** `frontend/src/components/chat/ThoughtPanel.tsx`

Promote `ThoughtPanel` from side panel to inline rendering. When an `AgentStep` with `type === 'reasoning'` appears in `message.steps[]`, render it as a collapsible monospace block directly below the message content:

```tsx
{step.type === 'reasoning' && (
  <Collapsible>
    <CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground">
      <Brain className="h-4 w-4" />
      <span>{step.name}</span>
      <StatusBadge status={step.status} />
    </CollapsibleTrigger>
    <CollapsibleContent>
      <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto">
        {step.reasoning}
      </pre>
    </CollapsibleContent>
  </Collapsible>
)}
```

### 2.5 — Add permission request cards (frontend)

**Create:** `frontend/src/components/chat/PermissionCard.tsx`

Inline card for `permission_request` steps:
- Shows tool name, required scopes, mission context, **task_id** and **interrupt_id** (both needed for the actual approve endpoint)
- **Approve** button → `POST /api/v2/missions/{mission_id}/tasks/{task_id}/approve?interrupt_id={id}` (verified — `v2/missions.py:465`)
- **Deny** button → `POST /api/v2/missions/{mission_id}/tasks/{task_id}/deny?interrupt_id={id}` (⚠️ read the v2 missions router — the deny route may not exist yet; if it doesn't, deny is "abort the mission", which goes through `POST /api/v2/missions/{mission_id}/abort`)
- On approve: update step status to `success`, resume mission stream
- On deny: update step status to `error`, abort mission

### 2.6 — Wire spawn command to chat input

**File:** `frontend/src/lib/slash-commands.ts`

Add `/spawn` slash command:
```typescript
{
  command: 'spawn',
  description: 'Spawn an autonomous agent mission from chat',
  handler: async (args, threadId) => {
    const { mission_id, stream_url } = await spawnMission(threadId, { prompt: args });
    // Connect to SSE stream and pipe events into useStreaming
    connectMissionStream(stream_url, threadId);
  },
}
```

### 2.7 — Tests

**Backend:** Create `backend/tests/test_spawn_mission_from_chat.py`
- Test mission created with the new `parent_thread_id` / side link (whatever shape 2.1 landed on) and `source='chat'`
- Test SSE stream polls `EventLog.get_events` and emits at least one `agent_step` event for a trivial mission (use a seeded run_id with a known event sequence)
- Test `permission_request` fires when a tool with required scopes is invoked without prior grant (use a tool with `required_scopes=["test:restricted"]`)

Do not try to model the SSE stream test on the non-existent `executor.subscribe` — use the `EventLog` directly: seed a few `substrate_events` rows for a known `run_id` and assert the proxy maps them to the expected chat frames.

**Frontend:** Manual integration test:
- Send `/spawn summarize my Q3 repo activity` in chat
- Watch agent step tree stream inline
- Click Approve on a GitHub tool permission card
- See the tool call card resolve

### 2.8 — Verification gate

```bash
# Backend (host — not in Docker build context — wait for rebuild)
cd /opt/flowmanner
docker compose exec backend pytest app/tests/test_spawn_mission_from_chat.py -v

# Frontend
cd /home/glenn/FlowmannerV2-frontend
pnpm lint && pnpm build

# Manual: spawn mission from chat, watch steps stream inline
```

---

## File Map

| File | Action |
|------|--------|
| `backend/app/api/v2/chat.py` | Add `spawn-mission` (POST `:394` region) + `mission-stream` SSE proxy with `EventLog.get_events` polling |
| `backend/app/schemas/...` | Possibly extend `MissionCreate` schema with `parent_thread_id`/`source` (decide in 2.1) |
| `backend/app/api/v2/__init__.py` | Ensure chat v2 router is registered (already is — sanity-check) |
| `backend/tests/test_spawn_mission_from_chat.py` | **NEW** — spawn + stream tests |
| `frontend/src/hooks/useStreaming.ts` | Parse `agent_step` + `permission_request` events |
| `frontend/src/components/chat/ThoughtPanel.tsx` | Promote to inline reasoning renderer |
| `frontend/src/components/chat/PermissionCard.tsx` | **NEW** — approve/deny card targeting the real hitl interrupt endpoint |
| `frontend/src/lib/slash-commands.ts` | Add `/spawn` command |

---

## Architecture Notes

- **SSE vs WebSocket:** Use SSE for all streaming (tokens + agent steps + permissions). Socket.IO is already installed (`socket.io-client: ^4.8.3`) and can be added later for cancel/pause/inject — but Phase 2 ships with SSE + `POST /missions/{id}/abort` per the re-imagine prompt's explicit guidance. Don't ship Socket.IO in this phase.
- **Event unification:** The mission SSE proxy emits the same frame types as `stream_message_to_llm` (`tool_call_start`, `tool_call_result` — both already emitted at `chat_service.py:1605, 1616`). The new `agent_step` and `permission_request` types are additive.
- **Substrate event log is the source of truth** (per `substrate/AGENTS.md` rule #2). The proxy polls `EventLog.get_events(db, run_id, after_seq=N)`, NOT a fabricated `executor.subscribe`. Polling cadence of 500ms is a starting point — tune for responsiveness vs DB load.
- **Run resolution:** the chat sees `mission_id`; the substrate event log keys events by `run_id`. Read `commands.py` abort handlers to find the canonical `run_id` lookup (`mission.plan.substrate_run_id` is the pattern used by `abort_mission`).

---

## Risks

| Risk | Mitigation |
|------|------------|
| Substrate event type strings differ from the draft's guesses | Read `node_executor.py` `event_log.append(...)` call sites and `event_log.py::SubstrateEvent.event_type` enum before writing `_translate_substrate_event_to_chat_frame`. |
| Mission takes too long, SSE connection drops | Frontend reconnects with `Last-Event-ID` (the current_seq cursor). The EventLog persists events for replay. |
| Permission approve/deny race condition | Use idempotent approve/deny with the actual `interrupt_id`. `hitl.resolve_interrupt` is idempotent per its CQRS pattern (verify by reading `hitl_service.py`). |
| `MissionCreate` schema change is cross-cutting | If extending `MissionCreate` is risky, take option (b) — a side link / new column on `chat_threads`. ADR-style comment in the route handler documents the choice. |
| Polling the EventLog adds DB load | Use the smallest possible `after_seq` cursor + a 500ms sleep. If DB pressure shows up in metrics, switch to the substrate WebSocket-manager pubsub (`WorkflowWSManager` in `strategies/base.py`). |
