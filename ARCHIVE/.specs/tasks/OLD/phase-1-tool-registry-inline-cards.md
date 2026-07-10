# Task: Phase 1 — Tool Registry + Inline Tool-Call Cards

**Status:** DRAFT (revised by Hermes — supersedes DeepSeek draft)
**Priority:** P1 — first feature layer on clean chat baseline
**Estimated effort:** 2 sessions
**Created:** 2026-07-05
**Depends on:** Phase 0 (stabilize) ✅ complete
**Blocks:** Phase 2 (agent step streaming)
**Context docs:** `docs/HYBRID-PLATFORM-WORKSPACE.md`, `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` §Phase 1, `.specs/REFERENCE-PROTOTYPE.md`

---

## ⚠️ Corrections from the DeepSeek draft

The original draft had several issues that touch the backend design:

1. **`ToolMetadata` already has most of what the draft asked to add.** Reading `backend/app/tools/base.py:63-81` on 2026-07-05, the class already has: `tool_id`, `name`, `description`, `category`, `input_schema`, `output_schema`, `source_service`, `requires_auth: bool`, `cost_estimate`, `rate_limit: int | None`, `timeout_seconds`, `tags`, `examples`, `metadata` (arbitrary dict), `created_at`, `updated_at`. It also already has `to_openai_tool()`, `to_anthropic_tool()`, `to_langchain_tool()`. What it does **NOT** have and we need to add: `required_scopes: list[str]` (the draft's `requires_auth: bool` is a poor man's version — it's a single boolean, not a scope list; keep `requires_auth` for backwards compat and add `required_scopes` alongside it), `requires_sandbox: bool`, `rate_limit_key: str | None` (note: `rate_limit: int | None` already exists as a numeric rate ceiling; the draft's `rate_limit_key` is a different concept — a *grouping key* for shared limits, e.g. `'browser'` so all browser tools share one budget). Do **not** silently replace `rate_limit` with `rate_limit_key` — add the latter alongside.

2. **`ToolRegistry` is already fully implemented** at `base.py:151` with `register()`, `unregister()`, `list_all()`, `search()`, `by_tag()`, `get()`, and a `get_tool_registry()` singleton accessor. The Phase 1.1 backend work is therefore: **add three fields, write a discovery endpoint, and wire capability token checks** — not "create a registry". The research doc understated how much is already there.

3. **The chat tool-calling loop today only exposes 6 sandboxd tools.** Verified at `chat_service.py:1352-1369` (`_get_chat_openai_tools`): it pulls `registry.list_all()`, filters to `sandboxd_ids = {"sandboxd_preview", "sandboxd_exec", "sandboxd_file_write", "sandboxd_file_read", "sandboxd_file_list", "sandboxd_serve"}`, and returns those (or `None` if `settings.SANDBOXD_ENABLED` is false). The ~110 other tools in `app/tools/` are **not** exposed to the LLM in chat today. Phase 1's "tool discovery" is therefore not just an enumeration endpoint — it is also **the act of widening the chat tool surface** beyond sandboxd. Decide deliberately which tools to expose to chat (web search yes; destructive DB writes no). Capture this decision in a follow-up ADR rather than silently opening all 110 to the LLM.

4. **`_execute_tool_call` already uses the registry.** Verified at `chat_service.py:1375-1394`: it calls `get_tool_registry().get(tool_name)`, executes via `await tool.execute(args)`, and returns JSON. What it does **not** do is check capability tokens, workspace allowlists, or per-user scope — this is the actual authz gap that Phase 1 (and Phase 5) must close. Keep the existing dispatch path; add an authz gate in front of `tool.execute(args)`.

5. **The SSE frames already exist.** Verified at `chat_service.py:1605` (`tool_call_start`) and `1616` (`tool_call_result`) — the streaming loop already emits these events. Frontend `useStreaming.ts` therefore doesn't need new SSE frame types for Phase 1; it needs to consume the existing frames into a new `message.steps[]` shape.

---

## 🔴 Reference prototype patterns (from `.sisyphus/src/`)

The prototype is the authoritative design reference for Phase 1. Three contributions are critical:

### A. The SSE event vocabulary is larger than the drafts assumed

