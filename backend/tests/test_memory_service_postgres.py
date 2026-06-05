"""Tests for the Postgres-first MemoryService (Phase 1 of Postgres-native migration).

Validates:
- Agent memory store/retrieve via Postgres (memory_entries table)
- Simple KV store/retrieve via Postgres
- Redis cache is optional (graceful degradation when Redis unavailable)
- delete_memory removes from Postgres and invalidates cache
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.memory_service import MemoryService, _MISSING


# ── Helpers ────────────────────────────────────────────────────────


def _make_entry(**overrides):
    """Build a mock MemoryEntry row."""
    from app.models.memory_models import MemoryEntry
    from datetime import datetime, timezone

    defaults = {
        "id": str(uuid4()),
        "agent_id": "test-agent",
        "namespace": "agent",
        "memory_type": "episodic",
        "content": "test content",
        "importance": 0.7,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "meta": {},
    }
    defaults.update(overrides)

    entry = MagicMock(spec=MemoryEntry)
    for k, v in defaults.items():
        setattr(entry, k, v)
    return entry


# ═══════════════════════════════════════════════════════════════════
# store() — agent memory
# ═══════════════════════════════════════════════════════════════════


class TestStoreAgentMemory:

    @pytest.mark.asyncio
    async def test_store_writes_to_postgres(self):
        """Agent memory store must create a MemoryEntry in Postgres."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        svc = MemoryService(db=mock_session)
        result = await svc.store(
            agent_id="agent-1",
            content="Remember this",
            memory_type="episodic",
            importance=0.8,
            metadata={"key": "val"},
            user_id=42,
        )

        assert result is not None
        assert result["agent_id"] == "agent-1"
        assert result["content"] == "Remember this"
        assert result["importance"] == 0.8
        assert "id" in result
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_store_with_tags_in_metadata(self):
        """Tags should be merged into the metadata dict."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        svc = MemoryService(db=mock_session)
        result = await svc.store(
            agent_id="agent-1",
            content="tagged memory",
            tags=["important", "user"],
        )

        assert result is not None
        meta = result["metadata"]
        assert meta["tags"] == ["important", "user"]

    @pytest.mark.asyncio
    async def test_store_returns_none_on_db_error(self):
        """Postgres write failure should return None, not raise."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock(side_effect=RuntimeError("DB down"))

        svc = MemoryService(db=mock_session)
        result = await svc.store(agent_id="agent-1", content="fail test")

        assert result is None


# ═══════════════════════════════════════════════════════════════════
# store() — simple KV
# ═══════════════════════════════════════════════════════════════════


