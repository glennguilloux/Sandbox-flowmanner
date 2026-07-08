"""Tests for Item #3 — Workflow replay idempotency + budget ledger.

Covers:
- idempotency_key computation determinism
- EventLog dedup-on-write
- Durable abort (abort event in log, re-arm on replay)
- LLM output replay (skip provider call on cached response)
- Budget reserve/refund for nested sub-workflows
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.capability_models import Budget, BudgetExhausted
from app.models.substrate_models import SubstrateEvent, SubstrateEventType

# ═══════════════════════════════════════════════════════════════════
# Idempotency key computation
# ═══════════════════════════════════════════════════════════════════


class TestIdempotencyKeyComputation:
    def test_deterministic_same_inputs(self):
        """Same inputs produce the same key."""
        from app.services.substrate.event_log import _compute_idempotency_key

        k1 = _compute_idempotency_key("run-1", "task.completed", "node-a", {"output": "ok"})
        k2 = _compute_idempotency_key("run-1", "task.completed", "node-a", {"output": "ok"})
        assert k1 == k2

    def test_different_run_ids_differ(self):
        """Different run_id produces a different key."""
        from app.services.substrate.event_log import _compute_idempotency_key

        k1 = _compute_idempotency_key("run-1", "task.completed", "n", {"x": 1})
        k2 = _compute_idempotency_key("run-2", "task.completed", "n", {"x": 1})
        assert k1 != k2

    def test_different_task_ids_differ(self):
        """Different task_id produces a different key."""
        from app.services.substrate.event_log import _compute_idempotency_key

        k1 = _compute_idempotency_key("run-1", "task.completed", "n1", {"x": 1})
        k2 = _compute_idempotency_key("run-1", "task.completed", "n2", {"x": 1})
        assert k1 != k2

    def test_different_payloads_differ(self):
        """Different payload produces a different key."""
        from app.services.substrate.event_log import _compute_idempotency_key

        k1 = _compute_idempotency_key("run-1", "llm.response", "n", {"text": "hello"})
        k2 = _compute_idempotency_key("run-1", "llm.response", "n", {"text": "world"})
        assert k1 != k2

    def test_payload_order_independent(self):
        """Payload key order doesn't matter (sorted JSON)."""
        from app.services.substrate.event_log import _compute_idempotency_key

        k1 = _compute_idempotency_key("r", "t", "n", {"b": 2, "a": 1})
        k2 = _compute_idempotency_key("r", "t", "n", {"a": 1, "b": 2})
        assert k1 == k2


# ═══════════════════════════════════════════════════════════════════
# EventLog dedup-on-write
# ═══════════════════════════════════════════════════════════════════


class TestEventLogDedup:
    def test_dedup_skips_duplicate_events(self):
        """Second append with same idempotency key skips the event."""
        from app.services.substrate.event_log import EventLog

        el = EventLog()
        run_id = str(uuid4())
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        # Mock _idempotency_key_exists to return True on second call
        call_count = {"n": 0}

        async def mock_exists(db, key):
            call_count["n"] += 1
            return call_count["n"] > 1  # First call False, second True

        async def mock_count(db, rid):
            return 0

        el._count_events = AsyncMock(side_effect=mock_count)
        el._idempotency_key_exists = AsyncMock(side_effect=mock_exists)
        el.get_latest_sequence = AsyncMock(return_value=0)

        events = [{"type": "task.started", "payload": {"task_id": "t1"}, "actor": "test"}]

        # First append — should persist
        result1 = asyncio.run(el.append(db, run_id, events))
        assert len(result1) == 1
        db.add.assert_called_once()

        # Second append with same key — should be skipped
        db.add.reset_mock()
        result2 = asyncio.run(el.append(db, run_id, events))
        assert len(result2) == 0
        db.add.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# Budget reserve / refund
# ═══════════════════════════════════════════════════════════════════


class TestBudgetReserve:
    def test_reserve_deducts_from_remaining(self):
        """reserve() increases spent_usd."""
        budget = Budget(max_cost_usd=Decimal("10.00"))
        budget.reserve(Decimal("3.00"))
        assert budget.spent_usd == Decimal("3.00")

    def test_reserve_raises_when_exceeds_remaining(self):
        """reserve() raises BudgetExhausted if reservation > remaining."""
        budget = Budget(max_cost_usd=Decimal("5.00"))
        with pytest.raises(BudgetExhausted):
            budget.reserve(Decimal("6.00"))

    def test_reserve_chains_correctly(self):
        """Multiple reservations accumulate."""
        budget = Budget(max_cost_usd=Decimal("10.00"))
        budget.reserve(Decimal("3.00"))
        budget.reserve(Decimal("4.00"))
        assert budget.spent_usd == Decimal("7.00")
        # Third reservation exceeds remaining
        with pytest.raises(BudgetExhausted):
            budget.reserve(Decimal("4.00"))


