"""Unit tests for FailureAnalyzer budget enforcement (H2.2).

Covers:
- per-error-class budget initialization
- retry budget exhaustion
- wall-clock budget exhaustion behavior
- cost budget exhaustion behavior
- analyze_failure() returns non-recoverable when class budget exhausted
- reset_budgets() semantics
- classify_error() correctness
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.services.nexus.failure_analyzer import (
    DEFAULT_ERROR_BUDGETS,
    ErrorBudget,
    ErrorClass,
    ExecutionObservation,
    FailureAnalysisResult,
    FailureAnalyzer,
    get_failure_analyzer,
)

# ═══════════════════════════════════════════════════════════════════
# ErrorBudget: initialization
# ═══════════════════════════════════════════════════════════════════


class TestErrorBudgetInit:
    def test_default_initialization(self):
        budget = ErrorBudget()
        assert budget.retry_count == 0
        assert budget.total_wall_clock_ms == 0.0
        assert budget.total_cost_usd == 0.0
        assert budget.started_at == 0.0

    def test_custom_budget_initialization(self):
        budget = ErrorBudget(
            max_retries=5,
            max_wall_clock_seconds=600.0,
            max_cost_usd=2.50,
        )
        assert budget.max_retries == 5
        assert budget.max_wall_clock_seconds == 600.0
        assert budget.max_cost_usd == 2.50

    def test_default_error_budgets_cover_all_classes(self):
        for ec in ErrorClass:
            assert ec in DEFAULT_ERROR_BUDGETS, f"Missing budget for {ec}"
        assert len(DEFAULT_ERROR_BUDGETS) == len(ErrorClass)

    def test_permission_budget_zero_retries(self):
        budget = DEFAULT_ERROR_BUDGETS[ErrorClass.PERMISSION]
        assert budget.max_retries == 0

    def test_timeout_budget_generous(self):
        budget = DEFAULT_ERROR_BUDGETS[ErrorClass.TIMEOUT]
        assert budget.max_retries == 5


# ═══════════════════════════════════════════════════════════════════
# ErrorBudget: exhaustion checks
# ═══════════════════════════════════════════════════════════════════


class TestErrorBudgetExhaustion:
    def test_not_exhausted_initially(self):
        budget = ErrorBudget(max_retries=3)
        exhausted, reason = budget.is_exhausted()
        assert exhausted is False
        assert reason == ""

    def test_retry_budget_exhausted(self):
        budget = ErrorBudget(max_retries=2)
        budget.retry_count = 2
        exhausted, reason = budget.is_exhausted()
        assert exhausted is True
        assert "Retry budget exhausted" in reason
        assert "2/2" in reason

    def test_retry_budget_not_exhausted_when_under(self):
        budget = ErrorBudget(max_retries=3)
        budget.retry_count = 2
        exhausted, reason = budget.is_exhausted()
        assert exhausted is False
        assert reason == ""

    def test_cost_budget_exhausted(self):
        budget = ErrorBudget(max_cost_usd=1.00)
        budget.total_cost_usd = 1.00
        exhausted, reason = budget.is_exhausted()
        assert exhausted is True
        assert "Cost budget exhausted" in reason

    def test_cost_budget_exhausted_when_over(self):
        budget = ErrorBudget(max_cost_usd=0.50)
        budget.total_cost_usd = 0.75
        exhausted, reason = budget.is_exhausted()
        assert exhausted is True

    def test_wall_clock_budget_exhausted(self):
        budget = ErrorBudget(max_wall_clock_seconds=10.0)
        budget.started_at = time.monotonic() - 15.0
        exhausted, reason = budget.is_exhausted()
        assert exhausted is True
        assert "Wall-clock budget exhausted" in reason

    def test_wall_clock_budget_not_exhausted_when_fresh(self):
        budget = ErrorBudget(max_wall_clock_seconds=3600.0)
        budget.started_at = time.monotonic()
        exhausted, reason = budget.is_exhausted()
        assert exhausted is False

    def test_wall_clock_zero_max_disables_check(self):
        budget = ErrorBudget(max_wall_clock_seconds=0.0, max_retries=1)
        budget.started_at = time.monotonic() - 1000.0
        exhausted, reason = budget.is_exhausted()
        if exhausted:
            assert "Wall-clock" not in reason


# ═══════════════════════════════════════════════════════════════════
# ErrorBudget: record_attempt()
# ═══════════════════════════════════════════════════════════════════


class TestErrorBudgetRecordAttempt:
    def test_record_increments_retry_count(self):
        budget = ErrorBudget(max_retries=3)
        budget.record_attempt()
        assert budget.retry_count == 1
        budget.record_attempt()
        assert budget.retry_count == 2

    def test_record_accumulates_wall_clock(self):
        budget = ErrorBudget()
        budget.record_attempt(wall_clock_ms=100.0)
        budget.record_attempt(wall_clock_ms=200.0)
        assert budget.total_wall_clock_ms == 300.0

    def test_record_accumulates_cost(self):
        budget = ErrorBudget()
        budget.record_attempt(cost_usd=0.05)
        budget.record_attempt(cost_usd=0.10)
        assert budget.total_cost_usd == pytest.approx(0.15)

    def test_record_sets_started_at_on_first_attempt(self):
        budget = ErrorBudget()
        assert budget.started_at == 0.0
        budget.record_attempt()
        assert budget.started_at > 0.0

    def test_started_at_does_not_change_on_subsequent_attempts(self):
        budget = ErrorBudget()
        budget.record_attempt()
        first_started = budget.started_at
        budget.record_attempt()
        assert budget.started_at == first_started


# ═══════════════════════════════════════════════════════════════════
# ErrorBudget: to_dict()
# ═══════════════════════════════════════════════════════════════════


class TestErrorBudgetToDict:
    def test_to_dict_includes_all_fields(self):
        budget = ErrorBudget(max_retries=3, max_cost_usd=0.50)
        budget.record_attempt(wall_clock_ms=150.0, cost_usd=0.10)
        d = budget.to_dict()
        assert d["retry_count"] == 1
        assert d["max_retries"] == 3
        assert d["total_wall_clock_ms"] == 150.0
        assert d["max_cost_usd"] == 0.50
        assert d["total_cost_usd"] == pytest.approx(0.10)


# ═══════════════════════════════════════════════════════════════════
# FailureAnalyzer: analyze_failure() with budgets
# ═══════════════════════════════════════════════════════════════════


class TestFailureAnalyzerBudgets:
    def setup_method(self):
        self.analyzer = FailureAnalyzer()

    def test_analyze_failure_records_attempt(self):
        budget = self.analyzer._budgets[ErrorClass.TIMEOUT]
        initial_count = budget.retry_count

        self.analyzer.analyze_failure(
            error=Exception("timeout error"),
            context={},
            execution_log=[],
            wall_clock_ms=50.0,
            cost_usd=0.02,
        )

        assert budget.retry_count == initial_count + 1
        assert budget.total_wall_clock_ms == 50.0
        assert budget.total_cost_usd == pytest.approx(0.02)

    def test_analyze_failure_returns_non_recoverable_on_exhaustion(self):
        budget = self.analyzer._budgets[ErrorClass.LOGIC]
        budget.max_retries = 1
        budget.retry_count = 1

        result = self.analyzer.analyze_failure(
            error=ValueError("logic error"),
            context={},
            execution_log=[],
        )

        assert result.is_recoverable is False
        assert result.retry_recommended is False
        assert result.context_updates.get("budget_exhausted") is True
        assert "exhausted" in result.root_cause.lower()

    def test_analyze_failure_returns_recoverable_when_budget_available(self):
        result = self.analyzer.analyze_failure(
            error=Exception("connection refused"),
            context={},
            execution_log=[],
        )

        assert result.error_class == ErrorClass.NETWORK
        assert result.is_recoverable is True

    def test_budget_exhaustion_makes_any_error_non_recoverable(self):
        budget = self.analyzer._budgets[ErrorClass.TIMEOUT]
        budget.max_retries = 0
        budget.retry_count = 0

        result = self.analyzer.analyze_failure(
            error=Exception("timeout error"),
            context={},
            execution_log=[],
        )

        assert result.is_recoverable is False
        assert "Budget exhausted" in result.root_cause

    def test_analyze_failure_with_cost_budget_exhaustion(self):
        # "too many requests" classifies as RATE_LIMIT
        budget = self.analyzer._budgets[ErrorClass.RATE_LIMIT]
        budget.total_cost_usd = budget.max_cost_usd

        result = self.analyzer.analyze_failure(
            error=Exception("too many requests"),
            context={},
            execution_log=[],
            cost_usd=0.0,
        )

        assert result.is_recoverable is False
        assert "Cost budget exhausted" in result.root_cause


# ═══════════════════════════════════════════════════════════════════
# FailureAnalyzer: reset_budgets()
# ═══════════════════════════════════════════════════════════════════


class TestFailureAnalyzerResetBudgets:
    def test_reset_budgets_clears_retry_counts(self):
        analyzer = FailureAnalyzer()
        analyzer._budgets[ErrorClass.TIMEOUT].retry_count = 3
        analyzer._budgets[ErrorClass.TIMEOUT].total_cost_usd = 0.50
        analyzer._budgets[ErrorClass.NETWORK].retry_count = 2

        analyzer.reset_budgets()

        for ec in ErrorClass:
            budget = analyzer._budgets[ec]
            assert budget.retry_count == 0, f"{ec.value} retry_count not reset"
            assert budget.total_wall_clock_ms == 0.0, f"{ec.value} wall_clock not reset"
            assert budget.total_cost_usd == 0.0, f"{ec.value} cost not reset"
            assert budget.started_at == 0.0, f"{ec.value} started_at not reset"

    def test_reset_budgets_preserves_max_limits(self):
        analyzer = FailureAnalyzer()
        timeout_budget = analyzer._budgets[ErrorClass.TIMEOUT]
        original_max_retries = timeout_budget.max_retries
        timeout_budget.retry_count = 2

        analyzer.reset_budgets()

        assert analyzer._budgets[ErrorClass.TIMEOUT].max_retries == original_max_retries

    def test_budgets_fresh_after_reset(self):
        analyzer = FailureAnalyzer()
        analyzer._budgets[ErrorClass.TIMEOUT].retry_count = 5
        is_exhausted, _ = analyzer._budgets[ErrorClass.TIMEOUT].is_exhausted()
        assert is_exhausted is True

        analyzer.reset_budgets()

        is_exhausted, _ = analyzer._budgets[ErrorClass.TIMEOUT].is_exhausted()
        assert is_exhausted is False


# ═══════════════════════════════════════════════════════════════════
# FailureAnalyzer: classify_error()
# ═══════════════════════════════════════════════════════════════════


class TestClassifyError:
    def setup_method(self):
        self.analyzer = FailureAnalyzer()

    def test_classify_timeout(self):
        assert (
            self.analyzer.classify_error(TimeoutError("timed out"))
            == ErrorClass.TIMEOUT
        )

    def test_classify_validation(self):
        assert (
            self.analyzer.classify_error(Exception("validation failed"))
            == ErrorClass.VALIDATION
        )

    def test_classify_network(self):
        assert (
            self.analyzer.classify_error(ConnectionError("connection refused"))
            == ErrorClass.NETWORK
        )

    def test_classify_permission(self):
        assert (
            self.analyzer.classify_error(PermissionError("access denied"))
            == ErrorClass.PERMISSION
        )

    def test_classify_not_found(self):
        assert (
            self.analyzer.classify_error(FileNotFoundError("not found"))
            == ErrorClass.NOT_FOUND
        )

    def test_classify_rate_limit(self):
        # "rate limit" matches before "limit exceeded" in classify_error
        assert (
            self.analyzer.classify_error(Exception("too many requests — rate limit"))
            == ErrorClass.RATE_LIMIT
        )

    def test_classify_resource_limit_exceeded(self):
        # "limit exceeded" matches RESOURCE
        assert (
            self.analyzer.classify_error(Exception("rate limit exceeded"))
            == ErrorClass.RESOURCE
        )

    def test_classify_unknown(self):
        assert (
            self.analyzer.classify_error(Exception("something weird"))
            == ErrorClass.UNKNOWN
        )


# ═══════════════════════════════════════════════════════════════════
# FailureAnalyzer: other methods
# ═══════════════════════════════════════════════════════════════════


class TestFailureAnalyzerOther:
    def setup_method(self):
        self.analyzer = FailureAnalyzer()

    def test_is_budget_exhausted_returns_false_for_fresh(self):
        exhausted, reason = self.analyzer.is_budget_exhausted(ErrorClass.TIMEOUT)
        assert exhausted is False

    def test_is_budget_exhausted_returns_true_when_exhausted(self):
        self.analyzer._budgets[ErrorClass.TIMEOUT].retry_count = 5
        exhausted, reason = self.analyzer.is_budget_exhausted(ErrorClass.TIMEOUT)
        assert exhausted is True

    def test_get_budget_returns_budget_for_class(self):
        budget = self.analyzer.get_budget(ErrorClass.NETWORK)
        assert isinstance(budget, ErrorBudget)
        assert (
            budget.max_retries == DEFAULT_ERROR_BUDGETS[ErrorClass.NETWORK].max_retries
        )

    def test_get_budget_returns_none_for_unknown(self):
        budget = self.analyzer.get_budget(MagicMock())
        assert budget is None

    def test_get_budget_summary_covers_all_classes(self):
        summary = self.analyzer.get_budget_summary()
        assert len(summary) == len(ErrorClass)
        for ec in ErrorClass:
            assert ec.value in summary

    def test_should_retry_returns_true_for_network(self):
        assert self.analyzer.should_retry(ErrorClass.NETWORK, 0) is True

    def test_should_retry_returns_false_for_permission(self):
        assert self.analyzer.should_retry(ErrorClass.PERMISSION, 0) is False

    def test_should_retry_returns_false_when_exceeded_max(self):
        assert self.analyzer.should_retry(ErrorClass.TIMEOUT, 3, max_retries=3) is False

    def test_suggest_recovery_returns_strategy(self):
        result = self.analyzer.suggest_recovery(ErrorClass.TIMEOUT, {})
        assert "is_recoverable" in result
        assert "retry_recommended" in result
        assert "strategy" in result


# ═══════════════════════════════════════════════════════════════════
# ExecutionObservation
# ═══════════════════════════════════════════════════════════════════


class TestExecutionObservation:
    def test_default_timestamp(self):
        obs = ExecutionObservation(tool_id="test", status="success")
        assert obs.timestamp is not None

    def test_to_dict(self):
        obs = ExecutionObservation(
            tool_id="tool:test",
            status="failure",
            error="something went wrong",
            duration_ms=150.0,
        )
        d = obs.to_dict()
        assert d["tool_id"] == "tool:test"
        assert d["status"] == "failure"
        assert d["error"] == "something went wrong"
        assert d["duration_ms"] == 150.0


# ═══════════════════════════════════════════════════════════════════
# FailureAnalysisResult
# ═══════════════════════════════════════════════════════════════════


class TestFailureAnalysisResult:
    def test_to_dict(self):
        result = FailureAnalysisResult(
            error_class=ErrorClass.TIMEOUT,
            root_cause="Operation timed out",
            is_recoverable=True,
            suggested_recovery="Retry with increased timeout",
            retry_recommended=True,
        )
        d = result.to_dict()
        assert d["error_class"] == "timeout"
        assert d["root_cause"] == "Operation timed out"
        assert d["is_recoverable"] is True
        assert d["retry_recommended"] is True


# ═══════════════════════════════════════════════════════════════════
# FailureAnalyzer: singleton
# ═══════════════════════════════════════════════════════════════════


class TestFailureAnalyzerSingleton:
    def test_get_failure_analyzer_returns_same_instance(self):
        fa1 = get_failure_analyzer()
        fa2 = get_failure_analyzer()
        assert fa1 is fa2
        assert isinstance(fa1, FailureAnalyzer)
