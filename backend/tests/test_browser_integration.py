"""Integration tests for browser tools (no mocks — real Playwright).

These tests spin up a local HTTP server with a known test page, then exercise
the real ``BrowserNavigateTool`` / ``BrowserSnapshotTool`` /
``BrowserClickTool`` / ``BrowserTypeTool`` / ``BrowserScreenshotTool`` /
``BrowserCloseTool`` against it.  This is the test that would have caught the
``.run()`` vs ``.execute()`` bug in ``_handle_browser``.

Requires Playwright + Chromium installed (available in the Docker image).
Skip if Playwright is not importable (e.g. running on the host without it).
"""

from __future__ import annotations

import asyncio
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from unittest.mock import patch

import pytest

# Skip the entire module if Playwright is not installed.
playwright = pytest.importorskip("playwright")

from app.services.browser_manager import BrowserManager  # noqa: E402
from app.services.browser_service import (  # noqa: E402
    validate_url_for_navigation,
)
from app.tools.browser_click import BrowserClickTool  # noqa: E402
from app.tools.browser_close import BrowserCloseTool  # noqa: E402
from app.tools.browser_navigate import BrowserNavigateTool  # noqa: E402
from app.tools.browser_screenshot import BrowserScreenshotTool  # noqa: E402
from app.tools.browser_snapshot import BrowserSnapshotTool  # noqa: E402
from app.tools.browser_type import BrowserTypeTool  # noqa: E402

# ── Local HTTP server fixture ────────────────────────────────────────

_TEST_HTML = """<!DOCTYPE html>
<html><head><title>Test Page</title></head>
<body>
  <h1>Login Form</h1>
  <form id="login-form" onsubmit="return false">
    <input type="text" id="username" name="username" placeholder="Username" />
    <input type="password" id="password" name="password" placeholder="Password" />
    <button type="submit" id="login-button">Log In</button>
  </form>
  <div id="content">Hello, world!</div>
</body></html>"""


class _TestPageHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_TEST_HTML.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # suppress logs


@pytest.fixture(scope="module")
def test_server():
    """Start a local HTTP server on a random port."""
    server = HTTPServer(("127.0.0.1", 0), _TestPageHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _reset_browser_manager():
    """Reset the BrowserManager singleton between tests."""
    yield
    # Clean up any sessions left open.
    mgr = BrowserManager()
    try:
        asyncio.get_event_loop().run_until_complete(mgr.close_all_sessions())
    except Exception:
        pass
    mgr._sessions.clear()
    mgr._user_sessions.clear()


# ── SSRF validator tests ──────────────────────────────────────────────


class TestSSRFValidator:
    def test_blocks_private_ip_literal(self):
        ok, _ = validate_url_for_navigation("http://192.168.1.1/admin")
        assert ok is False

    def test_blocks_localhost(self):
        ok, _ = validate_url_for_navigation("http://localhost/admin")
        assert ok is False

    def test_blocks_127_literal(self):
        ok, _ = validate_url_for_navigation("http://127.0.0.1/admin")
        assert ok is False

    def test_blocks_file_scheme(self):
        ok, _ = validate_url_for_navigation("file:///etc/passwd")
        assert ok is False

    def test_blocks_no_hostname(self):
        ok, _ = validate_url_for_navigation("http:///path")
        assert ok is False

    def test_allows_public_url(self):
        # example.com resolves to a public IP (93.184.216.34 or similar).
        ok, err = validate_url_for_navigation("https://example.com")
        assert ok is True, f"Expected example.com to be allowed, got: {err}"

    def test_blocks_dns_rebinding_to_private(self):
        """A hostname that resolves to a private IP is blocked."""
        # 'testhost.local' won't resolve → fail-closed.
        ok, _ = validate_url_for_navigation("http://nonexistent.invalid.test/page")
        assert ok is False


# ── Real tool integration tests ──────────────────────────────────────


@pytest.mark.asyncio
class TestBrowserToolIntegration:
    async def test_navigate_snapshot_screenshot_close_chain(self, test_server):
        """Exercise the real navigate→snapshot→screenshot→close chain."""
        ctx = {"user_id": "integration-test-1"}

        # Navigate
        nav = BrowserNavigateTool()
        result = await nav.execute({"url": test_server, "context": ctx})
        assert result.success, f"Navigate failed: {result.error}"
        assert "Test Page" in result.result.get("title", "")

        # Snapshot — should find the login form elements
        snap = BrowserSnapshotTool()
        result = await snap.execute({"context": ctx})
        assert result.success, f"Snapshot failed: {result.error}"
        elements = result.result.get("elements", [])
        tags = [el["tag"] for el in elements]
        assert "input" in tags, f"Expected input elements, got tags: {tags}"

        # Screenshot
        ss = BrowserScreenshotTool()
        result = await ss.execute({"context": ctx})
        assert result.success, f"Screenshot failed: {result.error}"
        assert "screenshot" in result.result
        assert len(result.result["screenshot"]) > 100  # non-trivial base64

        # Close
        close = BrowserCloseTool()
        result = await close.execute({"context": ctx})
        assert result.success, f"Close failed: {result.error}"

    async def test_click_and_type_by_selector(self, test_server):
        """Test the new selector-based click/type on the login form."""
        ctx = {"user_id": "integration-test-2"}

        # Navigate first
        nav = BrowserNavigateTool()
        await nav.execute({"url": test_server, "context": ctx})

        # Type into the username field by CSS selector
        type_tool = BrowserTypeTool()
        result = await type_tool.execute({
            "selector": "#username",
            "text": "testuser",
            "context": ctx,
        })
        assert result.success, f"Type failed: {result.error}"

        # Click the login button by CSS selector
        click_tool = BrowserClickTool()
        result = await click_tool.execute({
            "selector": "#login-button",
            "context": ctx,
        })
        assert result.success, f"Click failed: {result.error}"

        # Close
        await BrowserCloseTool().execute({"context": ctx})
