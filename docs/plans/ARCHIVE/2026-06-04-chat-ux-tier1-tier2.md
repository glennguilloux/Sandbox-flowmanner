# Chat UX & Platform Features — Tier 1 & 2

**Date:** 2026-06-04
**Goal:** 11 features from the AionUi adoption plan (Tier 1: Chat UX, Tier 2: Platform).
**Source spec:** `/opt/flowmanner/docs/plans/2026-06-04-aionui-feature-adoption.md`
**Frontend:** `/home/glenn/FlowmannerV2-frontend/` | **Backend:** `/opt/flowmanner/backend/`
**Deploy:** `bash /opt/flowmanner/deploy-frontend.sh` (~4min) / `deploy-backend.sh` (~2min)

---

## Already Exists (DO NOT rebuild)

- Slash command registry: 9 commands wired (`/help`, `/search`, `/template`, `/mission`, `/agents`, `/settings`, `/attach`, `/clear`, `/sandbox`) in `src/lib/slash-commands.ts`
- Slash dropdown UI in `ChatInputArea.tsx`, triggered from `SSEChat.tsx`
- `TokenBar.tsx` (47 lines) — progress bar, green/yellow/red color logic
- `ContextPeek.tsx` — right sidebar context usage
- `VoiceInput.tsx` (144 lines) — mic + MediaRecorder + backend Whisper
- `TriggerManagement.tsx` — basic trigger CRUD
- i18n locales: `de.json`, `en.json`, `es.json`, `fr.json`, `ja.json` in `src/i18n/locales/`
- Backend `/api/v1/io/documents/parse` endpoint exists

---

## Phase 1 — Quick Wins

### Task 1.1: Collapsible Content Blocks (1 day)

Auto-collapse long code (>20 lines) and text (>15 lines) in chat with "Show more" toggle.

**Edit:** `src/components/chat/MessageList.tsx`
- In `CodeBlock` (~line 99): if code text > 20 lines, show first 10 + "Show N more lines" button
- Apply same pattern to plain text messages > 15 lines
- Smooth height transition, collapsed by default
- Keep short blocks (< threshold) always expanded

### Task 1.2: Context Window Indicator (1 day)

**Problem:** `ChatLayout.tsx` hardcodes `contextWindowSize={32000}`. Make dynamic per model.

**Edit:** `ChatLayout.tsx`, `TokenBar.tsx`, `ChatHeader.tsx`
- Replace hardcoded 32000 with model-specific lookup map in `ChatLayout.tsx`:
  ```
  llamacpp/qwen-3.6-27b: 32768, openai/gpt-4o: 128000,
  anthropic/claude-sonnet-4: 200000, default: 32768
  ```
- Add TokenBar to ChatHeader (currently only in right sidebar)
- Add hover tooltip on TokenBar: prompt/completion/cost breakdown
- Verify store `tokenUsage` is wired (it is — SSEEvent.usage populates it)

### Task 1.3: Speech Input — Verify & Polish (0.5 day)

`VoiceInput.tsx` already exists and wired in `ChatInputArea.tsx`. Verify it works:
- Test in dev: does mic button render? Does recording produce transcription?
- Add browser Web Speech API fallback (`webkitSpeechRecognition`) when backend Whisper unavailable
- Ensure transcribed text inserts at cursor position, not appended to end

---

## Phase 2 — Core Chat UX

### Task 2.1: @-File Mentions (3-4 days)

Typing `@` opens file picker dropdown. Select file → attaches to message.

**Create:** `src/components/chat/AtFileMention.tsx`, `src/hooks/useFileSearch.ts`
**Edit:** `ChatInputArea.tsx`, `SSEChat.tsx`

1. Check file search endpoint: `grep -rn "router\.\(get\|post\)" backend/app/api/v1/file*.py`
2. Create `AtFileMention.tsx` — popover above input with debounced search, keyboard nav (up/down/Enter/Esc), file icons by extension, recent files when query empty
3. Trigger on `@` in ChatInputArea: detect `@` following space or at input start, don't trigger inside code blocks
4. On select: add file_id to attachments array (reuse existing attachment mechanism)
5. Design: search bar + file list + keyboard hints footer

### Task 2.2: Slash Commands — Add Missing Commands (2 days)

9 commands exist. Add: `/summarize`, `/translate`, `/agent`, `/tool`, `/code`.

**Edit:** `src/lib/slash-commands.ts`, `ChatInputArea.tsx`

Follow existing `registerSlashCommand` pattern:
- `/summarize <text>` — prepends system prompt for bullet-point summary, sends as normal message
- `/translate <lang> <text>` — prepends translation system prompt
- `/agent <name>` — queries `/api/v1/agents`, switches active agent for thread
- `/tool <name>` — triggers specific tool from tools catalog
- `/code <language>` — opens sandbox with language pre-selected

