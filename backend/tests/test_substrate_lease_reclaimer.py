"""Tests for the stale-lease reclaimer (Q1-A Chunk 3).

Covers:
- find_expired_leases: ordering, filtering, limit
- reclaim_one: success, idempotency, event emission
- LeaseReclaimer.run_loop: exception resilience, stop event
- Feature flag gating
- Real subprocess chaos tests: spawn subprocess that acquires lease then
  exits without releasing (simulating crash), verify reclaimer cleans up

The chaos tests (TestChaosReclaimer) spawn a real Python subprocess that
acquires a lease then exits without releasing it (simulating a crash).
The test then runs the reclaimer and verifies the lease is gone and the
correct audit event was emitted.  These tests require a running PostgreSQL
database (they are pg-integration tests, not unit tests).
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.substrate_models import SubstrateEventType
from app.services.substrate.lease_reclaimer import (
    LeaseReclaimer,
    find_expired_leases,
    reclaim_one,
)
from app.services.substrate.leases import LeaseRecord


# ── Helpers ────────────────────────────────────────────────────────

CHAOS_HELPER = os.path.join(os.path.dirname(__file__), "_helpers", "chaos_lease_holder.py")

# DATABASE_URL for tests running on the host — override the Docker-internal
# hostname (postgres or workflow-postgres) with localhost since port 5432
# is mapped to the host.
_TEST_DB_URL: str | None = None


def _get_test_db_url() -> str:
    """Return a DATABASE_URL reachable from the test host (localhost:5432)."""
    global _TEST_DB_URL
    if _TEST_DB_URL is None:
        import re

        from app.config import settings

        # Replace the hostname in the authority part of the URL.
        # Handles both 'postgres' and 'workflow-postgres' hostnames.
        _TEST_DB_URL = re.sub(
            r"@[^/:]+(:\d+)",
            r"@localhost\1",
            settings.DATABASE_URL,
        )
    return _TEST_DB_URL


def _make_mock_db(*, fetchall_result=None, fetchone_result=None):
    """Create a mock AsyncSession with configurable execute() results."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = fetchall_result or []
    mock_result.fetchone.return_value = fetchone_result
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _make_expired_lease(
    *,
    worker_id: str = "dead-worker",
    run_id: str | None = None,
    renewed_count: int = 3,
) -> LeaseRecord:
    """Create an expired LeaseRecord for testing."""
    now = datetime.now(UTC)
    return LeaseRecord(
        id=1,
        worker_id=worker_id,
        run_id=run_id or str(uuid4()),
        acquired_at=now - timedelta(seconds=600),
        expires_at=now - timedelta(seconds=300),
        renewed_count=renewed_count,
        generation=1,
    )


