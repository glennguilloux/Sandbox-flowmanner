"""Unit tests for typed HandoffPacket (Q2-Q3 Chunk 5).

Covers:
- Schema validation (required fields, constraints, round-trip)
- Protocol methods (delegate_with_packet, accept_with_packet, complete_with_packet)
- Budget enforcement (zero budget, overspend)
- HITL scoping (cross-workspace rejection)
- Backward compatibility (old delegate still works)

All tests use mocked DB and lease/event services — no live DB required.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.handoff_packet_models import (
    HandoffBudget,
    HandoffDepthPolicyState,
    HandoffHITLState,
    HandoffPacket,
)
from app.services.swarm.handoff_protocol import (
    BudgetExceededError,
    HandoffProtocol,
)

# ── Helpers ────────────────────────────────────────────────────────


def _make_budget(
    remaining: str = "1.00",
    initial: str = "5.00",
) -> HandoffBudget:
    return HandoffBudget(
        remaining_usd=Decimal(remaining),
        initial_usd=Decimal(initial),
    )


def _make_packet(**overrides) -> HandoffPacket:
    defaults = {
        "handoff_id": "h-001",
        "from_agent_id": "agent-a",
        "from_agent_name": "Agent A",
        "to_agent_id": "agent-b",
        "to_agent_name": "Agent B",
        "goal": "Implement the widget",
        "success_criteria": ["Tests pass", "No regressions"],
        "budget": _make_budget(),
    }
    defaults.update(overrides)
    return HandoffPacket(**defaults)


def _mock_db():
    """Create a mock AsyncSession that tracks .add() calls."""
    db = AsyncMock()
    db.add = MagicMock()
    return db


def _make_record(**overrides):
    """Create a mock HandoffRecord with sensible defaults."""
    rec = MagicMock()
    rec.id = overrides.get("id", "h-001")
    rec.from_agent_id = overrides.get("from_agent_id", "agent-a")
    rec.from_agent_name = overrides.get("from_agent_name", "Agent A")
    rec.to_agent_id = overrides.get("to_agent_id", "agent-b")
    rec.to_agent_name = overrides.get("to_agent_name", "Agent B")
    rec.task_description = overrides.get("task_description", "Implement the widget")
    rec.goal = overrides.get("goal", "Implement the widget")
    rec.success_criteria = overrides.get("success_criteria", ["Tests pass"])
    rec.retrieved_context_ids = overrides.get("retrieved_context_ids", [])
    rec.tool_candidates = overrides.get("tool_candidates", [])
    rec.budget_remaining_usd = overrides.get("budget_remaining_usd", 1.0)
    rec.hitl_state = overrides.get("hitl_state", {})
    rec.depth_policy_state = overrides.get("depth_policy_state")
    rec.parent_handoff_id = overrides.get("parent_handoff_id")
    rec.status = overrides.get("status", "pending")
    rec.execution_id = overrides.get("execution_id")
    rec.priority = overrides.get("priority", 0)
    rec.started_at = overrides.get("started_at")
    rec.completed_at = overrides.get("completed_at")
    rec.result = overrides.get("result")
    rec.result_metadata = overrides.get("result_metadata")
    return rec


# ── Schema tests (no DB) ──────────────────────────────────────────


class TestHandoffPacketSchema:
    def test_packet_required_fields(self):
        """HandoffPacket rejects missing goal, success_criteria, budget."""
        with pytest.raises(Exception):
            HandoffPacket(handoff_id="h", from_agent_id="a", to_agent_id="b")

    def test_packet_budget_must_be_positive_initial(self):
        """HandoffBudget(initial_usd=0) raises."""
        with pytest.raises(Exception):
            HandoffBudget(remaining_usd=Decimal("0"), initial_usd=Decimal("0"))

    def test_packet_remaining_cannot_be_negative(self):
        """HandoffBudget with negative remaining raises."""
        with pytest.raises(Exception):
            HandoffBudget(remaining_usd=Decimal("-1"), initial_usd=Decimal("5"))

    def test_packet_extra_forbidden(self):
        """HandoffPacket rejects extra fields (extra='forbid')."""
        with pytest.raises(Exception):
            HandoffPacket(
                handoff_id="h",
                from_agent_id="a",
                to_agent_id="b",
                goal="Test",
                success_criteria=["Done"],
                budget=_make_budget(),
                bogus_field="nope",
            )

    def test_packet_serialize_to_json_round_trip(self):
        """model_dump_json → model_validate_json round-trips."""
        packet = _make_packet()
        # by_alias=True is needed because metadata_ uses alias="metadata"
        # and extra="forbid" would reject the alias key on re-validation.
        json_str = packet.model_dump_json(by_alias=True)
        restored = HandoffPacket.model_validate_json(json_str)
        assert restored.handoff_id == packet.handoff_id
        assert restored.goal == packet.goal
        assert restored.budget.remaining_usd == packet.budget.remaining_usd

    def test_packet_decimal_preserved(self):
        """Decimal('0.000001') survives JSON round-trip."""
        budget = HandoffBudget(
            remaining_usd=Decimal("0.000001"),
            initial_usd=Decimal("1.000000"),
        )
        packet = _make_packet(budget=budget)
        json_str = packet.model_dump_json(by_alias=True)
        restored = HandoffPacket.model_validate_json(json_str)
        assert restored.budget.remaining_usd == Decimal("0.000001")


# ── Protocol tests (mocked DB + lease + event_log) ────────────────


class TestHandoffProtocolTyped:
    @pytest.fixture
    def protocol(self):
        db = _mock_db()
        mock_lease = AsyncMock()
        mock_event_log = AsyncMock()
        hp = HandoffProtocol(db, lease_integration=mock_lease, event_log=mock_event_log)
        return hp

    @pytest.mark.asyncio
    async def test_delegate_with_packet_persists_typed_fields(self, protocol):
        """delegate_with_packet writes all 7 new HandoffRecord columns."""
        packet = _make_packet()
        await protocol.delegate_with_packet(packet, execution_id="exec-1")
        added = protocol.db.add.call_args[0][0]
        assert added.goal == "Implement the widget"
        assert added.success_criteria == ["Tests pass", "No regressions"]
        assert added.retrieved_context_ids == []
        assert added.tool_candidates == []
        assert added.budget_remaining_usd == Decimal("1.00")
        assert added.hitl_state is not None
        assert added.depth_policy_state is None

    @pytest.mark.asyncio
    async def test_delegate_with_packet_claims_lease(self, protocol):
        """delegate_with_packet calls lease_integration.claim_for_handoff."""
        packet = _make_packet()
        await protocol.delegate_with_packet(packet)
        protocol.lease_integration.claim_for_handoff.assert_awaited_once_with("h-001", "agent-b")

    @pytest.mark.asyncio
    async def test_delegate_with_packet_emits_initiated_event(self, protocol):
        """HANDOFF_INITIATED event is appended via event_log."""
        packet = _make_packet()
        await protocol.delegate_with_packet(packet, execution_id="exec-1")
        protocol._event_log.append.assert_awaited_once()
        call_args = protocol._event_log.append.call_args
        events = call_args[0][2]
        assert events[0]["type"] == "handoff.initiated"

    @pytest.mark.asyncio
    async def test_delegate_with_zero_budget_raises(self, protocol):
        """packet.budget.remaining_usd = 0 raises BudgetExceededError."""
        packet = _make_packet(budget=HandoffBudget(remaining_usd=Decimal("0"), initial_usd=Decimal("1")))
        with pytest.raises(BudgetExceededError):
            await protocol.delegate_with_packet(packet)
        protocol.db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_delegate_with_cross_workspace_hitl_raises(self, protocol):
        """Cross-workspace HITL item raises ValueError."""
        packet = _make_packet(
            hitl_state=HandoffHITLState(
                pending_items=[{"id": "item-1", "workspace_id": "ws-other"}],
                workspace_id="ws-main",
            )
        )
        with pytest.raises(ValueError, match="workspace_id mismatch"):
            await protocol.delegate_with_packet(packet)

    @pytest.mark.asyncio
    async def test_delegate_with_unscoped_hitl_item_raises(self, protocol):
        """HITL item with no workspace_id in a scoped packet raises ValueError."""
        packet = _make_packet(
            hitl_state=HandoffHITLState(
                pending_items=[{"id": "item-1"}],
                workspace_id="ws-main",
            )
        )
        with pytest.raises(ValueError, match="no workspace_id"):
            await protocol.delegate_with_packet(packet)

    @pytest.mark.asyncio
    async def test_accept_with_packet_returns_typed_packet(self, protocol):
        """accept_with_packet returns a HandoffPacket from the record."""
        record = _make_record(status="pending", budget_remaining_usd=2.5)
        with patch.object(protocol, "_get", return_value=record):
            packet = await protocol.accept_with_packet("h-001")
        assert isinstance(packet, HandoffPacket)
        assert packet.goal == "Implement the widget"
        assert packet.budget.remaining_usd == Decimal("2.5")
        assert record.status == "accepted"

    @pytest.mark.asyncio
    async def test_accept_with_packet_not_pending_raises(self, protocol):
        """accept_with_packet on non-pending handoff raises ValueError."""
        record = _make_record(status="completed")
        with patch.object(protocol, "_get", return_value=record):
            with pytest.raises(ValueError, match="not pending"):
                await protocol.accept_with_packet("h-001")

    @pytest.mark.asyncio
    async def test_complete_with_packet_releases_and_emits(self, protocol):
        """complete_with_packet releases lease and emits HANDOFF_COMPLETED."""
        record = _make_record(budget_remaining_usd=5.0)
        with patch.object(protocol, "_get", return_value=record):
            result = await protocol.complete_with_packet("h-001", "Done", spent_usd=Decimal("1.00"))
        assert result.status == "completed"
        protocol.lease_integration.release.assert_awaited_once_with("h-001")
        events = protocol._event_log.append.call_args[0][2]
        assert events[0]["type"] == "handoff.completed"

    @pytest.mark.asyncio
    async def test_complete_with_overspend_raises_and_emits_budget_exhausted(self, protocol):
        """Overspend raises BudgetExceededError and emits BUDGET_EXHAUSTED."""
        record = _make_record(budget_remaining_usd=1.0)
        with patch.object(protocol, "_get", return_value=record), pytest.raises(BudgetExceededError):
            await protocol.complete_with_packet("h-001", "Partial", spent_usd=Decimal("5.00"))
        assert record.status == "failed"
        protocol.lease_integration.release.assert_awaited_once()
        events = protocol._event_log.append.call_args[0][2]
        assert events[0]["type"] == "handoff.budget_exhausted"

    @pytest.mark.asyncio
    async def test_backward_compat_delegate_still_works(self, protocol):
        """Old delegate() method still works (no typed fields set)."""
        with patch.object(protocol.registry, "get_capability", return_value=MagicMock(name="Agent B")):
            handoff = await protocol.delegate(
                from_agent_id="agent-a",
                from_agent_name="Agent A",
                task_description="Do something",
                to_agent_id="agent-b",
            )
        assert handoff.task_description == "Do something"
        assert handoff.goal is None  # typed field not set

    @pytest.mark.asyncio
    async def test_complete_with_packet_updates_remaining(self, protocol):
        """complete_with_packet correctly deducts spent from remaining."""
        record = _make_record(budget_remaining_usd=5.0)
        with patch.object(protocol, "_get", return_value=record):
            await protocol.complete_with_packet("h-001", "Done", spent_usd=Decimal("2.50"))
        assert float(record.budget_remaining_usd) == pytest.approx(2.5)

    @pytest.mark.asyncio
    async def test_delegate_with_depth_policy_state(self, protocol):
        """Packet with depth_policy_state persists it."""
        packet = _make_packet(
            depth_policy_state=HandoffDepthPolicyState(
                last_level="deep",
                last_reason="complex task",
                policy_version="1.0",
                decision_count=3,
            )
        )
        await protocol.delegate_with_packet(packet)
        added = protocol.db.add.call_args[0][0]
        assert added.depth_policy_state is not None
        assert added.depth_policy_state["last_level"] == "deep"

    @pytest.mark.asyncio
    async def test_delegate_with_retrieved_context_ids(self, protocol):
        """Packet with retrieved_context_ids persists them."""
        packet = _make_packet(
            retrieved_context_ids=["ep-001", "ep-002"],
            tool_candidates=["web_search", "code_edit"],
        )
        await protocol.delegate_with_packet(packet)
        added = protocol.db.add.call_args[0][0]
        assert added.retrieved_context_ids == ["ep-001", "ep-002"]
        assert added.tool_candidates == ["web_search", "code_edit"]

    @pytest.mark.asyncio
    async def test_accept_with_packet_not_found_raises(self, protocol):
        """accept_with_packet on missing handoff raises ValueError."""
        with patch.object(protocol, "_get", return_value=None), pytest.raises(ValueError, match="not found"):
            await protocol.accept_with_packet("h-nonexistent")

    @pytest.mark.asyncio
    async def test_accept_with_packet_emits_lease_lost_when_renew_fails(self, protocol):
        """If renew() returns False, HANDOFF_LEASE_LOST is emitted and
        accept still completes (fail-open)."""
        record = _make_record(status="pending", budget_remaining_usd=1.0)
        protocol.lease_integration.renew = AsyncMock(return_value=False)
        with patch.object(protocol, "_get", return_value=record):
            packet = await protocol.accept_with_packet("h-001")
        assert record.status == "accepted"
        assert isinstance(packet, HandoffPacket)
        # Both HANDOFF_LEASE_LOST and HANDOFF_ACCEPTED are emitted.
        # event_log.append is called twice in this flow.
        call_args_list = protocol._event_log.append.call_args_list
        emitted_types = [c[0][2][0]["type"] for c in call_args_list]
        assert "handoff.lease_lost" in emitted_types
        assert "handoff.accepted" in emitted_types

    @pytest.mark.asyncio
    async def test_packet_from_record_old_record_fallback(self):
        """_packet_from_record handles pre-chunk-5 records where
        from_agent_name/success_criteria/typed-fields are NULL."""
        from app.services.swarm.handoff_protocol import HandoffProtocol

        db = _mock_db()
        hp = HandoffProtocol(db)
        record = _make_record(
            status="completed",
            goal=None,  # pre-chunk-5 record
            success_criteria=None,  # pre-chunk-5 record
            retrieved_context_ids=None,
            tool_candidates=None,
            budget_remaining_usd=None,
            hitl_state=None,
            depth_policy_state=None,
        )
        packet = hp._packet_from_record(record)
        assert packet.goal == record.task_description  # fallback to task_description
        assert packet.success_criteria == [record.task_description]
        assert packet.retrieved_context_ids == []
        assert packet.tool_candidates == []
        assert packet.budget.remaining_usd == Decimal("0")
        assert packet.depth_policy_state is None
