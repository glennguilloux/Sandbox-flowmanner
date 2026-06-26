"""Unit tests for the adaptive reasoning depth feature (Q2-Q3 Chunk 4).

Comprehensive coverage of:
- DepthPolicy: deterministic decision logic, priority ordering, HITL escalation
- DepthLevel / DepthDecision / DepthTriggeredEvent: Pydantic model validation
- API endpoints: POST /depth/decide, GET /missions/{id}/depth-events

Usage:
    pytest tests/test_depth_policy.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.depth_models import (
    DepthDecision,
    DepthLevel,
    DepthTriggeredEvent,
)
from app.services.depth_policy import REFLECTION_ITERATIONS, DepthPolicy

# ═══════════════════════════════════════════════════════════════════════════
# DepthLevel Enum
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthLevel:
    """Verify DepthLevel enum values and string representation."""

    def test_has_three_levels(self):
        assert len(DepthLevel) == 3

    def test_string_values(self):
        assert DepthLevel.SHALLOW.value == "shallow"
        assert DepthLevel.NORMAL.value == "normal"
        assert DepthLevel.DEEP.value == "deep"

    def test_str_coercion(self):
        assert str(DepthLevel.SHALLOW) == "DepthLevel.SHALLOW"

    def test_reflection_iterations_map(self):
        assert REFLECTION_ITERATIONS[DepthLevel.SHALLOW] == 0
        assert REFLECTION_ITERATIONS[DepthLevel.NORMAL] == 1
        assert REFLECTION_ITERATIONS[DepthLevel.DEEP] == 3


# ═══════════════════════════════════════════════════════════════════════════
# DepthDecision Model
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthDecision:
    """Verify DepthDecision Pydantic model construction and defaults."""

    def test_minimal_construction(self):
        d = DepthDecision(
            level=DepthLevel.NORMAL,
            reason="test",
        )
        assert d.level == DepthLevel.NORMAL
        assert d.reason == "test"
        assert d.escalate_to_hitl is False
        assert d.hitl_reason is None
        assert d.policy_version == "v1.0.0"
        assert d.estimated_reflection_iterations == 0

    def test_full_construction(self):
        d = DepthDecision(
            level=DepthLevel.DEEP,
            reason="risk=high",
            escalate_to_hitl=True,
            hitl_reason="tool_requires_approval",
            policy_version="v2.0.0",
            estimated_reflection_iterations=3,
        )
        assert d.level == DepthLevel.DEEP
        assert d.escalate_to_hitl is True
        assert d.hitl_reason == "tool_requires_approval"
        assert d.policy_version == "v2.0.0"
        assert d.estimated_reflection_iterations == 3

    def test_from_attributes(self):
        """DepthDecision should be constructable from dict (API response pattern)."""
        data = {
            "level": "shallow",
            "reason": "budget preservation",
            "escalate_to_hitl": False,
            "hitl_reason": None,
            "policy_version": "v1.0.0",
            "estimated_reflection_iterations": 0,
        }
        d = DepthDecision(**data)
        assert d.level == DepthLevel.SHALLOW


# ═══════════════════════════════════════════════════════════════════════════
# DepthTriggeredEvent Model
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthTriggeredEvent:
    """Verify DepthTriggeredEvent construction and field defaults."""

    def test_minimal_construction(self):
        event = DepthTriggeredEvent(
            level="deep",
            reason="risk=high",
            risk="high",
            uncertainty=0.8,
            budget_remaining_usd=5.0,
            prior_failures=2,
            retry_count=1,
            escalate_to_hitl=False,
            hitl_reason=None,
            policy_version="v1.0.0",
        )
        assert event.level == "deep"
        assert event.step_id is None
        assert event.mission_id is None
        assert event.workspace_id is None
        assert event.user_id is None
        assert event.estimated_reflection_iterations == 0

    def test_full_construction(self):
        event = DepthTriggeredEvent(
            level="shallow",
            reason="all signals low",
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=3.50,
            prior_failures=0,
            retry_count=0,
            escalate_to_hitl=False,
            hitl_reason=None,
            policy_version="v1.0.0",
            step_id="step-1",
            mission_id="m-1",
            workspace_id="ws-1",
            user_id=42,
            estimated_reflection_iterations=0,
        )
        assert event.step_id == "step-1"
        assert event.mission_id == "m-1"
        assert event.workspace_id == "ws-1"
        assert event.user_id == 42

    def test_model_dump_roundtrip(self):
        """model_dump should produce a dict that reconstructs the event."""
        event = DepthTriggeredEvent(
            level="normal",
            reason="risk=medium",
            risk="medium",
            uncertainty=0.5,
            budget_remaining_usd=2.0,
            prior_failures=0,
            retry_count=0,
            escalate_to_hitl=False,
            hitl_reason=None,
            policy_version="v1.0.0",
        )
        data = event.model_dump()
        restored = DepthTriggeredEvent(**data)
        assert restored.level == event.level
        assert restored.reason == event.reason
        assert restored.risk == event.risk


# ═══════════════════════════════════════════════════════════════════════════
# DepthPolicy — Risk Signal
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthPolicyRiskSignal:
    """Test risk → depth mapping."""

    def setup_method(self):
        self.policy = DepthPolicy()

    def test_high_risk_forces_deep(self):
        d = self.policy.decide(
            risk="high",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP
        assert "risk=high" in d.reason

    def test_medium_risk_forces_normal(self):
        d = self.policy.decide(
            risk="medium",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.NORMAL
        assert "risk=medium" in d.reason

    def test_low_risk_suggests_shallow(self):
        """Low risk with all other signals low should result in shallow."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.SHALLOW


