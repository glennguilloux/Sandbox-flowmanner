# Phase 2 — Agent Step Streaming + Sidebar Unification — Handoff

**Status:** Backend complete ✅ | Frontend implemented (not committed) ⚠️ | Frontend build verified ✅
**Date:** 2026-07-05
**Commits:** `3fbf9ea2` (feat), `92aad3dd` (test) — ahead of origin/main (unpushed)
**Spec:** `.specs/tasks/draft/phase-2-agent-step-streaming.md` (user-pasted Phase 2 task spec)

---

## What was done

### Backend (committed, image rebuilt, container restarted)

| File | Action | Details |
|------|--------|---------|
| `backend/app/core/auth_constants.py` | **Created** | `ADMIN_ROLES: frozenset[str] = frozenset({"admin", "owner"})` — extracted from hardcoded strings in `v2/tools.py` and `chat_service.py` |
| `backend/app/api/v2/tools.py` | Modified | `_user_has_scopes` now imports `ADMIN_ROLES` from `app.core.auth_constants` instead of hardcoding `"admin"`, `"owner"` |
| `backend/app/services/chat_service.py` | Modified | (a) `_get_chat_openai_tools` widened with 10 Phase 2 read-only tools. (b) `_execute_tool_call` signature gains `_user_scopes: set[str] \| None` and `_user_role: str \| None`. (c) Scope check replaced: three-branch logic (admin/owner bypass → cached scopes check → defense-in-depth deny). (d) Both `send_message_to_llm` and `stream_message_to_llm` pre-fetch user scopes before the tool loop. |
| `backend/tests/test_tool_registry.py` | Modified | Added `TestExecuteToolCallScopeResolution` — 13 tests covering all branches. Total: 37 tests. |

### Frontend (written to `/home/glenn/FlowmannerV2-frontend/`, NOT committed)

| File | Action | Details |
|------|--------|---------|
| `src/lib/chat-types.ts` | Modified | Added `stepId?: string` to `AgentStep`. Added `SSEEventType` union (14 event types). |
| `src/hooks/useStreaming.ts` | Modified | Added `stepIdToStepIndexRef`, `reasoningAccumulatorRef`. Handlers for `agent_step_start`, `agent_step_end`, `tool_call_delta` (no-op), `reasoning_delta`. Cleanup in `finally`. |
| `src/components/chat/ToolCallCard.tsx` | Modified | Added `Brain` icon. Reasoning steps render as collapsible monospace blocks in expanded body. |
| `src/components/chat/ToolEventContext.tsx` | **Rewritten** | Added `setSourceSteps()` for sidebar unification. `toolEvents` derives from `message.steps[]` via `useMemo` when source steps are set. Falls back to internal state (backwards compat). `filesTouched` tracking unchanged. |
| `src/app/[locale]/(dashboard)/chat/page-client.tsx` | Modified | Wired `setSourceSteps` via `useEffect` watching `store.messages`. Derives sidebar from last assistant message's `steps[]`. |

---

## What was NOT done (deferred to Phase 3+)

| Item | Phase | Notes |
|------|-------|-------|
| `permission_request` SSE event handling | 3 | Frontend handler not yet wired — needs HITL interrupt integration |
| `canvas_update` SSE event handling | 3 | Backend-driven tile orchestration (open_tile) |
| `sandbox_event` SSE event handling | 3 | Sandbox lifecycle in the stream |
| `handoff` SSE event rendering | 3–4 | Agent handoff visualization |
| `citation` SSE event handling | 3 | Already handled for memory_citation; generic citation is separate |
| `tool_call_delta` live preview | 3 | Handler is a no-op hook; will stream partial arguments to ToolCallCard |
| Frontend commit + deploy | now | Frontend has its own git repo at `/home/glenn/FlowmannerV2-frontend/`. Commit separately, then `ship`. |
| `PermissionCard` component | 3 | Approve/deny card targeting real HITL interrupt endpoint |
| `/spawn mission` slash command | 3 | Chat-to-mission spawning |
| framer-motion animation on ToolCallCard | polish | Spec mentioned `motion` for expand/collapse. Currently uses CSS `rotate-180` transition. Works correctly. |

---

## Phase 2 Allowlist Additions (ADR-001)

The `_get_chat_openai_tools` allowlist was widened with these read-only, non-destructive tools:

| Tool ID | Service | Risk | Rationale |
|---------|---------|------|-----------|
| `browser_navigate` | Browser | Read-only | Browse URLs, no side effects |
| `browser_extract` | Browser | Read-only | Extract content from pages |
| `linear_list_issues` | Linear | Read-only | List issues |
| `linear_get_issue` | Linear | Read-only | Get single issue |
| `slack_list_channels` | Slack | Read-only | List channels |
| `slack_read_messages` | Slack | Read-only | Read messages |
| `github_list_repos` | GitHub | Read-only | List repos |
| `github_get_repo` | GitHub | Read-only | Get repo details |
| `github_list_issues` | GitHub | Read-only | List issues |
| `github_list_prs` | GitHub | Read-only | List pull requests |

Write ops (`linear_create_issue`, `slack_post_message`, `github_manager` write ops, `stripe_*`) remain excluded until Phase 3 workspace gating.

---

## Architecture decisions made

1. **Three-branch scope resolution replaces blanket deny.** Phase 1 denied ALL tools with `required_scopes`. Phase 2 checks admin/owner role first, then cached user scopes, then falls back to deny. This enables scoped tools to work for authorized users.

