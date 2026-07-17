"""Tenancy backstop regression test — non-member MUST NOT read another workspace's rows.

Real PostgreSQL integration test (``_pg`` convention → auto-skipped when the
DB is unreachable). Companion to ``docs/adr/ADR-003-tenancy-backstop.md``
and ``app/services/workspace_tenancy.py``.

This card implements ONLY the design + safe slice:
  * It does NOT migrate any endpoint (no call-site edits).
  * It does NOT run a schema migration.
  * It pins the *required* behaviour so a future rollout cannot silently
    regress: a caller who is NOT a member of an entity's workspace must get
    a 404 / denial, never the row.

Coverage:
  * Mission.get_by_id       -> require_mission_access denies non-member (404)
  * ChatThread.get_by_id    -> require_chat_thread_access denies non-member (404)
  * MemoryEntry             -> verify_entity_tenancy (the new backstop helper)
                               denies a non-member and allows an active member.
                               (No service-level require_* exists for MemoryEntry
                               yet — see ADR phase 2; this pins the helper that
                               the future guard will route through.)

Run (containerized, DB reachable):
    docker compose exec backend pytest /app/tests/test_tenancy_backstop_pg.py -v
Run (homelab, DB at workflow-postgres):
    pytest backend/tests/test_tenancy_backstop_pg.py -v
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

try:
    from app.config import settings
    from app.models.chat import ChatThread
    from app.models.memory_models import MemoryEntry
    from app.models.mission_models import Mission
    from app.models.user import User
    from app.models.workspace_models import Workspace, WorkspaceMember
    from app.services.mission_errors import MissionNotFoundError
    from app.services.mission_service import require_mission_access
    from app.services.workspace_tenancy import TenancyError, verify_entity_tenancy
    from app.services.chat_service import require_chat_thread_access

    _DB_AVAILABLE = True
except Exception as e:  # pragma: no cover
    _DB_AVAILABLE = False
    _DB_IMPORT_ERROR = str(e)


# ── Session-scoped event loop (matches other _pg tests) ────────────
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Build a session factory pointed at a reachable backend DB ──────
def _make_session_factory():
    """Return an async_sessionmaker for the backend DB.

    The .env DATABASE_URL points at ``postgres:5432`` (resolves inside the
    Docker stack). On the homelab the same DB is reachable at
    ``workflow-postgres:5432``, so we transparently rewrite the host when
    that host resolves. This keeps the test runnable in both environments
    without changing app config.
    """
    import socket

    url = settings.DATABASE_URL
    if socket.gethostbyname("workflow-postgres") and "postgres" in url:
        url = url.replace("@postgres:", "@workflow-postgres:")
    engine = create_async_engine(url, pool_pre_ping=True)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


pytestmark = [
    pytest.mark.skipif(
        not _DB_AVAILABLE,
        reason=f"Database not available: {_DB_IMPORT_ERROR if not _DB_AVAILABLE else ''}",
    ),
    pytest.mark.integration,
    pytest.mark.requires_postgres,
]


# ═══════════════════════════════════════════════════════════════════
# Fixture: an isolated 2-user / 2-workspace sandbox
# ═══════════════════════════════════════════════════════════════════
@pytest.fixture
async def sandbox():
    """Create two users, two workspaces (member-only on ws A), and tear down.

    user_a  -> member of ws_a (owns the entities)
    user_b  -> member of ws_b ONLY (must be denied ws_a's rows)
    user_c  -> member of NEITHER (control: must be denied everything)
    """
    SessionLocal = _make_session_factory()
    async with SessionLocal() as db:
        suffix = uuid4().hex[:8]
        user_a = User(
            email=f"a-{suffix}@example.com",
            username=f"a-{suffix}",
            hashed_password="x",
            role="user",
            is_active=True,
        )
        user_b = User(
            email=f"b-{suffix}@example.com",
            username=f"b-{suffix}",
            hashed_password="x",
            role="user",
            is_active=True,
        )
        user_c = User(
            email=f"c-{suffix}@example.com",
            username=f"c-{suffix}",
            hashed_password="x",
            role="user",
            is_active=True,
        )
        db.add_all([user_a, user_b, user_c])
        await db.flush()

        ws_a = Workspace(id=str(uuid4()), name=f"ws-a-{suffix}", slug=f"ws-a-{suffix}", owner_id=user_a.id, is_active=True)
        ws_b = Workspace(id=str(uuid4()), name=f"ws-b-{suffix}", slug=f"ws-b-{suffix}", owner_id=user_b.id, is_active=True)
        db.add_all([ws_a, ws_b])
        await db.flush()

        db.add(WorkspaceMember(workspace_id=ws_a.id, user_id=user_a.id, role="owner", is_active=True))
        db.add(WorkspaceMember(workspace_id=ws_b.id, user_id=user_b.id, role="owner", is_active=True))
        await db.commit()

    yield {
        "user_a_id": user_a.id,
        "user_b_id": user_b.id,
        "user_c_id": user_c.id,
        "ws_a_id": ws_a.id,
        "ws_b_id": ws_b.id,
        "SessionLocal": SessionLocal,
    }

    # ── Teardown ──
    async with SessionLocal() as db:
        await db.execute(delete(WorkspaceMember).where(WorkspaceMember.workspace_id.in_([ws_a.id, ws_b.id])))
        await db.execute(delete(Mission).where(Mission.workspace_id.in_([ws_a.id, ws_b.id])))
        await db.execute(delete(ChatThread).where(ChatThread.workspace_id.in_([ws_a.id, ws_b.id])))
        await db.execute(delete(MemoryEntry).where(MemoryEntry.workspace_id.in_([ws_a.id, ws_b.id])))
        await db.execute(delete(Workspace).where(Workspace.id.in_([ws_a.id, ws_b.id])))
        await db.execute(delete(User).where(User.id.in_([user_a.id, user_b.id, user_c.id])))
        await db.commit()
    await SessionLocal().bind.dispose()


# ═══════════════════════════════════════════════════════════════════
# Mission — GET-by-id must 404 for a non-member workspace
# ═══════════════════════════════════════════════════════════════════
class TestMissionTenancyBackstop:
    @pytest.mark.asyncio
    async def test_non_member_gets_404(self, sandbox):
        """A user with no membership in ws_a must be denied the mission (404)."""
        db = sandbox["SessionLocal"]()
        try:
            mission = Mission(
                title="secret-mission",
                user_id=sandbox["user_a_id"],
                workspace_id=sandbox["ws_a_id"],
                status="pending",
            )
            db.add(mission)
            await db.commit()
            await db.refresh(mission)
            mid = mission.id

            # user_b is only in ws_b -> must be denied (MissionNotFoundError == 404)
            with pytest.raises(MissionNotFoundError):
                await require_mission_access(db, mid, user_id=sandbox["user_b_id"])

            # user_c is in no workspace -> must be denied
            with pytest.raises(MissionNotFoundError):
                await require_mission_access(db, mid, user_id=sandbox["user_c_id"])
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_member_can_read(self, sandbox):
        """The workspace owner (active member) can read their own mission."""
        db = sandbox["SessionLocal"]()
        try:
            mission = Mission(
                title="mine-mission",
                user_id=sandbox["user_a_id"],
                workspace_id=sandbox["ws_a_id"],
                status="pending",
            )
            db.add(mission)
            await db.commit()
            await db.refresh(mission)

            result = await require_mission_access(db, mission.id, user_id=sandbox["user_a_id"])
            assert result.id == mission.id
        finally:
            await db.close()


# ═══════════════════════════════════════════════════════════════════
# ChatThread — GET-by-id must 404 for a non-member workspace
# ═══════════════════════════════════════════════════════════════════
class TestChatThreadTenancyBackstop:
    @pytest.mark.asyncio
    async def test_non_member_gets_404(self, sandbox):
        """A non-member workspace user must be denied the thread (HTTPException 404)."""
        db = sandbox["SessionLocal"]()
        try:
            thread = ChatThread(
                user_id=sandbox["user_a_id"],
                username="a",
                title="secret-thread",
                workspace_id=sandbox["ws_a_id"],
            )
            db.add(thread)
            await db.commit()
            await db.refresh(thread)
            tid = thread.id

            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc:
                await require_chat_thread_access(db, tid, user_id=sandbox["user_b_id"])
            assert exc.value.status_code == 404

            with pytest.raises(HTTPException) as exc2:
                await require_chat_thread_access(db, tid, user_id=sandbox["user_c_id"])
            assert exc2.value.status_code == 404
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_member_can_read(self, sandbox):
        db = sandbox["SessionLocal"]()
        try:
            thread = ChatThread(
                user_id=sandbox["user_a_id"],
                username="a",
                title="mine-thread",
                workspace_id=sandbox["ws_a_id"],
            )
            db.add(thread)
            await db.commit()
            await db.refresh(thread)

            result = await require_chat_thread_access(db, thread.id, user_id=sandbox["user_a_id"])
            assert result.id == thread.id
        finally:
            await db.close()


# ═══════════════════════════════════════════════════════════════════
# MemoryEntry — the new backstop helper (verify_entity_tenancy)
# ═══════════════════════════════════════════════════════════════════
class TestMemoryEntryTenancyBackstop:
    """MemoryEntry has no service-level require_* guard yet (ADR phase 2 gap).

    This pins the NEW backstop helper that the future guard must route
    through, so the helper itself is regression-covered before any
    call-site migration.
    """

    @pytest.mark.asyncio
    async def test_non_member_denied_by_helper(self, sandbox):
        db = sandbox["SessionLocal"]()
        try:
            entry = MemoryEntry(
                workspace_id=sandbox["ws_a_id"],
                user_id=sandbox["user_a_id"],
                namespace="agent",
                content="secret memory",
                memory_type="semantic",
                importance=0.9,
            )
            db.add(entry)
            await db.commit()
            await db.refresh(entry)

            # Non-member (ws_b only) -> TenancyError (fail-closed)
            with pytest.raises(TenancyError):
                await verify_entity_tenancy(
                    db,
                    entity_type="memory",
                    entity_id=entry.id,
                    workspace_id=entry.workspace_id,
                    user_id=sandbox["user_b_id"],
                )

            # No-workspace user -> also denied
            with pytest.raises(TenancyError):
                await verify_entity_tenancy(
                    db,
                    entity_type="memory",
                    entity_id=entry.id,
                    workspace_id=entry.workspace_id,
                    user_id=sandbox["user_c_id"],
                )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_member_allowed_by_helper(self, sandbox):
        db = sandbox["SessionLocal"]()
        try:
            entry = MemoryEntry(
                workspace_id=sandbox["ws_a_id"],
                user_id=sandbox["user_a_id"],
                namespace="agent",
                content="my memory",
                memory_type="semantic",
                importance=0.9,
            )
            db.add(entry)
            await db.commit()
            await db.refresh(entry)

            allowed = await verify_entity_tenancy(
                db,
                entity_type="memory",
                entity_id=entry.id,
                workspace_id=entry.workspace_id,
                user_id=sandbox["user_a_id"],
            )
            assert allowed is True
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_null_workspace_fails_closed_without_fallback(self, sandbox):
        """Legacy NULL workspace_id rows are DENIED by default (fail-closed).

        The insecure user-ownership fallback must be an explicit opt-in, not
        the implicit default — this is the core backstop guarantee.
        """
        db = sandbox["SessionLocal"]()
        try:
            entry = MemoryEntry(
                workspace_id=None,
                user_id=sandbox["user_a_id"],
                namespace="agent",
                content="legacy memory",
                memory_type="semantic",
                importance=0.9,
            )
            db.add(entry)
            await db.commit()
            await db.refresh(entry)

            # Default: NULL workspace + non-owner -> denied
            with pytest.raises(TenancyError):
                await verify_entity_tenancy(
                    db,
                    entity_type="memory",
                    entity_id=entry.id,
                    workspace_id=None,
                    user_id=sandbox["user_b_id"],
                )

            # Default: NULL workspace + owner but fallback NOT enabled -> still denied
            with pytest.raises(TenancyError):
                await verify_entity_tenancy(
                    db,
                    entity_type="memory",
                    entity_id=entry.id,
                    workspace_id=None,
                    user_id=sandbox["user_a_id"],
                )

            # Explicit fallback + owner -> allowed
            allowed = await verify_entity_tenancy(
                db,
                entity_type="memory",
                entity_id=entry.id,
                workspace_id=None,
                user_id=sandbox["user_a_id"],
                owner_user_id=sandbox["user_a_id"],
                allow_legacy_owner_fallback=True,
            )
            assert allowed is True
        finally:
            await db.close()
