"""browser_sandbox — isolated browser environment with live noVNC preview.

Launches a sandboxd browser container with Chromium + Xvfb + x11vnc + websockify
(noVNC). The agent can navigate, click, type, and take screenshots inside the
container. The user sees the live browser via a noVNC iframe in a canvas tile.

VNC chain (correct — not the draft's broken CDP proxy):
  Chromium → Xvfb → x11vnc (:5900) → websockify (:6080) → noVNC client
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# Track the active browser sandbox per chat session.
# Only ONE browser sandbox may exist at a time — creating a new one
# automatically closes the previous one. This prevents Docker containers
# from piling up across LLM turns (each "launch" call from a new turn
# would otherwise create a fresh container, leaking the old one).
_active_browser_sandbox_id: str | None = None

# ── Playwright scripts executed inside the container via sandboxd exec ──

_NAVIGATE_SCRIPT = """\
import asyncio, json, sys
from playwright.async_api import async_playwright

async def main():
    url = sys.argv[1]
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        title = await page.title()
        current_url = page.url
        print(json.dumps({
            "success": True,
            "url": current_url,
            "title": title,
            "status": resp.status if resp else None,
        }))

asyncio.run(main())
"""

_CLICK_SCRIPT = """\
import asyncio, json, sys
from playwright.async_api import async_playwright

async def main():
    selector = sys.argv[1]
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        await page.click(selector, timeout=10000)
        title = await page.title()
        print(json.dumps({"success": True, "title": title, "url": page.url}))

asyncio.run(main())
"""

_TYPE_SCRIPT = """\
import asyncio, json, sys
from playwright.async_api import async_playwright

async def main():
    selector = sys.argv[1]
    text = sys.argv[2]
    submit = sys.argv[3] == "true" if len(sys.argv) > 3 else False
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        await page.fill(selector, text, timeout=10000)
        if submit:
            await page.press(selector, "Enter")
        print(json.dumps({"success": True, "url": page.url}))

asyncio.run(main())
"""

_SCREENSHOT_SCRIPT = """\
import asyncio, base64, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        screenshot = await page.screenshot(type="png")
        b64 = base64.b64encode(screenshot).decode("utf-8")
        print(json.dumps({
            "success": True,
            "screenshot": b64,
            "url": page.url,
            "title": await page.title(),
        }))

asyncio.run(main())
"""

_SNAPSHOT_SCRIPT = """\
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        # Get accessibility snapshot
        snapshot = await page.accessibility.snapshot()
        print(json.dumps({
            "success": True,
            "snapshot": snapshot,
            "url": page.url,
            "title": await page.title(),
        }))

