"""Backend tests for the v2 Notifications router + mission-completion emission.

HERMETIC: spins up a unique throwaway Postgres DB per test (mirrors
``test_decay_memory.py``). Never touches the live ``flowmanner`` DB.

Covers:
  * v2 envelope shape for list / unread-count / mark-read / read-all
  * owner isolation (user A cannot read/mark user B's notification -> 404)
  * mission-completion emission contract (send_notification creates exactly one
    Notification row for the owner with type {mission_completed} and
    entity_id == mission_id) -- this is the exact call the inline code at
    ``trigger_service.py:269`` makes.

Run from the backend dir:
    cd /opt/flowmanner/backend && PYTHONPATH=. .venv/bin/python -m pytest \\
        app/tests/test_v2_notifications.py -q
"""

from __future__ import annotations

import os
import sys
import urllib.parse
import uuid
from pathlib import Path

# Make ``app`` importable from the worktree's backend dir.
os.environ.setdefault("OPENAI_API_KEY", "test-notifications")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Resolve a host-reachable Postgres URL BEFORE importing app modules.
# settings.DATABASE_URL uses the compose service name ``postgres`` which does
# not resolve on the host; the homelab Postgres is reachable at 127.0.0.1:5432
# with the same credentials. Mirror the repo's integration-test convention:
# replace the ``@postgres:`` / ``@localhost:`` host with ``@127.0.0.1:``.
from app.config import settings as _settings  # noqa: E402

_DB_URL = os.getenv("FLOWMANNER_NOTIF_TEST_DB_BASE") or _settings.DATABASE_URL
_DB_URL = _DB_URL.replace("@postgres:", "@127.0.0.1:").replace("@localhost:", "@127.0.0.1:")
os.environ["DATABASE_URL"] = _DB_URL  # keep the global engine aligned too


def _build_db_urls():
    """Return (admin_url, test_base_url) using urllib.parse (handles ``://``)."""
    p = urllib.parse.urlparse(_DB_URL)
    netloc = p.username or ""
    if p.password:
        netloc += ":" + p.password
    netloc += "@127.0.0.1:" + str(p.port or 5432)
    base = f"{p.scheme}://{netloc}"
    return base + "/postgres", base


import pytest  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.api.deps import get_current_user  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main_fastapi import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.mission_models import Mission, MissionStatus  # noqa: E402
from app.models.notification_models import Notification  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.notification_service import send_notification  # noqa: E402


@pytest.fixture
async def db_session():
    """Create a unique throwaway Postgres DB + session per test (hermetic)."""
    admin_url, test_base = _build_db_urls()
    db_name = f"notif_{uuid.uuid4().hex[:12]}"
    test_url = test_base + "/" + db_name

    admin = create_async_engine(admin_url, future=True)
    async with admin.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    await admin.dispose()

    eng = create_async_engine(test_url, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(bind=eng, expire_on_commit=False)
    session = Session()
    yield session
    await session.close()
    await eng.dispose()

    admin = create_async_engine(admin_url, future=True)
    async with admin.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f'DROP DATABASE "{db_name}" WITH (FORCE)'))
    await admin.dispose()


def _mk_user(session, user_id: int, email: str) -> User:
    u = User(email=email, hashed_password="x", role="user")
    session.add(u)
    return u


def _mk_notification(session, user_id: int, ntype: str = "info", is_read: bool = False) -> Notification:
    n = Notification(
        user_id=user_id,
        title=f"t-{user_id}-{ntype}",
        message="hello",
        notification_type=ntype,
        severity="info",
        is_read=is_read,
        entity_type="mission",
        entity_id=str(uuid.uuid4()),
    )
    session.add(n)
    return n


@pytest.fixture
def authed_client(db_session):
    """AsyncClient with get_db + get_current_user overridden deterministically.

    The active user id is set in the ``state`` dict; tests that need a different
    acting user mutate ``client._state['user_id']`` before the request.
    """
    state = {"user_id": 1}

    async def _override_db():
        yield db_session

    def _override_user():
        class _U:
            id = state["user_id"]

        return _U()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client._state = state  # type: ignore[attr-defined]
    yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_paginated_envelope(db_session, authed_client):
    u1 = _mk_user(db_session, 1, "a@example.com")
    await db_session.flush()
    for _ in range(3):
        _mk_notification(db_session, u1.id, ntype="mission_completed")
    await db_session.commit()

    r = await authed_client.get("/api/v2/notifications")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["error"] is None
    assert "request_id" in body["meta"]
    data = body["data"]
    assert data["total"] == 3
    assert data["pages"] == 1
    assert len(data["items"]) == 3
    # Frontend-expected fields present
    assert data["items"][0]["type"] == "mission_completed"
    assert data["items"][0]["notification_type"] == "mission_completed"


