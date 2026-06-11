"""Tests for HITL backend primitives (H5.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.orchestration.human_interrupt import (
    HITLManager,
    HumanInterrupt,
    HumanInterruptRecord,
    get_hitl_manager,
)

# ═══════════════════════════════════════════════════════════════════
# HumanInterrupt dataclass
# ═══════════════════════════════════════════════════════════════════


class TestHumanInterruptDataclass:
    def test_creates_with_required_fields(self):
        hi = HumanInterrupt(mission_id=str(uuid4()), interrupt_type="approval")
        assert hi.mission_id
        assert hi.interrupt_type == "approval"
        assert hi.confidence == 0.5

    def test_to_dict_serializes(self):
        mid = str(uuid4())
        deadline = datetime(2026, 7, 1, tzinfo=UTC)
        hi = HumanInterrupt(
            mission_id=mid,
            interrupt_type="clarification",
            context={"question": "which model?"},
            proposed_action={"model": "deepseek-chat"},
            confidence=0.85,
            deadline=deadline,
        )
        d = hi.to_dict()
        assert d["mission_id"] == mid
        assert d["interrupt_type"] == "clarification"
        assert d["confidence"] == 0.85
        assert d["deadline"] == "2026-07-01T00:00:00+00:00"

    def test_interrupt_type_accepts_all_valid_values(self):
        for t in ("approval", "clarification", "escalation"):
            hi = HumanInterrupt(mission_id=str(uuid4()), interrupt_type=t)
            assert hi.interrupt_type == t


# ═══════════════════════════════════════════════════════════════════
# Persistence (raise + resolve)
# ═══════════════════════════════════════════════════════════════════


class TestInterruptPersistence:
    @pytest.mark.asyncio
    async def test_raise_interrupt_persists_record(self):
        mgr = HITLManager()
        db = AsyncMock(spec=AsyncSession)
        mid = str(uuid4())

        hi = HumanInterrupt(
            mission_id=mid,
            interrupt_type="approval",
            context={"action": "delete"},
            confidence=0.75,
        )
        await mgr.raise_interrupt(db, hi)

        calls = [c.args[0] for c in db.add.call_args_list]
        records = [o for o in calls if isinstance(o, HumanInterruptRecord)]
        assert len(records) == 1
        r = records[0]
        assert r.mission_id == mid
        assert r.interrupt_type == "approval"
        assert r.status == "pending"

    @pytest.mark.asyncio
    async def test_raise_interrupt_fires_listeners(self):
        mgr = HITLManager()
        db = AsyncMock(spec=AsyncSession)
        received = []

        async def listener(signal, interrupt):
            received.append((signal, interrupt.interrupt_type))

        mgr.on_interrupt_raised(listener)
        hi = HumanInterrupt(mission_id=str(uuid4()), interrupt_type="escalation")
        await mgr.raise_interrupt(db, hi)

        assert len(received) == 1
        assert received[0] == ("HUMAN_INTERRUPT_RAISED", "escalation")

    @pytest.mark.asyncio
    async def test_resolve_interrupt_approves(self):
        mgr = HITLManager()
        db = AsyncMock(spec=AsyncSession)
        intr_id = str(uuid4())

        record = HumanInterruptRecord(
            id=intr_id,
            mission_id=str(uuid4()),
            interrupt_type="approval",
            status="pending",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = record
        db.execute = AsyncMock(return_value=result_mock)

        ok = await mgr.resolve_interrupt(db, intr_id, "approved", "user-42")
        assert ok is True
        assert record.status == "approved"

    @pytest.mark.asyncio
    async def test_resolve_interrupt_rejects(self):
        mgr = HITLManager()
        db = AsyncMock(spec=AsyncSession)
        intr_id = str(uuid4())

        record = HumanInterruptRecord(
            id=intr_id,
            mission_id=str(uuid4()),
            interrupt_type="approval",
            status="pending",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = record
        db.execute = AsyncMock(return_value=result_mock)

        ok = await mgr.resolve_interrupt(db, intr_id, "rejected")
        assert ok is True
        assert record.status == "rejected"

    @pytest.mark.asyncio
    async def test_resolve_interrupt_not_found(self):
        mgr = HITLManager()
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        ok = await mgr.resolve_interrupt(db, str(uuid4()), "approved")
        assert ok is False

    @pytest.mark.asyncio
    async def test_resolve_interrupt_already_resolved(self):
        mgr = HITLManager()
        db = AsyncMock(spec=AsyncSession)
        intr_id = str(uuid4())
        record = HumanInterruptRecord(
            id=intr_id,
            mission_id=str(uuid4()),
            interrupt_type="approval",
            status="approved",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = record
        db.execute = AsyncMock(return_value=result_mock)

        ok = await mgr.resolve_interrupt(db, intr_id, "rejected")
        assert ok is False


# ═══════════════════════════════════════════════════════════════════
# list_pending()
# ═══════════════════════════════════════════════════════════════════


class TestListPending:
    @pytest.mark.asyncio
    async def test_returns_pending_records(self):
        mgr = HITLManager()
        db = AsyncMock(spec=AsyncSession)
        r1 = HumanInterruptRecord(
            id=str(uuid4()),
            mission_id=str(uuid4()),
            interrupt_type="approval",
            status="pending",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [r1]
        db.execute = AsyncMock(return_value=result_mock)

        pending = await mgr.list_pending(db)
        assert len(pending) == 1
        assert pending[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_filters_by_mission(self):
        mgr = HITLManager()
        db = AsyncMock(spec=AsyncSession)
        mid = str(uuid4())
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        await mgr.list_pending(db, mission_id=mid)
        db.execute.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# approval_required_for()
# ═══════════════════════════════════════════════════════════════════


class TestApprovalRequiredFor:
    def test_low_confidence_requires_approval(self):
        assert HITLManager.approval_required_for("read", confidence=0.5) is True

    def test_high_confidence_plain_action_does_not(self):
        assert HITLManager.approval_required_for("read", confidence=0.9) is False

    def test_destructive_prefix_requires_approval(self):
        assert HITLManager.approval_required_for("destructive_delete", confidence=1.0) is True

    def test_explicit_destructive_set(self):
        gate = {"delete_file", "transfer_funds"}
        assert HITLManager.approval_required_for("delete_file", confidence=1.0, destructive_actions=gate) is True
        assert HITLManager.approval_required_for("read", confidence=1.0, destructive_actions=gate) is False


# ═══════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════


class TestSingleton:
    def test_get_hitl_manager_returns_same_instance(self):
        m1 = get_hitl_manager()
        m2 = get_hitl_manager()
        assert m1 is m2
        assert isinstance(m1, HITLManager)
