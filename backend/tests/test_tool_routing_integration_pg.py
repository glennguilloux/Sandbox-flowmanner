"""Integration tests for tool routing audit table — Q2-Q3 Chunk 3.

Tests the tool_routing_decisions audit log table (insert, query, index hit).
Marked with @pytest.mark.integration so the canonical baseline can skip them.
Only runs when PostgreSQL is reachable in the test environment.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

# Skip entire module if PG is not available
pytestmark = pytest.mark.integration


@pytest.fixture
def _require_pg():
    """Skip if PostgreSQL is not reachable."""
    try:
        import asyncio

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.config import settings

        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

        async def _check():
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()

        asyncio.run(_check())
    except Exception:
        pytest.skip("PostgreSQL not reachable in test environment")


@pytest.mark.usefixtures("_require_pg")
class TestToolRoutingAuditTable:
    """Integration tests for the tool_routing_decisions table."""

    def test_table_exists(self):
        """Verify the tool_routing_decisions table was created by migration."""
        import asyncio

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.config import settings

        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

        async def _check():
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT EXISTS ("
                        "  SELECT FROM information_schema.tables "
                        "  WHERE table_name = 'tool_routing_decisions'"
                        ")"
                    )
                )
                exists = result.scalar()
                return exists

        exists = asyncio.run(_check())
        asyncio.run(engine.dispose())
        assert exists, "tool_routing_decisions table should exist after migration"

    def test_insert_and_query_routing_decision(self):
        """Verify insert and query of a routing decision row."""
        import asyncio

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.config import settings

        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

        async def _test():
            ws_id = str(uuid4())
            mission_id = str(uuid4())

            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        INSERT INTO tool_routing_decisions
                            (id, workspace_id, user_id, mission_id, task_text_hash,
                             mode, top_score, candidates_considered, candidates_returned,
                             selected_tool_ids, created_at)
                        VALUES
                            (:id, :ws, :uid, :mid, :hash,
                             :mode, :score, :considered, :returned,
                             :tools, now())
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "ws": ws_id,
                        "uid": 42,
                        "mid": mission_id,
                        "hash": "abc123def456",
                        "mode": "sparse",
                        "score": 0.85,
                        "considered": 10,
                        "returned": 3,
                        "tools": '["tool_a", "tool_b", "tool_c"]',
                    },
                )

            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT mode, top_score, candidates_returned "
                        "FROM tool_routing_decisions "
                        "WHERE workspace_id = :ws AND user_id = :uid"
                    ),
                    {"ws": ws_id, "uid": 42},
                )
                row = result.fetchone()
                assert row is not None
                assert row[0] == "sparse"
                assert row[1] == pytest.approx(0.85)
                assert row[2] == 3

            # Cleanup
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM tool_routing_decisions WHERE workspace_id = :ws"),
                    {"ws": ws_id},
                )
            await engine.dispose()

        asyncio.run(_test())

    def test_mission_id_partial_index_exists(self):
        """Verify the partial index on mission_id exists."""
        import asyncio

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.config import settings

        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

        async def _check():
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT EXISTS ("
                        "  SELECT 1 FROM pg_indexes "
                        "  WHERE indexname = 'ix_tool_routing_mission'"
                        ")"
                    )
                )
                return result.scalar()

        exists = asyncio.run(_check())
        asyncio.run(engine.dispose())
        assert exists, "ix_tool_routing_mission partial index should exist"
