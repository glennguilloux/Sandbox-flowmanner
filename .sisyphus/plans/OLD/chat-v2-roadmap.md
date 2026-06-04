# FlowManner Chat System v2 — Full Roadmap Plan

## TL;DR

> **Quick Summary**: Comprehensive upgrade of FlowManner's chat system from a stateless v1 single-player experience to a persistent, performant, collaborative AI workspace. Covers 4 phases: quick wins, core features, advanced features, and moonshots.
> 
> **Deliverables**:
> - Zustand chat store + page-client decomposition
> - Auto-thread titling, message regeneration, reactions
> - Virtual scrolling in MessageList
> - Persistent workspace memory
> - Full-text search across messages
> - Shared threads, export, thread templates
> - Artifacts / code preview rendering
> - Cost tracking + usage dashboard
> - Code execution sandbox
> - Project-level context (repo ingestion → RAG)
> 
> **Estimated Effort**: XL (4-6 weeks total across 4 phases)
> **Parallel Execution**: YES — 4 waves per phase
> **Critical Path**: Phase 1 (foundation) → Phase 2 (core) → Phase 3 (advanced) → Phase 4 (moonshots)

---

## Context

### Original Request
Turn the FlowManner Chat System brainstorm report (`flowmanner_chat_report.md`) into a `.sisyphus/plans/` work plan covering all 4 roadmap phases.

### Interview Summary
**Key Discussions**:
- Chat system is a solid v1 but fundamentally single-player, single-thread, single-model with no memory
- Top 5 priorities: persistent memory, virtual scrolling, artifacts, full-text search, team collaboration
- 4 roadmap phases defined in the brainstorm report with clear deliverables per phase

**Research Findings**:
- **Frontend**: Next.js 16.2.6, React 19.2.4, Zustand 5.0.13 (already installed), 30 chat components
- **Backend**: FastAPI + PostgreSQL + SQLAlchemy, all chat models exist (ChatThread, ChatMessage, ChatFile, ChatBranch)
- **Already installed**: zustand, react-markdown, rehype-highlight, remark-gfm, remark-math, rehype-katex, socket.io-client
- **NOT installed**: react-virtuoso or @tanstack/react-virtual, mermaid, react-diff-viewer
- **State management**: page-client.tsx has 18 useState calls (502 lines), NO Zustand chat store
- **ChatMessage.reactions**: Already a Text field in backend model (currently unused by frontend)
- **ChatThread.metadata_**: JSON field — can store tags, shared_with, cost without migration
- **Backend API**: Full CRUD for threads/messages/files/branches + SSE streaming endpoint exists
- **Deployment**: Frontend source at /home/glenn/FlowmannerV2-frontend/, deployed via rsync to VPS (takes ~4 min)
- **Backend**: No volume mounts — requires Docker rebuild after any code change (~2 min)

---

## Work Objectives

### Core Objective
Transform FlowManner chat from a stateless prompt box into a persistent, performant, collaborative AI workspace with memory, search, and agent integration.

### Concrete Deliverables
- Zustand chat store replacing 18 useState calls in page-client.tsx
- Auto-thread titling via LLM (backend async task)
- Message regeneration, reactions (👍👎🚩💡), keyboard shortcuts
- Virtual scrolling in MessageList for 500+ message support
- Persistent workspace memory (fact triples prepended to system prompt)
- Full-text search across all messages (PostgreSQL tsvector)
- Shared threads with read-only + fork
- Thread templates, export to markdown
- Mermaid diagram, LaTeX math, diff rendering
- Cost tracking + usage dashboard
- Code execution sandbox
- Project-level context (repo → vector DB → RAG)

### Must Have
- All Phase 1 quick wins (auto-titling, regeneration, reactions, keyboard shortcuts)
- Zustand chat store (foundation for all subsequent work)
- Virtual scrolling (prevent crash at 500+ messages)
- Full-text search (most painful omission per report)

### Must NOT Have (Guardrails)
- No big-bang rewrite — all changes incremental
- Do NOT replace SSE with WebSocket for streaming (SSE is fine for unidirectional tokens)
- Do NOT add team chat channels (Phase 4 moonshot, defer)
- Do NOT add voice input or image generation (defer to Phase 4)
- Do NOT change the existing topographic/instrument panel design language
- Do NOT install new CSS frameworks or UI libraries
- Do NOT modify backend chat models without corresponding Alembic migration
- Frontend deploy takes ~4 min — never batch tiny changes; group related work

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (Vitest + Playwright)
- **Automated tests**: Tests-after (add tests for new features, not TDD)
- **Framework**: Vitest for unit, Playwright for E2E

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Frontend/UI**: Use Playwright — Navigate, interact, assert DOM, screenshot
- **API/Backend**: Use Bash (curl) — Send requests, assert status + response fields
- **Library/Module**: Use Bash (bun/node REPL) — Import, call functions, compare output

---

## Execution Strategy

### Phase 1 — Quick Wins (1-2 weeks)

```
Wave 1.1 (Start Immediately — independent quick wins):
├── Task 1: Zustand chat store extraction [deep]
├── Task 2: Auto-thread titling (backend) [quick]
├── Task 3: Message regeneration button [quick]
├── Task 4: Message reactions UI [quick]
└── Task 5: Keyboard shortcut expansion [quick]

Wave 1.2 (After Wave 1.1 — polish):
├── Task 6: Error boundaries per section [quick]
├── Task 7: Typing indicator animation [quick]
└── Task 8: page-client decomposition [deep]

Wave FINAL (After ALL Phase 1 tasks):
└── Task F1: Phase 1 integration QA [unspecified-high]
```

### Phase 2 — Core Features (2-4 weeks)

```
Wave 2.1 (Start Immediately — independent):
├── Task 9: Virtual scrolling in MessageList [deep]
├── Task 10: Optimistic updates for send/edit/delete [deep]
├── Task 11: Export to Markdown (backend + frontend) [quick]
├── Task 12: Thread tagging & starring [quick]
└── Task 13: Mermaid diagram rendering [quick]

Wave 2.2 (After Wave 2.1 — dependent on store):
├── Task 14: LaTeX math rendering [quick]
├── Task 15: Diff rendering for code blocks [quick]
├── Task 16: Thread templates (backend model + API + frontend UI) [unspecified-high]
└── Task 17: SSE render batching + exponential backoff [medium]

Wave FINAL (After ALL Phase 2 tasks):
└── Task F2: Phase 2 integration QA [unspecified-high]
```

### Phase 3 — Advanced Features (1-2 months)

```
Wave 3.1 (Start Immediately — independent):
├── Task 18: Full-text search backend (PostgreSQL tsvector) [deep]
├── Task 19: Full-text search frontend (search modal) [visual-engineering]
├── Task 20: Cost tracking backend (pricing config + aggregation) [unspecified-high]
├── Task 21: Persistent workspace memory backend [deep]
└── Task 22: Shared threads backend (auth + sharing) [unspecified-high]

Wave 3.2 (After Wave 3.1 — dependent on backend):
├── Task 23: Cost tracking frontend (dashboard + charts) [visual-engineering]
├── Task 24: Workspace memory frontend (memory viewer/editor) [visual-engineering]
├── Task 25: Shared threads frontend (share UI + read-only view) [visual-engineering]
├── Task 26: RAG citation chips [medium]
└── Task 27: Context window management (auto-summarize + token bar) [deep]

Wave 3.3 (After Wave 3.2 — integration):
├── Task 28: Agent handoff mid-conversation [deep]
└── Task 29: Mission-from-chat (/mission command) [unspecified-high]

Wave FINAL (After ALL Phase 3 tasks):
└── Task F3: Phase 3 integration QA [unspecified-high]
```

### Phase 4 — Moonshots