2. **User scopes are pre-fetched once per streaming request.** Both `send_message_to_llm` and `stream_message_to_llm` resolve user scopes from the DB before the tool-calling loop starts. The cached `_user_scopes` and `_user_role` are passed to `_execute_tool_call` on each iteration, avoiding per-tool DB lookups.

3. **`ADMIN_ROLES` is a shared frozenset.** Extracted to `backend/app/core/auth_constants.py` so both `v2/tools.py` and `chat_service.py` use the same constant. Adding a new admin-like role requires changing one place.

4. **`agent_step_start` / `agent_step_end` are paired events.** The frontend tracks `stepId → stepIndex` via `stepIdToStepIndexRef`. `agent_step_start` creates a running step; `agent_step_end` updates it to terminal status. This matches the prototype pattern in `.sisyphus/src/lib/store.ts`.

5. **`reasoning_delta` creates or appends to reasoning steps.** If the last step is a running reasoning step, chunks are appended. Otherwise a new reasoning step is created. This handles both single-block and interleaved reasoning streams.

6. **Sidebar unification via `setSourceSteps()`.** `ToolEventContext` now exposes `setSourceSteps(steps)` which makes `toolEvents` derive from `message.steps[]` via `useMemo`. The `page-client.tsx` wires this by watching `store.messages` and setting the last assistant message's steps as the source. This makes `steps[]` the single source of truth with the sidebar as a read-only projection.

7. **`tool_call_delta` is a no-op hook.** The handler exists but does nothing — it's a hook point for Phase 3 live argument preview in ToolCallCard. The final state comes via `tool_call_result`.

8. **Backwards compat preserved.** `ToolEventContext` still maintains internal `toolEvents` state. When `setSourceSteps` is not called (or called with `[]`), it falls back to the internal state. The `addToolEvent`/`updateToolEvent` API still works for the text-parsing fallback path.

---

## Key files for context

| File | Why it matters |
|------|---------------|
| `backend/app/core/auth_constants.py` | `ADMIN_ROLES` — the shared role constant |
| `backend/app/services/chat_service.py` | `_get_chat_openai_tools` (allowlist) + `_execute_tool_call` (scope resolution) + `stream_message_to_llm` (scope pre-fetch + SSE emitter) |
| `backend/app/api/v2/tools.py` | `_user_has_scopes` (discovery endpoint scope check) |
| `backend/tests/test_tool_registry.py` | 37 tests — Phase 1 (24) + Phase 2 scope resolution (13) |
| `/home/glenn/FlowmannerV2-frontend/src/lib/chat-types.ts` | `SSEEventType` union, `AgentStep.stepId` |
| `/home/glenn/FlowmannerV2-frontend/src/hooks/useStreaming.ts` | SSE event handlers for all Phase 2 event types |
| `/home/glenn/FlowmannerV2-frontend/src/components/chat/ToolCallCard.tsx` | Reasoning rendering in expanded body |
| `/home/glenn/FlowmannerV2-frontend/src/components/chat/ToolEventContext.tsx` | Sidebar unification via `setSourceSteps()` |
| `/home/glenn/FlowmannerV2-frontend/src/app/[locale]/(dashboard)/chat/page-client.tsx` | Wiring: messages → setSourceSteps → sidebar |

---

## Verification steps for next agent

```bash
# 1. Backend — already verified
docker compose exec backend python -m pytest tests/test_tool_registry.py -v
# Expected: 37 passed

# 2. Frontend — already verified (build passes)
cd /home/glenn/FlowmannerV2-frontend
pnpm build

# 3. Commit frontend changes (separate git repo)
cd /home/glenn/FlowmannerV2-frontend
git add src/lib/chat-types.ts src/hooks/useStreaming.ts src/components/chat/ToolCallCard.tsx src/components/chat/ToolEventContext.tsx src/app/\[locale\]/\(dashboard\)/chat/page-client.tsx
git commit -m "feat: Phase 2 — agent step streaming, reasoning rendering, sidebar unification"

# 4. Deploy frontend
ship
# or: bash /opt/flowmanner/deploy-frontend.sh
# ⚠️ Takes ~4 minutes. Use timeout=300.

# 5. Push backend commits
cd /opt/flowmanner
git push origin main

# 6. Manual verification
# Send a chat message that triggers tool calls
# → ToolCallCard should render inline (Phase 1 — backwards compat)
# → Reasoning steps should render as collapsible monospace blocks
# → Sidebar should show the same events as message.steps[]
```

---

## Gotchas

- **Frontend changes are NOT committed.** They live at `/home/glenn/FlowmannerV2-frontend/` which has its own git repo. The frontend has 59 modified files and 8 untracked files (most are from prior work). Only the 5 Phase 2 files listed above should be committed.
- **3 backend commits are unpushed.** Run `git push origin main` from homelab when ready.
- **`tool_call_delta` is intentionally a no-op.** Don't confuse it with `tool_call_result` — the delta is for partial argument streaming (Phase 3), the result is the final state.
- **`reasoning_delta` creates steps on the fly.** If the backend emits `reasoning_delta` events without a preceding `agent_step_start`, a new reasoning step is created automatically. This is intentional — the backend may not always emit paired start/end for reasoning.
- **The `setSourceSteps` `useMemo` depends on a version counter.** `sourceStepsVersion` is incremented on each `setSourceSteps` call to trigger recalculation. This is because `useMemo` can't deep-compare arrays efficiently.
- **Scope pre-fetch uses the same DB session.** It happens before `db.commit()` / `db.close()` in both streaming and non-streaming paths. If the user row doesn't exist (deleted user), the pre-fetch silently fails and scopes default to `None` (defense-in-depth deny).
