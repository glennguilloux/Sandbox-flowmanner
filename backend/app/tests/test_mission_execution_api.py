import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.deps import get_current_user
from app.main_fastapi import app

os.environ.setdefault("OPENAI_API_KEY", "***")

pytestmark = pytest.mark.integration

MISSION_ID = uuid4()
INVALID_MISSION_ID = uuid4()


def make_mission(status="pending"):
    mission = MagicMock()
    mission.id = MISSION_ID
    mission.user_id = 1
    mission.workspace_id = None
    mission.title = "Test Mission"
    mission.description = "Test mission for execution"
    mission.mission_type = "general"
    mission.status = status
    mission.priority = "medium"
    mission.tokens_used = 0
    mission.estimated_cost = 0.0
    mission.actual_cost = 0.0
    mission.budget_usd = 10.0
    mission.budget_seconds = 300
    mission.started_at = None
    mission.completed_at = None
    mission.created_at = None
    mission.updated_at = None
    return mission


def make_user():
    user = MagicMock()
    user.id = 1
    user.email = "executor@example.com"
    user.username = "executor"
    user.is_active = True
    user.role = "user"
    return user


def test_execute_mission_success(test_client):
    """POST /api/missions/{id}/execute returns 200 with status."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        mock_mission = make_mission()
        mock_tasks = []

        # Mock the unified executor used by the handler (Phase 8.1 GA)
        mock_unified = MagicMock()
        mock_unified.execute = AsyncMock(
            return_value=MagicMock(
                success=True,
                status="completed",
                completed_nodes=[],
                failed_nodes=[],
                data={},
                error=None,
                total_tokens=0,
                total_cost_usd=0.0,
            )
        )

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new_callable=AsyncMock,
                return_value=mock_mission,
            ),
            patch(
                "app.services.subscription_service.check_mission_execute_allowed",
                return_value=MagicMock(allowed=True),
            ),
            patch(
                "app.services.substrate.executor.get_unified_executor",
                return_value=mock_unified,
            ),
            patch(
                "app.services.mission_service.get_mission_tasks",
                return_value=mock_tasks,
            ),
        ):
            response = test_client.post(f"/api/missions/{MISSION_ID}/execute")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == mock_mission.status
            assert data["mission_id"] == str(MISSION_ID)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_execute_mission_not_found(test_client):
    """POST /api/missions/{id}/execute returns 404 for non-existent mission."""
    from app.services.mission_errors import MissionNotFoundError

    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            new_callable=AsyncMock,
            side_effect=MissionNotFoundError("Mission not found"),
        ):
            response = test_client.post(f"/api/missions/{INVALID_MISSION_ID}/execute")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_get_mission_status_success(test_client):
    """GET /api/missions/{id}/status returns 200 with status."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        mock_mission = make_mission(status="completed")
        mock_tasks = [MagicMock(status="completed"), MagicMock(status="completed")]
        with (
            patch(
                "app.services.mission_service.get_mission", return_value=mock_mission
            ),
            patch(
                "app.services.mission_service.get_mission_tasks",
                return_value=mock_tasks,
            ),
        ):
            response = test_client.get(f"/api/missions/{MISSION_ID}/status")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert data["mission_id"] == str(MISSION_ID)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_execute_async_mission(test_client):
    """POST /api/missions/{id}/execute-async returns 200 with queued status."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        mock_mission = make_mission()
        mock_tasks = []
        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new_callable=AsyncMock,
                return_value=mock_mission,
            ),
            patch(
                "app.services.subscription_service.check_mission_execute_allowed",
                return_value=MagicMock(allowed=True),
            ),
            patch(
                "app.services.mission_service.get_mission_tasks",
                return_value=mock_tasks,
            ),
        ):
            response = test_client.post(f"/api/missions/{MISSION_ID}/execute-async")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            assert data["mission_id"] == str(MISSION_ID)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
