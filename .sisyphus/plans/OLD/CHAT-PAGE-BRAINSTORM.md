# Chat Page Brainstorm — From LLM Chat to Agentic Interface

**Status:** BRAINSTORM — for Claude Opus review and implementation direction.
**Created:** 2026-06-13
**Author:** Hermes (brainstorm), Glenn (decisions), Claude Opus (review/implementation)
**Preceded by:** `.sisyphus/plans/q2-q3-agentic-workflow.md` (all 6 agentic chunks implemented)

---

## 0. What the Chat Page Is Today

The chat page is a **feature-rich LLM chat with a live-preview sandbox**. It is
the most polished surface in FlowManner, but it operates in a different universe
from the agentic substrate (missions, episodic memory, tool routing, HITL,
self-correction) that the Q2-Q3 work built.

### Current capabilities (evidence from source)

**Frontend** (`frontend/src/components/chat/`):
- 3-column layout: ThreadSidebar (left) | main chat (center) | ChatRightSidebar activity panel (right)
- SSE streaming with 60fps render batching, exponential-backoff retry (3 attempts)
- Tool-event activity feed in the right sidebar (tool_call_start / tool_call_result)
- sandboxd live preview (write files → serve → preview URL)
- Multi-provider LLM support (13 providers: deepseek, zhipuai, llamacpp, openrouter, openai, anthropic, groq, together, fireworks, deepinfra, xai, google, glennguilloux-proxy)
- BYOK (Bring Your Own Key) with per-provider stored-key fallback
- Branching conversations (create branches from any message)
- Attachments: images (10MB), files (20MB), PDFs, drag-and-drop, paste
- Web search injection toggle (SearXNG-backed)
- Slash commands (`/sandbox`, extensible registry)
- Session milestones (positive/negative heuristics)
- Zen mode, command palette (Ctrl+K pattern), keyboard shortcuts
- Mobile companion mode (fallback)
- Voice input
- Manual code sandbox panel (separate from sandboxd)
- Session summary cards, quick stats bar (duration, tokens, tool calls)
- Connecting/idle overlays, topographic background
- Message reactions, edit/delete/regenerate

**Backend** (`backend/app/services/chat_service.py`):
- `stream_message_to_llm()` — SSE streaming with tool-calling loop (up to `_MAX_TOOL_ROUNDS`)
- Tool surface: **sandboxd only** (6 tools: preview, exec, file_write, file_read, file_list, serve)
- Circuit breaker per provider
- Usage/cost tracking → Prometheus metrics + usage service
- Auto title generation after first response

### The central tension

The platform has built a sophisticated agentic execution engine (episodic memory, tool routing, adaptive depth, self-correction, multi-agent handoff, cost attribution, HITL pause/resume, leased execution, replayable event logs). **None of it is reachable from the chat page.** The chat is a stateless LLM call with a sandbox bolted on. The missions page is where agentic work happens. These two worlds do not talk to each other.

---

## 1. The Strategic Question

Should the chat page stay a **conversation-first interface with agentic features**, or should it evolve into the **primary agentic interface** (absorbing mission triggers, HITL, memory, and tool routing)?

This is the most important decision. Everything else flows from it.

**Option A — Conversation-first with agentic escalation:**
Chat stays clean and fast for quick Q&A. When a task needs long-horizon work, the user escalates it to a mission. The chat is the entry point; the mission is the workhorse. The bridge is an "Escalate to Mission" action.

**Option B — Chat becomes the agentic interface:**
The chat absorbs mission capabilities. The agent can plan, pause for HITL, recall episodic memory, choose reasoning depth, and hand off to sub-agents — all visible inline. Missions become a headless/background mode of the chat, not a separate page.

**Option C — Dual-mode:**
A toggle between "Quick Chat" (fast, stateless, current behavior) and "Agent Mode" (plan-then-execute, HITL, memory, cost budget). The user picks per-conversation.

My recommendation is **Option A** for Q3 (lowest risk, clearest scope), with a path toward **Option C** as the agentic substrate matures. The rest of this document develops themes under that assumption, but the proposals can be adapted if Glenn prefers B or C.

---

## 2. Brainstorm Themes

### Theme 1: The chat-to-mission bridge (highest impact)

**Problem:** A user starts a chat, asks a complex question, and the model gives a text answer. If the user wants multi-step agentic work (plan → execute → verify), they have to leave the chat, go to the Missions page, and create a mission from scratch. The chat context is lost.

**Proposal: "Escalate to Mission" action.**
- A button on any user message (or a slash command `/escalate`) that:
  1. Packages the conversation context (messages, files, sandbox state) into a handoff packet.
  2. Creates a mission pre-filled with the conversation as context.
  3. Redirects to the mission page or opens the mission in a side panel.
