"""Tests for scripts/import_bindings.py

Verifies that the binding import script correctly extracts tool and
capability references from agent_templates.definition and creates
rows in agent_tool_bindings / agent_capability_bindings.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


def _make_agent_row(template_id, slug, name, definition_dict):
    """Create a mock agent_templates row."""
    row = MagicMock()
    row.template_id = template_id
    row.slug = slug
    row.name = name
    row.definition = definition_dict
    return row


def _make_catalog_row(id_, slug):
    """Create a mock catalog row."""
    row = MagicMock()
    row.id = id_
    row.slug = slug
    return row


class TestImportBindingsLogic:
    """Test the core logic of the import script using mock DB."""

    @pytest.mark.asyncio
    async def test_tool_bindings_created_from_definition(self):
        """Agent with tools in definition should produce agent_tool_bindings rows."""
        from scripts.import_bindings import run

        agent = _make_agent_row(
            "tid-1",
            "general-assistant-v1",
            "General Assistant",
            {
                "tools": [
                    {"tool_id": "web_search", "enabled": True},
                    {"tool_id": "calculator", "enabled": True},
                ],
                "capabilities": ["chat", "analysis"],
            },
        )

        tool_row_ws = _make_catalog_row("tool-uuid-ws", "web_search")
        tool_row_calc = _make_catalog_row("tool-uuid-calc", "calculator")
        cap_row_chat = _make_catalog_row("cap-uuid-chat", "chat")
        cap_row_analysis = _make_catalog_row("cap-uuid-analysis", "analysis")

        mock_conn = AsyncMock()

        # Sequence of execute calls:
        # 1. tools_catalog SELECT → tool rows
        # 2. capabilities_catalog SELECT → cap rows
        # 3. agent_templates SELECT → agent rows
        # 4+. INSERT bindings
        tool_result = MagicMock()
        tool_result.fetchall.return_value = [tool_row_ws, tool_row_calc]

        cap_result = MagicMock()
        cap_result.fetchall.return_value = [cap_row_chat, cap_row_analysis]

        agent_result = MagicMock()
        agent_result.fetchall.return_value = [agent]

        insert_result = MagicMock()
        insert_result.rowcount = 1

        mock_conn.execute = AsyncMock(
            side_effect=[
                tool_result,
                cap_result,
                agent_result,
                insert_result,
                insert_result,  # tool bindings
                insert_result,
                insert_result,
            ]  # cap bindings
        )

        mock_engine = MagicMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_engine.dispose = AsyncMock()

        with patch(
            "sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine
        ), patch("app.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://test"
            await run()

        # Verify 4 insert calls were made (2 tool bindings + 2 cap bindings)
        # sa_text() creates TextClause objects; check .text attr for SQL string
        insert_calls = []
        for c in mock_conn.execute.call_args_list:
            stmt = c.args[0] if c.args else c.kwargs.get("statement", None)
            if (
                stmt is not None
                and hasattr(stmt, "text")
                and "INSERT INTO" in stmt.text
            ):
                insert_calls.append(c)
        assert len(insert_calls) == 4

        # Verify the tool binding inserts reference the correct IDs
        tool_inserts = [
            c for c in insert_calls if "agent_tool_bindings" in c.args[0].text
        ]
        assert len(tool_inserts) == 2

    @pytest.mark.asyncio
    async def test_missing_tool_slug_skipped(self):
        """Tool IDs not in tools_catalog should be skipped gracefully."""
        from scripts.import_bindings import run

        agent = _make_agent_row(
            "tid-2",
            "content-writer-v1",
            "Content Writer",
            {
                "tools": [{"tool_id": "seo_analyzer", "enabled": True}],
                "capabilities": [],
            },
        )

        # seo_analyzer not in catalog
        tool_result = MagicMock()
        tool_result.fetchall.return_value = []  # empty catalog

        cap_result = MagicMock()
        cap_result.fetchall.return_value = []

        agent_result = MagicMock()
        agent_result.fetchall.return_value = [agent]

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(
            side_effect=[tool_result, cap_result, agent_result]
        )

        mock_engine = MagicMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_engine.dispose = AsyncMock()

        with patch(
            "sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine
        ), patch("app.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://test"
            await run()

        # No insert calls — the tool slug wasn't found
        insert_calls = []
        for c in mock_conn.execute.call_args_list:
            stmt = c.args[0] if c.args else None
            if (
                stmt is not None
                and hasattr(stmt, "text")
                and "INSERT INTO" in stmt.text
            ):
                insert_calls.append(c)
        assert len(insert_calls) == 0

    @pytest.mark.asyncio
    async def test_no_definition_skipped(self):
        """Agent with no definition should be silently skipped."""
        from scripts.import_bindings import run

        agent = _make_agent_row("tid-3", "md-agent", "MD Agent", None)

        tool_result = MagicMock()
        tool_result.fetchall.return_value = []

        cap_result = MagicMock()
        cap_result.fetchall.return_value = []

        agent_result = MagicMock()
        agent_result.fetchall.return_value = [agent]

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(
            side_effect=[tool_result, cap_result, agent_result]
        )

        mock_engine = MagicMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_engine.dispose = AsyncMock()

        with patch(
            "sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine
        ), patch("app.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://test"
            await run()

        # Only 3 execute calls (tool query, cap query, agent query) — no inserts
        assert mock_conn.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_string_tool_ids_handled(self):
        """Tool configs as plain strings (not dicts) should work."""
        from scripts.import_bindings import run

        agent = _make_agent_row(
            "tid-4",
            "test-agent",
            "Test Agent",
            {"tools": ["web_search"], "capabilities": []},
        )

        tool_row = _make_catalog_row("tool-uuid-ws", "web_search")

        tool_result = MagicMock()
        tool_result.fetchall.return_value = [tool_row]

        cap_result = MagicMock()
        cap_result.fetchall.return_value = []

        agent_result = MagicMock()
        agent_result.fetchall.return_value = [agent]

        insert_result = MagicMock()
        insert_result.rowcount = 1

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(
            side_effect=[tool_result, cap_result, agent_result, insert_result]
        )

        mock_engine = MagicMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_engine.dispose = AsyncMock()

        with patch(
            "sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine
        ), patch("app.config.settings") as mock_settings:
            mock_settings.DATABASE_URL = "postgresql+asyncpg://test"
            await run()

        insert_calls = []
        for c in mock_conn.execute.call_args_list:
            stmt = c.args[0] if c.args else None
            if (
                stmt is not None
                and hasattr(stmt, "text")
                and "INSERT INTO" in stmt.text
            ):
                insert_calls.append(c)
        assert len(insert_calls) == 1
