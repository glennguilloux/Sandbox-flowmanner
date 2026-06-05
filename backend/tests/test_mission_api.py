import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main_fastapi import app

pytestmark = pytest.mark.integration

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


MISSION_ID = "014da489-b7f5-44f7-9e89-046a05a5ab56"


def make_mission(status="pending"):
    return SimpleNamespace(
        id=UUID(MISSION_ID),
        user_id=1,
        title="Test",
        description="test",
        mission_type="general",
        status=status,
        priority="medium",
        plan=None,
        results=None,
        error_message=None,
        tokens_used=0,
        estimated_cost=0.0,
        actual_cost=0.0,
        started_at=None,
        completed_at=None,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


def make_user():
    return SimpleNamespace(
        id=1,
        email="user@example.com",
        username="sample-user",
        full_name="Sample User",
        hashed_password="hashed-password",
        avatar_url=None,
        is_active=True,
        is_admin=False,
        is_superuser=False,
        bio=None,
        api_key="sk-test",
        role="user",
    )


@pytest.fixture()
def mock_user():
    return make_user()


@pytest.fixture()
def mission_service_mocks():
    mission = make_mission()
    analytics = SimpleNamespace(
        total_missions=1,
        success_rate=0.0,
        avg_completion_time=None,
        total_tokens_used=0,
    )

    with patch("app.api._mission_handlers.get_mission", new=AsyncMock(return_value=mission)) as mock_get_mission, patch(
        "app.api._mission_handlers.get_mission_tasks", new=AsyncMock(return_value=[])
    ) as mock_get_mission_tasks, patch("app.api._mission_handlers.get_mission_logs", new=AsyncMock(return_value=[])) as mock_get_mission_logs, patch(
        "app.api._mission_handlers.get_mission_analytics", new=AsyncMock(return_value=analytics)
    ) as mock_get_mission_analytics, patch(
        "app.api._mission_handlers.get_mission_analytics_over_time", new=AsyncMock(return_value=[])
    ) as mock_get_mission_analytics_over_time, patch(
        "app.api._mission_handlers.get_token_usage_breakdown", new=AsyncMock(return_value=[])
    ) as mock_get_token_usage_breakdown, patch(
        "app.api._mission_handlers.get_failure_analysis", new=AsyncMock(return_value=[])
    ) as mock_get_failure_analysis, patch("app.api._mission_handlers.asyncio.sleep", new=AsyncMock(return_value=None)) as mock_sleep, patch(
        "app.api._mission_handlers.MissionExecutor"
    ) as mock_executor_cls, patch("app.api._mission_handlers.SelfImprovementEngine") as mock_engine_cls:
        executor = MagicMock()
        executor.plan_mission = AsyncMock(return_value={"success": True})
        executor.execute_mission = AsyncMock(return_value={"success": True})
        mock_executor_cls.return_value = executor

        engine = MagicMock()
        engine.get_improvements = AsyncMock(return_value=[])
        engine.generate_strategy = AsyncMock(return_value=SimpleNamespace())
        engine.apply_strategy = AsyncMock(return_value=SimpleNamespace())
        mock_engine_cls.return_value = engine

        yield SimpleNamespace(
            mission=mission,
            analytics=analytics,
            get_mission=mock_get_mission,
            get_mission_tasks=mock_get_mission_tasks,
            get_mission_logs=mock_get_mission_logs,
            get_mission_analytics=mock_get_mission_analytics,
            get_mission_analytics_over_time=mock_get_mission_analytics_over_time,
            get_token_usage_breakdown=mock_get_token_usage_breakdown,
            get_failure_analysis=mock_get_failure_analysis,
            sleep=mock_sleep,
            executor_cls=mock_executor_cls,
            executor=executor,
            engine_cls=mock_engine_cls,
            engine=engine,
        )


@pytest.fixture()
def auth_client(mock_db_session, mock_user, mission_service_mocks):
    async def override_get_db():
        yield mock_db_session

    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def unauth_client(mock_db_session):
    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.pop(get_db, None)


class TestMissionSchemaRepairEndpoints:
    def test_status_returns_expected_keys(self, auth_client):
        response = auth_client.get(f"/api/missions/{MISSION_ID}/status/")

        assert response.status_code == 200
        data = response.json()
        assert "mission_id" in data
        assert "status" in data

    def test_tasks_returns_list(self, auth_client):
        response = auth_client.get(f"/api/missions/{MISSION_ID}/tasks/")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_plan_returns_expected_keys(self, auth_client, mission_service_mocks):
        response = auth_client.post(f"/api/missions/{MISSION_ID}/plan")

        assert response.status_code == 200
        data = response.json()
        assert "mission_id" in data
        assert "status" in data

    def test_execute_returns_expected_keys(self, auth_client, mission_service_mocks):
        response = auth_client.post(f"/api/missions/{MISSION_ID}/execute")

        assert response.status_code == 200
        data = response.json()
        assert "mission_id" in data
        assert "status" in data

    def test_improvements_returns_list(self, auth_client):
        response = auth_client.get(f"/api/missions/{MISSION_ID}/improvements/")

        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestMissionSlashCompatibility:
    @pytest.mark.parametrize(
        "path_a,path_b",
        [
            (f"/api/missions/{MISSION_ID}", f"/api/missions/{MISSION_ID}/"),
            (f"/api/missions/{MISSION_ID}/tasks", f"/api/missions/{MISSION_ID}/tasks/"),
            (f"/api/missions/{MISSION_ID}/logs", f"/api/missions/{MISSION_ID}/logs/"),
            (f"/api/missions/{MISSION_ID}/status", f"/api/missions/{MISSION_ID}/status/"),
            (f"/api/missions/{MISSION_ID}/improvements", f"/api/missions/{MISSION_ID}/improvements/"),
            (f"/api/missions/{MISSION_ID}/analytics", f"/api/missions/{MISSION_ID}/analytics/"),
            (f"/api/missions/{MISSION_ID}/stream", f"/api/missions/{MISSION_ID}/stream/"),
        ],
    )
    def test_dual_routes_return_200(self, auth_client, mission_service_mocks, path_a, path_b):
        if "/stream" in path_a:
            mission_service_mocks.get_mission.side_effect = [
                make_mission("pending"),
                make_mission("completed"),
                make_mission("pending"),
                make_mission("completed"),
            ]

        response_a = auth_client.get(path_a)
        response_b = auth_client.get(path_b)

        assert response_a.status_code == 200
        assert response_b.status_code == 200


class TestMissionStreamContract:
    def test_stream_returns_sse_and_done(self, auth_client, mission_service_mocks):
        mission_service_mocks.get_mission.side_effect = [make_mission("pending"), make_mission("completed")]

        response = auth_client.get(f"/api/missions/{MISSION_ID}/stream")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.text
        assert body.startswith("data: ")
        assert "data: [DONE]" in body

    def test_stream_requires_auth(self, unauth_client):
        response = unauth_client.get(f"/api/missions/{MISSION_ID}/stream")

        assert response.status_code in (401, 403)
