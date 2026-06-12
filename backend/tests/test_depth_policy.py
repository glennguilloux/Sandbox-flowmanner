"""Tests for the depth policy — Q2-Q3 Chunk 4.

Unit tests for DepthPolicy.decide() covering:
- Happy path: low risk → shallow
- Medium risk → normal
- High risk → deep
- High uncertainty → deep
- Low budget → shallow (budget preservation)
- Many prior failures → deep
- Tool requires approval → HITL (unless override)
- Retry exhaustion → HITL
- Persistent failure → HITL
- Policy override with high-risk → deep, no HITL
- Audit event fields
- Policy version recorded in every decision
"""

from decimal import Decimal

import pytest

from app.models.depth_models import DepthDecision, DepthLevel, DepthTriggeredEvent
from app.services.depth_policy import DepthPolicy, REFLECTION_ITERATIONS


@pytest.fixture()
def policy() -> DepthPolicy:
    """Default depth policy with standard thresholds."""
    return DepthPolicy()


@pytest.fixture()
def custom_policy() -> DepthPolicy:
    """Depth policy with custom thresholds for edge-case testing."""
    return DepthPolicy(
        policy_version="v2.0.0",
        shallow_budget_threshold_usd=Decimal("0.50"),
        deep_uncertainty_threshold=0.6,
        deep_prior_failure_threshold=1,
        hitl_retry_threshold=2,
    )


# ── 1. Happy path: low risk + low uncertainty + high budget + 0 failures → shallow ──