- The handoff packet uses the existing `HandoffPacket` schema from Chunk 5 (goal, constraints, retrieved context, budget, HITL state).
- The mission planner receives the chat context as seed context, so it doesn't start from scratch.

**Why this matters:** It turns the chat from a dead-end into the natural starting point for agentic work. The user never has to re-explain context.

**Code surface:**
- Frontend: `ChatLayout.tsx`, new `EscalateToMissionButton.tsx`, `chat-store.ts`
- Backend: `chat_service.py` (export thread context), `mission_service.py` (create from chat context)

---

### Theme 2: Expand the tool surface beyond sandboxd

**Problem:** The chat only exposes 6 sandboxd tools. The platform has browser automation (navigate, click, type, scroll, screenshot, snapshot, close), web search (SearXNG), RAG (Qdrant vector retrieval), file operations, code execution, and a tool registry with many more tools. None are available in chat.

**Proposal: Selective tool exposure based on user intent.**
- When the user asks to "search the web", "read this file", "analyze the codebase", "browse this site", the model should have the appropriate tools.
- Use the Q2-Q3 tool router (Chunk 3) to select a small candidate set instead of dumping all tool definitions into context.
- Gate high-risk tools (browser automation, file writes) behind explicit user permission or HITL.

**Proposed tool tiers:**
| Tier | Tools | Default | Permission |
|------|-------|---------|------------|
| Read-only | web_search, rag_search, file_read, browser_snapshot | Enabled | Auto-approve |
| Create | sandboxd_*, code_exec | Enabled | Auto-approve (already sandboxed) |
| Mutating | file_write, browser_click/type, external_api | Disabled | Require explicit enable per session |

**Why this matters:** The chat is the most natural place for tool use. Restricting it to sandboxd is like having a Swiss Army knife but only using the bottle opener.

**Code surface:**
- Backend: `_get_chat_openai_tools()` (currently hardcodes sandboxd IDs), `_execute_tool_call()` (already generic via registry)
- Frontend: `useStreaming.ts` (tool event types need expansion), `ToolEventContext.tsx`

---

### Theme 3: Inline tool execution visualization

**Problem:** Tool calls appear in the right sidebar activity feed, not inline in the conversation. When the model calls sandboxd_file_write, the user sees a line in a sidebar, not the result in context. Compare to Claude/ChatGPT where "Reading file...", "Running code...", "Browsing..." appear inline as collapsible cards.

**Proposal: Inline tool-call cards in the message stream.**
- Render tool calls as inline cards within the assistant message bubble, not just the sidebar:
  ```
  ┌─ 🔧 sandboxd_file_write ─────────────┐
  │ index.html · 2.4 KB · written       │
  │ [diff: +45 -3]  [view file]         │
  └──────────────────────────────────────┘
  ```
- Collapsible: collapsed by default, expandable to see arguments and results.
- Live status: running spinner → success check / error.
- The right sidebar becomes optional/secondary, not the primary tool visualization.

**Why this matters:** Inline cards keep the user's attention in the conversation flow. The sidebar is great for session-level overview, but per-turn tool activity belongs inline.

**Code surface:**
- Frontend: `MessageList.tsx`, new `ToolCallCard.tsx`, `SSEChat.tsx` (pass tool events to message renderer)
- This requires correlating tool events to specific assistant messages (currently tool events are session-scoped, not message-scoped)

---

### Theme 4: Cross-thread episodic memory

**Problem:** Each chat thread is isolated. The chat has no memory of past conversations, user preferences, or ongoing projects. The Q2-Q3 plan built `EpisodicMemoryService` for missions, but the chat doesn't use it.

**Proposal: Episodic memory injection in chat.**
- Before sending the user's message to the LLM, retrieve relevant past episodes (from both chat threads and missions).
- Inject a compact "relevant context" block into the system prompt:
  ```
  [Relevant past context]
  - In a previous conversation about "auth refactor", you discussed using JWT rotation...
  - The user's project uses Next.js 14 with App Router and prefers TypeScript.
  ```
- Source from: past chat threads (semantic search over message content), mission outcomes, user preferences.
- Make it visible to the user (a "context used" indicator) and dismissible.

**Why this matters:** Memory is what separates a tool from an assistant. The user should not have to re-explain their project, stack, or preferences every conversation.

**Code surface:**
- Backend: `chat_service.py` `_build_chat_messages()` (inject memory), `episodic_memory_service.py` (reuse retrieval)
- Frontend: new `MemoryContextIndicator.tsx` in the chat header or input area

