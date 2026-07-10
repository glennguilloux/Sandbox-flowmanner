# W2 Analysis — Chat / SSE Streaming Subsystem

**Date:** 2026-07-07
**Author:** W2 analysis worker (subagent)
**Scope:** `/opt/flowmanner/backend` chat + SSE streaming subsystem
**Read-first note:** The brief `PLATFORM-FOUNDATION-BRIEF-2026-07-07.md` was **not present** at `/opt/flowmapper/.sisyphus/analysis/`. The actual repo lives at `/opt/flowmanner` (the task's `/opt/flowmapper` path is a typo of the workspace dir `/opt/flowmanner`). I grounded this analysis directly in the real source: `chat_service.py`, `sse_protocol.py`, `sse_buffer.py`, `llm_providers.py`, `chat_context.py`, `background_task_manager.py`, `database.py`, `nginx/default.conf`, and the `docs/ROADMAP-Q3-Q4-2026.md` + `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` roadmap context. Phase 1 in the roadmap is "Strategy Profiling & AI Quality Gate ✅ COMPLETE"; the SSE/Chat wiring work is the W2 / Phase 1.3 track.

---

## 1. SSE Event Taxonomy & What `canvas_update` Actually Does

### 1.1 The 10 event types (constants in `app/services/sse_protocol.py`)

| Constant | String value | Where emitted | Payload shape |
|----------|--------------|---------------|---------------|
| `SSE_EVENT_STREAM_START` | `"stream_start"` | **NOT in `stream_message_to_llm`** — emitted ONLY by `sse_buffer.get_stream_buffer()` | `event: stream_start\ndata: {"stream_id": "..."}` (SSE-framed in `sse_buffer.py:113`) |
| `SSE_EVENT_TOKEN` | `"token"` | `chat_service.py:1755` (per content delta) and `:1916` (non-stream retry fallback) | `{"type":"token","content": "..."}` |
| `SSE_EVENT_TOOL_CALL_START` | `"tool_call_start"` | `chat_service.py:1817` | `{"type","tool","arguments","call_id"}` |
| `SSE_EVENT_TOOL_CALL_RESULT` | `"tool_call_result"` | `chat_service.py:1841` | `{"type","tool","result","call_id"}` |
| `SSE_EVENT_CANVAS_UPDATE` | `"canvas_update"` | `chat_service.py:1854` (via `_build_canvas_update`, only when tool warrants) | `{"type":"canvas_update","data":{"action":"open_tile",...}}` |
| `SSE_EVENT_MEMORY_RECALL_USED` | `"memory_recall_used"` | `chat_service.py:1964` | built by `build_recall_used_event(claim, message_id)` |
| `SSE_EVENT_MEMORY_CITATION` | `"memory_citation"` | `chat_service.py:1973` | built by `build_citation_event(claim, message_id)` |
| `SSE_EVENT_COMPLETE` | `"complete"` | `chat_service.py:2002` | `{"type","full_response","message_id","model"}` |
| `SSE_EVENT_ERROR` | `"error"` | `chat_service.py:1612` (BYOK mismatch), `:2015` (circuit open), `:2025` (generic) | `{"type":"error","error":"..."}` |
| `SSE_EVENT_SAVE_FAILED` | `"save_failed"` | `chat_service.py:1956` (assistant msg save failed 3×) | `data: {"type":"save_failed","content": full_response[:500]}` |

**Framing reality (important):** The generator `stream_message_to_llm` yields **bare `json.dumps(...)` strings with NO `data:` prefix**. The SSE framing (`data: {chunk}\n\n`) is applied one layer up in `app/api/v1/chat.py:_sse_stream` (line 369). `stream_start` and `save_failed` are the two exceptions that are *already* `data:`-framed inside `sse_buffer.py` / `chat_service.py` — so when wrapped by `_sse_stream` they become `data: data: {...}` (double-framed). `stream_start` is emitted by `get_stream_buffer` which runs *outside* `_sse_stream`, so it is correctly framed once. `save_failed` is emitted by the generator *inside* `_sse_stream`, so it is double-framed — a latent bug worth noting for the W2 cleanup.

**Terminator:** `_sse_stream` appends a final `data: [DONE]\n\n` (line 370) after the generator is exhausted. The frontend's `EventSource`/`useStreaming` hook therefore sees `stream_start → token* → (tool_call_start/result/canvas_update)* → memory_recall_used* → memory_citation* → complete → [DONE]`.

### 1.2 What `canvas_update` actually does — the tile mapping

`_build_canvas_update` (`sse_protocol.py:43`) is the **only** place a canvas tile is opened. The mapping table `_CANVAS_UPDATE_TOOLS` currently has exactly **one** entry:

```python
_CANVAS_UPDATE_TOOLS = {
    "browser_sandbox": {"tileKind": "browser-sandbox", "titlePrefix": "Browse"},
}
```

So the full behavioral contract is:
- The event is emitted **only after** a `tool_call_result` for `tool_name == "browser_sandbox"`.
- `_build_canvas_update` parses the tool result JSON; it **returns None** (no event) when:
  - the result isn't valid JSON / isn't a dict,
  - `result.error` is truthy, or
  - `result.action != "launch"` (i.e. a `navigate`, `click`, `screenshot`, etc. action does **not** open a tile — only `launch` does).
- On a successful `launch`, it emits:
  ```json
  {"type":"canvas_update","data":{
     "action":"open_tile",
     "tileKind":"browser-sandbox",
     "title":"Browse: <preview_url>",
     "payload":{"sandbox_id":"...","preview_url":"...","status":"running"}
  }}
  ```
- The frontend receives this and **auto-opens a `browser-sandbox` tile** (the noVNC/sandboxd preview iframe) without any user click. This is the agent-driven tile orchestration hook described in `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` Phase 4 / `RESEARCH-ROADMAP` §4 — the canvas-first future built on top of SSE.

**Key takeaway for the roadmap:** `canvas_update` is currently a single-tool, single-tile mechanism. It is *extensible by design* (`_CANVAS_UPDATE_TOOLS` is explicitly the extension point), but right now only `browser_sandbox` triggers any tile. Any Phase-3 Canvas work that wants chat/code-sandbox/agent-reasoning tiles to pop automatically must add entries here — the plumbing supports it, the content doesn't yet exist.

---

## 2. Why the SSE Keepalive Is Effectively MISSING (the Phase 1.3 gap)

The brief flags keepalive as a Phase 1.3 gap. The source shows the keepalive code *exists* but is **yield-gated, not timer-driven** — which is the real gap.

### 2.1 What the code actually does

- `_SSE_KEEPALIVE_INTERVAL = 15` (seconds), `chat_service.py:196`.
- `_sse_keepalive(last_yield, now)` (`chat_service.py:199`) returns `": ping\n\n"` only if `now - last_yield > 15`, else `None`.
- It is called at exactly **three** yield points inside `stream_message_to_llm`:
  1. `:1608` — before a BYOK mismatch `error` (edge case, rarely hit).
  2. `:1751` — right after emitting each `token` (so pings are folded into token cadence).
  3. `:1868` — after a tool executes (the longest idle gap, where it matters most).

### 2.2 The actual gap

`proxy_read_timeout` for `/api/` is **300s** (`nginx/default.conf:97`), and the `/ws` WebSocket block is `86400s`. The keepalive *would* protect the 300s window *if* it could emit during silent upstream gaps. But:

- **There is no background timer task emitting pings.** `_sse_keepalive` only runs at existing `yield` moments. During the **initial LLM "thinking" gap** — the `await client.chat.completions.create(...)` at `:1731` before the first chunk arrives — the generator is blocked on the network. `_last_yield` was set just before that await (line 1601, from stream start), so if the model thinks for 60s, **zero bytes cross the wire for the entire 60s**. A `: ping` is only produced at the *first* token (line 1751: `now - _last_yield = 60 > 15 → emit one ping, then reset`).
- Within a tool round there is one ping after execution (line 1868), but a tool that itself blocks on a slow upstream for >300s with no intermediate yield would still trip `proxy_read_timeout`.
- `_sse_keepalive` emits a **bare SSE comment** `": ping\n\n"` *without* a `data:` prefix, and it is yielded *through* `_sse_stream` which wraps it as `data: : ping\n\n\n\n`. A bare comment line is correct SSE, but the double-newline wrapping is sloppy and the comment is non-semantic.

So: **keepalive is present as a helper but not as a guarantee.** The W2 fix is a *timer-driven* ping — either a `BackgroundTaskManager.spawn` coroutine that sleeps `interval` and `yield`s a ping every N seconds regardless of token cadence, or a `StreamingResponse`-level heartbeat. This is exactly the "Tasks 1.2a (keepalive)" item the `sse_protocol.py` header calls out as still-to-do.

### 2.3 How Nginx currently handles it (verbatim)

`nginx/default.conf` `/api/` block (lines 84–98):
```
    # ── Backend API (FastAPI on homelab via WireGuard) ──────────────────
    # SSE support: proxy_buffering off ensures streaming responses
    # (chat, HITL, notifications, mission events) are forwarded
    # chunk-by-chunk instead of buffered until complete.
    location /api/ {
        proxy_pass http://10.99.0.3:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization $http_authorization;
        proxy_buffering off;
        proxy_read_timeout 300;
    }
```

- `proxy_buffering off;` — **shipped & deployed** (commit `205a99d2`, per `plans/NEXT-SESSION.md:13,23`, deployed to `flowmanner-nginx`). This is the correct and necessary setting: without it Nginx buffers the whole SSE body until the stream ends, defeating streaming.
- `proxy_read_timeout 300;` — 300s. The FastAPI route also sends `X-Accel-Buffering: no` (chat.py:408) as a belt-and-suspenders directive telling Nginx not to buffer this specific response.
- **Gap on the Nginx side:** there is **no `proxy_send_timeout`** override and **no `proxy_timeout`** (the stream-level timeout for `proxy_http_version 1.1` long-lived connections). The 300s `proxy_read_timeout` is generous enough that the *current* yield-gated keepalive usually survives, which is why the gap hasn't bitten in production yet — but it's a quiet dependency: streaming liveness is borrowed from Nginx's 300s window, not from real heartbeat bytes. For Phase 1.3 robustness (and to support reconnect/replay via `sse_buffer`), a backend timer-ping is the durable fix; Nginx should additionally get `proxy_send_timeout 300;` for symmetry.

---

## 3. What `fresh_session()` + `BackgroundTaskManager` Actually Bought — "Perception, Not Plumbing"

Phase 1 (per `ROADMAP-Q3-Q4-2026.md:51`, "Strategy Profiling & AI Quality Gate ✅ COMPLETE") was about **getting the platform to *perceive and survive* streaming in production**, not about adding features. Two shipped primitives made that real:

### 3.1 `fresh_session()` (`database.py:73`) — the idle-in-transaction fix

- Before: `stream_message_to_llm` held the caller's `AsyncSession` open across the entire LLM call + tool loop. PostgreSQL's `idle_in_transaction_session_timeout` (set in `database.py:19`) kills such connections → "idle-in-transaction" deaths mid-stream, corrupting the conversation.
- The fix in the generator: save the user message, `await db.commit()`, then **`await db.close()`** (`:1711–1713`) *before* `client.chat.completions.create`. All later writes use a **brand-new short-lived session** via `create_chat_message_fresh_session` (`:1947`), which wraps `fresh_session()`.
- `fresh_session()` owns its own transaction (commit on success, rollback on exception) — explicitly exempt from the AGENTS.md §3 "no commit in sub-modules" rule *because it is the boundary*, not a sub-module.
- **What it bought:** streams no longer die when the upstream LLM thinks for 30–120s. This is *perception* — the system now reliably *shows* the conversation progressing — not *plumbing feature work*. The streaming capability existed; its reliability in production did not.

### 3.2 `BackgroundTaskManager` (`background_task_manager.py`) — GC-safe fire-and-forget

- Replaces raw `asyncio.create_task(...)` calls that didn't hold strong refs (tasks could be garbage-collected mid-flight — a silent failure mode).
- `.spawn(coro, label=)` holds the task in a `set`, attaches a `_on_task_done` callback that discards it and logs unhandled exceptions (via `_safe_fire_and_forget`), and `.drain(timeout=5.0)` on shutdown waits for in-flight tasks.
- Used for non-blocking side effects: `_record_tool_cost_fire_and_forget` (`:1834`), durable memory extraction via Celery (`:1979`), usage recording (`:1991`).
- **What it bought:** background side effects (cost tracking, memory extraction, usage metering) now *actually fire and are observable* in logs instead of vanishing to GC. Again — perception/observability, not new capability. The memory extraction and usage recording were already "in the code"; they just weren't *guaranteed to run*.

**Why Phase 1 = "perception not plumbing":** Both primitives fix *survivability and observability* of a streaming system that already worked in the happy path. They make the platform *perceive* (log, meter, survive) what it was already doing. The roadmap's real feature work — tool-registry v1, agent-step streaming, canvas tiles — is Phase 1→2 forward, and it stands on this reliability floor. The W2 SSE analysis (keepalive, `stream_start` framing, double-framed `save_failed`) is the *remaining* perception/plumbing debt from this same track.

---

## 4. Two-Pane Chat UI Default Simplification Proposal

**Constraint:** The frontend (`/home/glenn/FlowmapperV2-frontend/`) is **not present on this machine** — only the backend and the roadmap docs are. I could not read `floating-nav.tsx` (task said it was already gated this session, but the file path does not exist here). The proposal below is therefore grounded in the backend event contract (§1) and the documented frontend architecture in `docs/RESEARCH-ROADMAP-HYBRID-PLATFORM-2026-07-05.md` §4 and `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md`.

### 4.1 Current surface (from docs)

- `ChatLayout.tsx` is a **3-column** layout: thread sidebar / message area / right "cockpit". It carries heavy **decorative chrome**: `MatrixRain.tsx` (full-screen canvas, black bg, glowing katakana/CJK/Arabic/Greek/Hebrew/Runic rain) was swapped in to replace `TopographicBackground.tsx` (preserved, no longer rendered). Plus Zen mode, mobile layout, and a `LaunchPad` surface.
- The right cockpit hides tool-call cards, agent steps, reasoning, permissions, cost — the exact data the SSE stream *already emits* (`tool_call_start`, `tool_call_result`, `memory_recall_used`, `memory_citation`, `canvas_update`).

### 4.2 Proposed default: a **two-pane** baseline, progressive-reveal

Collapse the 3-column default to **two panes** and move everything else behind explicit reveal:

| Pane | Default content | Source |
|------|----------------|--------|
| **Left (narrow, collapsible)** | Thread list + New + Search. Collapses to a hamburger on first paint. | existing sidebar |
| **Center (primary)** | The chat stream — tokens, tool-call cards *inline-collapsed*, agent-step chips *inline-collapsed*, memory citation chips. | `token`, `tool_call_start/result`, `memory_citation` |
| **Right cockpit** | **Hidden by default.** Becomes a reveal-on-demand drawer (toggle in the top bar) that expands the collapsed tool/agent/cost cards. | existing cockpit |

**Progressive-reveal rules (mapped to SSE events):**
1. **Tool calls:** render `tool_call_start`/`tool_call_result` as a **collapsed inline card** by default (one line: tool name + status). Click to expand args + result. This keeps the stream readable for 90% of users who just want the answer, while surfacing the full trace for the 10% who debug.
2. **Agent steps / reasoning:** sub-chips under each message, collapsed by default (`reasoning → tool → result → final`). Expand-on-click. (Phase 2 work; the event hooks exist once substrate events are glued in.)
3. **Memory citations:** always show the small `memory_citation` chip (cheap, high-trust signal) — but the verbose `memory_recall_used` metadata stays in the reveal drawer.
4. **canvas_update tiles (`browser-sandbox`):** these *should* still auto-open (that's the point of the event) — but only when `action == "launch"`. Non-launch tool actions must NOT spawn tiles. Cap concurrent auto-opened tiles to 1–2; queue the rest behind a "Open in canvas" affordance so the screen isn't hijacked mid-conversation.
5. **Decorative chrome — demote by default:**
   - `MatrixRain` / `TopographicBackground`: gate behind a **settings toggle** (the original plan's "optional theme toggle", EXIT-AUDIT-2026-06-28-matrix-rain-theme.md Step 4). Default to a **static, low-cost background** (solid `bg-cream` or a single static gradient) so first paint is fast and the canvas animation only runs when the user opts in — and always honor `prefers-reduced-motion` (already implemented in MatrixRain) plus `visibilitychange` pause (already implemented).
   - `LaunchPad` and **Zen mode**: keep Zen mode as the *primary* simplification toggle (one click → single chat column, chrome gone). LaunchPad becomes a command-palette (⌘K) entry, not a default-visible surface.
6. **Nav gating (floating-nav):** the session's nav-gating work should default the chat route to the two-pane baseline and treat the 3-column canvas as an *upgrade* the user opts into, not the entry state.

### 4.3 Why this grounds the roadmap

The backend already emits every event the simplified UI needs — `token`, `tool_call_*`, `memory_citation`, `canvas_update` — so the two-pane simplification is **pure frontend information architecture**, zero backend changes required. The only backend-adjacent item is §2's timer-driven keepalive (so the simplified UI doesn't show a frozen spinner during 60s model think-time). This makes "simplify the default" a cheap, high-leverage W2 deliverable that de-risks the heavier Phase 3 Canvas re-imagining — ship the two-pane now, let Canvas be the progressive reveal.

---

## 5. Open Issues / Bugs Found (for W2 cleanup backlog)

1. **Double-framed `save_failed`** — `chat_service.py:1956` yields `f"data: {save_failed_payload}\n\n"` which `_sse_stream` wraps again → `data: data: {...}`. Frontend SSE parsers may choke or double-parse. Fix: emit the bare JSON (like `token`/`error`) and let `_sse_stream` frame it, OR `yield` it outside `_sse_stream`.
2. **`stream_start` only on the `sse_buffer` path** — if a route calls `stream_message_to_llm` *without* `get_stream_buffer` (e.g. the v2 chat route at `app/api/v2/chat.py:481`), there is **no `stream_start` event** and no Redis replay buffer. The two routes have divergent SSE envelopes. W2 should standardize on the buffered path (or document the divergence).
3. **Keepalive is yield-gated, not timer-driven** (see §2) — the Phase 1.3 fix.
4. **`memory_recall_used` vs `memory_citation` duplication** — both loop over the same `memory_recall_claims` list (`:1963` and `:1972`) emitting per-claim events; frontend must correlate by `message_id` + claim id. Low risk but worth a single combined event to reduce payload.
5. **Nginx symmetry** — add `proxy_send_timeout 300;` to `/api/` to match `proxy_read_timeout` once timer-pings land.

---

*Generated from source read at `/opt/flowmanner/backend` on 2026-07-07. No code edited, no deploy, no commit (per constraints). Foundation brief file was absent; analysis grounded in live source + `docs/ROADMAP-Q3-Q4-2026.md`, `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md`, `docs/RESEARCH-ROADMAP-HYBRID-PLATFORM-2026-07-05.md`. Frontend tree not present on this host; §4 grounded in those docs + the backend event contract.*
