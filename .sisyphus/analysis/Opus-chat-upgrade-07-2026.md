Glenn guilloux's Workspace

Search
Ctrl K

AI Chats

Home
1
Planner
6
AI
Teams

Invite

Upgrade
AI

Create

Ask or Create
Super Agents

Create Agent
All Agents
All Agents
1
My Agents
1
Activity
Recent Super Agents
Onboarding Assistant
Recent Chats
Flowmanner Improvement Plan
AI App Development Roadmap
Fixing URL/Port Normalization

Connections
45
Brain AI uses
1.5k
Credits left
Brain² can do what ChatGPT & Claude can't. Show me the receipts →



Flowmanner Improvement Plan
I need you to produce a comprehensive improvement plan for a chat system called Flowmanner. Here is the full architecture context:



## Current Architecture



### Backend (FastAPI, /opt/flowmanner/backend/)

- Models: ChatFolder, ChatThread, ChatMessage, ChatFile, ChatBranch, ChatTemplate, SharedLink (integer PKs, JSON metadata, workspace-scoped)

- API v1: /api/v1/chat/* — full CRUD + LLM chat (SSE streaming + non-streaming), export, auto-title, metadata PATCH, template CRUD

- API v2: /api/v2/chat/* — standardized envelope, cursor pagination, message edit/delete, system_prompt on payload, attachments, web_search

- Chat Service (~1400 lines): Multi-provider LLM resolution (15 providers via PROVIDER_MAP), BYOK key management (X-User-API-Key header + stored DB keys via UserAPIKey model), tool-calling loop (sandboxd preview/exec/files, web_search_enhanced, rag_search, memory_recall, browser_navigate/extract, linear_list/get, slack_list/read, github_list/get/list_issues/list_prs), memory injection (pre-LLM recall from PersonalMemoryClaim), memory extraction (post-LLM via LLM+regex fallback), circuit breaker per provider, streaming fallback to non-streaming, usage recording, cost tracking, prompt versioning with Redis cache

- Streaming protocol: SSE with event types: token, tool_call_start, tool_call_result, canvas_update, memory_recall_used, memory_citation, complete, error

- Session lifecycle: saves user message → commits → closes DB session → LLM streaming (multi-minute) → saves assistant message via fresh session

- Access control: workspace membership check with cross-workspace grant support



### Frontend (Next.js App Router, /home/glenn/FlowmannerV2-frontend/)

- SSEChat.tsx: Main streaming orchestrator — manages useChatMessages, useAttachments, useStreaming, useToolEvents hooks; slash commands (/sandbox), file drag-drop, mobile mode via MobileCompanion, auto-title on first response

- ChatLayout.tsx: Multi-column — ThreadSidebar | Canvas + InstrumentPanel + QuickStatsBar | ChatRightSidebar; zen mode; MatrixRain/TopographicBackground; LaunchPad when no thread

- ChatStore (Zustand): Per-thread localStorage persistence for settings + canvas tiles; tracks activeThreadId, messages, branches, connectionState, isTyping, canvasTiles, sessionStartTime

- useChatMessages: Fetch history from API, optimistic edit/delete with rollback

- MessageList: react-markdown (GFM, math, Mermaid, Diff, CodeBlock), tool call cards, memory citation chips, TTS via SpeechSynthesis

- ChatInputArea: Textarea with attachment previews, web search toggle, slash command autocomplete, send/stop streaming

- ThreadSidebar: Folder organization, date grouping (Today/Yesterday/This Week/Last Week/Older), fuzzy search

- ChatSettings: Model selector (PLATFORM_MODELS), TTS voice/speed, background mode, BYOK key+baseURL, temperature, max tokens, system prompt with version saving via /api/v2/prompts

- ChatHeader: Model switcher dropdown, export (MD/JSON/PDF/image/copy all text), share links, settings button

- useShareThread: Create/revoke/fetch share links

- useMessageSearch: Ctrl+F search with debounced query, match navigation, message highlighting

- ChatRightSidebar: Right panel (I haven't read this file in detail yet)

- chat-types.ts: TypeScript interfaces for ChatThread, ChatMessage (streaming/error/reactions/attachments/citations/agent_steps), SSEEvent, CanvasTile, AgentStep, ToolInvocation



## Questions I need you to answer



For each question, provide: (1) current state assessment, (2) recommended approach, (3) estimated effort (S/M/L), (4) priority (P0/P1/P2/P3), and (5) any dependencies between items.



### Architecture & Code Quality



1. The chat_service.py is ~1400 lines with LLM client setup, provider resolution, BYOK management, tool calling, memory injection/extraction, message building, and streaming all in one file. What is your recommended decomposition strategy? Identify the natural service boundaries and propose a module structure.



2. There are two API versions (v1 and v2) for chat. The v2 adds cursor pagination, message edit/delete, standardized envelope, attachments, and web_search. Should we deprecate v1 chat endpoints? What migration strategy would you recommend for the frontend which currently calls v1 for some operations and v2 for others?



3. The streaming session lifecycle (save user msg → commit → close session → LLM call → fresh session for assistant msg) was designed to avoid idle-in-transaction timeouts. Are there edge cases or failure modes we should handle better? What happens if the assistant message save fails after a successful stream?



### Streaming & Real-time



4. The SSE streaming protocol has 8 event types (token, tool_call_start, tool_call_result, canvas_update, memory_recall_used, memory_citation, complete, error). Is this well-designed for extensibility? Should we consider WebSocket for bidirectional communication, or is SSE the right choice here?



5. The tool-calling loop supports up to CHAT_MAX_TOOL_ROUNDS iterations. How should we handle the UX when the model makes many sequential tool calls (e.g., sandboxd_preview → sandboxd_file_write × 5 → sandboxd_serve)? The user currently sees a long pause with tool_call_start/result events but no text tokens.



6. The streaming has a fallback chain: streaming → non-streaming retry → non-streaming without tools. Is this robust enough? Should we add partial response recovery if the connection drops mid-stream?



### Context Window & Memory



7. Conversation history is limited to the last 20 messages (_build_chat_messages with max_history=20). For long conversations, this means earlier context is lost. What strategies would you recommend for context window management? (Summarization, sliding window with key message retention, RAG over conversation history, etc.)



8. The memory system has three layers: (a) pre-LLM memory recall (injects PersonalMemoryClaims as context), (b) post-LLM memory extraction (LLM+regex extracts new claims), (c) memory citation chips in the UI. How well do these work together? Are there gaps or improvements needed?



9. Prompt versioning is stored per-workspace with Redis caching (5min TTL). The frontend can save/load prompt versions via /api/v2/prompts. Is this a good foundation? Should we add prompt templates, community sharing, or A/B testing capabilities?



### Tool System



10. The tool allowlist is split into phases (Phase 1: sandboxd, web search, RAG, memory; Phase 2: browser, Linear, Slack, GitHub read-only). Phase 5 adds workspace-level allowlist filtering. Is this architecture scalable as we add more tools? Should we move to a capability/permission model instead of an allowlist?



11. Tools include sandboxd (6 tools for live preview), web search (DuckDuckGo + SearxNG), RAG search, memory recall, browser automation, and third-party integrations (Linear, Slack, GitHub). What tools are missing for a competitive AI chat experience? (Code execution, file analysis, image generation, calendar, email, etc.)



12. The canvas_update event auto-opens canvas tiles when certain tools execute (currently only browser_sandbox). Should this be extended to other tools? How should the canvas tile system evolve?



### Frontend UX



13. The ChatLayout has a complex multi-column layout (ThreadSidebar | Canvas | ChatRightSidebar) with zen mode. What is the ideal information architecture for a modern AI chat interface? Are we over-engineering the layout, or does it serve real use cases?



14. MessageList renders markdown with react-markdown + plugins (GFM, math, Mermaid, Diff, CodeBlock). What content rendering capabilities are we missing? (Tables of contents, collapsible sections, inline images, interactive widgets, etc.)



15. The chat supports branching (create_chat_branch copies messages up to a point into a new thread). How should the branching UX work in the frontend? Currently the backend supports it but I need to assess the frontend integration depth.



16. File attachments support images (base64 for vision models, text placeholder for non-vision) and documents (PDF via pdfplumber, DOCX via python-docx, XLSX via openpyxl, PPTX via python-pptx, plain text fallback). What improvements are needed for file handling? (Upload progress, preview, larger file support, more formats, etc.)



17. Export supports Markdown, JSON, PDF, image, and copy-all-text. Should we add more export formats or improve existing ones? What about importing conversations?



18. Share links exist (SharedLink model with token, expiry, is_active). How should the shared view work for external users who don't have a Flowmanner account?



### Performance & Reliability



19. The circuit breaker pattern is per-provider. Should we add rate limiting per user, per workspace, or per model? How should we handle provider outages gracefully?



20. Message history fetches ALL messages (get_chat_messages with offset/limit but the frontend calls it once). For threads with hundreds of messages, this will be slow. What virtualization or pagination strategy should we use?



21. The Zustand store persists settings per-thread in localStorage. Is this the right approach? Should we move to server-side preferences?



### Security & Access Control



22. BYOK keys are validated against provider format (sk-or- for OpenRouter, sk-ant- for Anthropic, etc.) with a stored-key fallback. Is this secure enough? Should we encrypt stored keys at rest?



23. The workspace access model allows cross-workspace grants for chat threads. How should this interact with the tool allowlist and memory system?



24. Shared links expose thread content to anyone with the token. Should we add password protection, view counting, or revocation scheduling?



### Missing Features (Competitive Analysis)



25. What are the top 5 features that modern AI chat platforms (ChatGPT, Claude.ai, Cursor, etc.) have that Flowmanner is missing? Prioritize by user impact and implementation effort.



26. How should collaborative chat (multiple users in the same thread) work? Is this a priority?



27. Should we add conversation forking (take a conversation to a different model mid-thread)?



28. How should the system handle model-specific capabilities (vision for GPT-4o, long context for Claude, code for DeepSeek) and surface these differences to the user?



Please produce a phased plan (Phase 1: Quick Wins, Phase 2: Core Improvements, Phase 3: Advanced Features, Phase 4: Platform Evolution) with concrete tasks, dependencies, and effort estimates. Focus on what will have the highest user impact with reasonable implementation effort.


PonderingClaude Opus 4.8
This is a meaty one, Glenn. Let me put together the full plan and drop it into a doc so you've got it in your workspace.

Done. Full plan is in
Flowmanner Chat: Comprehensive Improvement PlanDoc
, all 28 questions answered and sequenced into your four phases with effort, priority, and dependencies.



The short version: do the cheap-but-scary stuff first, assistant-save-failure recovery and encrypting BYOK keys at rest (both P0, both small). Then decompose that 1400-line chat_service.py because it unblocks nearly everything else. The two structural landmines that'll bite at scale are the full-history fetch (needs virtualization) and the fixed 20-message context window (silently forgetting mid-conversation). And your biggest competitive gap is code execution/data analysis, which you're well-positioned for since sandboxd already exists.



Want me to turn any phase into actual ClickUp tasks so you can start tracking it?






Like

Dislike
Follow ups

Turn Phase 1 into ClickUp tasks with subtasks


Make a slide deck of this plan for leadership


Build an agent to triage new Flowmanner bug reports




Opus 4.8

Docs
Flowmanner Chat: Comprehensive Improvement Plan


Brain²

Share
1







Add page

Mark Wiki

Add icon

Add cover

Settings
Flowmanner Chat: Comprehensive Improvement Plan
•

Last updated Today at 8:58 pm
Flowmanner Chat: Comprehensive Improvement Plan
Scope: architecture, streaming, memory, tools, UX, performance, security, and competitive gaps. Answers to all 28 questions are folded into the phased plan below, with a per-question appendix at the end. Effort scale: S (<3d), M (3-10d), L (>10d). Priority: P0 (do now) → P3 (someday).
﻿
Executive Summary
Flowmanner is already a serious, feature-dense chat platform: multi-provider LLM routing, BYOK, a real tool-calling loop, three-layer memory, SSE streaming with a proper protocol, canvas tiles, branching, and share links. The bones are strong. The risks are the usual ones for a fast-built system: a 1400-line service that's becoming a bottleneck, two live API versions, a full-history fetch that won't scale, unencrypted stored keys, and a fixed 20-message context window that silently drops information.

The highest-leverage moves, in order:
Fix the two correctness/scale landmines first: assistant-message-save failure recovery (Q3) and unencrypted BYOK keys at rest (Q22). Small effort, outsized risk reduction.
Decompose chat_service.py (Q1) so everything else gets easier and safer to change.
Solve context-window loss (Q7) and message-history virtualization (Q20): these directly degrade the product on exactly the conversations power users care about.
Close the competitive gaps that users feel daily (Q25): code execution, image gen, better file handling, artifacts/canvas maturity.

Everything below is sequenced into four phases.

﻿
Phase 1 — Quick Wins (P0/P1, mostly S/M)
Goal: kill the sharp edges and correctness bugs, and ship visible UX wins that need little new infra.

#
Task
Effort
Priority
Depends on
1.1
Assistant-save failure recovery (Q3). Persist streamed tokens incrementally or buffer + retry the assistant-message write. On failure, mark the message partial/failed and expose a client retry that reuses the already-streamed content instead of re-billing an LLM call.
M
P0
—
1.2
Encrypt BYOK keys at rest (Q22). Move from plaintext to envelope encryption (KMS/Fernet), never log keys, add a key-rotation path.
S
P0
—
1.3
Idempotency + transaction safety on the streaming lifecycle (Q3). Add an idempotency key per stream so a retry can't double-write; use a short transaction for the assistant save, not a long-held one.
S
P0
1.1
1.4
Tool-call progress UX (Q5). Emit a tool_progress/status event and render a live "agent step" timeline with human labels ("Writing 5 files", "Starting preview server") so long tool runs don't look frozen. Optional interim text streaming between rounds.
M
P1
protocol change (4.x)
1.5
Message-history pagination in the UI (Q20). Frontend already has offset/limit on the API but calls it once. Wire cursor pagination + windowed/virtualized MessageList (react-virtuoso). Load newest N, fetch older on scroll-up.
M
P1
—
1.6
Share-link hardening (Q24). Add optional password, view counting, and scheduled revocation/expiry. All additive to the SharedLink model.
S
P1
—
1.7
Context-window guard (Q7, cheap version). Replace naive last-20 with token-budget-aware truncation that always pins the system prompt + first user turn + last K turns, and warns in-UI when older context was dropped.
S
P1
—
1.8
Stored-key format validation cleanup (Q22). Keep format checks but stop treating them as security; they're UX guards only. Add provider-side key validation ping on save.
S
P2
1.2
1.9
Export polish (Q17). Fix PDF fidelity (code blocks, Mermaid rendered to SVG), add HTML export, and preserve citations/tool cards in MD/JSON.
S
P2
—

﻿
Phase 2 — Core Improvements (P1, mostly M/L)
Goal: pay down the structural debt and make the system scale and evolve safely.
2A. Decompose chat_service.py (Q1)
Split the 1400-line service along natural seams. Proposed module structure:

chat/
  orchestrator.py        # request → response flow, ties everything together
  providers/
    resolver.py          # PROVIDER_MAP, model→provider resolution
    client_factory.py    # builds provider clients
    circuit_breaker.py   # per-provider breaker (moved out)
  keys/
    byok.py              # header + stored-key resolution, encryption
  context/
    history_builder.py    # _build_chat_messages, truncation/summarization
    memory_recall.py     # pre-LLM injection
    memory_extract.py    # post-LLM extraction (LLM + regex)
  tools/
    registry.py          # tool definitions + allowlist/capability checks
    loop.py              # tool-calling loop, max-rounds
    executors/           # sandboxd, web_search, rag, browser, integrations
  streaming/
    sse.py               # event emission, protocol types
    fallback.py          # streaming → non-streaming → no-tools chain
  telemetry/
    usage.py             # usage + cost recording
    prompts.py           # prompt versioning + Redis cache

2B. API v1 → v2 consolidation (Q2)

Recommendation: yes, deprecate v1, but don't hard-delete. v2's envelope/cursor/edit-delete is the right foundation; unify on it and keep v1 as a thin compatibility shim only while telemetry shows traffic.
2C. Context window & memory (Q7, Q8)
2D. Streaming protocol & reliability (Q4, Q6, Q19)

SSE vs WebSocket (Q4): stay on SSE. Chat is server-push-dominant; SSE is simpler, proxy-friendly, and resumable via Last-Event-ID. Only revisit WebSocket if/when you add genuinely bidirectional realtime (collaborative editing, live presence in Q26).
2E. File handling (Q16)

﻿
Phase 3 — Advanced Features (P2, M/L)
Goal: close the competitive gap and deepen the differentiated surfaces (canvas, tools, branching).
3A. Tool system evolution (Q10, Q11, Q12)
3B. Branching & forking (Q15, Q27)
3C. Content rendering & IA (Q13, Q14)
3D. Sharing & preferences (Q18, Q21)

﻿
Phase 4 — Platform Evolution (P3, L)
Goal: multiplayer, governance, and the features that turn a chat app into a platform.


﻿
Top 5 Competitive Gaps (Q25), ranked by impact ÷ effort
Code execution / data analysis (3.2/3.4) — the single biggest "table stakes" gap vs ChatGPT/Claude/Cursor. High impact, high effort but bounded by your existing sandboxd.
Mature artifacts/canvas (3.6/3.10) — you already have canvas tiles; generalizing them to a typed-artifact surface is high impact, medium effort.
Image generation (3.3) — expected baseline, medium effort.
Better file handling (2.17-2.19) — upload progress, previews, bigger files, more formats. Medium impact, medium effort, low risk.
Context that doesn't silently forget (2.9/2.10) — summarization + RAG over history. High impact for power users, higher effort.

﻿
Cross-cutting dependency notes
The decomposition (2A) unblocks almost everything in tools, memory, and streaming. Do it early in Phase 2.
The versioned event envelope (2.13) unblocks partial-recovery (2.14), tool-progress UX (1.4), and generalized canvas (3.6). Prioritize it.
The capability model (3.1) unblocks new tools (3.2-3.5), cross-workspace governance (4.2), and any future marketplace (4.5).
Do the P0 correctness/security items (1.1, 1.2, 1.3) before anything else — they're cheap and they're the ones that bite in production.

﻿
Appendix — Per-question quick answers
Q1 Decompose per module map in 2A. Natural seams: providers, keys, context/memory, tools, streaming, telemetry. → 2.1-2.5.
Q2 Yes, deprecate v1; migrate frontend fully to v2, keep v1 as a shim until telemetry is zero. → 2.6-2.8.
Q3 Biggest gap is assistant-save-after-successful-stream failure: buffer tokens, retry, mark partial, allow no-recharge retry; add idempotency. → 1.1, 1.3, 2.14.
Q4 SSE is the right call; make the event envelope versioned + sequenced for extensibility. → 2.13.
Q5 Emit tool-progress events + human-labeled agent-step timeline; optionally stream interim text. → 1.4.
Q6 Fallback chain is decent; add server-side token persistence + Last-Event-ID resume for mid-stream drops. → 2.14.
Q7 Replace fixed last-20 with token-budget truncation (pin system+first+last-K), then rolling summarization, then RAG over history. → 1.7, 2.9, 2.10.
Q8 Layers are sound but loosely coupled; add dedupe, confidence/provenance, relevance ranking, a memory-management UI, and a review queue. → 2.11, 2.12.
Q9 Good foundation; add templates, workspace sharing, then A/B testing. → 3.12, 4.4.
Q10 Move allowlist → capability/permission model; keeps scaling as tools grow. → 3.1.
Q11 Missing: code execution, file/data analysis, image gen, calendar, email. → 3.2-3.5.
Q12 Generalize canvas_update to a typed-tile system driven by any tool. → 3.6.
Q13 Over-engineered by default; collapse to focused two-pane, progressively reveal panels, drop decorative backgrounds, keep zen. → 3.11.
Q14 Add TOC, collapsible sections, inline images, per-block copy, interactive widgets. → 3.10.
Q15 Backend has branching; build the frontend — branch-from-message, branch tree, lineage. → 3.7.
Q16 Upload progress, previews, chunked large-file upload to object storage, more formats + OCR. → 2.17-2.19.
Q17 Improve PDF fidelity, add HTML export, preserve citations/tool cards; add conversation import. → 1.9, 4.3.
Q18 Clean account-less read-only view respecting password/expiry, with a sign-up-to-continue CTA. → 3.13.
Q19 Add per-user/workspace/model rate limits + auto model-fallback on breaker-open. → 2.15, 2.16.
Q20 Virtualize MessageList + cursor pagination; load newest N, fetch older on scroll. → 1.5.
Q21 Move settings to server-side prefs; localStorage as cache. → 3.14.
Q22 Encrypt keys at rest (envelope encryption), never log, add rotation; format checks are UX-only. → 1.2, 1.8.
Q23 Cross-workspace grants must not inherit host tools or leak memory; define explicit policy. → 4.2.
Q24 Add password, view counting, scheduled revocation to SharedLink. → 1.6.
Q25 Code exec, mature artifacts/canvas, image gen, better files, non-forgetting context. See ranked list above.
Q26 Collaborative chat is a Phase 4 bet; priority depends on team vs solo ICP; needs WebSocket/CRDT. → 4.1.
Q27 Yes, mid-thread model forking as a branch. → 3.8.
Q28 Build a per-model capability registry and surface it in the UI (vision, context, tools, cost). → 3.9.


Improve

Comment
Bulleted list
All lists

Text
Turn Into

A
Text color





Alignment


You can't create tasks here. Please highlight only text in order to create tasks.
More settings

Welcome to your first Doc!

Learn how to use Docs to enhance your workflow.

Show me
