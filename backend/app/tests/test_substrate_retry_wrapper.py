"""Tests for the standalone ``retry`` reliability wrapper (NodeType.RETRY).

The ``retry`` node is a composition wrapper: it resolves its single wrapped
child, overrides the child's effective ``max_retries`` (wrapper wins per Q1)
and propagates ``backoffMs`` into the child's config, then re-executes the
child through ``NodeExecutor.execute`` — reusing the existing retry loop and
BudgetExhausted handling unchanged.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
pytestmark = pytest.mark.integration


def _make_executor():
    from app.models.capability_models import Budget
    from app.services.substrate.node_executor import NodeExecutor
    from app.services.substrate.workflow_models import (
        EffectClass,
        NodeType,
        Workflow,
        WorkflowEdge,
        WorkflowNode,
    )

    return (
        NodeExecutor(MagicMock()),
        Budget,
        EffectClass,
        NodeType,
        Workflow,
        WorkflowEdge,
        WorkflowNode,
    )


class TestRetryWrapperContract:
    """Static contract checks: child resolution, override precedence, backoff."""

    @pytest.mark.asyncio
    async def test_retry_overrides_child_retries_and_propagates_backoff(self):
        executor, Budget, EffectClass, NodeType, Workflow, WorkflowEdge, WorkflowNode = _make_executor()
        # Child carries its own (lower) inline max_retries + no backoff.
        child = WorkflowNode(
            id="child",
            type=NodeType.TRANSFORM,
            title="Child",
            max_retries=1,
            config={"transformExpression": "x"},
        )
        retry = WorkflowNode(
            id="retry",
            type=NodeType.RETRY,
            title="Retry",
            config={"maxRetries": 5, "backoffMs": 250},
        )
        workflow = Workflow(
            id="w1",
            type="solo",
            title="wf",
            nodes=[retry, child],
            edges=[WorkflowEdge(source="retry", target="child")],
        )

        # Capture the child as passed into execute() to assert overrides.
        seen = {}

        async def fake_execute(db, node, context, budget, run_id, workflow=None):
            seen["node"] = node
            return {"success": True, "output": {"ok": True}, "tokens": 0, "cost": 0.0}

        with patch.object(executor, "execute", side_effect=fake_execute):
            result = await executor._handle_retry(
                db=AsyncMock(),
                node=retry,
                context={},
                budget=Budget(),
                run_id="run-1",
                workflow=workflow,
            )

        assert result["success"] is True
        # Wrapper wins (Q1): child.max_retries overridden to 5.
        assert seen["node"].max_retries == 5
        # Backoff propagated into child config as backoff_ms (consumed by loop).
        assert seen["node"].config.get("backoff_ms") == 250

    @pytest.mark.asyncio
    async def test_retry_without_child_errors_explicitly(self):
        executor, Budget, EffectClass, NodeType, Workflow, WorkflowEdge, WorkflowNode = _make_executor()
        retry = WorkflowNode(
            id="retry",
            type=NodeType.RETRY,
            title="Retry",
            config={"maxRetries": 3},
        )
        workflow = Workflow(
            id="w1",
            type="solo",
            title="wf",
            nodes=[retry],
            edges=[],
        )
        result = await executor._handle_retry(
            db=AsyncMock(),
            node=retry,
            context={},
            budget=Budget(),
            run_id="run-1",
            workflow=workflow,
        )
        # No silent swallow: an unconnected wrapper reports a clear error.
        assert result["success"] is False
        assert "no wrapped child" in result["error"]

    @pytest.mark.asyncio
    async def test_retry_requires_workflow_graph(self):
        executor, Budget, EffectClass, NodeType, Workflow, WorkflowEdge, WorkflowNode = _make_executor()
        retry = WorkflowNode(id="retry", type=NodeType.RETRY, title="Retry")
        result = await executor._handle_retry(
            db=AsyncMock(),
            node=retry,
            context={},
            budget=Budget(),
            run_id="run-1",
            workflow=None,
        )
        assert result["success"] is False
        assert "workflow" in result["error"]


class TestRetryWrapperIntegration:
    """End-to-end: a failing child is retried N times with backoff sleep."""

    @pytest.mark.asyncio
    async def test_child_retried_with_backoff(self):
        executor, Budget, EffectClass, NodeType, Workflow, WorkflowEdge, WorkflowNode = _make_executor()
        # A transform with no expression fails deterministically on every attempt.
        child = WorkflowNode(
            id="child",
            type=NodeType.TRANSFORM,
            title="Child",
            effect_class=EffectClass.REVERSIBLE,  # retryable: pure transform, no irreversible side effect
            config={},  # no transformExpression -> handler returns success=False
        )
        retry = WorkflowNode(
            id="retry",
            type=NodeType.RETRY,
            title="Retry",
            config={"maxRetries": 2, "backoffMs": 50},
        )
        workflow = Workflow(
            id="w1",
            type="solo",
            title="wf",
            nodes=[retry, child],
            edges=[WorkflowEdge(source="retry", target="child")],
        )

        executor.executor.is_aborted = MagicMock(return_value=False)
        mock_event_log = AsyncMock()
        mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])
        mock_event_log.get_latest_sequence = AsyncMock(return_value=0)
        mock_event_log.find_by_idempotency_key = AsyncMock(return_value=None)
        sleep_calls = []

        async def fake_sleep(secs):
            sleep_calls.append(secs)

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_event_log,
            ),
            patch("asyncio.sleep", side_effect=fake_sleep),
        ):
            result = await executor._handle_retry(
                db=AsyncMock(),
                node=retry,
                context={},
                budget=Budget(),
                run_id="run-1",
                workflow=workflow,
            )

        # Child fails every attempt; after maxRetries+1 attempts the wrapper
        # surfaces the child failure (budget exhaustion is preserved separately).
        assert result["success"] is False
        # maxRetries=2 -> 3 attempts -> 2 backoff sleeps between them.
        assert len(sleep_calls) == 2
        assert all(s == 0.05 for s in sleep_calls)
