# Phase 2 — Agent Step Streaming + Sidebar Unification — Handoff

**Status:** Backend complete ✅ | Frontend committed ✅ | Phase 3 also complete ✅
**Date:** 2026-07-05
**Commits:** Backend `3fbf9ea2`, `92aad3dd` (pushed). Frontend `42771b9` (committed locally).
**Spec:** `.specs/tasks/draft/phase-2-agent-step-streaming.md`

---

## What was done

### Backend (committed, image rebuilt, container restarted, pushed to origin)

| File | Action | Details |
|------|--------|---------|
| `backend/app/core/auth_constants.py` | **Created** | `ADMIN_ROLES: frozenset[str] = frozenset({"admin", "owner"})` |
| `backend/app/api/v2/tools.py` | Modified | `_user_has_scopes` imports `ADMIN_ROLES` from `app.core.auth_constants` |
| `backend/app/services/chat_service.py` | Modified | (a) Widened allowlist with 10 read-only tools. (b) Three-branch scope resolution. (c) Pre-fetch user scopes. |
| `backend/tests/test_tool_registry.py` | Modified | +13 tests. Total: 37. All pass. |

### Frontend (committed — `42771b9`)

| File | Action | Details |
|------|--------|---------|
| `src/lib/chat-types.ts` | Modified | Added `stepId?: string` to `AgentStep`. Added `SSEEventType` union (14 types). |
| `src/hooks/useStreaming.ts` | Modified | Added `stepIdToStepIndexRef`, `reasoningAccumulatorRef`. Handlers for `agent_step_start`, `agent_step_end`, `tool_call_delta` (no-op), `reasoning_delta`. |
| `src/components/chat/ToolCallCard.tsx` | Modified | Added `Brain` icon. Reasoning steps render as collapsible monospace blocks. |
| `src/components/chat/ToolEventContext.tsx` | **Rewritten** | `setSourceSteps()` for sidebar unification. `toolEvents` derives from `message.steps[]`. |
| `src/app/[locale]/(dashboard)/chat/page-client.tsx` | Modified | Wired `setSourceSteps` via `useEffect` watching `store.messages`. |

---

## Architecture decisions made

1. **Three-branch scope resolution replaces blanket deny.** Admin/owner bypass → cached scopes → defense-in-depth deny.

2. **User scopes pre-fetched once per streaming request.** Both `send_message_to_llm` and `stream_message_to_llm` resolve scopes before the tool-calling loop.

3. **`ADMIN_ROLES` is a shared frozenset.** Extracted to `backend/app/core/auth_constants.py`.

4. **`agent_step_start` / `agent_step_end` are paired events.** Frontend tracks `stepId → stepIndex` via `stepIdToStepIndexRef`.

5. **`reasoning_delta` creates or appends to reasoning steps.** Handles both single-block and interleaved reasoning streams.

6. **Sidebar unification via `setSourceSteps()`.** `steps[]` is the single source of truth. Sidebar is a read-only projection.

7. **`tool_call_delta` is a no-op hook.** Hook point for Phase 3b live argument preview in ToolCallCard.

---

## What was NOT done (deferred to Phase 3+) — Status

| Item | Status | Notes |
|------|--------|-------|
| `permission_request` SSE event handling | Phase 3b | HITL interrupt integration |
| `canvas_update` SSE event handling | Phase 3b | Backend-driven tile orchestration |
| `sandbox_event` SSE event handling | Phase 3b | Sandbox lifecycle in stream |
| `tool_call_delta` live preview | Phase 3b | Handler is no-op hook; will stream partial arguments |
| `PermissionCard` component | Phase 3b | Approve/deny card for HITL |
| `/spawn mission` slash command | Phase 3+ | Chat-to-mission spawning |

---

## Key files for context

| File | Why it matters |
|------|---------------|
| `backend/app/core/auth_constants.py` | `ADMIN_ROLES` — the shared role constant |
| `backend/app/services/chat_service.py` | `_get_chat_openai_tools` (allowlist) + `_execute_tool_call` (scope resolution) + `stream_message_to_llm` (SSE emitter) |
| `src/lib/chat-types.ts` | `SSEEventType` union, `AgentStep.stepId` |
| `src/hooks/useStreaming.ts` | SSE event handlers for all Phase 2 event types |
| `src/components/chat/ToolCallCard.tsx` | Reasoning rendering in expanded body |
| `src/components/chat/ToolEventContext.tsx` | Sidebar unification via `setSourceSteps()` |
