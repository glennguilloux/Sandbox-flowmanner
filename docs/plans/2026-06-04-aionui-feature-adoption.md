# FlowManner Elevation Plan — Features Inspired by AionUi

**Date:** 2026-06-04
**Source:** https://github.com/iOfficeAI/AionUi (Electron + React AI agent platform)
**Goal:** Identify which AionUi features would most elevate FlowManner, ranked by impact-to-effort ratio.

---

## What AionUi Is

AionUi is an Electron desktop AI agent platform (React + TypeScript frontend, Python backend server). Key differentiators: multi-channel deployment (Feishu/WeCom/Slack/Discord/Telegram), extension SDK, desktop app, multi-language UI (9 languages), and a polished chat UX with agent orchestration.

## What FlowManner Already Has (no need to copy)

FlowManner already covers these areas — do NOT waste time porting:
- Mission/flow builder + graph execution (superior to AionUi's basic agent runner)
- Marketplace + templates + community
- Swarm/multi-agent orchestration
- RAG pipeline + Qdrant
- Browser + terminal tools
- Analytics, cost tracking, observability
- HITL approvals
- Team/workspace with roles
- Webhook system
- 75+ backend API routes

---

## Tier 1 — High Impact, Chat UX (Week 1-2)

These directly improve the core user experience. FlowManner's chat is functional but bare-bones compared to AionUi's polished UX.

### 1.1 @-File Mentions in Chat
**What AionUi has:** `AtFileMenu/` — typing `@` in chat opens a file picker dropdown. Users can attach files from workspace, knowledge base, or recent uploads without leaving the input.
**What FlowManner has:** `/inbox` and `/files` pages exist but no in-chat file attachment.
**Implementation:**
- Frontend: `@` trigger in chat input → popover with file search (reuse `/api/v1/file` + `/api/v1/rag` endpoints)
- Backend: already supports file upload + RAG indexing
- Effort: **3-4 days**
- Files to study: `packages/desktop/src/renderer/components/chat/AtFileMenu/`

### 1.2 Slash Command Menu
**What AionUi has:** `SlashCommandMenu.tsx` — typing `/` shows quick actions (summarize, translate, run tool, switch agent, etc.)
**What FlowManner has:** Nothing — users type natural language for everything.
**Implementation:**
- Frontend: `/` trigger → command palette (cmdk or radix popover)
- Pre-built commands: `/summarize`, `/translate`, `/search`, `/agent <name>`, `/tool <name>`
- Wire to existing backend endpoints
- Effort: **2-3 days**

### 1.3 Context Window Usage Indicator
**What AionUi has:** `ContextUsageIndicator.tsx` — a progress bar showing how much of the model's context window is consumed. Warns at 80%, goes red at 95%.
**What FlowManner has:** Nothing — users hit context limits silently.
**Implementation:**
- Backend: add `context_tokens_used` to the chat streaming response (count via tokenizer)
- Frontend: thin bar under chat header or in the send box
- Effort: **1-2 days**

### 1.4 Agent Thought / Reasoning Display
**What AionUi has:** `ThoughtDisplay.tsx` — collapsible panel showing the agent's chain-of-thought in real-time during streaming.
**What FlowManner has:** Observatory page for mission replays, but no inline reasoning in chat.
**Implementation:**
- Backend: stream `thinking` events alongside `content` events (already supported by some LLM providers)
- Frontend: collapsible "Thinking..." panel above each assistant message
- Effort: **2-3 days**

### 1.5 Collapsible Content Blocks
**What AionUi has:** `CollapsibleContent.tsx` — long outputs (code blocks, tool results, tables) auto-collapse with a "Show more" toggle.
**What FlowManner has:** Full output always rendered — long messages blow up the chat.
**Implementation:**
- Frontend: wrap code blocks > 20 lines and tool outputs > 10 lines in collapsible
- Effort: **1 day**

### 1.6 Speech Input Button
**What AionUi has:** `SpeechInputButton.tsx` — microphone icon that uses browser Web Speech API for voice-to-text in the chat input.
**What FlowManner has:** `/api/v1/io` has voice transcribe/synthesize on the backend, but no frontend button.
**Implementation:**
- Frontend: mic button in SendBox, use `webkitSpeechRecognition` or backend Whisper endpoint
- Effort: **1-2 days**

---

## Tier 2 — Medium Impact, Platform Features (Week 3-4)

### 2.1 Command Queue Panel
**What AionUi has:** `CommandQueuePanel.tsx` — sidebar showing queued/pending agent actions (tool calls, sub-tasks). Users can cancel, reorder, or inspect.
**What FlowManner has:** Substrate/orchestration backend exists but no user-facing queue UI.
**Implementation:**
- Backend: expose `GET /api/v1/orchestration/queue` (task queue already in DB)
- Frontend: slide-out panel from chat showing pending tool calls / sub-tasks
- Effort: **3-4 days**

### 2.2 Cron Job Management UI
**What AionUi has:** Full `pages/cron/` — create, edit, pause, delete scheduled agent runs with cron expressions.
**What FlowManner has:** `/triggers` page exists but is basic. Backend trigger system exists.
**Implementation:**
- Polish the existing triggers page: cron expression builder, next-run preview, run history
- Effort: **2-3 days**
- Files to study: `packages/desktop/src/renderer/pages/cron/`

### 2.3 Extension / Plugin SDK
**What AionUi has:** Full extension system with examples (`hello-world-extension`, `e2e-full-extension`, `acp-adapter-extension`). Extensions register tools, UI components, and providers.
**What FlowManner has:** `/plugins` API and tools catalog, but no third-party extension SDK.
**Implementation:**
- Define extension manifest schema (JSON)
- Extension loader in backend (load tools from `/plugins/<name>/`)
- Frontend: extension settings page
- Effort: **5-7 days** (this is a bigger project)
- Files to study: `examples/` directory

### 2.4 Office Document Parsing (PPTX, DOCX)
**What AionUi has:** `pptx2json.d.ts`, Office type definitions — can parse PowerPoint files and extract structured content.
**What FlowManner has:** `/api/v1/io` document parse exists but may not cover PPTX.
**Implementation:**
- Backend: add `python-pptx` + `python-docx` to requirements
- Extend `/api/v1/io/parse` endpoint
- Effort: **1-2 days**

### 2.5 Multi-Language UI (i18n)
**What AionUi has:** README in 9 languages, UI supports localization.
**What FlowManner has:** `[locale]` routing in Next.js but only English content (`en.json`).
**Implementation:**
- Add `fr.json`, `es.json`, etc. to `/messages/`
- Use LLM to translate en.json → other locales
- Hook up language switcher in settings
- Effort: **2 days** (mostly translation work)
- **NOTE:** User preference is ENGLISH ONLY for dev. This is for end-user product only.

---

## Tier 3 — Strategic Bets (Month 2+)

### 3.1 Desktop App (Electron Wrapper)
**What AionUi has:** Full Electron desktop app with auto-update, system tray, native notifications.
**What FlowManner has:** Web-only.
**Why consider:** Desktop app could differentiate FlowManner for power users who want local file access, keyboard shortcuts, system tray notifications.
**Implementation:**
- Wrap Next.js in Electron (static export or BrowserWindow pointing to flowmanner.com)
- Add native notification integration
- Effort: **1-2 weeks**
- Risk: High maintenance burden, app store distribution

### 3.2 Multi-Channel Deployment
**What AionUi has:** Extensions for Feishu, WeCom Bot, Discord, Slack — deploy agents as chat bots on external platforms.
**What FlowManner has:** Webhooks and integrations API but no turn-key "deploy agent to Slack" flow.
**Implementation:**
- Slack/Discord adapter services (listen to platform webhooks, forward to FlowManner agent)
- Per-channel agent configuration
- Effort: **1 week per channel**
- Highest value channels: **Slack** and **Discord** (matches user's DJ/music audience)

### 3.3 Agent Hub / Discovery (AionHub equivalent)
**What AionUi has:** AionHub for sharing and discovering agents/templates.
**What FlowManner has:** Marketplace page exists but is basic.
**Implementation:**
- Polish marketplace: ratings, reviews, screenshots, one-click install
- Add "Featured Agents" section
- Effort: **1 week**

### 3.4 ACP (Agent Communication Protocol) Support
**What AionUi has:** `acp-adapter-extension/` and `types/codex/` — supports ACP for agent-to-agent communication.
**What FlowManner has:** A2A (agent-to-agent) service exists but ACP is a standardized protocol.
**Implementation:**
- Add ACP adapter to existing A2A service
- Enables interop with other ACP-compatible agents
- Effort: **3-5 days**

---

## NOT Recommended (Skip These)

| Feature | Reason to Skip |
|---------|---------------|
| Desktop Pet (`renderer/pet/`) | Novelty, not core to FlowManner's value prop |
| WeCom/Feishu adapters | Wrong market (China-focused), no user demand |
| pptx2json custom types | Use standard python-pptx instead |
| AionUi's provider system | FlowManner already has superior BYOK + multi-provider |
| AionUi's agent runner | FlowManner's mission/graph system is more advanced |

---

## Recommended Execution Order

```
Week 1: Tier 1.5 (Collapsible) + 1.3 (Context Indicator) + 1.6 (Speech Input)
         → Quick wins, immediately visible UX improvement
Week 2: Tier 1.1 (@-File) + 1.2 (Slash Commands) + 1.4 (Thought Display)
         → Core chat UX parity with AionUi
Week 3: Tier 2.1 (Command Queue) + 2.2 (Cron UI)
         → Platform polish
Week 4: Tier 2.4 (Office parsing) + 2.5 (i18n if needed)
         → Feature breadth
Month 2: Tier 2.3 (Extension SDK) or Tier 3.2 (Multi-channel)
         → Strategic bets based on user feedback
```

## Total Estimated Effort

| Tier | Effort | Impact |
|------|--------|--------|
| Tier 1 (Chat UX) | ~12 days | Immediate, high-visibility |
| Tier 2 (Platform) | ~15 days | Medium, fills feature gaps |
| Tier 3 (Strategic) | ~3-4 weeks | High potential, riskier |
| **Total** | **~8-10 weeks** | Full parity + differentiation |

## Key Insight

FlowManner's backend is already MORE capable than AionUi's (mission builder, swarm, RAG, observability, 75+ API routes). The gap is in **frontend polish** — specifically the chat experience. Tier 1 alone would close 80% of the perceived quality gap for a fraction of the effort.
