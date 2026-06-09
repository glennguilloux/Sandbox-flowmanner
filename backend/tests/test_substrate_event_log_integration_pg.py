"""Real PostgreSQL integration test for substrate_events append-only trigger.

Verifies that the database-level BEFORE UPDATE OR DELETE trigger
rejects any attempt to modify or remove rows from substrate_events.

This test requires a live PostgreSQL connection with the H2 substrate
migration applied. It should be run inside the Docker container where
the full database stack is available.

Usage (containerized):
    docker compose exec backend pytest /app/tests/test_substrate_event_log_integration_pg.py -v
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from uuid import uuid4

import pytest
from sqlalchemy import text

# Only run these tests when a real database is available
try:
    from app.database import AsyncSessionLocal
    from app.models.substrate_models import SubstrateEvent, SubstrateEventType
    from app.services.substrate.event_log import EventLog

    _DB_AVAILABLE = True
except Exception as e:
    _DB_AVAILABLE = False
    _DB_IMPORT_ERROR = str(e)


# ── Session-scoped event loop ──────────────────────────────────────
# Prevents asyncpg "Future attached to a different loop" errors
# when asyncio_mode=auto creates new loops per test function.
# All integration tests share one loop so the SQLAlchemy engine's
# connection pool stays valid across test boundaries.


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Skip condition ─────────────────────────────────────────────────

pytestmark = [
    pytest.mark.skipif(
        not _DB_AVAILABLE,
        reason=f"Database not available: {_DB_IMPORT_ERROR if not _DB_AVAILABLE else ''}",
    ),
    pytest.mark.integration,
]


# ═══════════════════════════════════════════════════════════════════
# Test: append-only trigger enforcement
# ═══════════════════════════════════════════════════════════════════


class TestAppendOnlyTriggerIntegration:
    @pytest.mark.asyncio
    async def test_insert_succeeds(self):
        """A normal INSERT into substrate_events succeeds."""
        run_id = str(uuid4())
        event_id = str(uuid4())

        async with AsyncSessionLocal() as db:
            try:
                event = SubstrateEvent(
                    id=event_id,
                    sequence=1,
                    run_id=run_id,
                    type="test.insert",
                    payload={"note": "integration test"},
                    actor="test_runner",
                )
                db.add(event)
                await db.commit()

                # Verify it was inserted
                from sqlalchemy import select

                result = await db.execute(
                    select(SubstrateEvent).where(SubstrateEvent.id == event_id)
                )
                found = result.scalars().first()
                assert found is not None
                assert str(found.run_id) == run_id
                assert found.type == "test.insert"

            finally:
                # Cleanup: temporarily drop trigger to allow DELETE for cleanup
                await db.execute(
                    text(
                        "DROP TRIGGER IF EXISTS trg_substrate_events_append_only ON substrate_events"
                    )
                )
                await db.execute(
                    text("DELETE FROM substrate_events WHERE id = :eid"),
                    {"eid": event_id},
                )
                await db.execute(
                    text(
                        """
                    CREATE TRIGGER trg_substrate_events_append_only
                    BEFORE UPDATE OR DELETE ON substrate_events
                    FOR EACH STATEMENT
                    EXECUTE FUNCTION enforce_substrate_events_append_only();
                """
                    )
                )
                await db.commit()

    @pytest.mark.asyncio
    async def test_update_rejected_by_trigger(self):
        """An UPDATE on substrate_events raises a database error."""
        run_id = str(uuid4())
        event_id = str(uuid4())

        async with AsyncSessionLocal() as db:
            # Insert a row
            event = SubstrateEvent(
                id=event_id,
                sequence=1,
                run_id=run_id,
                type="test.update_check",
                payload={"note": "will try to update"},
                actor="test",
            )
            db.add(event)
            await db.commit()

            # Attempt UPDATE — should be rejected by trigger
            update_rejected = False
            try:
                await db.execute(
                    text(
                        "UPDATE substrate_events SET type = 'test.modified' WHERE id = :eid"
                    ),
                    {"eid": event_id},
                )
                await db.commit()
            except Exception as exc:
                update_rejected = True
                await db.rollback()
                error_msg = str(exc).lower()
                assert (
                    "append-only" in error_msg
                    or "forbidden" in error_msg
                    or "update" in error_msg
                ), f"Unexpected error: {exc}"

            assert (
                update_rejected
            ), "UPDATE should have been rejected by append-only trigger"

            # Cleanup: drop trigger, delete row, recreate trigger
            await db.execute(
                text(
                    "DROP TRIGGER IF EXISTS trg_substrate_events_append_only ON substrate_events"
                )
            )
            await db.execute(
                text("DELETE FROM substrate_events WHERE id = :eid"),
                {"eid": event_id},
            )
            await db.execute(
                text(
                    """
                CREATE TRIGGER trg_substrate_events_append_only
                BEFORE UPDATE OR DELETE ON substrate_events
                FOR EACH STATEMENT
                EXECUTE FUNCTION enforce_substrate_events_append_only();
            """
                )
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_delete_rejected_by_trigger(self):
        """A DELETE on substrate_events raises a database error."""
        run_id = str(uuid4())
        event_id = str(uuid4())

        async with AsyncSessionLocal() as db:
            # Insert a row
            event = SubstrateEvent(
                id=event_id,
                sequence=1,
                run_id=run_id,
                type="test.delete_check",
                payload={"note": "will try to delete"},
                actor="test",
            )
            db.add(event)
            await db.commit()

            try:
                # Attempt DELETE — should be rejected by trigger
                await db.execute(
                    text("DELETE FROM substrate_events WHERE id = :eid"),
                    {"eid": event_id},
                )
                await db.commit()
                pytest.fail("DELETE should have been rejected by append-only trigger")
            except Exception as exc:
                await db.rollback()
                error_msg = str(exc).lower()
                assert (
                    "append-only" in error_msg
                    or "forbidden" in error_msg
                    or "delete" in error_msg
                ), f"Unexpected error: {exc}"

            finally:
                # Cleanup
                await db.execute(
                    text(
                        "DROP TRIGGER IF EXISTS trg_substrate_events_append_only ON substrate_events"
                    )
                )
                await db.execute(
                    text("DELETE FROM substrate_events WHERE id = :eid"),
                    {"eid": event_id},
                )
                await db.execute(
                    text(
                        """
                    CREATE TRIGGER trg_substrate_events_append_only
                    BEFORE UPDATE OR DELETE ON substrate_events
                    FOR EACH STATEMENT
                    EXECUTE FUNCTION enforce_substrate_events_append_only();
                """
                    )
                )
                await db.commit()

    @pytest.mark.asyncio
    async def test_trigger_exists_in_database(self):
        """Verify the trigger exists in the PostgreSQL catalog."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text(
                    """
                SELECT tgname FROM pg_trigger
                WHERE tgname = 'trg_substrate_events_append_only'
            """
                )
            )
            rows = result.fetchall()
            assert (
                len(rows) > 0
            ), "Append-only trigger not found in database. Run the H2 substrate migration first."

    @pytest.mark.asyncio
    async def test_trigger_catalog_matches_migration(self):
        """Query pg_trigger catalog with joins to verify the trigger's full
        definition matches the H2 migration:
        - Trigger name: trg_substrate_events_append_only
        - Table: substrate_events
        - Function: enforce_substrate_events_append_only()
        - Fires: BEFORE UPDATE OR DELETE
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text(
                    """
                SELECT
                    t.tgname          AS trigger_name,
                    c.relname         AS table_name,
                    p.proname         AS function_name,
                    t.tgtype::int     AS tgtype
                FROM pg_trigger t
                JOIN pg_class c ON t.tgrelid = c.oid
                JOIN pg_proc  p ON t.tgfoid  = p.oid
                WHERE t.tgname = 'trg_substrate_events_append_only'
                  AND NOT t.tgisinternal
            """
                )
            )
            rows = result.fetchall()

            assert (
                len(rows) == 1
            ), f"Expected exactly 1 trigger row, got {len(rows)}. Run the H2 substrate migration first."

            trigger_name, table_name, function_name, tgtype = rows[0]

            assert (
                trigger_name == "trg_substrate_events_append_only"
            ), f"Trigger name mismatch: {trigger_name}"
            assert (
                table_name == "substrate_events"
            ), f"Table name mismatch: expected 'substrate_events', got '{table_name}'"
            assert (
                function_name == "enforce_substrate_events_append_only"
            ), f"Function name mismatch: {function_name}"

            # tgtype bits (from pg_trigger.h):
            #   BEFORE  = 1 << 1  = 2
            #   UPDATE  = 1 << 3  = 8
            #   DELETE  = 1 << 4  = 16
            #   TRIGGER_TYPE_ROW = 1 << 0 = 1 (absent for statement-level)
            BEFORE_BIT = 2
            UPDATE_BIT = 8
            DELETE_BIT = 16
            INSERT_BIT = 4
            ROW_BIT = 1

            assert (
                tgtype & BEFORE_BIT
            ), f"Trigger fires BEFORE: bit 1 not set (tgtype={tgtype})"
            assert (
                tgtype & UPDATE_BIT
            ), f"Trigger fires on UPDATE: bit 3 not set (tgtype={tgtype})"
            assert (
                tgtype & DELETE_BIT
            ), f"Trigger fires on DELETE: bit 4 not set (tgtype={tgtype})"
            assert not (
                tgtype & INSERT_BIT
            ), f"Trigger should NOT fire on INSERT (bit 2 is set), tgtype={tgtype}"
            assert not (
                tgtype & ROW_BIT
            ), f"Trigger is STATEMENT-level (row bit 0 should be absent), got tgtype={tgtype}"
