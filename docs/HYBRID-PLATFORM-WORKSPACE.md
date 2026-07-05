# Hybrid Platform Workspace — Implementation Kickoff

**Created:** 2026-07-05
**Purpose:** Single reference doc for the next implementation sessions. Synthesizes the research roadmap, re-imagination prompt, codebase audit, and readiness assessment.
**Status:** Ready for Phase 0 (Stabilize)

---

## Quick Links

| Doc | Path | Purpose |
|-----|------|---------|
| Research Roadmap | `docs/RESEARCH-ROADMAP-HYBRID-PLATFORM-2026-07-05.md` | Deep-dive design rationale |
| Re-Imagination Prompt | `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` | Phase-by-phase implementation spec |
| Site Audit | `docs/SITE-AUDIT-CONSOLE-ERRORS-2026-07-05.md` | Console errors + network failures |
| Sandbox Investigation | `docs/SANDBOX-PREVIEW-BLANK-INVESTIGATION.md` | Backend fix deployed, frontend residual |
| This Document | `docs/HYBRID-PLATFORM-WORKSPACE.md` | You are here |

---

## 1. Codebase Readiness Assessment

### 1.1 What Already Exists (surprisingly a lot)

#### Frontend (`/home/glenn/FlowmannerV2-frontend/`)

| Asset | Path | Status | Notes |
|-------|------|--------|-------|
| **Canvas prototype** | `src/components/chat/Canvas.tsx` | Exists | Seed for Phase 3 canvas tiles |
| **ArtifactCard** | `src/components/artifacts/ArtifactCard.tsx` | Exists | Artifact rendering, reusable for tool-call cards |
| **ThoughtPanel** | `src/components/chat/ThoughtPanel.tsx` | Exists | Reasoning display — promote to inline |
| **ToolActivityFeed** | `src/components/chat/ToolActivityFeed.tsx` | Exists | Right sidebar tool feed |
| **ToolEventContext** | `src/components/chat/ToolEventContext.tsx` | Exists | Context provider for streaming tool events |
| **CodeSandboxPanel** | `src/components/chat/CodeSandboxPanel.tsx` | Exists | Code execution panel — becomes canvas tile |
| **SandboxPreviewButton** | `src/components/chat/SandboxPreviewButton.tsx` | Exists | iframe auth via `?token=JWT` — reuse for browser sandbox tile |
| **MemoryCitationChip** | `src/components/chat/MemoryCitationChip.tsx` | Exists | Citation rendering pattern for inline cards |
| **BranchingPanel** | `src/components/chat/BranchingPanel.tsx` | Exists | Thread branching UI |
| **ChatRightSidebar** | `src/components/chat/ChatRightSidebar.tsx` | Exists | Cockpit: tool events, files, branches, milestones |
| **CommandPalette** | `src/components/chat/CommandPalette.tsx` | Exists | Kbar-based command palette |

**Full chat component count: ~44 files** in `src/components/chat/`.

#### Frontend Dependencies (already installed)

| Package | Version | Relevance |
|---------|---------|-----------|
| `@dnd-kit/core` | ^6.3.1 | **Canvas tile drag/resize** — already installed |
| `@dnd-kit/sortable` | ^10.0.0 | **Canvas tile reorder** — already installed |
| `@dnd-kit/utilities` | ^3.2.2 | DnD utilities |
| `motion` | ^12.40.0 | **Animations/transitions** (framer-motion successor) |
| `zustand` | ^5.0.13 | **State management** — already the store layer |
| `@xyflow/react` | (installed) | **Flow diagrams** — agent trace visualization |
| `elkjs` | (installed) | **Graph layout** — for agent step trees |
| `@formkit/auto-animate` | (installed) | Auto-animate lists |
| `socket.io-client` | (installed) | WebSocket client (already available) |
| `react-hook-form` + `zod` | (installed) | Form validation, tool input schemas |
| `@tanstack/react-query` | (installed) | Data fetching |
| `react-markdown` + rehype/remark | (installed) | Markdown rendering |
| `recharts` | (installed) | Charts for eval dashboard |

**Key insight:** No `react-grid-layout` — canvas will use `@dnd-kit` (already installed) with custom flex layout. This is actually better — more control, lighter weight, and already battle-tested in the project.

#### Backend (`/opt/flowmanner/backend/`)

