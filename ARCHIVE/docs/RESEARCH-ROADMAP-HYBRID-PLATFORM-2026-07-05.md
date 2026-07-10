# Research Roadmap: FlowManner as a Hybrid Chat / Tools / Agents / Sandbox Platform

**Date:** 2026-07-05
**Author:** Hermes (z-ai/glm-5.2)
**Status:** Research plan + prompt — not yet implemented
**Companion docs:** `SITE-AUDIT-CONSOLE-ERRORS-2026-07-05.md`, `SANDBOX-PREVIEW-BLANK-INVESTIGATION.md`, `flowmanner_chat_brainstorm.md` (frontend repo)

---

## 0. What this is

A research-first plan to evolve FlowManner from **a chat app with tool calls and a sandbox side-panel** into a **hybrid platform** where chat, tools, agents, and sandboxes are equal first-class surfaces — woven into a single conversation fabric. The deliverable is (a) this roadmap, (b) a re-imagination prompt for the chat page, and (c) triage of the two audit docs that currently block the chat surface.

We are **not** implementing yet. This is the deep-dive + design pass that precedes implementation.

---

## 1. Current state (grounded in the actual codebase)

### 1.1 Frontend chat surface — what exists

Located at `/home/glenn/FlowmannerV2-frontend/src/` (edit here, rsync to VPS):

| File | Role | Relevance to roadmap |
|------|------|-----------------------|
| `app/[locale]/(dashboard)/chat/page-client.tsx` | Orchestrator: thread CRUD, branch CRUD, keyboard. | Entry point for re-imagination. |
| `components/chat/ChatLayout.tsx` (272 lines) | 3-column layout: thread sidebar / message area / right cockpit. Zen mode, mobile, sandbox panel, command palette. | **The page that has to be re-imagined.** |
| `components/chat/SSEChat.tsx` (725 lines) | SSE streaming, slash commands, `/sandbox`, attachments, memory citations, regenerate, reactions. | Core chat engine — tool-call rendering hooks live here. |
| `components/chat/SandboxPreviewButton.tsx` (316 lines) | Fetches sandbox preview, renders authenticated iframe via `?token=JWT`. | **Surface of the blank-preview bug.** |
| `components/chat/CodeSandboxPanel.tsx` | Right-side code execution panel (python/js/ts). | Current sandbox surface — could become a canvas tile. |
| `components/chat/MessageList.tsx` | Markdown, code blocks, branch menu, edit/delete. | Needs tool-call / artifact / agent-step rendering. |
| `components/chat/ChatRightSidebar.tsx` | Cockpit: tool events feed, files touched, branches, milestones. | Becomes the "activity / agent trace" stream. |
| `components/chat/ToolEventContext.tsx` | Context provider for streaming tool events into the right sidebar. | Backbone of agent observability. |
| `components/chat/Canvas.tsx`, `ArtifactCard.tsx`, `ThoughtPanel.tsx` | Partially-built canvas/artifact surfaces (already prototyped). | Seeds of the artifact/canvas model. |
| `stores/chat-store.ts` (222 lines) | Zustand store: threads, messages, settings, sandbox, branches, tool events. | Needs agent-state, tool-permission, canvas-tile slices. |
| `lib/chat-types.ts` (339 lines) | Types: `ChatMessage`, `SSEEvent`, `ToolEvent`, `MemoryCitation`, `BranchInfo`. | Needs `AgentStep`, `ToolCall`, `ToolResult`, `CanvasTile`, `PermissionGrant` types. |
| `lib/sandbox-api.ts` | Sandbox preview/exec API client. | Stays. |
| `hooks/useStreaming.ts` | Tool-call SSE parsing, streaming state. | Needs agent-step / tool-permission event parsing. |
| `lib/slash-commands.ts` | Registry for `/sandbox`, `/mission`, etc. | Stays as a thin shell; tools become the real mechanism. |

### 1.2 Backend — what exists

Located at `/opt/flowmanner/backend/app/`:

