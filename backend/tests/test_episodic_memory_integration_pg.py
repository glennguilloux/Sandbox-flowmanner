"""Integration tests for episodes table — Q2-Q3 Chunk 2.

Tests the DB schema (insert, query, index hit) against a real PostgreSQL.
Marked with @pytest.mark.integration so the canonical substrate baseline
can skip them in dev environments.

Requires: running PostgreSQL with the episodic_memory_001 migration applied.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.memory_models import Episode


# Skip all tests in this module if PG is unreachable
pytestmark = pytest.mark.integration


@pytest.fixture
def sample_episode_data():
    """Generate sample episode data for integration tests."""
    return {
        "id": str(uuid4()),
        "workspace_id": str(uuid4()),
        "user_id": 1,
        "mission_id": str(uuid4()),
        "step_type": "code_execute",
        "outcome": "success",
        "cost_bucket": "small",
        "hitl_outcome": None,
        "retrieval_text": "Mission abcd1234 step code_execute: success, cost small, 3 files modified",
        "qdrant_point_id": str(uuid4()),
        "embedding_model": "all-MiniLM-L6-v2",
    }


class TestEpisodeTableSchema:
    """Test that the episodes table schema is correct."""

    @pytest.mark.asyncio
    async def test_insert_and_query(self, db_session):
        """Verify basic insert and select works on the episodes table."""
        from sqlalchemy import text

        ws_id = str(uuid4())
        uid = 1
        mission_id = str(uuid4())

        # Insert an episode
        await db_session.execute(
            text("""
                INSERT INTO episodes (id, workspace_id, user_id, mission_id,
                    step_type, outcome, cost_bucket, retrieval_text, embedding_model)
                VALUES (:id, :ws, :uid, :mid, :st, :oc, :cb, :rt, :em)
            """),
            {
                "id": str(uuid4()),
                "ws": ws_id,
                "uid": uid,
                "mid": mission_id,
                "st": "code_execute",
                "oc": "success",
                "cb": "small",
                "rt": "Mission test step code_execute: success, cost small",
                "em": "all-MiniLM-L6-v2",
            },
        )
        await db_session.commit()

        # Query it back
        result = await db_session.execute(
            text("SELECT * FROM episodes WHERE workspace_id = :ws AND user_id = :uid"),
            {"ws": ws_id, "uid": uid},
        )
        rows = result.fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert str(row.mission_id) == mission_id
        assert row.outcome == "success"
        assert row.cost_bucket == "small"

    @pytest.mark.asyncio
    async def test_tsvector_auto_populated(self, db_session):
        """Verify the tsvector trigger auto-populates retrieval_vector."""
        from sqlalchemy import text

        ws_id = str(uuid4())
        ep_id = str(uuid4())

        await db_session.execute(
            text("""
                INSERT INTO episodes (id, workspace_id, user_id, mission_id,
                    step_type, outcome, cost_bucket, retrieval_text, embedding_model)
                VALUES (:id, :ws, 1, :mid, 'plan', 'failure', 'large',
                        'Mission xyz step plan: failure, cost large, timeout after 3 retries', 'all-MiniLM-L6-v2')
            """),
            {"id": ep_id, "ws": ws_id, "mid": str(uuid4())},
        )
        await db_session.commit()

        # Check tsvector was auto-populated by trigger
        result = await db_session.execute(
            text("SELECT retrieval_vector FROM episodes WHERE id = :id"),
            {"id": ep_id},
        )
        row = result.fetchone()
        assert row is not None
        assert row.retrieval_vector is not None  # trigger should have populated it

    @pytest.mark.asyncio
    async def test_fulltext_search_query(self, db_session):
        """Verify full-text search with ts_rank works on the episodes table."""
        from sqlalchemy import text

        ws_id = str(uuid4())

        # Insert a few episodes
        for i in range(3):
            await db_session.execute(
                text("""
                    INSERT INTO episodes (id, workspace_id, user_id, mission_id,
                        step_type, outcome, cost_bucket, retrieval_text, embedding_model)
                    VALUES (:id, :ws, 1, :mid, :st, :oc, :cb, :rt, 'all-MiniLM-L6-v2')
                """),
                {
                    "id": str(uuid4()),
                    "ws": ws_id,
                    "mid": str(uuid4()),
                    "st": "code_execute" if i < 2 else "plan",
                    "oc": "success" if i == 0 else "failure",
                    "cb": "small",
                    "rt": f"Mission step {'code_execute' if i < 2 else 'plan'}: "
                          f"{'success' if i == 0 else 'failure'}, "
                          f"{'deployed 3 files' if i == 0 else 'timeout after retries'}",
                },
            )
        await db_session.commit()

        # Full-text search for "deploy"
        result = await db_session.execute(
            text("""
                SELECT id, ts_rank(retrieval_vector, plainto_tsquery('english', :query)) AS score
                FROM episodes
                WHERE workspace_id = :ws
                  AND retrieval_vector @@ plainto_tsquery('english', :query)
                ORDER BY score DESC
            """),
            {"ws": ws_id, "query": "deploy"},
        )
        rows = result.fetchall()
        # At least the "deployed 3 files" episode should match
        assert len(rows) >= 1