class TestBudgetRefund:
    def test_refund_returns_to_pool(self):
        """refund() decreases spent_usd."""
        budget = Budget(max_cost_usd=Decimal("10.00"))
        budget.reserve(Decimal("5.00"))
        assert budget.spent_usd == Decimal("5.00")
        budget.refund(Decimal("2.00"))
        assert budget.spent_usd == Decimal("3.00")

    def test_refund_clamped_to_spent(self):
        """refund() never goes below zero."""
        budget = Budget(max_cost_usd=Decimal("10.00"))
        budget.reserve(Decimal("2.00"))
        budget.refund(Decimal("5.00"))  # More than spent
        assert budget.spent_usd == Decimal("0.00")

    def test_reserve_refund_cycle(self):
        """Full reserve → execute → refund cycle restores budget."""
        budget = Budget(max_cost_usd=Decimal("10.00"))
        child_cost = Decimal("4.00")
        budget.reserve(Decimal("6.00"))
        # Child spent 4 out of 6
        unused = Decimal("6.00") - child_cost
        budget.refund(unused)
        assert budget.spent_usd == child_cost


# ═══════════════════════════════════════════════════════════════════
# Durable abort
# ═══════════════════════════════════════════════════════════════════


class TestDurableAbort:
    def test_abort_writes_event_to_log(self):
        """abort() with db writes an abort_requested event."""
        from app.services.substrate.executor import UnifiedExecutor

        executor = UnifiedExecutor()
        executor.event_log = MagicMock()
        executor.event_log.append = AsyncMock()

        db = MagicMock()
        result = asyncio.run(executor.abort("run-1", reason="user_cancel", db=db))

        assert result is True
        executor.event_log.append.assert_called_once()
        call_args = executor.event_log.append.call_args
        events = call_args[0][2]
        assert events[0]["type"] == "abort_requested"
        assert events[0]["payload"]["reason"] == "user_cancel"

    def test_abort_without_db_still_sets_signal(self):
        """abort() without db still sets the in-memory signal."""
        from app.services.substrate.executor import UnifiedExecutor

        executor = UnifiedExecutor()
        executor.event_log = MagicMock()
        executor.event_log.append = AsyncMock()

        result = asyncio.run(executor.abort("run-1", reason="test"))

        assert result is True
        assert executor.is_aborted("run-1") is True
        # No event written
        executor.event_log.append.assert_not_called()

    def test_abort_idempotent(self):
        """abort() twice returns False on second call."""
        from app.services.substrate.executor import UnifiedExecutor

        executor = UnifiedExecutor()

        r1 = asyncio.run(executor.abort("run-1"))
        r2 = asyncio.run(executor.abort("run-1"))
        assert r1 is True
        assert r2 is False


# ═══════════════════════════════════════════════════════════════════
# LLM output replay
# ═══════════════════════════════════════════════════════════════════


class TestLLMOutputReplay:
    def test_replay_returns_cached_response(self):
        """_handle_llm returns cached LLM response without calling provider."""
        from app.services.substrate.node_executor import NodeExecutor

        mock_executor = MagicMock()
        mock_executor.check_circuit_breaker = AsyncMock(return_value=(True, ""))
        ne = NodeExecutor(mock_executor)

        node = MagicMock()
        node.id = "node-1"
        node.assigned_model = "deepseek-v4-flash"
        node.config = {"prompt": "Hello world"}
        node.title = "Test"

        cached_event = MagicMock()
        cached_event.payload = {
            "response": "Cached response text",
            "tokens": 42,
            "cost_usd": 0.01,
            "model": "deepseek-v4-flash",
            "provider": "deepseek",
        }

        mock_event_log = MagicMock()
        mock_event_log.find_by_idempotency_key = AsyncMock(return_value=cached_event)

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = asyncio.run(
                ne._handle_llm(
                    db=AsyncMock(),
                    node=node,
                    context={},
                    budget=MagicMock(),
                    run_id="run-1",
                    workflow=MagicMock(id="wf-1", user_id="1"),
                )
            )

        assert result["success"] is True
        assert result["output"]["text"] == "Cached response text"
        assert result["tokens"] == 42
        # Provider comes from the cached event payload
        assert result["provider"] == "deepseek"

    def test_no_replay_calls_provider(self):
        """_handle_llm calls provider when no cached response exists."""
        from app.services.substrate.node_executor import NodeExecutor

        mock_executor = MagicMock()
        mock_executor.check_circuit_breaker = AsyncMock(return_value=(True, ""))
        ne = NodeExecutor(mock_executor)

        node = MagicMock()
        node.id = "node-2"
        node.assigned_model = "deepseek-v4-flash"
        node.config = {"prompt": "Hello"}
        node.title = "Test"

        mock_event_log = MagicMock()
        mock_event_log.find_by_idempotency_key = AsyncMock(return_value=None)
        mock_event_log.append = AsyncMock()

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value={
                "success": True,
                "response": "Fresh response",
                "cost": {"input_tokens": 10, "output_tokens": 20, "usd": 0.005},
                "budget": {"spent_usd": 0.005},
                "model": "deepseek-v4-flash",
                "provider": "deepseek",
            }
        )

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_event_log,
            ),
            patch(
                "app.services.budget_enforcer.get_budget_enforcer",
                return_value=mock_enforcer,
            ),
        ):
            result = asyncio.run(
                ne._handle_llm(
                    db=AsyncMock(),
                    node=node,
                    context={},
                    budget=MagicMock(),
                    run_id="run-2",
                    workflow=MagicMock(id="wf-1", user_id="1"),
                )
            )

        assert result["success"] is True
        assert result["output"]["text"] == "Fresh response"
        mock_enforcer.call.assert_called_once()