**Chat + LLM (`services/chat_service.py`)**
- `send_message_to_llm` — non-streaming, `_execute_tool_call` at line 1375.
- `stream_message_to_llm` (line 1397) — SSE streaming with **tool-call delta aggregation** (`tool_calls_by_index`, `tool_call_start`/`tool_call_result` SSE events).
- `_resolve_provider` + BYOK precedence (`kwargs → stored → platform`).
- 14-provider `PROVIDER_MAP` with fallback chain.
- Tool-calling loop is **partially implemented**: assistant message carries `tool_calls`, results re-injected into history, the loop re-enters streaming. Currently calls `_execute_tool_call` for a fixed internal tool set.

**Tool registry (`app/tools/`)**
- ~110 tool files already. Categories: browser (`browser_navigate.py`, `browser_click.py`, …), sandbox (`sandboxd_exec.py`, `sandboxd_preview.py`, `sandboxd_*.py`), file utils, integrations (`github_manager.py`, `linear_tasks.py`, `slack_communicator.py`, `stripe_operations.py`), data tools, LLM-as-judge (`llm_output_evaluator.py`).
- `base.py` is the tool base class. `integration.py` handles registration. `external.py` is the external-tool adapter.
- No unified tool-discovery/permission layer today — tools are imported directly by `chat_service._execute_tool_call`.

**Sandbox (`services/sandbox_service.py`, `services/mission_code_sandbox.py`, `tools/sandboxd_*.py`)**
- Sandboxd: Docker-based code sandbox with preview URLs on `*.preview.flowmanner.com`.
- Forward-auth chain: Traefik `ForwardAuth` → `/api/sandbox/forward-auth` → JWT validation from `X-Forwarded-Uri` header. **Fixed** (see `SANDBOX-PREVIEW-BLANK-INVESTIGATION.md`).
- `nodejs_sandbox.py`, `python_sandbox.py` — language-specific executors.
- No browser sandbox yet (only `playwright_controller.py` tool, no isolated container).

**Agent system (`app/agent_definitions/`, `app/services/substrate/`, `app/models/agent.py`)**
- 17 domain-agent directories (engineering, marketing, finance, design, …).
- `substrate/` — the **UnifiedExecutor**: `mission_to_workflow()` converts a mission to a workflow, `get_unified_executor().execute()` runs it. Strategies: `DAGStrategy`, `SwarmStrategy`, `GraphStrategy`. This is the autonomous-agent runtime.
- `_mission_cqrs/` — mission lifecycle as CQRS handlers. All v1/v2 mission routes delegate here.
- `langgraph/` — LangGraph-based stateful agent graphs.
- `a2a/` — agent-to-agent handoff.
- `governance/`, `hitl_models.py` — human-in-the-loop approvals.

**Infrastructure already on the homelab**
- PostgreSQL, Redis, Qdrant (vector), RabbitMQ + Celery, llama.cpp (2× RTX 5060 Ti, 32 GB VRAM).
- Traefik for sandbox routing. Nginx on VPS for public TLS.
- OpenTelemetry → Jaeger. Langfuse for LLM observability.

### 1.3 What's broken (the two audit docs)

**`SITE-AUDIT-CONSOLE-ERRORS-2026-07-05.md`** — 3 issues, 2 priority:
1. **🔴 React hydration error #419 on `/chat`** — server/client DOM mismatch when sending a message. Likely cause: `SandboxPreviewButton` or `MessageList` renders client-only state (timestamps, random IDs, `typeof window` checks, `Date.now()`) without SSR guards. The auth token fetch in `SandboxPreviewButton` (line 56-67) runs in `useEffect` but the surrounding component renders `Loader2` on first paint with escaped-unicode strings (`\u2026`) — React's SSR escape handling can mismatch. Also `chat-store.ts` calls `Date.now()` at module init (line 127) which differs server vs client.
2. **🟡 `/integrations/browse` → 404** for `/api/marketplace/listings?type=integration` and `/api/marketplace/listings/featured`. The frontend calls endpoints that don't exist in the v1 router. Either implement them (v2 marketplace already exists in `v2/__init__.py`) or frontend-fallback.
3. **🟢 Form fields missing `id`/`name`** on `/chat` (3), `/missions` (1), `/integrations/browse` (2). Pure accessibility.

