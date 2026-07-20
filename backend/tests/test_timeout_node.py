"""Deadline wrapper tests for the ``timeout`` node type.

Exercises ``UnifiedExecutor.execute_with_timeout`` directly:

1. A child that exceeds the deadline -> ``branch == "on_timeout"`` result and
   a ``NODE_TIMEOUT`` substrate event is emitted; the in-flight task is
   cancelled cleanly (no leaked coroutines).
2. A child that completes in time -> its result passes through unchanged.
3. Abort / budget failures propagate (not swallowed by the wrapper).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.substrate_models import SubstrateEventType
from app.models.capability_models import Budget, BudgetExhausted
from app.services.substrate.executor import UnifiedExecutor
from app.services.substrate.workflow_models import NodeType, WorkflowNode


def _node(node_type: str, node_id: str = "n", config: dict | None = None) -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        type=NodeType(node_type),
        title=node_type,
        config=config or {},
    )


def _executor() -> UnifiedExecutor:
    ex = UnifiedExecutor(event_log=MagicMock())
    # event_log.append must be awaitable; record calls so we can assert.
    ex.event_log.append = AsyncMock()
    return ex


@pytest.mark.asyncio
async def test_timeout_fires_on_deadline_miss_and_cancels_cleanly():
    ex = _executor()

    timeout_node = _node("timeout", "t", {"timeoutMs": 50})
    child = _node("llm_call", "c")

    # Child sleeps longer than the deadline.
    async def _slow_child(*_a, **_k):
        await asyncio.sleep(0.5)
        return {"success": True, "output": {"done": True}}

    with patch(
        "app.services.substrate.node_executor.NodeExecutor.execute",
        new=_slow_child,
    ):
        result = await ex.execute_with_timeout(
            db=MagicMock(),
            node=timeout_node,
            child=child,
            context={},
            budget=Budget(),
            run_id="run-1",
            workflow=None,
            timeout_ms=50,
        )

    # Branch routing signal for strategy-level gating.
    assert result["success"] is True
    assert result["branch"] == "on_timeout"
    assert result["timed_out"] is True
    # NODE_TIMEOUT event emitted.
    assert ex.event_log.append.await_count == 1
    emitted = ex.event_log.append.call_args[0][2][0]
    assert emitted["type"] == SubstrateEventType.NODE_TIMEOUT
    assert emitted["payload"]["child_id"] == "c"
    # No leaked tasks remain.
    pending = asyncio.all_tasks()
    assert not any(t.get_name() == "timeout_child" for t in pending)


@pytest.mark.asyncio
async def test_timeout_passes_through_when_child_completes_in_time():
    ex = _executor()

    timeout_node = _node("timeout", "t", {"timeoutMs": 5000})
    child = _node("llm_call", "c")

    async def _fast_child(*_a, **_k):
        await asyncio.sleep(0.01)
        return {"success": True, "output": {"ok": 1}, "tokens": 3, "cost": 0.01}

    with patch(
        "app.services.substrate.node_executor.NodeExecutor.execute",
        new=_fast_child,
    ):
        result = await ex.execute_with_timeout(
            db=MagicMock(),
            node=timeout_node,
            child=child,
            context={},
            budget=Budget(),
            run_id="run-2",
            workflow=None,
            timeout_ms=5000,
        )

    # Child result passes through unchanged (no "on_timeout" branch).
    assert result["success"] is True
    assert result.get("branch") != "on_timeout"
    assert result["output"] == {"ok": 1}
    assert result["tokens"] == 3
    # No timeout event emitted on the happy path.
    ex.event_log.append.assert_not_called()


@pytest.mark.asyncio
async def test_timeout_propagates_budget_exhausted():
    ex = _executor()

    timeout_node = _node("timeout", "t", {"timeoutMs": 5000})
    child = _node("llm_call", "c")

    async def _boom(*_a, **_k):
        raise BudgetExhausted("over budget", Budget())

    with patch(
        "app.services.substrate.node_executor.NodeExecutor.execute",
        new=_boom,
    ):
        with pytest.raises(BudgetExhausted):
            await ex.execute_with_timeout(
                db=MagicMock(),
                node=timeout_node,
                child=child,
                context={},
                budget=Budget(),
                run_id="run-3",
                workflow=None,
                timeout_ms=5000,
            )

    # Budget failure is NOT turned into a timeout branch.
    ex.event_log.append.assert_not_called()


@pytest.mark.asyncio
async def test_timeout_node_handler_resolves_wrapped_child_and_wraps():
    """End-to-end through NodeExecutor._handle_timeout (no patch of execute)."""
    from app.services.substrate.node_executor import NodeExecutor

    ex = _executor()

    timeout_node = _node("timeout", "t", {"timeoutMs": 30, "wrapped_node_id": "c"})
    child = _node("llm_call", "c")
    workflow = MagicMock()
    workflow.node_map = {"c": child}
    workflow.edges = []

    async def _slow_child(*_a, **_k):
        await asyncio.sleep(0.3)
        return {"success": True, "output": {}}

    node_exec = NodeExecutor(ex)
    with patch(
        "app.services.substrate.node_executor.NodeExecutor.execute",
        new=_slow_child,
    ):
        result = await node_exec._handle_timeout(
            db=MagicMock(),
            node=timeout_node,
            context={},
            budget=Budget(),
            run_id="run-4",
            workflow=workflow,
        )

    assert result["branch"] == "on_timeout"
    assert result["timed_out"] is True


@pytest.mark.asyncio
async def test_timeout_node_handler_missing_child_fails():
    from app.services.substrate.node_executor import NodeExecutor

    ex = _executor()
    timeout_node = _node("timeout", "t", {"timeoutMs": 100})
    workflow = MagicMock()
    workflow.node_map = {}
    workflow.edges = []

    node_exec = NodeExecutor(ex)
    result = await node_exec._handle_timeout(
        db=MagicMock(),
        node=timeout_node,
        context={},
        budget=Budget(),
        run_id="run-5",
        workflow=workflow,
    )
    assert result["success"] is False
    assert "wrapped child" in result["error"]