```
Wave 4.1 (Start Immediately — independent):
├── Task 30: Code execution sandbox (backend Docker + frontend terminal UI) [deep]
├── Task 31: Project-level context (repo ingestion → vector DB → RAG) [deep]
└── Task 32: Artifacts / live preview (code cards + iframe sandbox) [visual-engineering]

Wave 4.2 (After Wave 4.1):
├── Task 33: Canvas mode (React Flow workspace for artifacts) [visual-engineering]
├── Task 34: Public share links [unspecified-high]
└── Task 35: Thread history pagination [quick]

Wave FINAL (After ALL Phase 4 tasks):
└── Task F4: Phase 4 integration QA [unspecified-high]
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 (Zustand store) | — | 8, 9, 10, 16, 19, 23, 24, 25 |
| 2 (Auto-title) | — | — |
| 3 (Regeneration) | — | — |
| 4 (Reactions) | — | — |
| 5 (Keyboard) | — | — |
| 6 (Error boundaries) | — | — |
| 7 (Typing indicator) | — | — |
| 8 (page-client decompose) | 1 | 9, 10 |
| 9 (Virtual scrolling) | 1, 8 | — |
| 10 (Optimistic updates) | 1, 8 | — |
| 11 (Export) | — | — |
| 12 (Tags/stars) | — | — |
| 13 (Mermaid) | — | — |
| 14 (LaTeX) | — | — |
| 15 (Diff rendering) | — | — |
| 16 (Templates) | 1 | — |
| 17 (SSE batching) | — | — |
| 18 (Search backend) | — | 19 |
| 19 (Search frontend) | 1, 18 | — |
| 20 (Cost backend) | — | 23 |
| 21 (Memory backend) | — | 24 |
| 22 (Shared threads backend) | — | 25 |
| 23 (Cost frontend) | 1, 20 | — |
| 24 (Memory frontend) | 1, 21 | — |
| 25 (Shared threads frontend) | 1, 22 | — |
| 26 (RAG citations) | — | — |
| 27 (Context management) | — | — |
| 28 (Agent handoff) | — | — |
| 29 (Mission-from-chat) | — | — |
| 30 (Code sandbox) | — | — |
| 31 (Project context) | — | — |
| 32 (Artifacts) | — | 33 |
| 33 (Canvas mode) | 32 | — |
| 34 (Public share) | — | — |
| 35 (Pagination) | — | — |

---

## TODOs

### Phase 1 — Quick Wins

- [ ] 1. Zustand Chat Store Extraction

  **What to do**:
  - Create `src/stores/chat-store.ts` with Zustand store containing all chat state currently in page-client.tsx
  - Store shape: `{ activeThreadId, threads, messages, settings, tokenUsage, connectionState, isZenMode, isTyping, branches, sessionStartTime, toolEvents, filesTouched, connectingStage, connectingElapsed, sidebarOpen, rightSidebarOpen, settingsOpen, commandPaletteOpen, isMobile, refreshKey, threadTitle, autoTitleUpdate }`
  - Add actions: `setActiveThread`, `setMessages`, `addMessage`, `updateMessage`, `deleteMessage`, `setSettings`, `setTokenUsage`, `setConnectionState`, `toggleZenMode`, `toggleSidebar`, etc.
  - Refactor `page-client.tsx` to import from `useChatStore` instead of 18 `useState` calls
  - Ensure all child components (SSEChat, ThreadSidebar, ChatRightSidebar) receive props from store or use `useChatStore` directly
  - Preserve all existing behavior — this is a pure refactor with no feature changes

  **Must NOT do**:
  - Do NOT change any UI behavior or styling
  - Do NOT add new features during this refactor
  - Do NOT modify backend code

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1.1 (with Tasks 2, 3, 4, 5)
  - **Blocks**: Tasks 8, 9, 10, 16, 19, 23, 24, 25
  - **Blocked By**: None (can start immediately)

  **References**:
  - `src/app/[locale]/(dashboard)/chat/page-client.tsx:50-70` — All 18 useState calls to extract
  - `src/stores/auth-store.ts` — Existing Zustand store pattern to follow
  - `src/stores/notification-store.ts` — Another Zustand store example
  - `src/lib/chat-types.ts` — All type definitions for store state

  **Acceptance Criteria**:
  - [ ] `src/stores/chat-store.ts` exists and exports `useChatStore`
  - [ ] `page-client.tsx` reduced from 502 lines to ~100-150 lines
  - [ ] Zero `useState` calls remain in page-client.tsx for chat state
  - [ ] All existing functionality preserved (thread switching, settings, zen mode, etc.)
  - [ ] `npm run build` succeeds with no TypeScript errors

  **QA Scenarios**:
  ```
  Scenario: Chat store preserves all existing state
    Tool: Bash (build verification)
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npm run build
      2. Verify exit code 0
      3. Verify no TypeScript errors in output
    Expected Result: Build succeeds with zero errors
    Evidence: .sisyphus/evidence/task-1-build.txt

  Scenario: page-client.tsx is decomposed
    Tool: Bash (line count)
    Steps:
      1. wc -l src/app/[locale]/(dashboard)/chat/page-client.tsx
      2. Assert line count < 200
    Expected Result: page-client.tsx is under 200 lines
    Evidence: .sisyphus/evidence/task-1-decomposition.txt
  ```

  **Commit**: YES (groups with Phase 1)
  - Message: `refactor(chat): extract Zustand store from page-client`
  - Files: `src/stores/chat-store.ts`, `src/app/[locale]/(dashboard)/chat/page-client.tsx`

- [ ] 2. Auto-Thread Titling (Backend)

  **What to do**:
  - Add a new endpoint `POST /api/chat/threads/{id}/auto-title` that takes the first user message + first assistant response and generates a 3-5 word title using a fast/cheap model
  - Backend implementation: after the first assistant response is streamed in `stream_message_to_llm`, trigger an async background task that calls a cheap model (GPT-4o-mini or local llama.cpp) with prompt "Generate a 3-5 word title for this conversation"
  - Store the generated title in `ChatThread.title`
  - Return the new title via the existing WebSocket notification channel (Socket.IO)
  - Frontend: after first exchange, poll or listen for title update and refresh the sidebar

  **Must NOT do**:
  - Do NOT block the streaming response waiting for title generation
  - Do NOT use the user's selected model for title generation (use cheap model only)
  - Do NOT change the existing thread creation flow

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1.1 (with Tasks 1, 3, 4, 5)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `/opt/flowmanner/backend/app/api/v1/chat.py:56` — `generate_thread_title` already exists in chat_service
  - `/opt/flowmanner/backend/app/services/chat_service.py` — Look for `generate_thread_title` implementation
  - `/opt/flowmanner/backend/app/models/chat.py:25-37` — ChatThread model with title field
  - `src/lib/websocket.ts` — Socket.IO client for receiving title updates

  **Acceptance Criteria**:
  - [ ] `POST /api/chat/threads/{id}/auto-title` endpoint exists
  - [ ] Title is generated asynchronously (non-blocking)
  - [ ] ChatThread.title is updated in database
  - [ ] Frontend sidebar updates with new title within 5 seconds
  - [ ] Thread titled "New Chat" is replaced with generated title after first exchange

  **QA Scenarios**:
  - Scenario: Send first message → title auto-generated
  - Scenario: Existing threads with titles are not overwritten

  **Commit**: YES (groups with Phase 1)
  - Message: `feat(chat): auto-thread titling via LLM`
  - Files: Backend chat.py, chat_service.py; Frontend ThreadSidebar.tsx

- [ ] 3. Message Regeneration Button

  **What to do**:
  - Add a "Regenerate" button on the last assistant message in MessageList.tsx
  - Button appears only on the last assistant message when not streaming
  - Clicking it: resends the previous user prompt with the same settings to the backend
  - The regenerated response replaces the previous assistant message (or creates a new one with a `parent_message_id` link)
  - Backend: reuse existing `POST /api/chat/threads/{id}/messages` endpoint (just send the same content again)
  - Frontend: add a `regenerate` action to the Zustand store

  **Must NOT do**:
  - Do NOT create a new backend endpoint (reuse existing message creation)
  - Do NOT allow regeneration mid-stream
  - Do NOT modify the message list ordering

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1.1 (with Tasks 1, 2, 4, 5)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/components/chat/MessageList.tsx:9` — Existing icon imports (RefreshCw already imported)
  - `src/components/chat/MessageList.tsx:40` — REACTIONS array (similar pattern for regenerate button)
  - `src/hooks/useStreaming.ts` — Streaming hook to trigger regeneration
  - `src/lib/chat-types.ts:52-66` — ChatMessage type

  **Acceptance Criteria**:
  - [ ] "Regenerate" button visible on last assistant message
  - [ ] Button hidden during streaming
  - [ ] Click resends previous user prompt
  - [ ] New response appears in message list
  - [ ] Existing messages preserved (regeneration creates new message)

  **QA Scenarios**:
  - Scenario: Click regenerate → previous prompt resent → new response appears
  - Scenario: Button not visible on non-last messages
  - Scenario: Button disabled during streaming

  **Commit**: YES (groups with Phase 1)
  - Message: `feat(chat): message regeneration button`
  - Files: `src/components/chat/MessageList.tsx`, `src/stores/chat-store.ts`

