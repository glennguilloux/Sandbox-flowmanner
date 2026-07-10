# W2 — Chat / SSE Streaming Subsystem (VERIFIED 2026-07-10)

**Date:** 2026-07-10
**Worker:** roadmap deep-analysis (claimed `t_e9f6e019`)
**Grounding:** `/opt/flowmanner/backend/app` + `/opt/flowmanner/nginx/default.conf` — re-grepped live 2026-07-10.
**Corrected premise:** the task body says *"why SSE keepalive ping is missing (Phase 1.3)"*. **That is stale.** The keepalive IS implemented (`chat_service.py:201-209`, timer-driven, 15s, via `BackgroundTaskManager`). Nginx `/api/` already sets `proxy_buffering off; proxy_read_timeout 300;`. Phase 1.3 is **DONE**, not open. See `W2-chat-sse.md` (prior, also predates the keepalive landing).

---

## 0. Measured facts (live)

| Item | Verified location | State |
|------|------------------|-------|
| SSE event taxonomy | `sse_protocol.py:23-32` | 11 constants defined |
| `canvas_update` mapping | `sse_protocol.py:38-40` | 1 entry: `browser_sandbox` |
| `_build_canvas_update` | `sse_protocol.py:43-` | pure helper, returns None unless tool in map |
| Keepalive ping | `chat_service.py:201-209` | **IMPLEMENTED** (was "missing" in brief) |
| `fresh_session()` | `database.py:73-90` | owns its own txn, commit/rollback |
| `BackgroundTaskManager` | `background_task_manager.py:43` | strong-ref task wrapper |
| Nginx SSE | `nginx/default.conf:96-97` | `proxy_buffering off; proxy_read_timeout 300;` |

---

## 1. SSE event taxonomy (11 events, `sse_protocol.py`)

`stream_start`, `token`, `tool_call_start`, `tool_call_result`, `canvas_update`, `memory_recall_used`, `memory_citation`, `complete`, `error`, `save_failed`.

Notes:
- `stream_start` is emitted **only** by `sse_buffer.get_stream_buffer()` (Redis-buffered path), not by `stream_message_to_llm` directly.
- `token` carries content deltas; `complete` carries `{full_response, message_id, model}`.
- `memory_recall_used` / `memory_citation` are emitted at `chat_service.py:1964/1973` — these render citations from SSE metadata, **not** parsed from text (per brief §4).

---

## 2. What `canvas_update` actually does

- `_CANVAS_UPDATE_TOOLS` (`sse_protocol.py:38`) is a **single-entry map**: `{"browser_sandbox": {tileKind: "browser-sandbox", titlePrefix: "Browse"}}`.
- `_build_canvas_update(tool_name, result_json)` returns `None` unless `tool_name` is in the map AND the result parses to a non-error dict. So today **only `browser_sandbox` opens a tile**.
- Wired in `chat_service.py:199` (import) and called from the tool-result emission path (`chat_service.py:~1854`, per prior W2 doc).
- **Extensibility:** add entries to `_CANVAS_UPDATE_TOOLS` for new tile types. This is the clean seam for "surface the arsenal in chat" (Phase 1.4 / Phase 2) — e.g. a `pdf_parser` result could open a doc tile.

---

## 3. SSE keepalive — DONE (corrected from "missing")

`chat_service.py:201-209`:
- `_SSE_KEEPALIVE_INTERVAL = 15` seconds.
- `_SSE_KEEPALIVE_PING = ": ping\n\n"` (SSE comment line — `EventSource` ignores it).
- `_sse_keepalive_timer(queue, stop_event)` runs as a `BackgroundTaskManager` task, pumps pings every 15s **independent of token cadence** (a tool round can block the generator >15s; a yield-gated ping would never fire).

Nginx side (`nginx/default.conf:96-97`): `proxy_buffering off;` + `proxy_read_timeout 300;` — correctly handles long idle streams. **No deploy needed** for keepalive; the work is complete.

**Action (verification only):** add a smoke test that a 20s idle tool round does not drop the connection (keepalive should keep nginx's 300s read window alive). This is a test gap, not a code gap.

---

## 4. What `fresh_session` / `BackgroundTaskManager` bought

- **`fresh_session()`** (`database.py:73`): opens a short-lived `AsyncSession` that **owns its own transaction** (commit on success, rollback on exception). Used for fire-and-forget writes that must NOT hold a txn open across an LLM stream or tool execution. This decouples side-effect writes (audit, memory save) from the long-lived chat stream transaction — a real reliability win, not plumbing debt.
- **`BackgroundTaskManager`** (`background_task_manager.py:43`): replaces raw `asyncio.create_task()` (which let tasks be GC'd if no strong ref was held). It holds strong refs, logs exceptions, drains on shutdown. `_safe_fire_and_forget` wraps this. The keepalive timer (§3) runs on it.
- **Why this means Phase 1 is perception, not plumbing:** the streaming mechanism is correct and hardened. The gap is not "does streaming work" — it's "does the first 30 seconds of the UI convey the depth." The engine is done; the front door is not.

---

## 5. Two-pane default simplification (concrete proposal)

Per brief §12.4 / Phase 1.4: default the chat UI to a **focused two-pane** (conversation | canvas) with **progressive-reveal chrome**, and default the decorative backgrounds OFF.

- **Default OFF (config, no rebuild if already env-gated):** `MatrixRain`, `TopographicBackground`, the 3-column / zen / LaunchPad decorative modes. Keep them as opt-in toggles.
- **Two-pane:** conversation pane + canvas pane (tiles open via `canvas_update`, §2). Single-pane on narrow viewports.
- **Progressive reveal:** memory-citation / recall chips appear only when `memory_citation` / `memory_recall_used` events fire — already supported by the SSE taxonomy; the UI just needs to render them by default instead of hiding behind a panel.
- **Verification:** `npx tsc --noEmit` + `next build` locally before handoff (per VPS trust boundary, agent does NOT deploy — Glenn runs `deploy-frontend.sh`).

**Note:** this is a frontend change (allowed, no backend rebuild). It is out of scope to *implement* here (analysis task) — this is the spec the implementer should follow.

---

## 6. Verification gates passed

- [x] Event taxonomy read from `sse_protocol.py` constants, not the brief.
- [x] Keepalive verified present in `chat_service.py` (corrects "missing" premise).
- [x] Nginx SSE config verified in live `nginx/default.conf`.
- [x] No-deploy: analysis only.

---

*Generated by roadmap deep-analysis worker. The prior `W2-chat-sse.md` predates the keepalive landing — treat §3 of this file as authoritative.*
