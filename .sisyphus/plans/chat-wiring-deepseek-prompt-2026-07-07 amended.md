# DeepSeek Prompt — Chat Wiring Sprint Amendment (Round 2)

**Date:** 2026-07-07
**Machine:** Homelab (172.16.1.1 / 10.99.0.3)
**Backend:** `/opt/flowmanner/backend/`
**Frontend:** `/home/glenn/FlowmannerV2-frontend/` (HOMELAB LOCAL — NOT `/opt/flowmanner/frontend/`)
**Source audits:**
- `.sisyphus/analysis/Opus-chat-critique-07-2026.md` (Round 1 critique of Opus's first plan)
- `.sisyphus/analysis/Opus-chat-architecture-deepdive-round2-2026-07-07.md` (Round 2 — Opus's architecture deep-dive, verified against codebase)
**Prior plan (superseded in part by this one):** `.sisyphus/plans/chat-wiring-deepseek-prompt-2026-07-06.md` (585 lines, 14 tasks across 2 phases)
**Plan shape:** Shape D (plan-for-AI-execution). This prompt is self-contained. You have zero prior context — everything you need is here.
**Sprint status:** Tasks 1.1 (allowlist expansion), 1.5 (fire-and-forget wrapper), 2.3 (scroll pagination), 2.5 (save recovery) are SHIPPED. This amended plan supersedes the portions of those tasks that the Round 2 analysis found insufficient, and adds 8 new/amended tasks. Tasks 1.2, 1.3, 1.4, 1.6, 1.7, 2.1, 2.2, 2.4, 2.6, 2.7 remain as specced in the 2026-07-06 prompt unless this doc explicitly amends them.

---

## CRITICAL RULES (READ FIRST — applies to ALL tasks)

1. **You are on the homelab.** Do NOT SSH the VPS. Do NOT deploy. Do NOT run `deploy-frontend.sh`, `deploy-backend.sh`, `docker compose up`, `rsync`, or any real network command. Edit source files only.
2. **DO NOT write meta-docs, handoff docs, exit audits, or analysis documents.** IMPLEMENT code changes only. Past sessions have warned: agents who write a "summary of what I would do" instead of editing files will be rolled back.
3. **After every change, run the verification command listed for that task. PASTE THE OUTPUT.** "Tests pass" without `pytest ... -v` output is a self-report, not evidence. Same for `npx tsc --noEmit`.
4. **If `npx tsc --noEmit` or `pytest` fails, FIX IT before moving to the next task.** Do not skip.
5. **One commit per logical change.** Do not bundle all tasks into one commit. Message format: `feat(chat): <one-line>` or `fix(chat): <one-line>`. Reference the task identifier (e.g. "Task 2.8") in the commit body so the audit trail cross-references this plan.
6. **Read `backend/AGENTS.md` and `backend/app/services/AGENTS.md` before touching `chat_service.py`.** Both files have local contracts you must follow (async-first, no `db.commit()` in sub-modules, BYOK precedence, tool capability tokens, migration data-mutation convention).
7. **Frontend lives at `/home/glenn/FlowmannerV2-frontend/`.** The path `/opt/flowmanner/frontend/` is the **VPS rsync target** — editing there has zero effect on the dev server and is lost on next deploy. Always edit in `/home/glenn/FlowmannerV2-frontend/`.
8. **English only.** All output in English. Do not mirror the prompt's language.
9. **Do NOT re-verify the "Already Verified" table facts** in the 2026-07-06 prompt. They are still ground truth. The additional facts in the "Round 2 Verified" table below are ALSO ground truth — do not re-grep them either.
10. **This sprint is Phase 1 + Phase 2 ONLY of the chat wiring work, plus the leaf-module extraction (Phase 0).** Phase 3 (decompose `chat_service.py` trunk, replace fresh-session pattern with task queue, API v1→v2) is STILL out of scope — it gets its own prompt after this sprint lands. The leaf extraction in Phase 0 is IN scope because it does NOT touch the trunk (the whole point of extracting leaves).

---

## Round 2 Verified (DO NOT re-investigate — add to the 2026-07-06 Already Verified table)

These facts were verified against the codebase on 2026-07-07 by Hermes on the homelab. Do not re-grep.

| Fact | Location | Verified by |
|---|---|---|
| `chat_service.py` is now 2,482 lines (was 2,343; +139 from Task 1.5 wrapper + Task 2.5 save-recovery retry) | `backend/app/services/chat_service.py` | `wc -l` |
| `_safe_fire_and_forget` wrapper EXISTS at line 38 (Task 1.5 shipped) | `chat_service.py:38` | grep |
| 5 fire-and-forget sites are WRAPPED with `_safe_fire_and_forget` at lines 484, 517, 1407, 1641, 2286 (Task 1.5 shipped) | `chat_service.py:484,517,1407,1641,2286` | grep |
| `AsyncSessionLocal()` fresh-session sites are at lines 613, 1172, 1392 (3 sites; save-recovery retry adds a 4th near 613) | `chat_service.py:613,1172,1392` | grep |
| `ToolMetadata` already has `category` (line 67), `required_scopes` (line 78), `tags` (line 75) fields — DOES NOT have a `visibility` field | `backend/app/tools/base.py:63-86` | read_file |
| `_execute_tool_call` enforces `required_scopes` against cached user scopes (capability gate EXISTS and works) | `chat_service.py:1704-1763` | read_file (already in 2026-07-06 verified table) |
| `docs/DUAL-WRITE-DECISION.md` recommends Option (a): Mission canonical, Blueprint+Run as projected read model. `DualWriteService` lives in `_mission_cqrs/compat.py` as `dual_write_sync_run_status`, `dual_write_sync_blueprint`, `dual_write_soft_delete_blueprint` — fire-and-forget via `_schedule_fire_and_forget()`. NOT in scope for this sprint (separate prompt after the sprint lands) | `docs/DUAL-WRITE-DECISION.md`, `backend/app/api/_mission_cqrs/compat.py`, `backend/app/api/_mission_cqrs/AGENTS.md` §6 | read_file + grep |
| `_prune_messages_to_budget` already exists at `chat_service.py:1005` (token-budget pruning function — Task 2.1 needs to WIRE it into `_build_chat_messages`, not write it from scratch) | `chat_service.py:1005-1063` | grep + read |
| Nginx config for SSE lives on the VPS only — homelab has no relevant nginx config. `proxy_buffering off` + `proxy_read_timeout 300s` is a VPS manual edit by Glenn, NOT an agent task | (no path on homelab) | grep `/etc/nginx/` on homelab → only `mime.types` + unrelated sites |
| `@tanstack/react-virtual` is installed but unused in the frontend; `react-virtuoso` is NOT installed | `frontend/package.json` (already in 2026-07-06 verified table) | grep |

---

## ⚠️ Amendments to the 2026-07-06 plan (READ these — they supersede the prior task specs)

| Prior task | Round 2 verdict | Amendment |
|---|---|---|
| Task 1.1 (allowlist expansion) — SHIPPED | The hardcoded allowlist should be Deprecated, not just extended. `required_scopes` IS the capability model. | Task 1.1's 11-tool additions are KEPT. New Task 3.2 (below) adds `visibility` metadata + starts the migration to computed allowlist. Do NOT re-do Task 1.1. |
| Task 1.2 (SSE reconnection) — NOT STARTED | Last-Event-ID alone is a lie — no server-side buffer. Reconnects during in-flight streams LOSE events. | Task 1.2 is SPLIT into 1.2a (keepalive ping) + 1.2b (client reconnect + server-side Redis event buffer). See below. |
| Task 1.5 (fire-and-forget) — SHIPPED | The wrapper is a band-aid — doesn't hold a strong ref (GC risk), doesn't split durable vs ephemeral. | New Task 3.3 (below) replaces the band-aid with a `BackgroundTaskManager` singleton (3 ephemeral sites) + Celery migration (2 memory-extraction sites). Task 1.5's wrapper is KEPT as the internal implementation of the ephemeral tier — do NOT undo it. |
| Task 2.3 (virtualization) — SHIPPED (pagination only) | SKIP virtualization. Memoize markdown rendering, remove render cap. Gate tanstack behind real >500-msg data. | New Task 3.5 (below) replaces the virtualization half of Task 2.3 with "memoize markdown + raise render cap." The pagination half of Task 2.3 is DONE and KEPT. |
| Task 2.5 (save recovery) — SHIPPED | The retry logic is good. The 4th fresh-session pattern needs consolidation. | New Task 2.8 (below) consolidates the 3+1 fresh-session patterns into one `fresh_session()` context manager. |

---

## Scope of THIS sprint — Phase 0 + Phase 1 + Phase 2 + Phase 3

This sprint now has FOUR phases. Phase 0 (leaf extraction) runs IN PARALLEL with Phase 1/2 — that's the whole point of extracting leaves (no trunk-line conflicts). Phase 3 (below) amends/extends the shipped tasks per Round 2.

**IN scope:**
- Phase 0: Extract 3 leaf modules from `chat_service.py` (parallel to Phase 1/2, no trunk conflicts)
- Phase 1: Tasks 1.2a, 1.2b, 1.3, 1.4, 1.6, 1.7 (1.1 and 1.5 already shipped; 1.2 split into 1.2a/b)
- Phase 2: Tasks 2.1, 2.2, 2.4, 2.6, 2.7, 2.8 (2.3 and 2.5 already shipped)
- Phase 3: Tasks 3.2 (computed allowlist), 3.3 (fire-and-forget tiers), 3.5 (markdown memoization)

**OUT of scope (named so the next prompt picks them up):**
- Phase 4 (trunk decomposition of `chat_service.py`): the tool loop + streaming session lifecycle extraction. Runs AFTER this sprint lands. Trunk extraction conflicts with everything — that's why it's last.
- Phase 5 (task-queue for durable work): replace the fresh-session `wrapper` with Celery for memory extraction. The fresh-session wrapper (Task 2.8) is the bridge; the queue is Phase 5.
- Dual-write removal (`docs/DUAL-WRITE-DECISION.md` Option a): separate prompt, not this sprint.
- Strategy viability UX (27B "needs larger model" prompt): separate prompt, gated on Phase 1 of the Q3/Q4 roadmap (strategy profiling).
- Nginx `proxy_buffering off` + `proxy_read_timeout 300s` on the SSE location: VPS manual edit by Glenn, NOT an agent task. Glenn does this before or same-day as Task 1.2a ships.

---

# PHASE 0: Extract Leaf Modules (run in parallel with Phase 1/2)

Theme: `chat_service.py` is 2,482 lines. Extract 3 pure leaf modules — no back-references to the orchestrator — so Phase 1/2 trunk edits don't conflict. Leaf extraction is additive (new files + import swaps), which barely touches the lines Phase 1/2 is editing.

**⚠️ Critical constraint:** The 3 leaf modules MUST be pure — they take inputs and return outputs, they do NOT call back into `chat_service.py`'s orchestrator functions. If you find a circular dependency while extracting, STOP and note it in your report — do not create a circular import.

---

## Task 0.1: Extract `llm_providers.py`

**Effort:** M (~2 hours)
**Files:**
- Create: `backend/app/services/llm_providers.py`
- Modify: `backend/app/services/chat_service.py` (import swaps at the call sites only — do NOT move trunk code)

**Background:** Round 2 verified `PROVIDER_MAP` at `chat_service.py:46`, `_normalize_provider` at :67, `_get_base_url_for_provider` at :80, `_get_provider_for_model` at :94, `_get_upstream_model_name` at :101, `_resolve_provider` at :116. These are pure lookups — no back-references to the orchestrator. Extracting them breaks the most import-edges (everyone depends on provider resolution).

**Steps:**

1. Read `chat_service.py:46-170` to see all provider-related functions. Confirm none of them call other `chat_service.py` functions that are NOT being moved.
2. Create `backend/app/services/llm_providers.py`. Move into it:
   - `PROVIDER_MAP` dict
   - `_normalize_provider()`, `_get_base_url_for_provider()`, `_get_provider_for_model()`, `_get_upstream_model_name()`, `_resolve_provider()`
   - `_detect_provider_from_key()` and `_providers_compatible()` (these are BYOK-adjacent; they go here for now — they'll move to a dedicated `byok.py` in Phase 4)
3. In `chat_service.py`, replace the moved definitions with:
   ```python
   from app.services.llm_providers import (
       PROVIDER_MAP, _normalize_provider, _get_base_url_for_provider,
       _get_provider_for_model, _get_upstream_model_name, _resolve_provider,
       _detect_provider_from_key, _providers_compatible,
   )
   ```
   Place the import at the top of the file with the other `from app.services...` imports. Do NOT leave the original definitions in place — delete them after the import swap.
4. **Signature preservation:** Every moved function must have the EXACT same signature (params, defaults, return type) as before. If you need to change a signature, STOP — that's a Phase 4 refactor, not a Phase 0 move.
5. Tests: create `backend/app/tests/test_llm_providers.py`. Test:
   - `_resolve_provider("openai/gpt-4")` returns the expected `(provider, base_url, model_name)` tuple
   - `_detect_provider_from_key("sk-or-...")` returns `"openrouter"`
   - `_providers_compatible(None, "openai")` returns `True` (ambiguous prefix is hint-only, per services/AGENTS.md §6)
   - `_normalize_provider("OpenAI")` returns `"openai"` (case-insensitive)
   Copy the assertion patterns from any existing chat test that calls `_resolve_provider`.

**Verification:**
```bash
docker compose exec backend python -m pytest app/tests/test_llm_providers.py -v
docker compose exec backend python -c "from app.services.llm_providers import _resolve_provider; print(_resolve_provider('openai/gpt-4'))"
docker compose exec backend python -c "import ast; ast.parse(open('app/services/chat_service.py').read()); print('chat_service parse ok')"
```
Expected: 4+ tests pass; the `_resolve_provider` print returns the tuple; `chat_service.py` still parses (no syntax errors from the move).

---

## Task 0.2: Extract `chat_context.py`

**Effort:** M (~1.5 hours)
**Files:**
- Create: `backend/app/services/chat_context.py`
- Modify: `backend/app/services/chat_service.py` (import swaps only)

**Background:** Round 2 verified `_prune_messages_to_budget` at `chat_service.py:1005` (with `_estimate_tokens` nested at :1017), `_build_chat_messages` at :1064, `_inject_memory_context` at :1121. These are pure transforms over message lists — they take `list[dict]` and return `list[dict]`. Task 2.1 (context window manager integration) edits `_build_chat_messages` — extracting it FIRST means Task 2.1 lands in its own file, no merge conflict with other Phase 1/2 work.

**Steps:**

1. Read `chat_service.py:1005-1160` to see the full context-building cluster. Confirm:
   - `_prune_messages_to_budget`, `_estimate_tokens`, `_build_chat_messages`, `_inject_memory_context` are all pure (no orchestrator back-calls).
   - If `_build_chat_messages` calls `_inject_memory_context`, that's fine — both move together into the same file.
2. Create `backend/app/services/chat_context.py`. Move into it:
   - `_prune_messages_to_budget()` and its nested `_estimate_tokens()`
   - `_build_chat_messages()`
   - `_inject_memory_context()`
3. In `chat_service.py`, replace with:
   ```python
   from app.services.chat_context import (
       _prune_messages_to_budget, _build_chat_messages, _inject_memory_context,
   )
   ```
4. Signature preservation: every moved function keeps exact signature + return shape.
5. Tests: create `backend/app/tests/test_chat_context.py`. Test:
   - `_prune_messages_to_budget([...20 messages...], 6000)` returns a list shorter than 20, keeps first 2 + last 5, middle replaced with a placeholder (read :1005-1063 to confirm the exact placeholder shape before asserting)
   - `_build_chat_messages(...)` returns `list[dict]` in OpenAI message format (roles: system/user/assistant)
   - Copy assertion patterns from existing chat tests that exercise `_build_chat_messages` (grep `backend/app/tests/` for `test_chat_*.py` first).

**Verification:**
```bash
docker compose exec backend python -m pytest app/tests/test_chat_context.py -v
docker compose exec backend python -c "import ast; ast.parse(open('app/services/chat_service.py').read()); print('chat_service parse ok')"
```

---

## Task 0.3: Extract `sse_protocol.py`

**Effort:** S (~45 min)
**Files:**
- Create: `backend/app/services/sse_protocol.py`
- Modify: `backend/app/services/chat_service.py` (import swaps only)

**Background:** Round 2 named SSE event emission as a leaf. The SSE event types (`token`, `tool_call_start`, `tool_call_result`, `canvas_update`, `memory_recall_used`, `memory_citation`, `complete`, `error`, `save_failed` — Task 2.5 added the last one) are constants. The event serializer (dict → SSE-formatted `data: ...\n\n` string) is pure formatting. Task 1.2a (keepalive ping) and Task 1.2b (Redis event buffer) both need to call the serializer — extracting it FIRST means those tasks land in their own files.

**Steps:**

1. Grep for the SSE event emission helpers in `chat_service.py`:
   ```bash
   grep -n "data: \|event: \|yield f\"data\|SSEEvent\|_format_sse\|_emit_sse\|def.*sse" backend/app/services/chat_service.py | head -30
   ```
2. Identify the pure formatting functions (dict → `data: {...}\n\n` string). Move them + the event-type constants into `sse_protocol.py`.
3. **If the SSE emission is inline in `stream_message_to_llm` (a generator) and NOT extracted into helper functions:** do NOT refactor the generator in Phase 0 — that's trunk work (Phase 4). Instead, extract just the event-type constants and any pure formatting helpers that already exist as standalone functions. Note in your report "SSE emission is inline in the generator; only constants extracted; full serializer extraction deferred to Phase 4."
4. In `chat_service.py`, import the constants from `sse_protocol.py`.
5. Tests: create `backend/app/tests/test_sse_protocol.py`. Test the formatting helper (if extracted) produces the exact `data: {...}\n\n` shape. If only constants were extracted, test the constants are importable.

**Verification:**
```bash
docker compose exec backend python -m pytest app/tests/test_sse_protocol.py -v
docker compose exec backend python -c "import ast; ast.parse(open('app/services/chat_service.py').read()); print('chat_service parse ok')"
```

---

# PHASE 1: Wire What Exists (amended)

Tasks 1.1 (allowlist expansion, shipped) and 1.5 (fire-and-forget wrapper, shipped) are DONE. Task 1.2 is split into 1.2a + 1.2b. Tasks 1.3, 1.4, 1.6, 1.7 remain as specced in the 2026-07-06 prompt — do NOT re-read them here, they are unchanged.

---

## Task 1.2a: SSE keepalive ping (server-side, highest-value single fix)

**Effort:** S (~30 min)
**Files:**
- Modify: `backend/app/services/chat_service.py` — the `stream_message_to_llm` generator (starts at :1904)
- Or modify: `backend/app/services/sse_protocol.py` (if Task 0.3 extracted a serializer helper)

**Background:** Round 2 verified the Nginx → Docker → FastAPI path. The single highest-value reliability fix is keepalive pings: the SSE spec recommends `: ping\n\n` comment lines every ~15s to stop reverse proxies from killing idle-looking connections during long tool rounds. This is fully in the agent's control (no VPS edit needed). Glenn does the Nginx `proxy_buffering off` + `proxy_read_timeout 300s` change on the VPS in parallel.

**Steps:**

1. Read `stream_message_to_llm` (chat_service.py:1904 to ~2338). Identify the generator's `yield` sites — every place the generator emits an SSE event.
2. Add a keepalive mechanism. Two acceptable designs (pick one, document in commit message):
   - **(a) Last-yield timestamp + idle check:** before each `yield`, check if >15s elapsed since the last yield. If yes, first `yield ": ping\n\n"` then yield the real event. Simple, no background task.
   - **(b) Background ping task:** spawn an `asyncio.create_task` that yields `": ping\n\n"` every 15s. More complex, and `yield` from a background task into a generator is NOT straightforward — prefer (a) unless you can demonstrate (b) works in a test.
3. **Use design (a) unless you can prove (b) works.** The pattern for (a):
   ```python
   import time
   last_yield = time.monotonic()
   async for event in _stream(...):
       if time.monotonic() - last_yield > 15:
           yield ": ping\n\n"
           last_yield = time.monotonic()
       yield event
       last_yield = time.monotonic()
   ```
4. Test: create `backend/app/tests/test_sse_keepalive.py`. Test that a stream with a 20s gap between events emits at least one `: ping\n\n` comment line. You'll need to mock the LLM stream to introduce the gap — copy the mock pattern from existing streaming tests (grep `test_chat_stream` in `backend/app/tests/`).

**Verification:**
```bash
docker compose exec backend python -m pytest app/tests/test_sse_keepalive.py -v
docker compose exec backend python -c "import ast; ast.parse(open('app/services/chat_service.py').read()); print('parse ok')"
```
Expected: keepalive test passes; chat_service parses.

**Commit message:** `feat(chat): add SSE keepalive ping every 15s (Task 1.2a) — defeats proxy idle timeouts during long tool rounds`

---

## Task 1.2b: SSE reconnection with server-side Redis event buffer

**Effort:** L (~3 hours — the server-side buffer is the new scope vs the original Task 1.2)
**Files:**
- Modify: `backend/app/services/chat_service.py` — `stream_message_to_llm` (append events to Redis buffer)
- Modify: `backend/app/services/sse_protocol.py` (if Task 0.3 extracted a serializer) — add buffer-append helper
- Modify: `/home/glenn/FlowmannerV2-frontend/src/hooks/useStreaming.ts` (client reconnect + `Last-Event-ID` header)
- Modify: `/home/glenn/FlowmannerV2-frontend/src/components/chat/SSEChat.tsx` (reconnecting banner)
- Create: `backend/app/tests/test_sse_reconnect_buffer.py`
- Create: `frontend/src/hooks/__tests__/useStreaming.reconnect.test.tsx`

**Background:** Round 2's key finding: Last-Event-ID alone is a lie without a server-side buffer. FastAPI `StreamingResponse` retains nothing. For in-flight streams the tokens aren't in Postgres yet, so only a Redis buffer can replay. The buffer is keyed by `stream_id`, events appended with a monotonic `seq`, short TTL (5min — just long enough to cover a reconnect). Settled streams (assistant message committed) → client re-fetches from the message API, no replay.

**Design (from Round 2 §5):**
- Redis list or Redis STREAM keyed by `chat:stream:{stream_id}`, events appended with monotonic `seq`, TTL 5min
- On reconnect, client sends `Last-Event-ID: <seq>`; server replays events with `seq > last_seq` from the buffer, then resumes live
- If buffer is gone (TTL expired or stream completed), client falls back to re-fetching the settled message from the message API
- Client reconnect: exponential backoff 1s → 2s → 4s → 8s (capped at 30s), max 5 retries, jitter ±500ms, `sonner` toast on give-up with "Retry" button
- Do NOT reconnect if user pressed stop (`stoppedRef.current === true`)
- Do NOT reconnect on 4xx (surface the error — auth failure etc.); DO reconnect on `AbortError` (network drop) and HTTP 5xx

**Steps (server side):**

1. In `stream_message_to_llm` (or in the route handler that wraps it — grep for where the `StreamingResponse` is constructed):
   - Generate a `stream_id` (UUID) at stream start. Emit it as the first SSE event: `event: stream_start\ndata: {"stream_id": "..."}\n\n`
   - For every event the generator yields, append it to the Redis buffer `chat:stream:{stream_id}` with a monotonic `seq` (use `INCR chat:stream:{stream_id}:seq` for the seq number, then `RPUSH chat:stream:{stream_id}:events` the JSON-encoded event). Set `EXPIRE` to 300s on both keys on every append (sliding window).
   - On stream completion, emit `event: complete` with the final `seq` and KEEP the buffer for the remaining TTL (so a client that reconnects after completion can still replay).
2. Add a new endpoint `GET /api/v1/chat/streams/{stream_id}/replay?since={seq}` that reads events with `seq > since` from the Redis buffer and returns them as a JSON array. If the buffer is gone (key doesn't exist), return 404 so the client knows to fall back to the message API.
3. Read `backend/app/services/AGENTS.md` §7-9 — substrate events go through `BudgetEnforcer`, tools need `CapabilityToken`. Confirm the Redis buffer append is a pure cache write (not a tool call) so it doesn't need a CapabilityToken. If the AGENTS.md is ambiguous, note it in your report.

**Steps (client side):**

1. Read `useStreaming.ts` (598+ lines — it was modified by Task 2.5 for `onSaveFailed`). Identify the fetch call, `AbortController` lifecycle, error paths.
2. Add a `connectionState: 'idle' | 'streaming' | 'reconnecting' | 'error'` state. Expose from the hook return.
3. On stream start, capture the `stream_id` from the first `stream_start` event. Store in a `useRef`.
4. Track `lastSeq` (the last `seq` seen in any SSE event) in a `useRef`.
5. On reconnect:
   - If the stream is still in-flight (no `complete` event seen): call `GET /api/v1/chat/streams/{stream_id}/replay?since={lastSeq}`, apply the replayed events to the message state, then re-open the SSE stream with `Last-Event-ID: {lastSeq}` header.
   - If the stream is settled (assistant message committed): re-fetch the final message from `GET /api/v1/chat/threads/{thread_id}/messages` and apply. Do NOT replay.
6. Exponential backoff: 1s → 2s → 4s → 8s → 16s, max 5 retries, jitter ±500ms. After 5, give up + `sonner.error("Connection lost", { action: { label: "Retry", onClick: ... } })`.
7. Do NOT reconnect if `stoppedRef.current === true`. Do NOT reconnect on 4xx.
8. In `SSEChat.tsx`, render a thin "Reconnecting…" banner when `connectionState === 'reconnecting'`. Check if `ConnectingOverlay.tsx` fits — if not, inline banner.

**Server tests (`test_sse_reconnect_buffer.py`):**
- Start a stream, append 3 events to the buffer, simulate a reconnect with `since=1`, assert events 2 and 3 are returned
- Simulate buffer expiry (delete the Redis key), call `/replay`, assert 404
- Assert TTL is set (use `redis.ttl(...)` > 0)

**Client tests (`useStreaming.reconnect.test.tsx`):**
- Mock `fetch` to drop after 2 events; assert the hook reconnects, sends `Last-Event-ID`, applies replayed events
- Assert give-up after 5 retries surfaces the toast
- Assert no reconnect when `stoppedRef.current === true`
- Assert no reconnect on 4xx

**Verification:**
```bash
docker compose exec backend python -m pytest app/tests/test_sse_reconnect_buffer.py -v
cd /home/glenn/FlowmannerV2-frontend && npx vitest run src/hooks/__tests__/useStreaming.reconnect.test.tsx
cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit
```

**Commit messages (one per logical change):**
- `feat(chat): add server-side Redis event buffer for SSE replay (Task 1.2b)`
- `feat(chat): add /replay endpoint for SSE stream resumption (Task 1.2b)`
- `feat(chat): add client SSE reconnect with Last-Event-ID + backoff (Task 1.2b)`

---

## Tasks 1.3, 1.4, 1.6, 1.7 — UNCHANGED

Run these as specced in the 2026-07-06 prompt (`.sisyphus/plans/chat-wiring-deepseek-prompt-2026-07-06.md` Task 1.3, 1.4, 1.6, 1.7). Do NOT re-derive them here — the original specs are still valid. The only change: when Task 1.3 (collapse triple state) touches `chat_service.py`, it will import from the new leaf modules instead of the inline functions. That's the only integration point.

---

# PHASE 2: Activate Dead Code (amended)

Tasks 2.1, 2.2, 2.4, 2.6, 2.7 remain as specced in the 2026-07-06 prompt. Task 2.8 (below) is NEW. Tasks 2.3 (pagination, shipped) and 2.5 (save recovery, shipped) are DONE.

**Amendment to Task 2.1:** Round 2 verified `_prune_messages_to_budget` ALREADY EXISTS at `chat_service.py:1005` (it was not there when the 2026-07-06 plan was written, or the plan didn't notice it). Task 2.1 is now WIRE not BUILD: call `_prune_messages_to_budget` from `_build_chat_messages` (or, after Task 0.2, from `chat_context.py`'s `_build_chat_messages`) after the `max_history=20` first-pass cap. Keep `max_history=20` as the DB-load cap; prune to `settings.CHAT_CONTEXT_TOKEN_BUDGET` (add to `app/config.py` if absent, default 6000) after the fetch.

**Amendment to Task 2.2:** Round 2 confirms `platform-models.ts` is a hardcoded `ModelInfo[]` with no capability data. Task 2.2 is unchanged. Note: the model capability registry produced here is ALSO needed by Task 3.2 (computed allowlist needs `model_supports_tool_calling` check — the capability data is the source). Sequence: Task 2.2 before Task 3.2.

---

## Task 2.8: Consolidate fresh-session patterns into one `fresh_session()` wrapper

**Effort:** S (~1 hour)
**Files:**
- Create: `backend/app/services/fresh_session.py` (or add to `backend/app/database.py` if that's the natural home — check where `AsyncSessionLocal` is defined first)
- Modify: `backend/app/services/chat_service.py` — replace the 3 existing `AsyncSessionLocal()` sites (lines 613, 1172, 1392) + the save-recovery retry site (near 613, added by Task 2.5) with the wrapper

**Background:** Round 2 verified 3 `AsyncSessionLocal()` sites (613, 1172, 1392) plus the save-recovery retry's 4th pattern. The pattern is spreading — consolidating now stops it at 4 instead of 5+. This is the "cheap insurance" task: one reusable async context manager, then every site is a single import instead of a bespoke copy. The pool-knob framing (Round 2 §2): no pool setting eliminates fresh sessions because the problem is holding a transaction open across a multi-minute LLM await. The wrapper makes the discipline explicit and enforced.

**Design (from Round 2 §2):**
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def fresh_session():
    """Open a short-lived AsyncSession that commits on success, rolls back on exception.

    Use this for writes that must NOT hold a transaction open across a long-running
    operation (LLM stream, tool execution). The caller does NOT own this transaction —
    fresh_session does.
    """
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
```

**Steps:**

1. Check where `AsyncSessionLocal` is defined — grep `class AsyncSessionLocal\|AsyncSessionLocal =` in `backend/app/`. If it's in `app/database.py`, add `fresh_session` there. Otherwise create `app/services/fresh_session.py`.
2. Add the wrapper (design above). Match the existing `structlog`/`logging` style — check other modules in the same file for the logger pattern.
3. Replace the 3 existing sites (chat_service.py:613, 1172, 1392) with:
   ```python
   async with fresh_session() as fresh_db:
       # ... existing body, using fresh_db instead of the old var name ...
   ```
   **Verify commit discipline:** the 3 existing sites have inconsistent commit behavior — some commit explicitly, some rely on the caller. The wrapper now commits on success. If a site was committing explicitly, REMOVE the explicit `await db.commit()` (double-commit is a no-op but confusing). If a site was relying on the caller, the wrapper now commits — confirm that's the intended behavior by reading the surrounding 10 lines.
4. Replace the save-recovery retry's 4th fresh-session site (near 613, added by Task 2.5) similarly.
5. Also check: does `app/services/AGENTS.md` §3 ("No `db.commit()` inside a sub-module that doesn't own the transaction") conflict with the wrapper's commit-on-success? It should NOT — the wrapper IS the transaction owner (fresh session, not inherited). Note in your commit body: "fresh_session() owns its transaction (fresh AsyncSession), so the §3 'no commit in sub-modules' rule does not apply — the wrapper is the transaction boundary, not a sub-module of the caller."
6. Recommended pool guardrails (add to the SQLAlchemy engine config in `app/database.py` if not already set — grep `pool_pre_ping` first):
   - `pool_pre_ping=True` (recycled connections don't hand you dead sockets after a long stream)
   - `pool_recycle=3600` (recycle connections every hour)
   - These are READ-ONLY checks — if they're already set, note "already set" and skip. If not, add them.
7. Tests: create `backend/app/tests/test_fresh_session.py`. Test:
   - Successful write: `fresh_session()` commits, row is queryable after the context exits
   - Exception: `fresh_session()` rolls back, row is NOT queryable
   - Nested: calling `fresh_session()` inside another `fresh_session()` does not share a transaction (fresh sessions are independent)

**Verification:**
```bash
docker compose exec backend python -m pytest app/tests/test_fresh_session.py -v
docker compose exec backend python -c "import ast; ast.parse(open('app/services/chat_service.py').read()); print('parse ok')"
docker compose exec backend python -c "from app.services.fresh_session import fresh_session; print('import ok')"
# Verify the existing tests still pass after the wrapper swap:
docker compose exec backend python -m pytest app/tests/test_chat_tool_allowlist.py app/tests/test_fire_and_forget_safety.py -v
```
Expected: fresh_session tests pass; chat_service parses; existing tests still green.

**Commit message:** `refactor(chat): consolidate AsyncSessionLocal patterns into fresh_session() wrapper (Task 2.8) — 4 sites now share one context manager, commit-on-success/rollback-on-exception`

---

# PHASE 3: Amendments to Shipped Tasks (per Round 2)

---

## Task 3.2: Computed allowlist — promote `required_scopes` to primary gate, add `visibility` metadata

**Effort:** L (~4 hours — this is the biggest task in the sprint)
**Files:**
- Modify: `backend/app/tools/base.py` — add `visibility` field to `ToolMetadata` (line 63-86)
- Modify: `backend/app/services/chat_service.py:1677-1828` — `_get_chat_openai_tools` (replace hardcoded `allowed_ids` set with computed intersection)
- Modify: every tool file in `backend/app/tools/` that is in the "exposed + 1.1 candidates" set (24 tools — see step 2) — add `visibility` to their `ToolMetadata`
- Create: `backend/app/tests/test_computed_allowlist.py`

**Dependencies:** Task 2.2 (model capability registry) MUST land first — the computed allowlist needs `model_supports_tool_calling` check, which reads the capability data Task 2.2 produces. If Task 2.2 is not done, do this task WITHOUT the model-capability check (gate that one check behind `if capabilities_available: ...`) and note "model_supports_tool_calling gated on Task 2.2" in your report.

**Background:** Round 2 verified `ToolMetadata` already has `category` (line 67), `required_scopes` (line 78), `tags` (line 75). `_execute_tool_call` already enforces `required_scopes` against cached user scopes (chat_service.py:1704-1763 — the capability gate EXISTS and works). The workspace gate exists (`workspace_models.get_workspace_tool_allowlist()`). The hardcoded `allowed_ids` set in `_get_chat_openai_tools` is doing CURATION work, not security work — `required_scopes` is the actual security boundary. So the fix is: promote `required_scopes` to the primary gate (it already is — just stop maintaining the parallel hardcoded set), add a `visibility` field (`default_on`, `opt_in`, `hidden`) for curation, and compute the exposed set as an intersection of 3 gates.

**Design (from Round 2 §3):**
```python
# End-state in _get_chat_openai_tools:
exposed_tools = [
    tool for tool in registry.list_all()
    if tool.metadata.visibility != "hidden"                          # curation gate
    and workspace_allows(tool.metadata.category, workspace_id)      # workspace gate (exists)
    and user_has_scopes(tool.metadata.required_scopes, user)           # scope gate (exists)
    and model_supports_tool_calling(model_id)                        # capability gate (Task 2.2)
]
```
Adding tool #47 means tagging it, not editing a set.

**Steps:**

1. Add `visibility` field to `ToolMetadata` in `base.py:63-86`:
   ```python
   visibility: str = Field("opt_in", description="default_on | opt_in | hidden — curation, NOT security. required_scopes is the security boundary.")
   ```
   Default `"opt_in"` (safe — must be explicitly turned on). `default_on` for the 13 currently-exposed tools. `hidden` for write tools that shouldn't appear in the tool picker UI even if scoped.
2. Survey and tag the **24 tools** (the 13 currently exposed + the 11 Task 1.1 candidates). For each, set `visibility`:
   - `default_on`: the 13 currently in `safe_chat_ids | phase2_readonly_ids` + `sandboxd_*` (if sandboxd enabled)
   - `opt_in`: the 11 Task 1.1 candidates (`dall_e_image_gen`, `crypto_market_data`, `global_news_aggregator`, `wikipedia_fetcher`, `wikipedia_fetcher`, `arxiv_paper_finder`, `google_search_api`, `fact_check_validator`, `html_to_markdown`, `pdf_parser`, `ocr_text_extractor`)
   - `hidden`: `google_workspace_hub` (mixed read/write — keep hidden until a later task splits its read methods into a separate tool ID), `gmail_sender`, `linkedin_publisher`, any write tool
   - Do NOT tag the remaining 93 tools — they stay `visibility="opt_in"` by default (the safe default). They can be promoted lazily later. This is the "narrow scope" decision.
3. Modify `_get_chat_openai_tools` (chat_service.py:1677-1828) to compute `exposed_tools` per the design above. DELETE the hardcoded `safe_chat_ids | phase2_readonly_ids | sandboxd_ids` set construction. Keep the workspace gate call (`workspace_models.get_workspace_tool_allowlist`). Add the `model_supports_tool_calling` check IF Task 2.2 is done; otherwise gate it behind `if capabilities_available`.
4. **Critical safety check:** after deleting the hardcoded set, run the existing allowlist test to confirm write tools (`slack_post_message`, `linear_create_issue`) are STILL absent. They should be — `required_scopes` blocks them. If a write tool appears in the computed set, the scope gate has a bug — STOP and report.
5. Update the ADR-001 comment block (chat_service.py:1607-1638) to document the new computed-allowlist architecture: "Visibility tags are curation. required_scopes is security. The hardcoded phase sets are deleted."
6. Tests (`test_computed_allowlist.py`):
   - Call `_get_chat_openai_tools(db=mock, workspace_id=mock, user=mock)` and assert `default_on` tools are present, `opt_in` tools are present (different from before — they were absent), `hidden` tools are absent
   - Assert `slack_post_message`, `linear_create_issue` (write tools) are STILL absent (scope gate)
   - Assert `sandboxd_*` tools are absent when `settings.SANDBOXD_ENABLED=False` (mock the setting)
   - Assert the computed set is the INTERSECTION (remove one tool from `workspace_allows` → it disappears from the computed set; remove a scope from the user → scoped tools disappear)

**Verification:**
```bash
docker compose exec backend python -m pytest app/tests/test_computed_allowlist.py app/tests/test_chat_tool_allowlist.py -v
docker compose exec backend python -c "from app.tools.base import ToolMetadata; print('visibility' in ToolMetadata.model_fields)"
```
Expected: new tests pass; existing allowlist test still passes; `visibility` field exists.

**Commit messages (one per logical change):**
- `feat(tools): add visibility field to ToolMetadata (Task 3.2) — curation tag, NOT security`
- `refactor(chat): compute allowlist from visibility×scope×workspace×capability (Task 3.2) — delete hardcoded sets`
- `feat(tools): tag 24 exposed+candidate tools with visibility metadata (Task 3.2)`

---

## Task 3.3: Fire-and-forget tiers — `BackgroundTaskManager` + Celery for memory extraction

**Effort:** L (~4 hours)
**Files:**
- Create: `backend/app/services/background_task_manager.py`
- Modify: `backend/app/services/chat_service.py` — replace the 3 ephemeral `_safe_fire_and_forget` sites (484, 517, 1407) with `background_task_manager.spawn(...)`; replace the 2 memory-extraction sites (1641, 2286) with Celery `enqueue_durable(...)`
- Create: `backend/app/tasks/memory_extraction_task.py` (Celery task wrapper around the memory-extraction coroutine)
- Create: `backend/app/models/task_record.py` (DB model for durable task records — status, retry_count, last_error)
- Create: an Alembic migration for the `task_records` table
- Create: `backend/app/tests/test_background_task_manager.py`
- Create: `backend/app/tests/test_memory_extraction_celery.py`

**Background:** Round 2 verified Task 1.5's `_safe_fire_and_forget` wrapper (line 38) wraps all 5 sites — but it's a band-aid. Two problems: (1) `asyncio.create_task()` without holding a strong reference can be GC'd mid-flight — the wrapper adds try/except but does NOT hold a ref, so the task can vanish before the except runs. (2) Memory extraction (sites 1641, 2286) is durable work (30-120s LLM call) — losing it silently means flaky memory, the kind of bug you don't notice until a user complains. The fix is two-tier: ephemeral in-process → `BackgroundTaskManager` (ref-held, failures logged, drained on shutdown); durable retryable → Celery + DB task record (so the dashboard can list failures and a human can retry).

**Design (from Round 2 §4):**
```python
# Two-tier pattern:
# Ephemeral (short callbacks, canvas updates, UI-side effects) → BackgroundTaskManager
# Durable (memory extraction: 30-120s LLM call, not acceptable to lose) → Celery + DB task record

# background_task_manager.py:
class BackgroundTaskManager:
    """Holds strong refs to spawned tasks, logs exceptions, drains on shutdown."""
    def __init__(self):
        self._tasks: set[asyncio.Task] = set()
    def spawn(self, coro, *, label: str) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(lambda t: (self._tasks.discard(t), t.exception() and logger.exception("task failed", label=label)))
        return task
    async def drain(self, timeout: float = 5.0):
        if not self._tasks: return
        await asyncio.wait_for(asyncio.gather(*self._tasks, return_exceptions=True), timeout=timeout)
```

The existing `_safe_fire_and_forget` (chat_service.py:38) becomes the internal implementation detail of `BackgroundTaskManager.spawn` — do NOT delete it, do NOT undo Task 1.5. Wrap it in the manager.

**Steps:**

1. Create `background_task_manager.py` with the `BackgroundTaskManager` class (design above). Singleton instance exported as `background_task_manager` (module-level). On app shutdown (grep `app.on_event("shutdown")\|lifespan` in `main_fastapi.py`), call `background_task_manager.drain()`.
2. Create `backend/app/models/task_record.py` — `TaskRecord` model: `id` (UUID), `task_type` (str), `payload` (JSON), `status` (enum: `pending`/`running`/`completed`/`failed`), `retry_count` (int, default 0), `last_error` (text, nullable), `created_at`, `updated_at`. Read `backend/AGENTS.md` "Migration data-mutation convention" before writing the migration.
3. Create the Alembic migration: `docker compose exec backend alembic revision -m "add task_records table for durable fire-and-forget"`. Follow the migration convention (no `DELETE`, use sentinel `UPDATE` if any data mutation needed — likely none here since it's a new table).
4. Create `backend/app/tasks/memory_extraction_task.py` — a Celery task `@celery_app.task(bind=True, max_retries=3)` that takes a `thread_id` + `assistant_message_id`, opens a fresh DB session (use `fresh_session()` from Task 2.8), runs `_maybe_extract_memory_claims(...)`, writes a `TaskRecord` row with status, and on failure retries with exponential backoff.
5. Replace the 3 ephemeral sites (chat_service.py:484, 517, 1407) with `background_task_manager.spawn(_safe_fire_and_forget(coro, label=...), label=...)`. The 3 ephemeral sites are: access-denied audit logging (484, 517), tool cost recording (1407).
6. Replace the 2 memory-extraction sites (1641, 2286) with `memory_extraction_task.delay(thread_id=..., assistant_message_id=...)` + write a `TaskRecord` row with status=`pending`. The Celery task picks it up.
7. Tests (`test_background_task_manager.py`):
   - `spawn()` holds a strong ref — after spawning, `manager._tasks` is non-empty; after the task completes, the ref is discarded
   - Exception in the spawned coro → `logger.exception` called (mock the logger), exception NOT propagated to the caller
   - `drain()` waits for all tasks to complete within the timeout
   - GC test: spawn a task that sleeps 1s, do NOT hold a ref in the test, assert the task still completes (the manager holds it) — this is the key test that proves the GC bug is fixed
8. Tests (`test_memory_extraction_celery.py`):
   - The Celery task writes a `TaskRecord` with status=`pending` on enqueue
   - On success, status → `completed`
   - On failure, status → `failed`, `retry_count` incremented, `last_error` set
   - Mock the Celery broker (use `celery_app.conf.task_always_eager = True` for tests — grep existing Celery tests for the pattern)

**Verification:**
```bash
docker compose exec backend python -m pytest app/tests/test_background_task_manager.py app/tests/test_memory_extraction_celery.py -v
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
docker compose exec backend python -c "import ast; ast.parse(open('app/services/chat_service.py').read()); print('parse ok')"
```

**Commit messages:**
- `feat(chat): add BackgroundTaskManager singleton for ref-held ephemeral tasks (Task 3.3)`
- `feat(chat): add TaskRecord model + migration for durable fire-and-forget (Task 3.3)`
- `feat(chat): migrate memory extraction to Celery + TaskRecord (Task 3.3) — 2 sites`
- `refactor(chat): route 3 ephemeral fire-and-forget sites through BackgroundTaskManager (Task 3.3)`

---

## Task 3.5: Markdown memoization + remove render cap (replaces virtualization half of Task 2.3)

**Effort:** M (~2 hours)
**Files:**
- Modify: `/home/glenn/FlowmannerV2-frontend/src/components/chat/MessageList.tsx` — wrap the message row in `React.memo`, memoize the parsed markdown
- Modify: `/home/glenn/FlowmannerV2-frontend/src/components/chat/MessageList.tsx` — raise or remove the render cap (find it — grep `slice\|MAX_MESSAGES\|render cap` in MessageList.tsx)
- Modify: any shared markdown-rendering component (grep `react-markdown\|ReactMarkdown` in `src/components/chat/`) to memoize the parsed output
- Create: `frontend/src/components/chat/__tests__/MessageList.memoization.test.tsx`

**Background:** Round 2 §8: the bottleneck for chat message lists is almost never DOM node count — it's markdown re-rendering (react-markdown + Mermaid + syntax highlighting re-running on every stream tick). The pagination half of Task 2.3 shipped (good). The virtualization half should be REPLACED with markdown memoization. Gate actual virtualization (tanstack, already installed) behind real data: instrument thread lengths, only build the tanstack integration once >500-message threads are common. This task does the memoization; the instrumentation is a small follow-up.

**Design (from Round 2 §8):**
- `React.memo` on the message row component with a stable key (`messageId`)
- Parsed markdown cached so identical content doesn't re-parse (use `useMemo` on the `children`/`remarkPlugins` output, or a `react-markdown` cache wrapper)
- During streaming of message N, messages 1..N-1 do NOT re-render
- Raise the render cap from 50 (or whatever it is — verify) to 500, or remove it if it's only there to prevent the re-render perf issue (which memoization now addresses)

**Steps:**

1. Read `MessageList.tsx`. Find:
   - The render cap (grep `slice\|MAX\|limit` in the file)
   - The message row component (is it a separate component or inline?)
   - The `ReactMarkdown` usage and which plugins (`remarkGfm`, `remarkMath`, `remarkMermaid`, etc.)
2. Extract the message row into a `React.memo`-wrapped component if it isn't already. The memo comparator should compare `message.id`, `message.content` (for streaming, content changes every tick — so the streaming message DOES re-render, but others don't), and any prop that affects rendering (tool call state, citation state).
3. Memoize the parsed markdown: wrap the `ReactMarkdown` + plugins in a `useMemo` keyed by `message.content`. If `react-markdown` doesn't support `useMemo` directly (it renders, doesn't return a parse tree), create a small `<MemoizedMarkdown content={content} />` component that wraps `ReactMarkdown` in `React.memo` with a content comparator.
4. Raise the render cap: find the `slice(0, 50)` or equivalent. Change to 500. If there's no cap, note "no render cap found — skipping this step."
5. Instrument thread lengths: add a small `console.log` or a Prometheus counter (grep `useMetrics\|trackEvent` in the frontend for the pattern) that logs the thread message count on load. This is the data-gathering step that gates future virtualization. Keep it lightweight — one log per thread load.
6. Tests (`MessageList.memoization.test.tsx`):
   - Render 50 messages, trigger a re-render of the parent, assert only the streaming message re-renders (use a render-count spy — `jest.fn()` on the memoized row)
   - Assert `React.memo` prevents re-render of messages with identical `id` + `content`
   - Copy the mock pattern from existing MessageList tests — grep `MessageList.test.tsx\|MessageList.memory` in `__tests__/`

**Verification:**
```bash
cd /home/glenn/FlowmannerV2-frontend && npx vitest run src/components/chat/__tests__/MessageList.memoization.test.tsx
cd /home/glenn/FlowmannerV2-frontend && npx vitest run src/components/chat/
cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit
```

**Commit messages:**
- `perf(chat): memoize MessageList rows so streaming doesn't re-render history (Task 3.5)`
- `perf(chat): raise render cap to 500 + instrument thread lengths (Task 3.5)`

---

# Things you MUST NOT do in this sprint

- ❌ Run `deploy-frontend.sh`, `deploy-backend.sh`, `docker compose up`, `docker build`, `rsync`, `ssh` to VPS. Source edits only.
- ❌ Decompose `chat_service.py` TRUNK — that's Phase 4, a separate sprint. Your Phase 0 edits EXTRACT leaves (additive: new files + import swaps in chat_service.py). They do NOT move the tool loop or the streaming lifecycle.
- ❌ Replace the fresh-session pattern with a task queue — that's Phase 5. Task 2.8 is a context-manager consolidation, NOT a queue migration. Only the 2 memory-extraction sites in Task 3.3 go to Celery.
- ❌ Build multi-user chat, conversation summarization, or canvas tile generalization — Phase 4+ (out of scope).
- ❌ Write meta-docs, handoff docs, or exit audits. The `SESSION-RITUAL.md` exit audit is run by the human at end-of-session, NOT by you.
- ❌ Touch the VPS filesystem. The frontend at `/opt/flowmanner/frontend/` is a deploy target, NOT a source. Nginx config is VPS-only.
- ❌ Commit `.env` files, `.sisyphus/exit-audit-*.md`, or anything in `.gitignore`.
- ❌ Re-verify the "Already Verified" table facts (2026-07-06 or Round 2). That's wasted effort — past sessions already grepped them. If you re-find a contradiction, note it but don't burn the cycle preemptively.
- ❌ Skip the verification step on any task. Every task ends with a command-and-paste-output step. If you can't run the command (e.g., the dev-server manual check), say "manual check: pending human verify" — don't pretend.
- ❌ Run `git push --force` or `git reset --hard`. If a rebase conflicts, stop and report.
- ❌ Tag all 117 tools with `visibility` metadata. Task 3.2 tags the 24 exposed + 1.1 candidates ONLY. The long tail stays `visibility="opt_in"` by default (the safe default). Backfill lazily as tools get promoted.
- ❌ Build a parallel capability/permission system. `required_scopes` IS the capability model. Task 3.2 promotes it to the primary gate and adds `visibility` for curation. Do NOT create a new permission system alongside it.
- ❌ Install `react-virtuoso`. `@tanstack/react-virtual` is already installed (unused). Task 3.5 does NOT use either — it does markdown memoization. Virtualization is deferred to Phase 3 (Q3/Q4 roadmap), gated on >500-msg-thread data.
- ❌ Auto-route to DeepSeek/OpenRouter when a 27B-incompatible strategy is picked. That's a SEPARATE prompt (strategy viability UX), and the decision is "visible prompt to switch, not silent auto-route." Do NOT build it in this sprint.

---

# End-of-sprint report (paste this at the END of your final message)

After all tasks, produce this report. Paste raw command output, do not paraphrase.

```
=== SPRINT REPORT — Chat Wiring Amendment (Round 2, 2026-07-07) ===

TASKS COMPLETED:
  Phase 0:
    0.1 llm_providers.py:     [DONE | PARTIAL | BLOCKED] — [functions moved: list them]
    0.2 chat_context.py:      [DONE | PARTIAL | BLOCKED] — [functions moved: list them]
    0.3 sse_protocol.py:      [DONE | PARTIAL | BLOCKED — full serializer extracted OR only constants]
  Phase 1:
    1.2a keepalive ping:      [DONE | PARTIAL | BLOCKED]
    1.2b SSE reconnect+buffer:[DONE | PARTIAL | BLOCKED — server buffer: DONE | PARTIAL; client reconnect: DONE | PARTIAL]
    1.3 state collapse:       [DONE | PARTIAL | BLOCKED — per 2026-07-06 spec]
    1.4 Canvas branching:     [DONE | PARTIAL | BLOCKED — per 2026-07-06 spec]
    1.6 SharedLink drift:    [DONE | NO-OP (no drift) | BLOCKED — per 2026-07-06 spec]
    1.7 FolderManager:      [DONE | PARTIAL | BLOCKED — per 2026-07-06 spec]
  Phase 2:
    2.1 context pruning:    [DONE | PARTIAL | BLOCKED — WIRED _prune_messages_to_budget, not built from scratch]
    2.2 model capabilities: [DONE | PARTIAL | BLOCKED — per 2026-07-06 spec]
    2.4 BYOK validation:    [DONE | PARTIAL | BLOCKED — per 2026-07-06 spec]
    2.6 BYOK encryption:    [DONE | PARTIAL | BLOCKED — per 2026-07-06 spec]
    2.7 ThoughtPanel wiring:[DONE | PARTIAL | BLOCKED — per 2026-07-06 spec]
    2.8 fresh_session wrapper: [DONE | PARTIAL | BLOCKED — 4 sites consolidated]
  Phase 3:
    3.2 computed allowlist: [DONE | PARTIAL | BLOCKED — model_supports_tool_calling: GATED on 2.2 | DONE]
    3.3 fire-and-forget tiers: [DONE | PARTIAL | BLOCKED — BackgroundTaskManager: DONE; Celery migration: DONE | PARTIAL]
    3.5 markdown memoization: [DONE | PARTIAL | BLOCKED]

=== VERIFICATION (raw output) ===

□ cd /opt/flowmanner && git log --oneline -25
  (paste)

□ cd /opt/flowmanner && git status
  (paste — should be clean except for untracked .sisyphus/ files)

□ docker compose exec backend python -m pytest app/tests/test_llm_providers.py app/tests/test_chat_context.py app/tests/test_sse_protocol.py app/tests/test_sse_keepalive.py app/tests/test_sse_reconnect_buffer.py app/tests/test_fresh_session.py app/tests/test_computed_allowlist.py app/tests/test_background_task_manager.py app/tests/test_memory_extraction_celery.py app/tests/test_chat_tool_allowlist.py app/tests/test_fire_and_forget_safety.py -v 2>&1 | tail -40
  (paste)

□ cd /home/glenn/FlowmannerV2-frontend && npx vitest run src/hooks/__tests__/useStreaming.reconnect.test.tsx src/components/chat/__tests__/MessageList.memoization.test.tsx 2>&1 | tail -20
  (paste)

□ cd /home/glenn/FlowmannerV2-frontend && npx vitest run src/components/chat/ src/hooks/__tests__/useStreaming.*.test.tsx 2>&1 | tail -30
  (paste)

□ cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit
  (paste — should be empty)

□ docker compose exec backend alembic current
  (paste — should show the new task_records migration at head)

□ docker compose exec backend python -c "from app.services.llm_providers import _resolve_provider; from app.services.chat_context import _build_chat_messages; from app.services.fresh_session import fresh_session; from app.services.background_task_manager import background_task_manager; print('all leaf imports ok')"
  (paste)

=== BLOCKERS / NOTES ===
- [any task that's PARTIAL/BLOCKED — explain why + exact file:line]
- [if Task 3.2's model_supports_tool_calling is gated on Task 2.2, note it]
- [if Task 0.3 found SSE emission inline in the generator and only extracted constants, note "full serializer deferred to Phase 4"]

=== CRITIQUE CORRECTIONS ===
- [if you found another stale claim in the 2026-07-06 plan or the Round 2 analysis, list it here — file:line evidence]

=== END ===
```

---

## Final reminder

This sprint is grounded in TWO code-level audits that ALREADY verified the key facts (2026-07-06 critique + 2026-07-07 Round 2 deep-dive). Do not re-audit. Do not re-grep the "Already Verified" or "Round 2 Verified" tables. Open the file, make the edit, run the test, paste the output, commit, move on. If a task is blocked, say so plainly — do not invent a partial implementation to hide the blocker.

**You are the executor, not the planner.** The plan is already written — and amended per Round 2. Your value is shipping code that passes its tests, not re-deriving the plan. The 8 decisions Glenn already made are baked into this prompt. If you find a 9th decision that needs Glenn's input, STOP and report — do not guess.

**Phase 0 (leaf extraction) runs in PARALLEL with Phase 1/2.** That's the whole point of extracting leaves — no trunk-line conflicts. Do Phase 0 first if you can (it unblocks nothing but it's clean), or interleave it with Phase 1/2. The only requirement: Phase 0 commits should be pure move-with-import-swap (no behavior change), individually reviewable.

**The dual-write decision is OUT of scope.** `docs/DUAL-WRITE-DECISION.md` already recommends Option (a). Glenn approved it. It gets a separate prompt after this sprint lands.

**The 27B strategy viability UX is OUT of scope.** Glenn decided "visible prompt to switch, not auto-route." It gets a separate prompt, gated on Phase 1 of the Q3/Q4 roadmap (strategy profiling).

**Nginx `proxy_buffering off` + `proxy_read_timeout 300s` is Glenn's manual VPS edit,** done before or same-day as Task 1.2a ships. Do NOT attempt it from the agent — you can't SSH the VPS.