| Asset | Path | Status | Notes |
|-------|------|--------|-------|
| **ToolRegistry** | `app/tools/base.py` | **FULLY IMPLEMENTED** | `register()`, `get()`, `list_all()`, `search()`, `by_tag()`, `to_openai_tools()`, `hydrate_from_db()` — all working |
| **BaseTool + ToolMetadata** | `app/tools/base.py` | **FULLY IMPLEMENTED** | `tool_id`, `name`, `description`, `category`, `input_schema`, `required_scopes`, `rate_limit`, `to_openai_tool()` |
| **Tool execution** | `app/services/chat_service.py` | **WORKING** | `_execute_tool_call()` uses registry, `tool_call_start`/`tool_call_result` SSE events already emitted |
| **SSE streaming** | `app/services/chat_service.py` | **WORKING** | `stream_message_to_llm()` with tool-call delta aggregation, multi-round loop |
| **~110 tool files** | `app/tools/*.py` | Working | Browser, sandbox, data, integrations, LLM-eval |
| **MCP gateway** | `mcp_gateway/client_config.json` | Exists | 3 servers configured (codegraph, filesystem, github) |
| **Marketplace DB** | `app/services/nexus/marketplace_db.py` | **FULLY IMPLEMENTED** | `MarketplaceService` with search, list, categories, reviews |
| **Marketplace seed** | `app/lifespan.py:690` | Working | `_seed_marketplace()` on startup |
| **CapabilityEngine** | `app/services/substrate/` | Exists | `CapabilityEngine.issue()` for authz tokens |
| **HITL models** | `app/models/hitl_models.py` | Exists | Human-in-the-loop approval |
| **CQRS mission commands** | `app/api/v1/missions.py` | Exists | `create_mission`, `approve` patterns |
| **v2 API router** | `app/api/v2/` | 20+ modules | Chat, missions, agents, integrations, dashboard, etc. |
| **Feature flags** | `app/api/v1/feature_flags.py` | Exists | Gate canvas/browser-sandbox behind flags |
| **Cost tracking** | `app/services/cost_tracker.py` | Exists | `cost_event` model for billable events |
| **Auth scopes** | `app/api/deps.py` | Exists | `require_role`, `require_scope`, `require_permission` |

**Key insight:** The `ToolRegistry` is far more complete than the research doc assumed. It already has `hydrate_from_db()`, category/tag indexing, search, composition, and OpenAI/Anthropic/LangChain schema export. Phase 1.1 (backend tool registry) is essentially **done** — we just need to wire it to capability tokens and expose a discovery endpoint.

### 1.2 What Needs Building

| Phase | Backend Work | Frontend Work |
|-------|-------------|---------------|
| **0 — Stabilize** | Marketplace listings endpoint (v2) | Fix hydration #419, form field ids |
| **1 — Tool registry + cards** | Wire capability tokens to tool dispatch, add discovery endpoint | `ToolCallCard.tsx` inline component, extend `chat-types.ts` with `ToolInvocation`/`AgentStep`, update `useStreaming.ts` |
| **2 — Agent step streaming** | `POST /v2/chat/threads/{id}/spawn-mission`, SSE proxy from substrate events | Parse `agent_step` SSE events, inline `ThoughtPanel`, permission request cards |
| **3 — Canvas v1** | None (frontend only) | Promote `Canvas.tsx` to primary, tile system with `@dnd-kit`, slash command extensions |
| **4 — Browser sandbox** | `browser_sandbox` tool, new sandboxd image | Browser sandbox tile with noVNC iframe |
| **5 — Permissions + metering** | `tool:call` scope, workspace allowlist table, cost events per tool call | Allowlist UI, request-access cards |
| **6 — Evals + prompts** | `prompt_versions` table, `eval_run` Celery task | Version dropdown in settings, eval dashboard |

---

## 2. Phase 0 — Stabilize (THE FIRST SESSION)

This is the immediate work. Fix what's broken before building anything new.

### 0.1 React Hydration Error #419

**File:** `/home/glenn/FlowmannerV2-frontend/`

**Approach:**
1. Run `cd /home/glenn/FlowmannerV2-frontend && NODE_ENV=development npx next dev` to get the full unminified error
2. Check `SSEChat.tsx` (725 lines) and `MessageList.tsx` for SSR mismatches — these are the most likely culprits since the error occurs when sending a message

**Prime suspects (ordered by likelihood):**

| Suspect | File | Problem | Fix |
|---------|------|---------|-----|
| `Date.now()` at module init | `stores/chat-store.ts` | SSR timestamp ≠ client timestamp | Move to `useEffect` or lazy init |
| SandboxPreviewButton SSR | `components/chat/SandboxPreviewButton.tsx` | Escaped unicode (`\u2026`) in JSX, auth token fetch in useEffect but Loader2 renders first | Wrap in client-only guard, use literal chars |
| MessageList timestamps | `components/chat/MessageList.tsx` | `new Date()` during SSR | `suppressHydrationWarning` or `useEffect` |
| SSEChat client-only state | `components/chat/SSEChat.tsx` | Various `typeof window` checks producing different JSX | Unify server/client render path |
| ChatLayout store access | `components/chat/ChatLayout.tsx:42-48` | Destructured Zustand values with different initial states | Use `useEffect` for client-only values |