- [ ] 4. Message Reactions UI

  **What to do**:
  - Add hover-to-reveal reaction bar on each message (👍👎🚩💡 — already defined in MessageList.tsx line 40)
  - Backend: `ChatMessage.reactions` field already exists as Text — store as JSON string
  - Frontend: on reaction click, call `POST /api/chat/threads/{id}/react` (endpoint already exists per report)
  - Display reaction counts below messages with active state for user's reactions
  - Add `remove_reaction` endpoint if not exists: `DELETE /api/chat/threads/{id}/react`

  **Must NOT do**:
  - Do NOT change the reactions field type in the database (keep as Text/JSON string)
  - Do NOT add reaction notifications (defer to Phase 3)
  - Do NOT allow custom emoji reactions

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1.1 (with Tasks 1, 2, 3, 5)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/components/chat/MessageList.tsx:40` — `REACTIONS = ["👍", "👎", "🚩", "💡"]` already defined
  - `/opt/flowmanner/backend/app/models/chat.py:54` — `reactions: Mapped[Optional[str]]` already exists
  - `/opt/flowmanner/backend/app/api/v1/chat.py` — Check for existing react endpoint

  **Acceptance Criteria**:
  - [ ] Reaction bar appears on message hover
  - [ ] Clicking a reaction toggles it (add/remove)
  - [ ] Reaction counts displayed below messages
  - [ ] User's own reactions visually distinct
  - [ ] Reactions persisted to backend

  **QA Scenarios**:
  - Scenario: Hover message → reaction bar appears → click 👍 → count increments
  - Scenario: Click same reaction again → count decrements (toggle off)

  **Commit**: YES (groups with Phase 1)
  - Message: `feat(chat): message reactions UI`
  - Files: `src/components/chat/MessageList.tsx`, backend chat.py

- [ ] 5. Keyboard Shortcut Expansion

  **What to do**:
  - Add keyboard shortcuts: ⌘J (focus thread search), ⌘[ / ⌘] (prev/next thread), Escape (close modals/overlays)
  - Add a `?` shortcut to show the existing ShortcutsHelp component
  - Wire shortcuts to Zustand store actions (setActiveThread, toggleSidebar, etc.)
  - Update ShortcutsHelp.tsx to display the new shortcuts
  - Ensure shortcuts don't conflict with browser defaults or existing bindings

  **Must NOT do**:
  - Do NOT add vim-style navigation (nice-to-have, not in Phase 1)
  - Do NOT override browser shortcuts (⌘T, ⌘W, etc.)
  - Do NOT add shortcuts that require modifier keys on mobile

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1.1 (with Tasks 1, 2, 3, 4)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/components/chat/ShortcutsHelp.tsx` — Existing shortcuts help component
  - `src/app/[locale]/(dashboard)/chat/page-client.tsx` — Existing keyboard handler (look for useEffect with keydown)
  - `src/stores/chat-store.ts` — Store actions to wire shortcuts to

  **Acceptance Criteria**:
  - [ ] ⌘J focuses thread search input
  - [ ] ⌘[ navigates to previous thread
  - [ ] ⌘] navigates to next thread
  - [ ] Escape closes any open overlay/modal
  - [ ] `?` shows shortcuts help panel
  - [ ] All shortcuts documented in ShortcutsHelp.tsx

  **QA Scenarios**:
  - Scenario: Press ⌘J → thread search input focused
  - Scenario: Press Escape → open modal closes
  - Scenario: Press `?` → shortcuts help appears

  **Commit**: YES (groups with Phase 1)
  - Message: `feat(chat): keyboard shortcut expansion`
  - Files: ShortcutsHelp.tsx, page-client.tsx or keyboard hook

- [ ] 6. Error Boundaries Per Section

  **What to do**:
  - Wrap ThreadSidebar, SSEChat, and ChatRightSidebar in individual ErrorBoundary components
  - Each boundary has a section-specific fallback UI (not the generic "Something went wrong")
  - SSEChat already has an ErrorBoundary (line 4) — verify it's properly wrapping
  - Add ErrorBoundary around ThreadSidebar with "Sidebar unavailable" fallback
  - Add ErrorBoundary around ChatRightSidebar with "Activity panel unavailable" fallback
  - Use existing `@/components/ErrorBoundary` component

  **Must NOT do**:
  - Do NOT create new ErrorBoundary components (use existing one)
  - Do NOT add error reporting to Sentry (already configured at project level)
  - Do NOT change error recovery behavior (reload button pattern)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1.2 (with Tasks 7, 8)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/components/chat/SSEChat.tsx:4` — `import { ErrorBoundary } from "@/components/ErrorBoundary"` — existing pattern
  - `src/components/chat/SSEChat.tsx:22-56` — MESSAGE_LIST_FALLBACK and CHAT_INPUT_FALLBACK — pattern for section-specific fallbacks
  - `src/app/[locale]/(dashboard)/chat/page-client.tsx` — Where to wrap components

  **Acceptance Criteria**:
  - [ ] ThreadSidebar wrapped in ErrorBoundary with custom fallback
  - [ ] ChatRightSidebar wrapped in ErrorBoundary with custom fallback
  - [ ] SSEChat ErrorBoundary verified working
  - [ ] Each section crash shows only that section's fallback (others unaffected)

  **QA Scenarios**:
  - Scenario: Inject error in ThreadSidebar → only sidebar shows fallback, chat still works
  - Scenario: All three boundaries render correctly in normal operation

  **Commit**: YES (groups with Phase 1)
  - Message: `fix(chat): add error boundaries per section`
  - Files: `page-client.tsx`

- [ ] 7. Typing Indicator Animation

  **What to do**:
  - When `isStreaming` is true and content is empty, show animated dots (`. . .`) pulsing instead of an empty message bubble
  - Add CSS animation for pulsing dots (keyframe animation, opacity 0.3 → 1 → 0.3)
  - Ensure animation works in dark theme (topographic background)
  - Remove animation once content starts streaming

  **Must NOT do**:
  - Do NOT add a typing indicator for the user (only for assistant)
  - Do NOT add sound effects
  - Do NOT change the streaming logic

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1.2 (with Tasks 6, 8)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/components/chat/MessageList.tsx` — Where streaming messages render
  - `src/app/globals.css` — Where to add CSS animation
  - `src/components/chat/SSEChat.tsx` — isStreaming state

  **Acceptance Criteria**:
  - [ ] Animated dots appear when assistant is thinking (streaming, no content yet)
  - [ ] Dots disappear once content starts arriving
  - [ ] Animation is subtle (pulsing opacity, not bouncing)
  - [ ] Works on dark background

  **QA Scenarios**:
  - Scenario: Send message → animated dots appear → content streams → dots disappear
  - Scenario: No animation when not streaming

  **Commit**: YES (groups with Phase 1)
  - Message: `feat(chat): typing indicator animation`
  - Files: MessageList.tsx, globals.css

- [ ] 8. page-client Decomposition

  **What to do**:
  - After Zustand store extraction (Task 1), decompose page-client.tsx into focused components:
    - `ChatLayout` — sidebar + main + right sidebar shell (layout composition only)
    - `ChatKeyboardManager` — keyboard shortcut hook (extract from useEffect)
    - `ChatConnectionManager` — WebSocket/SSE connection lifecycle
  - page-client.tsx becomes a thin orchestrator: ~100-150 lines of layout composition
  - Each extracted component/hook uses `useChatStore` directly (no prop drilling)

  **Must NOT do**:
  - Do NOT change any UI rendering or behavior
  - Do NOT modify the component hierarchy visible to the user
  - Do NOT extract more than 3 components (avoid over-decomposition)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1.2 (with Tasks 6, 7)
  - **Blocks**: Tasks 9, 10
  - **Blocked By**: Task 1 (Zustand store must exist first)

  **References**:
  - `src/app/[locale]/(dashboard)/chat/page-client.tsx:50-70` — State to verify is now in store
  - `src/stores/chat-store.ts` — Store that extracted components will use

  **Acceptance Criteria**:
  - [ ] page-client.tsx is under 150 lines
  - [ ] ChatLayout component exists and handles layout composition
  - [ ] ChatKeyboardManager hook exists and handles shortcuts
  - [ ] ChatConnectionManager hook exists and handles SSE/WebSocket lifecycle
  - [ ] `npm run build` succeeds
  - [ ] All existing functionality preserved

  **QA Scenarios**:
  - Scenario: Build succeeds after decomposition
  - Scenario: All chat features work identically to before

  **Commit**: YES (groups with Phase 1)
  - Message: `refactor(chat): decompose page-client into focused components`
  - Files: page-client.tsx, new component files

### Phase 2 — Core Features

