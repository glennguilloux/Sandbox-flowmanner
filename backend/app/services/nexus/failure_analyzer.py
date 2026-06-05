"""
Failure Analyzer - Intelligent Failure Analysis with Budget Enforcement (H2.2)

Provides intelligent failure analysis for the recursive planning loop:
- Classifies errors by type (timeout, validation, resource, logic, etc.)
- Identifies root causes
- Suggests recovery strategies
- Recommends alternative tools
- Tracks failure patterns for learning
- **H2.2: Budget-per-error-class** — each error class has retry/wall-clock/cost budgets

Integration:
- Used by MetaLoopAgent in plan_execute_observe() loop
- Informs intelligent re-planning decisions
- Prevents repeating failed approaches
- Enforces per-error-class budget limits
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ErrorClass(str, Enum):
    """Classification of error types for recovery planning"""

    TIMEOUT = "timeout"
    VALIDATION = "validation"
    RESOURCE = "resource"
    LOGIC = "logic"
    NETWORK = "network"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"


# ── H2.2: Budget per error class ───────────────────────────────────


@dataclass
class ErrorBudget:
    """Budget limits for a single error class.

    When any budget is exhausted, retries for that error class stop
    and the mission transitions to a permanent failure.
    """

    max_retries: int = 3
    max_wall_clock_seconds: float = 300.0  # 5 minutes total retry time
    max_cost_usd: float = 1.00  # $1.00 total retry cost

    # Runtime tracking (reset per mission)
    retry_count: int = 0
    total_wall_clock_ms: float = 0.0
    total_cost_usd: float = 0.0
    started_at: float = 0.0

    def is_exhausted(self) -> tuple[bool, str]:
        """Check if any budget limit has been exceeded.

        Wall-clock budget uses elapsed time from the first retry's started_at,
        not accumulated per-attempt time.

        Returns:
            (is_exhausted, reason_string)
        """
        if self.retry_count >= self.max_retries:
            return (
                True,
                f"Retry budget exhausted ({self.retry_count}/{self.max_retries})",
            )

        # H2.2 fix: Use elapsed wall-clock time from first retry, not accumulated
        if self.max_wall_clock_seconds > 0 and self.started_at > 0:
            elapsed_seconds = time.monotonic() - self.started_at
            if elapsed_seconds >= self.max_wall_clock_seconds:
                return (
                    True,
                    f"Wall-clock budget exhausted ({elapsed_seconds:.1f}s/{self.max_wall_clock_seconds}s)",
                )

        if self.total_cost_usd >= self.max_cost_usd:
            return (
                True,
                f"Cost budget exhausted (${self.total_cost_usd:.4f}/${self.max_cost_usd:.2f})",
            )
        return False, ""

    def record_attempt(self, wall_clock_ms: float = 0.0, cost_usd: float = 0.0) -> None:
        """Record a retry attempt against the budget."""
        self.retry_count += 1
        self.total_wall_clock_ms += wall_clock_ms
        self.total_cost_usd += cost_usd
        if self.started_at == 0.0:
            self.started_at = time.monotonic()

    def to_dict(self) -> dict:
        return {
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "total_wall_clock_ms": self.total_wall_clock_ms,
            "max_wall_clock_seconds": self.max_wall_clock_seconds,
            "total_cost_usd": self.total_cost_usd,
            "max_cost_usd": self.max_cost_usd,
        }


# Default budgets per error class (tuneable)
DEFAULT_ERROR_BUDGETS: dict[ErrorClass, ErrorBudget] = {
    ErrorClass.TIMEOUT: ErrorBudget(
        max_retries=5, max_wall_clock_seconds=600.0, max_cost_usd=0.50
    ),
    ErrorClass.VALIDATION: ErrorBudget(
        max_retries=1, max_wall_clock_seconds=60.0, max_cost_usd=0.10
    ),
    ErrorClass.RESOURCE: ErrorBudget(
        max_retries=3, max_wall_clock_seconds=120.0, max_cost_usd=0.25
    ),
    ErrorClass.LOGIC: ErrorBudget(
        max_retries=1, max_wall_clock_seconds=30.0, max_cost_usd=0.10
    ),
    ErrorClass.NETWORK: ErrorBudget(
        max_retries=5, max_wall_clock_seconds=300.0, max_cost_usd=0.50
    ),
    ErrorClass.PERMISSION: ErrorBudget(
        max_retries=0, max_wall_clock_seconds=0.0, max_cost_usd=0.0
    ),
    ErrorClass.NOT_FOUND: ErrorBudget(
        max_retries=2, max_wall_clock_seconds=60.0, max_cost_usd=0.10
    ),
    ErrorClass.RATE_LIMIT: ErrorBudget(
        max_retries=5, max_wall_clock_seconds=600.0, max_cost_usd=0.50
    ),
    ErrorClass.UNKNOWN: ErrorBudget(
        max_retries=1, max_wall_clock_seconds=120.0, max_cost_usd=0.25
    ),
}


@dataclass
class ExecutionObservation:
    """Observation from tool execution for the observe phase"""

    tool_id: str
    status: str  # "success", "failure", "partial"
    output: Any | None = None
    error: str | None = None
    duration_ms: float = 0.0
    failure_analysis: dict[str, Any] | None = None
    recovery_attempted: bool = False
    recovery_successful: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "status": self.status,
            "output": str(self.output)[:200] if self.output else None,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "failure_analysis": self.failure_analysis,
            "recovery_attempted": self.recovery_attempted,
            "recovery_successful": self.recovery_successful,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class FailureAnalysisResult:
    """Result of failure analysis"""

    error_class: ErrorClass
    root_cause: str
    is_recoverable: bool
    suggested_recovery: str
    retry_recommended: bool
    alternative_tools: list[str] = field(default_factory=list)
    context_updates: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_class": self.error_class.value,
            "root_cause": self.root_cause,
            "is_recoverable": self.is_recoverable,
            "suggested_recovery": self.suggested_recovery,
            "retry_recommended": self.retry_recommended,
            "alternative_tools": self.alternative_tools,
            "context_updates": self.context_updates,
            "confidence": self.confidence,
        }


class FailureAnalyzer:
    """
    Analyzes execution failures with per-error-class budget enforcement (H2.2).

    Provides intelligent failure analysis for the recursive planning loop:
    - Classifies errors by type
    - Identifies root causes
    - Suggests recovery strategies
    - Recommends alternative tools
    - Tracks failure patterns
    - **H2.2**: Enforces per-error-class budgets (retry count, wall-clock, cost)
    """

    def __init__(self):
        self._failure_history: list[dict[str, Any]] = []
        self._pattern_cache: dict[str, int] = {}  # error_pattern -> count

        # H2.2: Per-error-class budgets (reset per mission)
        self._budgets: dict[ErrorClass, ErrorBudget] = {
            ec: ErrorBudget(
                max_retries=b.max_retries,
                max_wall_clock_seconds=b.max_wall_clock_seconds,
                max_cost_usd=b.max_cost_usd,
            )
            for ec, b in DEFAULT_ERROR_BUDGETS.items()
        }

        # Recovery strategies by error class
        self._recovery_strategies = {
            ErrorClass.TIMEOUT: self._recover_timeout,
            ErrorClass.VALIDATION: self._recover_validation,
            ErrorClass.RESOURCE: self._recover_resource,
            ErrorClass.LOGIC: self._recover_logic,
            ErrorClass.NETWORK: self._recover_network,
            ErrorClass.PERMISSION: self._recover_permission,
            ErrorClass.NOT_FOUND: self._recover_not_found,
            ErrorClass.RATE_LIMIT: self._recover_rate_limit,
            ErrorClass.UNKNOWN: self._recover_unknown,
        }

        # Alternative tools by capability
        self._alternative_tools = {
            "tool:recall_memory": ["search_knowledge", "query_rag"],
            "search_knowledge": ["tool:recall_memory", "web_search"],
            "query_rag": ["search_knowledge", "web_search"],
            "web_search": ["search_knowledge", "query_rag"],
            "execute_code": ["query_rag"],
        }

    def analyze_failure(
        self,
        error: Exception,
        context: dict[str, Any],
        execution_log: list[ExecutionObservation],
        *,
        wall_clock_ms: float = 0.0,
        cost_usd: float = 0.0,
    ) -> FailureAnalysisResult:
        """
        Analyze what went wrong during execution.

        H2.2: Also checks the error-class budget.  If the budget is exhausted,
        the failure is marked as non-recoverable regardless of the error type.

        Args:
            error: The exception that occurred
            context: Current execution context
            execution_log: Log of previous executions in this cycle
            wall_clock_ms: Wall-clock time spent on this attempt (for budget tracking)
            cost_usd: Cost incurred on this attempt (for budget tracking)

        Returns:
            FailureAnalysisResult with recovery recommendations
        """
        # Classify the error
        error_class = self.classify_error(error)

        # H2.2: Check budget before analyzing recovery
        budget = self._budgets.get(error_class)
        if budget is not None:
            budget.record_attempt(wall_clock_ms=wall_clock_ms, cost_usd=cost_usd)
            is_exhausted, exhaust_reason = budget.is_exhausted()
            if is_exhausted:
                logger.warning(
                    "Budget exhausted for %s: %s (retries=%d, wall=%.1fs, cost=$%.4f)",
                    error_class.value,
                    exhaust_reason,
                    budget.retry_count,
                    budget.total_wall_clock_ms / 1000.0,
                    budget.total_cost_usd,
                )
                return FailureAnalysisResult(
                    error_class=error_class,
                    root_cause=f"Budget exhausted: {exhaust_reason}",
                    is_recoverable=False,
                    suggested_recovery=f"{exhaust_reason} — aborting mission",
                    retry_recommended=False,
                    alternative_tools=[],
                    context_updates={
                        "budget_exhausted": True,
                        "exhaust_reason": exhaust_reason,
                    },
                    confidence=1.0,
                )

        # Get the last observation for context
        last_obs = execution_log[-1] if execution_log else None
        tool_id = last_obs.tool_id if last_obs else "unknown"

        # Analyze root cause
        root_cause = self._identify_root_cause(error, error_class, context, last_obs)

        # Get recovery strategy
        recovery_func = self._recovery_strategies.get(
            error_class, self._recover_unknown
        )
        recovery_result = recovery_func(error, context, last_obs)

        # Get alternative tools
        alternatives = self._alternative_tools.get(tool_id, [])

        # Record failure for pattern learning
        self._record_failure(error_class, tool_id, root_cause)

        result = FailureAnalysisResult(
            error_class=error_class,
            root_cause=root_cause,
            is_recoverable=recovery_result["is_recoverable"],
            suggested_recovery=recovery_result["strategy"],
            retry_recommended=recovery_result["retry_recommended"],
            alternative_tools=alternatives,
            context_updates=recovery_result.get("context_updates", {}),
            confidence=recovery_result.get("confidence", 0.8),
        )

        logger.info(
            f"Failure analysis: {error_class.value} - {root_cause} (recoverable: {result.is_recoverable})"
        )

        return result

    def classify_error(self, error: Exception) -> ErrorClass:
        """
        Classify error type based on exception characteristics.

        Args:
            error: Exception to classify

        Returns:
            ErrorClass enum value
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()

        # Timeout errors
        if any(kw in error_str for kw in ["timeout", "timed out", "deadline"]):
            return ErrorClass.TIMEOUT
        if "timeout" in error_type:
            return ErrorClass.TIMEOUT

        # Validation errors
        if any(
            kw in error_str
            for kw in ["validation", "invalid", "schema", "required field"]
        ):
            return ErrorClass.VALIDATION
        if any(kw in error_type for kw in ["validation", "value"]):
            return ErrorClass.VALIDATION

        # Resource errors
        if any(
            kw in error_str
            for kw in ["memory", "disk", "resource", "quota", "limit exceeded"]
        ):
            return ErrorClass.RESOURCE

        # Network errors
        if any(
            kw in error_str
            for kw in ["connection", "network", "dns", "socket", "refused"]
        ):
            return ErrorClass.NETWORK
        if any(kw in error_type for kw in ["connection", "network", "socket"]):
            return ErrorClass.NETWORK

        # Permission errors
        if any(
            kw in error_str
            for kw in ["permission", "unauthorized", "forbidden", "access denied"]
        ):
            return ErrorClass.PERMISSION
        if any(kw in error_type for kw in ["permission", "auth"]):
            return ErrorClass.PERMISSION

        # Not found errors
        if any(kw in error_str for kw in ["not found", "does not exist", "no such"]):
            return ErrorClass.NOT_FOUND

        # Rate limit errors
        if any(kw in error_str for kw in ["rate limit", "too many", "throttl"]):
            return ErrorClass.RATE_LIMIT

        # Logic errors (default for many exception types)
        if any(
            kw in error_type for kw in ["value", "type", "key", "index", "attribute"]
        ):
            return ErrorClass.LOGIC

        return ErrorClass.UNKNOWN

    def suggest_recovery(
        self, error_class: ErrorClass, context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Suggest recovery strategy based on error classification.

        Args:
            error_class: Classified error type
            context: Current execution context

        Returns:
            Recovery strategy dictionary
        """
        recovery_func = self._recovery_strategies.get(
            error_class, self._recover_unknown
        )
        return recovery_func(Exception("Generic error"), context, None)

    def should_retry(
        self, error_class: ErrorClass, attempt_count: int, max_retries: int = 3
    ) -> bool:
        """
        Decide if retry makes sense for this error type.

        Args:
            error_class: Classified error type
            attempt_count: Number of attempts so far
            max_retries: Maximum retry attempts

        Returns:
            True if retry is recommended
        """
        if attempt_count >= max_retries:
            return False

        # Errors that benefit from retry
        retry_beneficial = {
            ErrorClass.TIMEOUT,
            ErrorClass.NETWORK,
            ErrorClass.RATE_LIMIT,
            ErrorClass.RESOURCE,
        }

        # Errors that will not be fixed by retry
        retry_futile = {
            ErrorClass.VALIDATION,
            ErrorClass.PERMISSION,
            ErrorClass.NOT_FOUND,
            ErrorClass.LOGIC,
        }

        if error_class in retry_beneficial:
            return True
        elif error_class in retry_futile:
            return False
        else:
            # Unknown errors: allow one retry
            return attempt_count < 1

    def _identify_root_cause(
        self,
        error: Exception,
        error_class: ErrorClass,
        context: dict[str, Any],
        last_obs: ExecutionObservation | None,
    ) -> str:
        """Identify the root cause of the failure"""
        error_str = str(error)

        if error_class == ErrorClass.TIMEOUT:
            return f"Operation exceeded time limit: {error_str[:100]}"
        elif error_class == ErrorClass.VALIDATION:
            return f"Input validation failed: {error_str[:100]}"
        elif error_class == ErrorClass.RESOURCE:
            return f"Resource constraint: {error_str[:100]}"
        elif error_class == ErrorClass.NETWORK:
            return f"Network connectivity issue: {error_str[:100]}"
        elif error_class == ErrorClass.PERMISSION:
            return f"Access denied: {error_str[:100]}"
        elif error_class == ErrorClass.NOT_FOUND:
            return f"Required resource not found: {error_str[:100]}"
        elif error_class == ErrorClass.RATE_LIMIT:
            return f"Rate limit exceeded: {error_str[:100]}"
        elif error_class == ErrorClass.LOGIC:
            return f"Logic error in execution: {error_str[:100]}"
        else:
            return f"Unknown error: {error_str[:100]}"

    def _recover_timeout(self, error, context, last_obs) -> dict[str, Any]:
        return {
            "is_recoverable": True,
            "retry_recommended": True,
            "strategy": "Retry with increased timeout or use faster alternative tool",
            "context_updates": {"timeout_multiplier": 2},
            "confidence": 0.9,
        }

    def _recover_validation(self, error, context, last_obs) -> dict[str, Any]:
        return {
            "is_recoverable": True,
            "retry_recommended": False,
            "strategy": "Fix input parameters based on schema requirements",
            "context_updates": {"validation_mode": "strict"},
            "confidence": 0.85,
        }

    def _recover_resource(self, error, context, last_obs) -> dict[str, Any]:
        return {
            "is_recoverable": True,
            "retry_recommended": True,
            "strategy": "Wait and retry, or use less resource-intensive alternative",
            "context_updates": {"resource_mode": "conservative"},
            "confidence": 0.7,
        }

    def _recover_logic(self, error, context, last_obs) -> dict[str, Any]:
        return {
            "is_recoverable": True,
            "retry_recommended": False,
            "strategy": "Adjust parameters or try alternative approach",
            "context_updates": {"logic_check": True},
            "confidence": 0.6,
        }

    def _recover_network(self, error, context, last_obs) -> dict[str, Any]:
        return {
            "is_recoverable": True,
            "retry_recommended": True,
            "strategy": "Retry with exponential backoff, check connectivity",
            "context_updates": {"network_retry": True},
            "confidence": 0.85,
        }

    def _recover_permission(self, error, context, last_obs) -> dict[str, Any]:
        return {
            "is_recoverable": False,
            "retry_recommended": False,
            "strategy": "Check credentials and permissions, cannot auto-recover",
            "context_updates": {},
            "confidence": 0.95,
        }

    def _recover_not_found(self, error, context, last_obs) -> dict[str, Any]:
        return {
            "is_recoverable": True,
            "retry_recommended": False,
            "strategy": "Use alternative data source or broaden search",
            "context_updates": {"search_mode": "broad"},
            "confidence": 0.8,
        }

    def _recover_rate_limit(self, error, context, last_obs) -> dict[str, Any]:
        return {
            "is_recoverable": True,
            "retry_recommended": True,
            "strategy": "Wait and retry with exponential backoff",
            "context_updates": {"rate_limit_wait": 60},
            "confidence": 0.9,
        }

    def _recover_unknown(self, error, context, last_obs) -> dict[str, Any]:
        return {
            "is_recoverable": True,
            "retry_recommended": True,
            "strategy": "Generic retry with modified parameters",
            "context_updates": {},
            "confidence": 0.5,
        }

    def _record_failure(self, error_class: ErrorClass, tool_id: str, root_cause: str):
        """Record failure for pattern learning"""
        pattern_key = f"{error_class.value}:{tool_id}"
        self._pattern_cache[pattern_key] = self._pattern_cache.get(pattern_key, 0) + 1

        self._failure_history.append(
            {
                "error_class": error_class.value,
                "tool_id": tool_id,
                "root_cause": root_cause,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        # Keep history bounded
        if len(self._failure_history) > 100:
            self._failure_history = self._failure_history[-50:]

    def get_budget(self, error_class: ErrorClass) -> ErrorBudget | None:
        """Get the current budget for an error class (H2.2)."""
        return self._budgets.get(error_class)

    def reset_budgets(self) -> None:
        """Reset all error-class budgets (e.g., at start of a new mission)."""
        self._budgets = {
            ec: ErrorBudget(
                max_retries=b.max_retries,
                max_wall_clock_seconds=b.max_wall_clock_seconds,
                max_cost_usd=b.max_cost_usd,
            )
            for ec, b in DEFAULT_ERROR_BUDGETS.items()
        }
        logger.debug("Error-class budgets reset")

    def is_budget_exhausted(self, error_class: ErrorClass) -> tuple[bool, str]:
        """Check if the budget for an error class is exhausted.

        Returns:
            (is_exhausted, reason_string)
        """
        budget = self._budgets.get(error_class)
        if budget is None:
            return False, ""
        return budget.is_exhausted()

    def get_budget_summary(self) -> dict[str, dict]:
        """Get a summary of all error-class budgets."""
        return {ec.value: budget.to_dict() for ec, budget in self._budgets.items()}

    def get_failure_patterns(self) -> dict[str, int]:
        """Get observed failure patterns"""
        return self._pattern_cache.copy()

    def get_common_failures(self, limit: int = 5) -> list[dict[str, Any]]:
        """Get most common failure patterns"""
        sorted_patterns = sorted(
            self._pattern_cache.items(), key=lambda x: x[1], reverse=True
        )
        return [{"pattern": p, "count": c} for p, c in sorted_patterns[:limit]]


# Singleton instance
_failure_analyzer: Optional["FailureAnalyzer"] = None


def get_failure_analyzer() -> FailureAnalyzer:
    """Get or create the failure analyzer singleton"""
    global _failure_analyzer
    if _failure_analyzer is None:
        _failure_analyzer = FailureAnalyzer()
    return _failure_analyzer