asyncio.run(main())
"""


# ── Input ─────────────────────────────────────────────────────────────


class BrowserSandboxInput(ToolInput):
    action: str = Field(
        ...,
        description=(
            "Action: 'launch' (create browser container), "
            "'navigate' (go to URL), 'click' (click element by CSS selector), "
            "'type' (fill input by CSS selector), 'screenshot' (take PNG screenshot), "
            "'snapshot' (get accessibility tree), 'close' (destroy container)"
        ),
    )
    sandbox_id: str | None = Field(
        default=None,
        description="Browser sandbox ID (required for all actions except 'launch')",
    )
    url: str | None = Field(
        default=None,
        description="URL to navigate to (for 'navigate' action)",
    )
    selector: str | None = Field(
        default=None,
        description="CSS selector (for 'click' and 'type' actions)",
    )
    text: str | None = Field(
        default=None,
        description="Text to type (for 'type' action)",
    )
    submit: bool = Field(
        default=False,
        description="Press Enter after typing (for 'type' action)",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class BrowserSandboxTool(BaseTool):
    """Isolated browser environment with live noVNC preview."""

    def __init__(self) -> None:
        metadata = ToolMetadata(
            visibility="default_on",
            tool_id="browser_sandbox",
            name="Browser Sandbox",
            description=(
                "Launch an isolated browser with a live visual preview (noVNC). "
                "Navigate, click, type, and take screenshots. The user can watch "
                "the browser in real time via the canvas tile. "
                "Actions: launch, navigate, click, type, screenshot, snapshot, close."
            ),
            category="browser",
            input_schema=BrowserSandboxInput.schema_extra(),
            tags=["browser", "sandbox", "playwright", "novnc"],
            required_scopes=["tool:browser-sandbox"],
            requires_sandbox=True,
            rate_limit_key=None,
            timeout_seconds=120,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        try:
            validated = BrowserSandboxInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        action = validated.action.lower()

        try:
            if action == "launch":
                return await self._launch(validated)
            elif action == "navigate":
                return await self._navigate(validated)
            elif action == "click":
                return await self._click(validated)
            elif action == "type":
                return await self._type_text(validated)
            elif action == "screenshot":
                return await self._screenshot(validated)
            elif action == "snapshot":
                return await self._snapshot(validated)
            elif action == "close":
                return await self._close(validated)
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Unknown action: '{action}'. Use launch, navigate, click, type, screenshot, snapshot, or close.",
                )
        except Exception as e:
            logger.exception("browser_sandbox.%s failed", action)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── Actions ───────────────────────────────────────────────────────

    async def _launch(self, validated: BrowserSandboxInput) -> ToolResult:
        """Create a browser sandbox container."""
        from app.integrations.sandboxd_client import get_sandboxd_client
        from app.services.sandbox_service import SandboxService

        global _active_browser_sandbox_id

        service = SandboxService()
        user_id = "chat-browser"

        # ── Close any previous active browser sandbox ─────────────────
        # Every "launch" call (across LLM turns) would otherwise create a
        # fresh container, leaking the old one.  Closing the previous
        # sandbox ensures at most one browser container exists at a time.
        if _active_browser_sandbox_id:
            previous_id = _active_browser_sandbox_id
            _active_browser_sandbox_id = None  # clear before close (avoid re-entry)
            try:
                await service.close_browser_sandbox(previous_id)
                logger.info(
                    "Closed previous browser sandbox %s before creating new one",
                    previous_id,
                )
            except Exception as close_err:
                logger.warning(
                    "Failed to close previous browser sandbox %s (continuing): %s",
                    previous_id,
                    close_err,
                )

        # Create sandbox via SandboxService (reuses sandboxd client + preview URL logic)
        try:
            result = await service.create_browser_sandbox(user_id=user_id)
        except Exception as e:
            logger.error("Failed to create browser sandbox: %s", e)
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Failed to create browser container: {e}. Ensure sandboxd-browser image is built.",
            )

        sandbox_id = result.get("sandbox_id")
        if not sandbox_id:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="sandboxd returned empty sandbox ID",
            )

        # Track as the active sandbox
        _active_browser_sandbox_id = sandbox_id

        preview_url = result.get("preview_url")
        client = get_sandboxd_client()

        # Wait for the container to be ready
        import asyncio

        for _attempt in range(60):  # 60 × 500ms = 30s max
            await asyncio.sleep(0.5)
            try:
                info = await client.get(sandbox_id)
                status = info.get("status", "")
                if status in ("running", "ready"):
                    break
                # Also check live state
                internal = await client.get_internal(sandbox_id)
                live_state = internal.get("live_state", {})
                container_status = live_state.get("State", {}).get("Status", "")
                if container_status == "running":
                    break
            except Exception:
                logger.debug("browser_sandbox launch: poll attempt %d failed", _attempt, exc_info=True)

        # Verify CDP is reachable inside the container
        try:
            exec_result = await client.exec_command(
                sandbox_id,
                ["curl", "-sf", "http://localhost:9222/json/version"],
                timeout=10.0,
            )
            if exec_result.get("exit_code", -1) != 0:
                logger.warning(
                    "browser_sandbox: CDP not ready after container start (exit_code=%s)",
                    exec_result.get("exit_code"),
                )
        except Exception:
            logger.debug("browser_sandbox: CDP check failed (non-fatal)", exc_info=True)

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "sandbox_id": sandbox_id,
                "status": "running",
                "preview_url": preview_url,
                "action": "launch",
            },
        )

    async def _navigate(self, validated: BrowserSandboxInput) -> ToolResult:
        """Navigate to a URL."""
        sandbox_id = self._require_sandbox_id(validated)
        if isinstance(sandbox_id, ToolResult):
            return sandbox_id  # error result

        if not validated.url:
            return ToolResult.error_result(tool_id=self.tool_id, error="'url' is required for navigate action")

        result = await self._exec_playwright(
            sandbox_id,
            ["python3", "-c", _NAVIGATE_SCRIPT, validated.url],
        )
        if "error" in result:
            return ToolResult.error_result(tool_id=self.tool_id, error=result["error"])

        result["action"] = "navigate"
        return ToolResult.success_result(tool_id=self.tool_id, result=result)

    async def _click(self, validated: BrowserSandboxInput) -> ToolResult:
        """Click an element by CSS selector."""
        sandbox_id = self._require_sandbox_id(validated)
        if isinstance(sandbox_id, ToolResult):
            return sandbox_id

        if not validated.selector:
            return ToolResult.error_result(tool_id=self.tool_id, error="'selector' is required for click action")

        result = await self._exec_playwright(
            sandbox_id,
            ["python3", "-c", _CLICK_SCRIPT, validated.selector],
        )
        if "error" in result:
            return ToolResult.error_result(tool_id=self.tool_id, error=result["error"])

        result["action"] = "click"
        return ToolResult.success_result(tool_id=self.tool_id, result=result)

    async def _type_text(self, validated: BrowserSandboxInput) -> ToolResult:
        """Type text into an input field."""
        sandbox_id = self._require_sandbox_id(validated)
        if isinstance(sandbox_id, ToolResult):
            return sandbox_id

        if not validated.selector:
            return ToolResult.error_result(tool_id=self.tool_id, error="'selector' is required for type action")
        if not validated.text:
            return ToolResult.error_result(tool_id=self.tool_id, error="'text' is required for type action")

        result = await self._exec_playwright(
            sandbox_id,
            ["python3", "-c", _TYPE_SCRIPT, validated.selector, validated.text, str(validated.submit).lower()],
        )
        if "error" in result:
            return ToolResult.error_result(tool_id=self.tool_id, error=result["error"])

        result["action"] = "type"
        return ToolResult.success_result(tool_id=self.tool_id, result=result)

    async def _screenshot(self, validated: BrowserSandboxInput) -> ToolResult:
        """Take a screenshot of the current page."""
        sandbox_id = self._require_sandbox_id(validated)
        if isinstance(sandbox_id, ToolResult):
            return sandbox_id

        result = await self._exec_playwright(
            sandbox_id,
            ["python3", "-c", _SCREENSHOT_SCRIPT],
        )
        if "error" in result:
            return ToolResult.error_result(tool_id=self.tool_id, error=result["error"])

        result["action"] = "screenshot"
        return ToolResult.success_result(tool_id=self.tool_id, result=result)

    async def _snapshot(self, validated: BrowserSandboxInput) -> ToolResult:
        """Get accessibility tree snapshot."""
        sandbox_id = self._require_sandbox_id(validated)
        if isinstance(sandbox_id, ToolResult):
            return sandbox_id

        result = await self._exec_playwright(
            sandbox_id,
            ["python3", "-c", _SNAPSHOT_SCRIPT],
        )
        if "error" in result:
            return ToolResult.error_result(tool_id=self.tool_id, error=result["error"])

        result["action"] = "snapshot"
        return ToolResult.success_result(tool_id=self.tool_id, result=result)

    async def _close(self, validated: BrowserSandboxInput) -> ToolResult:
        """Destroy the browser sandbox container."""
        sandbox_id = self._require_sandbox_id(validated)
        if isinstance(sandbox_id, ToolResult):
            return sandbox_id

        from app.services.sandbox_service import SandboxService

        global _active_browser_sandbox_id
        if _active_browser_sandbox_id == sandbox_id:
            _active_browser_sandbox_id = None

        service = SandboxService()
        await service.close_browser_sandbox(sandbox_id)

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={"sandbox_id": sandbox_id, "action": "close", "status": "closed"},
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _require_sandbox_id(self, validated: BrowserSandboxInput) -> str | ToolResult:
        """Return sandbox_id or an error ToolResult if missing."""
        if validated.sandbox_id:
            return validated.sandbox_id

        # Try context
        try:
            from app.tools._sandbox_context import get_current_sandbox_id

            ctx_id = get_current_sandbox_id()
            if ctx_id:
                return ctx_id
        except ImportError:
            pass

        return ToolResult.error_result(
            tool_id=self.tool_id,
            error="'sandbox_id' is required. Call browser_sandbox(action='launch') first.",
        )

    async def _exec_playwright(self, sandbox_id: str, cmd: list[str]) -> dict[str, Any]:
        """Execute a Playwright script inside the sandbox container.

        Uses sandboxd exec_command (same pattern as sandboxd_exec.py).
        Returns parsed JSON output or error dict.
        """
        from app.integrations.sandboxd_client import get_sandboxd_client

        client = get_sandboxd_client()
        result = await client.exec_command(sandbox_id, cmd, timeout=60.0)

        exit_code = result.get("exit_code", -1)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")

        if exit_code != 0:
            return {"error": f"Playwright script failed (exit_code={exit_code}): {stderr or stdout}"}

        # Parse JSON from stdout (script prints a single JSON object)
        try:
            # Find the JSON object in stdout (may have log lines before it)
            lines = stdout.strip().split("\n")
            for line in reversed(lines):
                line = line.strip()
                if line.startswith("{"):
                    return json.loads(line)
            return {"error": f"No JSON output from Playwright script: {stdout[:500]}"}
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse Playwright output: {e} — raw: {stdout[:500]}"}


# ── Register ──────────────────────────────────────────────────────────

register_tool(BrowserSandboxTool())