@pytest.fixture
async def db():
    """Real async database session for pg-integration tests.

    Connects via localhost:5432 (the Docker port mapping) instead of the
    Docker-internal hostname.  Each test runs in a transaction that is
    rolled back on teardown so tests don't leak data.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(_get_test_db_url(), pool_pre_ping=True)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        yield session
        # Roll back any uncommitted data so tests are isolated.
        await session.rollback()

    await engine.dispose()


# ═══════════════════════════════════════════════════════════════════
# find_expired_leases (pg-integration)
# ═══════════════════════════════════════════════════════════════════


class TestFindExpiredLeases:
    async def test_returns_only_expired(self, db):
        """find_expired_leases returns only leases with expires_at < now()."""
        from sqlalchemy import text

        expired_id = str(uuid4())
        active_id = str(uuid4())

        await db.execute(
            text(
                """
                INSERT INTO substrate_worker_leases
                    (worker_id, run_id, acquired_at, expires_at, renewed_count, generation)
                VALUES
                    ('dead', :rid1, now(), now() - interval '5 minutes', 0, 1),
                    ('alive', :rid2, now(), now() + interval '5 minutes', 0, 1)
                """
            ),
            {"rid1": expired_id, "rid2": active_id},
        )
        await db.flush()

        results = await find_expired_leases(db)

        run_ids = [r.run_id for r in results]
        assert expired_id in run_ids
        assert active_id not in run_ids

    async def test_ordered_oldest_first(self, db):
        """Expired leases are returned ordered by expires_at ASC."""
        from sqlalchemy import text

        rid_old = str(uuid4())
        rid_new = str(uuid4())

        await db.execute(
            text(
                """
                INSERT INTO substrate_worker_leases
                    (worker_id, run_id, acquired_at, expires_at, renewed_count, generation)
                VALUES
                    ('w1', :rid_old, now(), now() - interval '10 minutes', 0, 1),
                    ('w2', :rid_new, now(), now() - interval '1 minute', 0, 1)
                """
            ),
            {"rid_old": rid_old, "rid_new": rid_new},
        )
        await db.flush()

        results = await find_expired_leases(db)

        assert len(results) >= 2
        # Find our two leases in the results and verify order.
        our_leases = [r for r in results if r.run_id in (rid_old, rid_new)]
        assert len(our_leases) == 2
        assert our_leases[0].run_id == rid_old
        assert our_leases[1].run_id == rid_new

    async def test_respects_limit(self, db):
        """Limit parameter caps the number of returned leases."""
        from sqlalchemy import text

        rids = [str(uuid4()) for _ in range(5)]
        for rid in rids:
            await db.execute(
                text(
                    """
                    INSERT INTO substrate_worker_leases
                        (worker_id, run_id, acquired_at, expires_at, renewed_count, generation)
                    VALUES ('w', :rid, now(), now() - interval '5 minutes', 0, 1)
                    """
                ),
                {"rid": rid},
            )
        await db.flush()

        results = await find_expired_leases(db, limit=2)
        assert len(results) == 2


# ═══════════════════════════════════════════════════════════════════
# reclaim_one (mock-based)
# ═══════════════════════════════════════════════════════════════════


class TestReclaimOne:
    def test_succeeds_when_expired(self):
        """reclaim_one returns True for an expired lease and emits an event."""
        lease = _make_expired_lease()
        db = _make_mock_db(fetchone_result=MagicMock(generation=2))
        event_log = MagicMock()
        event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])

        with patch(
            "app.services.substrate.lease_reclaimer.try_claim_lease",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "app.services.substrate.lease_reclaimer.release_lease",
            new_callable=AsyncMock,
        ):
            result = asyncio.run(
                reclaim_one(db, lease, "reclaimer-test", event_log=event_log)
            )

        assert result is True
        # Verify LEASE_RELEASED event with reason="reclaimed".
        event_log.append.assert_called_once()
        call_args = event_log.append.call_args
        events = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("events", [])
        assert any(
            e.get("type") == SubstrateEventType.LEASE_RELEASED
            and e.get("payload", {}).get("reason") == "reclaimed"
            and e.get("payload", {}).get("previous_worker_id") == lease.worker_id
            for e in events
        ), f"Expected LEASE_RELEASED with reason='reclaimed' in {events}"

    def test_returns_false_when_already_released(self):
        """reclaim_one returns False when another process already reclaimed."""
        lease = _make_expired_lease()
        db = _make_mock_db()
        event_log = MagicMock()
        event_log.append = AsyncMock()

        with patch(
            "app.services.substrate.lease_reclaimer.try_claim_lease",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = asyncio.run(
                reclaim_one(db, lease, "reclaimer-test", event_log=event_log)
            )

        assert result is False
        event_log.append.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# LeaseReclaimer loop
# ═══════════════════════════════════════════════════════════════════


class TestLeaseReclaimerLoop:
    def test_loop_continues_after_exception(self):
        """The reclaimer loop survives an exception in _scan_once."""
        reclaimer = LeaseReclaimer(scan_interval_seconds=1, batch_size=10)
        scan_count = [0]

        async def flaky_scan():
            scan_count[0] += 1
            if scan_count[0] == 1:
                raise RuntimeError("Transient DB error")
            return 0

        reclaimer._scan_once = flaky_scan  # type: ignore[assignment]

        stop = asyncio.Event()

        async def run():
            task = asyncio.create_task(reclaimer.run_loop(stop))
            await asyncio.sleep(2.5)
            stop.set()
            await task

        asyncio.run(run())
        assert scan_count[0] >= 2, f"Expected at least 2 scans, got {scan_count[0]}"


# ═══════════════════════════════════════════════════════════════════
# Feature flag
# ═══════════════════════════════════════════════════════════════════


class TestReclaimerDisabledFlag:
    def test_disabled_flag_skips_start(self):
        """When FLOWMANNER_LEASE_RECLAIMER_ENABLED=false, no thread is started."""
        with patch(
            "app.config.settings.FLOWMANNER_LEASE_RECLAIMER_ENABLED", False
        ), patch(
            "app.services.substrate.lease_reclaimer.start_reclaimer"
        ) as mock_start:
            from app.config import settings

            if settings.FLOWMANNER_LEASE_RECLAIMER_ENABLED:
                from app.services.substrate.lease_reclaimer import start_reclaimer

                start_reclaimer()

        mock_start.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# Reclaimer integration — reclaim expired seed (pg-integration)
# ═══════════════════════════════════════════════════════════════════


class TestReclaimerIntegration:
    async def test_reclaimer_cleans_up_expired_seeds(self, db):
        """Seed an expired lease, run the reclaimer, verify it's gone."""
        from sqlalchemy import text

        run_id = str(uuid4())
        await db.execute(
            text(
                """
                INSERT INTO substrate_worker_leases
                    (worker_id, run_id, acquired_at, expires_at, renewed_count, generation)
                VALUES ('crashed-worker', :rid, now(), now() - interval '5 minutes', 2, 1)
                """
            ),
            {"rid": run_id},
        )
        await db.flush()

        reclaimer_id = f"reclaimer-test-{uuid4().hex[:8]}"

        lease_row = await db.execute(
            text(
                "SELECT id, worker_id, run_id, acquired_at, expires_at, renewed_count, generation "
                "FROM substrate_worker_leases WHERE run_id = :rid"
            ),
            {"rid": run_id},
        )
        row = lease_row.fetchone()
        assert row is not None
        lease = LeaseRecord(
            id=row.id,
            worker_id=row.worker_id,
            run_id=row.run_id,
            acquired_at=row.acquired_at,
            expires_at=row.expires_at,
            renewed_count=row.renewed_count,
            generation=row.generation,
        )

        event_log = MagicMock()
        event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])

        ok = await reclaim_one(db, lease, reclaimer_id, event_log=event_log)
        await db.commit()

        assert ok is True

        remaining = await db.execute(
            text("SELECT 1 FROM substrate_worker_leases WHERE run_id = :rid"),
            {"rid": run_id},
        )
        assert remaining.fetchone() is None

        event_log.append.assert_called_once()
        events = event_log.append.call_args[0][2]
        assert any(
            e.get("type") == SubstrateEventType.LEASE_RELEASED
            and e.get("payload", {}).get("reason") == "reclaimed"
            for e in events
        )