class TestDepthPolicyHappyPath:
    def test_low_risk_low_uncertainty_high_budget_shallow(self, policy: DepthPolicy):
        """Low risk, low uncertainty, high budget, 0 failures → shallow."""
        decision = policy.decide(
            risk="low",
            uncertainty=0.2,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.level == DepthLevel.SHALLOW
        assert "risk=low" in decision.reason
        assert decision.escalate_to_hitl is False
        assert decision.hitl_reason is None
        assert decision.estimated_reflection_iterations == 0


# ── 2. Medium risk + medium uncertainty → normal ──────────────────────


class TestMediumRisk:
    def test_medium_risk_normal(self, policy: DepthPolicy):
        """Medium risk → normal."""
        decision = policy.decide(
            risk="medium",
            uncertainty=0.4,
            budget_remaining_usd=Decimal("2.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.level == DepthLevel.NORMAL
        assert "risk=medium" in decision.reason
        assert decision.escalate_to_hitl is False


# ── 3. High risk → deep ───────────────────────────────────────────────


class TestHighRisk:
    def test_high_risk_deep(self, policy: DepthPolicy):
        """High risk → deep."""
        decision = policy.decide(
            risk="high",
            uncertainty=0.3,
            budget_remaining_usd=Decimal("2.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.level == DepthLevel.DEEP
        assert "risk=high" in decision.reason
        assert decision.estimated_reflection_iterations == 3
        assert decision.escalate_to_hitl is False


# ── 4. High uncertainty → deep ────────────────────────────────────────


class TestHighUncertainty:
    def test_high_uncertainty_deep(self, policy: DepthPolicy):
        """Uncertainty > 0.7 → deep."""
        decision = policy.decide(
            risk="low",
            uncertainty=0.85,
            budget_remaining_usd=Decimal("2.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.level == DepthLevel.DEEP
        assert "uncertainty=0.85" in decision.reason
        assert decision.escalate_to_hitl is False


# ── 5. Low budget → shallow (budget preservation) ─────────────────────


class TestLowBudget:
    def test_low_budget_shallow(self, policy: DepthPolicy):
        """Budget < $0.10 → shallow (budget preservation)."""
        decision = policy.decide(
            risk="medium",
            uncertainty=0.5,
            budget_remaining_usd=Decimal("0.05"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.level == DepthLevel.SHALLOW
        assert "budget=$0.05" in decision.reason
        assert "budget preservation" in decision.reason
        assert decision.escalate_to_hitl is False


# ── 6. Many prior failures → deep ─────────────────────────────────────


class TestPriorFailures:
    def test_many_prior_failures_deep(self, policy: DepthPolicy):
        """Prior failures >= 2 → deep (but below HITL threshold of 3)."""
        decision = policy.decide(
            risk="low",
            uncertainty=0.3,
            budget_remaining_usd=Decimal("2.00"),
            prior_failures=2,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.level == DepthLevel.DEEP
        assert "prior_failures=2" in decision.reason
        assert decision.escalate_to_hitl is False


# ── 7. Tool requires approval → HITL (unless override) ────────────────


class TestHITLEscalation:
    def test_tool_requires_approval_escalates_to_hitl(self, policy: DepthPolicy):
        """Tool requires approval → escalate_to_hitl=True."""
        decision = policy.decide(
            risk="low",
            uncertainty=0.2,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=True,
            retry_count=0,
        )
        assert decision.escalate_to_hitl is True
        assert decision.hitl_reason == "tool_requires_approval"
        assert decision.level == DepthLevel.DEEP  # HITL overrides to deep

    def test_tool_requires_approval_with_override_no_hitl(self, policy: DepthPolicy):
        """policy_override=True bypasses HITL for approval-requiring tools."""
        decision = policy.decide(
            risk="low",
            uncertainty=0.2,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=True,
            retry_count=0,
            policy_override=True,
        )
        assert decision.escalate_to_hitl is False
        assert decision.hitl_reason is None
        # Level is determined by other signals (low risk + low unc → shallow)
        assert decision.level == DepthLevel.SHALLOW


# ── 8. Retry count >= threshold → HITL ────────────────────────────────


class TestRetryEscalation:
    def test_retry_exhaustion_escalates_to_hitl(self, policy: DepthPolicy):
        """Retry count >= 3 → escalate_to_hitl=True."""
        decision = policy.decide(
            risk="low",
            uncertainty=0.2,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=3,
        )
        assert decision.escalate_to_hitl is True
        assert decision.hitl_reason == "retry_exhausted"


# ── 9. Persistent failure >= threshold → HITL ─────────────────────────


class TestPersistentFailureEscalation:
    def test_persistent_failure_escalates_to_hitl(self, policy: DepthPolicy):
        """Prior failures >= hitl_retry_threshold (3) → HITL."""
        decision = policy.decide(
            risk="low",
            uncertainty=0.2,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=3,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.escalate_to_hitl is True
        assert decision.hitl_reason == "persistent_failure"
        assert decision.level == DepthLevel.DEEP


# ── 10. Policy override with high-risk → deep but no HITL ─────────────


class TestPolicyOverride:
    def test_policy_override_with_high_risk(self, policy: DepthPolicy):
        """policy_override=True + high risk → deep, but no HITL."""
        decision = policy.decide(
            risk="high",
            uncertainty=0.3,
            budget_remaining_usd=Decimal("2.00"),
            prior_failures=0,
            tool_requires_approval=True,
            retry_count=0,
            policy_override=True,
        )
        assert decision.level == DepthLevel.DEEP
        assert decision.escalate_to_hitl is False
        assert decision.hitl_reason is None


# ── 11. Audit event fields ────────────────────────────────────────────


class TestAuditEvent:
    def test_build_audit_event_has_all_fields(self, policy: DepthPolicy):
        """Audit event contains all required fields, no PII."""
        decision = policy.decide(
            risk="medium",
            uncertainty=0.5,
            budget_remaining_usd=Decimal("2.00"),
            prior_failures=1,
            tool_requires_approval=False,
            retry_count=0,
        )
        event = policy.build_audit_event(
            decision,
            risk="medium",
            uncertainty=0.5,
            budget_remaining_usd=Decimal("2.00"),
            prior_failures=1,
            retry_count=0,
            step_id="step-123",
            mission_id="mission-456",
            workspace_id="ws-789",
            user_id=42,
        )

        assert isinstance(event, DepthTriggeredEvent)
        assert event.level == decision.level.value
        assert event.risk == "medium"
        assert event.uncertainty == 0.5
        assert event.budget_remaining_usd == 2.0
        assert event.prior_failures == 1
        assert event.retry_count == 0
        assert event.escalate_to_hitl == decision.escalate_to_hitl
        assert event.hitl_reason == decision.hitl_reason
        assert event.policy_version == policy.policy_version
        assert event.step_id == "step-123"
        assert event.mission_id == "mission-456"
        assert event.workspace_id == "ws-789"
        assert event.user_id == 42

        # Ensure no PII fields exist
        event_dict = event.model_dump()
        assert "task_text" not in event_dict
        assert "tool_input" not in event_dict
        assert "tool_output" not in event_dict


# ── 12. Policy version recorded in every decision ─────────────────────


class TestPolicyVersion:
    def test_policy_version_in_decision(self, policy: DepthPolicy):
        """Policy version is recorded in every decision."""
        decision = policy.decide(
            risk="low",
            uncertainty=0.2,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.policy_version == "v1.0.0"

    def test_custom_policy_version(self, custom_policy: DepthPolicy):
        """Custom policy version is propagated."""
        decision = custom_policy.decide(
            risk="low",
            uncertainty=0.2,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.policy_version == "v2.0.0"


# ── Additional: Custom thresholds ─────────────────────────────────────


class TestCustomThresholds:
    def test_custom_shallow_budget_threshold(self, custom_policy: DepthPolicy):
        """Custom shallow_budget_threshold_usd changes the cutoff."""
        # $0.30 < $0.50 (custom threshold) → shallow
        decision = custom_policy.decide(
            risk="medium",
            uncertainty=0.5,
            budget_remaining_usd=Decimal("0.30"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.level == DepthLevel.SHALLOW

    def test_custom_uncertainty_threshold(self, custom_policy: DepthPolicy):
        """Custom deep_uncertainty_threshold changes the cutoff."""
        # 0.65 > 0.6 (custom threshold) → deep
        decision = custom_policy.decide(
            risk="low",
            uncertainty=0.65,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.level == DepthLevel.DEEP

    def test_custom_hitl_retry_threshold(self, custom_policy: DepthPolicy):
        """Custom hitl_retry_threshold changes the HITL cutoff."""
        # retry_count=2 >= 2 (custom threshold) → HITL
        decision = custom_policy.decide(
            risk="low",
            uncertainty=0.2,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=2,
        )
        assert decision.escalate_to_hitl is True
        assert decision.hitl_reason == "retry_exhausted"


# ── Additional: Reflection iterations mapping ─────────────────────────


class TestReflectionIterations:
    def test_reflection_iterations_shallow(self, policy: DepthPolicy):
        decision = policy.decide(
            risk="low", uncertainty=0.1, budget_remaining_usd=Decimal("5.00"),
            prior_failures=0, tool_requires_approval=False, retry_count=0,
        )
        assert decision.estimated_reflection_iterations == REFLECTION_ITERATIONS[DepthLevel.SHALLOW]

    def test_reflection_iterations_deep(self, policy: DepthPolicy):
        decision = policy.decide(
            risk="high", uncertainty=0.3, budget_remaining_usd=Decimal("5.00"),
            prior_failures=0, tool_requires_approval=False, retry_count=0,
        )
        assert decision.estimated_reflection_iterations == REFLECTION_ITERATIONS[DepthLevel.DEEP]


# ── Additional: Priority order correctness ─────────────────────────────


class TestPriorityOrder:
    def test_high_risk_beats_medium_uncertainty(self, policy: DepthPolicy):
        """High risk (priority 40) beats medium uncertainty (priority 15)."""
        decision = policy.decide(
            risk="high",
            uncertainty=0.5,  # medium
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.level == DepthLevel.DEEP
        assert "risk=high" in decision.reason

    def test_high_uncertainty_beats_low_risk(self, policy: DepthPolicy):
        """High uncertainty (priority 35) beats low risk (priority 5)."""
        decision = policy.decide(
            risk="low",
            uncertainty=0.8,
            budget_remaining_usd=Decimal("5.00"),
            prior_failures=0,
            tool_requires_approval=False,
            retry_count=0,
        )
        assert decision.level == DepthLevel.DEEP
        assert "uncertainty=0.80" in decision.reason