@pytest.mark.asyncio
async def test_unread_count_envelope(db_session, authed_client):
    u1 = _mk_user(db_session, 1, "a@example.com")
    await db_session.flush()
    _mk_notification(db_session, u1.id, is_read=False)
    _mk_notification(db_session, u1.id, is_read=True)
    await db_session.commit()

    r = await authed_client.get("/api/v2/notifications/unread-count")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["error"] is None
    assert body["data"]["unread_count"] == 1


@pytest.mark.asyncio
async def test_mark_read_envelope_and_not_found(db_session, authed_client):
    u1 = _mk_user(db_session, 1, "a@example.com")
    await db_session.flush()
    n = _mk_notification(db_session, u1.id, is_read=False)
    await db_session.commit()
    nid = n.id

    r = await authed_client.post(f"/api/v2/notifications/{nid}/read")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["error"] is None
    assert body["data"]["is_read"] is True

    # Missing id -> 404 envelope (err("NOT_FOUND", 404))
    r2 = await authed_client.post("/api/v2/notifications/999999/read")
    # The v2 envelope returns err("NOT_FOUND") with HTTP 200 + error.code.
    assert r2.status_code == 200, r2.text
    assert r2.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_read_all_envelope(db_session, authed_client):
    u1 = _mk_user(db_session, 1, "a@example.com")
    await db_session.flush()
    _mk_notification(db_session, u1.id, is_read=False)
    _mk_notification(db_session, u1.id, is_read=False)
    await db_session.commit()

    r = await authed_client.post("/api/v2/notifications/read-all")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["error"] is None
    assert body["data"]["updated"] == 2

    # Confirm via unread-count
    r2 = await authed_client.get("/api/v2/notifications/unread-count")
    assert r2.json()["data"]["unread_count"] == 0


@pytest.mark.asyncio
async def test_owner_isolation(db_session, authed_client):
    _mk_user(db_session, 1, "a@example.com")
    _mk_user(db_session, 2, "b@example.com")
    await db_session.flush()
    n = _mk_notification(db_session, 2, is_read=False)  # owned by user 2
    await db_session.commit()
    nid = n.id

    # Default acting user is 1 -> must NOT see user 2's notification.
    r = await authed_client.post(f"/api/v2/notifications/{nid}/read")
    # v2 envelope: owner check returns err("NOT_FOUND") (HTTP 200 + error.code).
    assert r.status_code == 200, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"

    # List must not include user 2's notification for user 1
    r2 = await authed_client.get("/api/v2/notifications")
    assert r2.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_type_filter_and_pagination_query(db_session, authed_client):
    u1 = _mk_user(db_session, 1, "a@example.com")
    await db_session.flush()
    _mk_notification(db_session, u1.id, ntype="mission_completed")
    _mk_notification(db_session, u1.id, ntype="system_alert")
    await db_session.commit()

    r = await authed_client.get("/api/v2/notifications?type=mission_completed")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["total"] == 1
    assert r.json()["data"]["items"][0]["type"] == "mission_completed"


@pytest.mark.asyncio
async def test_emission_on_mission_completion(db_session):
    """Mirror the exact send_notification call made at trigger_service.py:269.

    Validates the emission contract: exactly one Notification row for the owner
    with notification_type == 'mission_completed' and entity_id == mission_id.

    ``send_notification`` also publishes to Redis SSE; Redis is not reachable in
    the hermetic host env, so we stub the publish (the production emission sites
    already wrap send_notification in try/except and never raise on it).
    """
    import app.services.notification_service as _ns

    async def _fake_publish(*args, **kwargs):
        return None

    _orig = _ns.publish_user_notification
    _ns.publish_user_notification = _fake_publish
    try:
        owner = _mk_user(db_session, 42, "owner@example.com")
        await db_session.flush()
        owner_id = owner.id
        mission = Mission(
            id=uuid.uuid4(),
            user_id=owner_id,
            title="Emission test mission",
            status=MissionStatus.COMPLETED,
        )
        db_session.add(mission)
        await db_session.commit()

        mission_id = str(mission.id)
        await send_notification(
            user_id=owner_id,
            notification_type="mission_completed",
            data={
                "title": f"Mission completed: {mission.title}",
                "message": mission.title,
                "mission_id": mission_id,
                "entity_type": "mission",
                "entity_id": mission_id,
                "dashboard_url": f"/missions/{mission_id}",
            },
            db=db_session,
        )
    finally:
        _ns.publish_user_notification = _orig

    rows = (
        await db_session.execute(
            select(Notification).where(
                Notification.user_id == owner_id,
                Notification.notification_type == "mission_completed",
            )
        )
    ).scalars().all()
    assert len(rows) == 1, f"expected exactly one mission_completed notification, got {len(rows)}"
    assert rows[0].entity_id == mission_id
    assert rows[0].entity_type == "mission"
    assert rows[0].is_read is False
