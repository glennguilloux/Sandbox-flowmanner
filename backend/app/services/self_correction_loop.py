"""SelfCorrectionLoop — bounded self-correction under cost ceilings (Q2-Q3 Chunk 6).

Provides a disciplined recovery loop for failed mission tasks:
- Classifies the failure via FailureAnalyzer
- Decides a recovery action via RecoveryPolicy
- Tracks retry budgets by cost, wall-clock, attempts, and depth
- Emits substrate events for every iteration (audit/replay)
- Stops on budget exhaustion and escalates to HITL or abort

Integration:
- Used by MissionExecutor when a task fails
- Consults FailureAnalyzer for error classification + per-error-class budgets
- Consults RecoveryPolicy for the recovery action
- Emits SELF_CORRECTION_ATTEMPTED / COMPLETED / ABORTED events
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.models.substrate_models import SubstrateEventType
from app.services.nexus.failure_analyzer import (
    ErrorBudget,
    ErrorClass,
    ExecutionObservation,
    FailureAnalysisResult,
    FailureAnalyzer,
)
from app.services.recovery_policy import RecoveryAction, RecoveryPolicy

logger = logging.getLogger(__name__)


# ── Mission-level self-correction budget ───────────────────────────


@dataclass
class SelfCorrectionBudget:
    """Budget limits for self-correction across ALL error classes in a mission.

    These are mission-level ceilings on top of the per-error-class budgets
    in FailureAnalyzer.  When any field is exhausted, no more correction
    attempts are allowed.
    """

    max_total_attempts: int = 10
    max_total_cost_usd: float = 2.00
    max_total_wall_clock_seconds: float = 600.0  # 10 minutes
    max_reflections: int = 3  # max REFLECT actions per mission

    # Runtime tracking
    total_attempts: int = 0
    total_cost_usd: float = 0.0
    total_wall_clock_ms: float = 0.0
    reflection_count: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def is_exhausted(self) -> tuple[bool, str]:
        """Check if any mission-level budget limit is exceeded.

        Returns:
            (is_exhausted, reason_string)
        """
        if self.total_attempts >= self.max_total_attempts:
            return True, (
                f"Self-correction attempt budget exhausted " f"({self.total_attempts}/{self.max_total_attempts})"
            )

        if self.total_cost_usd >= self.max_total_cost_usd:
            return True, (
                f"Self-correction cost budget exhausted " f"(${self.total_cost_usd:.4f}/${self.max_total_cost_usd:.2f})"
            )

        elapsed = time.monotonic() - self.started_at
        if elapsed >= self.max_total_wall_clock_seconds:
            return True, (
                f"Self-correction wall-clock budget exhausted " f"({elapsed:.1f}s/{self.max_total_wall_clock_seconds}s)"
            )

        return False, ""

    def record_attempt(self, cost_usd: float = 0.0, wall_clock_ms: float = 0.0) -> None:
        """Record a correction attempt against the mission budget."""
        self.total_attempts += 1
        self.total_cost_usd += cost_usd
        self.total_wall_clock_ms += wall_clock_ms

    def record_reflection(self) -> None:
        """Record a reflection action against the mission budget."""
        self.reflection_count += 1

    def can_reflect(self) -> bool:
        """Check if another reflection is allowed."""
        return self.reflection_count < self.max_reflections

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_attempts": self.total_attempts,
            "max_total_attempts": self.max_total_attempts,
            "total_cost_usd": self.total_cost_usd,
            "max_total_cost_usd": self.max_total_cost_usd,
            "total_wall_clock_ms": self.total_wall_clock_ms,
            "max_total_wall_clock_seconds": self.max_total_wall_clock_seconds,
            "reflection_count": self.reflection_count,
            "max_reflections": self.max_reflections,
        }


# ── Self-correction result ─────────────────────────────────────────


@dataclass
class SelfCorrectionResult:
    """Result of a self-correction attempt."""

    action_taken: RecoveryAction
    final_success: bool
    attempts_used: int
    total_cost_usd: float
    analysis: FailureAnalysisResult | None = None
    aborted_reason: str | None = None
    escalated_to_hitl: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_taken": self.action_taken.value,
            "final_success": self.final_success,
            "attempts_used": self.attempts_used,
            "total_cost_usd": self.total_cost_usd,
            "error_class": self.analysis.error_class.value if self.analysis else None,
            "aborted_reason": self.aborted_reason,
            "escalated_to_hitl": self.escalated_to_hitl,
        }


# ── Self-correction loop ───────────────────────────────────────────


class SelfCorrectionLoop:
    """Bounded self-correction loop for failed mission tasks.

    Usage::

        loop = SelfCorrectionLoop()
        result = await loop.correct(
            error=task_error,
            context={"task_id": ..., "mission_id": ...},
            task_fn=re_execute_task,  # async callable
            event_emitter=emit_fn,
        )
    """

    def __init__(
        self,
        failure_analyzer: FailureAnalyzer | None = None,
        recovery_policy: RecoveryPolicy | None = None,
        budget: SelfCorrectionBudget | None = None,
    ) -> None:
        self._failure_analyzer = failure_analyzer or FailureAnalyzer()
        self._recovery_policy = recovery_policy or RecoveryPolicy()
        self._budget = budget or SelfCorrectionBudget()
        self._execution_log: list[ExecutionObservation] = []

    @property
    def budget(self) -> SelfCorrectionBudget:
        return self._budget

    @property
    def failure_analyzer(self) -> FailureAnalyzer:
        return self._failure_analyzer

    @property
    def recovery_policy(self) -> RecoveryPolicy:
        return self._recovery_policy

    async def correct(
        self,
        *,
        error: Exception,
        context: dict[str, Any],
        event_emitter: Any | None = None,
    ) -> SelfCorrectionResult:
        """Run one iteration of the self-correction loop.

        This does NOT re-execute the task itself — it decides *what* to do
        and returns the decision.  The caller (MissionExecutor) is responsible
        for executing the actual retry/reflect/hitl/abort.

        Args:
            error: The exception that caused the failure
            context: Execution context (task_id, mission_id, etc.)
            event_emitter: Optional async callable(db, run_id, events) for substrate events

        Returns:
            SelfCorrectionResult with the decision
        """
        run_id = context.get("mission_id", "unknown")
        task_id = context.get("task_id")

        # 1. Check mission-level budget first
        budget_exhausted, budget_reason = self._budget.is_exhausted()
        if budget_exhausted:
            logger.warning("Self-correction budget exhausted: %s", budget_reason)
            result = SelfCorrectionResult(
                action_taken=RecoveryAction.ABORT,
                final_success=False,
                attempts_used=self._budget.total_attempts,
                total_cost_usd=self._budget.total_cost_usd,
                aborted_reason=budget_reason,
            )
            if event_emitter:
                await self._emit_event(
                    event_emitter,
                    run_id,
                    task_id,
                    SubstrateEventType.SELF_CORRECTION_ABORTED,
                    {"reason": budget_reason, "budget": self._budget.to_dict()},
                )
            return result

        # 2. Classify and analyze the failure
        wall_clock_ms = context.get("wall_clock_ms", 0.0)
        cost_usd = context.get("cost_usd", 0.0)

        analysis = self._failure_analyzer.analyze_failure(
            error=error,
            context=context,
            execution_log=self._execution_log,
            wall_clock_ms=wall_clock_ms,
            cost_usd=cost_usd,
        )

        # 3. Record the attempt against mission budget
        self._budget.record_attempt(cost_usd=cost_usd, wall_clock_ms=wall_clock_ms)

        # 4. Decide recovery action
        action = self._recovery_policy.decide(analysis)

        # 5. Handle reflection limit
        if action == RecoveryAction.REFLECT and not self._budget.can_reflect():
            logger.info(
                "Reflection budget exhausted (%d/%d), falling back to RETRY",
                self._budget.reflection_count,
                self._budget.max_reflections,
            )
            # Downgrade: if we can't reflect, try retry; if retry also not recommended, abort
            action = RecoveryAction.RETRY if analysis.retry_recommended else RecoveryAction.ABORT

        # 6. Emit substrate event
        event_payload = {
            "attempt_number": self._budget.total_attempts,
            "action": action.value,
            "error_class": analysis.error_class.value,
            "root_cause": analysis.root_cause,
            "is_recoverable": analysis.is_recoverable,
            "retry_recommended": analysis.retry_recommended,
            "confidence": analysis.confidence,
            "budget": self._budget.to_dict(),
            "error_class_budget": self._failure_analyzer.get_budget(analysis.error_class).to_dict()
            if self._failure_analyzer.get_budget(analysis.error_class)
            else None,
        }
        if event_emitter:
            await self._emit_event(
                event_emitter,
                run_id,
                task_id,
                SubstrateEventType.SELF_CORRECTION_ATTEMPTED,
                event_payload,
            )

        # 7. Record reflection if action is REFLECT
        if action == RecoveryAction.REFLECT:
            self._budget.record_reflection()

        # 8. Build result
        if action == RecoveryAction.ABORT:
            result = SelfCorrectionResult(
                action_taken=action,
                final_success=False,
                attempts_used=self._budget.total_attempts,
                total_cost_usd=self._budget.total_cost_usd,
                analysis=analysis,
                aborted_reason=analysis.root_cause,
            )
            if event_emitter:
                await self._emit_event(
                    event_emitter,
                    run_id,
                    task_id,
                    SubstrateEventType.SELF_CORRECTION_ABORTED,
                    {
                        "reason": analysis.root_cause,
                        "error_class": analysis.error_class.value,
                        "budget": self._budget.to_dict(),
                    },
                )
        elif action == RecoveryAction.ASK_HITL:
            result = SelfCorrectionResult(
                action_taken=action,
                final_success=False,
                attempts_used=self._budget.total_attempts,
                total_cost_usd=self._budget.total_cost_usd,
                analysis=analysis,
                escalated_to_hitl=True,
            )
        else:
            # RETRY, REFLECT, or FALLBACK_PROVIDER — caller will re-execute
            result = SelfCorrectionResult(
                action_taken=action,
                final_success=False,
                attempts_used=self._budget.total_attempts,
                total_cost_usd=self._budget.total_cost_usd,
                analysis=analysis,
            )

        logger.info(
            "Self-correction decision: action=%s error_class=%s attempt=%d/%d",
            action.value,
            analysis.error_class.value,
            self._budget.total_attempts,
            self._budget.max_total_attempts,
        )

        return result

    async def mark_success(
        self,
        *,
        context: dict[str, Any],
        event_emitter: Any | None = None,
    ) -> None:
        """Mark a successful correction (task eventually succeeded).

        Emits SELF_CORRECTION_COMPLETED event.
        """
        run_id = context.get("mission_id", "unknown")
        task_id = context.get("task_id")

        if event_emitter:
            await self._emit_event(
                event_emitter,
                run_id,
                task_id,
                SubstrateEventType.SELF_CORRECTION_COMPLETED,
                {
                    "total_attempts": self._budget.total_attempts,
                    "total_cost_usd": self._budget.total_cost_usd,
                    "total_wall_clock_ms": self._budget.total_wall_clock_ms,
                    "reflection_count": self._budget.reflection_count,
                },
            )

        logger.info(
            "Self-correction completed after %d attempts ($%.4f)",
            self._budget.total_attempts,
            self._budget.total_cost_usd,
        )

    @staticmethod
    async def _emit_event(
        event_emitter: Any,
        run_id: str,
        task_id: str | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Emit a substrate event.  Non-critical — failures are logged and swallowed."""
        try:
            await event_emitter(
                run_id,
                [
                    {
                        "type": event_type,
                        "payload": payload,
                        "actor": "self_correction_loop",
                        "task_id": task_id,
                    }
                ],
            )
        except Exception as e:
            logger.debug("Failed to emit self-correction event %s: %s", event_type, e)


# ── Module-level factory ───────────────────────────────────────────

_default_loop: SelfCorrectionLoop | None = None


def get_self_correction_loop(
    budget: SelfCorrectionBudget | None = None,
) -> SelfCorrectionLoop:
    """Get or create the SelfCorrectionLoop singleton."""
    global _default_loop
    if _default_loop is None:
        _default_loop = SelfCorrectionLoop(budget=budget)
    return _default_loop


def reset_self_correction_loop() -> None:
    """Reset the singleton (for testing)."""
    global _default_loop
    _default_loop = None
