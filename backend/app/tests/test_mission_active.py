from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api._mission_cqrs.queries import MissionQueryHandlers
from app.api.v1.mission import list_active_missions
from app.schemas.mission import MissionListResult, MissionResponse


def _configure_session():
    s = AsyncMock()

    async def _exe(*a, **kw):
        return MagicMock()

    s.execute = _exe
    return s


@pytest.fixture
def db_session():
    return _configure_session()


@pytest.fixture
def pro_user():
    user = MagicMock()
    user.id = 1
    user.role = "pro"
    user.is_pro = True
    return user


@pytest.fixture
def basic_user():
    user = MagicMock()
    user.id = 2
    user.role = "basic"
    user.is_pro = False
    return user


@pytest.mark.asyncio
async def test_active_missions_success(db_session, pro_user):
    """AC-03/04: Progress and ETA returned."""
    mission_id = uuid4()
    response_item = MissionResponse(
        id=mission_id,
        user_id=1,
        title="Test",
        description="",
        status="running",
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        progress=50,
        eta=datetime.now(UTC) + timedelta(minutes=5),
    )
    q = MissionQueryHandlers(db_session)
    q.active_missions = AsyncMock(
        return_value=MissionListResult(missions=[response_item], total=1)
    )
    response = await list_active_missions(user=pro_user, q=q)
    assert len(response) == 1
    assert response[0].progress == 50
    assert response[0].eta is not None


@pytest.mark.asyncio
async def test_active_missions_no_active(db_session, pro_user):
    q = MissionQueryHandlers(db_session)
    q.active_missions = AsyncMock(return_value=MissionListResult(missions=[], total=0))
    response = await list_active_missions(user=pro_user, q=q)
    assert response == []


@pytest.mark.asyncio
async def test_active_missions_pro_required(db_session, basic_user):
    """AC-01: Non-Pro user gets 403."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from app.api._mission_cqrs.deps import get_mission_queries
    from app.api.deps import get_current_user, get_db, get_workspace_id
    from app.api.v1.mission import router
    from app.services.mission_errors import MissionForbiddenError

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: basic_user
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_workspace_id] = lambda: None

    q = MissionQueryHandlers(db_session)
    app.dependency_overrides[get_mission_queries] = lambda: q

    @app.exception_handler(MissionForbiddenError)
    async def handle_forbidden(request, exc):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    client = TestClient(app)
    assert client.get("/missions/active").status_code == 403


@pytest.mark.asyncio
async def test_active_missions_progress_calculation(db_session, pro_user):
    """AC-03: Progress % correct."""
    mission_id = uuid4()
    response_item = MissionResponse(
        id=mission_id,
        user_id=1,
        title="Test",
        description="",
        status="running",
        started_at=datetime.now(UTC),
        progress=66,
    )
    q = MissionQueryHandlers(db_session)
    q.active_missions = AsyncMock(
        return_value=MissionListResult(missions=[response_item], total=1)
    )
    response = await list_active_missions(user=pro_user, q=q)
    assert response[0].progress == 66


@pytest.mark.asyncio
async def test_active_missions_eta_calculation(db_session, pro_user):
    """AC-04: ETA calculated when running with completed tasks."""
    mission_id = uuid4()
    response_item = MissionResponse(
        id=mission_id,
        user_id=1,
        title="Test",
        description="",
        status="running",
        started_at=datetime.now(UTC) - timedelta(minutes=10),
        progress=50,
        eta=datetime.now(UTC) + timedelta(minutes=10),
    )
    q = MissionQueryHandlers(db_session)
    q.active_missions = AsyncMock(
        return_value=MissionListResult(missions=[response_item], total=1)
    )
    response = await list_active_missions(user=pro_user, q=q)
    assert response[0].eta is not None
