"""Tests for Phase 2.4: TopologyManager.build_from_db and save_snapshot."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


class TestBuildFromDB:
    """Test TopologyManager.build_from_db(session)."""

    @pytest.mark.asyncio
    async def test_build_from_db_with_snapshot(self):
        """Should load topology data from the latest DB snapshot."""
        from app.services.semantic.topology_manager import TopologyManager

        snapshot_data = {
            "nodes": [
                {"id": "agent-a", "label": "Agent A", "stack": "agent"},
                {"id": "tool-b", "label": "Tool B", "stack": "tool"},
            ],
            "edges": [
                {"source": "agent-a", "target": "tool-b", "relation": "uses"},
            ],
        }

        mock_snapshot = MagicMock()
        mock_snapshot.id = "snap-1"
        mock_snapshot.version = 1
        mock_snapshot.node_count = 2
        mock_snapshot.edge_count = 1
        mock_snapshot.snapshot_data = snapshot_data

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_snapshot

        session = AsyncMock()
        session.execute.return_value = mock_result

        topo = TopologyManager()
        result = await topo.build_from_db(session)

        assert len(result["nodes"]) == 2
        assert len(result["edges"]) == 1
        assert topo.G is not None

    @pytest.mark.asyncio
    async def test_build_from_db_empty_falls_back_to_filesystem(self):
        """When no snapshots exist, should fall back to build()."""
        from app.services.semantic.topology_manager import TopologyManager

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute.return_value = mock_result

        topo = TopologyManager()
        # graph_path won't exist in tests, so build() returns empty
        result = await topo.build_from_db(session)

        assert "nodes" in result
        assert "edges" in result

    @pytest.mark.asyncio
    async def test_build_from_db_handles_string_snapshot_data(self):
        """snapshot_data stored as JSON string should be parsed."""
        from app.services.semantic.topology_manager import TopologyManager

        snapshot_data_str = json.dumps({
            "nodes": [{"id": "x", "label": "X", "stack": "test"}],
            "edges": [],
        })

        mock_snapshot = MagicMock()
        mock_snapshot.id = "snap-2"
        mock_snapshot.version = 1
        mock_snapshot.node_count = 1
        mock_snapshot.edge_count = 0
        mock_snapshot.snapshot_data = snapshot_data_str

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_snapshot

        session = AsyncMock()
        session.execute.return_value = mock_result

        topo = TopologyManager()
        result = await topo.build_from_db(session)

        assert len(result["nodes"]) == 1

    @pytest.mark.asyncio
    async def test_build_from_db_handles_links_key(self):
        """graph.json uses 'links' instead of 'edges' — should work."""
        from app.services.semantic.topology_manager import TopologyManager

        snapshot_data = {
            "nodes": [{"id": "a", "label": "A", "stack": "agent"}],
            "links": [
                {"source": "a", "target": "b", "relation": "calls"},
            ],
        }

        mock_snapshot = MagicMock()
        mock_snapshot.id = "snap-3"
        mock_snapshot.version = 1
        mock_snapshot.node_count = 1
        mock_snapshot.edge_count = 1
        mock_snapshot.snapshot_data = snapshot_data

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_snapshot

        session = AsyncMock()
        session.execute.return_value = mock_result

        topo = TopologyManager()
        result = await topo.build_from_db(session)

        # Should have built the graph with the "links" key
        assert topo.G is not None


class TestSaveSnapshot:
    """Test TopologyManager.save_snapshot(session)."""

    @pytest.mark.asyncio
    async def test_save_snapshot_creates_new_version(self):
        """Should create a new snapshot with version = max + 1."""
        from app.services.semantic.topology_manager import TopologyManager
        import networkx as nx

        topo = TopologyManager()
        topo.G = nx.DiGraph()
        topo.G.add_node("a", label="A", stack="test")
        topo.G.add_node("b", label="B", stack="test")
        topo.G.add_edge("a", "b", relation="calls", confidence="INFERRED")
        topo.communities = {0: ["a", "b"]}
        topo.embeddings = {0: {"avg_degree": 1.0, "node_count": 2}}

        # Mock: max version = 3
        mock_version_result = MagicMock()
        mock_version_result.scalar.return_value = 3

        session = AsyncMock()
        session.execute.return_value = mock_version_result

        snapshot_id = await topo.save_snapshot(session, description="test snapshot")

        assert snapshot_id is not None
        # Should have called session.add with a TopologySnapshot
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.version == 4
        assert added.node_count == 2
        assert added.edge_count == 1
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_snapshot_empty_graph(self):
        """Should handle empty graph gracefully."""
        from app.services.semantic.topology_manager import TopologyManager

        topo = TopologyManager()
        # No G set — empty topology

        mock_version_result = MagicMock()
        mock_version_result.scalar.return_value = 0

        session = AsyncMock()
        session.execute.return_value = mock_version_result

        snapshot_id = await topo.save_snapshot(session)

        assert snapshot_id is not None
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.version == 1
        assert added.node_count == 0
        assert added.edge_count == 0


class TestBuildMethod:
    """Test that the existing build() method handles both 'links' and 'edges' keys."""

    @pytest.mark.asyncio
    async def test_build_with_edges_key(self):
        """build() should accept 'edges' key as well as 'links'."""
        from app.services.semantic.topology_manager import TopologyManager

        topo = TopologyManager()
        data = {
            "nodes": [{"id": "x", "label": "X", "stack": "test"}],
            "edges": [{"source": "x", "target": "y", "relation": "calls"}],
        }
        result = await topo.build(data=data)

        assert len(result["nodes"]) >= 1

    @pytest.mark.asyncio
    async def test_build_with_links_key(self):
        """build() should accept 'links' key (original graph.json format)."""
        from app.services.semantic.topology_manager import TopologyManager

        topo = TopologyManager()
        data = {
            "nodes": [{"id": "x", "label": "X", "stack": "test"}],
            "links": [{"source": "x", "target": "y", "relation": "calls"}],
        }
        result = await topo.build(data=data)

        assert len(result["nodes"]) >= 1

    @pytest.mark.asyncio
    async def test_build_empty_data(self):
        """build() with empty data should return empty topology."""
        from app.services.semantic.topology_manager import TopologyManager

        topo = TopologyManager()
        result = await topo.build(data={"nodes": [], "edges": []})

        assert result["nodes"] == []
        assert result["edges"] == []
