"""Workspace-delete purge integration test (card t_d043d05e).

Verifies that ``delete_workspace`` (app/api/v3/workspaces.py) removes EVERY
workspace-owned child row whose foreign key is SET NULL / NO ACTION / missing —
not just the rows that cascade. Before the fix the handler did only
``db.delete(ws)`` and relied entirely on FK cascades, silently orphaning the
workspace's missions/agents/blueprints/playground sandboxes/HITL items/memory
entries/chat threads (and, on the live schema where those FKs are NO ACTION,
500ing instead of deleting at all).

These are REAL-DB integration tests: they open a fresh async session on the
module-global engine (same harness as test_scope_isolation.py) and commit.
Seeds use high-entropy ids so re-runs never collide with pre-existing rows.

The database connection string is taken from app.config.settings, which the
test runner overrides via the DATABASE_URL environment variable (the container
points at ``postgres``; locally we point at ``localhost``).

Run (from the backend dir of THIS worktree):
    DATABASE_URL='postgresql+asyncpg://flowmanner:...@localhost:5432/flowmanner' \\
        /opt/flowmanner/backend/.venv/bin/python -m pytest app/tests/test_ws_delete_purge.py -v

NOTE: this test imports the worktree-local ``app`` package (it is run from the
backend directory, so the worktree's code is on sys.path). It intentionally
does NOT hard-code a path to the main checkout — the whole point is to validate
the fix in *this* branch, not the main repo.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.api.v3 import workspaces as ws_router
from app.database import fresh_session
from app.models.agent import Agent
from app.models.blueprint_models import Blueprint
from app.models.chat import ChatMessage, ChatThread
from app.models.hitl_models import InboxItem
from app.models.memory_models import MemoryEntry
from app.models.mission_models import Mission, MissionTask
from app.models.playground_models import PlaygroundSandbox
from app.models.user import User
from app.models.workspace_models import Workspace, WorkspaceMember


def _uid() -> int:
    """Globally-unique int user id (avoids PK collisions across re-runs)."""
    return 900_000_000 + (uuid.uuid4().int % 90_000_000)


def _wsid() -> str:
    # Full 32-char hex UUID4 — MUST be a valid UUID because a handful of
    # workspace_id columns in the live schema are ``uuid`` (not ``varchar``):
    # e.g. ``episodes``, ``memory_action_events``. A ``ws-<hex>`` style id
    # would raise a DataError when the purge binds :ws against those columns.
    return str(uuid.uuid4())


def _make_user(db, user_id: int) -> User:
    user = User(
        email=f"purge-user-{user_id}@example.com",
        hashed_password="x",
        role="user",
    )
    user.id = user_id
    db.add(user)
    return user


def _make_workspace(db, workspace_id: str, owner_id: int) -> Workspace:
    ws = Workspace(
        id=workspace_id,
        name=f"ws-{workspace_id}",
        slug=f"ws-{workspace_id}-{uuid.uuid4().hex[:6]}",
        owner_id=owner_id,
        is_active=True,
    )
    db.add(ws)
    db.add(WorkspaceMember(workspace_id=workspace_id, user_id=owner_id, role="owner"))
    return ws


async def _enable_v3_flag(db) -> bool:
    """Flip the WORKSPACES_V3_ENDPOINTS flag on so delete_workspace passes
    its _require_workspaces_v3() gate. Returns the previous value so the
    test can restore it.
    """
    prev = await db.execute(text("SELECT enabled_globally FROM feature_flags " "WHERE key = 'WORKSPACES_V3_ENDPOINTS'"))
    previous = prev.scalar()
    await db.execute(text("UPDATE feature_flags SET enabled_globally = TRUE " "WHERE key = 'WORKSPACES_V3_ENDPOINTS'"))
    return bool(previous)


async def _restore_v3_flag(db, value: bool) -> None:
    await db.execute(
        text("UPDATE feature_flags SET enabled_globally = :v " "WHERE key = 'WORKSPACES_V3_ENDPOINTS'"),
        {"v": value},
    )


async def _seed_content(db, ws_id: str, owner_id: int) -> dict:
    """Create one row of each representative workspace-scoped content type in
    ws_id, including grandchildren that carry NO workspace_id of their own.
    """
    mission = Mission(
        user_id=owner_id,
        title="purge-mission",
        description="",
        workspace_id=ws_id,
        status="pending",
    )
    db.add(mission)
    await db.flush()  # generate mission.id (uuid default) for the child FK
    # MissionTask references missions.id (NO ACTION) — must be cleared via
    # the FK-join predicate before missions is deleted.
    db.add(MissionTask(mission_id=mission.id, title="t", status="pending", task_type="generic"))
    db.add(Agent(name="a", workspace_id=ws_id, owner_id=str(owner_id), state="active"))
    db.add(Blueprint(title="b", workspace_id=ws_id, user_id=owner_id, definition={}))
    db.add(
        PlaygroundSandbox(
            workspace_id=ws_id,
            sandbox_id=f"sb-{uuid.uuid4().hex}",
            user_id=owner_id,
            session_token=f"tok-{uuid.uuid4().hex}",
            expires_at=__import__("datetime").datetime(2030, 1, 1),
        )
    )
    db.add(
        InboxItem(
            workspace_id=ws_id,
            user_id=owner_id,
            interrupt_type="approval",
            title="purge-item",
        )
    )
    db.add(
        MemoryEntry(
            workspace_id=ws_id,
            user_id=owner_id,
            namespace="test",
            key="k",
            content="secret",
        )
    )
    thread = ChatThread(user_id=owner_id, username="u", title="purge-thread", workspace_id=ws_id)
    db.add(thread)
    await db.flush()  # generate thread.id (autoincrement) for the child FK
    # chat_messages references chat_threads.id (NO ACTION) — cleared via FK join.
    db.add(ChatMessage(thread_id=thread.id, user_id=owner_id, role="user", content="hi"))
    return {"mission": mission, "thread": thread}


async def _purge_plan_tables(db) -> list[str]:
    """The exact set of tables the handler will purge, in child-first order."""
    # _compute_purge_plan now returns (table, predicate, ws_owner) 3-tuples.
    return [t for t, _, _ in await ws_router._compute_purge_plan(db)]


async def _ws_bind_type(db, table_name: str):
    """Mirror the handler's per-table ``:ws`` bind typing (uuid vs str)."""
    from sqlalchemy import UUID as _SA_UUID

    engine = db.bind
    meta = __import__("sqlalchemy").MetaData()
    async with engine.connect() as conn:
        await conn.run_sync(lambda sc: meta.reflect(bind=sc))
    col = meta.tables[table_name].columns["workspace_id"]
    if isinstance(col.type, _SA_UUID):
        import uuid as _uuid

        return _uuid.UUID
    return str


