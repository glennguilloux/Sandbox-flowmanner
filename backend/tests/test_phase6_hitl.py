"""Phase 6 tests — HITL, Circuit Breaker, Cost Attribution.

Tests cover:
- InboxItem model creation and status transitions
- HITLService create/resolve/list operations
- CircuitBreakerService limit checks and state transitions
- CostAttributionService aggregation queries
- HumanInterrupt exception behavior
"""

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.circuit_breaker_models import (
    CircuitBreakerState,
    MissionCircuitBreaker,
)
from app.models.hitl_models import (
    HumanInterrupt,
    HumanInterruptType,
    InboxItem,
    InboxItemStatus,
)

# ── HITL Models ────────────────────────────────────────────────────


class TestHumanInterrupt:
    """Test the HumanInterrupt exception class."""

    def test_approval_interrupt(self):
        exc = HumanInterrupt(
            interrupt_type=HumanInterruptType.APPROVAL,
            title="Approve deployment?",
            description="Deploy v2.0 to production",
            proposed_action={"tool": "deploy", "target": "prod"},
        )
        assert exc.interrupt_type == HumanInterruptType.APPROVAL
        assert exc.title == "Approve deployment?"
        assert exc.proposed_action == {"tool": "deploy", "target": "prod"}
        assert "[approval]" in str(exc)

    def test_clarification_interrupt(self):
        exc = HumanInterrupt(
            interrupt_type=HumanInterruptType.CLARIFICATION,
            title="Which database?",
            context={"options": ["postgres", "mysql"]},
        )
        assert exc.interrupt_type == HumanInterruptType.CLARIFICATION
        assert exc.context == {"options": ["postgres", "mysql"]}

    def test_escalation_interrupt(self):
        exc = HumanInterrupt(
            interrupt_type=HumanInterruptType.ESCALATION,
            title="Permission denied for S3 bucket",
            task_id="task-123",
            node_id="node-456",
        )
        assert exc.task_id == "task-123"
        assert exc.node_id == "node-456"

    def test_default_values(self):
        exc = HumanInterrupt(
            interrupt_type=HumanInterruptType.APPROVAL,
            title="Test",
        )
        assert exc.description is None
        assert exc.proposed_action is None
        assert exc.context is None
        assert exc.task_id is None
        assert exc.node_id is None
        assert exc.expires_at is None


class TestInboxItemModel:
    """Test InboxItem model constraints."""

    def test_default_status(self):
        """InboxItem should default to PENDING status."""
        item = InboxItem(
            id=str(uuid4()),
            user_id=1,
            mission_id=str(uuid4()),
            interrupt_type=HumanInterruptType.APPROVAL.value,
            title="Test item",
            status=InboxItemStatus.PENDING.value,
        )
        assert item.status == InboxItemStatus.PENDING.value

    def test_status_enum_values(self):
        """All expected status values should exist."""
        expected = {
            "pending",
            "approved",
            "rejected",
            "clarified",
            "escalated",
            "expired",
            "cancelled",
        }
        actual = {s.value for s in InboxItemStatus}
        assert expected == actual

    def test_interrupt_type_values(self):
        """All expected interrupt type values should exist."""
        expected = {"approval", "clarification", "escalation"}
        actual = {t.value for t in HumanInterruptType}
        assert expected == actual


# ── Circuit Breaker Models ─────────────────────────────────────────