The prototype at `lib/types.ts:14-28` defines **14 event types**. The drafts only knew about 3. The events Phase 1 must handle:

| Event | Source file | Purpose |
|-------|------------|---------|
| `text_delta` | `store.ts:294-296` | Streaming tokens (already exists in production) |
| `tool_call_start` | `store.ts:302-306` | Tool invocation begins — adds to `activeToolCalls` Map |
| `tool_call_delta` | — | Tool args streaming incrementally (optional for Phase 1, needed for Phase 2) |
| `tool_call_result` | `store.ts:309-315` | Tool invocation completes — moves to `toolResults` Map, removes from `activeToolCalls` |
| `agent_step_start` | `store.ts:318-322` | Agent step begins — adds to `activeSteps` Map |
| `agent_step_end` | `store.ts:325-328` | Agent step completes — removes from `activeSteps` Map |
| `reasoning_delta` | `store.ts:298-299` | Reasoning text streaming incrementally |
| `citation` | `store.ts:331-335` | RAG citation |
| `permission_request` | `store.ts:338-342` | HITL approval needed |
| `canvas_update` | `store.ts:345-347` | Backend instructs frontend to open/modify a tile |
| `sandbox_event` | `store.ts:349-353` | Sandbox lifecycle event |
| `handoff` | — | Agent-to-agent handoff (Phase 2) |
| `error` | `store.ts:356-358` | Stream error |
| `done` | `store.ts:361-362` | Stream complete (carries `messageId`, `tokenCount`, `cost`) |

**Phase 1 scope:** implement `tool_call_start`, `tool_call_result`, `text_delta`, `done`. The remaining events are additive in Phases 2-4 but the type union should be defined now to avoid churn.

### B. StreamingState uses Maps, not arrays

The prototype's `StreamingState` (`types.ts:93-105`) uses `Map<string, T>` for active tool calls, results, and steps — **not array appends**. This is the correct architecture:

```typescript
// From prototype lib/types.ts:93-105
interface StreamingState {
  isStreaming: boolean;
  content: string;                                    // Accumulated text_delta
  reasoning: string;                                  // Accumulated reasoning_delta
  activeToolCalls: Map<string, ToolCallStart>;        // In-flight tool calls (keyed by toolCallId)
  toolResults: Map<string, ToolCallResult>;           // Completed tool results
  activeSteps: Map<string, AgentStepEvent>;           // In-flight agent steps (keyed by stepId)
  citations: { source: string; excerpt: string; score: number }[];
  pendingPermissions: PermissionRequest[];
  sandboxEvents: { sandboxId: string; status: string; previewUrl?: string }[];
  error: string | null;
  messageId: string | null;                           // Set by 'done' event
}
```

Why Maps: O(1) updates during streaming (no array scan to find the right entry), no duplicates (Map keys are unique), and the `finalizeStream()` pattern collapses Maps into the persisted `message.steps[]` array on `done`.

### C. `finalizeStream()` — the streaming-to-persisted transition

`store.ts:370-424`: on the `done` event, `finalizeStream()` builds the assistant `ChatMessage` with `steps[]` derived from `streaming.toolResults`, persists it, and resets streaming state. The drafts' "append to steps[] on every event" approach would create duplicates and race conditions; the prototype's Map → array collapse on `done` is the correct pattern.

### D. AgentStepCard — the ToolCallCard template

`MessageList.tsx:268-346` — the prototype's `AgentStepCard` component IS the `ToolCallCard` Phase 1 needs:
- Collapsible header with status icon logic: `Check` (completed), `X` (failed), animated `pulse` dot (running), static dot (pending)
- `stepType` prefix labels: "Tool:", "Reasoning:", "Handoff:", "Sandbox:"
- `displayName || name` for the title
- `agentName` shown on the right
- Expand/collapse chevron with `rotate-180` transition
- Expanded body: `result` as pretty JSON via `safeStringify`, `error` in red

Adapt this component — do not reinvent it.

---

## Problem

Tool calls in chat are invisible to the user. When the LLM calls a tool (e.g. `sandboxd_preview`, `sandboxd_exec`), the tool executes silently and only the final text response is shown. The user has no visibility into what tools were called, with what arguments, or what results came back. The right sidebar `ToolEventContext` captures the events but they are disconnected from the inline message flow.

