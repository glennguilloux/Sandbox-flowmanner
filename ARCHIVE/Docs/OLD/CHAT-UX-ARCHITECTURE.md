# Flowmanner Chat UX — Deep-Dive Architecture Analysis

## 1. Architecture Overview
Chat system: composition-of-hooks + Zustand global store.

ChatLayout.tsx (Shell) → SSEChat.tsx (Orchestrator)
  ├── MessageList.tsx + ChatInputArea + Canvas.tsx
  ├── TokenBar.tsx + ChatHeader.tsx
  └── CodeSandboxPanel.tsx

Hooks: useChatMessages, useStreaming, useAttachments, useToolEvents, useWebSearch, useCostTracker, useChatKeyboard
State: chat-store.ts (Zustand) + localStorage

## 2. Component Breakdown

### SSEChat.tsx — Orchestrator
Wires all hooks: useChatMessages, useStreaming, useAttachments, useToolEvents, useWebSearchToggle, useCostTracker, useChatKeyboard

Message flow: User send → addMessage(user) → addMessage(assistant placeholder) → streamResponse() SSE → RAF-batched updateMessage tokens → [DONE] finalize

### useStreaming.ts — SSE Engine
Endpoint: POST /api/chat/threads/:id/chat/stream. Protocol: SSE via ReadableStreamDefaultReader.
Retry: max 3, exponential backoff with jitter. Abort vs network vs fatal distinction.
60fps batching: requestAnimationFrame batches tokens. Tool parsing throttled to 200ms, dedup via Set.

### useChatMessages.ts — CRUD + Optimistic
Fetch: useEffect on threadId, AbortController cleanup. Normalizes 3 API shapes.
Edit/Delete: Optimistic → PATCH/DELETE → rollback on failure via prevMessagesRef snapshot.

### chat-store.ts — Zustand
State domains: UI (sidebar, zenMode, sandbox etc), Content (messages, title, branches), Settings (model, temp, BYOK), Connectivity (state, typing, tokens), Tools (events, files)
Settings auto-persisted to localStorage by activeThreadId.

### MessageList.tsx — Renderer
By role: user=plain text, assistant(streaming)=TypingIndicator+pulse cursor, assistant(complete)=react-markdown+GFM+math+syntax highlighting
Specialized: CodeBlock(copy), MermaidDiagram(lazy SVG), DiffBlock(color-coded +/-)
Performance: React.memo with custom comparator on content/isStreaming/editedAt. No virtualization.

### Canvas.tsx — Visual Workspace
Grid-based, text and code nodes, drag positioning with boundary constraints, bidirectional state sync.

### ArtifactCard.tsx — Data Display
Types: table (HTML table), card (key-value grid), json (pre block), chart (placeholder). Collapsible body.

### CodeSandboxPanel.tsx — Code Execution
Python/JS/TS sandbox. POST /api/chat/execute-code → subprocess. 30s default, 120s max, 100KB output limit.

### ChatHeader.tsx / TokenBar.tsx / Slash Commands
Header: Model switcher, settings, export (MD/JSON), copy all.
TokenBar: Color thresholds green≤60%, yellow 60-80%, red>80%. Shows tokens + cost.
Slash: /help, /integrations, /search.

## 3. Data Flow
User Input → handleSend() → addMessage(user) → addMessage(assistant placeholder) → streamResponse() SSE → RAF-batched tokens → [DONE] → finalize + token report
Thread switch → selectThread(id) → load localStorage settings → reset state → fetch history

## 4. Design Patterns
1. Composition of hooks 2. Optimistic UI with rollback 3. 60fps RAF batching 4. Zustand global sync 5. localStorage persistence 6. Error boundaries on MessageList+ChatInput 7. SSE/CRUD separation 8. Dual auth (NextAuth JWT + fm_tokens)

## 5. Chat Types
ChatThread: id, title, folder_id, parent_thread_id, system_prompt, model, message_count
ChatMessage: id, role, content, timestamp, streaming, isError, tokenCount, model, parentId, branchInfo, reactions, attachments, toolEvents
ToolType: read_file|edit_file|write_file|run_command|search|browse|other
ChatBranch: id, parentMessageId, threadId, title
SharedLink: id, token, expires_at, is_active
ENDOFDOC"