**Verification:** `pnpm build` succeeds, `pnpm dev` no longer throws #419 after sending a message.

### 0.2 Marketplace 404

**Backend:** The `MarketplaceService` already exists at `app/services/nexus/marketplace_db.py` with full CRUD + search + categories. The v2 router (`app/api/v2/__init__.py`) exists. Need to add the missing endpoint.

**Frontend:** `GET /api/marketplace/listings?type=integration` and `GET /api/marketplace/listings/featured` — these hit the v1 path. Either:
- **Option A (preferred):** Add `GET /api/v2/marketplace/listings` with `?type=` and `?featured=1` → wire to existing `MarketplaceService`. Update frontend to hit v2.
- **Option B:** Frontend fallback to static catalog.

### 0.3 Form Field IDs

Batch fix: add `id` and `name` to `<input>`/`<select>`/`<textarea>` in:
- `ChatInputArea.tsx` (3 fields)
- Missions form (1 field)
- Integrations browse (2 fields)

### 0.4 Phase 0 Verification Gate

```
pnpm lint && pnpm build    # Frontend — must pass
curl http://127.0.0.1:8000/api/health  # Backend — must return 200
curl http://127.0.0.1:8000/api/v2/marketplace/listings?type=integration  # Must return 200
```

---

## 3. Architecture Decisions (pre-resolved)

### 3.1 Canvas Grid Framework → `@dnd-kit` (already installed)

**Decision:** Use `@dnd-kit/core` + `@dnd-kit/sortable` with custom flex layout instead of `react-grid-layout`.

**Rationale:**
- Already installed and used elsewhere in the project
- Lighter weight, more control over tile behavior
- `react-grid-layout` would add a new dependency + has React 18/19 compat issues
- Custom flex with `@dnd-kit` handles our resize/drag needs

**Implementation:** Each canvas tile is a `SortableItem` in a `DndContext`. Tiles use CSS `resize: both` + flex-basis for sizing. Snap-to-grid via custom collision detection.

### 3.2 SSE for Streaming, Socket.IO for Control

**Decision:** Keep SSE for token streaming (already working), add Socket.IO for command/control (cancel, pause, inject human input).

**Rationale:**
- `socket.io-client` already installed in frontend
- SSE is unidirectional (server → client) — fine for streaming tokens
- Agent control (cancel/pause/resume/inject) needs client → server messages
- Socket.IO handles reconnection, rooms (per-thread), and binary transport

### 3.3 Tool Registry → Extend existing, don't rebuild

**Decision:** The `ToolRegistry` in `base.py` is already the right foundation. Add:
1. `required_scopes: list[str]` to `ToolMetadata` (partially exists via `requires_auth`)
2. `requires_sandbox: bool` to `ToolMetadata`
3. `rate_limit_key: str | None` to `ToolMetadata`
4. A `get_permitted_tools(user, workspace)` filtering function
5. A `GET /api/v2/tools/discover` endpoint returning the filtered tool list

### 3.4 Chat Message Type Extension

