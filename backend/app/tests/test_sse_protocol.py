"""Tests for app.services.sse_protocol — Phase 0.3 leaf extraction.

Verifies event-type constants are importable and the _build_canvas_update
pure helper behaves correctly.
"""

import json

from app.services.sse_protocol import (
    _CANVAS_UPDATE_TOOLS,
    SSE_EVENT_CANVAS_UPDATE,
    SSE_EVENT_COMPLETE,
    SSE_EVENT_ERROR,
    SSE_EVENT_MEMORY_CITATION,
    SSE_EVENT_MEMORY_RECALL_USED,
    SSE_EVENT_SAVE_FAILED,
    SSE_EVENT_STREAM_START,
    SSE_EVENT_TOKEN,
    SSE_EVENT_TOOL_CALL_RESULT,
    SSE_EVENT_TOOL_CALL_START,
    _build_canvas_update,
)


class TestEventConstants:
    def test_all_constants_are_strings(self):
        constants = [
            SSE_EVENT_TOKEN,
            SSE_EVENT_TOOL_CALL_START,
            SSE_EVENT_TOOL_CALL_RESULT,
            SSE_EVENT_CANVAS_UPDATE,
            SSE_EVENT_MEMORY_RECALL_USED,
            SSE_EVENT_MEMORY_CITATION,
            SSE_EVENT_COMPLETE,
            SSE_EVENT_ERROR,
            SSE_EVENT_SAVE_FAILED,
            SSE_EVENT_STREAM_START,
        ]
        for c in constants:
            assert isinstance(c, str), f"Constant {c!r} is not a string"

    def test_token_event(self):
        assert SSE_EVENT_TOKEN == "token"

    def test_complete_event(self):
        assert SSE_EVENT_COMPLETE == "complete"

    def test_error_event(self):
        assert SSE_EVENT_ERROR == "error"

    def test_save_failed_event(self):
        assert SSE_EVENT_SAVE_FAILED == "save_failed"

    def test_stream_start_event(self):
        assert SSE_EVENT_STREAM_START == "stream_start"


class TestBuildCanvasUpdate:
    def test_browser_sandbox_launch(self):
        result_json = json.dumps(
            {
                "action": "launch",
                "sandbox_id": "s123",
                "preview_url": "https://preview.example.com",
                "status": "running",
            }
        )
        result = _build_canvas_update("browser_sandbox", result_json)
        assert result is not None
        assert result["type"] == SSE_EVENT_CANVAS_UPDATE
        assert result["data"]["action"] == "open_tile"
        assert result["data"]["tileKind"] == "browser-sandbox"
        assert result["data"]["payload"]["sandbox_id"] == "s123"
        assert result["data"]["payload"]["preview_url"] == "https://preview.example.com"
        assert "preview.example.com" in result["data"]["title"]

    def test_unknown_tool_returns_none(self):
        result = _build_canvas_update("unknown_tool", json.dumps({"action": "launch"}))
        assert result is None

    def test_error_result_returns_none(self):
        result_json = json.dumps({"error": "something failed"})
        result = _build_canvas_update("browser_sandbox", result_json)
        assert result is None

    def test_non_launch_action_returns_none(self):
        result_json = json.dumps({"action": "stop", "sandbox_id": "s1"})
        result = _build_canvas_update("browser_sandbox", result_json)
        assert result is None

    def test_invalid_json_returns_none(self):
        result = _build_canvas_update("browser_sandbox", "not valid json")
        assert result is None

    def test_non_dict_result_returns_none(self):
        result = _build_canvas_update("browser_sandbox", json.dumps("just a string"))
        assert result is None

    def test_empty_string_returns_none(self):
        result = _build_canvas_update("browser_sandbox", "")
        assert result is None

    def test_canvas_update_tools_has_browser_sandbox(self):
        assert "browser_sandbox" in _CANVAS_UPDATE_TOOLS
        config = _CANVAS_UPDATE_TOOLS["browser_sandbox"]
        assert config["tileKind"] == "browser-sandbox"
        assert "titlePrefix" in config

    def test_title_without_preview_url(self):
        result_json = json.dumps(
            {
                "action": "launch",
                "sandbox_id": "s456",
                "preview_url": "",
                "status": "running",
            }
        )
        result = _build_canvas_update("browser_sandbox", result_json)
        assert result is not None
        assert result["data"]["title"] == "Browse"