**`SANDBOX-PREVIEW-BLANK-INVESTIGATION.md`** — backend fix already deployed:
- Traefik ForwardAuth didn't pass `?token=` → fixed by parsing `X-Forwarded-Uri`.
- Global CSP `frame-ancestors 'none'` blocked the 401 from rendering → exempted forward-auth path.
- **Status:** backend returns 200 OK. **Remaining:** frontend may still blank-render if the iframe `src` is built before `accessToken` arrives (the `authPreviewUrl` only builds when `info.preview_url && accessToken` are both non-null — but the iframe is only mounted in the `expanded && authPreviewUrl` branch, so this is gated). The live residual issue may be (a) sandbox recycled between conversations, (b) the React hydration error in #1 prevents `SandboxPreviewButton` from mounting at all.

These two docs are linked: the hydration error is the most likely reason the sandbox preview still appears blank despite the backend fix. **Fixing #1 is the P0 unblock for the sandbox preview.**

---

## 2. Research tracks (the six from the brief, mapped to FlowManner)

### Track 1 — Architecture patterns

**Study targets:**
- **Vercel AI SDK** (`ai` npm package) — `streamText`, `useChat`, `useCompletion`. Their tool-call rendering and `tool` definition API is the cleanest mental model for "chat → tool → result" UI. We already do this manually in `useStreaming.ts`; studying their `StreamData` + `ToolInvocation` type will tell us what our `SSEEvent` type is missing.
- **LangChain/LangGraph** — already in the backend (`langgraph/`, `langchain/tools/`). Study their `AgentExecutor` loop and how `AgentAction` / `AgentFinish` map to SSE events. Our `substrate/` is essentially a homegrown LangGraph — compare for missing primitives (checkpointing, interrupt/resume, parallel branches).
- **OpenAI Agents SDK** — lightweight, single-file agent loop with handoffs. Maps cleanly to our `a2a/` handoff packets. Study their `Runner` streaming and `Handoff` type.
- **AutoGen** — multi-agent conversation as the unit of work. Compare to our `SwarmOrchestrator` + `swarm_protocol.py` (DebateProtocol, EscalationChain, HandoffProtocol).
- **Microsoft Magentic-One** — orchestrator + workers pattern with a shared scratchpad. Useful for the "agent canvas" idea below.

**FlowManner-specific research questions:**
- How should the existing `substrate.UnifiedExecutor` emit events that the **frontend** can render? Today mission execution lives in Celery + substrate, completely separate from chat. The hybrid platform needs a single event stream that works for both chat-with-tools and full-mission execution.
- WireGuard proxy: today `/api/*` proxies from VPS Nginx → homelab FastAPI. SSE works. WebSockets work (`/ws` → homelab:8000). Question: should long-running agent tasks use WebSockets (bidirectional, faster cancel) or stick with SSE+POST `/cancel`? Vercel AI SDK uses SSE; OpenAI Agents SDK uses WebSocket-like `Runner`. We likely need both: SSE for streaming tokens, WS for command/control (cancel, pause, inject human input, send file).
- CQRS + chat: mission commands already go through `_mission_cqrs/commands.py`. Tool calls inside chat are a different path (`chat_service._execute_tool_call`). Should tool calls inside chat also go through CQRS for auditability? Probably yes — same `wrap_command()` pattern, async tool registry as the handler.

### Track 2 — Chat as the default surface

