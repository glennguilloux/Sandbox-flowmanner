"""Regression test for Trust B2: resume_mission must lock the mission row.

The paused→resume race: ``expire_paused_missions`` (Celery beat) selects
``PAUSED`` rows ``FOR UPDATE SKIP LOCKED`` and flips them to ``FAILED``.
Previously ``resume_mission`` did a plain ``SELECT`` (no lock) via
``require_mission_access``, so the expire task's ``SKIP LOCKED`` did NOT skip
the row a resume was mutating — the two transactions could interleave and the
user's resume could be clobbered to ``FAILED``.

The fix (app/api/_mission_cqrs/commands.py::resume_mission) locks the row
``FOR UPDATE`` before the status transition, so expire's ``SKIP LOCKED`` skips
the held row → mutual exclusion.

This test proves the fix three ways:

1. Static: the production source now contains ``with_for_update()``.
2. Dynamic (mutex from expire's side): a row locked by a resume-style
   ``FOR UPDATE`` is skipped by ``SELECT ... FOR UPDATE SKIP LOCKED`` (exactly
   the query the expire task issues) — proving the expire task cannot grab and
   FAIL the mission a user is resuming.
3. Dynamic (resume takes a lock): the real ``resume_mission`` handler BLOCKS on
   a row already held ``FOR UPDATE`` by a concurrent transaction, proving it now
   acquires the row lock (it did not before this fix).

NOTE (out-of-scope finding, flagged for review): ``resume_mission`` sets
``MissionStatus.QUEUED``, but the transition table in
``app/models/mission_models.py`` (``_MISSION_TRANSITIONS``) only permits
``PAUSED → {RUNNING, FAILED, ABORTED}`` — NOT ``PAUSED → QUEUED``. So against a
real DB the ORM status-set validator raises on resume. This is a *separate*
pre-existing defect (present in the base commit, uncovered because existing
resume tests mock the session so the validator never fires). It is unrelated to
the B2 lock race and is intentionally NOT fixed here (minimal-change scope). The
tests below therefore assert the lock/mutex behaviour, not the final QUEUED
status.

Requires a reachable Postgres (JSONB/UUID columns cannot be rendered on
sqlite). Skips cleanly when Postgres is unavailable. To point at the real
homelab DB set FLOWMANNER_RESUME_LOCK_TEST_DB (the pytest env guard pops
DATABASE_URL, so the config default dev password is used otherwise).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Unique per-session hermetic DB, mirroring test_batch_abort_concurrency.py.
_BASE = os.getenv(
    "FLOWMANNER_RESUME_LOCK_TEST_DB",
    str(settings.DATABASE_URL),
)
# Normalise host so the test runs from the homelab host (not just in-container).
# @postgres: is the in-compose hostname; @localhost: hits a pg_hba peer/socket
# rule on the host that rejects password auth, whereas @127.0.0.1: uses the
# TCP md5 rule that accepts it — so map both to 127.0.0.1.
_BASE = _BASE.replace("@postgres:", "@127.0.0.1:").replace("@localhost:", "@127.0.0.1:")


@pytest_asyncio.fixture
async def engines():
    db_name = f"resume_lock_{uuid.uuid4().hex[:12]}"
    admin_url = _BASE.rsplit("/", 1)[0] + "/postgres"
    test_url = _BASE.rsplit("/", 1)[0] + "/" + db_name

    admin = create_async_engine(admin_url, future=True)
    try:
        async with admin.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(sql_text(f'CREATE DATABASE "{db_name}"'))
    except Exception as exc:  # Postgres unreachable on host → skip cleanly.
        await admin.dispose()
        pytest.skip(f"Postgres unavailable for hermetic resume-lock test: {exc}")
    finally:
        await admin.dispose()

    engine = create_async_engine(test_url, future=True)
    async with engine.begin() as conn:
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
                await conn.execute(sql_text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        finally:
            await admin2.dispose()


@pytest_asyncio.fixture
async def seeded(engines):
    """Seed one user + one PAUSED mission; return (SessionLocal, user, mission_id)."""
    from app.models.mission_models import Mission, MissionStatus
    from app.models.user import User

    SessionLocal = async_sessionmaker(bind=engines, class_=AsyncSession, expire_on_commit=False)

    user = User(
        email=f"rl_{uuid.uuid4().hex[:8]}@example.com",
        username=f"rl_{uuid.uuid4().hex[:8]}",
        full_name="Resume Lock Test",
        hashed_password="x",
    )
    async with SessionLocal() as db:
        db.add(user)
        await db.flush()
        mission = Mission(
            id=uuid.uuid4(),
            user_id=user.id,
            title="resume-lock-target",
            description="test",
            mission_type="general",
            status=MissionStatus.PAUSED,
        )
        db.add(mission)
        await db.flush()
        mission_id = mission.id
        await db.commit()

    return SessionLocal, user, mission_id


def test_resume_mission_uses_for_update_lock():
    """Static guard: resume_mission must lock the row FOR UPDATE (B2 fix)."""
    import inspect

    from app.api._mission_cqrs import commands

    src = inspect.getsource(commands.MissionCommandHandlers.resume_mission)
    assert "with_for_update" in src, "resume_mission must lock the mission row FOR UPDATE (Trust B2)"


@pytest.mark.asyncio
async def test_expire_skips_row_locked_by_resume(seeded, engines):
    """A row locked by resume's FOR UPDATE is skipped by expire's SKIP LOCKED.

    This is the core B2 proof: while a resume-style ``FOR UPDATE`` lock is held
    on the mission row, the expire task's exact query
    (``SELECT ... WHERE status='paused' FOR UPDATE SKIP LOCKED``) must NOT return
    the row — so the expire beat task cannot flip it to FAILED underneath the
    user who is resuming it. Mutual exclusion.
    """
    from sqlalchemy import select

    from app.models.mission_models import Mission

    _SessionLocal, _user, mission_id = seeded

    # Hold the mission row FOR UPDATE exactly as resume_mission now does.
    resume_conn = await engines.connect()
    await resume_conn.execution_options(isolation_level="READ COMMITTED")
    await resume_conn.execute(sql_text("BEGIN"))
    await resume_conn.execute(select(Mission).where(Mission.id == str(mission_id)).with_for_update())

    # The expire task's query must now SKIP this row (SKIP LOCKED).
    expire_conn = await engines.connect()
    await expire_conn.execution_options(isolation_level="READ COMMITTED")
    await expire_conn.execute(sql_text("BEGIN"))
    expire_rows = (
        await expire_conn.execute(sql_text("SELECT id FROM missions WHERE status = 'paused' FOR UPDATE SKIP LOCKED"))
    ).all()
    await expire_conn.execute(sql_text("ROLLBACK"))
    await expire_conn.close()

    await resume_conn.execute(sql_text("ROLLBACK"))
    await resume_conn.close()

    assert all(
        str(r[0]) != str(mission_id) for r in expire_rows
    ), "expire task must skip the row locked by resume (FOR UPDATE SKIP LOCKED)"


@pytest.mark.asyncio
async def test_resume_mission_blocks_on_held_row_lock(seeded, engines):
    """The real resume_mission handler BLOCKS on a row already held FOR UPDATE.

    Before this fix resume used a plain SELECT and would NOT wait on a competing
    lock. Now it takes ``FOR UPDATE``, so with the row held by a concurrent
    transaction the handler must block until that lock is released — proving the
    lock is real (and thus that expire's SKIP LOCKED will skip resume's row).

    We do NOT assert the final QUEUED status: that hits a separate pre-existing
    transition-table defect (PAUSED→QUEUED is not permitted — see module
    docstring), which is out of B2 scope. We assert only the mutex: blocked
    while held, unblocked after release.
    """
    from sqlalchemy import select

    from app.api._mission_cqrs.commands import MissionCommandHandlers
    from app.models.mission_models import Mission

    SessionLocal, user, mission_id = seeded

    # Competing transaction holds the mission row FOR UPDATE.
    holder = await engines.connect()
    await holder.execution_options(isolation_level="READ COMMITTED")
    await holder.execute(sql_text("BEGIN"))
    await holder.execute(select(Mission).where(Mission.id == str(mission_id)).with_for_update())

    handler_session = SessionLocal()
    handler = MissionCommandHandlers(handler_session)
    resume_task = asyncio.create_task(handler.resume_mission(user, mission_id))

    # resume must block on the held row lock (it now takes FOR UPDATE).
    await asyncio.sleep(0.5)
    assert not resume_task.done(), "resume must block on the row lock — proves it takes FOR UPDATE"

    # Release the competing lock; resume unblocks and proceeds to its transition.
    await holder.execute(sql_text("ROLLBACK"))
    await holder.close()

    # It unblocks promptly. It may raise the KNOWN out-of-scope PAUSED→QUEUED
    # transition error; we only require that it is no longer blocked on the lock.
    with contextlib.suppress(Exception):
        await asyncio.wait_for(resume_task, timeout=5.0)
    finally_done = resume_task.done()
    with contextlib.suppress(Exception):
        await handler_session.close()
    assert finally_done, "resume must unblock once the competing lock is released"
