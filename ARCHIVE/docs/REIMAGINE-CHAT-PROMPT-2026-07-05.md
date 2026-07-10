# Re-Imagination Prompt: FlowManner Hybrid Chat → Tools → Agents → Sandbox Canvas

**Date:** 2026-07-05
**For:** the agent that will design and implement the new chat surface
**Read first:** `docs/RESEARCH-ROADMAP-HYBRID-PLATFORM-2026-07-05.md` (the deep-dive that produced this prompt), `docs/SITE-AUDIT-CONSOLE-ERRORS-2026-07-05.md`, `docs/SANDBOX-PREVIEW-BLANK-INVESTIGATION.md`.
**Stack reality:** Next.js 15 frontend at `/home/glenn/FlowmannerV2-frontend/` (edit here), FastAPI backend at `/opt/flowmanner/backend/`. Frontend deployed via `bash /opt/flowmanner/deploy-frontend.sh` (4 min). Backend via `deploy-backend.sh` (2 min). WireGuard VPS↔homelab. French-first content. Never claim €0 cost on landing. Never edit files on the VPS directly.

---

## Mission

Re-imagine `/chat` from a single-stream 3-column chat into a **hybrid canvas platform** where chat, tools, agents, and sandboxes are first-class, dockable, streaming surfaces. Do this in phases, with verification at each gate, and never break the existing chat (it's the core user-facing feature).

**You are NOT writing a meta-doc. You are IMPLEMENTING — phase by phase, with diffs, builds, and verification. If you find yourself producing prose instead of patches, stop and re-read this prompt.**

---

## Phase 0 — Stabilize (do this first, before any re-imagination)

The chat surface is currently broken by a React hydration error and a missing marketplace endpoint. Fix these so you have a clean baseline.

### 0.1 Hydration error #419 on `/chat`

**Symptom:** React throws "Minified React error #419" when sending a message. Server/client DOM mismatch. This likely also blocks `SandboxPreviewButton` from mounting, which is why the sandbox preview still appears blank even though the backend forward-auth is confirmed working (200 OK).

**Investigate (do NOT guess):**
1. Run the frontend in dev mode locally: `cd /home/glenn/FlowmannerV2-frontend && NODE_ENV=development pnpm dev` (or `npm run dev`). Load `/chat`, send a message, read the **full** unminified error from the browser console — it names the mismatching component and DOM node.
2. Prime suspects to check against the dev error:
   - `stores/chat-store.ts:127` — `sessionStartTime: Date.now()` in the Zustand initial state. This runs at module init; server render uses one timestamp, client uses another. Fix: move into a `useEffect` that sets `sessionStartTime` after mount, OR read it lazily only when a thread is selected.
   - `components/chat/SandboxPreviewButton.tsx` — escaped-unicode literals (`\u2026`, `\u2014`) in JSX string literals that may render differently through React's SSR escape pipeline vs. the client. Replace with plain characters.
   - `components/chat/MessageList.tsx` — any `new Date()` / `Date.now()` / `Math.random()` / `crypto.randomUUID()` rendered during SSR (timestamps especially).
   - Any `typeof window !== "undefined"` gate that returns different JSX on server vs client first paint.
   - The `useChatStore` access in `ChatLayout.tsx:42-48` that destructures values whose initializers differ server/client.
3. Once you've identified the **exact** mismatching element from the dev error, patch it with the minimal change. Don't refactor surrounding code. Add `suppressHydrationWarning` ONLY where the value is genuinely time-varying and cosmetic (like a timestamp label).
4. **Verify:** `pnpm build` (or `npm run build`) succeeds, then `pnpm dev` no longer throws #419 in the console after sending a message.

### 0.2 Marketplace 404 on `/integrations/browse`

The frontend calls `GET /api/marketplace/listings?type=integration` and `GET /api/marketplace/listings/featured` — neither exists in the v1 router. The v2 marketplace router **does** exist (`backend/app/api/v2/__init__.py` registers a marketplace router).

**Decide and act:**
- **Option A (preferred):** add `GET /api/v2/marketplace/listings` with `?type=` and `?featured=1` query params. Wire to existing `marketplace_service`. Return the v2 envelope (`ok(...)`, `paginated(...)`).
- **Option B (fast fallback):** update the frontend browse page to call an existing endpoint or show a static "coming soon" catalog. Only do this if Option A is genuinely blocked.

Patch the frontend's API client call to hit the v2 endpoint. Verify with `curl` against a local backend container.

### 0.3 Form field ids (accessibility — batch, low effort)

Add `id` and `name` to every `<input>`, `<select>`, `<textarea>` in:
- `components/chat/ChatInputArea.tsx` (3 fields per audit)
- the missions form (1 field)
- the integrations browse page (2 fields)

### 0.4 Phase 0 verification

- Frontend: `pnpm lint && pnpm build` (or `npm run lint && npm run build`) — both must pass.
- Don't deploy yet. Phases accumulate and we deploy once at the end of a coherent set.

---

## Phase 1 — Tool registry + inline tool-call cards

**Goal:** make tools a first-class concept with discoverable schemas, capability-gated execution, and inline rendering in the chat.

### 1.1 Backend tool registry

Create `backend/app/tools/registry.py`:
- A `ToolRegistry` class that loads tools from `app/tools/` + the MCP gateway config (`mcp_gateway/client_config.json`).
- Each tool exposes: `name`, `description`, `input_schema` (JSON Schema — derive from the tool's pydantic/typed args), `required_scopes: list[str]`, `requires_sandbox: bool`, `rate_limit_key: str | None`.
- A `get_permitted_tools(user, workspace)` dependency that returns the tool list the calling user/workspace is authorized to invoke (filter by scopes in `deps.require_scope`).
- Refactor `chat_service._execute_tool_call` to look up tools via the registry and check capability tokens (`CapabilityEngine.issue()` from `substrate/`) before invoking. Keep the existing tool implementations untouched — only the dispatch changes.

### 1.2 Frontend inline tool-call cards

Extend `lib/chat-types.ts`:
```ts
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
export interface ChatMessage {
  // ...existing fields...
  steps?: AgentStep[];   // replaces the side-channel ToolEvent[] for inline rendering
}
```

Update `hooks/useStreaming.ts` so `tool_call_start` / `tool_call_result` SSE events populate `message.steps[]` instead of pushing into the right-sidebar `ToolEventContext`. Keep the right-sidebar feed as a read-only projection of `steps` for backwards compat.

Create `components/chat/ToolCallCard.tsx` — renders inline in `MessageList.tsx` under the assistant message that triggered the call. Collapsible header (tool name + status badge), expandable body (args pretty-printed JSON, result, error, capability token id, duration). Match the existing dark/teal design language in `ChatLayout.tsx`.

### 1.3 Phase 1 verification

- Backend: `docker compose exec backend pytest app/tests/test_chat_service.py -v` (or the closest existing chat test). Add a `test_tool_registry.py` covering: registry loads, scope filtering, capability token issuance.
- Frontend: `pnpm lint && pnpm build`. Add a `ToolCallCard.test.tsx` covering render states.
- Manual: trigger a chat with a web_search tool call — the inline card should appear, stream `running → success`, show the result.

---

## Phase 2 — Agent step streaming (chat + missions unified)

**Goal:** a chat message can spawn a mini-mission; the mission's reasoning, tool calls, and handoffs render inline in the chat as `AgentStep[]`.

### 2.1 Backend: spawn-mission from chat

Add `POST /api/v2/chat/threads/{thread_id}/spawn-mission` that:
- Accepts `{ prompt: string, agent_team?: string, sandbox_required?: bool }`.
- Creates a `Mission` via `_mission_cqrs.commands.create_mission` with `parent_thread_id = thread_id`, source = 'chat'.
- Returns `{ mission_id: str, stream_url: str }` where `stream_url` is `/api/v2/chat/threads/{thread_id}/mission-stream/{mission_id}` — an SSE endpoint that proxies substrate `UnifiedExecutor` events and re-emits them as chat-compatible `tool_call_start`, `tool_call_result`, `agent_step` (new event type), `permission_request` SSE frames.
- Use `substrate` event log as the source of truth (`substrate/H5-1-DESIGN.md`).

### 2.2 Frontend: render agent steps inline

Parse `agent_step` SSE events in `useStreaming.ts` and append to the triggering user message's `steps[]`. Render reasoning steps as collapsible monospace blocks (similar to `ThoughtPanel.tsx` which already exists — promote it from side panel to inline).

Render `permission_request` events as inline cards with **Approve / Deny** buttons that POST to `POST /api/v2/missions/{id}/approve` (already exists in `_mission_cqrs/commands.py`).

### 2.3 Phase 2 verification

- Backend: add `test_spawn_mission_from_chat.py`. Assert mission created with `parent_thread_id`, SSE stream emits at least one `agent_step` event for a trivial mission, `permission_request` fires when a tool with a required scope is invoked without prior grant.
- Frontend: send `/spawn summarize my Q3 repo activity` in chat, watch the agent step tree stream inline, click Approve on the GitHub tool permission card, see the tool call card resolve.
- Run `make lint` and `make test` for backend (scoped to touched `.py` files per AGENTS.md verification rule).

---

## Phase 3 — Canvas v1 (multi-tile surface)

**Goal:** replace the single-stream `MessageList` with a magnetic canvas where chat, code sandbox, browser sandbox, and agent traces are dockable tiles.

### 3.1 Choose the grid framework

Check `frontend/package.json` for an existing grid/dnd library. If none, evaluate:
- `react-grid-layout` ( battle-tested, Resizable + Draggable)
- `@dnd-kit/core` + custom flex (more control, more code)

Pick one. Document the choice in a `docs/CANVAS-DECISION.md` (one-paragraph ADR, not a multi-page report).

### 3.2 Promote `Canvas.tsx`

`components/chat/Canvas.tsx` already exists as a prototype. Promote it to the primary surface in `ChatLayout.tsx`. Tile kinds:
- `chat` — the existing `SSEChat` wrapped as a tile.
- `code-sandbox` — `CodeSandboxPanel.tsx` as a tile (already renders python/js/ts).
- `browser-sandbox` — new tile reusing `SandboxPreviewButton`'s iframe auth.
- `agent-trace` — read-only projection of the active mission's `AgentStep[]` tree.
- `file-diff` — show a git diff (reuse existing file rendering).
- `image-gen` — image generation result tile.

Each tile has: title, kind, payload, state (`live|idle|error`), and a remove/detach control.

### 3.3 Slash commands create / focus tiles

Extend `lib/slash-commands.ts`:
- `/sandbox python` → opens a code-sandbox tile with python preselected.
- `/browse <url>` → opens a browser-sandbox tile and navigates.
- `/trace` → opens an agent-trace tile pinned to the active mission.
- `/close <tile-id>` → removes a tile.

### 3.4 Phase 3 verification

- Frontend: `pnpm lint && pnpm build && ppm test` (add a `Canvas.test.tsx` covering tile add/remove/resize).
- Manual: open chat, run `/sandbox python`, write `print("hello")`, see the result in the same tile. Run `/browse https://example.com` and watch the live preview stream in another tile.

---

## Phase 4 — Browser sandbox tile

**Goal:** an isolated Playwright container with a noVNC iframe preview, dockable in the canvas.

### 4.1 Sandbox image

Build a new sandboxd image variant (extend the existing `sandboxd` Dockerfile pattern) with Playwright + noVNC + a small static file server exposing the noVNC client on a port. The sandboxd preview mechanism already exposes `*.preview.flowmanner.com` — reuse it for the noVNC iframe.

### 4.2 `browser_sandbox` tool

Add `app/tools/browser_sandbox.py`:
- `launch(profile_seed?: str)` — starts a sandboxd container with the browser image, returns `{ sandbox_id, preview_url }`.
- `navigate(url)`, `click(selector)`, `type(selector, text)`, `screenshot()`, `snapshot()` — proxy to Playwright inside the container (the existing `browser_*` tools are the reference; here the calls run inside the sandbox container, not the backend).
- Capability token required (`scope: tool:browser-sandbox`). Per-workspace allowlist.

### 4.3 Frontend tile

The browser-sandbox tile reuses `SandboxPreviewButton`'s `?token=` iframe auth. Inside the tile, the agent's `navigate`/`click`/`type` tool calls render as a thread of `ToolInvocation` cards in the tile's own header; the iframe shows the live browser.

### 4.4 Phase 4 verification

- Backend: `docker compose exec backend pytest app/tests/test_browser_sandbox.py -v` (new). Verify the container launches, preview URL returns 200 with valid token, Playwright commands proxy correctly.
- Frontend: `/browse https://example.com` in chat opens the tile, the page loads in the iframe, agent clicks render as tool-invocation cards in the tile header.

---

## Phase 5 — Permissions + metering for tool calls

**Goal:** every tool call is authorized, scoped, metered, and billable.

### 5.1 Backend

- Add `tool:call` scope to `deps.require_scope`. Every tool route requires it.
- Per-workspace tool allowlist: new `workspace_tool_allowlist` table (workspace_id, tool_name, granted_at, granted_by). Tool registry filters by this.
- `cost_event` row per tool invocation: reuse `cost_tracker.py.record_llm_call` pattern but record tool calls with `event_type='tool_call'`, duration, sandbox_id if applicable.
- `analytics.py` rollup includes tool-call counts and costs.

### 5.2 Frontend

- Workspace settings page: tool allowlist manager (toggle each tool per workspace).
- Inline tool-call card shows the capability token id (small, copyable).
- Blocked tool calls render as a "Request access" CTA card that POSTs a permission request to workspace admins.

### 5.3 Phase 5 verification

- Backend: `test_workspace_tool_allowlist.py`, `test_tool_call_billing.py`.
- Frontend: a workspace without `tool:browser-sandbox` sees the request-access card when the agent tries to browse.

---

## Phase 6 — Evals + prompt versioning

**Goal:** close the loop on agent reliability.

### 6.1 Prompt versions

- New `prompt_versions` table (id, workspace_id, name, content, version, created_at, created_by).
- `ChatSettings.tsx` system prompt field becomes a dropdown of versions + "edit → save new version" flow.
- Agent definitions in `agent_definitions/` get a parallel `prompt_versions` lookup.

### 6.2 Eval runs

- New Celery task `run_eval_suite(eval_suite_id, target="chat_thread"|"agent_id")`.
- `eval_run` table records score per case. Dashboard `reliability` tab visualizes trends.
- Reuse `evaluation/` (LLM-as-judge) + the openclaw-llm-bench harness pattern.

### 6.3 Phase 6 verification

- New tests for `prompt_versions` CRUD and `eval_run` task.
- Dashboard shows at least one eval suite result for the chat tool-calling loop.

---

## Cross-phase rules (read every session)

1. **Always edit at `/home/glenn/FlowmannerV2-frontend/` (frontend) and `/opt/flowmanner/backend/` (backend). Never edit on the VPS.**
2. **Source edits require rebuild.** Don't claim a fix is live until `deploy-frontend.sh` (4 min) or `deploy-backend.sh` (2 min) has run and the health check passes.
3. **Verification scoping:** only run `make test; make lint; make build` when `.py` / `.ts` / `.tsx` files were actually touched. Doc-only changes don't need pytest.
4. **No volume mounts on backend.** Rebuild after every backend code change.
5. **French-first** for any user-facing string in the canvas (chat labels, tool card headers, tile titles). `fr.json` primary, `en.json` translation.
6. **Never paste secrets.** Don't read `.env` or credential files. JWT secret, OAuth client secrets — leave alone.
7. **Don't write meta-docs.** This prompt is the meta-doc. From here on, produce patches and verification output. If a phase is genuinely blocked, write a one-paragraph note in the session exit audit and stop — don't substitute a 5-page analysis for the missing code.
8. **AMEND plans, don't rewrite.** If a phase needs revision (you discover the grid framework is wrong, or a backend route shape changes), patch this prompt file in place with a `### Revision N (date)` block at the bottom of the affected phase. Don't delete prior context.
9. **End-of-session ritual** (`SESSION-RITUAL.md`): exit audit, commit, push. No deploy without human review.
10. **Verify on the host.** `curl` the live endpoint, `docker compose logs backend --tail 50` forbackend errors. Don't trust my own summary of what worked.

---

## Sequencing summary

| Phase | Estimate | Dependencies | Verification gate |
|-------|----------|--------------|--------------------|
| 0 — Stabilize | 1 session | none | `pnpm build` clean, dev mode no #419, marketplace endpoint 200 |
| 1 — Tool registry + inline cards | 2 sessions | 0 done | backend tests pass, inline card renders in chat |
| 2 — Agent step streaming | 2 sessions | 1 done | spawn-mission works end-to-end, agent steps render inline |
| 3 — Canvas v1 | 3 sessions | 2 done | multi-tile canvas works, slash commands open tiles |
| 4 — Browser sandbox tile | 2 sessions | 3 done | isolated Playwright container, noVNC tile, capability-gated |
| 5 — Permissions + metering | 2 sessions | 1 + 4 done | allowlist enforced, blocked tool shows request-access card, costs roll up |
| 6 — Evals + prompt versions | 2 sessions | 2 done | prompt_versions CRUD, first eval suite runs |

Total: ~14 sessions of focused work. Do not attempt to parallelize phases that have dependencies; do parallelize independent files within a phase.

---

## When to stop and ask

- If `/chat` is blank in production after a phase deploy, **immediately** roll back with `deploy-backend.sh --rollback` (backend) or `git revert` + redeploy (frontend) — don't try to patch a broken production chat live.
- If a phase needs a schema migration, write the Alembic migration per `backend/AGENTS.md` — sentinel `UPDATE` over `DELETE` for NOT NULL columns, pre-flight `SELECT COUNT(*)`, human sign-off if > 1000 rows.
- If you're uncertain whether a tool belongs in v1 or v2, default to **v2** (per `app/api/AGENTS.md`).
- If you discover a third audit doc or a new console error during implementation, **add it to `docs/SITE-AUDIT-CONSOLE-ERRORS-2026-07-05.md`** as a new numbered item — don't start a parallel audit file.

---

## Final reminder

**Implement, don't describe.** Every phase above ends with verification output from real commands, not a summary of what would have happened. If you can't get the verification to pass, say so honestly and stop — never invent output.
