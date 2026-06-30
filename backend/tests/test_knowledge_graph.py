"""
End-to-end tests for KnowledgeGraph persistence.

Verifies that nodes and edges are correctly persisted to PostgreSQL
and can be reloaded into a fresh KnowledgeGraph instance.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.improvement.causal_decomposer import StrategyType
from app.services.improvement.failure_types import FailureType
from app.services.improvement.knowledge_graph import (
    EdgeType,
    KnowledgeGraph,
    NodeType,
)

pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


# ── helpers ────────────────────────────────────────────────────────────


async def _make_session():
    """Create a fresh async DB session and clean the knowledge graph tables."""
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()
    await session.execute(text("DELETE FROM improvement_knowledge_edges"))
    await session.execute(text("DELETE FROM improvement_knowledge_nodes"))
    await session.commit()
    return session, engine


async def _cleanup(session, engine):
    await session.execute(text("DELETE FROM improvement_knowledge_edges"))
    await session.execute(text("DELETE FROM improvement_knowledge_nodes"))
    await session.commit()
    await session.close()
    await engine.dispose()


async def _count(session, table: str) -> int:
    result = await session.execute(text(f"SELECT count(*) FROM {table}"))
    return result.scalar() or 0


# ── persistence tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_persist_single_node_and_reload():
    """Add a node with db_session attached → reload → verify."""
    session, engine = await _make_session()
    try:
        kg = KnowledgeGraph(db_session=session)
        node_a = await kg.add_node(
            NodeType.FAILURE,
            FailureType.TOOL_TIMEOUT.value,
            properties={"severity": "high", "count": 5},
        )

        assert await _count(session, "improvement_knowledge_nodes") == 1

        kg2 = KnowledgeGraph(db_session=session)
        await kg2.load_from_database()

        reloaded = kg2.get_node(node_a.id)
        assert reloaded is not None
        assert reloaded.node_type == NodeType.FAILURE
        assert reloaded.node_key == FailureType.TOOL_TIMEOUT.value
        assert reloaded.id == node_a.id
        assert reloaded.properties["severity"] == "high"
        assert reloaded.properties["count"] == 5
    finally:
        await _cleanup(session, engine)


@pytest.mark.asyncio
async def test_persist_node_with_edge_and_reload():
    """Add two nodes + an edge → verify both nodes and edge reload correctly."""
    session, engine = await _make_session()
    try:
        kg = KnowledgeGraph(db_session=session)

        failure = await kg.add_node(
            NodeType.FAILURE,
            FailureType.TOOL_TIMEOUT.value,
            properties={"agent": "worker-1"},
        )
        strategy = await kg.add_node(
            NodeType.STRATEGY,
            StrategyType.ADD_RETRY.value,
            properties={"max_retries": 3},
        )
        edge = await kg.add_edge(
            failure.id,
            strategy.id,
            EdgeType.FIXES,
            weight=2.5,
            properties={"success_rate": 0.85, "total": 10, "successes": 8},
        )

        assert edge is not None
        assert await _count(session, "improvement_knowledge_nodes") == 2
        assert await _count(session, "improvement_knowledge_edges") == 1

        kg2 = KnowledgeGraph(db_session=session)
        await kg2.load_from_database()

        assert len(kg2._nodes) == 2
        assert len(kg2._edges) == 1

        reloaded_failure = kg2.get_node(failure.id)
        assert reloaded_failure is not None
        assert reloaded_failure.node_key == FailureType.TOOL_TIMEOUT.value

        reloaded_strategy = kg2.get_node(strategy.id)
        assert reloaded_strategy is not None
        assert reloaded_strategy.node_key == StrategyType.ADD_RETRY.value
        assert reloaded_strategy.properties["max_retries"] == 3

        reloaded_edge = kg2.get_edge(edge.id)
        assert reloaded_edge is not None
        assert reloaded_edge.edge_type == EdgeType.FIXES
        assert reloaded_edge.weight == 2.5
        assert reloaded_edge.source_id == failure.id
        assert reloaded_edge.target_id == strategy.id
        assert reloaded_edge.properties["success_rate"] == 0.85
    finally:
        await _cleanup(session, engine)


@pytest.mark.asyncio
async def test_save_to_database_bulk_persists_all():
    """save_to_database() persists every in-memory node and edge."""
    session, engine = await _make_session()
    try:
        kg = KnowledgeGraph(db_session=None)

        n1 = await kg.add_node(NodeType.FAILURE, "NETWORK_ERROR")
        n2 = await kg.add_node(NodeType.STRATEGY, "RETRY_WITH_BACKOFF")
        n3 = await kg.add_node(NodeType.PATTERN, "INTERMITTENT_FAILURE")
        await kg.add_edge(n1.id, n2.id, EdgeType.FIXES, weight=1.0)
        await kg.add_edge(n2.id, n3.id, EdgeType.CORRELATES_WITH, weight=0.5)

        assert await _count(session, "improvement_knowledge_nodes") == 0

        kg.db_session = session
        await kg.save_to_database()

        assert await _count(session, "improvement_knowledge_nodes") == 3
        assert await _count(session, "improvement_knowledge_edges") == 2

        kg2 = KnowledgeGraph(db_session=session)
        await kg2.load_from_database()

        assert len(kg2._nodes) == 3
        assert len(kg2._edges) == 2
        assert kg2.get_node_by_key(NodeType.FAILURE, "NETWORK_ERROR") is not None
        assert kg2.get_node_by_key(NodeType.PATTERN, "INTERMITTENT_FAILURE") is not None
    finally:
        await _cleanup(session, engine)


@pytest.mark.asyncio
async def test_update_node_persists_changes():
    """Updating a node's properties persists to DB and is visible on reload."""
    session, engine = await _make_session()
    try:
        kg = KnowledgeGraph(db_session=session)
        node = await kg.add_node(
            NodeType.STRATEGY,
            "CIRCUIT_BREAKER",
            properties={"threshold": 5},
        )

        await kg.update_node(node.id, {"threshold": 10, "cooldown_seconds": 30})

        kg2 = KnowledgeGraph(db_session=session)
        await kg2.load_from_database()

        reloaded = kg2.get_node(node.id)
        assert reloaded is not None
        assert reloaded.properties["threshold"] == 10
        assert reloaded.properties["cooldown_seconds"] == 30
    finally:
        await _cleanup(session, engine)


