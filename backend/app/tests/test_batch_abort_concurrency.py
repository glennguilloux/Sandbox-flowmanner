"""Regression test for the batch_abort deadlock hardening.

The previous ``batch_abort`` lock was an unordered ``SELECT ... FOR UPDATE``
over an ``IN (...)`` list with no ``SKIP LOCKED`` and no ``lock_timeout``.
Against a row already held by a concurrent per-mission abort, that lock would
block (then time out via the server's statement_timeout) — a live deadlock
risk under concurrent aborts.

The fix (app/api/_mission_cqrs/commands.py) sorts the ids, locks in
``ORDER BY Mission.id`` order, uses ``with_for_update(skip_locked=True)``, and
sets a session ``lock_timeout`` of 2s.

This test proves the fix: it holds a ``FOR UPDATE`` lock on ONE mission row
in a separate open transaction, then calls ``batch_abort`` over ALL missions
(including the contended one). ``SKIP LOCKED`` must let ``batch_abort`` skip
the held row and abort the rest, completing well within 3s. Without the fix,
``batch_abort`` would block on the contended row (or raise LockNotAvailable
after the 2s timeout).

Requires a reachable Postgres (JSONB/UUID columns cannot be rendered on
sqlite). Skips cleanly when Postgres is unavailable.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Unique per-session hermetic DB, mirroring test_marketplace_txn_lifecycle.py.
_BASE = os.getenv(
    "FLOWMANNER_BATCH_ABORT_TEST_DB",
    str(settings.DATABASE_URL),
)
# Normalise host so the test runs from the homelab host (not just in-container).
_BASE = _BASE.replace("@postgres:", "@127.0.0.1:")


@pytest_asyncio.fixture
async def engines():
    db_name = f"batch_abort_{uuid.uuid4().hex[:12]}"
    admin_url = _BASE.rsplit("/", 1)[0] + "/postgres"
    test_url = _BASE.rsplit("/", 1)[0] + "/" + db_name

    admin = create_async_engine(admin_url, future=True)
    try:
        async with admin.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(sql_text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await admin.dispose()

    engine = create_async_engine(test_url, future=True)
    async with engine.begin() as conn:
        # Minimal schema: only the tables this test touches.
        from app.models import Base

        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()
        admin2 = create_async_engine(admin_url, future=True)
        try:
            async with admin2.connect() as conn:
                await conn.execution_options(isolation_level="AUTOCOMMIT")
                await conn.execute(sql_text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        finally:
            await admin2.dispose()


@pytest_asyncio.fixture
async def seeded(engines):
    """Seed one user + 5 running missions; return (SessionLocal, user, mission_ids)."""
    from app.models.mission_models import Mission, MissionStatus
    from app.models.user import User

    SessionLocal = async_sessionmaker(bind=engines, class_=AsyncSession, expire_on_commit=False)

    user = User(
        email=f"ba_{uuid.uuid4().hex[:8]}@example.com",
        username=f"ba_{uuid.uuid4().hex[:8]}",
        full_name="Batch Abort Test",
        hashed_password="x",
    )
    async with SessionLocal() as db:
        db.add(user)
        await db.flush()
        mission_ids = []
        for _ in range(5):
            m = Mission(
                id=uuid.uuid4(),
                user_id=user.id,
                title="batch-abort-target",
                description="test",
                mission_type="general",
                status=MissionStatus.RUNNING,
            )
            db.add(m)
            await db.flush()
            mission_ids.append(m.id)
        await db.commit()

    return SessionLocal, user, mission_ids


async def _hold_lock(engines, mission_id):
    """Open a raw connection, lock one row FOR UPDATE, and keep it held.

    Returns the connection + the ``release`` coroutine the caller must await
    to roll back and free the lock.
    """
    conn = await engines.connect()
    await conn.execution_options(isolation_level="READ COMMITTED")
    await conn.execute(sql_text("BEGIN"))
    await conn.execute(sql_text("SELECT id FROM missions WHERE id = :mid FOR UPDATE").bindparams(mid=mission_id))

    async def release():
        await conn.execute(sql_text("ROLLBACK"))
        await conn.close()

    return release


@pytest.mark.asyncio
async def test_batch_abort_skips_contended_row_and_completes_under_3s(seeded, engines):
    from datetime import UTC, datetime

    from app.api._mission_cqrs.commands import MissionCommandHandlers
    from app.models.mission_models import Mission, MissionStatus

    SessionLocal, user, mission_ids = seeded
    contended = mission_ids[0]

    release = await _hold_lock(engines, contended)

    handler_session = SessionLocal()
    handler = MissionCommandHandlers(handler_session)

    import asyncio

    try:
        start = asyncio.get_event_loop().time()
        result = await asyncio.wait_for(
            handler.batch_abort(user, mission_ids, "user_requested"),
            timeout=3.0,
        )
        elapsed = asyncio.get_event_loop().time() - start
    finally:
        await handler_session.close()
        await release()

    # Completed promptly (SKIP LOCKED, not blocked on the contended row).
    assert elapsed < 3.0, f"batch_abort took {elapsed:.2f}s — looks blocked on the lock"

    # With SKIP LOCKED, the held row is skipped: 5 requested, 4 found/aborted.
    assert result["total_requested"] == 5
    assert result["total_found"] == 4, "contended row must be skipped via SKIP LOCKED"
    aborted_ids = {uuid.UUID(r["mission_id"]) for r in result["results"] if r["aborted"]}
    assert contended not in aborted_ids, "contended row must be skipped (SKIP LOCKED)"
    assert len(aborted_ids) == 4, f"expected 4 aborted, got {len(aborted_ids)}"

    # Verify on-disk state too.
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                sql_text("SELECT id, status FROM missions WHERE id = ANY(:ids)").bindparams(
                    ids=[str(m) for m in mission_ids]
                )
            )
        ).all()
    status_by_id = {uuid.UUID(str(r[0])): r[1] for r in rows}
    assert status_by_id[contended] == MissionStatus.RUNNING.value
    assert all(status_by_id[m] == MissionStatus.ABORTED.value for m in mission_ids[1:])


@pytest.mark.asyncio
async def test_batch_abort_lock_is_ordered_and_skip_locked(seeded):
    """Static assertion that the production lock uses the hardened shape.

    This guards against a future regression that removes ``SKIP LOCKED`` /
    ``order_by`` / ``lock_timeout`` from batch_abort.
    """
    import inspect

    from app.api._mission_cqrs import commands

    src = inspect.getsource(commands.MissionCommandHandlers.batch_abort)
    assert "skip_locked=True" in src, "batch_abort must use with_for_update(skip_locked=True)"
    assert "order_by(Mission.id)" in src, "batch_abort must lock rows in ORDER BY Mission.id"
    assert "lock_timeout" in src, "batch_abort must set a session lock_timeout"
    assert "SET LOCAL" in src, "batch_abort must SET LOCAL lock_timeout"
