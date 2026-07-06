from __future__ import annotations

"""SSE protocol constants and pure formatting helpers.

Phase 0.3 of the Chat Wiring Sprint (Round 2).  The SSE emission itself
is inline in the ``stream_message_to_llm`` generator (trunk code, Phase 4
to refactor).  This leaf module extracts:

  - Event-type string constants (shared by generator + frontend)
  - ``_CANVAS_UPDATE_TOOLS`` mapping (tool_name → tile config)
  - ``_build_canvas_update`` pure helper (dict → canvas_update event)

Tasks 1.2a (keepalive) and 1.2b (Redis event buffer) will import the
constants from here instead of using bare string literals.
"""

import json

# ── SSE event type constants ──────────────────────────────────────────
# Canonical names emitted by ``stream_message_to_llm`` and expected by
# the frontend's ``useStreaming`` hook.  Defining them as constants so
# the generator and the new keepalive/reconnect code share one source.
SSE_EVENT_TOKEN = "token"
SSE_EVENT_TOOL_CALL_START = "tool_call_start"
SSE_EVENT_TOOL_CALL_RESULT = "tool_call_result"
SSE_EVENT_CANVAS_UPDATE = "canvas_update"
SSE_EVENT_MEMORY_RECALL_USED = "memory_recall_used"
SSE_EVENT_MEMORY_CITATION = "memory_citation"
SSE_EVENT_COMPLETE = "complete"
SSE_EVENT_ERROR = "error"
SSE_EVENT_SAVE_FAILED = "save_failed"
SSE_EVENT_STREAM_START = "stream_start"


# ── Canvas update event builder ───────────────────────────────────────
# Maps tool_name → tile config for tools that should auto-open canvas tiles.
# Extensible: add new tool→tile mappings here as the platform grows.
_CANVAS_UPDATE_TOOLS: dict[str, dict[str, str]] = {
    "browser_sandbox": {"tileKind": "browser-sandbox", "titlePrefix": "Browse"},
}


def _build_canvas_update(tool_name: str, tool_result_json: str) -> dict | None:
    """Build a canvas_update SSE event if the tool result warrants opening a tile.

    Returns None for tools that don't trigger tile opens, or when the tool
    result indicates an error. Returns a canvas_update event dict otherwise.

    Extensible: add entries to ``_CANVAS_UPDATE_TOOLS`` for new tile types.
    """
    config = _CANVAS_UPDATE_TOOLS.get(tool_name)
    if config is None:
        return None

    try:
        result = json.loads(tool_result_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(result, dict):
        return None
    if result.get("error"):
        return None

    # Extract tile-relevant fields from the tool result
    action = result.get("action", "")
    if action != "launch":
        return None

    sandbox_id = result.get("sandbox_id", "")
    preview_url = result.get("preview_url", "")
    title = f"{config['titlePrefix']}: {preview_url}" if preview_url else config["titlePrefix"]

    return {
        "type": SSE_EVENT_CANVAS_UPDATE,
        "data": {
            "action": "open_tile",
            "tileKind": config["tileKind"],
            "title": title,
            "payload": {
                "sandbox_id": sandbox_id,
                "preview_url": preview_url,
                "status": result.get("status", "running"),
            },
        },
    }