- [ ] 9. Virtual Scrolling in MessageList

  **What to do**:
  - Install `@tanstack/react-virtual` (already have @tanstack/react-query, consistent ecosystem)
  - Replace `messages.map()` in MessageList.tsx with TanStack Virtual
  - Use `useVirtualizer` with `measureElement` for dynamic heights (ReactMarkdown has variable height)
  - Preserve auto-scroll-to-bottom behavior when new messages arrive
  - Preserve scroll-to-bottom button visibility logic
  - Handle streaming: virtualizer should scroll to bottom as new tokens arrive
  - Estimated: 3-5 day refactor with high regression risk

  **Must NOT do**:
  - Do NOT use react-virtuoso (TanStack chosen per architecture decision)
  - Do NOT change message rendering (ReactMarkdown, code blocks, etc.)
  - Do NOT add pagination yet (Task 35 in Phase 4)
  - Do NOT change the message list visual design

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2.1 (with Tasks 10, 11, 12, 13)
  - **Blocks**: None
  - **Blocked By**: Tasks 1, 8 (store + decomposition must be done)

  **References**:
  - `src/components/chat/MessageList.tsx:1-60` — Current imports and structure
  - `src/components/chat/MessageList.tsx` — Full 649-line file to refactor
  - `package.json` — @tanstack/react-query already installed (consistent ecosystem)

  **Acceptance Criteria**:
  - [ ] `@tanstack/react-virtual` installed
  - [ ] MessageList uses `useVirtualizer` instead of `messages.map()`
  - [ ] 500+ messages render without crash or significant performance degradation
  - [ ] Auto-scroll-to-bottom works for new messages during streaming
  - [ ] Scroll position preserved when loading earlier messages (future)
  - [ ] No visual changes to message rendering

  **QA Scenarios**:
  - Scenario: Load thread with 500 messages → smooth scrolling, no crash
  - Scenario: Send message during streaming → auto-scrolls to bottom
  - Scenario: Scroll up → scroll position preserved, no jump

  **Commit**: YES (groups with Phase 2)
  - Message: `perf(chat): add virtual scrolling to MessageList`
  - Files: `src/components/chat/MessageList.tsx`, `package.json`

- [ ] 10. Optimistic Updates for Send/Edit/Delete

  **What to do**:
  - Modify `useChatMessages` hook (or Zustand store actions) to immediately append user messages with `status: "sending"`
  - On server confirmation: update message with real ID and `status: "sent"`
  - On server error: roll back the message, show toast with "retry" action
  - Same pattern for edit: apply edit immediately, roll back on error
  - Same pattern for delete: remove message immediately, show undo toast, restore on error
  - Add `status` field to ChatMessage type: `"sending" | "sent" | "error"`

  **Must NOT do**:
  - Do NOT change the API contract (backend still receives the same requests)
  - Do NOT add offline queue (Phase 4 moonshot)
  - Do NOT change the visual design of sending/error states

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2.1 (with Tasks 9, 11, 12, 13)
  - **Blocks**: None
  - **Blocked By**: Tasks 1, 8

  **References**:
  - `src/hooks/useChatMessages.ts` — Hook to modify
  - `src/stores/chat-store.ts` — Store actions for message operations
  - `src/lib/chat-types.ts:52-66` — ChatMessage type (add status field)

  **Acceptance Criteria**:
  - [ ] User message appears instantly when sent (before server response)
  - [ ] Message shows "sending" indicator while pending
  - [ ] On error: message rolls back + toast with retry
  - [ ] Edit applies immediately, rolls back on error
  - [ ] Delete removes immediately, undo toast restores

  **QA Scenarios**:
  - Scenario: Send message → appears instantly → server confirms → status updates
  - Scenario: Send message → server error → message rolls back → toast appears

  **Commit**: YES (groups with Phase 2)
  - Message: `feat(chat): optimistic updates for send/edit/delete`
  - Files: `src/hooks/useChatMessages.ts`, `src/stores/chat-store.ts`, `src/lib/chat-types.ts`

- [ ] 11. Export to Markdown

  **What to do**:
  - Backend: add `GET /api/chat/threads/{id}/export?format=markdown` endpoint
  - Returns a complete markdown file with proper formatting (headers, code blocks, timestamps)
  - Frontend: add "Export" option to thread context menu in ThreadSidebar
  - Support markdown format first (JSON can be added later)
  - Download as `.md` file with thread title as filename

  **Must NOT do**:
  - Do NOT implement PDF export (defer to Phase 3)
  - Do NOT implement JSON export (can add later)
  - Do NOT add export to individual messages (whole thread only)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2.1 (with Tasks 9, 10, 12, 13)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `/opt/flowmanner/backend/app/api/v1/chat.py` — Add new endpoint
  - `/opt/flowmanner/backend/app/services/chat_service.py` — Export logic
  - `src/components/chat/ThreadSidebar.tsx` — Context menu to add Export option

  **Acceptance Criteria**:
  - [ ] `GET /api/chat/threads/{id}/export?format=markdown` returns markdown
  - [ ] Thread context menu has "Export" option
  - [ ] Downloaded file has correct thread title as filename
  - [ ] Markdown includes all messages with proper formatting

  **QA Scenarios**:
  - Scenario: Click Export → downloads .md file → contains all messages
  - Scenario: Export thread with code blocks → code formatting preserved

  **Commit**: YES (groups with Phase 2)
  - Message: `feat(chat): export thread to markdown`
  - Files: Backend chat.py, ThreadSidebar.tsx

- [ ] 12. Thread Tagging & Starring

  **What to do**:
  - Backend: Add `tags` (Text[], default '{}') and `is_starred` (Boolean, default false) columns to ChatThread via Alembic migration
  - Backend: Add `PATCH /api/chat/threads/{id}` endpoint to update tags, is_starred, title
  - Frontend: "Edit Tags" button in thread context menu with autocomplete from existing workspace tags
  - Frontend: Star icon in sidebar, "Starred" filter group
  - Store tags in `ChatThread.metadata_` JSON field OR add new columns (prefer new columns for queryability)

  **Must NOT do**:
  - Do NOT add tag management UI in settings (keep it inline)
  - Do NOT add tag-based permissions
  - Do NOT auto-tag threads (manual only)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2.1 (with Tasks 9, 10, 11, 13)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `/opt/flowmanner/backend/app/models/chat.py:25-37` — ChatThread model to extend
  - `/opt/flowmanner/backend/alembic/versions/` — Migration directory
  - `src/components/chat/ThreadSidebar.tsx` — Sidebar to add star/tag UI
  - `src/lib/chat-types.ts:40-50` — ChatThread type to extend

  **Acceptance Criteria**:
  - [ ] Alembic migration adds `tags` and `is_starred` columns
  - [ ] `PATCH /api/chat/threads/{id}` updates tags, is_starred
  - [ ] Star icon toggleable in sidebar
  - [ ] "Starred" filter group in sidebar
  - [ ] Tag input with autocomplete in thread context menu

  **QA Scenarios**:
  - Scenario: Star thread → appears in "Starred" group → unstar → disappears
  - Scenario: Add tags "auth" "debug" → filter by "auth" → thread appears

  **Commit**: YES (groups with Phase 2)
  - Message: `feat(chat): thread tagging and starring`
  - Files: Backend model, migration, chat.py; Frontend ThreadSidebar.tsx, chat-types.ts