---

### Theme 5: Visible agentic reasoning (plan-then-execute)

**Problem:** The chat sends a message and gets a response. There is no visible planning step, no "thinking" display, no opportunity for the user to redirect before the model commits to an approach. The model's reasoning is invisible.

**Proposal: Optional "reasoning" display for complex tasks.**
- When the model decides a task is complex (or the user enables "Agent Mode"), show a visible plan before execution:
  ```
  ┌─ 🧠 Planning ───────────────────────┐
  │ This task requires multiple steps:   │
  │ 1. Search the codebase for auth...   │
  │ 2. Read the relevant files...        │
  │ 3. Propose a refactoring approach... │
  │                                      │
  │ [Approve plan]  [Modify]  [Cancel]   │
  └──────────────────────────────────────┘
  ```
- This is HITL in the chat context — the user approves before the model acts.
- Uses the adaptive reasoning depth (Chunk 4) to decide when to show a plan.
- Optional: show the model's chain-of-thought as a collapsible "thinking" section (like Claude's extended thinking).

**Why this matters:** For simple questions, invisible reasoning is fine. For agentic tasks, the user needs to see and approve the plan. This is the bridge between chat and mission.

**Code surface:**
- Backend: `chat_service.py` (emit plan/thinking SSE events), adaptive depth integration
- Frontend: new `PlanCard.tsx`, `ThinkingDisplay.tsx`

---

### Theme 6: Project/workspace context awareness

**Problem:** The chat doesn't know what project the user is working on. There's no concept of "current project" or "current workspace context." The user has to manually provide context in every message.

**Proposal: @-mention system for context injection.**
- `@file path/to/file` — inject file contents as context
- `@project name` — inject project summary, tech stack, structure
- `@mission id` — inject mission results/context
- `@agent name` — mention a domain agent for specialized response
- `@memory "topic"` — explicitly retrieve episodic memory about a topic
- A context chip bar below the input showing what context is active:
  ```
  [📁 flowmanner-backend] [📄 auth.py] [🧠 auth-refactor-mission]  ✕
  ```

**Why this matters:** Context is the #1 friction point in LLM chat. Making it effortless to inject the right context transforms the experience.

**Code surface:**
- Frontend: `ChatInputArea.tsx` (@-mention autocomplete), new `ContextChipBar.tsx`, `chat-store.ts`
- Backend: context resolution endpoints (file read, project summary, mission export)

---

### Theme 7: Progressive disclosure (reduce chrome overload)

**Problem:** The chat page has a LOT of UI elements: ChatHeader, SessionBreadcrumb, InstrumentPanel, QuickStatsBar, SessionSummaryCard, ChatRightSidebar, FloatingNav, CommandPalette, TopographicBackground. For a simple chat, this is cognitive overload. The "cockpit" aesthetic is impressive but fights usability.

**Proposal: Progressive disclosure with a clean default.**
- **Default (simple chat):** Just the message stream + input. Minimal header (thread title + model selector). Right sidebar collapsed.
- **On-demand (deep work):** Expand to show stats, activity panel, milestones, session summary.
- **Zen mode (already exists):** Already strips everything. Make it the easy default for focused work.
- The InstrumentPanel and SessionBreadcrumb are the main candidates for simplification — they duplicate information available elsewhere.

**Why this matters:** The first impression of the chat page should be "clean conversation," not "aircraft cockpit." Power features should be one click away, not always visible.

**Code surface:**
- Frontend: `ChatLayout.tsx` (conditional rendering, collapse defaults), `chat-store.ts` (layout state)

---

### Theme 8: Inline artifacts (code, documents, diagrams)

**Problem:** sandboxd gives live preview in a separate sandbox. The CodeSandboxPanel is a separate panel. There's no inline rendering of artifacts within the conversation. Compare to Claude's Artifacts or ChatGPT's Canvas — when the model generates code, a document, or a diagram, it renders inline with edit capability.

**Proposal: Inline artifact rendering in the message stream.**
- When the model generates structured content (HTML, SVG, Mermaid diagram, JSON, markdown document), render it inline as an interactive artifact:
  ```
  ┌─ 📄 Artifact: landing-page.html ──────┐
  │ [Preview] [Code] [Split]               │
  │ ┌─────────────────────────────────┐   │
  │ │  [rendered HTML preview]         │   │
  │ └─────────────────────────────────┘   │
  │ [Open in sandbox] [Download] [Fork]   │
  └────────────────────────────────────────┘
  ```
- This is different from sandboxd (which is a full dev environment). Artifacts are lightweight inline renderers for single-file outputs.
- The model can generate an artifact via a structured output convention (fenced code block with a type annotation), no tool call needed.

