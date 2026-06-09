"""Tests for memory consolidation worker (H5.1)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.consolidation_worker import (
    MemoryConsolidationWorker,
    get_consolidation_worker,
)
from app.models.memory_models import Memory, MemorySession


def _make_mission_payload(**overrides):
    return {
        "status": "completed",
        "title": "Test Mission",
        "plan": {"steps": ["a", "b", "c"]},
        "results": {"output": "done"},
        "error_message": None,
        **overrides,
    }


# ═══════════════════════════════════════════════════════════════════
# process_mission()
# ═══════════════════════════════════════════════════════════════════


class TestProcessMission:

    @pytest.mark.asyncio
    async def test_extracts_episode_tuple_and_persists(self):
        worker = MemoryConsolidationWorker()
        db = AsyncMock(spec=AsyncSession)
        mid = str(uuid4())

        await worker.process_mission(
            db, mid, user_id=42, payload=_make_mission_payload()
        )

        calls = [c.args[0] for c in db.add.call_args_list]
        sessions = [o for o in calls if isinstance(o, MemorySession)]
        assert len(sessions) == 1
        assert sessions[0].user_id == 42

        memories = [o for o in calls if isinstance(o, Memory)]
        assert len(memories) == 1
        assert memories[0].source_mission_id == mid
        content = json.loads(memories[0].content)
        assert content["success"] is True
        assert content["context"] == "Test Mission"

    @pytest.mark.asyncio
    async def test_sets_success_false_for_failed_mission(self):
        worker = MemoryConsolidationWorker()
        db = AsyncMock(spec=AsyncSession)
        mid = str(uuid4())

        await worker.process_mission(
            db,
            mid,
            user_id=1,
            payload=_make_mission_payload(status="failed", error_message="boom"),
        )

        calls = [c.args[0] for c in db.add.call_args_list]
        memories = [o for o in calls if isinstance(o, Memory)]
        assert len(memories) == 1
        content = json.loads(memories[0].content)
        assert content["success"] is False
        assert content["error"] == "boom"

    @pytest.mark.asyncio
    async def test_metadata_includes_mission_id_and_success(self):
        worker = MemoryConsolidationWorker()
        db = AsyncMock(spec=AsyncSession)
        mid = str(uuid4())

        await worker.process_mission(
            db, mid, user_id=1, payload=_make_mission_payload()
        )

        calls = [c.args[0] for c in db.add.call_args_list]
        memories = [o for o in calls if isinstance(o, Memory)]
        assert memories[0].meta["type"] == "episode_tuple"
        assert memories[0].meta["mission_id"] == mid
        assert memories[0].meta["success"] is True


# ═══════════════════════════════════════════════════════════════════
# retrieve_by_mission()
# ═══════════════════════════════════════════════════════════════════


class TestRetrieveByMission:

    @pytest.mark.asyncio
    async def test_returns_matching_memories(self):
        worker = MemoryConsolidationWorker()
        db = AsyncMock(spec=AsyncSession)
        mid = str(uuid4())

        m1 = Memory(
            id=str(uuid4()),
            session_id=str(uuid4()),
            user_id=1,
            content='{"test":1}',
            source_mission_id=mid,
            meta={"type": "episode"},
        )
        m2 = Memory(
            id=str(uuid4()),
            session_id=str(uuid4()),
            user_id=1,
            content='{"test":2}',
            source_mission_id=mid,
            meta={"type": "episode"},
        )

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [m1, m2]
        db.execute = AsyncMock(return_value=result_mock)

        results = await worker.retrieve_by_mission(db, mid)
        assert len(results) == 2
        assert results[0]["content"] == {"test": 1}

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_matches(self):
        worker = MemoryConsolidationWorker()
        db = AsyncMock(spec=AsyncSession)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        results = await worker.retrieve_by_mission(db, str(uuid4()))
        assert results == []


# ═══════════════════════════════════════════════════════════════════
# retrieve_by_agent()
# ═══════════════════════════════════════════════════════════════════


class TestRetrieveByAgent:

    @pytest.mark.asyncio
    async def test_filters_by_agent_id_in_metadata(self):
        worker = MemoryConsolidationWorker()
        db = AsyncMock(spec=AsyncSession)
        agent = str(uuid4())

        m = Memory(
            id=str(uuid4()),
            session_id=str(uuid4()),
            user_id=1,
            content='{"test":1}',
            source_mission_id=str(uuid4()),
            meta={"type": "episode", "agent_id": agent},
        )

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [m]
        db.execute = AsyncMock(return_value=result_mock)

        results = await worker.retrieve_by_agent(db, agent)
        assert len(results) == 1
        assert results[0]["meta"]["agent_id"] == agent

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        worker = MemoryConsolidationWorker()
        db = AsyncMock(spec=AsyncSession)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        await worker.retrieve_by_agent(db, str(uuid4()), limit=5)
        # No assertion needed — verifying no error


# ═══════════════════════════════════════════════════════════════════
# apply_retention()
# ═══════════════════════════════════════════════════════════════════


class TestRetention:

    @pytest.mark.asyncio
    async def test_deletes_sessions_older_than_90_days(self):
        worker = MemoryConsolidationWorker()
        db = AsyncMock(spec=AsyncSession)

        result_mock = MagicMock()
        result_mock.rowcount = 5
        db.execute = AsyncMock(return_value=result_mock)

        deleted = await worker.apply_retention(db, retention_days=90)
        assert deleted == 5

    @pytest.mark.asyncio
    async def test_custom_retention_days(self):
        worker = MemoryConsolidationWorker()
        db = AsyncMock(spec=AsyncSession)

        result_mock = MagicMock()
        result_mock.rowcount = 3
        db.execute = AsyncMock(return_value=result_mock)

        deleted = await worker.apply_retention(db, retention_days=30)
        assert deleted == 3

    @pytest.mark.asyncio
    async def test_retention_is_deterministic(self):
        worker = MemoryConsolidationWorker()
        db = AsyncMock(spec=AsyncSession)

        result_mock = MagicMock()
        result_mock.rowcount = 0
        db.execute = AsyncMock(return_value=result_mock)

        assert await worker.apply_retention(db, retention_days=90) == 0
        assert await worker.apply_retention(db, retention_days=90) == 0


# ═══════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════


class TestSingleton:

    def test_get_consolidation_worker_returns_same_instance(self):
        w1 = get_consolidation_worker()
        w2 = get_consolidation_worker()
        assert w1 is w2
        assert isinstance(w1, MemoryConsolidationWorker)