Additionally, the chat tool surface is artificially narrow — only 6 sandboxd tools are exposed to the LLM (see correction #3 above), so the agent's capability set in chat is a tiny subset of what already exists in `app/tools/`.

**Goal:** Make tools a first-class concept with discoverable schemas, capability-gated execution, a discoverable API surface, and inline rendering in the chat message stream.

---

## Acceptance Criteria

- [ ] `ToolMetadata` extended with `required_scopes: list[str]`, `requires_sandbox: bool`, `rate_limit_key: str | None` (without removing the existing `rate_limit` int)
- [ ] `GET /api/v2/tools/discover` endpoint returns filtered tool list for the calling user/workspace
- [ ] `chat_service._execute_tool_call` checks capability tokens before invoking tools
- [ ] A deliberate decision (in an ADR or a comment in `_get_chat_openai_tools`) about which non-sandboxd tools to expose to chat in this phase
- [ ] `chat-types.ts` extended with `ToolInvocation` and `AgentStep` interfaces
- [ ] `ChatMessage` interface has optional `steps?: AgentStep[]` field
- [ ] `useStreaming.ts` populates `message.steps[]` from the existing `tool_call_start`/`tool_call_result` SSE events (no new frame types needed)
- [ ] `ToolCallCard.tsx` component renders inline in `MessageList.tsx` under the assistant message
- [ ] Tool call card shows: tool name, status badge, args (pretty JSON), result, error, duration
- [ ] Right sidebar `ToolEventContext` still works (backwards compat — read-only projection of `steps[]`)
- [ ] `pnpm lint && pnpm build` passes
- [ ] Backend tests pass: `test_tool_registry.py`

---

## Sub-tasks

### 1.1 — Extend ToolMetadata (backend)

**File:** `backend/app/tools/base.py:63-81`

Add three fields alongside the existing ones (do NOT remove or rename `rate_limit`):

```python
class ToolMetadata(BaseModel):
    # ... existing fields up to line 77 ...
    required_scopes: list[str] = Field(default_factory=list, description="Authz scopes needed to call this tool")
    requires_sandbox: bool = Field(False, description="Whether this tool runs in an isolated sandbox container")
    rate_limit_key: str | None = Field(None, description="Rate limit group key; tools sharing a key share one rate budget")
    # ... existing metadata dict, created_at, updated_at, model_config ...
```

`requires_auth: bool` at line 70 stays as-is for backwards compatibility (it's a coarse "requires any auth" flag; `required_scopes` is the fine-grained version). Existing tools that don't set the new fields get safe defaults (`[]`, `False`, `None`).

### 1.2 — Add tool discovery endpoint (backend)

**Create:** `backend/app/api/v2/tools.py`

```python
"""V2 Tool discovery — returns the tool list the calling user/workspace is authorized to invoke."""

from fastapi import APIRouter, Depends, Query
from app.api.deps import get_current_user
from app.api.v2.base import ok
from app.tools.base import get_tool_registry

router = APIRouter(prefix="/tools", tags=["v2-tools"])

@router.get("/discover")
async def discover_tools(
    user = Depends(get_current_user),
    workspace_id: str | None = None,
    category: str | None = Query(None),
):
    registry = get_tool_registry()
    tools = registry.list_all(category=category)
    # Filter by required_scopes — tools with no scopes are public.
    # Per-user scope check needs the actual authorization shape from app/api/deps.require_scope.
    permitted = [t for t in tools if not t.metadata.required_scopes or _user_has_scopes(user, t.metadata.required_scopes)]
    return ok({
        "tools": [t.to_openai_schema() for t in permitted],
        "total": len(permitted),
        "categories": sorted(registry._categories.keys()),
    })
```

**Register** in `backend/app/api/v2/__init__.py` alongside `workspaces_router`.

**⚠ Pivot:** do NOT hardcode `_user_has_scopes` until you have read `deps.py:358` (`require_scope(*required_scopes: str)` — v3 cookie session). The v2 routes use `get_current_user` (JWT), not `get_current_session` (cookie). Implement `_user_has_scopes` in terms of `require_scope` semantics — call the same dependency and catch `HTTPException(403)` on failure per tool, or copy the scope-resolution logic into a small helper. Match the v2 auth contract in `v2/AGENTS.md` (auth via `Depends(get_current_user)`).

### 1.3 — Wire capability token checks (backend)

**File:** `backend/app/services/chat_service.py:1375-1394`

The current `_execute_tool_call` already looks the tool up via the registry and executes it. Add a capability-token check before `await tool.execute(args)`:

```python
async def _execute_tool_call(tool_name: str, arguments_json: str, user_id: int | None = None, workspace_id: str | None = None) -> str:
    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if tool is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # NEW: capability check (per substrate/ node_executor.py — CapabilityEngine.verify())
    if tool.metadata.required_scopes:
        from app.services.substrate.capability_engine import CapabilityEngine  # verify import path
        try:
            CapabilityEngine.verify(scopes=tool.metadata.required_scopes,
                                    workspace_id=workspace_id)
        except Exception as e:
            return json.dumps({"error": f"capability denied: {e}"})

    args = json.loads(arguments_json) if arguments_json else {}
    result = await tool.execute(args)
    return json.dumps(result.result) if result.success else json.dumps({"error": result.error})
```

**⚠ Verify before coding:** the import path of `CapabilityEngine` and the exact `verify()` signature. `substrate/AGENTS.md` says "All tool calls go through `CapabilityEngine.issue()` + `verify_and_require()`. `NodeExecutor._handle_tool` is the canonical implementation." Open `node_executor.py` at `_handle_tool`, copy its capability-check pattern, and adapt it for the chat path. Do not invent a new signature.

### 1.4 — Decide which tools to expose to chat

**File:** `backend/app/services/chat_service.py:1352-1369` (`_get_chat_openai_tools`)

Currently the function hardcodes `sandboxd_ids = {6 sandboxd tools}`. Phase 1 is the moment to widen this deliberately. Reasonable Phase 1 additions (non-destructive, already implemented):
- `web_search_enhanced` — web search service (already used by chat for `?web_search=true`)
- `rag_search` — RAG retrieval (non-destructive)
- `memory_recall` — memory service (non-destructive read)

DO NOT expose in Phase 1: `browser_*` (Phase 4 will surface those as a dedicated sandbox), the destructive integrations (`linear_`, `slack_`, `stripe_`, `github_manager` write ops), or any tool with `requires_auth=True` + broad scopes that has no workspace gating yet.

Make this decision explicit in a comment block above the new `sandboxd_ids` set. The list is a Phase 1 allowlist, intentionally small; Phase 2+ widens it.

### 1.5 — Extend chat-types.ts (frontend)

**File:** `frontend/src/lib/chat-types.ts`

Add:
```typescript
export interface ToolInvocation {
  call_id: string;
  tool: string;
  arguments: Record<string, unknown>;
  status: 'pending' | 'running' | 'success' | 'error' | 'awaiting_approval';
  result?: string;
  error?: string;
  startedAt: number;
  endedAt?: number;
  capability_token?: string;
}

export interface AgentStep {
  type: 'reasoning' | 'tool' | 'handoff' | 'sandbox' | 'permission_request';
  name: string;
  status: 'running' | 'success' | 'error';
  tool_invocation?: ToolInvocation;
  reasoning?: string;
  startedAt: number;
  endedAt?: number;
}

// Extend existing ChatMessage
export interface ChatMessage {
  // ...existing fields...
  steps?: AgentStep[];
}
```

### 1.6 — Update useStreaming.ts (frontend)

**File:** `frontend/src/hooks/useStreaming.ts`

The backend already emits `tool_call_start` (chat_service.py:1605) and `tool_call_result` (1616). The frontend already parses them. The change is to **also** populate `message.steps[]` (in addition to the existing `ToolEventContext` feed) rather than only the sidebar.

```typescript
// On tool_call_start SSE event: append a new AgentStep to the triggering assistant message's steps[]
// On tool_call_result SSE event: update the matching step's status to 'success' or 'error', set result/error, endedAt
```

Keep the right-sidebar feed as a read-only projection for backwards compat — the goal is the steps array becomes the source of truth and the feed is derived from it.

### 1.7 — Create ToolCallCard.tsx (frontend)

**Create:** `frontend/src/components/chat/ToolCallCard.tsx`

Renders inline in `MessageList.tsx` under the assistant message that triggered the call.

**Design:**
- Collapsible header: tool name + status badge (⏳ pending, 🔄 running, ✅ success, ❌ error)
- Expandable body: args (pretty-printed JSON), result, error message, capability token id, duration
- Match existing dark/teal design language in `ChatLayout.tsx`
- Use `motion` (framer-motion) for expand/collapse animation

**States:**
- `pending` → gray border, spinner
- `running` → teal border, pulse animation
- `success` → green border, checkmark
- `error` → red border, error icon
- `awaiting_approval` → amber border, Approve/Deny buttons (Phase 2 hook — leave the button handlers as no-ops for Phase 1)

### 1.8 — Render ToolCallCard in MessageList.tsx

**File:** `frontend/src/components/chat/MessageList.tsx`

When rendering an assistant message, check `message.steps[]`. For each step with `type === 'tool'`, render a `<ToolCallCard>` below the message content.

### 1.9 — Tests

**Backend:** Create `backend/tests/test_tool_registry.py`
- Test registry loads tools via `get_tool_registry()` (no exceptions, returns a populated list)
- Test scope filtering (tool with `required_scopes=["x"]` is excluded from a user without that scope)
- Test `GET /api/v2/tools/discover` returns the expected filtered set for an authenticated user
- Test capability token denial path in `_execute_tool_call`

**Frontend:** Create `frontend/src/components/chat/ToolCallCard.test.tsx`
- Test render in each state (pending, running, success, error)
- Test expand/collapse
- Test args pretty-printing

### 1.10 — Verification gate

```bash
# Backend (host — not in Docker build context)
cd /opt/flowmanner
docker compose exec backend pytest app/tests/test_tool_registry.py -v

# Frontend
cd /home/glenn/FlowmannerV2-frontend
pnpm lint && pnpm build && pnpm test

# Manual: trigger a chat with a sandboxd_exec tool call
# → inline ToolCallCard should appear, stream running → success, show result
```

---

## File Map

| File | Action |
|------|--------|
| `backend/app/tools/base.py` | Extend `ToolMetadata` with 3 new fields (`:63-81`) |
| `backend/app/api/v2/tools.py` | **NEW** — tool discovery endpoint |
| `backend/app/api/v2/__init__.py` | Register tools router |
| `backend/app/services/chat_service.py` | Wire capability checks in `_execute_tool_call` (`:1375`); decide Phase 1 tool allowlist in `_get_chat_openai_tools` (`:1352`) |
| `backend/tests/test_tool_registry.py` | **NEW** — registry + endpoint tests |
| `frontend/src/lib/chat-types.ts` | Add `ToolInvocation`, `AgentStep`, extend `ChatMessage` |
| `frontend/src/components/chat/ToolCallCard.tsx` | **NEW** — inline tool-call card component |
| `frontend/src/components/chat/ToolCallCard.test.tsx` | **NEW** — component test |
| `frontend/src/hooks/useStreaming.ts` | Populate `message.steps[]` from existing `tool_call_start/result` SSE events |
| `frontend/src/components/chat/MessageList.tsx` | Render `ToolCallCard` for each tool step |

---

## Risks

| Risk | Mitigation |
|------|------------|
| `_get_chat_openai_tools` allowlist change exposes a destructive tool to chat | Phase 1 allowlist is intentionally small (sandboxd + web search + RAG + memory reads). Do not include `browser_*`, `linear_*`, `slack_*`, `stripe_*`, write integrations. A documented Phase 2+ decision widens it. |
| `CapabilityEngine.verify()` signature differs from the draft's pseudocode | Read `substrate/node_executor.py:_handle_tool` first; copy its pattern. Don't invent a new signature. |
| `useStreaming.ts` changes break existing tool event feed | Keep right-sidebar feed as a read-only projection of `steps[]` — the steps array is the new source of truth, the feed is derived. |
| Tool args JSON parsing fails for malformed arguments | Wrap in `try/catch`, show raw string on parse failure. |