**Why this matters:** Artifacts make the chat a creative workspace, not just a text exchange. This is what users love about Claude and ChatGPT.

**Code surface:**
- Frontend: `MessageList.tsx` (detect artifact blocks), new `ArtifactRenderer.tsx`, `ArtifactPreview.tsx`
- Backend: none (purely frontend rendering)

---

### Theme 9: Real-time cost awareness and budget controls

**Problem:** QuickStatsBar shows token count but not cost. The backend tracks cost via the usage service, but it's not surfaced in real-time. There's no budget control for chat sessions. The mission system has budget enforcement; the chat doesn't.

**Proposal: Cost display + optional session budget.**
- Show estimated cost per message and cumulative session cost in the QuickStatsBar.
- Optional: let the user set a per-session budget. When the budget is approaching, show a warning. When exhausted, pause the chat and ask for confirmation to continue.
- Reuse the `BudgetEnforcer` from the mission system (Chunk 4/6).

**Why this matters:** Cost is FlowManner's wedge. If the chat doesn't show cost, the platform's biggest differentiator is invisible in its most-used surface.

**Code surface:**
- Backend: `chat_service.py` (emit cost SSE events), reuse `budget_enforcer.py`
- Frontend: `QuickStatsBar.tsx` (add cost), new `SessionBudgetIndicator.tsx`

---

### Theme 10: Streaming reliability and UX

**Problem:** The streaming hook (`useStreaming.ts`) has retry logic, but the UX during retries is a text message ("Connection lost — retrying..."). There's no visible reconnection state, no "stop and retry" button, no graceful degradation.

**Proposals:**
- Visual reconnection indicator (a pulse animation on the header, not text in the message bubble).
- "Resume from last token" — when reconnecting, send the last received token count so the backend can resume.
- Graceful degradation: if streaming fails after all retries, offer to switch to non-streaming mode.
- Token-level undo: if the model hallucinated mid-stream, let the user stop, trim, and regenerate from a specific point.

**Why this matters:** Streaming is the backbone of the chat experience. Small reliability improvements compound into trust.

**Code surface:**
- Frontend: `useStreaming.ts` (reconnection UX), `ConnectingOverlay.tsx` (reuse pattern)

---

### Theme 11: Rich export and sharing

**Problem:** The CommandPalette has `onExportMarkdown` and `onExportJSON` as empty stubs (`() => {}`). The `ShareLink` type exists but sharing is basic. There's no way to export a conversation as a polished document, share a read-only link with formatting, or embed a conversation.

**Proposals:**
- Export to markdown (with tool calls and sandbox links preserved).
- Export to PDF (formatted, with code blocks and artifacts rendered).
- Shareable read-only links (with optional expiry and password protection).
- Embeddable conversation widget (for documentation sites).

**Why this matters:** Conversations are valuable artifacts. Making them shareable extends FlowManner's reach.

**Code surface:**
- Frontend: `CommandPalette.tsx` (wire up export stubs), new export utilities
- Backend: `chat.py` API (export endpoints, share link enhancement)

---

### Theme 12: Conversation search and organization

**Problem:** ThreadSidebar shows conversation threads, but there's no search within or across threads. Folders exist in the type system (`ChatFolder`) but organization is basic. There's no tagging, no full-text search across conversations.

**Proposals:**
- Full-text search across all conversations (use existing FTS or Qdrant).
- Tagging system for threads (manual + auto-suggested from content).
- Smart grouping (by project, by topic, by time).
- "Pinned" conversations for quick access.
- Merge/split conversations.

**Why this matters:** As conversation count grows, discoverability becomes critical.

**Code surface:**
- Frontend: `ThreadSidebar.tsx` (search, tags, grouping), `chat-store.ts`
- Backend: `chat.py` (search endpoints), reuse Qdrant for semantic search

---

## 3. Prioritization Matrix

| Theme | Impact | Effort | Risk | Recommendation |
|-------|--------|--------|------|----------------|
| 1. Chat-to-mission bridge | High | Medium | Low | **Do first** — bridges the two worlds |
| 3. Inline tool visualization | High | Medium | Low | **Do first** — immediate UX win |
| 2. Expand tool surface | High | Medium | Medium | **Do early** — unlocks capability |
| 7. Progressive disclosure | Medium | Low | Low | **Do early** — quick win, no backend |
| 9. Cost awareness | Medium | Low | Low | **Do early** — reinforces wedge |
| 6. @-mention context | High | High | Medium | **Do next** — big UX win but complex |
| 8. Inline artifacts | High | High | Medium | **Do next** — competitive parity |
| 4. Episodic memory | High | Medium | Medium | **Do after** tool surface expands |
| 5. Visible reasoning | Medium | Medium | Medium | **Depends on** Option A/B/C decision |
| 10. Streaming reliability | Medium | Low | Low | **Continuous** — incremental |
| 11. Export/sharing | Low | Low | Low | **When needed** |
| 12. Search/organization | Medium | Medium | Low | **When conversation count grows** |

