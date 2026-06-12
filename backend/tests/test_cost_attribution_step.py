"""Tests for per-step cost attribution (Q1-B Chunk 4).

Covers:
- CostCategory enum values
- CostEvent dataclass defaults
- CostTracker.record_cost_event()
- CostAttributionEngine.step_cost() and cost_by_category()
- API: GET /costs/mission/{id}/steps
- API: GET /costs/by-category
- NodeExecutor._emit_cost_event()
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.models.cost_event import CostCategory, CostEvent

# ── Test 1: CostCategory enum has 6 values ──────────────────────────

def test_cost_category_enum_has_6_values():
    """All 6 cost categories are defined."""
    assert len(CostCategory) == 6
    assert CostCategory.LLM_TOKENS.value == "llm_tokens"
    assert CostCategory.TOOL_EXECUTION.value == "tool_execution"
    assert CostCategory.EMBEDDING.value == "embedding"
    assert CostCategory.EXTERNAL_API.value == "external_api"
    assert CostCategory.STORAGE.value == "storage"
    assert CostCategory.BROWSER.value == "browser"


# ── Test 2: CostCategory is str enum ────────────────────────────────

def test_cost_category_is_str_enum():
    """CostCategory can be used as a string directly."""
    cat = CostCategory.LLM_TOKENS
    assert cat == "llm_tokens"
    assert isinstance(cat, str)


# ── Test 3: CostEvent dataclass defaults ────────────────────────────

def test_cost_event_defaults():
    """CostEvent has sensible defaults for all optional fields."""
    event = CostEvent(category=CostCategory.TOOL_EXECUTION, cost_usd=0.05)
    assert event.category == CostCategory.TOOL_EXECUTION
    assert event.cost_usd == 0.05
    assert event.mission_id == ""
    assert event.node_id == ""
    assert event.run_id == ""
    assert event.provider == "unknown"
    assert event.model_id == ""
    assert event.tool_name is None
    assert event.embedding_tokens == 0
    assert event.input_tokens == 0
    assert event.output_tokens == 0
    assert event.latency_ms == 0
    assert event.workspace_id == ""
    assert event.agent_id == ""
    assert event.timestamp is not None


# ── Test 4: CostEvent full construction ─────────────────────────────

def test_cost_event_full_construction():
    """CostEvent can be constructed with all fields populated."""
    ts = datetime(2026, 6, 20, tzinfo=UTC)
    event = CostEvent(
        category=CostCategory.EMBEDDING,
        cost_usd=0.003,
        mission_id="m-1",
        node_id="n-1",
        run_id="r-1",
        provider="qdrant",
        model_id="text-embedding-3-small",
        tool_name="rag_search",
        embedding_tokens=1500,
        input_tokens=0,
        output_tokens=0,
        latency_ms=120,
        workspace_id="ws-1",
        agent_id="agent-1",
        timestamp=ts,
    )
    assert event.embedding_tokens == 1500
    assert event.provider == "qdrant"
    assert event.tool_name == "rag_search"
    assert event.timestamp == ts


# ── Test 5: CostTracker.record_cost_event writes to DB ──────────────

@pytest.mark.anyio
async def test_cost_tracker_record_cost_event_writes_to_db():
    """record_cost_event adds an LLMCallRecord with cost_category."""
    from app.services.cost_tracker import CostTracker

    tracker = CostTracker()
    mock_db = MagicMock()
    mock_db.add = MagicMock()

    event = CostEvent(
        category=CostCategory.TOOL_EXECUTION,
        cost_usd=0.02,
        mission_id="m-1",
        node_id="n-1",
        run_id="r-1",
        provider="tool_execution",
        model_id="code_executor",
        tool_name="code_executor",
        latency_ms=500,
    )

    with patch("app.services.cost_tracker.record_llm_request"):
        await tracker.record_cost_event(mock_db, event)

    mock_db.add.assert_called_once()
    record = mock_db.add.call_args[0][0]
    assert record.cost_category == "tool_execution"
    assert record.cost_usd == 0.02
    assert record.tool_name == "code_executor"
    assert record.mission_id == "m-1"
    assert record.task_id == "n-1"


# ── Test 6: CostTracker.record_cost_event with embedding category ───

@pytest.mark.anyio
async def test_cost_tracker_record_cost_event_embedding():
    """record_cost_event handles embedding category with embedding_tokens."""
    from app.services.cost_tracker import CostTracker

    tracker = CostTracker()
    mock_db = MagicMock()
    mock_db.add = MagicMock()

    event = CostEvent(
        category=CostCategory.EMBEDDING,
        cost_usd=0.001,
        mission_id="m-2",
        node_id="n-2",
        run_id="r-2",
        provider="qdrant",
        model_id="text-embedding-3-small",
        embedding_tokens=2000,
    )

    with patch("app.services.cost_tracker.record_llm_request"):
        await tracker.record_cost_event(mock_db, event)

    record = mock_db.add.call_args[0][0]
    assert record.cost_category == "embedding"
    assert record.embedding_tokens == 2000


# ── Test 7: CostTracker.record_cost_event with None db ──────────────

@pytest.mark.anyio
async def test_cost_tracker_record_cost_event_no_db():
    """record_cost_event with db=None skips DB write but still records Prometheus."""
    from app.services.cost_tracker import CostTracker

    tracker = CostTracker()
    event = CostEvent(
        category=CostCategory.TOOL_EXECUTION,
        cost_usd=0.01,
    )

    # Should not raise
    with patch("app.services.cost_tracker.record_llm_request") as mock_prom:
        await tracker.record_cost_event(None, event)

    mock_prom.assert_called_once()


# ── Test 8: CostAttributionEngine.step_cost query ───────────────────

@pytest.mark.anyio
async def test_engine_step_cost_returns_grouped_results():
    """step_cost returns costs grouped by node_id and cost_category."""
    from app.observability.cost_engine import CostAttributionEngine

    engine = CostAttributionEngine()

    # Mock DB session
    mock_row_1 = MagicMock()
    mock_row_1.node_id = "node-1"
    mock_row_1.cost_category = "llm_tokens"
    mock_row_1.calls = 3
    mock_row_1.cost_usd = 0.15
    mock_row_1.prompt_tokens = 5000
    mock_row_1.completion_tokens = 2000
    mock_row_1.embedding_tokens = 0

    mock_row_2 = MagicMock()
    mock_row_2.node_id = "node-1"
    mock_row_2.cost_category = "tool_execution"
    mock_row_2.calls = 1
    mock_row_2.cost_usd = 0.02
    mock_row_2.prompt_tokens = 0
    mock_row_2.completion_tokens = 0
    mock_row_2.embedding_tokens = 0

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row_1, mock_row_2]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    steps = await engine.step_cost(mock_db, mission_id="m-1")

    assert len(steps) == 2
    assert steps[0]["node_id"] == "node-1"
    assert steps[0]["cost_category"] == "llm_tokens"
    assert steps[0]["cost_usd"] == 0.15
    assert steps[1]["cost_category"] == "tool_execution"
    assert steps[1]["cost_usd"] == 0.02


# ── Test 9: CostAttributionEngine.step_cost with node_id filter ─────

@pytest.mark.anyio
async def test_engine_step_cost_filters_by_node_id():
    """step_cost with node_id filters to a specific node."""
    from app.observability.cost_engine import CostAttributionEngine

    engine = CostAttributionEngine()

    mock_result = MagicMock()
    mock_result.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    steps = await engine.step_cost(mock_db, mission_id="m-1", node_id="n-1")

    assert steps == []
    # Verify the query was executed (call happened)
    mock_db.execute.assert_called_once()


# ── Test 10: CostAttributionEngine.cost_by_category ─────────────────

@pytest.mark.anyio
async def test_engine_cost_by_category_returns_breakdown():
    """cost_by_category returns costs grouped by cost_category."""
    from app.observability.cost_engine import CostAttributionEngine

    engine = CostAttributionEngine()

    mock_row_llm = MagicMock()
    mock_row_llm.cost_category = "llm_tokens"
    mock_row_llm.calls = 10
    mock_row_llm.cost_usd = 1.50

    mock_row_tool = MagicMock()
    mock_row_tool.cost_category = "tool_execution"
    mock_row_tool.calls = 5
    mock_row_tool.cost_usd = 0.25

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row_llm, mock_row_tool]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    categories = await engine.cost_by_category(mock_db, mission_id="m-1", days=30)

    assert len(categories) == 2
    assert categories[0]["cost_category"] == "llm_tokens"
    assert categories[0]["cost_usd"] == 1.50
    assert categories[1]["cost_category"] == "tool_execution"


# ── Test 11: API GET /costs/mission/{id}/steps ──────────────────────

@pytest.mark.anyio
async def test_api_mission_step_costs():
    """GET /costs/mission/{id}/steps returns per-step breakdown."""
    from app.api.v1.cost_attribution import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    fake_user = MagicMock(id=1, is_active=True)

    async def _fake_user():
        return fake_user

    async def _fake_db():
        return AsyncMock()

    async def _fake_workspace():
        return None

    from app.api.deps import get_current_user, get_workspace_id
    from app.database import get_db

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_workspace_id] = _fake_workspace
    app.dependency_overrides[get_db] = _fake_db

    mock_steps = [
        {"node_id": "n-1", "cost_category": "llm_tokens", "calls": 3, "cost_usd": 0.15,
         "prompt_tokens": 5000, "completion_tokens": 2000, "embedding_tokens": 0},
        {"node_id": "n-1", "cost_category": "tool_execution", "calls": 1, "cost_usd": 0.02,
         "prompt_tokens": 0, "completion_tokens": 0, "embedding_tokens": 0},
    ]

    with patch("app.observability.cost_engine.get_cost_engine") as mock_get_engine:
        mock_engine = MagicMock()
        mock_engine.step_cost = AsyncMock(return_value=mock_steps)
        mock_get_engine.return_value = mock_engine

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/costs/mission/m-1/steps")

    assert resp.status_code == 200
    data = resp.json()
    assert data["mission_id"] == "m-1"
    assert len(data["steps"]) == 2
    assert data["steps"][0]["cost_category"] == "llm_tokens"

    app.dependency_overrides.clear()


# ── Test 12: API GET /costs/by-category ─────────────────────────────

@pytest.mark.anyio
async def test_api_costs_by_category():
    """GET /costs/by-category returns category breakdown."""
    from app.api.v1.cost_attribution import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    fake_user = MagicMock(id=1, is_active=True)
    fake_ws = "ws-123"

    async def _fake_user():
        return fake_user

    async def _fake_db():
        return AsyncMock()

    async def _fake_workspace():
        return fake_ws

    from app.api.deps import get_current_user, get_workspace_id
    from app.database import get_db

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_workspace_id] = _fake_workspace
    app.dependency_overrides[get_db] = _fake_db

    mock_categories = [
        {"cost_category": "llm_tokens", "calls": 20, "cost_usd": 3.00},
        {"cost_category": "tool_execution", "calls": 8, "cost_usd": 0.50},
        {"cost_category": "embedding", "calls": 15, "cost_usd": 0.10},
    ]

    with patch("app.observability.cost_engine.get_cost_engine") as mock_get_engine:
        mock_engine = MagicMock()
        mock_engine.cost_by_category = AsyncMock(return_value=mock_categories)
        mock_get_engine.return_value = mock_engine

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/costs/by-category?days=7")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["categories"]) == 3
    assert data["categories"][0]["cost_category"] == "llm_tokens"
    assert data["categories"][2]["cost_category"] == "embedding"

    # Verify engine was called with workspace_id
    mock_engine.cost_by_category.assert_called_once()
    call = mock_engine.cost_by_category.call_args
    assert call.kwargs["workspace_id"] == fake_ws
    assert call.kwargs["days"] == 7

    app.dependency_overrides.clear()


# ── Test 13: NodeExecutor._emit_cost_event ──────────────────────────

@pytest.mark.anyio
async def test_node_executor_emit_cost_event():
    """_emit_cost_event creates a CostEvent and records it via tracker."""
    from app.services.substrate.node_executor import NodeExecutor

    mock_executor = MagicMock()
    node_exec = NodeExecutor(mock_executor)

    mock_node = MagicMock()
    mock_node.id = "node-1"
    mock_node.config = {"tool_name": "web_search"}

    mock_workflow = MagicMock()
    mock_workflow.id = "mission-1"
    mock_workflow.workspace_id = "ws-1"
    mock_workflow.user_id = "user-1"

    result = {"success": True, "output": {}, "cost": 0.05, "latency_ms": 200}

    with patch("app.services.cost_tracker.get_cost_tracker") as mock_get_tracker:
        mock_tracker = MagicMock()
        mock_tracker.record_cost_event = AsyncMock()
        mock_get_tracker.return_value = mock_tracker

        await node_exec._emit_cost_event(
            db=AsyncMock(),
            node=mock_node,
            result=result,
            category="tool_execution",
            run_id="run-1",
            workflow=mock_workflow,
            tool_name="web_search",
        )

    mock_tracker.record_cost_event.assert_called_once()
    call_args = mock_tracker.record_cost_event.call_args
    event = call_args[0][1]  # second positional arg
    assert event.category == CostCategory.TOOL_EXECUTION
    assert event.cost_usd == 0.05
    assert event.mission_id == "mission-1"
    assert event.node_id == "node-1"
    assert event.tool_name == "web_search"


# ── Test 14: _emit_cost_event with embedding category ───────────────

@pytest.mark.anyio
async def test_node_executor_emit_cost_event_embedding():
    """_emit_cost_event handles embedding category with embedding_tokens."""
    from app.services.substrate.node_executor import NodeExecutor

    mock_executor = MagicMock()
    node_exec = NodeExecutor(mock_executor)

    mock_node = MagicMock()
    mock_node.id = "node-2"
    mock_node.config = {"tool_name": "rag_search"}

    result = {"success": True, "output": {}, "cost": 0.003}

    with patch("app.services.cost_tracker.get_cost_tracker") as mock_get_tracker:
        mock_tracker = MagicMock()
        mock_tracker.record_cost_event = AsyncMock()
        mock_get_tracker.return_value = mock_tracker

        await node_exec._emit_cost_event(
            db=AsyncMock(),
            node=mock_node,
            result=result,
            category="embedding",
            run_id="run-1",
            workflow=None,
            tool_name="rag_search",
            embedding_tokens=1500,
        )

    event = mock_tracker.record_cost_event.call_args[0][1]
    assert event.category == CostCategory.EMBEDDING
    assert event.embedding_tokens == 1500


# ── Test 15: _emit_cost_event is fire-and-forget ────────────────────

@pytest.mark.anyio
async def test_node_executor_emit_cost_event_fire_and_forget():
    """_emit_cost_event swallows exceptions and never blocks execution."""
    from app.services.substrate.node_executor import NodeExecutor

    mock_executor = MagicMock()
    node_exec = NodeExecutor(mock_executor)

    mock_node = MagicMock()
    mock_node.id = "node-3"
    mock_node.config = {}

    result = {"success": True, "output": {}}

    with patch("app.services.cost_tracker.get_cost_tracker", side_effect=RuntimeError("boom")):
        # Should not raise
        await node_exec._emit_cost_event(
            db=AsyncMock(),
            node=mock_node,
            result=result,
            category="tool_execution",
            run_id="run-1",
        )


# ── Test 16: LLMCallRecord model has new columns ───────────────────

def test_llm_call_record_has_cost_attribution_columns():
    """LLMCallRecord model has cost_category, tool_name, embedding_tokens."""
    from app.models.llm_call_record import LLMCallRecord

    mapper = LLMCallRecord.__mapper__
    columns = {c.key for c in mapper.columns}
    assert "cost_category" in columns
    assert "tool_name" in columns
    assert "embedding_tokens" in columns