# ═══════════════════════════════════════════════════════════════════
# Chaos tests — real subprocess + kill -9 (pg-integration)
# ═══════════════════════════════════════════════════════════════════


def _spawn_chaos_subprocess(
    worker_id: str, run_id: str, ttl_seconds: int
) -> subprocess.Popen:
    """Spawn a chaos subprocess, wait for it to claim, then SIGKILL it.

    The helper acquires a lease, prints "OK", then blocks on stdin.
    We read "OK" from stdout, then send SIGKILL while the process is
    still alive — a real hard kill that prevents any cleanup.

    Returns the (killed) Popen object.
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = _get_test_db_url()

    proc = subprocess.Popen(
        [sys.executable, CHAOS_HELPER, worker_id, run_id, str(ttl_seconds)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
    )

    # Read the "OK" line — the helper blocks on stdin after printing it.
    assert proc.stdout is not None
    ok_line = proc.stdout.readline()
    assert "OK" in ok_line, f"Chaos helper did not print OK: {ok_line}"

    # Process is alive (blocked on stdin).  Kill it hard.
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait(timeout=5)

    return proc


async def _fresh_db():
    """Create a fresh DB session with a new transaction.

    PostgreSQL's ``now()`` is frozen to the transaction start time.
    The ``db`` fixture starts its transaction before the chaos sleep,
    so ``try_claim_lease``'s ``WHERE expires_at < now()`` sees a stale
    timestamp.  This helper creates a session whose ``now()`` is current.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(_get_test_db_url(), pool_pre_ping=True)
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    return factory(), engine