# ═══════════════════════════════════════════════════════════════════════════
# DepthPolicy — Uncertainty Signal
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthPolicyUncertaintySignal:
    """Test uncertainty → depth mapping."""

    def setup_method(self):
        self.policy = DepthPolicy()

    def test_high_uncertainty_forces_deep(self):
        """Uncertainty > 0.7 should force deep (priority 90)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.8,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP
        assert "uncertainty" in d.reason

    def test_medium_uncertainty_suggests_normal(self):
        """Uncertainty 0.3-0.7 should suggest normal (priority 30)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.5,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.NORMAL

    def test_low_uncertainty_suggests_shallow(self):
        """Uncertainty < 0.3 should suggest shallow."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.SHALLOW

    def test_uncertainty_at_boundary_03(self):
        """Uncertainty exactly at 0.3 → normal (>= 0.3)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.3,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.NORMAL

    def test_uncertainty_at_boundary_07(self):
        """Uncertainty exactly at 0.7 → normal (not > 0.7)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.7,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.NORMAL

    def test_uncertainty_just_above_07(self):
        """Uncertainty at 0.71 → deep (> 0.7)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.71,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP


# ═══════════════════════════════════════════════════════════════════════════
# DepthPolicy — Budget Signal
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthPolicyBudgetSignal:
    """Test budget → depth mapping."""

    def setup_method(self):
        self.policy = DepthPolicy()

    def test_low_budget_forces_shallow(self):
        """Budget below threshold should force shallow (priority 80)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("0.05"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.SHALLOW
        assert "budget" in d.reason.lower()

    def test_adequate_budget_suggests_normal(self):
        """Budget above threshold should suggest normal (priority 5)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        # With risk=low, uncertainty<0.3, no failures, adequate budget → shallow
        # (the low risk signal at priority 10 still beats budget's priority 5)
        assert d.level == DepthLevel.SHALLOW

    def test_budget_at_threshold(self):
        """Budget exactly at $0.10 → normal (not < 0.10)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("0.10"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.SHALLOW

    def test_budget_just_below_threshold(self):
        """Budget at $0.09 → shallow (< 0.10)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("0.09"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.SHALLOW

    def test_zero_budget_forces_shallow(self):
        """Zero budget → shallow."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("0.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.SHALLOW


# ═══════════════════════════════════════════════════════════════════════════
# DepthPolicy — Prior Failures Signal
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthPolicyPriorFailuresSignal:
    """Test prior_failures → depth mapping."""

    def setup_method(self):
        self.policy = DepthPolicy()

    def test_many_failures_forces_deep(self):
        """prior_failures >= 2 should force deep (priority 70)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=2,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP
        assert "prior_failures" in d.reason

    def test_one_failure_suggests_normal(self):
        """prior_failures = 1 should suggest normal (priority 20)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=1,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.NORMAL

    def test_zero_failures_suggests_shallow(self):
        """prior_failures = 0 → shallow."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.SHALLOW

    def test_many_failures_at_threshold(self):
        """prior_failures exactly at threshold (2) → deep."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=2,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP

    def test_excessive_failures_still_deep(self):
        """prior_failures = 100 → deep (not a different level)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=100,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP


# ═══════════════════════════════════════════════════════════════════════════
# DepthPolicy — Priority Ordering
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthPolicyPriorityOrdering:
    """Verify that the highest-priority signal wins when multiple conflict."""

    def setup_method(self):
        self.policy = DepthPolicy()

    def test_high_risk_beats_low_budget(self):
        """Risk=high (priority 100) beats budget=preservation (priority 80)."""
        d = self.policy.decide(
            risk="high",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("0.01"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP
        assert "risk=high" in d.reason

    def test_high_uncertainty_beats_low_budget(self):
        """Uncertainty>0.7 (priority 90) beats budget=preservation (priority 80)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.9,
            budget_remaining_usd=Decimal("0.01"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP
        assert "uncertainty" in d.reason

    def test_low_budget_beats_prior_failures_one(self):
        """Budget preservation (priority 80) beats prior_failures=1 (priority 20)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("0.05"),
            prior_failures=1,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.SHALLOW
        assert "budget" in d.reason.lower()

    def test_prior_failures_beats_medium_uncertainty(self):
        """prior_failures>=2 (priority 70) beats uncertainty=0.5 (priority 30)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.5,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=3,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP
        assert "prior_failures" in d.reason

    def test_high_risk_beats_high_uncertainty(self):
        """Both deep, but risk=high (priority 100) is the winner reason."""
        d = self.policy.decide(
            risk="high",
            uncertainty=0.9,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP
        assert "risk=high" in d.reason

    def test_all_signals_low_is_shallow(self):
        """Every signal at minimum → shallow (default)."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.0,
            budget_remaining_usd=Decimal("100.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.SHALLOW
        assert d.escalate_to_hitl is False

    def test_all_signals_high_is_deep(self):
        """Every signal at maximum → deep (highest priority wins)."""
        d = self.policy.decide(
            risk="high",
            uncertainty=1.0,
            budget_remaining_usd=Decimal("100.00"),
            prior_failures=10,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP


# ═══════════════════════════════════════════════════════════════════════════
# DepthPolicy — HITL Escalation
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthPolicyHITLEscalation:
    """Test HITL escalation rules (separate from level selection)."""

    def setup_method(self):
        self.policy = DepthPolicy()

    def test_tool_requires_approval_escalates(self):
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=True,
            retry_count=0,
        )
        assert d.escalate_to_hitl is True
        assert d.hitl_reason == "tool_requires_approval"
        assert d.level == DepthLevel.DEEP  # HITL forces deep

    def test_policy_override_bypasses_approval(self):
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=True,
            retry_count=0,
            policy_override=True,
        )
        assert d.escalate_to_hitl is False
        assert d.hitl_reason is None

    def test_retry_exhausted_escalates(self):
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=3,
        )
        assert d.escalate_to_hitl is True
        assert d.hitl_reason == "retry_exhausted"

    def test_persistent_failure_escalates(self):
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=3,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.escalate_to_hitl is True
        assert d.hitl_reason == "persistent_failure"

    def test_retry_below_threshold_no_escalation(self):
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=2,
        )
        assert d.escalate_to_hitl is False

    def test_hitl_forces_deep_level(self):
        """When HITL escalates, the level must always be deep."""
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=True,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP

    def test_hitl_reason_appended_to_main_reason(self):
        d = self.policy.decide(
            risk="medium",
            uncertainty=0.5,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=True,
            retry_count=0,
        )
        assert "HITL: tool_requires_approval" in d.reason

    def test_custom_hitl_retry_threshold(self):
        policy = DepthPolicy(hitl_retry_threshold=5)
        d = policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=4,
        )
        assert d.escalate_to_hitl is False  # 4 < 5

        d2 = policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=5,
        )
        assert d2.escalate_to_hitl is True


