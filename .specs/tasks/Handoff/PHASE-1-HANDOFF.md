# Phase 1 — Tool Registry + Inline Tool-Call Cards — Handoff

**Status:** Backend complete ✅ | Frontend implemented (not committed) ⚠️ | Frontend build unverified ⚠️
**Date:** 2026-07-05
**Commit:** `40647b52` (pushed to origin/main)
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
| `backend/tests/test_tool_registry.py` | **Created** | 24 tests — metadata defaults, registry ops, scope filtering, allowlist, scope denial, discovery serialization. All pass. |
| `.specs/tasks/draft/phase-1-tool-registry.md` | **Created** | Known limitations document. |

### Frontend (written to `/home/glenn/FlowmannerV2-frontend/`, NOT committed)

| File | Action | Details |
|------|--------|---------|
| `src/lib/chat-types.ts` | Modified | Added `ToolInvocation`, `AgentStep` interfaces. Added `steps?: AgentStep[]` directly to `ChatMessage` interface (at line 67). |
| `src/hooks/useStreaming.ts` | Modified | Added `callIdToStepIndexRef`. On `tool_call_start`: creates `AgentStep` + `tool_invocation`, appends to `message.steps[]`. On `tool_call_result`: updates matching step status/result/error. Existing sidebar feed (`addToolEvent`/`updateToolEvent`) preserved for backwards compat. |
| `src/components/chat/ToolCallCard.tsx` | **Created** | Collapsible card: status icons (Check/X/pulse dot/static dot), status badges (Pending/Running/Done/Error), step type prefix labels, duration display, args (pretty JSON), result, error in red, approval button stubs (Phase 2 no-ops). |
| `src/components/chat/MessageList.tsx` | Modified | Imported `ToolCallCard` + `AgentStep`. After message content and before citations, renders `<ToolCallCard>` for each step in `msg.steps`. |
| `src/components/chat/ToolCallCard.test.tsx` | **Created** | 12 vitest tests: render each state, expand/collapse, args pretty-printing, error display, step type prefixes, awaiting_approval buttons. |

---

## What was NOT done (deferred to Phase 2+)

| Item | Phase | Notes |
|------|-------|-------|
| `_execute_tool_call` real scope resolution | 5 | Currently denies ALL tools with `required_scopes` (no DB lookup). Phase 1 allowlisted tools all have empty scopes, so this is defense-in-depth. |
| Sidebar `ToolEventContext` derived from `steps[]` | 2 | Currently two parallel independent tracks. Spec wanted `steps[]` as single source of truth. |
| `_user_has_scopes` role constants | 2 | Hardcodes `admin`/`owner` strings. Extract to shared constants module. |
| Frontend `pnpm lint && pnpm build` | now | Frontend source outside project root — must be run manually. |
| Frontend commit + deploy | now | Frontend has its own git repo at `/home/glenn/FlowmannerV2-frontend/`. Commit separately, then `ship`. |
| framer-motion animation on ToolCallCard | polish | Spec mentioned `motion` for expand/collapse. Currently uses CSS `rotate-180` transition. Works correctly. |
| Wider tool allowlist (browser_*, linear_*, etc.) | 2+ | Phase 1 intentionally small: sandboxd + web search + RAG + memory reads only. |

---

## Verification steps for next agent

```bash
# 1. Backend — already verified
docker compose exec backend python -m pytest tests/test_tool_registry.py -v
# Expected: 24 passed

# 2. Frontend — MUST verify before deploying
cd /home/glenn/FlowmannerV2-frontend
pnpm lint && pnpm build && pnpm test

# 3. Commit frontend changes
git add src/lib/chat-types.ts src/hooks/useStreaming.ts src/components/chat/ToolCallCard.tsx src/components/chat/MessageList.tsx src/components/chat/ToolCallCard.test.tsx
git commit -m "feat: Phase 1 — inline tool-call cards + message steps[] population"

# 4. Deploy frontend
ship
# or: bash /opt/flowmanner/deploy-frontend.sh
# ⚠️ Takes ~4 minutes. Use timeout=300.

# 5. Manual verification
# Send a chat message that triggers a sandboxd tool call
# → Inline ToolCallCard should appear below the assistant message
# → Should show running → success transition
# → Click to expand: args (pretty JSON) + result
```

---

## Architecture decisions made

1. **Tool allowlist is explicit, not implicit.** The `_get_chat_openai_tools` function has a clearly documented allowlist of Phase 1 safe tools. This is intentional — the spec warned against silently opening all 110+ tools to the LLM.

2. **`required_scopes` coexists with `requires_auth`.** The existing `requires_auth: bool` stays for backwards compat. `required_scopes` is the fine-grained version. Both are on `ToolMetadata`.

3. **`rate_limit` (int) and `rate_limit_key` (str) are different concepts.** `rate_limit` is a numeric ceiling. `rate_limit_key` is a grouping key for shared rate budgets (e.g., all browser tools share one budget). Both on `ToolMetadata`.

4. **Discovery endpoint returns richer metadata than `to_openai_schema()`.** The spec suggested `to_openai_schema()` but the endpoint returns `required_scopes`, `requires_sandbox`, `rate_limit_key`, etc. — fields that don't exist in OpenAI's format but are essential for a discovery UI.

5. **`steps[]` populated via `setMessages` functional updater.** This is correct for React batching — multiple `tool_call_start` events in the same tick are handled correctly by the functional updater pattern.

6. **TypeScript interface hoisting.** `AgentStep` is defined at line 355 of `chat-types.ts` but referenced by `ChatMessage` at line 67. TypeScript hoists interface declarations, so this works. Unusual but valid.

---

## Key files for context

| File | Why it matters |
|------|---------------|
| `backend/app/tools/base.py` | `ToolMetadata` + `ToolRegistry` — the foundation |
| `backend/app/services/chat_service.py` | `_get_chat_openai_tools` (allowlist) + `_execute_tool_call` (auth gate) + `stream_message_to_llm` (SSE emitter) |
| `.sisyphus/src/components/MessageList.tsx` | Prototype `AgentStepCard` — the design reference for `ToolCallCard` |
| `.sisyphus/src/lib/types.ts` | Prototype `StreamingState` with Maps — the design reference for `steps[]` architecture |
| `.sisyphus/src/lib/store.ts` | Prototype `finalizeStream()` — Map → array collapse pattern |