```typescript
// Add to lib/chat-types.ts
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

---

## 4. Session Playbook

### Session 1: Phase 0 — Stabilize

```
1. Run dev mode, capture hydration error → identify exact component
2. Patch the mismatching component (minimal change)
3. Add marketplace endpoint (backend) + update frontend API call
4. Batch fix form field ids
5. pnpm build → passes
6. Deploy frontend (bash deploy-frontend.sh, timeout=300)
7. Verify: chat works, no #419, marketplace loads, no form warnings
```

### Session 2: Phase 1 — Tool Registry + Inline Cards

```
1. Extend ToolMetadata with scopes/sandbox/rate_limit fields
2. Add GET /api/v2/tools/discover endpoint
3. Create ToolCallCard.tsx component
4. Extend chat-types.ts with ToolInvocation + AgentStep
5. Update useStreaming.ts to populate message.steps[] from tool_call_start/result
6. Add ToolCallCard.test.tsx
7. Backend: test_tool_registry.py
8. Verify: trigger a sandboxd tool call, see inline card render
```

### Session 3: Phase 2 — Agent Step Streaming

```
1. Add POST /api/v2/chat/threads/{id}/spawn-mission
2. Add SSE proxy endpoint for mission events → chat-compatible frames
3. Parse agent_step SSE events in useStreaming.ts
4. Render agent steps inline (promote ThoughtPanel)
5. Add permission_request inline cards with Approve/Deny
6. Test: spawn mission from chat, watch steps stream inline
```

### Sessions 4-5: Phase 3 — Canvas v1

```
1. Design tile system (types, state, layout)
2. Promote Canvas.tsx to primary surface in ChatLayout.tsx
3. Implement tile kinds: chat, code-sandbox, browser-sandbox, agent-trace
4. Wire slash commands to create tiles (/sandbox, /browse, /trace)
5. pnpm build + test
```

### Sessions 6-7: Phase 4 — Browser Sandbox

```
1. Build sandboxd image variant with Playwright + noVNC
2. Add browser_sandbox tool (launch, navigate, click, type, screenshot)
3. Frontend: browser-sandbox tile with noVNC iframe + tool cards
4. Test: /browse https://example.com → live preview in tile
```

### Sessions 8-9: Phase 5 — Permissions + Metering

```
1. Add tool:call scope to deps
2. Create workspace_tool_allowlist table (Alembic migration)
3. Wire registry filtering by workspace allowlist
4. cost_event per tool invocation
5. Frontend: workspace settings tool toggle UI
6. Frontend: request-access card for blocked tools
```

### Sessions 10-11: Phase 6 — Evals + Prompt Versioning

```
1. Create prompt_versions table (Alembic migration)
2. Wire ChatSettings.tsx to version dropdown
3. Create eval_run Celery task
4. Dashboard reliability tab with recharts
5. Run first eval suite
```

---

## 5. File Map (files to touch per phase)

### Phase 0 — Stabilize

| File | Action |
|------|--------|
| `frontend/src/stores/chat-store.ts` | Fix `Date.now()` at module init |
| `frontend/src/components/chat/SandboxPreviewButton.tsx` | Fix escaped unicode, client-only guards |
| `frontend/src/components/chat/MessageList.tsx` | Fix SSR timestamp rendering |
| `frontend/src/components/chat/ChatInputArea.tsx` | Add form field ids |
| `backend/app/api/v2/marketplace.py` | **NEW** — listings endpoint |
| `backend/app/api/v2/__init__.py` | Register marketplace router (if not already) |
| `frontend/src/lib/chat-api.ts` | Update marketplace endpoint to v2 |

### Phase 1 — Tool Registry + Inline Cards

| File | Action |
|------|--------|
| `backend/app/tools/base.py` | Extend `ToolMetadata` with `required_scopes`, `requires_sandbox`, `rate_limit_key` |
| `backend/app/api/v2/tools.py` | **NEW** — `GET /api/v2/tools/discover` endpoint |
| `backend/app/api/v2/__init__.py` | Register tools router |
| `backend/tests/test_tool_registry.py` | **NEW** — registry tests |
| `frontend/src/lib/chat-types.ts` | Add `ToolInvocation`, `AgentStep`, extend `ChatMessage` |
| `frontend/src/components/chat/ToolCallCard.tsx` | **NEW** — inline tool-call card |
| `frontend/src/hooks/useStreaming.ts` | Populate `message.steps[]` from tool SSE events |
| `frontend/src/components/chat/ToolCallCard.test.tsx` | **NEW** — component test |

### Phase 2 — Agent Step Streaming

| File | Action |
|------|--------|
| `backend/app/api/v2/chat.py` | Add `POST /threads/{id}/spawn-mission` |
| `backend/app/api/v2/chat.py` | Add `GET /threads/{id}/mission-stream/{mission_id}` SSE proxy |
| `frontend/src/hooks/useStreaming.ts` | Parse `agent_step` events |
| `frontend/src/components/chat/ThoughtPanel.tsx` | Promote to inline rendering |
| `frontend/src/components/chat/PermissionCard.tsx` | **NEW** — approve/deny card |

### Phase 3 — Canvas v1

| File | Action |
|------|--------|
| `frontend/src/components/chat/Canvas.tsx` | Promote to primary surface |
| `frontend/src/components/chat/ChatLayout.tsx` | Replace MessageList with Canvas |
| `frontend/src/stores/chat-store.ts` | Add `canvasTiles[]` slice |
| `frontend/src/lib/chat-types.ts` | Add `CanvasTile` type |
| `frontend/src/lib/slash-commands.ts` | Add `/sandbox`, `/browse`, `/trace`, `/close` |

### Phase 4 — Browser Sandbox

| File | Action |
|------|--------|
| `sandboxd/Dockerfile.browser` | **NEW** — Playwright + noVNC image |
| `backend/app/tools/browser_sandbox.py` | **NEW** — launch, navigate, click, type, screenshot |
| `frontend/src/components/chat/BrowserSandboxTile.tsx` | **NEW** — noVNC iframe tile |

### Phase 5 — Permissions + Metering

| File | Action |
|------|--------|
| `backend/app/models/workspace_models.py` | Add `WorkspaceToolAllowlist` model |
| `backend/alembic/versions/xxx_workspace_tool_allowlist.py` | **NEW** — migration |
| `backend/app/api/deps.py` | Add `tool:call` scope |
| `backend/app/tools/base.py` | Filter tools by workspace allowlist |
| `backend/app/services/cost_tracker.py` | Record tool-call cost events |
| `frontend/src/components/settings/ToolAllowlist.tsx` | **NEW** — toggle UI |

### Phase 6 — Evals + Prompt Versioning

| File | Action |
|------|--------|
| `backend/app/models/prompt_version_models.py` | **NEW** — prompt_versions table |
| `backend/alembic/versions/xxx_prompt_versions.py` | **NEW** — migration |
| `backend/app/tasks/eval_run.py` | **NEW** — Celery task |
| `frontend/src/components/chat/ChatSettings.tsx` | Version dropdown |
| `frontend/src/components/dashboard/ReliabilityTab.tsx` | **NEW** — eval results chart |

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Hydration error is deeper than expected | Medium | Blocks Phase 0 | Run dev mode first, don't guess. If > 3 suspects, isolate by commenting out components |
| Marketplace service schema doesn't match frontend expectations | Low | Delays Phase 0 | Frontend fallback to static catalog |
| `@dnd-kit` can't handle canvas resize well | Low | Delays Phase 3 | Prototype in isolation first; `@xyflow/react` is the fallback |
| Socket.IO conflicts with existing SSE | Low | Delays Phase 2 | Use separate endpoint `/ws/chat/{thread_id}`, don't mix with SSE |
| Existing tool metadata doesn't have scope info | Medium | Delays Phase 1 | Add scopes incrementally — default to `[]` (no restriction) |
| Substrate events can't be proxied to SSE cleanly | Medium | Delays Phase 2 | Use event log as source of truth, translate in proxy |

---

## 7. Open Questions (for Glenn)

1. **Canvas default layout:** Should the chat tile be full-width by default (with tiles opening to the right), or should it start as a 50/50 split? Preference: full-width chat by default, tiles dock to the right or bottom.

2. **Tool permissions UX:** When a tool is blocked, should it show a "Request access" card that notifies workspace admins, or just silently hide the tool from the LLM's available tools?

3. **Browser sandbox priority:** Is the browser sandbox tile (Phase 4) more important than permissions/metering (Phase 5)? The research doc has them in order, but permissions might be higher priority for production safety.

4. **Deployment cadence:** Deploy after each phase, or batch phases 0-2 and deploy once? Recommendation: deploy after Phase 0 (stabilize), then batch 1-2, then batch 3-4, then 5-6.

5. **French-first strings:** All new UI strings go in `fr.json` first. Should we also add English translations in the same PR, or handle that separately?

---

## 8. Useful Commands Reference

```bash
# Frontend dev
cd /home/glenn/FlowmannerV2-frontend
pnpm dev                          # Dev server on :3000
pnpm lint && pnpm build           # Verify before deploy
pnpm test                         # Unit tests (Vitest)

