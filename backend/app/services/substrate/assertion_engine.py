"""ReplayAssertionEngine — validate replay state against expected behaviors (Phase 0.2).

Takes a completed run's replay state + event log and checks each expected
behavior assertion. Returns a structured report of passes/failures/warnings.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from app.models.substrate_models import SubstrateEvent, SubstrateEventType
from app.services.substrate.event_log import get_event_log
from app.services.substrate.replay_engine import get_replay_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Assertion types ─────────────────────────────────────────────────


class AssertionType:
    TOOL_SEQUENCE = "tool_sequence"
    COST_CEILING = "cost_ceiling"
    LATENCY = "latency"
    TASK_COMPLETION = "task_completion"
    NO_CIRCUIT_BREAKER = "no_circuit_breaker"


class Severity(str, Enum):
    FAILURE = "failure"
    WARNING = "warning"
    INFO = "info"


# ── Result model ────────────────────────────────────────────────────


@dataclass
class AssertionResult:
    """Result of evaluating a single assertion."""

    assertion_type: str
    passed: bool
    severity: Severity
    actual: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


# ── Engine ──────────────────────────────────────────────────────────


class ReplayAssertionEngine:
    """Evaluates expected behavior assertions against a run's replay state."""

    def __init__(self):
        self._event_log = get_event_log()
        self._replay_engine = get_replay_engine()

    async def evaluate(
        self,
        db: AsyncSession,
        run_id: str,
        expected_behaviors: list[dict[str, Any]],
    ) -> list[AssertionResult]:
        """Replay events, check each assertion, return results.

        Args:
            db: Async database session
            run_id: UUID string identifying the execution run
            expected_behaviors: List of assertion dicts from the template

        Returns:
            List of AssertionResult objects
        """
        if not expected_behaviors:
            return []

        # Replay events for the run
        state = await self._replay_engine.rebuild_state(db, run_id)
        events = await self._event_log.get_events(db, run_id)

        results: list[AssertionResult] = []
        for assertion in expected_behaviors:
            assertion_type = assertion.get("type", "")
            try:
                match assertion_type:
                    case AssertionType.TOOL_SEQUENCE:
                        results.append(self._check_tool_sequence(events, assertion))
                    case AssertionType.COST_CEILING:
                        results.append(self._check_cost(state, assertion))
                    case AssertionType.LATENCY:
                        results.append(self._check_latency(state, assertion))
                    case AssertionType.TASK_COMPLETION:
                        results.append(self._check_completion(state, assertion))
                    case AssertionType.NO_CIRCUIT_BREAKER:
                        results.append(self._check_no_circuit_breaker(events, assertion))
                    case _:
                        results.append(
                            AssertionResult(
                                assertion_type=assertion_type,
                                passed=False,
                                severity=Severity.WARNING,
                                message=f"Unknown assertion type: {assertion_type}",
                            )
                        )
            except Exception as exc:
                logger.warning(
                    "Assertion evaluation error for type=%s run=%s: %s",
                    assertion_type,
                    run_id,
                    exc,
                )
                results.append(
                    AssertionResult(
                        assertion_type=assertion_type,
                        passed=False,
                        severity=Severity.FAILURE,
                        message=f"Evaluation error: {exc}",
                    )
                )

        return results

    # ── Assertion checkers ──────────────────────────────────────────

    def _check_tool_sequence(
        self,
        events: list[SubstrateEvent],
        assertion: dict[str, Any],
    ) -> AssertionResult:
        """Check that the expected tools were called in the right order."""
        expected_tools = assertion.get("expected_tools", [])
        order = assertion.get("order", "subset")
        max_calls = assertion.get("max_calls_per_tool", {})

        # Extract tool call events
        tool_events = [e for e in events if e.type == SubstrateEventType.TOOL_CALL]
        actual_tools = [e.payload.get("tool_name") or e.payload.get("tool_id", "") for e in tool_events]
        actual_counts = Counter(actual_tools)

        # Check for missing tools
        expected_set = set(expected_tools)
        actual_set = set(actual_tools)
        missing = expected_set - actual_set
        extra = actual_set - expected_set

        # Check order if exact
        order_ok = True
        if order == "exact" and not missing:
            # Filter actual to expected tools and check order
            filtered = [t for t in actual_tools if t in expected_set]
            order_ok = filtered == expected_tools

        # Check max call counts
        call_violations: dict[str, dict[str, int]] = {}
        for tool_name, limit in max_calls.items():
            actual_count = actual_counts.get(tool_name, 0)
            if actual_count > limit:
                call_violations[tool_name] = {
                    "actual": actual_count,
                    "max": limit,
                }

        passed = not missing and order_ok and not call_violations

        # Build message
        parts: list[str] = []
        if missing:
            parts.append(f"Missing tools: {', '.join(sorted(missing))}")
        if extra:
            parts.append(f"Extra tools: {', '.join(sorted(extra))}")
        if not order_ok:
            parts.append("Tool call order mismatch")
        if call_violations:
            for name, info in call_violations.items():
                parts.append(f"Tool '{name}' called {info['actual']}x (max {info['max']})")
        if not parts:
            parts.append(f"All {len(expected_tools)} expected tools called correctly")

        severity = Severity.INFO if passed else Severity.FAILURE

        return AssertionResult(
            assertion_type=AssertionType.TOOL_SEQUENCE,
            passed=passed,
            severity=severity,
            actual={
                "tools_called": actual_tools,
                "call_counts": dict(actual_counts),
                "missing": sorted(missing),
                "extra": sorted(extra),
            },
            expected={
                "tools": expected_tools,
                "order": order,
                "max_calls_per_tool": max_calls,
            },
            message="; ".join(parts),
        )

    def _check_cost(
        self,
        state: Any,
        assertion: dict[str, Any],
    ) -> AssertionResult:
        """Check that cost is within ceiling."""
        max_cost = assertion.get("max_cost_usd", float("inf"))
        warn_at_pct = assertion.get("warn_at_pct", 80)

        actual_cost = state.total_cost_usd or 0.0
        pct_used = (actual_cost / max_cost * 100) if max_cost > 0 else 0

        passed = actual_cost <= max_cost
        if pct_used >= warn_at_pct and passed:
            severity = Severity.WARNING
        elif passed:
            severity = Severity.INFO
        else:
            severity = Severity.FAILURE

        if passed:
            message = f"Cost ${actual_cost:.4f} within ${max_cost:.4f} ceiling"
        else:
            message = f"Cost ${actual_cost:.4f} exceeds ${max_cost:.4f} ceiling"

        return AssertionResult(
            assertion_type=AssertionType.COST_CEILING,
            passed=passed,
            severity=severity,
            actual={"cost_usd": round(actual_cost, 6), "pct_used": round(pct_used, 1)},
            expected={"max_cost_usd": max_cost, "warn_at_pct": warn_at_pct},
            message=message,
        )

    def _check_latency(
        self,
        state: Any,
        assertion: dict[str, Any],
    ) -> AssertionResult:
        """Check that run duration is within limit."""
        max_seconds = assertion.get("max_duration_seconds", float("inf"))
        warn_at_pct = assertion.get("warn_at_pct", 80)

        # Compute duration from state timestamps
        actual_seconds = 0.0
        if state.started_at and state.last_event_at:
            delta = state.last_event_at - state.started_at
            actual_seconds = delta.total_seconds()

        pct_used = (actual_seconds / max_seconds * 100) if max_seconds > 0 else 0

        passed = actual_seconds <= max_seconds
        if pct_used >= warn_at_pct and passed:
            severity = Severity.WARNING
        elif passed:
            severity = Severity.INFO
        else:
            severity = Severity.FAILURE

        if passed:
            message = f"Duration {actual_seconds:.0f}s within {max_seconds:.0f}s limit"
        else:
            message = f"Duration {actual_seconds:.0f}s exceeds {max_seconds:.0f}s limit"

        return AssertionResult(
            assertion_type=AssertionType.LATENCY,
            passed=passed,
            severity=severity,
            actual={
                "duration_seconds": round(actual_seconds, 1),
                "pct_used": round(pct_used, 1),
            },
            expected={"max_duration_seconds": max_seconds, "warn_at_pct": warn_at_pct},
            message=message,
        )

    def _check_completion(
        self,
        state: Any,
        assertion: dict[str, Any],
    ) -> AssertionResult:
        """Check task completion counts."""
        min_completed = assertion.get("min_tasks_completed", 0)
        max_failed = assertion.get("max_tasks_failed", 0)

        completed = len(state.completed_tasks)
        failed = len(state.failed_tasks)

        passed = completed >= min_completed and failed <= max_failed
        severity = Severity.INFO if passed else Severity.FAILURE

        if passed:
            message = f"{completed} tasks completed, {failed} failed"
        else:
            parts: list[str] = []
            if completed < min_completed:
                parts.append(f"Only {completed}/{min_completed} tasks completed")
            if failed > max_failed:
                parts.append(f"{failed} tasks failed (max {max_failed})")
            message = "; ".join(parts)

        return AssertionResult(
            assertion_type=AssertionType.TASK_COMPLETION,
            passed=passed,
            severity=severity,
            actual={"completed": completed, "failed": failed},
            expected={
                "min_tasks_completed": min_completed,
                "max_tasks_failed": max_failed,
            },
            message=message,
        )

    def _check_no_circuit_breaker(
        self,
        events: list[SubstrateEvent],
        assertion: dict[str, Any],
    ) -> AssertionResult:
        """Check that no circuit breaker was triggered."""
        cb_events = [
            e
            for e in events
            if e.type
            in (
                SubstrateEventType.CIRCUIT_BREAKER_TRIGGERED,
                SubstrateEventType.CIRCUIT_BREAKER_BROKEN,
            )
        ]

        passed = len(cb_events) == 0
        severity = Severity.INFO if passed else Severity.FAILURE

        if passed:
            message = "No circuit breaker events detected"
        else:
            message = f"Circuit breaker triggered {len(cb_events)} time(s)"

        return AssertionResult(
            assertion_type=AssertionType.NO_CIRCUIT_BREAKER,
            passed=passed,
            severity=severity,
            actual={"circuit_breaker_events": len(cb_events)},
            expected={"max_circuit_breaker_events": 0},
            message=message,
        )


# ── Singleton ──────────────────────────────────────────────────────

_engine: ReplayAssertionEngine | None = None


def get_assertion_engine() -> ReplayAssertionEngine:
    """Get or create the ReplayAssertionEngine singleton."""
    global _engine
    if _engine is None:
        _engine = ReplayAssertionEngine()
    return _engine