Polish dropdown in `ChatInputArea.tsx`: add descriptions, group by category, icons per command.

### Task 2.3: Agent Thought / Reasoning Display (2-3 days)

Collapsible "Thinking..." panel above assistant messages showing chain-of-thought.

**Create:** `src/components/chat/ThoughtPanel.tsx`
**Edit:** `chat-types.ts`, `MessageList.tsx`, `useChatMessages.ts`, backend streaming

1. Add to `ChatMessage`: `thinking?: string`, `thinkingTime?: number`
2. Add to `SSEEvent`: `thinking?: string`
3. Backend: emit `{"type": "thinking", "thinking": "..."}` events for models that support it. Parse `<think>...</think>` tags from Qwen3.6 as fallback.
4. `ThoughtPanel.tsx`: collapsed by default (header only "Thinking... 2.3s"), auto-expanded during stream, dimmed text, smooth animation
5. In `MessageList.tsx`: render ThoughtPanel above message content if `message.thinking` exists
6. In streaming handler: accumulate `thinking` events into current message

---

## Phase 3 — Platform Features

### Task 3.1: Command Queue Panel (3-4 days)

Slide-out panel showing pending/running tool calls and agent sub-tasks with cancel.

**Create:** `src/components/chat/CommandQueuePanel.tsx`, `src/hooks/useCommandQueue.ts`
**Edit:** `ChatLayout.tsx`, `ChatHeader.tsx`, backend `api/v1/orchestration.py`

1. Backend: `GET /api/v1/orchestration/queue` (query Celery active tasks), `POST /queue/{id}/cancel`
2. Frontend: poll every 2s or subscribe to WS events. List: name, status spinner, duration, cancel button
3. Queue icon with badge in ChatHeader, click toggles panel

### Task 3.2: Cron Job UI Polish (2-3 days)

**Create:** `src/components/triggers/CronExpressionBuilder.tsx`, `TriggerRunHistory.tsx`
**Edit:** `TriggerManagement.tsx`

1. Cron builder: presets (every minute/hour/day/week) + custom 5-field editor + next 5 runs preview
2. Run history table: name, last run, status, duration, next scheduled
3. Polish `TriggerManagement.tsx`: card layout, toggle switches, "Run Now" button, status badges
4. Backend: `GET /api/v1/triggers/{id}/history` if not exists

### Task 3.3: Office Document Parsing (1-2 days)

**Edit:** `backend/app/api/v1/io.py`, `backend/requirements.txt`

1. Add to requirements: `python-pptx>=0.6.21`, `python-docx>=1.1.0`
2. Extend `document_parse` for PPTX: extract slides as structured text
3. Extend for DOCX: extract paragraphs
4. Frontend: add pptx/docx file type icons in `AttachmentPreview.tsx`
5. Rebuild backend: `deploy-backend.sh`

### Task 3.4: Multi-Language UI — Language Switcher (2 days)

5 locale files exist. Wire up switcher, verify completeness.

**Edit:** settings page, `src/i18n/locales/`

1. Compare keys across locale files, fill missing translations
2. Language dropdown in settings: flag + name per option. Save to localStorage.
3. On change: redirect to `/{locale}/...` path
4. Quick toggle in user menu dropdown

**NOTE:** ENGLISH ONLY for dev. This is end-user product feature.

### Task 3.5: Extension / Plugin SDK (5-7 days)

Largest task. Start only after all others done.

**Create (backend):** `api/v1/extensions.py`, `models/extension.py`, `schemas/extension.py`, `services/extension_loader.py`
**Create (frontend):** `extensions/page.tsx`, `ExtensionCard.tsx`

1. Extension model: id, name, version, manifest (JSON), status, workspace_id
2. Manifest schema: name, version, description, author, tools[], capabilities[], config_schema
3. Loader: scan `/opt/flowmanner/plugins/` for manifests, register tools
4. API: list, install, enable, disable, delete
5. Frontend: extensions page with cards, enable/disable toggles, config panel per extension
6. Example: `plugins/example-extension/manifest.json`

---

## Verification (per task)

- No TS errors: `cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit`
- Works in local dev (`http://172.16.1.1:3000`)
- No console errors, mobile responsive (375px), dark mode
- Deployed and verified on live site (not container)

## Constraints

- No new npm packages unless absolutely necessary (no cmdk, no radix — custom UI)
- No new Zustand stores — extend `chat-store.ts`
- Backend rebuild only needed for: Task 2.3, 3.1, 3.3, 3.5
- `chmod 644` new `.py` files before docker build