- [ ] 13. Mermaid Diagram Rendering

  **What to do**:
  - Install `mermaid` package
  - Add a custom `code` component to ReactMarkdown that detects ` ```mermaid` code blocks
  - Render detected Mermaid blocks via `mermaid.render()` into SVG
  - Handle rendering errors gracefully (show code block with error message)
  - Add dark theme support for Mermaid diagrams

  **Must NOT do**:
  - Do NOT add Mermaid editor (render only)
  - Do NOT auto-detect Mermaid in non-code-block content
  - Do NOT add Mermaid to the slash command system yet

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2.1 (with Tasks 9, 10, 11, 12)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/components/chat/MessageList.tsx` — ReactMarkdown custom components
  - `package.json` — remark-gfm already installed (pattern for adding remark plugins)

  **Acceptance Criteria**:
  - [ ] `mermaid` package installed
  - [ ] ` ```mermaid` code blocks render as SVG diagrams
  - [ ] Rendering errors show fallback code block
  - [ ] Dark theme applied to diagrams

  **QA Scenarios**:
  - Scenario: Send message with mermaid code block → renders as diagram
  - Scenario: Invalid mermaid syntax → shows code block with error

  **Commit**: YES (groups with Phase 2)
  - Message: `feat(chat): Mermaid diagram rendering`
  - Files: MessageList.tsx, package.json

- [ ] 14. LaTeX Math Rendering

  **What to do**:
  - Dependencies already installed: `remark-math` (v6) + `rehype-katex` (v7)
  - Add these plugins to ReactMarkdown in MessageList.tsx
  - Support inline math (`$...$`) and block math (`$$...$$`)
  - Add KaTeX CSS for proper rendering
  - Ensure math renders correctly in dark theme

  **Must NOT do**:
  - Do NOT add math editing capabilities
  - Do NOT add LaTeX to slash commands
  - Do NOT change the existing markdown rendering pipeline

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2.2 (with Tasks 15, 16, 17)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `package.json:36` — `remark-math` already installed
  - `package.json:33` — `rehype-katex` already installed
  - `src/components/chat/MessageList.tsx` — ReactMarkdown to add plugins to

  **Acceptance Criteria**:
  - [ ] `$E=mc^2$` renders as inline math
  - [ ] `$$\int_0^1 x dx$$` renders as block math
  - [ ] KaTeX CSS loaded for proper styling
  - [ ] Math renders correctly on dark background

  **QA Scenarios**:
  - Scenario: Send message with inline math → renders formatted
  - Scenario: Send message with block math → renders centered block

  **Commit**: YES (groups with Phase 2)
  - Message: `feat(chat): LaTeX math rendering`
  - Files: MessageList.tsx

- [ ] 15. Diff Rendering for Code Blocks

  **What to do**:
  - Detect code blocks with language "diff" or "patch" in MessageList.tsx
  - Render with +green/-red line highlighting instead of plain monospace
  - Use `react-diff-viewer` or a custom component (lightweight, ~100 lines)
  - Add copy button for diff content
  - Handle unified diff and side-by-side diff formats

  **Must NOT do**:
  - Do NOT install a heavy diff library (keep bundle size small)
  - Do NOT add diff editing capabilities
  - Do NOT auto-detect diffs outside code blocks

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2.2 (with Tasks 14, 16, 17)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/components/chat/MessageList.tsx:45-60` — CodeBlock component to extend
  - `src/components/chat/MessageList.tsx` — ReactMarkdown custom code component

  **Acceptance Criteria**:
  - [ ] ` ```diff` code blocks render with +green/-red highlighting
  - [ ] ` ```patch` code blocks render with diff highlighting
  - [ ] Copy button works for diff content
  - [ ] Regular code blocks unaffected

  **QA Scenarios**:
  - Scenario: Send diff code block → renders with colored lines
  - Scenario: Send regular code block → renders normally (no diff styling)

  **Commit**: YES (groups with Phase 2)
  - Message: `feat(chat): diff rendering for code blocks`
  - Files: MessageList.tsx

- [ ] 16. Thread Templates

  **What to do**:
  - Backend: Create `ChatTemplate` model (id, workspace_id, name, description, system_prompt, model, temperature, max_tokens, created_by, created_at)
  - Backend: Alembic migration for new table
  - Backend: CRUD endpoints — `GET /api/chat/templates`, `POST /api/chat/templates`, `POST /api/chat/templates/{id}/instantiate`
  - Frontend: "Save as Template" from thread settings (captures current system_prompt, model, temperature, max_tokens)
  - Frontend: "New from Template" in thread creation flow (dropdown to select template)
  - Frontend: Template management in workspace settings

  **Must NOT do**:
  - Do NOT share templates across workspaces (workspace-scoped only)
  - Do NOT add template marketplace integration (defer to Phase 3)
  - Do NOT auto-apply templates

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2.2 (with Tasks 14, 15, 17)
  - **Blocks**: None
  - **Blocked By**: Task 1 (Zustand store for settings)

  **References**:
  - `/opt/flowmanner/backend/app/models/` — Model directory for new ChatTemplate
  - `/opt/flowmanner/backend/app/api/v1/chat.py` — Router to add template endpoints
  - `src/components/chat/ChatSettings.tsx` — Settings to add "Save as Template"
  - `src/components/chat/ThreadSidebar.tsx` — Thread creation to add template picker

  **Acceptance Criteria**:
  - [ ] ChatTemplate model exists with correct fields
  - [ ] Alembic migration creates chat_templates table
  - [ ] CRUD endpoints functional
  - [ ] "Save as Template" button in thread settings
  - [ ] "New from Template" option in thread creation
  - [ ] Templates scoped to workspace

  **QA Scenarios**:
  - Scenario: Save thread as template → create new thread from template → settings applied
  - Scenario: List templates → shows workspace templates only

  **Commit**: YES (groups with Phase 2)
  - Message: `feat(chat): thread templates`
  - Files: Backend model, migration, chat.py; Frontend ChatSettings.tsx, ThreadSidebar.tsx

- [ ] 17. SSE Render Batching + Exponential Backoff

  **What to do**:
  - In `useStreaming.ts`, batch token updates at ~60fps using `requestAnimationFrame` instead of calling `updateMessage` on every token
  - This reduces React re-renders by 10-20x during fast streaming
  - Replace fixed 1s/2s retry delays with exponential backoff: `delay = min(1000 * 2^attempt + jitter, 30000)`
  - Add a "Connection lost. Retrying in Xs..." countdown in the UI
  - Add jitter to prevent thundering herd

  **Must NOT do**:
  - Do NOT change the SSE protocol or backend streaming
  - Do NOT add WebSocket for streaming (SSE is fine)
  - Do NOT change the retry maximum (keep reasonable)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2.2 (with Tasks 14, 15, 16)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/hooks/useStreaming.ts` — Streaming hook with retry logic
  - `src/components/chat/SSEChat.tsx` — SSE connection management

  **Acceptance Criteria**:
  - [ ] Token updates batched at ~60fps (requestAnimationFrame)
  - [ ] React re-renders reduced during streaming
  - [ ] Retry uses exponential backoff with jitter
  - [ ] "Connection lost" countdown displayed during retry
  - [ ] Max retry delay capped at 30 seconds

  **QA Scenarios**:
  - Scenario: Fast streaming → smooth rendering, no jank
  - Scenario: Connection drop → exponential retry → reconnection

  **Commit**: YES (groups with Phase 2)
  - Message: `perf(chat): SSE render batching + exponential backoff`
  - Files: `src/hooks/useStreaming.ts`, SSEChat.tsx

### Phase 3 — Advanced Features

- [ ] 18. Full-Text Search Backend (PostgreSQL tsvector)

  **What to do**:
  - Add `content_tsv` tsvector column to ChatMessage model via Alembic migration
  - Create GIN index on `content_tsv` for fast full-text search
  - Add trigger `trg_messages_tsv` to auto-update tsvector on INSERT/UPDATE
  - Add `POST /api/chat/search` endpoint: takes query string + workspace_id, returns ranked message snippets with thread context
  - Use `ts_rank` for relevance ranking
  - Return results with: thread_id, message_id, snippet (highlighted), score, thread_title

  **Must NOT do**:
  - Do NOT use external search services (Elasticsearch, etc.)
  - Do NOT add search to individual threads (global workspace search only)
  - Do NOT add search indexing for attachments (text content only)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3.1 (with Tasks 19, 20, 21, 22)
  - **Blocks**: Task 19
  - **Blocked By**: None

  **References**:
  - `/opt/flowmanner/backend/app/models/chat.py:45-60` — ChatMessage model to extend
  - `/opt/flowmanner/backend/alembic/versions/` — Migration directory
  - Report SQL in brainstorm report lines 451-462 — Exact migration SQL

  **Acceptance Criteria**:
  - [ ] `content_tsv` column exists with GIN index
  - [ ] Trigger auto-updates tsvector on message insert/update
  - [ ] `POST /api/chat/search` returns ranked results
  - [ ] Search is workspace-scoped (only user's workspace messages)
  - [ ] Results include highlighted snippets

  **QA Scenarios**:
  - Scenario: Index message with "NextAuth cookie" → search returns it with highlight
  - Scenario: Search workspace → only returns messages from user's workspace

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): full-text search backend with PostgreSQL tsvector`
  - Files: Backend model, migration, chat.py

