# Task: Wire Personal Memory into Chat (Enable the Memory Flywheel)

**Date:** 2026-06-29
**Estimated effort:** 1-2 days
**Priority:** Highest — this is the gateway to the Galaxy plan

---

## The Thesis

FlowManner's personal memory system is **90% built but disconnected**. All the pieces exist — extractor, recall, citation chips, Memory Inspector, pause toggle, SSE events — but they're not wired together in the live chat flow. The feature flag `FLOWMANNER_CROSS_MISSION_MEMORY` is OFF. This task turns it ON and fills the two remaining gaps.

---

## What Already Exists (DO NOT REBUILD)

### Backend (all at `/opt/flowmanner/backend/app/`)
- `services/personal_memory_service.py` — full CRUD: recall, forget, update_importance, consolidate
- `services/personal_memory_extractor.py` — LLM-based claim extraction (cheap model, regex fallback)
- `services/memory_citation_service.py` — `recall_for_chat()`, `format_memory_block()`, `build_recall_used_event()`, `build_citation_event()`
- `services/memory_extraction_pause_service.py` — per-conversation pause toggle
- `services/memory/background_review_service.py` — `stage_pending_write()`, `add_reviewed_entry()`
- `services/chat_service.py:861` — `_inject_memory_context()` already wired at line 1226
- `services/chat_service.py:1455-1468` — `memory_recall_used` and `memory_citation` SSE events already emitted
- `api/v2/personal_memory.py` — full REST API (recall, inspector, PATCH, DELETE, forget)
- `config.py:280` — `FLOWMANNER_CROSS_MISSION_MEMORY: bool = False`
- `models/personal_memory_models.py` — `PersonalMemoryClaim` model

### Frontend (all at `/home/glenn/FlowmannerV2-frontend/src/`)
- `components/chat/MemoryCitationChip.tsx` — renders `[memory: c-14, conf 0.85]` chip
- `components/chat/MessageList.tsx:489-496` — maps `message.citations` to `<MemoryCitationChip>`
- `components/chat/SSEChat.tsx:163` — opens WhyDrawer on chip click
- `components/memory-inspector/MemoryInspector.tsx` — full tree view with scope tabs
- `components/memory-inspector/ClaimRow.tsx` — individual claim row with actions
- `lib/chat-types.ts:282` — `MemoryCitation` interface
- `lib/chat-types.ts:67` — `ChatMessage.citations?: MemoryCitation[]`
- i18n keys for citation chips (en, fr, de, es, zh)

---

## The Two Gaps to Fill

### Gap 1: No post-chat extraction hook (backend)

**Problem:** `PersonalMemoryExtractor` is never called after a chat exchange. Users chat, the LLM responds, but no claims are extracted from the conversation. Memory stays empty.

**Where to wire it:** In `chat_service.py`, after the assistant message is saved and the SSE citation events are emitted. The extraction should happen **asynchronously** (fire-and-forget or background task) so it never blocks the chat response.

**Design:**
```
# In stream_message_to_llm(), AFTER the memory_citation events are yielded:
# 1. Check FLOWMANNER_CROSS_MISSION_MEMORY is ON
# 2. Check memory_extraction_pause_service.is_paused(conversation_id) is False
# 3. Fire-and-forget: call PersonalMemoryExtractor.extract() on the user's message + assistant response
# 4. For each extracted claim: either direct-write (solo user) or stage_pending_write (team workspace)
```