---

## 4. Proposed Sequencing (Q3 2026)

### Phase 1: Quick wins (1-2 weeks)
- Theme 7: Progressive disclosure — simplify the default layout
- Theme 3: Inline tool-call cards — move tool events into the message stream
- Theme 9: Cost display in QuickStatsBar
- Theme 10: Streaming reliability UX improvements

### Phase 2: The bridge (2-3 weeks)
- Theme 1: Escalate to Mission — package chat context into mission handoff
- Theme 2: Expand tool surface — add read-only tools (search, RAG, file_read) to chat

### Phase 3: Context and memory (3-4 weeks)
- Theme 6: @-mention system for context injection
- Theme 4: Episodic memory injection (reuse mission infrastructure)
- Theme 8: Inline artifacts renderer

### Phase 4: Agentic depth (optional, depends on Option A/B/C)
- Theme 5: Visible reasoning / plan-then-execute
- Deeper HITL integration in chat

---

## 5. What NOT to Build

- **A new chat backend.** The existing SSE streaming + tool-calling loop is solid. Extend it, don't rewrite it.
- **A second agent runtime.** The chat should reuse the mission system's agentic capabilities (memory, routing, depth, HITL), not build parallel versions.
- **A generic chatbot UI.** FlowManner's chat should be opinionated toward agentic work, not a ChatGPT clone. The differentiator is cost-aware, interruptible, tool-rich chat on sovereign infrastructure.
- **More chrome.** The page already has too many panels. Every new feature should be a progressive disclosure candidate, not another always-visible widget.

---

## 6. Key Decisions for Glenn

1. **Option A, B, or C?** (conversation-first with escalation / chat-as-agentic-interface / dual-mode toggle) — This determines the entire direction.

2. **How much tool surface in chat?** Read-only only? Or full mutating tools (browser automation, file writes) with permission gates?

3. **Is the right sidebar worth keeping?** If we move tool events inline (Theme 3), the activity panel may become redundant. Should it be repurposed (project context, memory browser) or removed?

4. **Artifact scope?** Lightweight inline renderers (Theme 8), or keep everything in sandboxd?

5. **Memory visibility?** Should the user see what memory was injected (transparent), or should it be invisible (seamless)?

---

## 7. Technical Notes for Implementation

### Current SSE event types (backend → frontend)
```
type: "token"          — text content delta
type: "complete"       — stream done
type: "error"          — error message
type: "tool_call_start" — tool execution beginning
type: "tool_call_result" — tool execution finished
type: "sandbox.*"      — sandbox lifecycle events
usage: {prompt_tokens, completion_tokens, total_tokens}
```

### Missing SSE events we'd need to add
```
type: "plan"           — model's proposed plan (Theme 5)
type: "thinking"       — chain-of-thought delta (Theme 5)
type: "cost"           — per-turn cost (Theme 9)
type: "memory_used"    — episodic memory retrieval result (Theme 4)
type: "context_resolved" — @-mention resolved context (Theme 6)
type: "artifact"       — structured artifact generated (Theme 8)
type: "hitl_request"   — human-in-the-loop pause (Theme 5)
```

### Current tool registry (available but not exposed in chat)
The backend tool registry (`app/tools/base.py`) has browser tools (navigate, click, type, scroll, screenshot, snapshot, close), and the mission system has file ops, search, RAG, code execution. The chat's `_get_chat_openai_tools()` hardcodes only sandboxd IDs. Expanding this is a one-function change in the backend, but the frontend tool-event renderer needs to handle the new tool types.

### Frontend component count
The chat directory has ~30 components. The main render path is `ChatLayout → SSEChat → MessageList + ChatInputArea`. Tool events flow through `ToolEventContext` to both `ChatRightSidebar` and (with Theme 3) inline cards. The Zustand store (`chat-store.ts`) is the single source of truth for layout/setting state.

---

## Stop Rule

- This is a brainstorm, not a commitment. Glenn picks themes; Opus sequences implementation.
- Do not start any theme without Glenn's direction on Option A/B/C (Section 1).
- Each theme, when selected, should get its own implementation prompt with file-level code surface, like the Q2-Q3 chunk prompts.
- No VPS source edits, no `docker cp`, no raw Docker deploy commands.
