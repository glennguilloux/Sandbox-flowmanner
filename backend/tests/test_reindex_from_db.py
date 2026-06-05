"""Tests for Phase 2.5: reindex_from_db and /admin/reindex endpoint."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestReindexFromDB:
    """Test ToolDiscoveryService.reindex_from_db(session)."""

    @pytest.mark.asyncio
    async def test_reindex_from_db_with_tools_and_caps(self):
        """Should index tools from tools_catalog and capabilities from capabilities_catalog."""
        from app.services.tool_discovery_service import ToolDiscoveryService

        # Mock DB rows
        mock_tool = MagicMock()
        mock_tool.slug = "browser_ping"
        mock_tool.name = "Ping Browser"
        mock_tool.description = "Ping the browser"
        mock_tool.category = "browser"
        mock_tool.tags = ["browser", "ping"]
        mock_tool.handler_ref = "app.tools.browser_ping.BrowserPingTool"

        mock_cap = MagicMock()
        mock_cap.slug = "agent:general-assistant"
        mock_cap.name = "General Assistant"
        mock_cap.description = "A general assistant agent"
        mock_cap.category = "agent"
        mock_cap.handler_ref = None

        tool_result = MagicMock()
        tool_result.scalars.return_value.all.return_value = [mock_tool]

        cap_result = MagicMock()
        cap_result.scalars.return_value.all.return_value = [mock_cap]

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[tool_result, cap_result])

        service = ToolDiscoveryService()

        # Mock Qdrant client directly on the instance
        mock_client = MagicMock()
        mock_client.delete_collection = MagicMock()
        mock_client.get_collections.return_value.collections = []
        mock_client.create_collection = MagicMock()
        mock_client.upsert = MagicMock()
        service._client = mock_client

        # Mock embedding model
        mock_model = MagicMock()
        import numpy as np

        mock_model.encode.return_value = np.array([[0.1] * 384, [0.2] * 384])

        with patch.object(
            ToolDiscoveryService, "_get_embedding_model", return_value=mock_model
        ):
            result = await service.reindex_from_db(session)

        assert result["tools_indexed"] == 1
        assert result["capabilities_indexed"] == 1
        assert result["total"] == 2
        assert service._initialized is True
        assert service._indexed_count == 2

        # Verify upsert was called with 2 points via keyword args
        points = mock_client.upsert.call_args.kwargs["points"]
        assert len(points) == 2

    @pytest.mark.asyncio
    async def test_reindex_from_db_empty_tables(self):
        """Should handle empty tables gracefully."""
        from app.services.tool_discovery_service import ToolDiscoveryService

        tool_result = MagicMock()
        tool_result.scalars.return_value.all.return_value = []

        cap_result = MagicMock()
        cap_result.scalars.return_value.all.return_value = []

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[tool_result, cap_result])

        service = ToolDiscoveryService()
        service._client = MagicMock()

        result = await service.reindex_from_db(session)

        assert result["tools_indexed"] == 0
        assert result["capabilities_indexed"] == 0
        assert result["total"] == 0

    def test_build_search_text_from_row(self):
        """Static helper should produce correct embedding text."""
        from app.services.tool_discovery_service import ToolDiscoveryService

        text = ToolDiscoveryService._build_search_text_from_row(
            name="Web Search",
            description="Search the web",
            tags=["search", "web"],
            category="research",
        )
        assert "Web Search" in text
        assert "Search the web" in text
        assert "search, web" in text
        assert "Category: research" in text

    def test_build_search_text_from_row_no_tags(self):
        """Should handle empty tags."""
        from app.services.tool_discovery_service import ToolDiscoveryService

        text = ToolDiscoveryService._build_search_text_from_row(
            name="Tool",
            description="A tool",
            tags=[],
            category="general",
        )
        assert "Tags:" not in text
        assert "Tool" in text


class TestReindexResponse:
    """Test the ReindexResponse schema."""

    def test_schema_fields(self):
        from app.api.v1.admin import ReindexResponse

        r = ReindexResponse(
            tools_indexed=10, capabilities_indexed=20, total=30, source="db"
        )
        assert r.tools_indexed == 10
        assert r.capabilities_indexed == 20
        assert r.total == 30
        assert r.source == "db"