async def _surviving_row_counts(db, ws_id: str, tables: list[str]) -> dict[str, int]:
    """Count rows per purged table that still reference ws_id.

    For tables with a ``workspace_id`` column we count directly; for tables
    without one (grandchildren) we count rows whose parent (joined by the same
    FK the purge plan uses) belongs to ws_id.
    """
    out: dict[str, int] = {}
    engine = db.bind
    meta = __import__("sqlalchemy").MetaData()
    async with engine.connect() as conn:
        await conn.run_sync(lambda sc: meta.reflect(bind=sc))
    plan = {t: (pred, owner) for t, pred, owner in await ws_router._compute_purge_plan(db)}
    for t in tables:
        if "workspace_id" in meta.tables[t].columns:
            # Type the bound value like the handler does (uuid columns need a
            # uuid object, not the varchar string).
            bind_type = await _ws_bind_type(db, t)
            n = await db.execute(
                text(f"SELECT count(*) FROM {t} WHERE workspace_id = :ws"),
                {"ws": bind_type(ws_id)},
            )
        else:
            # Reproduce the FK-JOIN predicate used by the purge for this table.
            # The :ws binds against the ROOT ancestor's workspace_id column,
            # whose type we must match too.
            pred, owner = plan[t]
            bind_type = await _ws_bind_type(db, owner)
            n = await db.execute(
                text(f"SELECT count(*) FROM {t} WHERE {pred}"),
                {"ws": bind_type(ws_id)},
            )
        out[t] = n.scalar() or 0
    out["workspaces"] = (
        await db.execute(
            text("SELECT count(*) FROM workspaces WHERE id = :ws"),
            {"ws": ws_id},
        )
    ).scalar() or 0
    return out


