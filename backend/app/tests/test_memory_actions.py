"""Tests for memory action events — model, service, and API.

Tests follow the pattern from test_background_review.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.memory_action_models import (
    ALL_MEMORY_ACTION_TYPES,
    MemoryActionEvent,
    MemoryActionType,
)

# ── Model tests ───────────────────────────────────────────────────────


class TestMemoryActionType:
    """Verify the action type constants are defined."""

    def test_all_types_present(self):
        assert len(ALL_MEMORY_ACTION_TYPES) == 7

    def test_log_observation(self):
        assert MemoryActionType.LOG_OBSERVATION == "log_observation"

    def test_recall_episodic(self):
        assert MemoryActionType.RECALL_EPISODIC == "recall_episodic"

    def test_recall_semantic(self):
        assert MemoryActionType.RECALL_SEMANTIC == "recall_semantic"

    def test_consolidate(self):
        assert MemoryActionType.CONSOLIDATE == "consolidate"

    def test_forget_low_quality(self):
        assert MemoryActionType.FORGET_LOW_QUALITY == "forget_low_quality"

    def test_promote(self):
        assert MemoryActionType.PROMOTE == "promote"

    def test_log_tool_result(self):
        assert MemoryActionType.LOG_TOOL_RESULT == "log_tool_result"


class TestMemoryActionEventModel:
    """Verify the ORM model table args and columns."""

    def test_table_name(self):
        assert MemoryActionEvent.__tablename__ == "memory_action_events"

    def test_has_required_columns(self):
        columns = {c.name for c in MemoryActionEvent.__table__.columns}
        required = {
            "id",
            "workspace_id",
            "user_id",
            "mission_id",
            "action_type",
            "action_input",
            "action_result",
            "action_latency_ms",
            "action_success",
            "agent_confidence",
            "created_at",
        }
        assert required.issubset(columns)

    def test_indexes_defined(self):
        index_names = [idx.name for idx in MemoryActionEvent.__table__.indexes]
        assert "ix_mem_actions_ws_user_created" in index_names
        assert "ix_mem_actions_mission" in index_names
        assert "ix_mem_actions_type" in index_names


# ── Service tests ─────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    """Create a MemoryActionService with a mock DB."""
    from app.services.memory_action_service import MemoryActionService

    return MemoryActionService(mock_db)


class TestRecordAction:
    """Test MemoryActionService.record_action."""

    @pytest.mark.asyncio
    async def test_record_action_returns_uuid(self, service, mock_db):
        with patch.object(service, "_emit_substrate_event"):
            event_id = await service.record_action(
                workspace_id=str(uuid.uuid4()),
                user_id=1,
                action_type=MemoryActionType.LOG_OBSERVATION,
                action_input={"text": "observed something"},
                action_result={"stored": True},
                latency_ms=12.5,
                success=True,
            )
        # Should be a valid UUID string
        uuid.UUID(event_id)
        # Should have added to DB
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_action_with_mission_id(self, service, mock_db):
        mission_id = str(uuid.uuid4())
        with patch.object(service, "_emit_substrate_event") as mock_emit:
            await service.record_action(
                workspace_id=str(uuid.uuid4()),
                user_id=1,
                action_type=MemoryActionType.RECALL_EPISODIC,
                action_input={"query": "find similar"},
                action_result={"matches": []},
                latency_ms=45.0,
                success=True,
                mission_id=mission_id,
            )
        mock_emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_action_without_mission_id(self, service, mock_db):
        with patch.object(service, "_emit_substrate_event") as mock_emit:
            await service.record_action(
                workspace_id=str(uuid.uuid4()),
                user_id=1,
                action_type=MemoryActionType.LOG_OBSERVATION,
                action_input={},
                action_result={},
                latency_ms=1.0,
                success=True,
            )
        # Should NOT emit substrate event without mission_id
        mock_emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_action_with_confidence(self, service, mock_db):
        with patch.object(service, "_emit_substrate_event"):
            await service.record_action(
                workspace_id=str(uuid.uuid4()),
                user_id=1,
                action_type=MemoryActionType.RECALL_SEMANTIC,
                action_input={"query": "search"},
                action_result={"results": ["a", "b"]},
                latency_ms=30.0,
                success=True,
                agent_confidence=0.85,
            )
        event = mock_db.add.call_args[0][0]
        assert event.agent_confidence == 0.85


class TestGetEpisodeTraces:
    """Test MemoryActionService.get_episode_traces."""

    @pytest.mark.asyncio
    async def test_returns_events_ordered(self, service, mock_db):
        mission_id = str(uuid.uuid4())
        mock_event_1 = MagicMock()
        mock_event_1.created_at = datetime(2026, 7, 4, 10, 0, tzinfo=UTC)
        mock_event_2 = MagicMock()
        mock_event_2.created_at = datetime(2026, 7, 4, 10, 1, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_event_1, mock_event_2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        events = await service.get_episode_traces(mission_id)
        assert len(events) == 2
        mock_db.execute.assert_called_once()


class TestScoreEpisode:
    """Test MemoryActionService.score_episode."""

    @pytest.mark.asyncio
    async def test_score_returns_expected_structure(self, service, mock_db):
        mission_id = str(uuid.uuid4())

        # Mock the aggregate query result
        agg_row = MagicMock()
        agg_row.total = 10
        agg_row.successful = 8
        agg_row.avg_latency = 45.3

        agg_result = MagicMock()
        agg_result.first.return_value = agg_row

        # Mock the per-type query result
        type_row_1 = MagicMock()
        type_row_1.action_type = "recall_episodic"
        type_row_1.count = 5
        type_row_1.success = 5
        type_row_1.avg_latency = 30.1

        type_row_2 = MagicMock()
        type_row_2.action_type = "log_observation"
        type_row_2.count = 5
        type_row_2.success = 3
        type_row_2.avg_latency = 60.5

        type_result = MagicMock()
        type_result.all.return_value = [type_row_1, type_row_2]

        mock_db.execute = AsyncMock(side_effect=[agg_result, type_result])

        score = await service.score_episode(mission_id)

        assert score["total_actions"] == 10
        assert score["successful"] == 8
        assert score["failed"] == 2
        assert score["avg_latency_ms"] == 45.3
        assert "recall_episodic" in score["by_type"]
        assert "log_observation" in score["by_type"]


# ── API endpoint tests ────────────────────────────────────────────────


class TestMemoryActionAPI:
    """Verify the API module is importable and routes are defined."""

    def test_router_importable(self):
        from app.api.v1.memory_actions import router

        assert router.prefix == "/memory-actions"
        # Should have 2 routes
        routes = [r for r in router.routes if hasattr(r, "methods")]
        assert len(routes) == 2

    def test_endpoint_paths(self):
        from app.api.v1.memory_actions import router

        paths = {r.path for r in router.routes if hasattr(r, "path")}
        assert any("mission/{mission_id}" in p for p in paths)
        assert any("mission/{mission_id}/score" in p for p in paths)
