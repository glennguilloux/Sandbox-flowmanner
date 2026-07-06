"""Tests for the chat tool allowlist (Task 1.1).

Verifies that:
- Phase 3 read-only tools are present in the allowlist
- Write tools (slack_post_message, linear_create_issue) are still absent
- sandboxd tools are absent when SANDBOXD_ENABLED=False
"""

import asyncio
import contextlib
import importlib
import os
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _populate_registry():
    """Import all tool modules to populate the registry before tests."""
    tools_dir = "/app/app/tools"
    if not os.path.isdir(tools_dir):
        tools_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "tools")
    for f in sorted(os.listdir(tools_dir)):
        if not f.endswith(".py") or f.startswith("__"):
            continue
        if f in ("base.py", "_file_utils.py", "_rlimits.py", "redis_cache.py", "data.py"):
            continue
        with contextlib.suppress(Exception):
            importlib.import_module(f"app.tools.{f[:-3]}")


def _get_chat_tool_ids():
    """Get the set of tool IDs from the chat allowlist."""
    from app.services.chat_service import _get_chat_openai_tools

    tools = asyncio.run(_get_chat_openai_tools(db=None, workspace_id=None))
    if tools is None:
        return set()
    return {t["function"]["name"] for t in tools}


def test_phase3_readonly_tools_present():
    """Phase 3 read-only tools should be in the chat allowlist."""
    tool_ids = _get_chat_tool_ids()
    expected = {
        "dall_e_image_gen",
        "crypto_market_data",
        "global_news_aggregator",
        "arxiv_paper_finder",
        "google_search_api",
        "fact_check_validator",
        "html_to_markdown",
        "pdf_parser",
        "deep_web_crawler",
        "wikipedia_fetcher",
        "ocr_text_extractor",
    }
    # Filter to only tools that are actually registered (may skip if deps missing)
    from app.tools.base import get_tool_registry

    registry = get_tool_registry()
    registered = {t.tool_id for t in registry.list_all()}
    available_expected = expected & registered

    missing = available_expected - tool_ids
    assert not missing, f"Expected tools not in allowlist: {missing}"


def test_write_tools_absent():
    """Write tools should NOT be in the chat allowlist."""
    tool_ids = _get_chat_tool_ids()
    forbidden = {"slack_post_message", "linear_create_issue"}
    found = forbidden & tool_ids
    assert not found, f"Write tools should not be in allowlist: {found}"


def test_sandboxd_absent_when_disabled():
    """sandboxd tools should be absent when SANDBOXD_ENABLED is False."""
    with patch("app.services.chat_service.settings") as mock_settings:
        mock_settings.SANDBOXD_ENABLED = False
        from app.services.chat_service import _get_chat_openai_tools

        tools = asyncio.run(_get_chat_openai_tools(db=None, workspace_id=None))
        if tools is None:
            return  # no tools at all is fine
        tool_ids = {t["function"]["name"] for t in tools}
        sandboxd = {"sandboxd_preview", "sandboxd_exec", "sandboxd_file_write"}
        found = sandboxd & tool_ids
        assert not found, f"sandboxd tools present when disabled: {found}"
