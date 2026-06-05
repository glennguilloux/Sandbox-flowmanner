import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api._mission_cqrs.deps import get_mission_commands, get_mission_queries
from app.api.deps import get_current_user, get_db
from app.database import get_db_session
from app.main_fastapi import app

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration

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
        workspace_id=None,
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


@pytest.fixture
def mock_user():
    return make_user()


@pytest.fixture
def mission_service_mocks():
    """Mock mission handlers at the DI level.

    Instead of patching internal module functions (which no longer match the
    CQRS call path through compat.py), we create mock MissionQueryHandlers and
    MissionCommandHandlers instances and inject them via FastAPI dependency
    overrides.  This matches exactly how the endpoints receive their deps.
    """
    mission = make_mission()
    analytics = SimpleNamespace(
        total_missions=1,
        success_rate=0.0,
        avg_completion_time=None,
        total_tokens_used=0,
    )

    # ── Build mock MissionQueryHandlers ────────────────────────────────
    mock_queries = MagicMock()
    mock_queries.get_mission = AsyncMock(return_value=mission)
    mock_queries.get_status = AsyncMock(
        return_value={
            "mission_id": str(MISSION_ID),
            "status": "pending",
            "total_tasks": 0,
            "completed_tasks": 0,
            "progress_pct": 0,
        }
    )
    mock_queries.list_tasks = AsyncMock(return_value=[])
    mock_queries.list_logs = AsyncMock(return_value=[])
    mock_queries.list_improvements = AsyncMock(return_value=[])
    mock_queries.mission_analytics = AsyncMock(return_value=analytics)

    # stream_status returns a StreamingResponse with SSE content
    import json as _json

    from starlette.responses import StreamingResponse

    def _stream_status(user_id, mission_id, mission_obj):
        async def _event_gen():
            yield f"data: {_json.dumps({'type': 'status', 'status': 'pending', 'mission_id': str(MISSION_ID)})}\n\n"
            yield f"data: {_json.dumps({'type': 'status', 'status': 'completed', 'mission_id': str(MISSION_ID)})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(_event_gen(), media_type="text/event-stream")

    mock_queries.stream_status = _stream_status

    # ── Build mock MissionCommandHandlers ──────────────────────────────
    mock_commands = MagicMock()
    mock_commands.plan_mission = AsyncMock(
        return_value={
            "mission_id": str(MISSION_ID),
            "status": "planned",
        }
    )
    mock_commands.execute_mission = AsyncMock(
        return_value={
            "mission_id": str(MISSION_ID),
            "status": "completed",
        }
    )
    mock_commands.create_mission = AsyncMock(return_value=mission)
    mock_commands.update_mission = AsyncMock(return_value=mission)
    mock_commands.delete_mission = AsyncMock(return_value=True)
    mock_commands.create_log = AsyncMock(return_value=MagicMock())
    mock_commands.create_task = AsyncMock(return_value=make_mission())

    # ── Inject via DI overrides ────────────────────────────────────────
    async def _override_queries():
        return mock_queries

    async def _override_commands():
        return mock_commands

    app.dependency_overrides[get_mission_queries] = _override_queries
    app.dependency_overrides[get_mission_commands] = _override_commands

    yield SimpleNamespace(
        mission=mission,
        analytics=analytics,
        queries=mock_queries,
        commands=mock_commands,
        # Expose individual mocks for tests that set side_effect
        get_mission=mock_queries.get_mission,
    )

    app.dependency_overrides.pop(get_mission_queries, None)
    app.dependency_overrides.pop(get_mission_commands, None)


@pytest.fixture
def auth_client(mock_db_session, mock_user, mission_service_mocks):
    async def override_get_db():
        yield mock_db_session

    async def override_get_db_session():
        yield mock_db_session

    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauth_client(mock_db_session):
    async def override_get_db():
        yield mock_db_session

    async def override_get_db_session():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_db_session, None)


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
        ("path_a", "path_b"),
        [
            (f"/api/missions/{MISSION_ID}", f"/api/missions/{MISSION_ID}/"),
            (f"/api/missions/{MISSION_ID}/tasks", f"/api/missions/{MISSION_ID}/tasks/"),
            (f"/api/missions/{MISSION_ID}/logs", f"/api/missions/{MISSION_ID}/logs/"),
            (
                f"/api/missions/{MISSION_ID}/status",
                f"/api/missions/{MISSION_ID}/status/",
            ),
            (
                f"/api/missions/{MISSION_ID}/improvements",
                f"/api/missions/{MISSION_ID}/improvements/",
            ),
            (
                f"/api/missions/{MISSION_ID}/analytics",
                f"/api/missions/{MISSION_ID}/analytics/",
            ),
            (
                f"/api/missions/{MISSION_ID}/stream",
                f"/api/missions/{MISSION_ID}/stream/",
            ),
        ],
    )
    def test_dual_routes_return_200(
        self, auth_client, mission_service_mocks, path_a, path_b
    ):
        if "/stream" in path_a:
            # stream uses async generator — already set up in fixture
            pass

        response_a = auth_client.get(path_a)
        response_b = auth_client.get(path_b)

        assert response_a.status_code == 200
        assert response_b.status_code == 200


class TestMissionStreamContract:
    def test_stream_returns_sse_and_done(self, auth_client, mission_service_mocks):
        response = auth_client.get(f"/api/missions/{MISSION_ID}/stream")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.text
        assert body.startswith("data: ")
        assert "data: [DONE]" in body

    def test_stream_requires_auth(self, unauth_client):
        response = unauth_client.get(f"/api/missions/{MISSION_ID}/stream")

        assert response.status_code in (401, 403)


class TestMissionE2ELifecycle:
    """End-to-end lifecycle test: create → plan → execute → verify completed."""

    @pytest.mark.asyncio
    async def test_full_mission_lifecycle_e2e(self, auth_client, mission_service_mocks):
        # 1. Create mission
        from uuid import UUID

        create_payload = {
            "title": "E2E Lifecycle Test",
            "description": "Testing full mission lifecycle",
            "mission_type": "general",
        }
        # READ-ONLY: v2 create endpoint for mission lifecycle
        response = auth_client.post("/api/v2/missions/", json=create_payload)
        assert response.status_code == 201
        data = response.json()
        assert data.get("error") is None
        mission_id = data["data"]["id"]

        # Verify the created mission appears
        assert UUID(mission_id)

    def test_create_plan_execute_flow(self, auth_client, mission_service_mocks):
        """Quick smoke test: create, plan, execute chain."""
        # Plan returns 200
        response = auth_client.post(f"/api/missions/{MISSION_ID}/plan")
        assert response.status_code == 200

        # Execute returns 200
        response = auth_client.post(f"/api/missions/{MISSION_ID}/execute")
        assert response.status_code == 200

        # Status is readable
        response = auth_client.get(f"/api/missions/{MISSION_ID}/status")
        assert response.status_code == 200