**State management:**
- Today: Zustand `chat-store.ts` per-thread, persisted settings in `localStorage`. Messages are fetched per-thread on `/api/chat/threads/{id}/messages`.
- Study Vercel AI SDK UI's message types (`Message`, `ToolInvocation`, `StepStart`, `StepEnd`). Our `ChatMessage` lacks an `agentSteps[]` field — agent reasoning, tool invocations, and sub-agent handoffs all collapse into `content`. **Recommendation:** extend `ChatMessage` with `steps: AgentStep[]` where `AgentStep = { type: 'tool'|'reasoning'|'handoff'|'sandbox', name, args, result, status, startedAt, endedAt }`. This unifies what today is split across `ToolEvent[]` (in the right sidebar) and the message body.
- **Branching:** we already have `ChatBranch` (parent_message_id, thread_id, title) and a branching UI in `BranchingPanel` + `ChatRightSidebar`. This is strong — ChatGPT/Claude parity. Study how Cursor's "fork at message" renders the branch switcher.
- **Context windows + token budgeting:** `TokenBar.tsx` + `settings.maxTokens` exists. No automatic context compression or summarization. Research: LangChain `ConversationSummaryMemory`, or our existing `memory_summarization.py` tool. Qdrant already on the stack → long-term memory is solvable. Short-term: a sliding window with a summarization step when context > N tokens.

**RAG / long-term memory:**
- Qdrant + `rag/` + `memory_service` already exist. `MemoryCitation` SSE events already flow into chat (`memory_citation` event → `WhyDrawer`).
- Research: prompt versioning. Today `settings.systemPrompt` is per-thread, no version pinning. Recommendation: store prompts in a `prompt_versions` table with `version_id`, surface in `ChatSettings.tsx` as a dropdown. Same for agent system prompts in `agent_definitions/`.

**Streaming:**
- Study Vercel AI SDK `StreamData` for attaching metadata (tool results, citations, reasoning) alongside tokens. Our `SSEEvent` already carries `tool_name`, `tool_status`, `citations` — extend with `agent_step`, `canvas_update`, `permission_request`.

### Track 3 — Tool system

**MCP first.**
- We already have an MCP gateway config (`backend/mcp_gateway/client_config.json`) with 3 servers (codegraph-ai, filesystem, github). **The hybrid platform should make MCP the canonical tool protocol**, with internal tools wrapped as MCP servers and external MCP servers pluggable per-workspace.
- Study: MCP tool discovery (list_tools), tool schemas (JSON Schema / Zod),OAuth-scoped tool permissions. MCP already supports `resources`, `tools`, `prompts` — map our existing 110 tools to MCP tool definitions. The `tools/base.py` is close to MCP's `Tool` shape.
- **Zod schemas:** frontend uses Zod already (validation throughout). Generate tool input schemas as Zod from the backend OpenAPI/MCP schema, render input forms dynamically in the chat canvas. Vercel AI SDK does this via `tool({ description, parameters: zodSchema, execute })`.

**Tool registry + permissions:**
- Today tools are imported directly inside `chat_service._execute_tool_call`. Recommendation: introduce an explicit **tool registry** (`app/tools/registry.py`) that returns tool metadata (name, description, input schema, required scopes, rate limit, sandbox-required). Routes use `Depends(get_permitted_tools)` so the LLM only sees tools the user's workspace is authorized to call.
- Capability tokens already exist in `substrate/` (`CapabilityEngine.issue()`). Wire these to per-call authz so a chat-instigated tool call carries the same capability model as a mission task. The `governance/` + `hitl_models.py` already model approval — surface approval prompts in chat as `permission_request` SSE events.
- **Dynamic code tools** — research `unsafe-eval` patterns, WASM tool execution (wasmtime-py), and our existing `python_sandbox.py`/`nodejs_sandbox.py` for user-defined tools. A user should be able to define a tool in chat ("whenever I say X, fetch Y and parse Z") and have it added to their workspace registry.

### Track 4 — Agents & orchestration (three levels)

**Level 1 — Assistants (chat + tool calling):**
- Current: `chat_service.stream_message_to_llm` with the openai-style tool_calls loop. This is the Vercel AI SDK pattern. It works. Recommendation: keep this as the default chat mode, but route tool execution through the new registry (Track 3).