# ═══════════════════════════════════════════════════════════════════════════
# DepthPolicy — Custom Thresholds
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthPolicyCustomThresholds:
    """Verify custom constructor thresholds are respected."""

    def test_custom_uncertainty_threshold(self):
        policy = DepthPolicy(deep_uncertainty_threshold=0.9)
        # 0.8 is below custom threshold 0.9
        d = policy.decide(
            risk="low",
            uncertainty=0.8,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.NORMAL  # not deep

    def test_custom_budget_threshold(self):
        policy = DepthPolicy(shallow_budget_threshold_usd=Decimal("1.00"))
        d = policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("0.50"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.SHALLOW  # 0.50 < 1.00

    def test_custom_failure_threshold(self):
        # Use prior_failures=2 to avoid triggering HITL escalation
        # (default hitl_retry_threshold=3, so 2 < 3 won't escalate).
        # With default deep_prior_failure_threshold=2: 2 >= 2 → DEEP (priority 70)
        # With custom deep_prior_failure_threshold=5: 2 < 5, 2 > 0 → NORMAL (priority 20)
        default_policy = DepthPolicy()  # deep_prior_failure_threshold=2
        d_default = default_policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=2,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d_default.level == DepthLevel.DEEP  # 2 >= 2 (default threshold)

        custom_policy = DepthPolicy(deep_prior_failure_threshold=5)
        d_custom = custom_policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=2,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d_custom.level == DepthLevel.NORMAL  # 2 < 5 (custom threshold)

    def test_custom_policy_version(self):
        policy = DepthPolicy(policy_version="v2.1.0")
        d = policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.policy_version == "v2.1.0"


# ═══════════════════════════════════════════════════════════════════════════
# DepthPolicy — Determinism
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthPolicyDeterminism:
    """The policy must be fully deterministic — same inputs → same outputs."""

    def test_same_inputs_same_output(self):
        policy = DepthPolicy()
        kwargs = {
            "risk": "medium",
            "uncertainty": 0.55,
            "budget_remaining_usd": Decimal("2.50"),
            "prior_failures": 1,
            "tool_requires_approval": False,
            "retry_count": 0,
        }
        results = [policy.decide(**kwargs) for _ in range(10)]
        levels = {r.level for r in results}
        reasons = {r.reason for r in results}
        assert len(levels) == 1
        assert len(reasons) == 1

    def test_no_randomness_in_1000_calls(self):
        """Stress test: 1000 calls must all return identical results."""
        policy = DepthPolicy()
        kwargs = {
            "risk": "high",
            "uncertainty": 0.95,
            "budget_remaining_usd": Decimal("0.01"),
            "prior_failures": 5,
            "tool_requires_approval": True,
            "retry_count": 10,
        }
        results = [policy.decide(**kwargs) for _ in range(1000)]
        assert all(r.level == results[0].level for r in results)
        assert all(r.reason == results[0].reason for r in results)
        assert all(r.escalate_to_hitl == results[0].escalate_to_hitl for r in results)


# ═══════════════════════════════════════════════════════════════════════════
# DepthPolicy — Audit Event Builder
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthPolicyAuditEvent:
    """Test build_audit_event() produces correct payloads."""

    def setup_method(self):
        self.policy = DepthPolicy()

    def test_audit_event_carries_all_signals(self):
        d = self.policy.decide(
            risk="medium",
            uncertainty=0.5,
            budget_remaining_usd=Decimal("2.50"),
            prior_failures=1,
            tool_requires_approval=False,
            retry_count=0,
        )
        event = self.policy.build_audit_event(
            d,
            risk="medium",
            uncertainty=0.5,
            budget_remaining_usd=Decimal("2.50"),
            prior_failures=1,
            retry_count=0,
            step_id="t-1",
            mission_id="m-1",
            workspace_id="ws-1",
            user_id=42,
        )
        assert event.risk == "medium"
        assert event.uncertainty == 0.5
        assert event.budget_remaining_usd == 2.5
        assert event.prior_failures == 1
        assert event.step_id == "t-1"
        assert event.mission_id == "m-1"
        assert event.workspace_id == "ws-1"
        assert event.user_id == 42

    def test_audit_event_no_raw_text(self):
        """Audit events must not contain task text or tool input."""
        d = self.policy.decide(
            risk="high",
            uncertainty=0.9,
            budget_remaining_usd=Decimal("1.00"),
            prior_failures=2,
            tool_requires_approval=True,
            retry_count=3,
        )
        event = self.policy.build_audit_event(
            d,
            risk="high",
            uncertainty=0.9,
            budget_remaining_usd=Decimal("1.00"),
            prior_failures=2,
            retry_count=3,
        )
        data = event.model_dump()
        for key in data:
            assert "task_text" not in key.lower()
            assert "tool_input" not in key.lower()
            assert "prompt" not in key.lower()

    def test_audit_event_includes_hitl_fields(self):
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=True,
            retry_count=0,
        )
        event = self.policy.build_audit_event(
            d,
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            retry_count=0,
        )
        assert event.escalate_to_hitl is True
        assert event.hitl_reason == "tool_requires_approval"


# ═══════════════════════════════════════════════════════════════════════════
# DepthPolicy — Reflection Iterations
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthPolicyReflectionIterations:
    """Verify estimated_reflection_iterations maps correctly to each level."""

    def setup_method(self):
        self.policy = DepthPolicy()

    def test_shallow_zero_iterations(self):
        d = self.policy.decide(
            risk="low",
            uncertainty=0.0,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.SHALLOW
        assert d.estimated_reflection_iterations == 0

    def test_normal_one_iteration(self):
        d = self.policy.decide(
            risk="medium",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.NORMAL
        assert d.estimated_reflection_iterations == 1

    def test_deep_three_iterations(self):
        d = self.policy.decide(
            risk="high",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert d.level == DepthLevel.DEEP
        assert d.estimated_reflection_iterations == 3

    def test_hitl_escalation_forces_three_iterations(self):
        d = self.policy.decide(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=True,
            retry_count=0,
        )
        assert d.estimated_reflection_iterations == 3


# ═══════════════════════════════════════════════════════════════════════════
# API: POST /depth/decide
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthDecideEndpoint:
    """Test the POST /depth/decide API endpoint."""

    @pytest.mark.asyncio
    async def test_decide_returns_correct_response(self):
        from app.api.v1.depth import DepthDecideRequest, decide_depth

        request = DepthDecideRequest(
            risk="high",
            uncertainty=0.8,
            budget_remaining_usd=5.0,
            prior_failures=2,
            tool_requires_approval=False,
            retry_count=0,
        )
        response = await decide_depth(request)

        assert response.level == "deep"
        assert response.policy_version == "v1.0.0"
        assert response.estimated_reflection_iterations == 3
        assert isinstance(response.reason, str)
        assert len(response.reason) > 0

    @pytest.mark.asyncio
    async def test_decide_shallow_budget_preservation(self):
        from app.api.v1.depth import DepthDecideRequest, decide_depth

        request = DepthDecideRequest(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=0.05,
            prior_failures=0,
        )
        response = await decide_depth(request)

        assert response.level == "shallow"
        assert response.escalate_to_hitl is False

    @pytest.mark.asyncio
    async def test_decide_hitl_escalation(self):
        from app.api.v1.depth import DepthDecideRequest, decide_depth

        request = DepthDecideRequest(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=5.0,
            tool_requires_approval=True,
        )
        response = await decide_depth(request)

        assert response.escalate_to_hitl is True
        assert response.hitl_reason == "tool_requires_approval"
        assert response.level == "deep"

    @pytest.mark.asyncio
    async def test_decide_with_policy_override(self):
        from app.api.v1.depth import DepthDecideRequest, decide_depth

        request = DepthDecideRequest(
            risk="low",
            uncertainty=0.1,
            budget_remaining_usd=5.0,
            tool_requires_approval=True,
            policy_override=True,
        )
        response = await decide_depth(request)

        assert response.escalate_to_hitl is False


# ═══════════════════════════════════════════════════════════════════════════
# API: GET /missions/{mission_id}/depth-events
# ═══════════════════════════════════════════════════════════════════════════


class TestDepthEventsEndpoint:
    """Test the GET /missions/{mission_id}/depth-events API endpoint."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_events(self):
        from app.api.v1.depth import get_depth_events

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        events = await get_depth_events(mission_id=str(uuid4()), db=db)
        assert events == []

    @pytest.mark.asyncio
    async def test_returns_events_in_order(self):
        from app.api.v1.depth import get_depth_events
        from app.models.substrate_models import SubstrateEventType

        mission_id = str(uuid4())
        now = datetime.now(UTC)

        mock_events = [
            MagicMock(
                id=uuid4(),
                sequence=1,
                type=SubstrateEventType.DEPTH_DECIDED,
                payload={"level": "shallow", "reason": "all low"},
                actor="depth_policy",
                timestamp=now,
                mission_id=mission_id,
                task_id="t-1",
            ),
            MagicMock(
                id=uuid4(),
                sequence=2,
                type=SubstrateEventType.DEPTH_DECIDED,
                payload={"level": "deep", "reason": "risk=high"},
                actor="depth_policy",
                timestamp=now,
                mission_id=mission_id,
                task_id="t-2",
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_events
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        events = await get_depth_events(mission_id=mission_id, db=db)

        assert len(events) == 2
        # Verify ordering: sequence numbers are ascending
        assert events[0].sequence < events[1].sequence
        assert events[0].payload["level"] == "shallow"
        assert events[1].payload["level"] == "deep"

    @pytest.mark.asyncio
    async def test_events_contain_mission_id(self):
        from app.api.v1.depth import get_depth_events

        mission_id = str(uuid4())
        now = datetime.now(UTC)

        mock_event = MagicMock(
            id=uuid4(),
            sequence=1,
            type="depth_decided",
            payload={},
            actor="depth_policy",
            timestamp=now,
            mission_id=mission_id,
            task_id=None,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_event]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        events = await get_depth_events(mission_id=mission_id, db=db)
        assert events[0].mission_id == mission_id

    @pytest.mark.asyncio
    async def test_events_timestamp_is_isoformat(self):
        from app.api.v1.depth import get_depth_events

        mission_id = str(uuid4())
        now = datetime.now(UTC)

        mock_event = MagicMock(
            id=uuid4(),
            sequence=1,
            type="depth_decided",
            payload={},
            actor="depth_policy",
            timestamp=now,
            mission_id=mission_id,
            task_id=None,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_event]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        events = await get_depth_events(mission_id=mission_id, db=db)
        assert events[0].timestamp == now.isoformat()

    @pytest.mark.asyncio
    async def test_events_with_none_timestamp(self):
        from app.api.v1.depth import get_depth_events

        mission_id = str(uuid4())

        mock_event = MagicMock(
            id=uuid4(),
            sequence=1,
            type="depth_decided",
            payload={},
            actor="depth_policy",
            timestamp=None,
            mission_id=mission_id,
            task_id=None,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_event]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        events = await get_depth_events(mission_id=mission_id, db=db)
        assert events[0].timestamp == ""
