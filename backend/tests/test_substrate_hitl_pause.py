"""Tests for HITL pause/resume wiring (Q1-B chunk 1).

Tests cover:
- HITLPaused exception propagation through strategies
- UnifiedExecutor catching HITLPaused and emitting RUN_PAUSED
- HITL resume: node executor checks inbox item status on re-entry
- check_hitl_resolution helper
- Integration: approve → Celery task → resume flow
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.substrate.hitl_pause import (
    HITLPaused,
    HITLResolution,
    check_hitl_resolution,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_inbox_item(
    status: str = "pending",
    inbox_item_id: str | None = None,
    run_id: str | None = None,
    node_id: str | None = None,
    expires_at: datetime | None = None,
    resolution_payload: dict | None = None,
    resolution_note: str | None = None,
) -> MagicMock:
    """Create a mock InboxItem."""
    item = MagicMock()
    item.id = inbox_item_id or str(uuid4())
    item.status = status
    item.run_id = run_id or str(uuid4())
    item.node_id = node_id or str(uuid4())
    item.expires_at = expires_at
    item.resolution_payload = resolution_payload
    item.resolution_note = resolution_note
    item.created_at = datetime.now(UTC)
    return item


def _mock_db_with_item(item) -> AsyncMock:
    """Create a mock DB session that returns a single item."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    db.execute.return_value = mock_result
    return db