class TestStoreSimpleKV:

    @pytest.mark.asyncio
    async def test_store_simple_returns_false_for_no_args(self):
        """Calling store() with no key and no agent_id should return False."""
        svc = MemoryService()
        result = await svc.store()
        assert result is False

    @pytest.mark.asyncio
    async def test_store_simple_writes_to_postgres(self):
        """KV store must create a MemoryEntry with namespace='kv'."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        svc = MemoryService(db=mock_session)
        result = await svc.store(key="config:theme", value={"color": "dark"})

        assert result is True
        mock_session.add.assert_called_once()
        added_entry = mock_session.add.call_args[0][0]
        assert added_entry.namespace == "kv"
        assert added_entry.key == "config:theme"
        assert json.loads(added_entry.content) == {"color": "dark"}

    @pytest.mark.asyncio
    async def test_store_simple_returns_false_on_db_error(self):
        """KV store should return False when Postgres write fails."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock(side_effect=RuntimeError("DB down"))

        svc = MemoryService(db=mock_session)
        result = await svc.store(key="k", value="v")
        assert result is False

    @pytest.mark.asyncio
    async def test_retrieve_simple_kv_from_postgres(self):
        """retrieve() should read KV entries from Postgres."""
        entry = MagicMock()
        entry.content = json.dumps({"color": "dark"})

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = entry
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.close = AsyncMock()

        svc = MemoryService(db=mock_session)
        value = await svc.retrieve("config:theme")

        assert value == {"color": "dark"}

    @pytest.mark.asyncio
    async def test_retrieve_simple_kv_returns_none_when_missing(self):
        """retrieve() should return None when key not found."""
        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.close = AsyncMock()

        svc = MemoryService(db=mock_session)
        value = await svc.retrieve("nonexistent")

        assert value is None

    @pytest.mark.asyncio
    async def test_store_simple_upserts_on_duplicate_key(self):
        """Storing the same key twice should delete-then-insert (no duplicates)."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        svc = MemoryService(db=mock_session)

        # First store
        await svc.store(key="theme", value={"color": "dark"})
        # Second store (overwrite)
        await svc.store(key="theme", value={"color": "light"})

        # Both calls should have succeeded
        assert mock_session.add.call_count == 2
        # The delete should have been called (via execute) before the second add
        assert mock_session.execute.call_count == 2  # 2 deletes (one per store)


# ═══════════════════════════════════════════════════════════════════
# retrieve_by_query()
# ═══════════════════════════════════════════════════════════════════


class TestRetrieveByQuery:

    @pytest.mark.asyncio
    async def test_returns_memories_from_postgres(self):
        """Should query Postgres and return formatted memory dicts."""
        entry = _make_entry(
            id="mem-1",
            agent_id="agent-1",
            content="Python is great",
            importance=0.9,
        )

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [entry]
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.close = AsyncMock()

        svc = MemoryService(db=mock_session)
        results = await svc.retrieve_by_query(
            agent_id="agent-1", query="python", limit=5
        )

        assert len(results) == 1
        assert results[0]["id"] == "mem-1"
        assert results[0]["content"] == "Python is great"

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(self):
        """DB errors should return empty list, not raise."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB down"))
        mock_session.close = AsyncMock()

        svc = MemoryService(db=mock_session)
        results = await svc.retrieve_by_query(agent_id="agent-1")

        assert results == []

    @pytest.mark.asyncio
    async def test_query_filters_by_keyword(self):
        """Keyword matching should filter results."""
        entry1 = _make_entry(content="Python is great", importance=0.9)
        entry2 = _make_entry(content="JavaScript is fine", importance=0.8)

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [entry1, entry2]
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.close = AsyncMock()

        svc = MemoryService(db=mock_session)
        results = await svc.retrieve_by_query(
            agent_id="agent-1", query="python", limit=5
        )

        # Only "Python is great" matches the query
        assert len(results) == 1
        assert "Python" in results[0]["content"]


# ═══════════════════════════════════════════════════════════════════
# delete_memory()
# ═══════════════════════════════════════════════════════════════════


class TestDeleteMemory:

    @pytest.mark.asyncio
    async def test_delete_returns_true_when_found(self):
        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.commit = AsyncMock()

        svc = MemoryService(db=mock_session)
        deleted = await svc.delete_memory("mem-1")

        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self):
        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.rowcount = 0
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.commit = AsyncMock()

        svc = MemoryService(db=mock_session)
        deleted = await svc.delete_memory("nonexistent")

        assert deleted is False


# ═══════════════════════════════════════════════════════════════════
# Redis cache — graceful degradation
# ═══════════════════════════════════════════════════════════════════


class TestRedisCacheOptional:

    @pytest.mark.asyncio
    async def test_store_succeeds_without_redis(self):
        """Memory store should work even when Redis is unavailable."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        svc = MemoryService(db=mock_session)
        # Force Redis to be unavailable
        svc._redis = None

        with patch.object(svc, "_get_redis", return_value=None):
            result = await svc.store(
                agent_id="agent-1",
                content="no redis needed",
            )

        assert result is not None
        assert result["content"] == "no redis needed"

    @pytest.mark.asyncio
    async def test_retrieve_by_query_works_without_redis(self):
        """Query retrieval should work from Postgres alone."""
        entry = _make_entry(content="Postgres-only memory")

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [entry]
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.close = AsyncMock()

        svc = MemoryService(db=mock_session)
        svc._redis = None

        results = await svc.retrieve_by_query(agent_id="agent-1")
        assert len(results) == 1


# ═══════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════


class TestSingleton:

    def test_get_memory_service_returns_instance(self):
        from app.services.memory_service import get_memory_service

        # Reset singleton for test isolation
        import app.services.memory_service as mod

        mod._memory_service_instance = None

        svc = get_memory_service()
        assert isinstance(svc, MemoryService)

        # Same instance on second call
        svc2 = get_memory_service()
        assert svc is svc2

        # Cleanup
        mod._memory_service_instance = None