**Level 2 — Autonomous agents (planning + loops):**
- Current: `substrate.UnifiedExecutor` with `DAGStrategy`, `SwarmStrategy`. This is LangGraph-equivalent. Already CQRS-delegated. **The hybrid move:** let a chat message spawn a "mini-mission" — `POST /api/v2/chat/threads/{id}/spawn-mission` returns a mission_id, the chat subscribes to its event stream, and the mission's tool calls / reasoning steps render inline in the chat as `AgentStep[]` on the triggering user message.
- Study LangGraph interrupt/resume + checkpointing. Our `substrate/H5-1-DESIGN.md` already introduces an event log as the source of truth — align checkpointing with that.
- HITL: `hitl_models.py` + `governance/` exist. Research how OpenAI Agents SDK's `handoff` and Magentic-One's orchestrator pause for human input. Map to our `permission_request` events rendered inline in chat.

**Level 3 — Multi-agent teams:**
- Current: `SwarmOrchestrator`, `DebateProtocol`, `EscalationChain`, `HandoffProtocol` (all in `services/swarm/`). `a2a/` for handoff packets.
- Study AutoGen's `GroupChat` + `GroupChatManager`. Recommendation: introduce a typed `AgentTeam` config (members, protocol, max_turns, escalation_policy) stored alongside the chat thread; the chat becomes the visible "team room" with per-agent speaking turns rendered as separate sub-messages.
- Observability: `langfuse_*` + OpenTelemetry → Jaeger already on the stack. Study LangSmith's trace tree (parent/child spans for tool calls inside agent steps). Render the same tree in `ChatRightSidebar` as an expandable agent activity trail.

### Track 5 — Sandboxes

**Code sandbox:**
- Current: `sandboxd_*` tools + `sandbox_service.py` + `mission_code_sandbox.py`. Docker-based. Preview URLs work (after the forward-auth fix).
- Study: **E2B** (managed microVMs, fast cold start), **Modal** (serverless containers with file system), **self-hosted Firecracker** (microVM, ~125ms boot). For French-hosted self-contained infra, Firecracker on the homelab is the strongest play; E2B/Modal reduce ops burden but add vendor lock-in.
- Recommendation: keep Docker sandboxd as the default, prototype Firecracker for sub-second multi-tenant cold start, gate behind `feature_flags.py`. The `feature_flags.py` router already exists.

**Browser sandbox:**
- Current: `playwright_controller.py` tool, `browser_*` tools. No isolated container — Playwright runs in the backend container.
- Study: **Browserbase** (managed, anti-detect), **Stagehand** (browserbase + LLM-friendly DOM extraction), **Playwright in isolated containers** (our pattern: spin a sandboxd container with playwright + VNC/noVNC for visual).
- Recommendation: add a `browser_sandbox` tool that launches a dedicated sandboxd container with Playwright + a noVNC iframe preview, exposed via the same `*.preview.flowmanner.com` mechanism. The `SandboxPreviewButton` already does the iframe auth — reuse it.
- Sandbox-to-agent interface: the agent receives screenshots (we have `browser_screenshot.py`), accessibility snapshots (`browser_snapshot.py`), and console output. Already there. Recommendation: stream these back into chat as `canvas_update` SSE events so the user watches the agent browse in real time.

**General secure environment:**
- gVisor / Kata / Wasmtime-WASI for tighter isolation than Docker. Research perf characteristics. For FlowManner's homelab scale, gVisor on the existing Docker host is the pragmatic upgrade; Kata needs nested virt. WASI for CPU-bound pure-compute tools (no syscalls) — wrap user-defined tools (Track 3) in WASI as the least-privilege execution tier.

### Track 6 — Cross-cutting

**Authz:** `require_role`, `require_scope`, `require_permission` already in `deps.py`. Add a `tool:call` scope and per-workspace tool allowlist (managed in v3 workspaces). Render blocked tools with a "request access" CTA in the chat canvas.

