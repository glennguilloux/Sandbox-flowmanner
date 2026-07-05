"""Tests for workspace tool allowlist — Phase 5.

Covers:
- WorkspaceToolAllowlist model CRUD
- get_workspace_tool_allowlist() helper
- ToolRegistry.get_permitted_tools() filtering
- Unique constraint enforcement
- Default behaviour (no entries → all tools permitted)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.base import BaseTool, ToolMetadata, ToolRegistry, ToolResult

# ── Helpers ────────────────────────────────────────────────────────


def _make_tool(tool_id: str, **kwargs) -> BaseTool:
    """Create a minimal tool for testing."""
    metadata = ToolMetadata(
        tool_id=tool_id,
        name=kwargs.get("name", tool_id),
        description=f"Test tool {tool_id}",
        category=kwargs.get("category", "general"),
    )
    tool = MagicMock(spec=BaseTool)
    tool.tool_id = tool_id
    tool.name = metadata.name
    tool.description = metadata.description
    tool.category = metadata.category
    tool.metadata = metadata
    tool.tags = []
    return tool


# ── ToolRegistry.get_permitted_tools ──────────────────────────────


class TestGetPermittedTools:
    def test_none_returns_all(self):
        """When allowlist is None, all tools are returned."""
        registry = ToolRegistry()
        t1 = _make_tool("tool_a")
        t2 = _make_tool("tool_b")
        t3 = _make_tool("tool_c")
        registry.register(t1)
        registry.register(t2)
        registry.register(t3)

        result = registry.get_permitted_tools(None)
        assert len(result) == 3
        tool_ids = {t.tool_id for t in result}
        assert tool_ids == {"tool_a", "tool_b", "tool_c"}

    def test_filters_by_allowed_names(self):
        """Only tools in the allowed set are returned."""
        registry = ToolRegistry()
        t1 = _make_tool("tool_a")
        t2 = _make_tool("tool_b")
        t3 = _make_tool("tool_c")
        registry.register(t1)
        registry.register(t2)
        registry.register(t3)

        result = registry.get_permitted_tools({"tool_a", "tool_c"})
        assert len(result) == 2
        tool_ids = {t.tool_id for t in result}
        assert tool_ids == {"tool_a", "tool_c"}

    def test_empty_allowed_returns_empty(self):
        """An empty allowlist means no tools permitted."""
        registry = ToolRegistry()
        registry.register(_make_tool("tool_a"))

        result = registry.get_permitted_tools(set())
        assert len(result) == 0

    def test_unknown_tool_ids_ignored(self):
        """Tool IDs in the allowlist that aren't registered are silently ignored."""
        registry = ToolRegistry()
        registry.register(_make_tool("tool_a"))

        result = registry.get_permitted_tools({"tool_a", "nonexistent_tool"})
        assert len(result) == 1
        assert result[0].tool_id == "tool_a"

    def test_empty_registry(self):
        """Empty registry with any allowlist returns empty."""
        registry = ToolRegistry()

        assert registry.get_permitted_tools(None) == []
        assert registry.get_permitted_tools({"tool_a"}) == []


# ── get_workspace_tool_allowlist helper ────────────────────────────


class TestGetWorkspaceToolAllowlist:
    @pytest.mark.asyncio
    async def test_no_entries_returns_none(self):
        """When no allowlist rows exist, returns None (all tools permitted)."""
        from app.models.workspace_models import get_workspace_tool_allowlist

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await get_workspace_tool_allowlist(mock_db, "ws-123")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_active_tools(self):
        """Returns set of tool names for active entries."""
        from app.models.workspace_models import get_workspace_tool_allowlist

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            "sandboxd_preview",
            "web_search_enhanced",
        ]
        mock_db.execute.return_value = mock_result

        result = await get_workspace_tool_allowlist(mock_db, "ws-123")
        assert result == {"sandboxd_preview", "web_search_enhanced"}

    @pytest.mark.asyncio
    async def test_empty_active_set_returns_none(self):
        """When the query returns empty list, returns None."""
        from app.models.workspace_models import get_workspace_tool_allowlist

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await get_workspace_tool_allowlist(mock_db, "ws-456")
        assert result is None


# ── WorkspaceToolAllowlist model shape ─────────────────────────────


class TestWorkspaceToolAllowlistModel:
    def test_table_name(self):
        from app.models.workspace_models import WorkspaceToolAllowlist

        assert WorkspaceToolAllowlist.__tablename__ == "workspace_tool_allowlist"

    def test_unique_constraint_name(self):
        from app.models.workspace_models import WorkspaceToolAllowlist

        constraint_names = [c.name for c in WorkspaceToolAllowlist.__table_args__]
        assert "uq_workspace_tool" in constraint_names

    def test_has_required_columns(self):
        from app.models.workspace_models import WorkspaceToolAllowlist

        columns = {c.name for c in WorkspaceToolAllowlist.__table__.columns}
        required = {"id", "workspace_id", "tool_name", "is_active", "granted_by", "created_at", "updated_at"}
        assert required.issubset(columns)

    def test_is_active_default(self):
        """is_active column has server_default of 'true'."""
        from app.models.workspace_models import WorkspaceToolAllowlist

        col = WorkspaceToolAllowlist.__table__.columns["is_active"]
        assert col.server_default is not None


# ── Integration: allowlist + registry ──────────────────────────────


class TestAllowlistRegistryIntegration:
    def test_full_pipeline(self):
        """Simulate: allowlist returns subset → registry filters."""
        registry = ToolRegistry()
        for tid in ["sandboxd_preview", "web_search_enhanced", "rag_search", "browser_sandbox"]:
            registry.register(_make_tool(tid))

        # Workspace only allows sandboxd_preview and rag_search
        allowlist = {"sandboxd_preview", "rag_search"}
        permitted = registry.get_permitted_tools(allowlist)

        assert len(permitted) == 2
        ids = {t.tool_id for t in permitted}
        assert ids == {"sandboxd_preview", "rag_search"}

    def test_no_allowlist_permit_all(self):
        """When allowlist is None (no entries in DB), all tools pass."""
        registry = ToolRegistry()
        for tid in ["a", "b", "c"]:
            registry.register(_make_tool(tid))

        permitted = registry.get_permitted_tools(None)
        assert len(permitted) == 3
