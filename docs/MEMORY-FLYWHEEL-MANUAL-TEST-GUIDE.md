# Memory Flywheel — End-to-End Manual Test Guide

**Feature:** Personal Memory in Chat (extract → recall → citation chip)
**Prerequisite:** Backend deployed with `FLOWMANNER_CROSS_MISSION_MEMORY=True`
**Date:** 2026-06-29

---

## Overview

The memory flywheel has three stages:

1. **Extract** — After each chat exchange, the backend extracts preference/fact
   claims from the user's message and the assistant's response.
2. **Persist** — Extracted claims are saved to the `personal_memory_claims` table
   (direct-write for solo workspaces, staged for team workspaces).
3. **Recall + Cite** — In subsequent chats, matching claims are recalled, injected
   into the LLM prompt, and emitted as `memory_citation` SSE events that render
   as citation chips in the chat UI.

---

## Prerequisites

- [ ] Backend is deployed with `FLOWMANNER_CROSS_MISSION_MEMORY=True` in `.env`
- [ ] You are logged in as a user with a **workspace** (the feature requires
      `workspace_id` on the chat thread)
- [ ] `CHAT_MEMORY_CITATIONS_ENABLED` is `True` (for the recall + citation chip
      path; extraction works independently)

---

## Test 1: Basic Preference Extraction → Recall → Citation Chip

### Step 1: Start a chat with a clear preference

Open a new chat in your workspace and send:

> **User:** I strongly prefer dark mode for all my applications. I find light
> themes hard on my eyes.

Wait for the assistant to respond (any response is fine).

### Step 2: Wait for extraction (5-10 seconds)

The extraction hook fires **after** the assistant response is persisted. It runs
as a background task (`asyncio.create_task`) so it won't block the chat.

- **Regex path** (instant): Catches "I prefer dark mode" immediately.
- **LLM path** (up to 5s): May extract additional nuanced claims.

### Step 3: Verify the claim was persisted

**Option A: Via API**

```bash
curl -s http://localhost:8000/api/v2/personal_memory/inspector \
  -H "Authorization: Bearer <your_token>" \
  | jq '.items[] | {id, subject, predicate, object, claim_type, scope, source_type}'
```

Expected output (example):

```json
{
  "id": "aabbccdd-...",
  "subject": "user",
  "predicate": "prefers",
  "object": {"value": "dark mode"},
  "claim_type": "preference",
  "scope": "personal",
  "source_type": "conversation"
}
```

**Option B: Via Memory Inspector UI**

1. Navigate to **Memory Inspector** in the sidebar
2. Look for a new claim with:
   - Subject: `user`
   - Predicate: `prefers`
   - Object: `dark mode` (or similar)
   - Source: `conversation`

### Step 4: Start a NEW chat and trigger recall

Open a **different** chat thread (or the same one) and send:

> **User:** What theme should I use for my new dashboard?

### Step 5: Verify citation chip appears

After the assistant responds, you should see:

1. **Citation chip** below the assistant's message:
   ```
   [memory: c-<8hex>, conf 0.85]
   ```
   Clicking the chip opens the **WhyDrawer** with the full claim details.