**Metering / billing:** `usage.py` + `cost_event.py` + `cost_tracker.py` + `paypal_service`/`subscription_service` exist. Recommendation: model tool calls as billable events (`cost_event` already supports this). Aggregator: `analytics.py` rollups. Tier-aware rate limits: `tier_rate_limit.py` exists — extend to tool calls, not just missions.

**Evals:** `evaluation/` exists (LLM-as-judge). Recommendation: add an `eval_run` Celery task that runs a benchmark suite after cherry-picked chat threads and reports a `reliability` score in the dashboard. `reliability.py` already produces checks. Plug in `openclaw-llm-bench` style suites.

---

## 3. Triage of the two audit docs

### `SITE-AUDIT-CONSOLE-ERRORS-2026-07-05.md`

| # | Issue | Action (this research pass) | Owner |
|---|-------|----------------------------|-------|
| 1 | React hydration #419 on `/chat` | **P0 — investigate root cause.** Suspects: (a) `chat-store.ts:127` `Date.now()` at init, (b) `SandboxPreviewButton` escaped-unicode strings, (c) `MessageList` timestamp rendering during SSR. Run `NODE_ENV=development` next build locally to get the full error; document the exact mismatching component here. | Frontend |
| 2 | `/integrations/browse` 404 | **P1 — decide:** implement `GET /api/v2/marketplace/listings?type=integration` (v2 marketplace already exists) OR frontend fallback to a static catalog. Recommend前者 — the v2 router exists, just need the listings endpoint. | Backend |
| 3 | Form field id/name | **P2 — patch.** Add `id`/`name` to `<input>`/`<textarea>` in `ChatInputArea.tsx`, missions form, integrations browse. Accessibility only. | Frontend |
| 4 | Token refresh 401 | **P2 — UX.** Frontend should treat `/sessions/refresh` 401 as "session expired" → auto-logout CTA, not a console error. | Frontend |

**Concrete next step for #1:** before re-imagining the chat page, fix the hydration error so we have a stable baseline. Likely fix: wrap all client-only state in `useEffect`-gated mounts, use `suppressHydrationWarning` where timestamps are cosmetic, and move `Date.now()` out of the Zustand initial state into a `useEffect` that sets `sessionStartTime` after mount.

### `SANDBOX-PREVIEW-BLANK-INVESTIGATION.md`

The backend chain is fixed and confirmed working (200 OK from forward-auth, valid tokens in logs). The remaining blank-preview is almost certainly downstream of audit issue #1 — if `SandboxPreviewButton` doesn't hydrate, the iframe never mounts. **Plan:**

1. Fix hydration #419 (above). Re-test the preview on a real chat thread with a live sandbox.
2. If still blank after hydration fix: add an `onError`-to-`postMessage` heartbeat from the sandboxed iframe (sandboxd already serves HTML; inject a `<script>` that posts `{type:'previewReady'}` to `parent`). The `SandboxPreviewButton` listens for `message` events → flips `iframeError` to false on timeout. This is independent of CORS/CSP since `postMessage` works across origins.
3. Sandbox recycling: persist `sandbox_id` per chat message (not per thread). On message re-render, if sandbox is recycled, show "Sandbox expired — re-run" CTA instead of blank. Already partially handled in `Known Limitations` of the investigation doc — the frontend should expose this state.

---

## 4. The re-imagination (sketch)