def _mock_db_empty() -> AsyncMock:
    """Create a mock DB session that returns no items."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result
    return db


# ── HITLPaused exception tests ──────────────────────────────────────


def test_hitl_paused_is_exception():
    """HITLPaused is an Exception subclass."""
    exc = HITLPaused(
        inbox_item_id="item-1",
        run_id="run-1",
        node_id="node-1",
        interrupt_type="approval",
        title="Approve deployment?",
    )
    assert isinstance(exc, Exception)
    assert exc.inbox_item_id == "item-1"
    assert exc.run_id == "run-1"
    assert exc.node_id == "node-1"


def test_hitl_paused_str_representation():
    """HITLPaused.__str__ includes type, title, and item ID."""
    exc = HITLPaused(
        inbox_item_id="item-42",
        run_id="run-1",
        node_id="node-1",
        interrupt_type="approval",
        title="Deploy to prod?",
    )
    s = str(exc)
    assert "approval" in s
    assert "Deploy to prod?" in s
    assert "item-42" in s


def test_hitl_paused_carries_context():
    """HITLPaused carries arbitrary context for the resume path."""
    exc = HITLPaused(
        inbox_item_id="item-1",
        run_id="run-1",
        node_id="node-1",
        context={"current_context": {"previous_output": "hello"}},
    )
    assert exc.context["current_context"]["previous_output"] == "hello"


# ── check_hitl_resolution tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_check_resolution_pending_not_expired():
    """Pending item with future expiry → not resolved."""
    item = _make_inbox_item(
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    db = _mock_db_with_item(item)
    resolution = await check_hitl_resolution(db, item.id)
    assert resolution.resolved is False
    assert resolution.status == "pending"


@pytest.mark.asyncio
async def test_check_resolution_pending_expired():
    """Pending item with past expiry → resolved as expired."""
    item = _make_inbox_item(
        status="pending",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db = _mock_db_with_item(item)
    resolution = await check_hitl_resolution(db, item.id)
    assert resolution.resolved is True
    assert resolution.status == "expired"


@pytest.mark.asyncio
async def test_check_resolution_approved():
    """Approved item → resolved with payload."""
    item = _make_inbox_item(
        status="approved",
        resolution_payload={"action": "deploy"},
        resolution_note="LGTM",
    )
    db = _mock_db_with_item(item)
    resolution = await check_hitl_resolution(db, item.id)
    assert resolution.resolved is True
    assert resolution.status == "approved"
    assert resolution.resolution_payload == {"action": "deploy"}
    assert resolution.resolution_note == "LGTM"


@pytest.mark.asyncio
async def test_check_resolution_rejected():
    """Rejected item → resolved as rejected."""
    item = _make_inbox_item(status="rejected", resolution_note="Too risky")
    db = _mock_db_with_item(item)
    resolution = await check_hitl_resolution(db, item.id)
    assert resolution.resolved is True
    assert resolution.status == "rejected"


@pytest.mark.asyncio
async def test_check_resolution_missing_item():
    """Missing inbox item → treated as expired."""
    db = _mock_db_empty()
    resolution = await check_hitl_resolution(db, "nonexistent-id")
    assert resolution.resolved is True
    assert resolution.status == "expired"


# ── HITLResolution dataclass tests ──────────────────────────────────


def test_hitl_resolution_frozen():
    """HITLResolution is immutable."""
    r = HITLResolution(resolved=True, status="approved")
    with pytest.raises(AttributeError):
        r.resolved = False  # type: ignore[misc]


# ── Strategy propagation tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_dag_strategy_propagates_hitl_paused():
    """DAGStrategy should propagate HITLPaused, not treat as node failure."""
    from app.services.substrate.strategies.dag import DAGStrategy

    strategy = DAGStrategy()

    hitl_exc = HITLPaused(
        inbox_item_id="item-1",
        run_id="run-1",
        node_id="node-1",
        interrupt_type="approval",
        title="Approve?",
    )

    workflow = MagicMock()
    workflow.nodes = [MagicMock(id="node-1")]
    workflow.edges = []
    workflow.metadata = {"substrate_run_id": "run-1"}
    workflow.node_map = {"node-1": workflow.nodes[0]}
    workflow.budget = MagicMock()
    workflow.dependency_map = {"node-1": []}
    workflow.get_in_degree = MagicMock(return_value={"node-1": 0})

    executor = MagicMock()
    executor.is_aborted = MagicMock(return_value=False)
    executor.execute_node = AsyncMock(side_effect=hitl_exc)

    db = AsyncMock()

    with pytest.raises(HITLPaused) as exc_info:
        await strategy.execute(workflow, {}, executor, db)

    assert exc_info.value.inbox_item_id == "item-1"


@pytest.mark.asyncio
async def test_solo_strategy_propagates_hitl_paused():
    """SoloStrategy should propagate HITLPaused (not catch it)."""
    from app.services.substrate.strategies.solo import SoloStrategy

    strategy = SoloStrategy()

    hitl_exc = HITLPaused(
        inbox_item_id="item-1",
        run_id="run-1",
        node_id="node-1",
        interrupt_type="approval",
        title="Approve?",
    )

    workflow = MagicMock()
    workflow.nodes = [MagicMock(id="node-1")]
    workflow.edges = []
    workflow.metadata = {"substrate_run_id": "run-1"}
    workflow.budget = MagicMock()

    executor = MagicMock()
    executor.is_aborted = MagicMock(return_value=False)
    executor.execute_node = AsyncMock(side_effect=hitl_exc)

    db = AsyncMock()

    with pytest.raises(HITLPaused) as exc_info:
        await strategy.execute(workflow, {}, executor, db)

    assert exc_info.value.inbox_item_id == "item-1"


# ── UnifiedExecutor HITL pause handling ──────────────────────────────


@pytest.mark.asyncio
async def test_executor_catches_hitl_paused_emits_run_paused():
    """UnifiedExecutor catches HITLPaused, emits RUN_PAUSED event, returns paused status."""
    from app.services.substrate.executor import UnifiedExecutor

    executor = UnifiedExecutor()

    hitl_exc = HITLPaused(
        inbox_item_id="item-1",
        run_id="run-1",
        node_id="node-1",
        mission_id="mission-1",
        interrupt_type="approval",
        title="Approve deployment?",
    )

    # Mock the strategy to raise HITLPaused
    mock_strategy = MagicMock()
    mock_strategy.validate = AsyncMock(return_value=[])
    mock_strategy.execute = AsyncMock(side_effect=hitl_exc)

    executor._strategies = {"solo": mock_strategy}
    executor._strategies_loaded = True

    mock_node = MagicMock()
    mock_node.id = "node-1"

    from app.services.substrate.workflow_models import WorkflowType

    workflow = MagicMock()
    workflow.id = "mission-1"
    workflow.type = WorkflowType.SOLO
    workflow.nodes = [mock_node]
    workflow.user_id = "user-1"
    workflow.title = "Test"
    workflow.description = ""
    workflow.budget = MagicMock()

    executor._strategies = {WorkflowType.SOLO: mock_strategy}

    db = AsyncMock()

    with (
        patch.object(executor, "_ensure_circuit_breaker", new_callable=AsyncMock),
        patch.object(executor.event_log, "append", new_callable=AsyncMock),
        patch.object(executor.event_log, "run_exists", new_callable=AsyncMock, return_value=False),
        patch("app.services.substrate.executor.settings") as mock_settings,
    ):
        mock_settings.FLOWMANNER_LEASE_ENABLED = False

        result = await executor.execute(db, workflow)

    assert result.success is False
    assert result.status == "paused"
    assert result.data["hitl_paused"] is True
    assert result.data["inbox_item_id"] == "item-1"
    assert result.data["interrupt_type"] == "approval"


# ── Node executor HITL resume check tests ────────────────────────────


@pytest.mark.asyncio
async def test_check_hitl_resume_approved():
    """_check_hitl_resume returns success for approved inbox item."""
    from app.services.substrate.node_executor import NodeExecutor

    ne = NodeExecutor(MagicMock())

    node = MagicMock()
    node.id = "node-1"
    node.type = MagicMock()

    item = _make_inbox_item(
        status="approved",
        run_id="run-1",
        node_id="node-1",
        resolution_payload={"action": "deploy"},
        resolution_note="LGTM",
    )

    db = _mock_db_with_item(item)

    result = await ne._check_hitl_resume(db, node, {}, "run-1")

    assert result is not None
    assert result["success"] is True
    assert result["output"]["hitl_resolution"] == "approved"
    assert result["output"]["resolution_payload"] == {"action": "deploy"}


@pytest.mark.asyncio
async def test_check_hitl_resume_rejected():
    """_check_hitl_resume returns failure for rejected inbox item."""
    from app.services.substrate.node_executor import NodeExecutor

    ne = NodeExecutor(MagicMock())

    node = MagicMock()
    node.id = "node-1"
    node.type = MagicMock()

    item = _make_inbox_item(
        status="rejected",
        run_id="run-1",
        node_id="node-1",
        resolution_note="Too risky",
    )

    db = _mock_db_with_item(item)

    result = await ne._check_hitl_resume(db, node, {}, "run-1")

    assert result is not None
    assert result["success"] is False
    assert "rejected" in result["error"]


@pytest.mark.asyncio
async def test_check_hitl_resume_still_pending():
    """_check_hitl_resume returns None for pending item (will re-raise HITLPaused)."""
    from app.services.substrate.node_executor import NodeExecutor

    ne = NodeExecutor(MagicMock())

    node = MagicMock()
    node.id = "node-1"
    node.type = MagicMock()

    item = _make_inbox_item(
        status="pending",
        run_id="run-1",
        node_id="node-1",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )

    db = _mock_db_with_item(item)

    result = await ne._check_hitl_resume(db, node, {}, "run-1")

    assert result is None


@pytest.mark.asyncio
async def test_check_hitl_resume_no_item():
    """_check_hitl_resume returns None when no inbox item exists (first execution)."""
    from app.services.substrate.node_executor import NodeExecutor

    ne = NodeExecutor(MagicMock())

    node = MagicMock()
    node.id = "node-1"
    node.type = MagicMock()

    db = _mock_db_empty()

    result = await ne._check_hitl_resume(db, node, {}, "run-1")

    assert result is None


@pytest.mark.asyncio
async def test_check_hitl_resume_expired():
    """_check_hitl_resume returns failure for expired inbox item."""
    from app.services.substrate.node_executor import NodeExecutor

    ne = NodeExecutor(MagicMock())

    node = MagicMock()
    node.id = "node-1"
    node.type = MagicMock()

    item = _make_inbox_item(
        status="expired",
        run_id="run-1",
        node_id="node-1",
    )

    db = _mock_db_with_item(item)

    result = await ne._check_hitl_resume(db, node, {}, "run-1")

    assert result is not None
    assert result["success"] is False
    assert "expired" in result["error"]


@pytest.mark.asyncio
async def test_check_hitl_resume_clarified():
    """_check_hitl_resume returns success for clarified inbox item."""
    from app.services.substrate.node_executor import NodeExecutor

    ne = NodeExecutor(MagicMock())

    node = MagicMock()
    node.id = "node-1"
    node.type = MagicMock()

    item = _make_inbox_item(
        status="clarified",
        run_id="run-1",
        node_id="node-1",
        resolution_payload={"response_text": "Use version 2"},
        resolution_note="Use version 2",
    )

    db = _mock_db_with_item(item)

    result = await ne._check_hitl_resume(db, node, {}, "run-1")

    assert result is not None
    assert result["success"] is True
    assert result["output"]["hitl_resolution"] == "clarified"


# ── Celery task dispatch test ────────────────────────────────────────


def test_dispatch_hitl_resume_sends_task():
    """dispatch_hitl_resume calls resume_hitl_task.delay with correct args."""
    with patch("app.tasks.hitl_resume.resume_hitl_task") as mock_task:
        from app.tasks.hitl_resume import dispatch_hitl_resume

        dispatch_hitl_resume(
            mission_id="mission-1",
            run_id="run-1",
            inbox_item_id="item-1",
            resolution="approved",
        )

    mock_task.delay.assert_called_once_with("mission-1", "run-1", "item-1", "approved")


# ── HITL API wiring test ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signal_executor_resume_dispatches_celery_task():
    """_signal_executor_resume dispatches a Celery task (not Redis pub/sub)."""
    mock_item = MagicMock()
    mock_item.id = "item-42"

    from app.api.v1.hitl import _signal_executor_resume

    with patch("app.tasks.hitl_resume.dispatch_hitl_resume") as mock_dispatch:
        await _signal_executor_resume("mission-1", "run-1", "approved", mock_item)

    mock_dispatch.assert_called_once_with(
        mission_id="mission-1",
        run_id="run-1",
        inbox_item_id="item-42",
        resolution="approved",
    )


@pytest.mark.asyncio
async def test_signal_executor_resume_no_run_id():
    """_signal_executor_resume does nothing if run_id is None."""
    mock_item = MagicMock()
    mock_item.id = "item-42"

    from app.api.v1.hitl import _signal_executor_resume

    with patch("app.tasks.hitl_resume.dispatch_hitl_resume") as mock_dispatch:
        await _signal_executor_resume("mission-1", None, "approved", mock_item)

    mock_dispatch.assert_not_called()
