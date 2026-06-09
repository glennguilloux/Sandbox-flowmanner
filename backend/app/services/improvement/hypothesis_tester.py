#!/usr/bin/env python3
"""
Hypothesis Tester - A/B testing and verification for improvements

This module provides:
- A/B testing framework for improvement strategies
- Pre-deployment verification before applying changes
- Automatic rollback triggers based on performance
- Safety constraints for high-risk modifications

Key Design Principle: Test before you change. Every improvement is a hypothesis
that must be verified before being permanently applied.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .causal_decomposer import (
    ImprovementStrategy,
    KnobType,
    RiskLevel,
)
from .knob_manager import (
    KnobManager,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


# ============================================================================
# HYPOTHESIS STATES
# ============================================================================


class HypothesisState(str, Enum):
    """States of a hypothesis test"""

    PENDING = "pending"  # Not yet started
    RUNNING = "running"  # Currently being tested
    PASSED = "passed"  # Test passed, improvement effective
    FAILED = "failed"  # Test failed, improvement ineffective
    ROLLED_BACK = "rolled_back"  # Improvement was rolled back
    CANCELLED = "cancelled"  # Test was cancelled
    INCONCLUSIVE = "inconclusive"  # Not enough data to determine


class TestType(str, Enum):
    """Types of hypothesis tests"""

    A_B_TEST = "a_b_test"  # Compare A vs B groups
    BEFORE_AFTER = "before_after"  # Compare before vs after
    SHADOW_MODE = "shadow_mode"  # Run in parallel, compare results
    CANARY = "canary"  # Gradual rollout to subset


class RollbackTrigger(str, Enum):
    """Triggers for automatic rollback"""

    SUCCESS_RATE_DROP = "success_rate_drop"
    LATENCY_INCREASE = "latency_increase"
    ERROR_RATE_SPIKE = "error_rate_spike"
    USER_FEEDBACK_NEGATIVE = "user_feedback_negative"
    OSCILLATION_DETECTED = "oscillation_detected"
    MANUAL = "manual"
    TIME_LIMIT = "time_limit"


# ============================================================================
# HYPOTHESIS TEST DEFINITION
# ============================================================================


@dataclass
class HypothesisTest:
    """
    Defines a hypothesis test for an improvement strategy.

    A hypothesis test validates that an improvement strategy
    actually improves the target metric without causing regressions.
    """

    # Identification
    test_id: str = field(default_factory=lambda: str(uuid4()))
    strategy: ImprovementStrategy | None = None

    # Test configuration
    test_type: TestType = TestType.BEFORE_AFTER
    duration_minutes: int = 60
    sample_size: int = 100  # Minimum samples needed

    # Success criteria
    target_metric: str = "success_rate"  # success_rate, latency_p95, error_rate
    min_improvement: float = 0.05  # Minimum improvement to consider successful
    max_regression: float = 0.02  # Maximum allowed regression in other metrics
    confidence_level: float = 0.95  # Statistical confidence required

    # Safety constraints
    risk_level: RiskLevel = RiskLevel.MEDIUM
    auto_rollback_enabled: bool = True
    rollback_triggers: list[RollbackTrigger] = field(
        default_factory=lambda: [
            RollbackTrigger.SUCCESS_RATE_DROP,
            RollbackTrigger.ERROR_RATE_SPIKE,
            RollbackTrigger.OSCILLATION_DETECTED,
        ]
    )

    # Thresholds for automatic rollback
    success_rate_drop_threshold: float = 0.10  # Rollback if success rate drops > 10%
    latency_increase_threshold: float = 0.50  # Rollback if latency increases > 50%
    error_rate_spike_threshold: float = 2.0  # Rollback if error rate doubles

    # State
    state: HypothesisState = HypothesisState.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Results
    baseline_metrics: dict[str, float] = field(default_factory=dict)
    test_metrics: dict[str, float] = field(default_factory=dict)
    improvement_delta: float | None = None
    p_value: float | None = None

    # Rollback info
    rollback_triggered: bool = False
    rollback_trigger: RollbackTrigger | None = None
    rollback_at: datetime | None = None

    # Metadata
    agent_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "strategy_id": self.strategy.strategy_id if self.strategy else None,
            "strategy_type": (
                self.strategy.strategy_type.value if self.strategy else None
            ),
            "test_type": self.test_type.value,
            "duration_minutes": self.duration_minutes,
            "sample_size": self.sample_size,
            "target_metric": self.target_metric,
            "min_improvement": self.min_improvement,
            "max_regression": self.max_regression,
            "risk_level": self.risk_level.value,
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "baseline_metrics": self.baseline_metrics,
            "test_metrics": self.test_metrics,
            "improvement_delta": self.improvement_delta,
            "p_value": self.p_value,
            "rollback_triggered": self.rollback_triggered,
            "rollback_trigger": (
                self.rollback_trigger.value if self.rollback_trigger else None
            ),
            "agent_id": self.agent_id,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
@dataclass
class SafetyConstraint:
    """
    Defines a safety constraint for improvement strategies.

    Safety constraints prevent dangerous modifications by defining
    boundaries that cannot be crossed.
    """

    constraint_id: str
    name: str
    description: str

    # Constraint type
    knob_type: KnobType
    constraint_type: str  # "range", "enum", "custom"

    # For range constraints
    min_value: float | None = None
    max_value: float | None = None

    # For enum constraints
    allowed_values: list[Any] | None = None

    # Custom validation function name (looked up in registry)
    custom_validator: str | None = None

    # Severity of violation
    violation_severity: str = "high"  # "warning", "high", "critical"

    # Bypass requires approval
    requires_approval: bool = True

    def validate(self, value: Any) -> tuple[bool, str | None]:
        """
        Validate a value against this constraint.

        Returns:
            (is_valid, error_message)
        """
        if self.constraint_type == "range":
            if self.min_value is not None and value < self.min_value:
                return False, f"Value {value} below minimum {self.min_value}"
            if self.max_value is not None and value > self.max_value:
                return False, f"Value {value} above maximum {self.max_value}"
            return True, None

        elif self.constraint_type == "enum":
            if value not in (self.allowed_values or []):
                return (
                    False,
                    f"Value {value} not in allowed values: {self.allowed_values}",
                )
            return True, None

        elif self.constraint_type == "custom":
            # Custom validators are looked up at runtime
            return True, None  # Placeholder, actual validation in HypothesisTester

        return True, None


# Default safety constraints
DEFAULT_SAFETY_CONSTRAINTS: list[SafetyConstraint] = [
    # Temperature constraints
    SafetyConstraint(
        constraint_id="temp_min",
        name="Temperature Minimum",
        description="LLM temperature cannot be below 0.0",
        knob_type=KnobType.TEMPERATURE,
        constraint_type="range",
        min_value=0.0,
        max_value=2.0,
        violation_severity="high",
    ),
    # Max tokens constraints
    SafetyConstraint(
        constraint_id="tokens_max",
        name="Max Tokens Limit",
        description="Max tokens cannot exceed model context limit",
        knob_type=KnobType.MAX_TOKENS,
        constraint_type="range",
        min_value=100,
        max_value=128000,  # Conservative upper bound
        violation_severity="high",
    ),
    # Timeout constraints
    SafetyConstraint(
        constraint_id="timeout_range",
        name="Timeout Range",
        description="Tool timeout must be between 1s and 5 minutes",
        knob_type=KnobType.TIMEOUT_MS,
        constraint_type="range",
        min_value=1000,
        max_value=300000,
        violation_severity="medium",
    ),
    # RAG top-k constraints
    SafetyConstraint(
        constraint_id="rag_k_range",
        name="RAG Top-K Range",
        description="RAG top-k must be between 1 and 50",
        knob_type=KnobType.RAG_TOP_K,
        constraint_type="range",
        min_value=1,
        max_value=50,
        violation_severity="medium",
    ),
    # RAG threshold constraints
    SafetyConstraint(
        constraint_id="rag_threshold_range",
        name="RAG Threshold Range",
        description="RAG similarity threshold must be between 0.1 and 0.99",
        knob_type=KnobType.RAG_THRESHOLD,
        constraint_type="range",
        min_value=0.1,
        max_value=0.99,
        violation_severity="medium",
    ),
    # Retry constraints
    SafetyConstraint(
        constraint_id="retry_max",
        name="Maximum Retries",
        description="Maximum retries cannot exceed 10",
        knob_type=KnobType.RETRY_CONFIG,
        constraint_type="custom",
        custom_validator="validate_retry_config",
        violation_severity="medium",
    ),
]


# ============================================================================
# HYPOTHESIS TESTER - Main class
# ============================================================================


@dataclass
class TestResult:
    """Result of a hypothesis test"""

    test_id: str
    hypothesis_id: str
    success: bool
    confidence: float
    metrics_before: dict[str, Any] = field(default_factory=dict)
    metrics_after: dict[str, Any] = field(default_factory=dict)
    improvement_percentage: float = 0.0
    p_value: float | None = None
    state: HypothesisState | None = None
    is_statistically_significant: bool = False
    recommendation: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    rollback_triggered: bool = False
    rollback_trigger: RollbackTrigger | None = None
    agent_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "hypothesis_id": self.hypothesis_id,
            "success": self.success,
            "confidence": self.confidence,
            "metrics_before": self.metrics_before,
            "metrics_after": self.metrics_after,
            "improvement_percentage": self.improvement_percentage,
            "p_value": self.p_value,
            "state": self.state.value if self.state else None,
            "is_statistically_significant": self.is_statistically_significant,
            "recommendation": self.recommendation,
            "details": self.details,
            "rollback_triggered": self.rollback_triggered,
            "rollback_trigger": (
                self.rollback_trigger.value if self.rollback_trigger else None
            ),
            "agent_id": self.agent_id,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


class HypothesisTester:
    """
    Tests improvement hypotheses before permanent application.

    This class provides:
    - Pre-deployment verification
    - A/B testing framework
    - Automatic rollback triggers
    - Safety constraint validation
    """

    def __init__(
        self,
        knob_manager: KnobManager,
        safety_constraints: list[SafetyConstraint] | None = None,
        default_test_duration_minutes: int = 60,
        min_sample_size: int = 100,
    ):
        self.knob_manager = knob_manager
        self.safety_constraints = safety_constraints or DEFAULT_SAFETY_CONSTRAINTS
        self.default_test_duration = default_test_duration_minutes
        self.min_sample_size = min_sample_size

        # Active tests
        self._active_tests: dict[str, HypothesisTest] = {}

        # Custom validators registry
        self._custom_validators: dict[str, Callable[[Any], tuple[bool, str | None]]] = (
            {}
        )

        # Register default custom validators
        self._register_default_validators()

    def _register_default_validators(self):
        """Register default custom validators"""

        def validate_retry_config(value: Any) -> tuple[bool, str | None]:
            if isinstance(value, dict):
                max_retries = value.get("max_retries", 0)
                if max_retries > 10:
                    return False, f"max_retries ({max_retries}) exceeds limit of 10"
                if max_retries < 0:
                    return False, f"max_retries cannot be negative"
            return True, None

        self._custom_validators["validate_retry_config"] = validate_retry_config

    async def create_test(
        self,
        strategy: ImprovementStrategy,
        agent_id: str | None = None,
        test_type: TestType = TestType.BEFORE_AFTER,
        duration_minutes: int | None = None,
    ) -> HypothesisTest:
        """
        Create a new hypothesis test for a strategy.

        Args:
            strategy: The improvement strategy to test
            agent_id: Optional agent ID
            test_type: Type of test to run
            duration_minutes: Test duration (uses default if not specified)

        Returns:
            HypothesisTest object
        """
        test = HypothesisTest(
            strategy=strategy,
            agent_id=agent_id,
            test_type=test_type,
            duration_minutes=duration_minutes or self.default_test_duration,
            risk_level=strategy.risk_level,
        )

        self._active_tests[test.test_id] = test
        logger.info(
            "Created hypothesis test %s for strategy %s",
            test.test_id,
            strategy.strategy_id,
        )

        return test

    async def validate_safety_constraints(
        self,
        strategy: ImprovementStrategy,
    ) -> tuple[bool, list[str]]:
        """
        Validate a strategy against all safety constraints.

        Args:
            strategy: The strategy to validate

        Returns:
            (is_valid, list_of_violations)
        """
        violations = []

        for constraint in self.safety_constraints:
            if constraint.knob_type == strategy.knob:
                is_valid, error = await self._validate_constraint(
                    constraint, strategy.knob_value
                )
                if not is_valid:
                    violations.append(f"{constraint.name}: {error}")

        return len(violations) == 0, violations

    async def _validate_constraint(
        self,
        constraint: SafetyConstraint,
        value: Any,
    ) -> tuple[bool, str | None]:
        """Validate a value against a constraint"""
        if constraint.constraint_type == "custom" and constraint.custom_validator:
            validator = self._custom_validators.get(constraint.custom_validator)
            if validator:
                return validator(value)

        return constraint.validate(value)

    async def run_pre_deployment_check(
        self,
        strategy: ImprovementStrategy,
    ) -> tuple[bool, list[str]]:
        """
        Run pre-deployment checks before applying a strategy.

        This includes:
        - Safety constraint validation
        - Oscillation risk check
        - Dependency verification

        Args:
            strategy: The strategy to check

        Returns:
            (can_deploy, list_of_issues)
        """
        issues = []

        # 1. Safety constraints
        is_safe, violations = await self.validate_safety_constraints(strategy)
        if not is_safe:
            issues.extend([f"Safety violation: {v}" for v in violations])

        # 2. Oscillation risk (check knob history)
        knob = await self.knob_manager.get_knob(
            strategy.knob,
            (
                strategy.applicable_failure_types[0].value
                if strategy.applicable_failure_types
                else None
            ),
        )
        if knob and len(knob.modification_history) >= 3:
            recent_values = [m["new_value"] for m in knob.modification_history[-3:]]
            if strategy.knob_value in recent_values:
                issues.append(
                    f"Oscillation risk: value {strategy.knob_value} was recently tried"
                )

        # 3. High-risk strategies need approval
        if strategy.risk_level == RiskLevel.HIGH:
            issues.append("High-risk strategy requires manual approval")

        return len(issues) == 0, issues

    async def start_test(
        self,
        test: HypothesisTest,
    ) -> bool:
        """
        Start a hypothesis test.

        This applies the improvement and begins monitoring.

        Args:
            test: The test to start

        Returns:
            True if test started successfully
        """
        if test.state != HypothesisState.PENDING:
            logger.warning("Test %s is not in PENDING state", test.test_id)
            return False

        # Run pre-deployment check
        if test.strategy:
            can_deploy, issues = await self.run_pre_deployment_check(test.strategy)
            if not can_deploy:
                logger.error(
                    "Pre-deployment check failed for test %s: %s", test.test_id, issues
                )
                test.state = HypothesisState.CANCELLED
                test.notes = "; ".join(issues)
                return False

        # Apply the improvement
        if test.strategy:
            adjustment = await self.knob_manager.apply_strategy(
                test.strategy, test.agent_id
            )
            if not adjustment:
                logger.error("Failed to apply strategy for test %s", test.test_id)
                test.state = HypothesisState.FAILED
                return False

        # Update test state
        test.state = HypothesisState.RUNNING
        test.started_at = datetime.now(UTC)

        logger.info("Started hypothesis test %s", test.test_id)
        return True

    async def evaluate_test(
        self,
        test: HypothesisTest,
        current_metrics: dict[str, float],
    ) -> TestResult:
        """
        Evaluate a running test against current metrics.

        Args:
            test: The test to evaluate
            current_metrics: Current performance metrics

        Returns:
            TestResult with recommendation
        """
        if test.state != HypothesisState.RUNNING:
            return TestResult(
                test_id=test.test_id,
                hypothesis_id=test.test_id,
                success=False,
                state=test.state,
                improvement_percentage=0.0,
                p_value=None,
                is_statistically_significant=False,
                recommendation="investigate",
                confidence=0.0,
            )

        # Check for rollback triggers
        if test.auto_rollback_enabled:
            should_rollback, trigger = self._check_rollback_triggers(
                test, current_metrics
            )
            if should_rollback:
                await self.rollback_test(test, trigger)
                return TestResult(
                    test_id=test.test_id,
                    hypothesis_id=test.test_id,
                    success=False,
                    state=HypothesisState.ROLLED_BACK,
                    improvement_percentage=0.0,
                    p_value=None,
                    is_statistically_significant=False,
                    recommendation="rollback",
                    confidence=1.0,
                    details={"trigger": trigger.value},
                )

        # Check if test duration has elapsed
        if test.started_at:
            elapsed = datetime.now(UTC) - test.started_at
            if elapsed.total_seconds() > test.duration_minutes * 60:
                return await self._complete_test(test, current_metrics)

        # Test still running
        test.test_metrics = current_metrics

        return TestResult(
            test_id=test.test_id,
            hypothesis_id=test.test_id,
            success=False,
            state=HypothesisState.RUNNING,
            improvement_percentage=0.0,
            p_value=None,
            is_statistically_significant=False,
            recommendation="continue",
            confidence=0.0,
        )

    def _check_rollback_triggers(
        self,
        test: HypothesisTest,
        current_metrics: dict[str, float],
    ) -> tuple[bool, RollbackTrigger | None]:
        """Check if any rollback triggers are activated"""

        baseline = test.baseline_metrics

        for trigger in test.rollback_triggers:
            if trigger == RollbackTrigger.SUCCESS_RATE_DROP:
                baseline_rate = baseline.get("success_rate", 1.0)
                current_rate = current_metrics.get("success_rate", 1.0)
                if baseline_rate > 0:
                    drop = (baseline_rate - current_rate) / baseline_rate
                    if drop > test.success_rate_drop_threshold:
                        return True, trigger

            elif trigger == RollbackTrigger.LATENCY_INCREASE:
                baseline_latency = baseline.get("latency_p95", 0)
                current_latency = current_metrics.get("latency_p95", 0)
                if baseline_latency > 0:
                    increase = (current_latency - baseline_latency) / baseline_latency
                    if increase > test.latency_increase_threshold:
                        return True, trigger

            elif trigger == RollbackTrigger.ERROR_RATE_SPIKE:
                baseline_rate = baseline.get("error_rate", 0)
                current_rate = current_metrics.get("error_rate", 0)
                if (
                    baseline_rate > 0
                    and current_rate > baseline_rate * test.error_rate_spike_threshold
                ):
                    return True, trigger

        return False, None

    async def rollback_test(
        self,
        test: HypothesisTest,
        trigger: RollbackTrigger = RollbackTrigger.MANUAL,
    ) -> bool:
        """
        Rollback a test by reverting the knob to its previous value.

        Args:
            test: The test to rollback
            trigger: What triggered the rollback

        Returns:
            True if rollback successful
        """
        if test.strategy:
            success = await self.knob_manager.rollback_knob(
                test.strategy.knob,
                test.agent_id,
                reason=f"Test rollback: {trigger.value}",
            )

            if success:
                test.state = HypothesisState.ROLLED_BACK
                test.rollback_triggered = True
                test.rollback_trigger = trigger
                test.rollback_at = datetime.now(UTC)
                logger.info(
                    "Rolled back test %s due to %s", test.test_id, trigger.value
                )
                return True

        return False

    async def _complete_test(
        self,
        test: HypothesisTest,
        final_metrics: dict[str, float],
    ) -> TestResult:
        """Complete a test and calculate results"""

        test.test_metrics = final_metrics
        test.completed_at = datetime.now(UTC)

        # Calculate improvement delta
        baseline_value = test.baseline_metrics.get(test.target_metric, 0)
        test_value = final_metrics.get(test.target_metric, 0)

        if baseline_value > 0:
            test.improvement_delta = (test_value - baseline_value) / baseline_value
        else:
            test.improvement_delta = 0.0

        # Determine if improvement is significant
        is_significant = test.improvement_delta >= test.min_improvement

        # Calculate p-value (simplified - would use proper statistical test in production)
        test.p_value = 0.05 if is_significant else 0.3

        # Determine state and recommendation
        if is_significant:
            test.state = HypothesisState.PASSED
            recommendation = "apply"
        elif test.improvement_delta >= 0:
            test.state = HypothesisState.INCONCLUSIVE
            recommendation = "investigate"
        else:
            test.state = HypothesisState.FAILED
            recommendation = "reject"

        logger.info(
            "Completed test %s: %s, improvement=%.2%",
            test.test_id,
            test.state.value,
            test.improvement_delta,
        )

        return TestResult(
            test_id=test.test_id,
            hypothesis_id=test.test_id,
            success=is_significant,
            state=test.state,
            improvement_percentage=test.improvement_delta,
            p_value=test.p_value,
            is_statistically_significant=is_significant,
            recommendation=recommendation,
            confidence=test.strategy.confidence if test.strategy else 0.5,
        )

    def get_active_tests(self) -> list[HypothesisTest]:
        """Get all active tests"""
        return list(self._active_tests.values())

    def get_test(self, test_id: str) -> HypothesisTest | None:
        """Get a specific test by ID"""
        return self._active_tests.get(test_id)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def get_hypothesis_tester(
    db_session,
    knob_manager: KnobManager | None = None,
) -> HypothesisTester:
    """Factory function to get a HypothesisTester instance"""
    if knob_manager is None:
        knob_manager = KnobManager(db_session=db_session)
    return HypothesisTester(knob_manager=knob_manager)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Constants
    "DEFAULT_SAFETY_CONSTRAINTS",
    # Enums
    "HypothesisState",
    # Dataclasses
    "HypothesisTest",
    # Classes
    "HypothesisTester",
    "RollbackTrigger",
    "SafetyConstraint",
    "TestResult",
    "TestType",
    # Functions
    "get_hypothesis_tester",
]
