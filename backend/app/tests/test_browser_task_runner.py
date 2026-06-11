"""Unit tests for app/services/browser_task_runner.py — BrowserTaskRunner."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


def _make_mock_import_browser():
    """Returns a tuple matching _import_browser_tools return value."""
    mock_registry = MagicMock()
    return (mock_registry,) + (MagicMock(),) * 5


# ── BROWSER_TASK_TYPES ────────────────────────────────────────────────────────


class TestBrowserTaskTypes:
    """BROWSER_TASK_TYPES: ensure all expected types are present."""

    def test_contains_all_expected_types(self):
        from app.services.browser_task_runner import BROWSER_TASK_TYPES

        assert "browser_navigate" in BROWSER_TASK_TYPES
        assert "browser_snapshot" in BROWSER_TASK_TYPES
        assert "browser_click" in BROWSER_TASK_TYPES
        assert "browser_type" in BROWSER_TASK_TYPES
        assert "browser_scroll" in BROWSER_TASK_TYPES
        assert "browser_screenshot" in BROWSER_TASK_TYPES
        assert "browser_close" in BROWSER_TASK_TYPES

    def test_length(self):
        from app.services.browser_task_runner import BROWSER_TASK_TYPES

        assert len(BROWSER_TASK_TYPES) == 7

    def test_all_are_strings(self):
        from app.services.browser_task_runner import BROWSER_TASK_TYPES

        for task_type in BROWSER_TASK_TYPES:
            assert isinstance(task_type, str)


# ── execute_browser_tool ──────────────────────────────────────────────────────


class TestExecuteBrowserTool:
    """BrowserTaskRunner.execute_browser_tool: browser tool dispatch.

    Patches _import_browser_tools rather than ToolRegistry directly because
    _import_browser_tools() does a fresh import, rebinding the local name.
    """

    def _patch_and_get_registry(self):
        """Patch _import_browser_tools and return (patcher, mock_registry)."""
        mock_registry = MagicMock()
        mock_tools = (mock_registry,) + (MagicMock(),) * 5
        patcher = patch(
            "app.services.browser_task_runner._import_browser_tools",
            return_value=mock_tools,
        )
        return patcher, mock_registry

    @pytest.mark.asyncio
    async def test_handles_unregistered_tool(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_unknown"

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = None
        with patcher:
            result = await runner.execute_browser_tool(mock_task, {})

        assert result["success"] is False
        assert "not registered" in result["error"]

    @pytest.mark.asyncio
    async def test_executes_navigate_successfully(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_navigate"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {"url": "https://example.com"}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            result = await runner.execute_browser_tool(mock_task, {"url": "https://example.com"})

        assert result["success"] is True
        assert result["output"] == {"url": "https://example.com"}
        mock_tool.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_passes_url(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_navigate"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            await runner.execute_browser_tool(mock_task, {"url": "https://test.page"})

        call_input = mock_tool.run.call_args[0][0]
        assert call_input["url"] == "https://test.page"

    @pytest.mark.asyncio
    async def test_executes_click(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_click"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            result = await runner.execute_browser_tool(mock_task, {"ref": "e15"})

        assert result["success"] is True
        call_input = mock_tool.run.call_args[0][0]
        assert call_input["ref"] == "e15"

    @pytest.mark.asyncio
    async def test_executes_type(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_type"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            result = await runner.execute_browser_tool(mock_task, {"ref": "e10", "text": "hello", "submit": True})

        assert result["success"] is True
        call_input = mock_tool.run.call_args[0][0]
        assert call_input["text"] == "hello"
        assert call_input["submit"] is True

    @pytest.mark.asyncio
    async def test_type_defaults_submit_to_false(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_type"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            await runner.execute_browser_tool(mock_task, {"ref": "e1", "text": "hi"})

        call_input = mock_tool.run.call_args[0][0]
        assert call_input["submit"] is False

    @pytest.mark.asyncio
    async def test_executes_scroll(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_scroll"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            result = await runner.execute_browser_tool(mock_task, {"x": 0, "y": 500})

        assert result["success"] is True
        call_input = mock_tool.run.call_args[0][0]
        assert call_input["y"] == 500

    @pytest.mark.asyncio
    async def test_scroll_defaults(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_scroll"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            await runner.execute_browser_tool(mock_task, {})

        call_input = mock_tool.run.call_args[0][0]
        assert call_input["x"] == 0
        assert call_input["y"] == 300

    @pytest.mark.asyncio
    async def test_passes_user_id_from_mission(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_navigate"

        mock_mission = MagicMock()
        mock_mission.user_id = 42

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            await runner.execute_browser_tool(mock_task, {"url": "http://x"}, mission=mock_mission)

        context = mock_tool.run.call_args[0][1]
        assert context["user_id"] == "42"

    @pytest.mark.asyncio
    async def test_uses_system_when_no_mission(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_navigate"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            await runner.execute_browser_tool(mock_task, {"url": "http://x"}, mission=None)

        context = mock_tool.run.call_args[0][1]
        assert context["user_id"] == "system"

    @pytest.mark.asyncio
    async def test_handles_tool_failure(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_navigate"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "failure"
        mock_result.error = "Page not found"
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            result = await runner.execute_browser_tool(mock_task, {"url": "http://x"})

        assert result["success"] is False
        assert result["error"] == "Page not found"

    @pytest.mark.asyncio
    async def test_reraises_retryable_error(self):
        from app.services.browser_task_runner import BrowserTaskRunner
        from app.services.mission_errors import RetryableMissionError

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_navigate"

        mock_tool = MagicMock()
        mock_tool.run = AsyncMock(side_effect=RetryableMissionError("overloaded"))

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher, pytest.raises(RetryableMissionError):
            await runner.execute_browser_tool(mock_task, {"url": "http://x"})

    @pytest.mark.asyncio
    async def test_catches_permanent_error(self):
        from app.services.browser_task_runner import BrowserTaskRunner
        from app.services.mission_errors import PermanentMissionError

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_navigate"

        mock_tool = MagicMock()
        mock_tool.run = AsyncMock(side_effect=PermanentMissionError("forbidden"))

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            result = await runner.execute_browser_tool(mock_task, {"url": "http://x"})

        assert result["success"] is False
        assert result.get("permanent") is True

    @pytest.mark.asyncio
    async def test_catches_general_exception(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_navigate"

        mock_tool = MagicMock()
        mock_tool.run = AsyncMock(side_effect=RuntimeError("browser crashed"))

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            result = await runner.execute_browser_tool(mock_task, {"url": "http://x"})

        assert result["success"] is False
        assert "browser crashed" in result["error"]

    @pytest.mark.asyncio
    async def test_executes_screenshot(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_screenshot"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {"screenshot": "base64..."}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            result = await runner.execute_browser_tool(mock_task, {})

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_executes_close(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_close"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            result = await runner.execute_browser_tool(mock_task, {})

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_executes_snapshot(self):
        from app.services.browser_task_runner import BrowserTaskRunner

        runner = BrowserTaskRunner()
        mock_task = MagicMock()
        mock_task.task_type = "browser_snapshot"

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {"dom": "<html>...</html>"}
        mock_tool.run = AsyncMock(return_value=mock_result)

        patcher, mock_registry = self._patch_and_get_registry()
        mock_registry.get.return_value = mock_tool
        with patcher:
            result = await runner.execute_browser_tool(mock_task, {})

        assert result["success"] is True