- [ ] 19. Full-Text Search Frontend

  **What to do**:
  - Add ⌘⇧F shortcut to open search modal
  - Search modal: text input with instant results (debounced 300ms)
  - Results display: thread title, message snippet with highlighted matches, timestamp
  - Click result → navigate to thread and scroll to message
  - Search results grouped by thread
  - Empty state: "No results found"

  **Must NOT do**:
  - Do NOT add search filters (date range, model, etc.) — keep simple
  - Do NOT add search history
  - Do NOT add search suggestions

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3.2 (with Tasks 23, 24, 25, 26, 27)
  - **Blocks**: None
  - **Blocked By**: Tasks 1, 18 (store + backend search)

  **References**:
  - `src/components/chat/CommandPalette.tsx` — Modal pattern to follow
  - `src/stores/chat-store.ts` — Store for search state
  - Backend `POST /api/chat/search` — API to call

  **Acceptance Criteria**:
  - [ ] ⌘⇧F opens search modal
  - [ ] Instant results with 300ms debounce
  - [ ] Results show thread title + highlighted snippet
  - [ ] Click result navigates to thread + scrolls to message
  - [ ] Empty state for no results

  **QA Scenarios**:
  - Scenario: Press ⌘⇧F → type "auth" → results appear → click → navigates to thread
  - Scenario: Search for nonexistent term → "No results found"

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): full-text search modal`
  - Files: New SearchModal.tsx, ThreadSidebar.tsx, chat-store.ts

- [ ] 20. Cost Tracking Backend

  **What to do**:
  - Create a pricing config (JSON file or database table) mapping model IDs to input/output prices per token
  - After each streaming response, compute cost = (prompt_tokens × input_price) + (completion_tokens × output_price)
  - Add `total_cost` field to ChatThread (Float, default 0.0)
  - Add `cost` field to ChatMessage (Float, default 0.0)
  - Alembic migration for new columns
  - Add `GET /api/chat/usage?period=7d|30d|90d` endpoint: returns total_tokens, total_cost, by_model, by_thread

  **Must NOT do**:
  - Do NOT add payment processing
  - Do NOT add cost alerts/limits (defer to Phase 3)
  - Do NOT require BYOK users to input pricing (use defaults)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3.1 (with Tasks 18, 19, 21, 22)
  - **Blocks**: Task 23
  - **Blocked By**: None

  **References**:
  - `/opt/flowmanner/backend/app/models/chat.py:25-37` — ChatThread model
  - `/opt/flowmanner/backend/app/services/chat_service.py` — Where to add cost computation
  - Report lines 391-392 — Usage endpoint spec

  **Acceptance Criteria**:
  - [ ] Pricing config exists for all supported models
  - [ ] Cost computed per response and stored in ChatMessage
  - [ ] total_cost accumulated in ChatThread
  - [ ] `GET /api/chat/usage` returns aggregated stats
  - [ ] Migration adds cost columns

  **QA Scenarios**:
  - Scenario: Send message using DeepSeek → cost computed and stored
  - Scenario: GET /usage?period=7d → returns correct aggregation

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): cost tracking backend`
  - Files: Backend model, migration, chat_service.py, chat.py

- [ ] 21. Persistent Workspace Memory Backend

  **What to do**:
  - Create `WorkspaceMemory` model (id, workspace_id, subject, predicate, object, confidence, source_thread_id, source_message_id, created_at, updated_at)
  - Alembic migration for new table
  - CRUD endpoints: `GET /api/chat/memory`, `POST /api/chat/memory`, `DELETE /api/chat/memory/{id}`
  - On every new message, backend prepends top-K relevant memories to the system prompt
  - Retrieval: keyword matching initially (Phase 3), embedding similarity later (Phase 4)
  - Users can view/edit/delete memories in settings

  **Must NOT do**:
  - Do NOT use vector embeddings yet (Phase 4 moonshot)
  - Do NOT auto-extract memories from conversations (manual only for now)
  - Do NOT share memories across workspaces

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3.1 (with Tasks 18, 19, 20, 22)
  - **Blocks**: Task 24
  - **Blocked By**: None

  **References**:
  - Report lines 409-420 — WorkspaceMemory model spec
  - `/opt/flowmanner/backend/app/models/` — Model directory
  - `/opt/flowmanner/backend/app/services/chat_service.py` — Where to inject memories into system prompt

  **Acceptance Criteria**:
  - [ ] WorkspaceMemory model exists with correct fields
  - [ ] Alembic migration creates workspace_memories table
  - [ ] CRUD endpoints functional
  - [ ] Memories prepended to system prompt on new messages
  - [ ] Memories scoped to workspace

  **QA Scenarios**:
  - Scenario: Add memory "Glenn prefers TypeScript strict" → next chat includes it in context
  - Scenario: Delete memory → no longer in system prompt

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): persistent workspace memory backend`
  - Files: Backend model, migration, chat_service.py, chat.py

- [ ] 22. Shared Threads Backend

  **What to do**:
  - Add `shared_with` field to ChatThread (JSON array of user IDs, default '[]')
  - Backend auth check: thread owner + shared users can read, only owner can write
  - Add `POST /api/chat/threads/{id}/share` endpoint: adds user_id to shared_with
  - Add `DELETE /api/chat/threads/{id}/share` endpoint: removes user_id from shared_with
  - Add `SharedLink` model for public share links (thread_id, token, expires_at, is_active)
  - Add `POST /api/chat/threads/{id}/share/link` endpoint: creates public share link
  - Alembic migration for new columns and table

  **Must NOT do**:
  - Do NOT add real-time collaborative editing (Phase 4)
  - Do NOT add WebSocket presence for shared threads (Phase 4)
  - Do NOT add permission levels (read-only vs read-write)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3.1 (with Tasks 18, 19, 20, 21)
  - **Blocks**: Task 25
  - **Blocked By**: None

  **References**:
  - Report lines 433-440 — SharedLink model spec
  - `/opt/flowmanner/backend/app/models/chat.py` — ChatThread model
  - `/opt/flowmanner/backend/app/api/v1/chat.py` — Router to add endpoints

  **Acceptance Criteria**:
  - [ ] shared_with field on ChatThread
  - [ ] Share/unshare endpoints functional
  - [ ] Shared users can read threads
  - [ ] Only owner can write
  - [ ] SharedLink model for public links
  - [ ] Migration applied

  **QA Scenarios**:
  - Scenario: Share thread with user B → user B can view → user B cannot edit
  - Scenario: Create share link → public URL accessible

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): shared threads backend`
  - Files: Backend model, migration, chat.py

- [ ] 23. Cost Tracking Frontend (Dashboard + Charts)

  **What to do**:
  - Add cost display in thread header (shows total thread cost)
  - Add cost in SessionSummaryCard (per-session cost)
  - Create `/dashboard/usage` page with:
    - Total tokens/month, cost/month
    - Breakdown by model (pie chart)
    - Top threads by cost (table)
    - Usage trend chart (line chart, recharts or chart.js)
  - Add `GET /api/chat/usage` integration

  **Must NOT do**:
  - Do NOT add cost alerts or limits
  - Do NOT add export from usage dashboard
  - Do NOT add real-time cost updates (refresh on page load)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3.2 (with Tasks 19, 24, 25, 26, 27)
  - **Blocks**: None
  - **Blocked By**: Tasks 1, 20 (store + backend)

  **References**:
  - `src/components/chat/SessionSummaryCard.tsx` — Add cost display
  - `src/components/chat/ChatHeader.tsx` — Add thread cost
  - `/dashboard/` — Dashboard directory for new usage page

  **Acceptance Criteria**:
  - [ ] Thread header shows total cost
  - [ ] SessionSummaryCard shows per-session cost
  - [ ] `/dashboard/usage` page exists with charts
  - [ ] Charts show token/cost breakdown by model and thread

  **QA Scenarios**:
  - Scenario: Open thread → cost displayed in header
  - Scenario: Navigate to /dashboard/usage → charts render with data

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): cost tracking frontend dashboard`
  - Files: SessionSummaryCard.tsx, ChatHeader.tsx, new usage page

- [ ] 24. Workspace Memory Frontend

  **What to do**:
  - Add "Memory" section in ChatSettings or workspace settings
  - Display list of workspace memories with subject, predicate, object
  - Add/edit/delete memory UI
  - Search/filter memories
  - Show memory source (which thread it came from)

  **Must NOT do**:
  - Do NOT add bulk import/export of memories
  - Do NOT add memory categories or tags
  - Do NOT add memory sharing across workspaces

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3.2 (with Tasks 19, 23, 25, 26, 27)
  - **Blocks**: None
  - **Blocked By**: Tasks 1, 21 (store + backend)

  **References**:
  - `src/components/chat/ChatSettings.tsx` — Settings to add memory section
  - Backend `GET /api/chat/memory` — API to call

  **Acceptance Criteria**:
  - [ ] Memory section in settings
  - [ ] List memories with CRUD operations
  - [ ] Search/filter memories
  - [ ] Source thread linked

  **QA Scenarios**:
  - Scenario: Open settings → Memory section → add memory → appears in list
  - Scenario: Delete memory → removed from list

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): workspace memory viewer`
  - Files: ChatSettings.tsx