The current chat page is a **3-column single-thread chat**. The re-imagined page is a **canvas-first hybrid surface** where chat is one of several tile types:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Top bar: thread title · model picker · agent/team picker · run/pause     │
├──────────┬─────────────────────────────────────────────┬──────────────────┤
│ Threads  │  Canvas (magnetic, resizable tiles)         │  Agent trace     │
│ Sidebar  │  ┌────────────────────┐ ┌────────────────┐ │  - reasoning     │
│          │  │ Chat (default)     │ │ Code sandbox   │ │  - tool calls    │
│  + New   │  │ streaming          │ │ (python)       │ │  - permissions   │
│  Search  │  │ tool-call cards    │ │ live preview   │ │  - handoffs      │
│  Folders │  │ agent step chips   │ └────────────────┘ │  - cost          │
│          │  └────────────────────┘                     │                  │
│  Pinned  │  ┌────────────────────────────────────────┐ │  Milestones      │
│          │  │ Browser sandbox (noVNC iframe)         │ │  Branches       │
│          │  │ ↑ reuses sandboxd + SandboxPreviewBtn │ │  Files touched  │
│          │  └────────────────────────────────────────┘ │                  │
└──────────┴─────────────────────────────────────────────┴──────────────────┘
```

Key moves:
- **Canvas** replaces the single-stream message list. Already prototyped as `Canvas.tsx` + `ArtifactCard.tsx`. Tiles can be: chat, code sandbox, browser sandbox, agent-reasoning tree, file diff, image gen, mission-status.
- **Tool calls render inline as cards** in the chat tile (collapsible, with the tool name, args form, result, status, authorizing capability token). Today these are hidden in the right sidebar.
- **Agent steps** are sub-chips on the user/assistant message (`reasoning → tool → tool → result → final`). Expandable tree.
- **Permission prompts** appear as inline cards with Approve / Deny — for tools that require HITL.
- **Sandbox preview** is a canvas tile, not a separate panel. Same `?token=` auth, same `SandboxPreviewButton` logic, just dockable.
- **Slash commands** stay (`/sandbox python`, `/spawn mission`, `/team engineering`) — they create new tiles or invoke tools.

---

## 5. Sequencing (what to do, in what order, after this research)

| Phase | Scope | Concrete deliverables |
|-------|-------|------------------------|
| **0. Stabilize** | Fix the two audit docs. | Patch `chat-store.ts:127`, `SandboxPreviewButton`, form ids. Verify against `make lint; make build` (frontend) — scoped to touched `.tsx` per AGENTS.md verification rule. |
| **1. Tool registry v1** | Single source of truth for tools; MCP-first. | `app/tools/registry.py`, capability-token checks in `chat_service._execute_tool_call`, frontend `SSEEvent.tool_call_start/result` rendered as inline cards (extend `ChatMessage.steps[]`). |
| **2. Agent step streaming** | One event stream for chat-with-tools and missions. | Glue `substrate.UnifiedExecutor` events into the chat SSE channel. `POST /api/v2/chat/threads/{id}/spawn-mission`. Render `AgentStep[]` in `MessageList`. |
| **3. Canvas v1** | Multi-tile canvas replaces single message list. | Promote `Canvas.tsx` to primary; chat, code sandbox, sandbox preview, browser sandbox as tile kinds. Drag-to-resize via existing lib (react-grid-layout likely — check frontend deps). |
| **4. Browser sandbox tile** | Isolated Playwright container with noVNC preview. | New `browser_sandbox` tool, new sandboxd image variant, reuse `?token=` forward-auth. |
| **5. Permissions + metering** | Per-workspace tool allowlist + billable tool events. | `tool:call` scope in deps, workspace tool config UI, `cost_event` per tool call, dashboard `reliability` tab. |
| **6. Evals + prompt versioning** | Eval suites for agent reliability. | `prompt_versions` table, `eval_run` Celery task, dashboard eval tab. |

Phases 0–2 are scoped and ready for implementation-planning prompts. Phases 3–6 need design passes of their own.

---

## 6. Open questions to resolve before implementation

1. **Canvas framework** — react-grid-layout vs custom flex; check what's already in `frontend/package.json`.
2. **WebSocket vs SSE for agent control** — keep SSE for tokens, add `/ws/chat/{thread_id}` for cancel/pause/inject? Or fold control into the same SSE with `event: control` typed frames?
3. **Multi-tenant sandbox quotas** — per-workspace concurrent sandbox ceiling; how to surface in billing.
4. **MCP for internal tools** — wrap all 110 existing tools as MCP server definitions, or only the user-facing ones?
5. **Branching UX in canvas mode** — when a tile spawns a branch, where does it go (new canvas tab, side panel, separate thread)?

These are flagged for the implementation-planning prompt, not resolved here.