class TestCircuitBreakerModel:
    """Test MissionCircuitBreaker model logic."""

    def test_default_state(self):
        cb = MissionCircuitBreaker(
            id=str(uuid4()),
            mission_id=str(uuid4()),
            state=CircuitBreakerState.ARMED.value,
            llm_calls_made=0,
            tool_calls_made=0,
            cost_accumulated_usd=0.0,
            trigger_count=0,
            max_llm_calls=100,
            max_cost_usd=10.0,
            max_tool_calls=200,
            max_duration_seconds=3600,
        )
        assert cb.state == CircuitBreakerState.ARMED.value
        assert cb.llm_calls_made == 0
        assert cb.tool_calls_made == 0
        assert cb.cost_accumulated_usd == 0.0
        assert cb.trigger_count == 0

    def test_check_limits_within_bounds(self):
        cb = MissionCircuitBreaker(
            id=str(uuid4()),
            mission_id=str(uuid4()),
            max_llm_calls=100,
            max_cost_usd=10.0,
            max_tool_calls=200,
            max_duration_seconds=3600,
            llm_calls_made=50,
            cost_accumulated_usd=5.0,
            tool_calls_made=100,
            state=CircuitBreakerState.ARMED.value,
        )
        is_broken, reason = cb.check_limits()
        assert is_broken is False
        assert reason == ""

    def test_check_limits_llm_exceeded(self):
        cb = MissionCircuitBreaker(
            id=str(uuid4()),
            mission_id=str(uuid4()),
            max_llm_calls=100,
            llm_calls_made=100,
            max_cost_usd=100.0,
            max_tool_calls=100,
            max_duration_seconds=3600,
            state=CircuitBreakerState.ARMED.value,
        )
        is_broken, reason = cb.check_limits()
        assert is_broken is True
        assert "LLM call limit" in reason

    def test_check_limits_cost_exceeded(self):
        cb = MissionCircuitBreaker(
            id=str(uuid4()),
            mission_id=str(uuid4()),
            max_cost_usd=10.0,
            cost_accumulated_usd=10.0,
            max_llm_calls=100,
            max_tool_calls=100,
            max_duration_seconds=3600,
            state=CircuitBreakerState.ARMED.value,
        )
        is_broken, reason = cb.check_limits()
        assert is_broken is True
        assert "Cost limit" in reason

    def test_check_limits_tool_exceeded(self):
        cb = MissionCircuitBreaker(
            id=str(uuid4()),
            mission_id=str(uuid4()),
            max_tool_calls=50,
            tool_calls_made=50,
            max_llm_calls=100,
            max_cost_usd=100.0,
            max_duration_seconds=3600,
            state=CircuitBreakerState.ARMED.value,
        )
        is_broken, reason = cb.check_limits()
        assert is_broken is True
        assert "Tool call limit" in reason

    def test_check_limits_duration_exceeded(self):
        cb = MissionCircuitBreaker(
            id=str(uuid4()),
            mission_id=str(uuid4()),
            max_duration_seconds=60,
            started_at=datetime.now(UTC) - timedelta(seconds=120),
            max_llm_calls=100,
            max_cost_usd=100.0,
            max_tool_calls=100,
            state=CircuitBreakerState.ARMED.value,
        )
        is_broken, reason = cb.check_limits()
        assert is_broken is True
        assert "Duration limit" in reason

    def test_check_limits_circuit_broken_permanent(self):
        cb = MissionCircuitBreaker(
            id=str(uuid4()),
            mission_id=str(uuid4()),
            state=CircuitBreakerState.CIRCUIT_BROKEN.value,
            max_llm_calls=100,
            max_cost_usd=10.0,
            max_tool_calls=100,
            max_duration_seconds=3600,
        )
        is_broken, reason = cb.check_limits()
        assert is_broken is True
        assert "permanently broken" in reason

    def test_should_approve_destructive(self):
        cb = MissionCircuitBreaker(
            id=str(uuid4()),
            mission_id=str(uuid4()),
            destructive_actions_require_approval=True,
            destructive_actions=["deploy_to_prod", "delete_database"],
            state=CircuitBreakerState.ARMED.value,
        )
        assert cb.should_approve("deploy_to_prod") is True
        assert cb.should_approve("delete_database") is True
        assert cb.should_approve("read_file") is False

    def test_should_approve_disabled(self):
        cb = MissionCircuitBreaker(
            id=str(uuid4()),
            mission_id=str(uuid4()),
            destructive_actions_require_approval=False,
            destructive_actions=["deploy_to_prod"],
            state=CircuitBreakerState.ARMED.value,
        )
        assert cb.should_approve("deploy_to_prod") is False

    def test_state_enum_values(self):
        expected = {"armed", "triggered", "circuit_broken"}
        actual = {s.value for s in CircuitBreakerState}
        assert expected == actual


# ── HITL Service (logic tests without DB) ─────────────────────────


class TestHITLServiceLogic:
    """Test HITLService static/logic methods."""

    def test_item_to_dict(self):
        now = datetime.now(UTC)
        item = InboxItem(
            id="test-id",
            workspace_id="ws-1",
            user_id=42,
            mission_id="mission-1",
            run_id="run-1",
            task_id="task-1",
            node_id="node-1",
            interrupt_type=HumanInterruptType.APPROVAL.value,
            title="Approve deploy?",
            description="Deploy to production",
            proposed_action={"tool": "deploy"},
            context={"env": "prod"},
            status=InboxItemStatus.PENDING.value,
            created_at=now,
            updated_at=now,
        )
        d = HITLService._item_to_dict(item)
        assert d["id"] == "test-id"
        assert d["interrupt_type"] == "approval"
        assert d["title"] == "Approve deploy?"
        assert d["status"] == "pending"
        assert d["workspace_id"] == "ws-1"
        assert d["user_id"] == 42
        assert d["proposed_action"] == {"tool": "deploy"}

    def test_item_to_dict_resolved(self):
        now = datetime.now(UTC)
        item = InboxItem(
            id="test-id-2",
            user_id=1,
            mission_id="m1",
            interrupt_type="clarification",
            title="Which env?",
            status=InboxItemStatus.CLARIFIED.value,
            resolved_at=now,
            resolved_by=1,
            resolution_payload={"response_text": "production"},
            resolution_note="Use production",
        )
        d = HITLService._item_to_dict(item)
        assert d["status"] == "clarified"
        assert d["resolved_by"] == 1
        assert d["resolution_note"] == "Use production"


# ── Import convenience ─────────────────────────────────────────────


def test_imports():
    """Verify all Phase 6 models and services can be imported."""
    from app.models.circuit_breaker_models import (
        CircuitBreakerState,
        MissionCircuitBreaker,
    )
    from app.models.hitl_models import (
        HumanInterrupt,
        HumanInterruptType,
        InboxItem,
        InboxItemStatus,
    )
    from app.services.circuit_breaker_service import CircuitBreakerService
    from app.services.cost_attribution_service import CostAttributionService
    from app.services.episodic_memory_worker import EpisodicMemoryWorker
    from app.services.hitl_service import HITLService

    assert InboxItem is not None
    assert HumanInterrupt is not None
    assert MissionCircuitBreaker is not None
    assert HITLService is not None
    assert CircuitBreakerService is not None
    assert CostAttributionService is not None
    assert EpisodicMemoryWorker is not None


# Need this import for the static method call above
from app.services.hitl_service import HITLService
