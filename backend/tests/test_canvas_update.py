"""Tests for _build_canvas_update — canvas_update SSE event builder.

Covers:
- Registry lookup (registered vs unregistered tools)
- JSON parsing (valid, invalid, malformed)
- Action filtering (only 'launch' triggers tile open)
- Error handling (tool errors, missing fields)
"""

from __future__ import annotations

import json

from app.services.chat_service import _CANVAS_UPDATE_TOOLS, _build_canvas_update


class TestCanvasUpdateRegistry:
    """Verify _CANVAS_UPDATE_TOOLS registry structure."""

    def test_registry_has_browser_sandbox(self):
        assert "browser_sandbox" in _CANVAS_UPDATE_TOOLS

    def test_registry_entry_has_required_keys(self):
        entry = _CANVAS_UPDATE_TOOLS["browser_sandbox"]
        assert "tileKind" in entry
        assert "titlePrefix" in entry

    def test_registry_tile_kind_matches_frontend(self):
        """tileKind must match TileKind type in frontend chat-types.ts."""
        entry = _CANVAS_UPDATE_TOOLS["browser_sandbox"]
        assert entry["tileKind"] == "browser-sandbox"


class TestBuildCanvasUpdate:
    """Test _build_canvas_update() core logic."""

    # ── Registry lookup ───────────────────────────────────────────────

    def test_returns_none_for_unregistered_tool(self):
        result = _build_canvas_update("unknown_tool", "{}")
        assert result is None

    def test_returns_none_for_sandboxd_preview(self):
        """sandboxd_preview is NOT in the canvas update registry."""
        result = _build_canvas_update(
            "sandboxd_preview",
            json.dumps({"sandbox_id": "sbx_123", "status": "running"}),
        )
        assert result is None

    def test_returns_none_for_web_search(self):
        result = _build_canvas_update("web_search_enhanced", "{}")
        assert result is None

    # ── JSON parsing ──────────────────────────────────────────────────

    def test_returns_none_for_invalid_json(self):
        result = _build_canvas_update("browser_sandbox", "not valid json{{{")
        assert result is None

    def test_returns_none_for_empty_string(self):
        result = _build_canvas_update("browser_sandbox", "")
        assert result is None

    def test_returns_none_for_none_input(self):
        result = _build_canvas_update("browser_sandbox", None)
        assert result is None

    def test_returns_none_for_non_dict_json(self):
        """JSON array or string is not a valid tool result."""
        result = _build_canvas_update("browser_sandbox", '["not", "a", "dict"]')
        assert result is None

    # ── Action filtering ──────────────────────────────────────────────

    def test_returns_none_for_non_launch_action(self):
        """Only 'launch' action should trigger a tile open."""
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps({"action": "navigate", "url": "https://example.com", "sandbox_id": "sbx_1"}),
        )
        assert result is None

    def test_returns_none_for_click_action(self):
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps({"action": "click", "selector": "button", "sandbox_id": "sbx_1"}),
        )
        assert result is None

    def test_returns_none_for_close_action(self):
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps({"action": "close", "sandbox_id": "sbx_1", "status": "closed"}),
        )
        assert result is None

    def test_returns_none_for_screenshot_action(self):
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps({"action": "screenshot", "sandbox_id": "sbx_1", "screenshot": "base64"}),
        )
        assert result is None

    # ── Error handling ────────────────────────────────────────────────

    def test_returns_none_when_result_has_error(self):
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps({"error": "container creation failed"}),
        )
        assert result is None

    def test_returns_none_when_result_has_error_key_with_launch(self):
        """Even if action is launch, an error should suppress the tile."""
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps({"action": "launch", "error": "timeout", "sandbox_id": "sbx_1"}),
        )
        assert result is None

    # ── Successful launch ─────────────────────────────────────────────

    def test_returns_canvas_update_for_launch(self):
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps(
                {
                    "sandbox_id": "sbx_abc123",
                    "status": "running",
                    "preview_url": "https://s-sbx_abc123-6080.preview.flowmanner.com",
                    "action": "launch",
                }
            ),
        )
        assert result is not None
        assert result["type"] == "canvas_update"
        assert result["data"]["action"] == "open_tile"
        assert result["data"]["tileKind"] == "browser-sandbox"

    def test_payload_contains_sandbox_id(self):
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps(
                {
                    "sandbox_id": "sbx_xyz",
                    "status": "running",
                    "preview_url": "https://example.com",
                    "action": "launch",
                }
            ),
        )
        assert result["data"]["payload"]["sandbox_id"] == "sbx_xyz"

    def test_payload_contains_preview_url(self):
        url = "https://s-sbx_xyz-6080.preview.flowmanner.com"
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps(
                {
                    "sandbox_id": "sbx_xyz",
                    "status": "running",
                    "preview_url": url,
                    "action": "launch",
                }
            ),
        )
        assert result["data"]["payload"]["preview_url"] == url

    def test_payload_contains_status(self):
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps(
                {
                    "sandbox_id": "sbx_1",
                    "status": "running",
                    "preview_url": "https://example.com",
                    "action": "launch",
                }
            ),
        )
        assert result["data"]["payload"]["status"] == "running"

    def test_title_includes_preview_url(self):
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps(
                {
                    "sandbox_id": "sbx_1",
                    "status": "running",
                    "preview_url": "https://example.com/page",
                    "action": "launch",
                }
            ),
        )
        assert "Browse" in result["data"]["title"]
        assert "https://example.com/page" in result["data"]["title"]

    def test_title_fallback_when_no_preview_url(self):
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps(
                {
                    "sandbox_id": "sbx_1",
                    "status": "running",
                    "preview_url": None,
                    "action": "launch",
                }
            ),
        )
        assert result["data"]["title"] == "Browse"

    def test_title_fallback_when_preview_url_empty(self):
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps(
                {
                    "sandbox_id": "sbx_1",
                    "status": "running",
                    "preview_url": "",
                    "action": "launch",
                }
            ),
        )
        assert result["data"]["title"] == "Browse"

    # ── Status defaults ───────────────────────────────────────────────

    def test_status_defaults_to_running_when_missing(self):
        result = _build_canvas_update(
            "browser_sandbox",
            json.dumps(
                {
                    "sandbox_id": "sbx_1",
                    "preview_url": "https://example.com",
                    "action": "launch",
                }
            ),
        )
        assert result["data"]["payload"]["status"] == "running"

    # ── Extensibility ─────────────────────────────────────────────────

    def test_registry_is_extensible(self):
        """Verify we can add new tool mappings without breaking existing ones."""
        original = _CANVAS_UPDATE_TOOLS.copy()
        try:
            _CANVAS_UPDATE_TOOLS["new_tool"] = {"tileKind": "new-tile", "titlePrefix": "New"}
            result = _build_canvas_update(
                "new_tool",
                json.dumps({"action": "launch", "sandbox_id": "sbx_new"}),
            )
            assert result is not None
            assert result["data"]["tileKind"] == "new-tile"
        finally:
            _CANVAS_UPDATE_TOOLS.clear()
            _CANVAS_UPDATE_TOOLS.update(original)