**Key constraints:**
- Extraction must NOT block the SSE stream — use `asyncio.create_task()` or similar
- Extraction must respect the pause toggle (`memory_extraction_pause_service.is_paused()`)
- Use the cheap model (default: `deepseek-chat` or `llamacpp` if configured)
- Extract from BOTH the user message AND the assistant response (the user's preferences often surface in what they ask the bot to do)
- Cap at 3-5 claims per exchange to avoid noise
- Apply the same defensive filter as `memory_citation_service` (no sensitive/restricted/private)

### Gap 2: Frontend SSE handler may not populate `message.citations` (frontend)

**Problem:** The backend emits `memory_citation` SSE events (chat_service.py:1463-1468), and the frontend has the `MemoryCitationChip` component, but the SSE handler in `useStreaming` or `SSEChat` may not be parsing `memory_citation` events into `message.citations`.

**Where to check:** Look at the SSE event parser (likely in `useStreaming.ts` or `SSEChat.tsx`). It needs to:
1. Detect `event.type === "memory_citation"`
2. Find the message with `id === event.message_id`
3. Push the citation payload into `message.citations[]`

**If it's already wired:** Skip this gap and note it as verified.

---

## Execution Plan (TDD)

### Step 1: Verify what's wired (30 min)
- Read `chat_service.py` around lines 1200-1470 to confirm the recall path works
- Read the SSE handler in the frontend to check if `memory_citation` events are parsed
- Read `personal_memory_extractor.py` to understand the API
- Run existing tests: `docker compose exec backend pytest app/tests/test_personal_memory*.py app/tests/test_memory_citation*.py -v`

### Step 2: Write the extraction hook test (RED) (1 hour)
- Create `backend/app/tests/test_chat_memory_extraction.py`
- Test: after a chat exchange, `PersonalMemoryExtractor.extract()` is called
- Test: extraction is skipped when `FLOWMANNER_CROSS_MISSION_MEMORY=False`
- Test: extraction is skipped when conversation is paused
- Test: extracted claims are persisted (direct-write or staged)
- Test: extraction does NOT block the SSE stream

### Step 3: Implement the extraction hook (GREEN) (1-2 hours)
- Add a post-response extraction call in `chat_service.py` (fire-and-forget)
- Wire in the pause check
- Wire in the feature flag check
- Wire in the `BackgroundReviewService` or direct-write based on workspace config

### Step 4: Enable the feature flag (1 line)
- `config.py:280` — change `FLOWMANNER_CROSS_MISSION_MEMORY: bool = False` to `True`

### Step 5: Verify frontend SSE handling (30 min)
- If `memory_citation` events are NOT parsed into `message.citations`, wire it
- If already wired, verify with a manual test

### Step 6: Integration test (1 hour)
- Start a chat, mention a preference ("I prefer Python over JavaScript")
- Check that a claim was extracted (query personal_memory_claims table or /api/v2/personal_memory/inspector)
- Start a new chat, ask "What language should I use?"
- Verify the bot recalls the preference and a citation chip appears

### Step 7: Deploy backend
- `bash /opt/flowmanner/deploy-backend.sh` from homelab
- Verify: `curl http://127.0.0.1:8000/api/health`

---

## Critical Rules

1. **DO NOT rebuild any of the existing components listed above.** They work. Wire them together.
2. **Extraction must be fire-and-forget.** A slow LLM call for extraction must never add latency to the chat response.
3. **Respect the pause toggle.** If the user paused extraction for a conversation, skip it.
4. **Respect the defensive filter.** No sensitive/restricted/private claims in chat.
5. **TDD: write the failing test first.** Then implement. Then verify.
6. **Backend only.** The frontend pieces are already built. Only touch frontend if the SSE handler is missing the `memory_citation` parser.
7. **Commit message format:** `feat(memory): <description>`
8. **Deploy after commit:** `bash /opt/flowmanner/deploy-backend.sh`

---

## Verification Checklist

- [ ] `FLOWMANNER_CROSS_MISSION_MEMORY` defaults to `True`
- [ ] Chat response is NOT slowed by extraction (fire-and-forget)
- [ ] Claims are extracted from chat exchanges
- [ ] Extraction respects pause toggle
- [ ] Extraction respects feature flag
- [ ] `memory_citation` SSE events reach the frontend
- [ ] Citation chips render in the chat UI
- [ ] Memory Inspector shows newly extracted claims
- [ ] Existing tests still pass: `docker compose exec backend pytest app/tests/test_personal_memory*.py app/tests/test_memory_citation*.py app/tests/test_chat_streaming.py -v`
- [ ] New tests pass: `docker compose exec backend pytest app/tests/test_chat_memory_extraction.py -v`
- [ ] Backend deployed and healthy