class TestChaosReclaimer:
    async def test_chaos_kill_then_reclaim(self):
        """Spawn a subprocess that acquires a lease, kill -9 it, verify reclaimer cleans up.

        This is the proof that the lease design handles real-world crashes:
        - A real process acquires a lease, then we send SIGKILL (hard kill).
        - After TTL expiry, the reclaimer finds and reclaims the orphaned lease.
        - A LEASE_RELEASED event with reason="reclaimed" appears in the event log.
        """
        from sqlalchemy import text

        chaos_worker_id = f"chaos-{uuid4().hex[:8]}"
        chaos_run_id = str(uuid4())
        ttl_seconds = 2

        # 1. Spawn subprocess, wait for claim, then SIGKILL.
        _spawn_chaos_subprocess(chaos_worker_id, chaos_run_id, ttl_seconds)

        # 2. Wait for TTL to expire.
        time.sleep(ttl_seconds + 1)

        # 3. Use a FRESH session so `now()` is current (not stale from
        #    the fixture's transaction that started before the sleep).
        session, engine = await _fresh_db()
        try:
            # Verify the lease exists (subprocess acquired it).
            row = (
                await session.execute(
                    text(
                        "SELECT 1 FROM substrate_worker_leases "
                        "WHERE run_id = :rid AND worker_id = :wid"
                    ),
                    {"rid": chaos_run_id, "wid": chaos_worker_id},
                )
            ).fetchone()
            assert row is not None, "Chaos subprocess did not acquire a lease"

            # 4. Run the reclaimer with the fresh session.
            reclaimer_id = f"reclaimer-chaos-{uuid4().hex[:8]}"
            event_log = MagicMock()
            event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])

            lease_row = (
                await session.execute(
                    text(
                        "SELECT id, worker_id, run_id, acquired_at, expires_at, "
                        "renewed_count, generation "
                        "FROM substrate_worker_leases WHERE run_id = :rid"
                    ),
                    {"rid": chaos_run_id},
                )
            ).fetchone()
            assert lease_row is not None, "Lease disappeared before reclaimer ran"

            lease = LeaseRecord(
                id=lease_row.id,
                worker_id=lease_row.worker_id,
                run_id=lease_row.run_id,
                acquired_at=lease_row.acquired_at,
                expires_at=lease_row.expires_at,
                renewed_count=lease_row.renewed_count,
                generation=lease_row.generation,
            )

            ok = await reclaim_one(session, lease, reclaimer_id, event_log=event_log)
            await session.commit()

            assert ok is True

            # 5. Verify the lease is gone.
            remaining = (
                await session.execute(
                    text("SELECT 1 FROM substrate_worker_leases WHERE run_id = :rid"),
                    {"rid": chaos_run_id},
                )
            ).fetchone()
            assert remaining is None, "Reclaimer did not clean up the lease"

            # 6. Verify the LEASE_RELEASED event.
            event_log.append.assert_called_once()
            events = event_log.append.call_args[0][2]
            lease_events = [
                e for e in events if e.get("type") == SubstrateEventType.LEASE_RELEASED
            ]
            assert len(lease_events) == 1
            payload = lease_events[0]["payload"]
            assert payload["reason"] == "reclaimed"
            assert payload["previous_worker_id"] == chaos_worker_id
        finally:
            await engine.dispose()

    async def test_chaos_reclaim_emits_event_with_previous_worker_id(self):
        """The LEASE_RELEASED event from a chaos reclaim carries the original worker_id."""
        from sqlalchemy import text

        chaos_worker_id = f"chaos-{uuid4().hex[:8]}"
        chaos_run_id = str(uuid4())
        ttl_seconds = 2

        # 1. Spawn and kill -9 chaos subprocess.
        _spawn_chaos_subprocess(chaos_worker_id, chaos_run_id, ttl_seconds)

        # 2. Wait for TTL.
        time.sleep(ttl_seconds + 1)

        # 3. Fresh session for the reclaim.
        session, engine = await _fresh_db()
        try:
            # Read the orphaned lease.
            lease_row = (
                await session.execute(
                    text(
                        "SELECT id, worker_id, run_id, acquired_at, expires_at, "
                        "renewed_count, generation "
                        "FROM substrate_worker_leases WHERE run_id = :rid"
                    ),
                    {"rid": chaos_run_id},
                )
            ).fetchone()
            assert lease_row is not None

            lease = LeaseRecord(
                id=lease_row.id,
                worker_id=lease_row.worker_id,
                run_id=lease_row.run_id,
                acquired_at=lease_row.acquired_at,
                expires_at=lease_row.expires_at,
                renewed_count=lease_row.renewed_count,
                generation=lease_row.generation,
            )

            # 4. Reclaim and verify event payload.
            event_log = MagicMock()
            event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])
            reclaimer_id = f"reclaimer-chaos2-{uuid4().hex[:8]}"

            ok = await reclaim_one(session, lease, reclaimer_id, event_log=event_log)
            await session.commit()

            assert ok is True

            events = event_log.append.call_args[0][2]
            payload = events[0]["payload"]
            assert payload["previous_worker_id"] == chaos_worker_id
            assert payload["previous_renewed_count"] == 0
        finally:
            await engine.dispose()
