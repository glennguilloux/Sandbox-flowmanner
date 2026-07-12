"""Regression test for S2: hard dedup-on-write via unique constraint.

Verifies that two concurrent EventLog.append() calls using the SAME
idempotency_key (the real crash-recovery / retry race) collide on the
database unique constraint and produce exactly ONE persisted event —
not a duplicate RUN_FAILED event.

Requires a live PostgreSQL. The test owns its own engine built from
SUBSTRATE_IDEM_TEST_DB_URL (NOT stripped by the test env-guard, so it runs
on the host too). Defaults to a throwaway flowmapper DB on localhost.
In CI/container, point the var at the reachable Postgres (e.g. workflow-postgres)
and run the substrate + S2 migrations there first.

    SUBSTRATE_IDEM_TEST_DB_URL='postgresql+asyncpg://flowmanner:***@localhost:5432/flowmapper' \
        .venv/bin/python -m pytest tests/test_substrate_idempotency_unique.py -v

(Skips automatically when no DB is reachable.)
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.substrate_models import SubstrateEvent, SubstrateEventType
from app.services.substrate.event_log import EventLog

if TYPE_CHECKING:
    from collections.abc import Generator

_TEST_DB_URL = os.environ.get(
    "SUBSTRATE_IDEM_TEST_DB_URL",
    "postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@localhost:5432/flowmapper",
)

try:
    _engine = create_async_engine(
        _TEST_DB_URL,
        future=True,
        pool_pre_ping=True,
        connect_args={"server_settings": {"statement_timeout": "3000"}},
    )
    _SessionLocal = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)
    _DB_AVAILABLE = True
except Exception as e:  # pragma: no cover - import guard
    _DB_AVAILABLE = False
    _DB_IMPORT_ERROR = str(e)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def _count_events_for_key(db, idem_key: str) -> int:
    stmt = select(func.count(SubstrateEvent.id)).where(SubstrateEvent.idempotency_key == idem_key)
    result = await db.execute(stmt)
    return result.scalar() or 0


pytestmark = [
    pytest.mark.skipif(
        not _DB_AVAILABLE,
        reason=f"Database not available: {_DB_IMPORT_ERROR if not _DB_AVAILABLE else ''}",
    ),
    pytest.mark.integration,
]


class TestIdempotencyKeyUnique:
    """S2: concurrent append of the same key must not duplicate the event."""

    @pytest.mark.asyncio
    async def test_duplicate_idempotency_key_yields_single_event(self):
        """Two _expire_one-style appends racing the commit both pass the soft
        SELECT, but the unique constraint forces exactly one row to survive."""
        el = EventLog()
        run_id = str(uuid4())
        idem_key = f"pause_timeout_fail:{uuid4()}"

        # Simulate two concurrent workers each appending the same RUN_FAILED
        # event with the same idempotency_key.
        s1 = _SessionLocal()
        s2 = _SessionLocal()
        try:
            ev1 = asyncio.create_task(
                el.append(
                    s1,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.MISSION_FAILED,
                            "payload": {"cause": "pause_timeout"},
                            "actor": "system:expire_paused",
                            "idempotency_key": idem_key,
                        }
                    ],
                    mission_id=str(uuid4()),
                )
            )
            ev2 = asyncio.create_task(
                el.append(
                    s2,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.MISSION_FAILED,
                            "payload": {"cause": "pause_timeout"},
                            "actor": "system:expire_paused",
                            "idempotency_key": idem_key,
                        }
                    ],
                    mission_id=str(uuid4()),
                )
            )
            await asyncio.gather(ev1, ev2, return_exceptions=True)

            # Commit whatever survived; the loser's session rolls back.
            for s in (s1, s2):
                try:
                    await s.commit()
                except Exception:
                    await s.rollback()
        finally:
            await s1.close()
            await s2.close()

        # Exactly one event persisted under that key.
        async with _SessionLocal() as db:
            count = await _count_events_for_key(db, idem_key)
            assert count == 1, f"Expected exactly 1 event for key, got {count}"

    @pytest.mark.asyncio
    async def test_distinct_idempotency_keys_both_persist(self):
        """Different keys are not constrained against each other."""
        el = EventLog()
        run_id = str(uuid4())
        key_a = f"key_a:{uuid4()}"
        key_b = f"key_b:{uuid4()}"

        async with _SessionLocal() as db:
            await el.append(
                db,
                run_id,
                [
                    {"type": "test.a", "payload": {}, "idempotency_key": key_a},
                    {"type": "test.b", "payload": {}, "idempotency_key": key_b},
                ],
            )
            await db.commit()

            n_a = await _count_events_for_key(db, key_a)
            n_b = await _count_events_for_key(db, key_b)
            assert n_a == 1
            assert n_b == 1

    @pytest.mark.asyncio
    async def test_null_idempotency_keys_not_constrained(self):
        """Nullable key: the unique constraint permits multiple NULL keys
        (Postgres unique semantics — only non-null keys are constrained).

        append() always auto-computes a non-null key, so to exercise the
        constraint's NULL branch we insert rows directly with NULL keys.
        """
        el = EventLog()
        run_id = str(uuid4())
        async with _SessionLocal() as db:
            db.add(
                SubstrateEvent(
                    id=str(uuid4()),
                    sequence=1,
                    run_id=run_id,
                    type="test.null1",
                    payload={},
                    idempotency_key=None,
                )
            )
            db.add(
                SubstrateEvent(
                    id=str(uuid4()),
                    sequence=2,
                    run_id=run_id,
                    type="test.null2",
                    payload={},
                    idempotency_key=None,
                )
            )
            await db.commit()
            n = await db.execute(
                select(func.count(SubstrateEvent.id)).where(
                    SubstrateEvent.run_id == run_id,
                    SubstrateEvent.idempotency_key.is_(None),
                )
            )
            assert int(n.scalar() or 0) == 2