2. **Memory context in the LLM prompt** — The assistant's response should
   reference your dark mode preference (e.g., "Since you prefer dark mode,
   I'd recommend...").

### Step 6: Verify SSE events (optional, for debugging)

Open browser DevTools → Network → filter by `stream` → look for the chat
stream response. You should see these SSE events in order:

```
data: {"type": "token", "content": "Since"}
data: {"type": "token", "content": " you prefer"}
...
data: {"type": "memory_recall_used", "message_id": "101", "claim_id": "...", ...}
data: {"type": "memory_citation", "message_id": "101", "label": "[memory: c-..., conf 0.85]", ...}
data: {"type": "complete", "full_response": "...", "message_id": 101, ...}
```

---

## Test 2: PII Filtering (Defensive Filter)

### Step 1: Send a message with PII

> **User:** My email is alice@example.com and I prefer Python over JavaScript.

### Step 2: Verify PII is NOT persisted

Check the Memory Inspector or API — you should see:
- ✅ `user prefers Python over JavaScript` (persisted)
- ❌ No claim with `has_email` or `alice@example.com` (filtered)

The defensive filter drops claims with `claim_type="sensitive"` or `scope="private"`.

---

## Test 3: Pause Toggle

### Step 1: Pause extraction for the conversation

Use the pause API (or the chat UI toggle if available):

```bash
curl -X POST http://localhost:8000/api/v2/personal_memory/pause \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "<thread_id>", "ttl_seconds": 3600}'
```

### Step 2: Send a message with a preference

> **User:** I love using Vim keybindings everywhere.

### Step 3: Verify NO new claims were extracted

Check Memory Inspector — no new claim for "vim keybindings" should appear.

### Step 4: Resume and verify extraction resumes

```bash
curl -X POST http://localhost:8000/api/v2/personal_memory/resume \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "<thread_id>"}'
```

Send another preference — it should now be extracted.

---

## Test 4: Multiple Claims in One Exchange

### Step 1: Send a message with multiple extractable facts

> **User:** My name is Alice. I prefer dark mode. We use Qdrant for vector search.

### Step 2: Verify multiple claims

Check Memory Inspector — you should see at least 2-3 claims:
- `user name Alice` (fact, personal)
- `user prefers dark mode` (preference, personal)
- `team uses Qdrant` (fact, workspace)

---

## Test 5: Team Workspace Staging

**Prerequisite:** You need a workspace with 2+ members, older than 30 days.

### Step 1: Send a preference in the team workspace

> **User:** I prefer concise commit messages.

### Step 2: Verify the claim is STAGED, not directly written

Check the `pending_writes` table or API:

```bash
curl -s http://localhost:8000/api/v2/personal_memory/pending \
  -H "Authorization: Bearer <your_token>"
```

You should see a pending write with:
- `action: "add"`
- `content: "user prefers: concise commit messages"`
- `status: "pending"`

### Step 3: Approve the pending write

Use the approval API to approve it — the claim should then appear in Memory Inspector.

---

## Test 6: Extraction Quality (LLM vs Regex)

### Regex patterns (instant, always available):
- "I prefer X" → `user prefers X`
- "I like/love X" → `user likes X`
- "I don't like X" → `user dislikes X`
- "My name is X" → `user name X`
- "We use X" → `team uses X`
- "Don't X" / "Never X" / "Always X" → `user do_not/never/always X`

### LLM patterns (up to 5s, requires model router):
- "Can you always use dark themes?" → `user prefers dark themes`
- "I'm a backend developer who works with Rust" → `user is backend developer`
- "Make sure to use semicolons in my code" → `user prefers semicolons`

### How to verify which path was used

Check the backend logs:

```bash
docker compose logs backend --tail=50 | grep memory_extraction
```

Expected log lines:
- LLM success: `memory_extraction: LLM extractor returned 2 claims (source=ExtractionSource.LLM) for thread 42`
- LLM empty → regex: `memory_extraction: LLM returned 0 claims; regex fallback found 1 for thread 42`
- LLM timeout: `memory_extraction: LLM extraction timed out for thread 42; falling back to regex`
- LLM error: `memory_extraction: LLM extraction failed for thread 42 (...); falling back to regex`

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| No claims extracted | Is `FLOWMANNER_CROSS_MISSION_MEMORY=True`? Is the thread in a workspace? |
| Claims extracted but no citation chip | Is `CHAT_MEMORY_CITATIONS_ENABLED=True`? |
| Citation chip but no memory context in response | Check `recall_for_chat` logs — the query may not match the stored claim's subject/predicate |
| PII appearing in Memory Inspector | Check the defensive filter — `claim_type` and `scope` should filter sensitive/private |
| Extraction seems slow | Check if LLM path is timing out (5s) — regex fallback is instant |
| Claims in team workspace not appearing | Check if they're staged in `pending_writes` — team workspaces require approval |

---

## Architecture Reference

```
Chat Exchange
    │
    ├─ Pre-LLM: recall_for_chat() → inject memory context → LLM sees it
    │
    ├─ LLM responds → SSE tokens streamed to frontend
    │
    ├─ Post-response: memory_recall_used + memory_citation SSE events
    │                  → frontend renders <MemoryCitationChip>
    │
    └─ Fire-and-forget: _maybe_extract_memory_claims()
        ├─ Check: FLOWMANNER_CROSS_MISSION_MEMORY flag
        ├─ Check: pause toggle
        ├─ Extract: LLM (5s timeout) → regex fallback
        ├─ Filter: drop sensitive/restricted/private
        └─ Persist:
            ├─ Solo workspace → PersonalMemoryService.create()
            └─ Team workspace → BackgroundReviewService.stage_pending_write()
```
