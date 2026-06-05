"""Integration tests for the CQRS DI pipeline — end-to-end from route → handler → response."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api._mission_cqrs.commands import MissionCommandHandlers
from app.api._mission_cqrs.deps import get_mission_commands, get_mission_queries
from app.api._mission_cqrs.queries import MissionQueryHandlers
from app.api.deps import get_current_user
from app.database import get_db_session
from app.main_fastapi import app

MISSION_ID = uuid.UUID("014da489-b7f5-44f7-9e89-046a05a5ab56")


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_mission_orm(**overrides):
    """Create an ORM-like mock mission with all fields MissionResponse needs."""
    m = MagicMock()
    m.id = str(overrides.get("id", MISSION_ID))
    m.user_id = overrides.get("user_id", 1)
    m.title = overrides.get("title", "Test Mission")
    m.description = overrides.get("description", "desc")
    m.mission_type = overrides.get("mission_type", "general")
    m.status = overrides.get("status", "pending")
    m.priority = overrides.get("priority", "medium")
    m.plan = overrides.get("plan")
    m.results = overrides.get("results")
    m.error_message = overrides.get("error_message")
    m.tokens_used = overrides.get("tokens_used", 0)
    m.estimated_cost = overrides.get("estimated_cost", 0.0)
    m.actual_cost = overrides.get("actual_cost", 0.0)
    m.started_at = overrides.get("started_at")
    m.completed_at = overrides.get("completed_at")
    m.created_at = overrides.get("created_at", "2026-01-01T00:00:00")
    m.updated_at = overrides.get("updated_at", "2026-01-01T00:00:00")
    m.workspace_id = overrides.get("workspace_id")
    return m


def make_mission_task_orm(mission_id=MISSION_ID, **overrides):
    t = MagicMock()
    t.id = str(overrides.get("id", uuid.uuid4()))
    t.mission_id = str(mission_id)
    t.title = overrides.get("title", "Task 1")
    t.description = overrides.get("description", "")
    t.task_type = overrides.get("task_type", "llm")
    t.status = overrides.get("status", "pending")
    t.order_index = overrides.get("order_index", 0)
    t.input_data = overrides.get("input_data")
    t.output_data = overrides.get("output_data")
    t.error_message = overrides.get("error_message")
    t.tokens_used = overrides.get("tokens_used", 0)
    t.assigned_agent_id = overrides.get("assigned_agent_id")
    t.assigned_model = overrides.get("assigned_model")
    t.dependencies = overrides.get("dependencies", [])
    t.max_retries = overrides.get("max_retries", 3)
    t.created_at = "2026-01-01T00:00:00"
    t.updated_at = "2026-01-01T00:00:00"
    return t


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_user():
    return MagicMock(
        id=1,
        email="user@example.com",
        username="testuser",
        role="user",
        is_active=True,
        is_admin=False,
        is_superuser=False,
    )


@pytest.fixture
def cqrs_session():
    """Mock AsyncSession with commit/rollback tracking for CQRS handlers."""
    s = AsyncMock()
    s.execute = AsyncMock()
    s.execute.return_value = MagicMock()
    s.execute.return_value.first.return_value = None
    s.execute.return_value.scalar_one_or_none.return_value = None
    s.execute.return_value.scalar.return_value = 0
    s.execute.return_value.scalars.return_value.all.return_value = []
    s.commit = AsyncMock()
    s.rollback = AsyncMock()
    s.flush = AsyncMock()
    s.refresh = AsyncMock()
    s.add = MagicMock()
    s.close = AsyncMock()
    return s


@pytest.fixture
def cqrs_client(cqrs_session, mock_user):
    """TestClient with CQRS handler DI overrides — real handlers, mock session."""

    # Inject CQRS handlers that use the mock session
    def override_get_mission_queries():
        return MissionQueryHandlers(cqrs_session)

    def override_get_mission_commands():
        return MissionCommandHandlers(cqrs_session)

    async def override_get_current_user():
        return mock_user

    async def override_get_db_session():
        yield cqrs_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_mission_queries] = override_get_mission_queries
    app.dependency_overrides[get_mission_commands] = override_get_mission_commands
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_mission_queries, None)
    app.dependency_overrides.pop(get_mission_commands, None)
    app.dependency_overrides.pop(get_current_user, None)


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests — full DI pipeline
# ═══════════════════════════════════════════════════════════════════════════════


class TestCqrsListCreatePipeline:
    """GET /api/v2/missions + POST /api/v2/missions/ — full round-trip."""

    def test_list_missions_returns_paginated(self, cqrs_client, cqrs_session):
        """Query handler → list_missions → PaginatedMissions → v2 envelope."""
        mission = make_mission_orm()

        with patch(
            "app.api._mission_cqrs.queries.list_missions",
            new=AsyncMock(return_value=([mission], 1)),
        ):
            response = cqrs_client.get("/api/v2/missions/?page=1&per_page=20")

        assert response.status_code == 200
        data = response.json()
        assert data.get("error") is None
        assert "data" in data
        assert data["data"]["total"] == 1
        assert data["data"]["page"] == 1
        assert data["data"]["per_page"] == 20
        assert len(data["data"]["items"]) == 1
        assert data["data"]["items"][0]["title"] == "Test Mission"

    def test_create_mission_commits_and_returns_201(self, cqrs_client, cqrs_session):
        """Command handler → create_mission → wrap_command → commit → 201."""
        mission = make_mission_orm()

        with patch(
            "app.api._mission_cqrs.commands.create_mission",
            new=AsyncMock(return_value=mission),
        ):
            response = cqrs_client.post(
                "/api/v2/missions/",
                json={
                    "title": "New Mission",
                    "mission_type": "general",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data.get("error") is None
        assert data["data"]["title"] == "Test Mission"
        # wrap_command should have committed
        cqrs_session.commit.assert_awaited()

    def test_create_mission_rollback_on_db_error(self, cqrs_client, cqrs_session):
        """Service failure inside wrap_command → rollback → 400/500."""
        from sqlalchemy.exc import IntegrityError

        with patch(
            "app.api._mission_cqrs.commands.create_mission",
            new=AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("boom"))),
        ):
            response = cqrs_client.post(
                "/api/v2/missions/",
                json={
                    "title": "Will Fail",
                    "mission_type": "general",
                },
            )

        # IntegrityError → MissionValidationError → HTTP 422 in FastAPI
        # (or 400 depending on exception handler registration)
        assert response.status_code in (400, 422, 500)
        cqrs_session.rollback.assert_awaited()


class TestCqrsCrudPipeline:
    """GET/PATCH/DELETE /api/v2/missions/{id} — ownership checks in DI pipeline."""

    def test_get_mission_success(self, cqrs_client, cqrs_session):
        """Query handler → get_mission → ownership check passes → 200."""
        mission = make_mission_orm(user_id=1)

        with patch(
            "app.services.mission_service.get_mission",
            new=AsyncMock(return_value=mission),
        ):
            response = cqrs_client.get(f"/api/v2/missions/{MISSION_ID}")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["title"] == "Test Mission"

    def test_get_mission_not_found(self, cqrs_client, cqrs_session):
        """Query handler → get_mission → returns None → 404."""
        with patch(
            "app.services.mission_service.get_mission",
            new=AsyncMock(return_value=None),
        ):
            response = cqrs_client.get(f"/api/v2/missions/{MISSION_ID}")

        assert response.status_code == 404

    def test_get_mission_wrong_owner(self, cqrs_client, cqrs_session):
        """Query handler → get_mission → ownership mismatch → 404."""
        mission = make_mission_orm(user_id=999)  # different user

        with patch(
            "app.services.mission_service.get_mission",
            new=AsyncMock(return_value=mission),
        ):
            response = cqrs_client.get(f"/api/v2/missions/{MISSION_ID}")

        assert response.status_code == 404

    def test_update_mission_commits_on_success(self, cqrs_client, cqrs_session):
        """Command handler → update_mission → ownership check → commit → 200."""
        mission = make_mission_orm(user_id=1)
        updated = make_mission_orm(title="Updated Title")

        with patch(
            "app.services.mission_service.get_mission",
            return_value=mission,
        ), patch(
            "app.api._mission_cqrs.commands.update_mission",
            new=AsyncMock(return_value=updated),
        ):
            response = cqrs_client.patch(
                f"/api/v2/missions/{MISSION_ID}",
                json={
                    "title": "Updated Title",
                },
            )

        assert response.status_code == 200
        assert response.json()["data"]["title"] == "Updated Title"
        cqrs_session.commit.assert_awaited()

    def test_update_mission_wrong_owner(self, cqrs_client, cqrs_session):
        """Command handler → update_mission → ownership mismatch → 404."""
        mission = make_mission_orm(user_id=999)

        with patch(
            "app.services.mission_service.get_mission",
            return_value=mission,
        ):
            response = cqrs_client.patch(
                f"/api/v2/missions/{MISSION_ID}",
                json={
                    "title": "Should 404",
                },
            )

        assert response.status_code == 404

    def test_delete_mission_commits_on_success(self, cqrs_client, cqrs_session):
        """Command handler → delete_mission → ownership check → commit → 204."""
        mission = make_mission_orm(user_id=1)

        with patch(
            "app.services.mission_service.get_mission",
            return_value=mission,
        ), patch(
            "app.api._mission_cqrs.commands.delete_mission",
            new=AsyncMock(return_value=True),
        ):
            response = cqrs_client.delete(f"/api/v2/missions/{MISSION_ID}")

        assert response.status_code == 204
        cqrs_session.commit.assert_awaited()

    def test_delete_mission_wrong_owner(self, cqrs_client, cqrs_session):
        """Command handler → delete_mission → ownership mismatch → 404."""
        mission = make_mission_orm(user_id=999)

        with patch(
            "app.services.mission_service.get_mission",
            return_value=mission,
        ):
            response = cqrs_client.delete(f"/api/v2/missions/{MISSION_ID}")

        assert response.status_code == 404


class TestCqrsStatusTaskPipeline:
    """GET /api/v2/missions/{id}/status + /tasks — query handler chain."""

    def test_get_status_returns_expected_keys(self, cqrs_client, cqrs_session):
        """Query handler → get_mission → get_mission_tasks → MissionExecutionStatus."""
        mission = make_mission_orm(user_id=1, status="running")

        with patch(
            "app.services.mission_service.get_mission",
            new=AsyncMock(return_value=mission),
        ), patch(
            "app.api._mission_cqrs.queries.get_mission_tasks",
            new=AsyncMock(return_value=[]),
        ):
            response = cqrs_client.get(f"/api/v2/missions/{MISSION_ID}/status")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["mission_id"] == str(MISSION_ID)
        assert data["status"] == "running"
        assert "total_tasks" in data
        assert "completed_tasks" in data
        assert "failed_tasks" in data

    def test_list_tasks_returns_list(self, cqrs_client, cqrs_session):
        """Query handler → list_tasks → ownership check → list[MissionTask]."""
        mission = make_mission_orm(user_id=1)
        task = make_mission_task_orm()

        with patch(
            "app.services.mission_service.get_mission",
            new=AsyncMock(return_value=mission),
        ), patch(
            "app.api._mission_cqrs.queries.get_mission_tasks",
            new=AsyncMock(return_value=[task]),
        ):
            response = cqrs_client.get(f"/api/v2/missions/{MISSION_ID}/tasks")

        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Task 1"


class TestCqrsDiComposition:
    """Verify the DI composition — that get_mission_queries/get_mission_commands
    inject real handler instances with the session from get_db_session."""

    def test_query_handlers_receive_session(self, cqrs_client, cqrs_session):
        """FastAPI resolves Depends(get_mission_queries) through the override,
        and the handler receives the mock session."""
        # Hit an endpoint that uses MissionQueryHandlers — the override
        # injects MissionQueryHandlers(cqrs_session).
        mission = make_mission_orm(user_id=1)

        with patch(
            "app.services.mission_service.get_mission",
            new=AsyncMock(return_value=mission),
        ):
            response = cqrs_client.get(f"/api/v2/missions/{MISSION_ID}")

        assert response.status_code == 200
        # The handler's session should have been used for the query —
        # verify it was accessible (no AttributeError on the mock session)

    def test_command_handlers_receive_session(self, cqrs_client, cqrs_session):
        """FastAPI resolves Depends(get_mission_commands) through the override,
        and the handler's wrap_command calls commit on the mock session."""
        mission = make_mission_orm(user_id=1)

        with patch(
            "app.services.mission_service.get_mission",
            return_value=mission,
        ), patch(
            "app.api._mission_cqrs.commands.delete_mission",
            new=AsyncMock(return_value=True),
        ):
            response = cqrs_client.delete(f"/api/v2/missions/{MISSION_ID}")

        assert response.status_code == 204
        # wrap_command should have committed via the mock session
        cqrs_session.commit.assert_awaited_once()
