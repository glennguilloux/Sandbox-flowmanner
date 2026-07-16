"""Real-time subscription tenant-isolation tests (regression for Round-4 fix).

Covers the gap closed in `subscribe_mission` / `subscribe_graph`
(app/websocket/mission_ws.py): a Socket.IO client may only enter a
`mission_{id}` / `graph_exec_{id}` room when the authenticated user owns (or is
an active workspace member of) the backing entity. Anonymous sockets and
non-owners must be denied the room join (fail-closed) — previously the handler
entered the room from a client-supplied id with no auth and no ownership check,
leaking another tenant's mission status / graph progress.

Real-DB integration test: opens a fresh async session on the module-global
engine and commits seed rows. Skips when no live Postgres is reachable (same
convention as the other `test_ws_*.py` integration suites in this dir).

Run (from the backend dir of this worktree):
    DATABASE_URL='postgresql+asyncpg://flowmanner:...@localhost:5432/flowmanner' \\
        .venv/bin/python -m pytest app/tests/test_ws_subscription_tenant_isolation.py -v
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal, fresh_session
from app.models.graph import Workflow, WorkflowExecution
from app.models.mission_models import Mission, MissionStatus
from app.models.user import User
from app.models.workspace_models import Workspace, WorkspaceMember
from app.websocket import mission_ws

pytestmark = pytest.mark.integration

# Reuse the engine-rebinding loop fixture convention from this dir's conftest.


async def _db_reachable() -> bool:
    try:
        async with AsyncSessionLocal() as s:
            await s.execute(__import__("sqlalchemy").text("select 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
async def _guard(request):
    if not await _db_reachable():
        pytest.skip("no live Postgres reachable")
    return


def _uid() -> int:
    return 915_000_000 + (uuid.uuid4().int % 80_000_000)


class _Seed:
    """Handles to the rows seeded by ``_seed_owner_and_other``."""

    def __init__(self, owner_id, other_id, mission_id, execution_id, ws_id):
        self.owner_id = owner_id
        self.other_id = other_id
        self.mission_id = mission_id
        self.execution_id = execution_id
        self.ws_id = ws_id


async def _seed_owner_and_other() -> _Seed:
    """Create two users, a workspace, and an owner-only mission + graph exec."""
    owner_id, other_id = _uid(), _uid()
    ws_id = f"ws-{uuid.uuid4().hex}"
    mission_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())
    workflow_id = uuid.uuid4()
    async with fresh_session() as db:
        db.add(
            User(
                id=owner_id,
                email=f"owner-{owner_id}@example.com",
                hashed_password="x",
                is_active=True,
            )
        )
        db.add(
            User(
                id=other_id,
                email=f"other-{other_id}@example.com",
                hashed_password="x",
                is_active=True,
            )
        )
        ws = Workspace(id=ws_id, name="iso-ws", owner_user_id=owner_id)
        db.add(ws)
        db.add(WorkspaceMember(workspace_id=ws_id, user_id=owner_id, is_active=True))
        db.add(
            Mission(
                id=mission_id,
                user_id=owner_id,
                title="iso-mission",
                status=MissionStatus.PENDING,
                workspace_id=ws_id,
            )
        )
        db.add(
            Workflow(
                id=workflow_id,
                name="iso-wf",
                user_id=owner_id,
                workspace_id=ws_id,
            )
        )
        db.add(
            WorkflowExecution(
                id=execution_id,
                workflow_id=workflow_id,
                user_id=owner_id,
                workspace_id=ws_id,
                status="pending",
            )
        )
    return _Seed(
        owner_id=owner_id,
        other_id=other_id,
        mission_id=mission_id,
        execution_id=execution_id,
        ws_id=ws_id,
    )


def _make_client(token_user_id: int | None):
    """Build a Socket.IO AsyncClient carrying the auth token the server expects."""
    client = mission_ws.sio.AsyncClient(  # type: ignore[attr-defined]
        reconnection=False,
        auth={"token": f"fake-jwt-for-{token_user_id}"} if token_user_id is not None else {},
    )
    return client


# NOTE: the server's `connect` decodes a *real* JWT; to keep this integration
# test focused on the subscription gate (not JWT issuance), we monkeypatch the
# session so the connected sid is attributed to a chosen user_id. The ownership
# check underneath uses that attributed user_id, which is exactly what we assert.


async def test_anonymous_subscribe_mission_denied():
    seed = await _seed_owner_and_other()

    captured = {}

    async def fake_get_session(sid):
        captured["sid"] = sid
        return {}  # no user_id -> anonymous

    async def fake_enter_room(sid, room):
        captured.setdefault("rooms", []).append(room)

    orig_get = mission_ws.sio.get_session
    orig_enter = mission_ws.sio.enter_room
    mission_ws.sio.get_session = fake_get_session
    mission_ws.sio.enter_room = fake_enter_room
    try:
        await mission_ws.subscribe_mission("sid-anon", {"mission_id": seed.mission_id})
    finally:
        mission_ws.sio.get_session = orig_get
        mission_ws.sio.enter_room = orig_enter

    assert "rooms" not in captured, "anonymous socket must NOT enter a mission room"


async def test_non_owner_subscribe_mission_denied():
    seed = await _seed_owner_and_other()

    captured = {}

    async def fake_get_session(sid):
        return {"user_id": seed.other_id}  # authenticated but NOT the owner/member

    async def fake_enter_room(sid, room):
        captured.setdefault("rooms", []).append(room)

    orig_get = mission_ws.sio.get_session
    orig_enter = mission_ws.sio.enter_room
    mission_ws.sio.get_session = fake_get_session
    mission_ws.sio.enter_room = fake_enter_room
    try:
        await mission_ws.subscribe_mission("sid-other", {"mission_id": seed.mission_id})
    finally:
        mission_ws.sio.get_session = orig_get
        mission_ws.sio.enter_room = orig_enter

    assert "rooms" not in captured, "non-owner must NOT enter the owner's mission room"


async def test_owner_subscribe_mission_allowed():
    seed = await _seed_owner_and_other()

    captured = {}

    async def fake_get_session(sid):
        return {"user_id": seed.owner_id}

    async def fake_enter_room(sid, room):
        captured.setdefault("rooms", []).append(room)

    orig_get = mission_ws.sio.get_session
    orig_enter = mission_ws.sio.enter_room
    mission_ws.sio.get_session = fake_get_session
    mission_ws.sio.enter_room = fake_enter_room
    try:
        await mission_ws.subscribe_mission("sid-owner", {"mission_id": seed.mission_id})
    finally:
        mission_ws.sio.get_session = orig_get
        mission_ws.sio.enter_room = orig_enter

    assert captured.get("rooms") == [f"mission_{seed.mission_id}"], "owner must enter their mission room"


async def test_non_owner_subscribe_graph_denied():
    seed = await _seed_owner_and_other()

    captured = {}

    async def fake_get_session(sid):
        return {"user_id": seed.other_id}

    async def fake_enter_room(sid, room):
        captured.setdefault("rooms", []).append(room)

    orig_get = mission_ws.sio.get_session
    orig_enter = mission_ws.sio.enter_room
    mission_ws.sio.get_session = fake_get_session
    mission_ws.sio.enter_room = fake_enter_room
    try:
        await mission_ws.subscribe_graph("sid-other", {"execution_id": seed.execution_id})
    finally:
        mission_ws.sio.get_session = orig_get
        mission_ws.sio.enter_room = orig_enter

    assert "rooms" not in captured, "non-owner must NOT enter the owner's graph room"


async def test_owner_subscribe_graph_allowed():
    seed = await _seed_owner_and_other()

    captured = {}

    async def fake_get_session(sid):
        return {"user_id": seed.owner_id}

    async def fake_enter_room(sid, room):
        captured.setdefault("rooms", []).append(room)

    orig_get = mission_ws.sio.get_session
    orig_enter = mission_ws.sio.enter_room
    mission_ws.sio.get_session = fake_get_session
    mission_ws.sio.enter_room = fake_enter_room
    try:
        await mission_ws.subscribe_graph("sid-owner", {"execution_id": seed.execution_id})
    finally:
        mission_ws.sio.get_session = orig_get
        mission_ws.sio.enter_room = orig_enter

    assert captured.get("rooms") == [f"graph_exec_{seed.execution_id}"], "owner must enter their graph room"
