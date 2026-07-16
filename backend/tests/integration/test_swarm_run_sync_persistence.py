"""Integration test: run_sync detachment persistence (P1 regression guard).

Opus confirmed the original swarm_tasks code was a SILENT data-loss bug: objects
returned from AsyncSession.run_sync() are DETACHED, so mutating them on the outer
async session and calling db.commit() writes nothing.

This test is self-contained (uses a dedicated real table `p1_probe`, dropped at
start/end; no dependency on the swarm schema, which is not migrated into this DB)
and proves:

  A) The FIXED pattern (select/merge ORM object on the async session, await
     commit -- exactly what swarm_tasks._*_task now does) PERSISTS the change.
  B) The OLD pattern (mutate the ORM object returned from run_sync, commit on the
     async session) does NOT persist -- locking in the regression.

Each scenario builds its OWN engine/session bound to the current event loop
(inside asyncio.run), mirroring how the production Celery task runs in a fresh
process. This avoids the cross-loop engine-binding issue seen when reusing the
module-level engine across separate asyncio.run calls.

Requires a reachable Postgres (the test harness points DATABASE_URL at it).
"""

import asyncio

import pytest
from sqlalchemy import String, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.models import Base


# Minimal model mapped to a dedicated table -- mirrors how SwarmTask was used.
class P1Probe(Base):
    __tablename__ = "p1_probe"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)


TABLE_DDL = "CREATE TABLE IF NOT EXISTS p1_probe ( id text primary key, status text)"


def _make_session():
    """Build a session factory bound to the CURRENT event loop."""
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


def _reset_table():
    async def _r():
        Session = _make_session()
        async with Session() as db:
            await db.execute(text("DROP TABLE IF EXISTS p1_probe"))
            await db.execute(text(TABLE_DDL))
            await db.execute(text("INSERT INTO p1_probe (id, status) VALUES ('t1', 'queued')"))
            await db.commit()

    asyncio.run(_r())


def _status(row_id: str) -> str | None:
    """Read status via a FRESH async session (independent of any prior session)."""

    async def _read():
        Session = _make_session()
        async with Session() as db:
            row = (await db.execute(text("SELECT status FROM p1_probe WHERE id = :i"), {"i": row_id})).first()
            return row[0] if row else None

    return asyncio.run(_read())


def test_fixed_pattern_persists():
    """The SHIPPED fix shape: merge the ORM object on the async session, await
    commit. The change MUST reach the DB."""
    _reset_table()

    async def _work():
        Session = _make_session()
        async with Session() as db:
            obj = P1Probe(id="t1", status="completed")
            await db.merge(obj)
            await db.commit()

    asyncio.run(_work())
    assert _status("t1") == "completed"


def test_old_detached_pattern_does_not_persist():
    """The BUGGY OLD pattern (what Opus flagged): load via run_sync -> DETACHED
    ORM object, mutate its attribute, commit on the async session. The change
    must NOT persist. Locks in the regression."""
    _reset_table()

    async def _load_detached():
        Session = _make_session()
        async with Session() as db:
            # Load via run_sync -> returns a DETACHED ORM object
            return await db.run_sync(lambda s: s.query(P1Probe).filter(P1Probe.id == "t1").first())

    detached = asyncio.run(_load_detached())

    # Mutate the detached object (the legacy bug) and commit on a fresh session.
    # Because `detached` is not part of the new session's identity map, the
    # commit is a silent no-op -- exactly the Opus bug.
    async def _commit_detached():
        Session = _make_session()
        async with Session() as db:
            detached.status = "stuck_via_detached"
            await db.commit()

    asyncio.run(_commit_detached())

    # The change must NOT have reached the database
    assert _status("t1") == "queued"
