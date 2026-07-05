# EXIT AUDIT — Phase 2: Agent Step Streaming + Sidebar Unification

**Date:** 2026-07-05
**Agent:** Buffy (mimo-v2.5-pro)
**Branch:** main
**Commits:** Backend `3fbf9ea2` (feat), `92aad3dd` (test), `0df2d8b7` (docs) — pushed to origin. Frontend `42771b9` (feat) — committed locally.

---

## WHAT CHANGED (one bullet per file, what + why)

### Backend (committed, image rebuilt, container restarted, pushed to origin)

- **backend/app/core/auth_constants.py**: NEW — extracted `ADMIN_ROLES` frozenset (`admin`, `owner`) from hardcoded strings in `v2/tools.py` and `chat_service.py`
- **backend/app/api/v2/tools.py**: Updated `_user_has_scopes` to import and use `ADMIN_ROLES` constant instead of hardcoded strings
- **backend/app/services/chat_service.py**: (a) Widened allowlist with Phase 2 read-only tools: `browser_navigate`, `browser_extract`, `linear_list_issues`, `linear_get_issue`, `slack_list_channels`, `slack_read_messages`, `github_list_repos`, `github_get_repo`, `github_list_issues`, `github_list_prs`. (b) Three-branch scope resolution in `_execute_tool_call`: admin/owner bypass → cached scopes → deny. (c) Pre-fetch user scopes before tool-calling loop.
- **backend/tests/test_tool_registry.py**: Added 13 tests in `TestExecuteToolCallScopeResolution`. Total: 37 tests. All pass.

### Frontend (committed — `42771b9`)

- **src/lib/chat-types.ts**: Added `stepId?: string` to `AgentStep`. Added `SSEEventType` union (14 event types).
- **src/hooks/useStreaming.ts**: Added `stepIdToStepIndexRef`, `reasoningAccumulatorRef`. Handlers for `agent_step_start`, `agent_step_end`, `tool_call_delta` (no-op), `reasoning_delta`.
- **src/components/chat/ToolCallCard.tsx**: Added `Brain` icon. Reasoning steps render as collapsible monospace blocks.
- **src/components/chat/ToolEventContext.tsx**: REWRITTEN — `setSourceSteps()` for sidebar unification. `toolEvents` derives from `message.steps[]` via `useMemo`.
- **src/app/[locale]/(dashboard)/chat/page-client.tsx**: Wired `setSourceSteps` via `useEffect` watching `store.messages`.

---

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- `backend/app/services/chat_service.py` — `_execute_tool_call` signature changed (added `_user_scopes` and `_user_role`). All callers updated. No API surface change.

---

## TESTS RUN + RESULT

```
docker compose exec backend python -m pytest tests/test_tool_registry.py -v --tb=short
→ 37 passed in 0.28s

cd /home/glenn/FlowmannerV2-frontend && pnpm build
→ Build succeeded

cd /home/glenn/FlowmannerV2-frontend && npx vitest run src/components/chat/ToolCallCard.test.tsx
→ 16 passed
```

---

## STATUS (run these and paste the output, do not paraphrase)

### □ git status (backend)

```
On branch main
Your branch is ahead of 'origin/main' by 1 commit.
  (use "git push" to publish your local commits)
nothing to commit, working tree clean
```

### □ git fetch origin && git log --oneline origin/main..main (backend)

```
235f6968 docs: Canvas ADR — @dnd-kit + custom flex layout decision
```

### □ git log --oneline (frontend — last 3)

```
f660636 feat: Phase 3 — Canvas v1 multi-tile surface with @dnd-kit sortable
42771b9 feat: Phase 2 — agent step streaming, reasoning rendering, sidebar unification
4ae5f41 revert: remove prefillPrompt drive-by from Phase 0 commit
```

### □ docker compose exec backend alembic current

```
20260705_scaffold_rejection_reason (head)
```

### □ curl -s http://127.0.0.1:8000/api/health

```json
{
  "status": "ok",
  "app": "workflows-backend",
  "env": "production",
  "components": {
    "database": {"status": "ok", "message": "PostgreSQL connected", "latency_ms": 1.1},
    "redis": {"status": "ok", "message": "Redis connected", "latency_ms": 0.7},
    "llm_provider": {"status": "healthy", "message": "deepseek/deepseek-v4-flash; API key configured"},
    "langfuse": {"status": "unhealthy", "message": "Langfuse disabled"}
  }
}
```

---

## ACCEPTANCE CRITERIA STATUS

| Criterion | Status |
|-----------|--------|
| `SSEEventType` union includes `agent_step_start`, `agent_step_end`, `tool_call_delta`, `reasoning_delta` | ✅ |
| `useStreaming.ts` handles `agent_step_start`/`agent_step_end` events → populates `steps[]` | ✅ |
| `useStreaming.ts` handles `reasoning_delta` → accumulates reasoning text on the message | ✅ |
| `ToolEventContext` sidebar reads from `message.steps[]` (no duplicate state) | ✅ |
| Reasoning steps render inline with a collapsible card | ✅ |
| Phase 1 `ToolCallCard` still works for tool steps (backwards compat) | ✅ |
| `_get_chat_openai_tools` allowlist widened with documented additions | ✅ |
| `_user_has_scopes` role strings extracted to constants | ✅ |
| `_execute_tool_call` scope check uses cached user scopes (not blanket deny) | ✅ |
| `pnpm build` passes | ✅ |
| Backend tests pass: `pytest tests/test_tool_registry.py -v` | ✅ 37/37 |

---

## NEXT SESSION HANDOFF

Phase 2 is complete and deployed. Frontend committed (`42771b9`). Phase 3 (Canvas v1) is also complete (`f660636`). See `PHASE-3-HANDOFF.md` for the current state.

**Gotchas for future phases:**
- `tool_call_delta` is intentionally a no-op — hook point for Phase 3b live argument preview
- `reasoning_delta` creates steps on the fly without preceding `agent_step_start` — this is intentional
- `setSourceSteps` uses a version counter (`sourceStepsVersion`) to trigger `useMemo` recalculation
- Scope pre-fetch uses the same DB session — happens before `db.commit()` / `db.close()`

---

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

- Untracked files: none (all Phase 2 files committed)
- Deleted files: none