- [ ] 25. Shared Threads Frontend

  **What to do**:
  - Add "Share" button in thread header
  - User picker modal to select workspace members to share with
  - Read-only view for non-owners (disable input, show "View only" banner)
  - "Fork to my threads" button in read-only view
  - "Create share link" button for public links
  - Visual indicator for shared threads in sidebar (share icon)

  **Must NOT do**:
  - Do NOT add real-time presence indicators (Phase 4)
  - Do NOT add typing indicators for shared threads (Phase 4)
  - Do NOT add permission levels beyond read-only

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3.2 (with Tasks 19, 23, 24, 26, 27)
  - **Blocks**: None
  - **Blocked By**: Tasks 1, 22 (store + backend)

  **References**:
  - `src/components/chat/ChatHeader.tsx` — Add share button
  - `src/components/chat/ThreadSidebar.tsx` — Add share icon
  - `src/stores/chat-store.ts` — Store for shared state

  **Acceptance Criteria**:
  - [ ] "Share" button in thread header
  - [ ] User picker modal for sharing
  - [ ] Read-only view for non-owners
  - [ ] "Fork to my threads" button
  - [ ] Share icon in sidebar for shared threads

  **QA Scenarios**:
  - Scenario: Share thread → user B sees it → user B opens → read-only view
  - Scenario: Click "Fork" → new thread created with same content

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): shared threads frontend`
  - Files: ChatHeader.tsx, ThreadSidebar.tsx, new ShareModal.tsx

- [ ] 26. RAG Citation Chips

  **What to do**:
  - When backend includes source metadata in SSE events, render clickable citation chips (`[1]`, `[2]`)
  - Citation chips expand to show source document snippet
  - Backend: add source metadata to SSE events when RAG grounding is used
  - Frontend: parse citation markers and render as interactive chips
  - Link to source document in knowledge base

  **Must NOT do**:
  - Do NOT add citation management
  - Do NOT add citation export
  - Do NOT change the RAG backend pipeline

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3.2 (with Tasks 19, 23, 24, 25, 27)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/components/chat/MessageList.tsx` — Where to render citations
  - `src/lib/chat-types.ts:76-95` — SSEEvent type (add source metadata)

  **Acceptance Criteria**:
  - [ ] Citation chips render in messages
  - [ ] Chips expand to show source snippet
  - [ ] Chips link to source document
  - [ ] No change when no RAG grounding

  **QA Scenarios**:
  - Scenario: RAG-grounded response → citations appear → click → source shown
  - Scenario: Non-RAG response → no citations

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): RAG citation chips`
  - Files: MessageList.tsx, chat-types.ts

- [ ] 27. Context Window Management

  **What to do**:
  - Add `context_management` field to ChatSettings (options: "full", "summarize", "sliding_window")
  - Backend: auto-truncate or summarize when token count exceeds threshold
  - Frontend: show context bar ("Using 8,192 / 32,768 tokens — 12 earlier messages summarized")
  - "Full" mode: send everything (current behavior)
  - "Summarize" mode: auto-generate rolling summary of earlier turns
  - "Sliding window" mode: keep last N messages, drop older

  **Must NOT do**:
  - Do NOT change the default behavior (keep "full" as default)
  - Do NOT auto-switch modes
  - Do NOT add manual summarization UI

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3.2 (with Tasks 19, 23, 24, 25, 26)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/components/chat/ChatSettings.tsx` — Add context management option
  - Backend `stream_message_to_llm` — Where to add truncation/summarization

  **Acceptance Criteria**:
  - [ ] Context management setting in ChatSettings
  - [ ] Backend respects context_management setting
  - [ ] Context bar shows token usage
  - [ ] Default is "full" (no behavior change)

  **QA Scenarios**:
  - Scenario: Set to "summarize" → long thread → summary appears in context
  - Scenario: Context bar shows correct token count

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): context window management`
  - Files: ChatSettings.tsx, backend chat_service.py

- [ ] 28. Agent Handoff Mid-Conversation

  **What to do**:
  - Add agent picker to ChatSettings (alongside model picker)
  - Switching agents mid-thread preserves message history but changes system prompt and tool set
  - Backend routes to different agent configurations based on selected agent
  - Show which agent is "speaking" in message headers
  - Agent picker only visible when workspace has multiple agents

  **Must NOT do**:
  - Do NOT add multi-agent autonomous loops (Phase 4)
  - Do NOT add agent-to-agent handoff without user action
  - Do NOT change the agent backend infrastructure

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3.3 (with Task 29)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/components/chat/ChatSettings.tsx` — Add agent picker
  - Backend agent registry — Existing agent infrastructure
  - `src/lib/chat-types.ts` — Add agent_id to ChatSettings

  **Acceptance Criteria**:
  - [ ] Agent picker in ChatSettings
  - [ ] Switching agents preserves message history
  - [ ] System prompt changes to selected agent's prompt
  - [ ] Message headers show agent name
  - [ ] Agent picker hidden when only one agent

  **QA Scenarios**:
  - Scenario: Switch from default to "coder" agent → responses use coder system prompt
  - Scenario: Switch agents mid-thread → previous messages preserved

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): agent handoff mid-conversation`
  - Files: ChatSettings.tsx, backend chat_service.py

- [ ] 29. Mission-from-Chat (/mission command)

  **What to do**:
  - Add `/mission` slash command that captures current thread context (last N messages)
  - Backend: create a FlowManner mission from the conversation context
  - Frontend: show mission creation progress + link to mission dashboard
  - Mission inherits the conversation context as initial input
  - User can name the mission before creation

  **Must NOT do**:
  - Do NOT auto-create missions from chat
  - Do NOT change the mission system backend
  - Do NOT add mission monitoring in chat

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3.3 (with Task 28)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/lib/slash-commands.ts` — Slash command registry
  - Backend mission system — Existing mission creation API

  **Acceptance Criteria**:
  - [ ] `/mission` slash command registered
  - [ ] Command captures last N messages as context
  - [ ] Backend creates mission from context
  - [ ] Frontend shows progress + link to dashboard
  - [ ] User can name the mission

  **QA Scenarios**:
  - Scenario: Type `/mission` → mission created → link to dashboard
  - Scenario: Mission contains conversation context

  **Commit**: YES (groups with Phase 3)
  - Message: `feat(chat): mission-from-chat slash command`
  - Files: slash-commands.ts, backend mission API

### Phase 4 — Moonshots

- [ ] 30. Code Execution Sandbox

  **What to do**:
  - Backend: Create a separate Docker container service for code execution (Python, JavaScript, TypeScript, Bash)
  - Security: container with no network access, resource limits (CPU, memory, timeout), read-only filesystem except /tmp
  - API: `POST /api/chat/sandbox/run` with language, code, timeout_secs → returns stdout, stderr, exit_code
  - Frontend: `/run <language>` slash command that sends code to sandbox
  - Frontend: terminal-style output rendering (monospace, ANSI colors)
  - Backend proxies `/api/sandbox/*` to the sandbox service

  **Must NOT do**:
  - Do NOT allow network access from sandbox
  - Do NOT allow file system writes beyond /tmp
  - Do NOT support all languages (start with Python, JS, TS, Bash)
  - Do NOT add sandbox persistence (each run is isolated)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4.1 (with Tasks 31, 32)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - Report lines 261-265 — Sandbox spec
  - `/opt/flowmanner/docker-compose.yml` — Add sandbox service
  - `src/lib/slash-commands.ts` — Add /run command

  **Acceptance Criteria**:
  - [ ] Sandbox Docker service running
  - [ ] `POST /api/chat/sandbox/run` functional
  - [ ] Python, JS, TS, Bash supported
  - [ ] Terminal-style output rendering
  - [ ] Network access blocked
  - [ ] Resource limits enforced

  **QA Scenarios**:
  - Scenario: `/run python print("hello")` → stdout: "hello"
  - Scenario: `/run bash curl example.com` → stderr: network access denied

  **Commit**: YES (groups with Phase 4)
  - Message: `feat(chat): code execution sandbox`
  - Files: Docker setup, backend sandbox service, slash-commands.ts

