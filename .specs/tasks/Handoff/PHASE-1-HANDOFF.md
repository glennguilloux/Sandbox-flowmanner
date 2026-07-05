# Phase 1 — Tool Registry + Inline Tool-Call Cards — Handoff

**Status:** Backend complete ✅ | Frontend committed ✅ (in Phase 2 commit) | Phase 2+3 also complete ✅
**Date:** 2026-07-05
**Commit:** Backend `40647b52`, Frontend committed in `42771b9`
**Spec:** Phase 1 task spec (pasted by user)

---

## What was done

### Backend (committed, image rebuilt, container restarted)

| File | Action | Details |
|------|--------|---------|
| `backend/app/tools/base.py` | Modified | `ToolMetadata` +3 fields: `required_scopes: list[str]`, `requires_sandbox: bool`, `rate_limit_key: str \| None`. Existing `rate_limit: int \| None` untouched. |
| `backend/app/api/v2/tools.py` | **Created** | `GET /api/v2/tools/discover` — scope-based filtering, composable `category` + `tag` query params, `rate_limit_key` in response. Uses `get_current_user` (JWT, v2 contract). |
| `backend/app/api/v2/__init__.py` | Modified | Registered `tools_router` after `marketplace_router`. |
| `backend/app/services/chat_service.py` | Modified | (a) `_get_chat_openai_tools` widened: sandboxd + `web_search_enhanced` + `rag_search` + `memory_recall`. (b) `_execute_tool_call` gains `user_id`/`workspace_id` params + deny-on-scope-required gate. (c) Both call sites pass `user_id`. |
| `backend/tests/test_tool_registry.py` | **Created** | 37 tests — Phase 1 (24) + Phase 2 scope resolution (13). All pass. |

### Frontend (committed in Phase 2 commit `42771b9`)

| File | Action | Details |
|------|--------|---------|
| `src/lib/chat-types.ts` | Modified | Added `ToolInvocation`, `AgentStep` interfaces. Added `steps?: AgentStep[]` directly to `ChatMessage` interface. |
| `src/hooks/useStreaming.ts` | Modified | Added `callIdToStepIndexRef`. On `tool_call_start`: creates `AgentStep` + `tool_invocation`, appends to `message.steps[]`. On `tool_call_result`: updates matching step status/result/error. |
| `src/components/chat/ToolCallCard.tsx` | **Created** | Collapsible card: status icons, status badges, step type prefix labels, duration display, args (pretty JSON), result, error in red. |
| `src/components/chat/MessageList.tsx` | Modified | Imported `ToolCallCard` + `AgentStep`. After message content, renders `<ToolCallCard>` for each step in `msg.steps`. |
| `src/components/chat/ToolCallCard.test.tsx` | **Created** | 16 vitest tests (updated in Phase 2). |

---

## What was NOT done (deferred to Phase 2+) — ALL COMPLETED

| Item | Status | Notes |
|------|--------|-------|
| `_execute_tool_call` real scope resolution | ✅ Phase 2 | Three-branch logic: admin/owner → cached scopes → deny |
| Sidebar `ToolEventContext` derived from `steps[]` | ✅ Phase 2 | `setSourceSteps()` for sidebar unification |
| `_user_has_scopes` role constants | ✅ Phase 2 | Extracted to `ADMIN_ROLES` in `auth_constants.py` |
| Frontend `pnpm lint && pnpm build` | ✅ Verified | Build passes |
| Frontend commit + deploy | ✅ Committed | In Phase 2 commit `42771b9` |
| framer-motion animation on ToolCallCard | Polish | CSS `rotate-180` transition works correctly |
| Wider tool allowlist (browser_*, linear_*, etc.) | ✅ Phase 2 | 10 read-only tools added |

---

## Architecture decisions made

1. **Tool allowlist is explicit, not implicit.** The `_get_chat_openai_tools` function has a clearly documented allowlist. Phase 1: 4 tools. Phase 2: +10 tools. Total: 14+.

2. **`required_scopes` coexists with `requires_auth`.** Both on `ToolMetadata`. `required_scopes` is the fine-grained version.

3. **`steps[]` populated via `setMessages` functional updater.** Correct for React batching — multiple `tool_call_start` events in the same tick handled correctly.

4. **Sidebar unified via `setSourceSteps()` (Phase 2).** `steps[]` is now the single source of truth. Sidebar derives from it.

---

## Key files for context

| File | Why it matters |
|------|---------------|
| `backend/app/tools/base.py` | `ToolMetadata` + `ToolRegistry` — the foundation |
| `backend/app/services/chat_service.py` | `_get_chat_openai_tools` (allowlist) + `_execute_tool_call` (scope resolution) + `stream_message_to_llm` (SSE emitter) |
| `src/lib/chat-types.ts` | `AgentStep`, `ToolInvocation`, `SSEEventType`, `CanvasTile` |
| `src/hooks/useStreaming.ts` | SSE event handlers for all Phase 1-2 event types |
| `src/components/chat/ToolCallCard.tsx` | Inline collapsible card with reasoning rendering |
