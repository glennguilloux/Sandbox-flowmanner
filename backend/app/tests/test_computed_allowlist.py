"""Tests for computed allowlist — Task 3.2.

Verifies the _get_chat_openai_tools function uses visibility × workspace
× scope gates instead of hardcoded sets.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_registry():
    """Create a mock tool registry with tools at various visibility levels."""
    from app.tools.base import BaseTool, ToolMetadata, ToolRegistry

    registry = ToolRegistry()

    # default_on tool
    t1 = MagicMock(spec=BaseTool)
    t1.tool_id = "web_search_enhanced"
    t1.metadata = ToolMetadata(tool_id="web_search_enhanced", name="web_search", description="search")
    t1.to_openai_schema.return_value = {"type": "function", "function": {"name": "web_search_enhanced"}}

    # opt_in tool (Phase 3)
    t2 = MagicMock(spec=BaseTool)
    t2.tool_id = "dall_e_image_gen"
    t2.metadata = ToolMetadata(tool_id="dall_e_image_gen", name="dall_e", description="image gen")
    t2.to_openai_schema.return_value = {"type": "function", "function": {"name": "dall_e_image_gen"}}

    # hidden tool (write op)
    t3 = MagicMock(spec=BaseTool)
    t3.tool_id = "slack_post_message"
    t3.metadata = ToolMetadata(tool_id="slack_post_message", name="slack_post", description="post")
    t3.to_openai_schema.return_value = {"type": "function", "function": {"name": "slack_post_message"}}

    # sandboxd tool
    t4 = MagicMock(spec=BaseTool)
    t4.tool_id = "sandboxd_preview"
    t4.metadata = ToolMetadata(tool_id="sandboxd_preview", name="sandboxd", description="sandbox")
    t4.to_openai_schema.return_value = {"type": "function", "function": {"name": "sandboxd_preview"}}

    # Unlisted tool (not in _TOOL_VISIBILITY map)
    t5 = MagicMock(spec=BaseTool)
    t5.tool_id = "some_random_tool"
    t5.metadata = ToolMetadata(tool_id="some_random_tool", name="random", description="random")
    t5.to_openai_schema.return_value = {"type": "function", "function": {"name": "some_random_tool"}}

    registry.register(t1)
    registry.register(t2)
    registry.register(t3)
    registry.register(t4)
    registry.register(t5)

    return registry


class TestComputedAllowlist:
    @pytest.mark.asyncio
    async def test_default_on_tools_exposed(self, mock_registry):
        """default_on tools are exposed in the tool list."""
        from app.services.chat_service import _get_chat_openai_tools

        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.SANDBOXD_ENABLED = True
            with patch("app.tools.base._tool_registry", mock_registry):
                tools = await _get_chat_openai_tools()

        assert tools is not None
        tool_names = {t["function"]["name"] for t in tools}
        assert "web_search_enhanced" in tool_names

    @pytest.mark.asyncio
    async def test_opt_in_tools_exposed(self, mock_registry):
        """opt_in tools are exposed (visible to LLM)."""
        from app.services.chat_service import _get_chat_openai_tools

        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.SANDBOXD_ENABLED = True
            with patch("app.tools.base._tool_registry", mock_registry):
                tools = await _get_chat_openai_tools()

        assert tools is not None
        tool_names = {t["function"]["name"] for t in tools}
        assert "dall_e_image_gen" in tool_names

    @pytest.mark.asyncio
    async def test_hidden_tools_not_exposed(self, mock_registry):
        """Hidden tools (write ops) are NOT exposed."""
        from app.services.chat_service import _get_chat_openai_tools

        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.SANDBOXD_ENABLED = True
            with patch("app.tools.base._tool_registry", mock_registry):
                tools = await _get_chat_openai_tools()

        assert tools is not None
        tool_names = {t["function"]["name"] for t in tools}
        assert "slack_post_message" not in tool_names

    @pytest.mark.asyncio
    async def test_unlisted_tools_not_exposed(self, mock_registry):
        """Tools not in _TOOL_VISIBILITY map default to hidden."""
        from app.services.chat_service import _get_chat_openai_tools

        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.SANDBOXD_ENABLED = True
            with patch("app.tools.base._tool_registry", mock_registry):
                tools = await _get_chat_openai_tools()

        assert tools is not None
        tool_names = {t["function"]["name"] for t in tools}
        assert "some_random_tool" not in tool_names

    @pytest.mark.asyncio
    async def test_sandboxd_gated_by_feature_flag(self, mock_registry):
        """sandboxd tools excluded when SANDBOXD_ENABLED=False."""
        from app.services.chat_service import _get_chat_openai_tools

        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.SANDBOXD_ENABLED = False
            with patch("app.tools.base._tool_registry", mock_registry):
                tools = await _get_chat_openai_tools()

        assert tools is not None
        tool_names = {t["function"]["name"] for t in tools}
        assert "sandboxd_preview" not in tool_names

    @pytest.mark.asyncio
    async def test_sandboxd_included_when_enabled(self, mock_registry):
        """sandboxd tools included when SANDBOXD_ENABLED=True."""
        from app.services.chat_service import _get_chat_openai_tools

        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.SANDBOXD_ENABLED = True
            with patch("app.tools.base._tool_registry", mock_registry):
                tools = await _get_chat_openai_tools()

        assert tools is not None
        tool_names = {t["function"]["name"] for t in tools}
        assert "sandboxd_preview" in tool_names
