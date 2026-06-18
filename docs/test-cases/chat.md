# Chat Test Cases

This catalog stores chat-domain behavior contracts per test automation strategy doc §6.

## Case record format

| Field | Value |
|---|---|
| ID | |
| Title | |
| Preconditions | |
| Steps | |
| Expected | |
| Priority | |
| Owner | |
| Last run | |
| Linked bugs | |

## P0 cases

### TC-CHAT-007 — Streaming chat emits at least one chunk within 5 s

- **Priority:** P0
- **Preconditions:** Authed user; BYOK key configured; LLM reachable.
- **Steps:**
  1. POST `/api/chat/stream` with a simple prompt.
  2. Open the SSE stream.
- **Expected:** First chunk arrives within 5 s; final `done` event present; total tokens > 0 in `output_data`.
- **Owner:** Backend / chat
- **Last run:** Not run yet
- **Linked bugs:** #88 (silent mocker), #142 (stream stalls)
