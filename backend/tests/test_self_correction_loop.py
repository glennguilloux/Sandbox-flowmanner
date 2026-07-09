"""Unit tests for Self-Correction and Retry Under Cost Ceilings (Q2-Q3 Chunk 6).

Covers:
- RecoveryPolicy: error-class → action mapping, non-recoverable → ABORT, retry_recommended=False → REFLECT
- SelfCorrectionBudget: exhaustion by attempts, cost, wall-clock; reflection limits
- SelfCorrectionLoop: correct() decision flow, budget interaction, event emission
- SelfCorrectionLoop: mark_success() emits SELF_CORRECTION_COMPLETED
- Integration: FailureAnalyzer + RecoveryPolicy + SelfCorrectionLoop end-to-end
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from app.models.substrate_models import SubstrateEventType
from app.services.nexus.failure_analyzer import (
    ErrorBudget,
    ErrorClass,
    ExecutionObservation,
    FailureAnalysisResult,
    FailureAnalyzer,
)
from app.services.recovery_policy import RecoveryAction, RecoveryPolicy
from app.services.self_correction_loop import (
    SelfCorrectionBudget,
    SelfCorrectionLoop,
    SelfCorrectionResult,
    get_self_correction_loop,
    reset_self_correction_loop,
)

# ═══════════════════════════════════════════════════════════════════
# RecoveryPolicy: default mappings
# ═══════════════════════════════════════════════════════════════════


class TestRecoveryPolicyDefaults:
    """Verify the default ErrorClass → RecoveryAction mappings."""

    def setup_method(self):
        self.policy = RecoveryPolicy()

    def test_timeout_maps_to_retry(self):
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.TIMEOUT,
            root_cause="timed out",
            is_recoverable=True,
            suggested_recovery="retry",
            retry_recommended=True,
        )
        assert self.policy.decide(analysis) == RecoveryAction.RETRY

    def test_network_maps_to_retry(self):
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.NETWORK,
            root_cause="connection refused",
            is_recoverable=True,
            suggested_recovery="retry",
            retry_recommended=True,
        )
        assert self.policy.decide(analysis) == RecoveryAction.RETRY

    def test_rate_limit_maps_to_fallback_provider(self):
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.RATE_LIMIT,
            root_cause="too many requests",
            is_recoverable=True,
            suggested_recovery="fallback",
            retry_recommended=True,
        )
        assert self.policy.decide(analysis) == RecoveryAction.FALLBACK_PROVIDER

    def test_resource_maps_to_retry(self):
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.RESOURCE,
            root_cause="quota exceeded",
            is_recoverable=True,
            suggested_recovery="retry",
            retry_recommended=True,
        )
        assert self.policy.decide(analysis) == RecoveryAction.RETRY

    def test_validation_maps_to_reflect(self):
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.VALIDATION,
            root_cause="bad input",
            is_recoverable=True,
            suggested_recovery="fix input",
            retry_recommended=False,
        )
        assert self.policy.decide(analysis) == RecoveryAction.REFLECT

    def test_logic_maps_to_reflect(self):
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.LOGIC,
            root_cause="logic error",
            is_recoverable=True,
            suggested_recovery="adjust",
            retry_recommended=False,
        )
        assert self.policy.decide(analysis) == RecoveryAction.REFLECT

    def test_not_found_maps_to_reflect(self):
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.NOT_FOUND,
            root_cause="resource missing",
            is_recoverable=True,
            suggested_recovery="broaden search",
            retry_recommended=False,
        )
        assert self.policy.decide(analysis) == RecoveryAction.REFLECT

    def test_permission_maps_to_ask_hitl(self):
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.PERMISSION,
            root_cause="access denied",
            is_recoverable=True,
            suggested_recovery="check creds",
            retry_recommended=False,
        )
        assert self.policy.decide(analysis) == RecoveryAction.ASK_HITL

    def test_unknown_maps_to_retry(self):
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.UNKNOWN,
            root_cause="something weird",
            is_recoverable=True,
            suggested_recovery="retry",
            retry_recommended=True,
        )
        assert self.policy.decide(analysis) == RecoveryAction.RETRY


# ═══════════════════════════════════════════════════════════════════
# RecoveryPolicy: non-recoverable → ABORT
# ═══════════════════════════════════════════════════════════════════


class TestRecoveryPolicyNonRecoverable:
    """Non-recoverable errors always yield ABORT, regardless of error class."""

    def test_non_recoverable_timeout_yields_abort(self):
        policy = RecoveryPolicy()
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.TIMEOUT,
            root_cause="budget exhausted",
            is_recoverable=False,
            suggested_recovery="abort",
            retry_recommended=False,
        )
        assert policy.decide(analysis) == RecoveryAction.ABORT

    def test_non_recoverable_network_yields_abort(self):
        policy = RecoveryPolicy()
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.NETWORK,
            root_cause="budget exhausted",
            is_recoverable=False,
            suggested_recovery="abort",
            retry_recommended=False,
        )
        assert policy.decide(analysis) == RecoveryAction.ABORT

    def test_non_recoverable_unknown_yields_abort(self):
        policy = RecoveryPolicy()
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.UNKNOWN,
            root_cause="budget exhausted",
            is_recoverable=False,
            suggested_recovery="abort",
            retry_recommended=False,
        )
        assert policy.decide(analysis) == RecoveryAction.ABORT


# ═══════════════════════════════════════════════════════════════════
# RecoveryPolicy: retry_recommended=False downgrades RETRY → REFLECT
# ═══════════════════════════════════════════════════════════════════


class TestRecoveryPolicyRetryDowngrade:
    """When the analysis says retry is not recommended, RETRY is downgraded to REFLECT."""

    def test_timeout_with_retry_not_recommended_yields_reflect(self):
        policy = RecoveryPolicy()
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.TIMEOUT,
            root_cause="timeout",
            is_recoverable=True,
            suggested_recovery="retry",
            retry_recommended=False,
        )
        assert policy.decide(analysis) == RecoveryAction.REFLECT

    def test_network_with_retry_not_recommended_yields_reflect(self):
        policy = RecoveryPolicy()
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.NETWORK,
            root_cause="connection error",
            is_recoverable=True,
            suggested_recovery="retry",
            retry_recommended=False,
        )
        assert policy.decide(analysis) == RecoveryAction.REFLECT


# ═══════════════════════════════════════════════════════════════════
# RecoveryPolicy: overrides
# ═══════════════════════════════════════════════════════════════════


class TestRecoveryPolicyOverrides:
    def test_override_changes_action(self):
        policy = RecoveryPolicy(overrides={ErrorClass.TIMEOUT: RecoveryAction.ABORT})
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.TIMEOUT,
            root_cause="timeout",
            is_recoverable=True,
            suggested_recovery="retry",
            retry_recommended=True,
        )
        assert policy.decide(analysis) == RecoveryAction.ABORT

    def test_get_policy_returns_dict(self):
        policy = RecoveryPolicy()
        p = policy.get_policy()
        assert isinstance(p, dict)
        assert p["timeout"] == "retry"
        assert p["permission"] == "ask_hitl"


# ═══════════════════════════════════════════════════════════════════
# SelfCorrectionBudget: initialization
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionBudgetInit:
    def test_default_initialization(self):
        budget = SelfCorrectionBudget()
        assert budget.max_total_attempts == 10
        assert budget.max_total_cost_usd == 2.00
        assert budget.max_total_wall_clock_seconds == 600.0
        assert budget.max_reflections == 3
        assert budget.total_attempts == 0
        assert budget.total_cost_usd == 0.0
        assert budget.reflection_count == 0

    def test_custom_initialization(self):
        budget = SelfCorrectionBudget(
            max_total_attempts=5,
            max_total_cost_usd=1.00,
            max_total_wall_clock_seconds=120.0,
            max_reflections=1,
        )
        assert budget.max_total_attempts == 5
        assert budget.max_total_cost_usd == 1.00
        assert budget.max_total_wall_clock_seconds == 120.0
        assert budget.max_reflections == 1


# ═══════════════════════════════════════════════════════════════════
# SelfCorrectionBudget: exhaustion checks
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionBudgetExhaustion:
    def test_not_exhausted_initially(self):
        budget = SelfCorrectionBudget()
        exhausted, reason = budget.is_exhausted()
        assert exhausted is False
        assert reason == ""

    def test_attempt_budget_exhausted(self):
        budget = SelfCorrectionBudget(max_total_attempts=3)
        budget.total_attempts = 3
        exhausted, reason = budget.is_exhausted()
        assert exhausted is True
        assert "attempt budget exhausted" in reason
        assert "3/3" in reason

    def test_cost_budget_exhausted(self):
        budget = SelfCorrectionBudget(max_total_cost_usd=1.00)
        budget.total_cost_usd = 1.00
        exhausted, reason = budget.is_exhausted()
        assert exhausted is True
        assert "cost budget exhausted" in reason

    def test_cost_budget_exhausted_when_over(self):
        budget = SelfCorrectionBudget(max_total_cost_usd=0.50)
        budget.total_cost_usd = 0.75
        exhausted, _reason = budget.is_exhausted()
        assert exhausted is True

    def test_wall_clock_budget_exhausted(self):
        budget = SelfCorrectionBudget(max_total_wall_clock_seconds=1.0)
        budget.started_at = time.monotonic() - 5.0
        exhausted, reason = budget.is_exhausted()
        assert exhausted is True
        assert "wall-clock budget exhausted" in reason

    def test_wall_clock_not_exhausted_when_fresh(self):
        budget = SelfCorrectionBudget(max_total_wall_clock_seconds=3600.0)
        exhausted, _reason = budget.is_exhausted()
        assert exhausted is False


# ═══════════════════════════════════════════════════════════════════
# SelfCorrectionBudget: record_attempt / reflection tracking
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionBudgetTracking:
    def test_record_attempt_increments(self):
        budget = SelfCorrectionBudget()
        budget.record_attempt(cost_usd=0.05, wall_clock_ms=100.0)
        assert budget.total_attempts == 1
        assert budget.total_cost_usd == pytest.approx(0.05)
        assert budget.total_wall_clock_ms == 100.0

    def test_record_attempt_accumulates(self):
        budget = SelfCorrectionBudget()
        budget.record_attempt(cost_usd=0.05, wall_clock_ms=100.0)
        budget.record_attempt(cost_usd=0.10, wall_clock_ms=200.0)
        assert budget.total_attempts == 2
        assert budget.total_cost_usd == pytest.approx(0.15)
        assert budget.total_wall_clock_ms == 300.0

    def test_can_reflect_true_initially(self):
        budget = SelfCorrectionBudget(max_reflections=3)
        assert budget.can_reflect() is True

    def test_can_reflect_false_at_limit(self):
        budget = SelfCorrectionBudget(max_reflections=2)
        budget.reflection_count = 2
        assert budget.can_reflect() is False

    def test_record_reflection_increments(self):
        budget = SelfCorrectionBudget()
        budget.record_reflection()
        budget.record_reflection()
        assert budget.reflection_count == 2

    def test_to_dict_includes_all_fields(self):
        budget = SelfCorrectionBudget(max_total_attempts=5)
        budget.record_attempt(cost_usd=0.10)
        d = budget.to_dict()
        assert d["total_attempts"] == 1
        assert d["max_total_attempts"] == 5
        assert d["total_cost_usd"] == pytest.approx(0.10)
        assert "max_reflections" in d
        assert "reflection_count" in d


# ═══════════════════════════════════════════════════════════════════
# SelfCorrectionLoop: correct() — basic decision flow
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionLoopDecisions:
    """Test the correct() method's decision flow with mocked FailureAnalyzer."""

    def _make_loop(self, budget: SelfCorrectionBudget | None = None) -> SelfCorrectionLoop:
        return SelfCorrectionLoop(budget=budget or SelfCorrectionBudget())

    @pytest.mark.asyncio
    async def test_correct_returns_retry_for_timeout(self):
        loop = self._make_loop()
        result = await loop.correct(
            error=Exception("timeout error"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.RETRY
        assert result.final_success is False
        assert result.analysis is not None
        assert result.analysis.error_class == ErrorClass.TIMEOUT

    @pytest.mark.asyncio
    async def test_correct_returns_reflect_for_validation(self):
        # VALIDATION default budget is max_retries=1, and analyze_failure() records
        # the attempt BEFORE checking exhaustion, so the first call already exhausts.
        # Pre-set a higher budget so the policy sees a recoverable analysis.
        loop = self._make_loop()
        loop.failure_analyzer._budgets[ErrorClass.VALIDATION].max_retries = 3
        result = await loop.correct(
            error=Exception("validation failed"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.REFLECT
        assert result.analysis.error_class == ErrorClass.VALIDATION

    def test_permission_policy_maps_to_ask_hitl(self):
        # PERMISSION errors are always non-recoverable in FailureAnalyzer
        # (_recover_permission returns is_recoverable=False), so the
        # RecoveryPolicy correctly maps them to ABORT.  Test the policy
        # directly with a recoverable analysis to verify the ASK_HITL mapping.
        policy = RecoveryPolicy()
        analysis = FailureAnalysisResult(
            error_class=ErrorClass.PERMISSION,
            root_cause="access denied",
            is_recoverable=True,
            suggested_recovery="check creds",
            retry_recommended=False,
        )
        assert policy.decide(analysis) == RecoveryAction.ASK_HITL

    @pytest.mark.asyncio
    async def test_permission_error_aborts_via_non_recoverable(self):
        """PERMISSION errors are non-recoverable by design — verify the full loop path."""
        loop = self._make_loop()
        result = await loop.correct(
            error=PermissionError("access denied"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.ABORT
        assert result.analysis is not None
        assert result.analysis.error_class == ErrorClass.PERMISSION
        assert result.analysis.is_recoverable is False

    @pytest.mark.asyncio
    async def test_correct_returns_fallback_provider_for_rate_limit(self):
        loop = self._make_loop()
        result = await loop.correct(
            error=Exception("too many requests — rate limit"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.FALLBACK_PROVIDER
        assert result.analysis.error_class == ErrorClass.RATE_LIMIT

    @pytest.mark.asyncio
    async def test_correct_returns_retry_for_network(self):
        loop = self._make_loop()
        result = await loop.correct(
            error=ConnectionError("connection refused"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.RETRY
        assert result.analysis.error_class == ErrorClass.NETWORK

    @pytest.mark.asyncio
    async def test_correct_returns_retry_for_unknown(self):
        # UNKNOWN default budget is max_retries=1, so the first attempt exhausts.
        # Pre-set a higher budget to test the policy's RETRY decision.
        loop = self._make_loop()
        loop.failure_analyzer._budgets[ErrorClass.UNKNOWN].max_retries = 3
        result = await loop.correct(
            error=RuntimeError("something weird happened"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.RETRY
        assert result.analysis.error_class == ErrorClass.UNKNOWN


# ═══════════════════════════════════════════════════════════════════
# SelfCorrectionLoop: correct() — budget exhaustion
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionLoopBudgetExhaustion:
    def _make_loop(self, budget: SelfCorrectionBudget) -> SelfCorrectionLoop:
        return SelfCorrectionLoop(budget=budget)

    @pytest.mark.asyncio
    async def test_aborts_when_attempt_budget_exhausted(self):
        budget = SelfCorrectionBudget(max_total_attempts=0)
        loop = self._make_loop(budget)
        result = await loop.correct(
            error=Exception("timeout"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.ABORT
        assert result.aborted_reason is not None
        assert "attempt budget exhausted" in result.aborted_reason

    @pytest.mark.asyncio
    async def test_aborts_when_cost_budget_exhausted(self):
        budget = SelfCorrectionBudget(max_total_cost_usd=0.0)
        loop = self._make_loop(budget)
        result = await loop.correct(
            error=Exception("timeout"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.ABORT
        assert "cost budget exhausted" in result.aborted_reason

    @pytest.mark.asyncio
    async def test_aborts_when_wall_clock_exhausted(self):
        budget = SelfCorrectionBudget(max_total_wall_clock_seconds=0.01)
        budget.started_at = time.monotonic() - 100.0
        loop = self._make_loop(budget)
        result = await loop.correct(
            error=Exception("timeout"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.ABORT
        assert "wall-clock budget exhausted" in result.aborted_reason

    @pytest.mark.asyncio
    async def test_budget_is_checked_before_analysis(self):
        """Budget check happens first — error is never even classified."""
        budget = SelfCorrectionBudget(max_total_attempts=0)
        loop = SelfCorrectionLoop(budget=budget)
        result = await loop.correct(
            error=Exception("timeout"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.analysis is None  # Analysis was never run
        assert result.action_taken == RecoveryAction.ABORT


# ═══════════════════════════════════════════════════════════════════
# SelfCorrectionLoop: correct() — per-error-class budget interaction
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionLoopErrorClassBudget:
    """Test that FailureAnalyzer's per-error-class budgets cause non-recoverable results."""

    @pytest.mark.asyncio
    async def test_error_class_budget_exhaustion_yields_abort(self):
        loop = SelfCorrectionLoop()
        # Exhaust the TIMEOUT error class budget
        timeout_budget = loop.failure_analyzer._budgets[ErrorClass.TIMEOUT]
        timeout_budget.retry_count = timeout_budget.max_retries

        result = await loop.correct(
            error=Exception("timeout error"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.ABORT
        assert result.analysis is not None
        assert result.analysis.is_recoverable is False

    @pytest.mark.asyncio
    async def test_permission_budget_zero_yields_abort_immediately(self):
        """PERMISSION has max_retries=0, so first attempt exhausts error-class budget.

        This is intentional: permission errors are permanent and should not be retried.
        analyze_failure() records the attempt then checks exhaustion, so max_retries=0
        means the very first call is already exhausted → non-recoverable → ABORT.
        """
        loop = SelfCorrectionLoop()
        result = await loop.correct(
            error=PermissionError("access denied"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.ABORT


# ═══════════════════════════════════════════════════════════════════
# SelfCorrectionLoop: correct() — reflection limit
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionLoopReflectionLimit:
    @pytest.mark.asyncio
    async def test_reflect_budget_exhausted_downgrades_to_abort_for_validation(self):
        """When reflection budget is exhausted and retry_recommended=False (VALIDATION),
        the downgrade logic yields ABORT (not RETRY)."""
        budget = SelfCorrectionBudget(max_reflections=1)
        budget.reflection_count = 1  # Already at limit
        loop = SelfCorrectionLoop(budget=budget)

        result = await loop.correct(
            error=Exception("validation failed"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        # VALIDATION → REFLECT policy, but can_reflect() is False.
        # Downgrade: retry_recommended=False → ABORT
        assert result.action_taken == RecoveryAction.ABORT

    @pytest.mark.asyncio
    async def test_reflect_budget_exhausted_downgrades_to_retry_when_recommended(self):
        """For errors where retry_recommended=True, reflection exhaustion → RETRY."""
        budget = SelfCorrectionBudget(max_reflections=0)
        # Use a custom policy where TIMEOUT → REFLECT so we can test the downgrade
        policy = RecoveryPolicy(overrides={ErrorClass.TIMEOUT: RecoveryAction.REFLECT})
        # Pre-set a higher retry budget so the first attempt doesn't exhaust
        loop = SelfCorrectionLoop(budget=budget, recovery_policy=policy)
        loop.failure_analyzer._budgets[ErrorClass.TIMEOUT].max_retries = 3

        result = await loop.correct(
            error=Exception("timeout error"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        # TIMEOUT has retry_recommended=True, so when reflection is exhausted → RETRY
        assert result.action_taken == RecoveryAction.RETRY


# ═══════════════════════════════════════════════════════════════════
# SelfCorrectionLoop: correct() — event emission
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionLoopEventEmission:
    @pytest.mark.asyncio
    async def test_emits_attempted_event_on_correction(self):
        loop = SelfCorrectionLoop()
        emitter = AsyncMock()

        await loop.correct(
            error=Exception("timeout error"),
            context={"task_id": "t1", "mission_id": "m1"},
            event_emitter=emitter,
        )
        emitter.assert_called_once()
        call_args = emitter.call_args
        assert call_args[0][0] == "m1"  # run_id
        events = call_args[0][1]
        assert len(events) == 1
        assert events[0]["type"] == SubstrateEventType.SELF_CORRECTION_ATTEMPTED
        assert events[0]["actor"] == "self_correction_loop"
        assert "action" in events[0]["payload"]
        assert "error_class" in events[0]["payload"]
        assert "budget" in events[0]["payload"]

    @pytest.mark.asyncio
    async def test_emits_aborted_event_once_on_budget_exhaustion(self):
        budget = SelfCorrectionBudget(max_total_attempts=0)
        loop = SelfCorrectionLoop(budget=budget)
        emitter = AsyncMock()

        await loop.correct(
            error=Exception("timeout error"),
            context={"task_id": "t1", "mission_id": "m1"},
            event_emitter=emitter,
        )
        # Budget exhaustion emits only SELF_CORRECTION_ABORTED
        assert emitter.call_count == 1
        event = emitter.call_args[0][1][0]
        assert event["type"] == SubstrateEventType.SELF_CORRECTION_ABORTED

    @pytest.mark.asyncio
    async def test_emitter_failure_does_not_raise(self):
        """Event emission failures are swallowed (non-critical)."""
        emitter = AsyncMock(side_effect=Exception("DB down"))
        loop = SelfCorrectionLoop()

        # Should not raise
        result = await loop.correct(
            error=Exception("timeout error"),
            context={"task_id": "t1", "mission_id": "m1"},
            event_emitter=emitter,
        )
        assert result.action_taken == RecoveryAction.RETRY

    @pytest.mark.asyncio
    async def test_no_event_when_emitter_is_none(self):
        loop = SelfCorrectionLoop()
        result = await loop.correct(
            error=Exception("timeout error"),
            context={"task_id": "t1", "mission_id": "m1"},
            event_emitter=None,
        )
        assert result.action_taken == RecoveryAction.RETRY


# ═══════════════════════════════════════════════════════════════════
# SelfCorrectionLoop: mark_success()
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionLoopMarkSuccess:
    @pytest.mark.asyncio
    async def test_mark_success_emits_completed_event(self):
        loop = SelfCorrectionLoop()
        emitter = AsyncMock()

        # Simulate some correction attempts
        loop.budget.record_attempt(cost_usd=0.05, wall_clock_ms=100.0)

        await loop.mark_success(
            context={"task_id": "t1", "mission_id": "m1"},
            event_emitter=emitter,
        )
        emitter.assert_called_once()
        event = emitter.call_args[0][1][0]
        assert event["type"] == SubstrateEventType.SELF_CORRECTION_COMPLETED
        assert event["payload"]["total_attempts"] == 1
        assert event["payload"]["total_cost_usd"] == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_mark_success_without_emitter(self):
        loop = SelfCorrectionLoop()
        # Should not raise
        await loop.mark_success(
            context={"task_id": "t1", "mission_id": "m1"},
            event_emitter=None,
        )

    @pytest.mark.asyncio
    async def test_mark_success_emitter_failure_does_not_raise(self):
        loop = SelfCorrectionLoop()
        emitter = AsyncMock(side_effect=Exception("DB down"))
        # Should not raise
        await loop.mark_success(
            context={"task_id": "t1", "mission_id": "m1"},
            event_emitter=emitter,
        )


# ═══════════════════════════════════════════════════════════════════
# SelfCorrectionLoop: to_dict on result
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionResultDict:
    @pytest.mark.asyncio
    async def test_result_to_dict(self):
        loop = SelfCorrectionLoop()
        result = await loop.correct(
            error=Exception("timeout error"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        d = result.to_dict()
        assert d["action_taken"] == "retry"
        assert d["final_success"] is False
        assert d["error_class"] == "timeout"
        assert "attempts_used" in d
        assert "total_cost_usd" in d

    @pytest.mark.asyncio
    async def test_result_to_dict_on_abort(self):
        budget = SelfCorrectionBudget(max_total_attempts=0)
        loop = SelfCorrectionLoop(budget=budget)
        result = await loop.correct(
            error=Exception("timeout error"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        d = result.to_dict()
        assert d["action_taken"] == "abort"
        assert d["aborted_reason"] is not None


# ═══════════════════════════════════════════════════════════════════
# SelfCorrectionLoop: singleton
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionLoopSingleton:
    def test_get_returns_same_instance(self):
        reset_self_correction_loop()
        loop1 = get_self_correction_loop()
        loop2 = get_self_correction_loop()
        assert loop1 is loop2

    def test_reset_clears_singleton(self):
        reset_self_correction_loop()
        loop1 = get_self_correction_loop()
        reset_self_correction_loop()
        loop2 = get_self_correction_loop()
        assert loop1 is not loop2


# ═══════════════════════════════════════════════════════════════════
# End-to-end: FailureAnalyzer + RecoveryPolicy + SelfCorrectionLoop
# ═══════════════════════════════════════════════════════════════════


class TestSelfCorrectionEndToEnd:
    """End-to-end tests exercising the full pipeline."""

    @pytest.mark.asyncio
    async def test_timeout_retry_then_success(self):
        """Simulate: timeout → retry → success."""
        loop = SelfCorrectionLoop()

        # First attempt: timeout
        result1 = await loop.correct(
            error=Exception("timeout"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result1.action_taken == RecoveryAction.RETRY
        assert loop.budget.total_attempts == 1

        # Mark success after retry
        emitter = AsyncMock()
        await loop.mark_success(
            context={"task_id": "t1", "mission_id": "m1"},
            event_emitter=emitter,
        )
        event = emitter.call_args[0][1][0]
        assert event["type"] == SubstrateEventType.SELF_CORRECTION_COMPLETED
        assert event["payload"]["total_attempts"] == 1

    @pytest.mark.asyncio
    async def test_validation_reflect_then_success(self):
        """Simulate: validation error → reflect → success."""
        loop = SelfCorrectionLoop()
        # VALIDATION default budget is max_retries=1; first attempt exhausts it.
        # Pre-set a higher budget to test the reflect path.
        loop.failure_analyzer._budgets[ErrorClass.VALIDATION].max_retries = 3

        result = await loop.correct(
            error=Exception("validation failed"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.REFLECT
        assert loop.budget.reflection_count == 1

    @pytest.mark.asyncio
    async def test_repeated_failures_exhaust_budget(self):
        """Simulate: repeated timeouts → budget exhausted → abort."""
        budget = SelfCorrectionBudget(max_total_attempts=3)
        loop = SelfCorrectionLoop(budget=budget)

        for i in range(3):
            result = await loop.correct(
                error=Exception(f"timeout {i}"),
                context={"task_id": "t1", "mission_id": "m1"},
            )
            assert result.action_taken == RecoveryAction.RETRY

        # 4th attempt: budget exhausted
        result = await loop.correct(
            error=Exception("timeout 3"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.ABORT
        assert "attempt budget exhausted" in result.aborted_reason

    @pytest.mark.asyncio
    async def test_cost_accumulation_across_error_classes(self):
        """Cost accumulates across different error classes."""
        budget = SelfCorrectionBudget(max_total_cost_usd=0.20)
        loop = SelfCorrectionLoop(budget=budget)

        # Timeout attempt costs $0.10
        await loop.correct(
            error=Exception("timeout"),
            context={"task_id": "t1", "mission_id": "m1", "cost_usd": 0.10},
        )
        assert budget.total_cost_usd == pytest.approx(0.10)

        # Network attempt costs $0.15 — total $0.25 > $0.20
        # But the cost is recorded AFTER analysis, and budget is checked BEFORE.
        # So the 2nd attempt proceeds (budget was $0.10 at check time), then records $0.15.
        # The 3rd attempt will see $0.25 and abort.
        await loop.correct(
            error=ConnectionError("connection refused"),
            context={"task_id": "t1", "mission_id": "m1", "cost_usd": 0.15},
        )
        assert budget.total_cost_usd == pytest.approx(0.25)

        # 3rd attempt: budget exhausted
        result = await loop.correct(
            error=Exception("timeout again"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.ABORT

    @pytest.mark.asyncio
    async def test_multiple_tasks_share_budget(self):
        """Budget is shared across multiple tasks in the same mission."""
        budget = SelfCorrectionBudget(max_total_attempts=3)
        loop = SelfCorrectionLoop(budget=budget)

        # Task 1: 2 attempts
        await loop.correct(
            error=Exception("timeout"),
            context={"task_id": "t1", "mission_id": "m1"},
        )
        await loop.correct(
            error=Exception("timeout again"),
            context={"task_id": "t1", "mission_id": "m1"},
        )

        # Task 2: 3rd attempt exhausts budget
        await loop.correct(
            error=Exception("network error"),
            context={"task_id": "t2", "mission_id": "m1"},
        )

        # Task 2: 4th attempt → budget exhausted
        result = await loop.correct(
            error=Exception("network error again"),
            context={"task_id": "t2", "mission_id": "m1"},
        )
        assert result.action_taken == RecoveryAction.ABORT

    @pytest.mark.asyncio
    async def test_event_payload_contains_budget_info(self):
        """Event payloads include full budget state for replay."""
        loop = SelfCorrectionLoop()
        emitter = AsyncMock()

        await loop.correct(
            error=Exception("timeout error"),
            context={"task_id": "t1", "mission_id": "m1"},
            event_emitter=emitter,
        )
        event = emitter.call_args[0][1][0]
        payload = event["payload"]
        assert "budget" in payload
        assert "total_attempts" in payload["budget"]
        assert "max_total_attempts" in payload["budget"]
        assert "error_class_budget" in payload
        assert payload["error_class_budget"]["max_retries"] > 0
