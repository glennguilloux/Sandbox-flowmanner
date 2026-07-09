"""Tests for browser_sandbox tool."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.base import ToolResult
from app.tools.browser_sandbox import BrowserSandboxInput, BrowserSandboxTool


class TestBrowserSandboxInput:
    def test_valid_launch_input(self):
        inp = BrowserSandboxInput(action="launch")
        assert inp.action == "launch"
        assert inp.sandbox_id is None
        assert inp.url is None

    def test_valid_navigate_input(self):
        inp = BrowserSandboxInput(action="navigate", sandbox_id="sbx_123", url="https://example.com")
        assert inp.action == "navigate"
        assert inp.sandbox_id == "sbx_123"
        assert inp.url == "https://example.com"

    def test_valid_click_input(self):
        inp = BrowserSandboxInput(action="click", sandbox_id="sbx_123", selector="button#submit")
        assert inp.action == "click"
        assert inp.selector == "button#submit"

    def test_valid_type_input(self):
        inp = BrowserSandboxInput(
            action="type", sandbox_id="sbx_123", selector="input[name=q]", text="hello", submit=True
        )
        assert inp.text == "hello"
        assert inp.submit is True

    def test_valid_screenshot_input(self):
        inp = BrowserSandboxInput(action="screenshot", sandbox_id="sbx_123")
        assert inp.action == "screenshot"

    def test_valid_close_input(self):
        inp = BrowserSandboxInput(action="close", sandbox_id="sbx_123")
        assert inp.action == "close"


class TestBrowserSandboxToolMetadata:
    def test_tool_id(self):
        tool = BrowserSandboxTool()
        assert tool.tool_id == "browser_sandbox"

    def test_required_scopes(self):
        tool = BrowserSandboxTool()
        assert tool.metadata.required_scopes == ["tool:browser-sandbox"]

    def test_category(self):
        tool = BrowserSandboxTool()
        assert tool.metadata.category == "browser"

    def test_requires_sandbox(self):
        tool = BrowserSandboxTool()
        assert tool.metadata.requires_sandbox is True

    def test_tags(self):
        tool = BrowserSandboxTool()
        assert "browser" in tool.metadata.tags
        assert "sandbox" in tool.metadata.tags
        assert "novnc" in tool.metadata.tags

    def test_openai_schema_has_action_param(self):
        tool = BrowserSandboxTool()
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "browser_sandbox"
        props = schema["function"]["parameters"]["properties"]
        assert "action" in props
        assert "sandbox_id" in props
        assert "url" in props
        assert "selector" in props


class TestBrowserSandboxToolExecution:
    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self):
        tool = BrowserSandboxTool()
        result = await tool.execute({"action": "invalid_action"})
        assert result.success is False
        assert "Unknown action" in result.error

    @pytest.mark.asyncio
    async def test_navigate_requires_sandbox_id(self):
        tool = BrowserSandboxTool()
        with patch("app.tools._sandbox_context.get_current_sandbox_id", return_value=None):
            result = await tool.execute({"action": "navigate", "url": "https://example.com"})
        assert result.success is False
        assert "sandbox_id" in result.error

    @pytest.mark.asyncio
    async def test_navigate_requires_url(self):
        tool = BrowserSandboxTool()
        result = await tool.execute({"action": "navigate", "sandbox_id": "sbx_123"})
        assert result.success is False
        assert "url" in result.error

    @pytest.mark.asyncio
    async def test_click_requires_selector(self):
        tool = BrowserSandboxTool()
        result = await tool.execute({"action": "click", "sandbox_id": "sbx_123"})
        assert result.success is False
        assert "selector" in result.error

    @pytest.mark.asyncio
    async def test_type_requires_selector(self):
        tool = BrowserSandboxTool()
        result = await tool.execute({"action": "type", "sandbox_id": "sbx_123", "text": "hello"})
        assert result.success is False
        assert "selector" in result.error

    @pytest.mark.asyncio
    async def test_type_requires_text(self):
        tool = BrowserSandboxTool()
        result = await tool.execute({"action": "type", "sandbox_id": "sbx_123", "selector": "input"})
        assert result.success is False
        assert "text" in result.error

    @pytest.mark.asyncio
    async def test_invalid_input_returns_error(self):
        tool = BrowserSandboxTool()
        result = await tool.execute({})
        assert result.success is False
        assert "Invalid input" in result.error

    @pytest.mark.asyncio
    async def test_launch_success(self):
        tool = BrowserSandboxTool()

        mock_client = AsyncMock()
        mock_client.create.return_value = {"id": "sbx_browser_abc", "status": "creating"}
        mock_client.get.return_value = {"status": "running"}
        mock_client.get_internal.return_value = {"live_state": {"State": {"Status": "running"}}}
        mock_client.exec_command.return_value = {"exit_code": 0, "stdout": "{}", "stderr": ""}

        with (
            patch("app.integrations.sandboxd_client.get_sandboxd_client", return_value=mock_client),
            patch("app.services.sandbox_service.get_sandboxd_client", return_value=mock_client),
            patch("app.config.settings") as mock_settings,
        ):
            mock_settings.SANDBOXD_PREVIEW_DOMAIN = "preview.flowmanner.com"
            result = await tool.execute({"action": "launch"})

        assert result.success is True
        assert result.result["sandbox_id"] == "sbx_browser_abc"
        assert result.result["action"] == "launch"
        assert "preview.flowmanner.com" in result.result["preview_url"]

    @pytest.mark.asyncio
    async def test_navigate_success(self):
        tool = BrowserSandboxTool()

        mock_client = AsyncMock()
        mock_client.exec_command.return_value = {
            "exit_code": 0,
            "stdout": json.dumps({"success": True, "url": "https://example.com", "title": "Example", "status": 200}),
            "stderr": "",
        }

        with patch("app.integrations.sandboxd_client.get_sandboxd_client", return_value=mock_client):
            result = await tool.execute({"action": "navigate", "sandbox_id": "sbx_123", "url": "https://example.com"})

        assert result.success is True
        assert result.result["url"] == "https://example.com"
        assert result.result["action"] == "navigate"

    @pytest.mark.asyncio
    async def test_close_success(self):
        tool = BrowserSandboxTool()

        mock_service = MagicMock()
        mock_service.close_browser_sandbox = AsyncMock()

        with patch("app.services.sandbox_service.SandboxService", return_value=mock_service):
            result = await tool.execute({"action": "close", "sandbox_id": "sbx_123"})

        assert result.success is True
        assert result.result["action"] == "close"
        assert result.result["status"] == "closed"
        mock_service.close_browser_sandbox.assert_called_once_with("sbx_123")

    @pytest.mark.asyncio
    async def test_exec_playwright_handles_nonzero_exit(self):
        tool = BrowserSandboxTool()

        mock_client = AsyncMock()
        mock_client.exec_command.return_value = {
            "exit_code": 1,
            "stdout": "",
            "stderr": "Connection refused",
        }

        with patch("app.integrations.sandboxd_client.get_sandboxd_client", return_value=mock_client):
            result = await tool.execute({"action": "navigate", "sandbox_id": "sbx_123", "url": "https://example.com"})

        assert result.success is False
        assert "Connection refused" in result.error

    @pytest.mark.asyncio
    async def test_screenshot_success(self):
        tool = BrowserSandboxTool()

        mock_client = AsyncMock()
        mock_client.exec_command.return_value = {
            "exit_code": 0,
            "stdout": json.dumps(
                {"success": True, "screenshot": "base64data", "url": "https://example.com", "title": "Example"}
            ),
            "stderr": "",
        }

        with patch("app.integrations.sandboxd_client.get_sandboxd_client", return_value=mock_client):
            result = await tool.execute({"action": "screenshot", "sandbox_id": "sbx_123"})

        assert result.success is True
        assert result.result["screenshot"] == "base64data"
        assert result.result["action"] == "screenshot"

    @pytest.mark.asyncio
    async def test_snapshot_success(self):
        tool = BrowserSandboxTool()

        mock_client = AsyncMock()
        mock_client.exec_command.return_value = {
            "exit_code": 0,
            "stdout": json.dumps(
                {"success": True, "snapshot": {"role": "WebArea"}, "url": "https://example.com", "title": "Example"}
            ),
            "stderr": "",
        }

        with patch("app.integrations.sandboxd_client.get_sandboxd_client", return_value=mock_client):
            result = await tool.execute({"action": "snapshot", "sandbox_id": "sbx_123"})

        assert result.success is True
        assert result.result["snapshot"]["role"] == "WebArea"
        assert result.result["action"] == "snapshot"