@pytest.mark.asyncio
async def test_duplicate_edge_averages_weight():
    """Adding the same edge twice averages the weight on the existing edge."""
    session, engine = await _make_session()
    try:
        kg = KnowledgeGraph(db_session=session)

        n1 = await kg.add_node(NodeType.FAILURE, "DUPLICATE_TEST_A")
        n2 = await kg.add_node(NodeType.STRATEGY, "DUPLICATE_TEST_B")

        e1 = await kg.add_edge(n1.id, n2.id, EdgeType.FIXES, weight=4.0, properties={"extra": "yes"})
        assert e1 is not None

        e2 = await kg.add_edge(n1.id, n2.id, EdgeType.FIXES, weight=8.0)
        assert e2 is not None
        assert e2.id == e1.id
        assert e2.weight == 6.0
        assert e2.properties.get("extra") == "yes"

        assert await _count(session, "improvement_knowledge_edges") == 1

        kg2 = KnowledgeGraph(db_session=session)
        await kg2.load_from_database()
        assert len(kg2._edges) == 1
        reloaded = kg2.get_edge(e2.id)
        assert reloaded is not None
        assert reloaded.weight == 6.0
    finally:
        await _cleanup(session, engine)


@pytest.mark.asyncio
async def test_get_node_by_key_after_reload():
    """get_node_by_key() works correctly after loading from DB."""
    session, engine = await _make_session()
    try:
        kg = KnowledgeGraph(db_session=session)
        await kg.add_node(NodeType.FAILURE, "RATE_LIMIT")
        await kg.add_node(NodeType.STRATEGY, "EXPONENTIAL_BACKOFF")

        kg2 = KnowledgeGraph(db_session=session)
        await kg2.load_from_database()

        assert kg2.get_node_by_key(NodeType.FAILURE, "RATE_LIMIT") is not None
        assert kg2.get_node_by_key(NodeType.STRATEGY, "EXPONENTIAL_BACKOFF") is not None
        assert kg2.get_node_by_key(NodeType.FAILURE, "NONEXISTENT") is None
    finally:
        await _cleanup(session, engine)


@pytest.mark.asyncio
async def test_statistics_reflect_loaded_graph():
    """get_statistics() returns correct counts after reload from DB."""
    session, engine = await _make_session()
    try:
        kg = KnowledgeGraph(db_session=session)

        await kg.add_node(NodeType.FAILURE, "F1")
        await kg.add_node(NodeType.FAILURE, "F2")
        await kg.add_node(NodeType.STRATEGY, "S1")
        await kg.add_node(NodeType.PATTERN, "P1")

        assert kg.get_statistics()["total_nodes"] == 4

        kg2 = KnowledgeGraph(db_session=session)
        await kg2.load_from_database()

        stats = kg2.get_statistics()
        assert stats["total_nodes"] == 4
        assert stats["nodes_by_type"]["failure"] == 2
        assert stats["nodes_by_type"]["strategy"] == 1
        assert stats["nodes_by_type"]["pattern"] == 1
    finally:
        await _cleanup(session, engine)


@pytest.mark.asyncio
async def test_delete_node_removes_edges():
    """Deleting a node removes its connected edges from both memory and DB."""
    session, engine = await _make_session()
    try:
        kg = KnowledgeGraph(db_session=session)

        n1 = await kg.add_node(NodeType.FAILURE, "DEL_TEST_A")
        n2 = await kg.add_node(NodeType.STRATEGY, "DEL_TEST_B")
        edge = await kg.add_edge(n1.id, n2.id, EdgeType.FIXES, weight=1.0)

        assert len(kg._nodes) == 2
        assert len(kg._edges) == 1

        await kg.delete_node(n1.id)

        assert len(kg._nodes) == 1
        assert len(kg._edges) == 0
        assert kg.get_node(n1.id) is None
        assert kg.get_edge(edge.id) is None

        kg2 = KnowledgeGraph(db_session=session)
        await kg2.load_from_database()

        assert len(kg2._nodes) == 1
        assert len(kg2._edges) == 0
        assert kg2.get_node(n2.id) is not None
    finally:
        await _cleanup(session, engine)


@pytest.mark.asyncio
async def test_no_db_session_skips_persistence():
    """Without a db_session, operations work in-memory only and don't crash."""
    kg = KnowledgeGraph(db_session=None)

    node = await kg.add_node(NodeType.FAILURE, "IN_MEMORY_ONLY", properties={"note": "should not persist"})
    await kg.add_edge(node.id, node.id, EdgeType.SIMILAR_TO, weight=0.5)

    assert len(kg._nodes) == 1
    assert len(kg._edges) == 1

    await kg.save_to_database()
    await kg.load_from_database()