@pytest.mark.asyncio(loop_scope="module")
async def test_delete_workspace_purges_all_children():
    """delete_workspace must remove EVERY workspace-owned row (no surviving row
    in ANY purged table for this workspace_id) — not just a hardcoded subset.
    """
    uid = _uid()
    ws_id = _wsid()
    async with fresh_session() as db:
        _make_user(db, uid)
        _make_workspace(db, ws_id, uid)
        await db.flush()
        await _seed_content(db, ws_id, uid)
        await db.flush()

        tables = await _purge_plan_tables(db)
        before = await _surviving_row_counts(db, ws_id, tables)
        # The seeded tables must have had rows.
        assert before["missions"] >= 1
        assert before["chat_threads"] >= 1
        assert before["mission_tasks"] >= 1
        assert before["chat_messages"] >= 1
        assert before["workspaces"] == 1

        prev_flag = await _enable_v3_flag(db)
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        await ws_router.delete_workspace(workspace_id=ws_id, user=user, db=db)
        await _restore_v3_flag(db, prev_flag)
        await db.commit()

        after = await _surviving_row_counts(db, ws_id, tables)
        # The core card requirement: NO purged table retains a row for ws_id.
        for t in tables:
            assert after[t] == 0, f"orphaned rows remain in {t} for {ws_id}"
        assert after["workspaces"] == 0


@pytest.mark.asyncio(loop_scope="module")
async def test_delete_workspace_is_isolated_to_one_workspace():
    """Deleting workspace A must NOT touch workspace B's content (no
    cross-tenant deletion)."""
    uid = _uid()
    ws_a = _wsid()
    ws_b = _wsid()
    async with fresh_session() as db:
        _make_user(db, uid)
        _make_workspace(db, ws_a, uid)
        _make_workspace(db, ws_b, uid)
        await db.flush()
        await _seed_content(db, ws_a, uid)
        await _seed_content(db, ws_b, uid)
        await db.flush()

        tables = await _purge_plan_tables(db)
        prev_flag = await _enable_v3_flag(db)
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        await ws_router.delete_workspace(workspace_id=ws_a, user=user, db=db)
        await _restore_v3_flag(db, prev_flag)
        await db.commit()

        after_a = await _surviving_row_counts(db, ws_a, tables)
        after_b = await _surviving_row_counts(db, ws_b, tables)
        for t in tables:
            assert after_a[t] == 0, f"A: orphaned rows remain in {t}"
        assert after_a["workspaces"] == 0
        # B is untouched.
        assert after_b["missions"] >= 1, "cross-tenant deletion: B lost missions"
        assert after_b["chat_threads"] >= 1, "cross-tenant deletion: B lost threads"
        assert after_b["workspaces"] == 1


@pytest.mark.asyncio(loop_scope="module")
async def test_delete_workspace_requires_owner():
    """Non-owner membership must be rejected (403), leaving data intact."""
    uid_owner = _uid()
    uid_member = _uid()
    ws_id = _wsid()
    async with fresh_session() as db:
        _make_user(db, uid_owner)
        _make_user(db, uid_member)
        _make_workspace(db, ws_id, uid_owner)
        await db.flush()
        db.add(WorkspaceMember(workspace_id=ws_id, user_id=uid_member, role="member"))
        await _seed_content(db, ws_id, uid_owner)
        await db.flush()

        tables = await _purge_plan_tables(db)
        prev_flag = await _enable_v3_flag(db)
        member = (await db.execute(select(User).where(User.id == uid_member))).scalar_one()

        with pytest.raises(HTTPException) as exc_info:
            await ws_router.delete_workspace(workspace_id=ws_id, user=member, db=db)
        assert exc_info.value.status_code == 403

        await _restore_v3_flag(db, prev_flag)
        await db.commit()

        after = await _surviving_row_counts(db, ws_id, tables)
        # The owner's data must be fully intact.
        assert after["missions"] >= 1
        assert after["chat_threads"] >= 1
        assert after["workspaces"] == 1