# Frontend deploy (from homelab)
bash /opt/flowmanner/deploy-frontend.sh    # ~4 min, timeout=300

# Backend
cd /opt/flowmanner
docker compose exec backend pytest app/tests/test_chat_service.py -v  # Chat tests
docker compose exec backend alembic upgrade head                       # Run migrations
docker compose exec backend alembic revision --autogenerate -m "desc"  # Create migration
bash /opt/flowmanner/deploy-backend.sh                                 # ~2 min, timeout=300

# Health checks
curl http://127.0.0.1:8000/api/health
ssh -i ~/.ssh/vps_flowmanner_new root@74.208.115.142 "cd /opt/flowmanner && docker compose ps"

# Logs
docker compose logs backend --tail 50
journalctl --user -u flowmanner-dev -f   # Frontend dev server logs
```

---

## 9. Current Blockers

| Blocker | Phase | Status | Owner |
|---------|-------|--------|-------|
| React hydration #419 | 0 | **Needs investigation** — run dev mode to get full error | Frontend |
| Marketplace endpoint 404 | 0 | **Needs implementation** — service exists, endpoint missing | Backend |
| Form field ids | 0 | **Needs batch fix** — 6 fields across 3 pages | Frontend |

**All three are fixable in a single session.** Phase 0 unblocks everything else.