- [ ] 31. Project-Level Context (Repo Ingestion → Vector DB → RAG)

  **What to do**:
  - Backend: project ingestion pipeline — clone repo → chunk files → embed → store in Qdrant
  - Backend: `POST /api/chat/projects/ingest` endpoint: takes git URL, clones, indexes
  - Backend: `/project` toggle in chat settings enables RAG grounding on project
  - Frontend: "Add to project context" button on files in the right sidebar
  - Frontend: project selection in ChatSettings
  - Use existing Qdrant infrastructure for vector storage

  **Must NOT do**:
  - Do NOT auto-sync repos (manual re-index only)
  - Do NOT index binary files
  - Do NOT add project-level permissions beyond workspace

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4.1 (with Tasks 30, 32)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - Report lines 265-266 — Project context spec
  - `/opt/flowmanner/backend/app/services/` — RAG services
  - Qdrant container — Already running at 10.0.4.3:6333

  **Acceptance Criteria**:
  - [ ] Project ingestion pipeline works
  - [ ] Files chunked and embedded in Qdrant
  - [ ] `/project` toggle in ChatSettings
  - [ ] RAG grounding on project files
  - [ ] "Add to project context" button in sidebar

  **QA Scenarios**:
  - Scenario: Ingest repo → search for function → results from project files
  - Scenario: Toggle /project off → responses don't reference project

  **Commit**: YES (groups with Phase 4)
  - Message: `feat(chat): project-level context`
  - Files: Backend ingestion pipeline, ChatSettings.tsx

- [ ] 32. Artifacts / Live Preview

  **What to do**:
  - When model outputs a code block with a filename hint, render as an artifact card
  - Artifact card: syntax highlighting, copy, download, "apply to workspace" buttons
  - For web artifacts (HTML/CSS/JS): render a live iframe preview
  - Artifact panel in right sidebar (alongside FilesTouched)
  - "Open in canvas" button on any artifact (for Task 33)

  **Must NOT do**:
  - Do NOT add artifact editing (view only)
  - Do NOT add artifact versioning
  - Do NOT auto-apply artifacts to workspace

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4.1 (with Tasks 30, 31)
  - **Blocks**: Task 33
  - **Blocked By**: None

  **References**:
  - Report lines 261-262 — Artifacts spec
  - `src/components/chat/FilesTouched.tsx` — Existing file display to extend
  - `src/components/chat/ChatRightSidebar.tsx` — Add artifact panel

  **Acceptance Criteria**:
  - [ ] Artifact cards render for code blocks with filenames
  - [ ] Syntax highlighting, copy, download buttons
  - [ ] "Apply to workspace" button
  - [ ] Live iframe preview for HTML/CSS/JS
  - [ ] Artifact panel in right sidebar

  **QA Scenarios**:
  - Scenario: Model outputs code block with filename → artifact card appears
  - Scenario: HTML artifact → live preview renders

  **Commit**: YES (groups with Phase 4)
  - Message: `feat(chat): artifacts and live preview`
  - Files: MessageList.tsx, ChatRightSidebar.tsx, new ArtifactCard.tsx

- [ ] 33. Canvas Mode (React Flow Workspace)

  **What to do**:
  - Create a visual workspace where artifacts (code files, diagrams, data tables) are arranged spatially
  - Reuse React Flow library (already installed: @xyflow/react)
  - "Open in canvas" button on any artifact (from Task 32)
  - Canvas mode toggle in chat header
  - Artifacts as nodes, connections as edges
  - Drag-and-drop positioning

  **Must NOT do**:
  - Do NOT add real-time collaboration on canvas (Phase 4 future)
  - Do NOT add canvas persistence (session only)
  - Do NOT add complex node types beyond artifacts

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4.2 (with Tasks 34, 35)
  - **Blocks**: None
  - **Blocked By**: Task 32 (artifacts must exist)

  **References**:
  - `package.json:17` — `@xyflow/react` already installed
  - `src/components/mission-builder/` — React Flow usage pattern to follow
  - Report lines 267-268 — Canvas mode spec

  **Acceptance Criteria**:
  - [ ] Canvas mode toggle in chat header
  - [ ] Artifacts render as React Flow nodes
  - [ ] Drag-and-drop positioning
  - [ ] "Open in canvas" button on artifacts
  - [ ] Canvas session-only (no persistence)

  **QA Scenarios**:
  - Scenario: Open canvas → artifacts appear as nodes → drag to reposition
  - Scenario: Close canvas → re-open → resets to default layout

  **Commit**: YES (groups with Phase 4)
  - Message: `feat(chat): canvas mode with React Flow`
  - Files: New Canvas.tsx, ChatHeader.tsx

- [ ] 34. Public Share Links

  **What to do**:
  - Backend: SharedLink model already created in Task 22
  - Backend: `GET /share/{token}` endpoint renders read-only public view (server-side for SEO)
  - Frontend: public share page at `/share/[token]`
  - Rate limiting on public endpoint
  - Share link optional expiration

  **Must NOT do**:
  - Do NOT add authentication for public links
  - Do NOT add editing in public view
  - Do NOT add link analytics (defer to future)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4.2 (with Tasks 33, 35)
  - **Blocks**: None
  - **Blocked By**: Task 22 (SharedLink model)

  **References**:
  - Report lines 269-270 — Public share spec
  - Backend SharedLink model from Task 22
  - `src/app/[locale]/` — Route structure for public page

  **Acceptance Criteria**:
  - [ ] `GET /share/{token}` returns public view
  - [ ] Public page renders at `/share/[token]`
  - [ ] Rate limiting on public endpoint
  - [ ] Optional link expiration

  **QA Scenarios**:
  - Scenario: Create share link → open in incognito → thread visible
  - Scenario: Expired link → "Link expired" message

  **Commit**: YES (groups with Phase 4)
  - Message: `feat(chat): public share links`
  - Files: Backend chat.py, new public page

- [ ] 35. Thread History Pagination

  **What to do**:
  - Backend: `GET /api/chat/threads/{id}/messages?before=<timestamp>&limit=50` endpoint
  - Returns messages with `has_more` flag
  - Frontend: "Load earlier messages" button at the top of MessageList
  - Integrates with virtual scrolling (Task 9) for seamless loading
  - Loading state while fetching earlier messages

  **Must NOT do**:
  - Do NOT add infinite scroll (button-triggered only)
  - Do NOT change the default message load count
  - Do NOT add message search within thread

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4.2 (with Tasks 33, 34)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - Report lines 219-220 — Pagination spec
  - Backend chat.py — Message listing endpoint
  - `src/components/chat/MessageList.tsx` — Add load earlier button

  **Acceptance Criteria**:
  - [ ] Backend supports `before` and `limit` params
  - [ ] `has_more` flag returned
  - [ ] "Load earlier messages" button at top
  - [ ] Loading state while fetching
  - [ ] Integrates with virtual scrolling

  **QA Scenarios**:
  - Scenario: Scroll to top → "Load earlier" button → click → messages load
  - Scenario: No more messages → button hidden

  **Commit**: YES (groups with Phase 4)
  - Message: `feat(chat): thread history pagination`
  - Files: Backend chat.py, MessageList.tsx

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search codebase for forbidden patterns. Check evidence files exist. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run linter + type check + tests. Review all changed files for: `as any`, empty catches, console.log in prod, unused imports. Check AI slop: excessive comments, over-abstraction.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task. Test cross-task integration. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance.
  Output: `Tasks [N/N compliant] | VERDICT`

---

## Commit Strategy

- **Phase 1**: `feat(chat): Phase 1 quick wins — Zustand store, auto-titling, regeneration, reactions, shortcuts`
- **Phase 2**: `feat(chat): Phase 2 core — virtual scrolling, optimistic updates, export, templates, mermaid/latex/diff`
- **Phase 3**: `feat(chat): Phase 3 advanced — full-text search, cost tracking, memory, sharing, RAG citations`
- **Phase 4**: `feat(chat): Phase 4 moonshots — code sandbox, project context, artifacts, canvas`

---

## Success Criteria

### Verification Commands
```bash
# Frontend builds without errors
cd /home/glenn/FlowmannerV2-frontend && npm run build

# Backend starts and health check passes
curl http://127.0.0.1:8000/api/health

# No TypeScript errors
cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit

# Tests pass
cd /home/glenn/FlowmannerV2-frontend && npx vitest run
```

### Final Checklist
- [ ] All Phase 1 quick wins delivered
- [ ] Zustand chat store replacing all useState in page-client
- [ ] Virtual scrolling handles 500+ messages without crash
- [ ] Full-text search returns ranked message snippets
- [ ] Workspace memory prepended to system prompt
- [ ] Shared threads with read-only + fork
- [ ] Cost tracking in thread header and usage dashboard
- [ ] All "Must NOT Have" guardrails respected
- [ ] No backend changes without Alembic migration
- [ ] Frontend deploy script succeeds
