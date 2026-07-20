"""Unit tests for NodeExecutor._handle_memory_write (Safety & State, T3-02).

The memory_write handler upserts a payload into the shared Qdrant
``flowmanner_memory`` collection. These tests mock the Qdrant client and the
embedding model so they run hermetically on the host (no Qdrant, no
sentence-transformers download).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.substrate.node_executor import NodeExecutor
from app.services.substrate.workflow_models import NodeType, WorkflowNode


def _make_node(config: dict | None = None) -> WorkflowNode:
    return WorkflowNode(
        id=str(uuid4()),
        type=NodeType.MEMORY_WRITE,
        title="Memory Write",
        config=config or {},
    )


def _make_executor() -> NodeExecutor:
    mock_executor = MagicMock()
    mock_executor.is_aborted = MagicMock(return_value=False)
    mock_executor.is_running = MagicMock(return_value=True)
    mock_executor.event_log = MagicMock()
    mock_executor.event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])
    return NodeExecutor(mock_executor)


def _patch_qdrant(mock_client: MagicMock):
    """Patch the lazily-imported qdrant_client + PointStruct + settings.

    Returns the patch context manager. The embedding model is patched
    separately per test via ``NodeExecutor._embed_memory``.
    """
    mock_qdrant_module = MagicMock()
    mock_qdrant_module.QdrantClient.return_value = mock_client
    mock_models_module = MagicMock()
    # PointStruct just echoes its kwargs so we can inspect them.
    mock_models_module.PointStruct.side_effect = lambda **kw: kw
    mock_config_module = MagicMock()
    mock_config_module.settings.QDRANT_URL = "http://qdrant:6333"

    return patch.dict(
        "sys.modules",
        {
            "qdrant_client": mock_qdrant_module,
            "qdrant_client.models": mock_models_module,
            "app.config": mock_config_module,
        },
    )


class TestHandleMemoryWrite:
    @pytest.mark.asyncio
    async def test_upsert_called_with_default_collection_and_vector(self):
        ne = _make_executor()
        node = _make_node(config={"payload": {"key": "value"}})
        mock_client = MagicMock()

        with (
            _patch_qdrant(mock_client),
            patch.object(NodeExecutor, "_embed_memory", return_value=[0.1] * 384),
        ):
            result = await ne._handle_memory_write(node, {})

        assert result["success"] is True
        mock_client.upsert.assert_called_once()
        _, kwargs = mock_client.upsert.call_args
        # Correct shared collection.
        assert kwargs["collection_name"] == "flowmanner_memory"
        # Correct vector (from the embedding model).
        point = kwargs["points"][0]
        assert point["vector"] == [0.1] * 384
        assert point["payload"]["payload"] == {"key": "value"}
        # Output reports the id + collection.
        assert result["output"]["collection"] == "flowmanner_memory"
        assert result["output"]["id"] == point["id"]

    @pytest.mark.asyncio
    async def test_collection_override_via_config(self):
        ne = _make_executor()
        node = _make_node(config={"collection": "custom_mem", "payload": "hello"})
        mock_client = MagicMock()

        with (
            _patch_qdrant(mock_client),
            patch.object(NodeExecutor, "_embed_memory", return_value=[0.2] * 384),
        ):
            result = await ne._handle_memory_write(node, {})

        assert result["success"] is True
        _, kwargs = mock_client.upsert.call_args
        assert kwargs["collection_name"] == "custom_mem"
        assert result["output"]["collection"] == "custom_mem"

    @pytest.mark.asyncio
    async def test_embedding_unavailable_falls_back_to_zero_vector(self):
        ne = _make_executor()
        node = _make_node(config={"payload": {"a": 1}})
        mock_client = MagicMock()

        with (
            _patch_qdrant(mock_client),
            patch.object(NodeExecutor, "_embed_memory", return_value=None),
        ):
            result = await ne._handle_memory_write(node, {})

        assert result["success"] is True
        _, kwargs = mock_client.upsert.call_args
        point = kwargs["points"][0]
        # Falls back to a zero vector of the model dimension so the write lands.
        assert point["vector"] == [0.0] * 384

    @pytest.mark.asyncio
    async def test_payload_defaults_to_context_input(self):
        ne = _make_executor()
        node = _make_node(config={})  # no explicit payload
        mock_client = MagicMock()
        context = {"input": {"from": "context"}}

        with (
            _patch_qdrant(mock_client),
            patch.object(NodeExecutor, "_embed_memory", return_value=[0.0] * 384),
        ):
            result = await ne._handle_memory_write(node, context)

        assert result["success"] is True
        _, kwargs = mock_client.upsert.call_args
        point = kwargs["points"][0]
        assert point["payload"]["payload"] == {"from": "context"}

    @pytest.mark.asyncio
    async def test_upsert_failure_returns_error(self):
        ne = _make_executor()
        node = _make_node(config={"payload": "x"})
        mock_client = MagicMock()
        mock_client.upsert.side_effect = RuntimeError("qdrant down")

        with (
            _patch_qdrant(mock_client),
            patch.object(NodeExecutor, "_embed_memory", return_value=[0.0] * 384),
        ):
            result = await ne._handle_memory_write(node, {})

        assert result["success"] is False
        assert "Memory write failed" in result["error"]

    @pytest.mark.asyncio
    async def test_dispatch_routes_memory_write_to_handler(self):
        ne = _make_executor()
        node = _make_node(config={"payload": "y"})
        mock_client = MagicMock()

        with (
            _patch_qdrant(mock_client),
            patch.object(NodeExecutor, "_embed_memory", return_value=[0.3] * 384),
        ):
            budget = MagicMock()
            result = await ne._dispatch(MagicMock(), node, {}, budget, run_id="run-1")

        assert result["success"] is True
        mock_client.upsert.assert_called_once()


class TestMemoryCollectionHelper:
    def test_default_collection(self):
        assert NodeExecutor._memory_collection() == "flowmanner_memory"

    def test_none_node_uses_default(self):
        assert NodeExecutor._memory_collection(None) == "flowmanner_memory"

    def test_config_override(self):
        node = _make_node(config={"collection": "  scoped_mem  "})
        assert NodeExecutor._memory_collection(node) == "scoped_mem"

    def test_blank_override_ignored(self):
        node = _make_node(config={"collection": "   "})
        assert NodeExecutor._memory_collection(node) == "flowmanner_memory"
