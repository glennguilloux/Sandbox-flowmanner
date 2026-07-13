"""ReplayAssertionEngine — validate replay state against expected behaviors (Phase 0.2).

Takes a completed run's replay state + event log and checks each expected
behavior assertion. Returns a structured report of passes/failures/warnings.

Item #9 enhancements:
- Baseline versioning: auto-invalidate on (model_id, pricing_version, template_version) change
- Cost: tight token ceiling (1.1-1.2x), compute from current pricing table
- Latency: p95 baseline × headroom, rolling-aggregate breach (N consecutive violations)
- Tool sequence: constrained partial order (required_edges, forbidden_tools, equivalence_classes)
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from enum import StrEnum
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
    BASELINE_VERSION = "baseline_version"


# ── Baseline version metadata ─────────────────────────────────────


@dataclass(frozen=True)
class BaselineVersion:
    """Identifies the exact baseline a set of expected_behaviors was derived from.

    Used for auto-invalidation: if any field drifts, the baseline is stale
    and must be re-extracted (pricing drift → auto-rebaseline; behavioral
    drift → human review).
    """

    model_id: str = ""
    pricing_table_version: str = ""
    template_version: str = ""

    def is_valid(self) -> bool:
        """Return True if all fields are populated (non-empty baseline)."""
        return bool(self.model_id and self.pricing_table_version and self.template_version)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class Severity(StrEnum):
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


# Default consecutive violations before latency assertion fails (Item #9)
DEFAULT_CONSECUTIVE_VIOLATIONS = 3


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
        *,
        current_baseline_version: BaselineVersion | None = None,
        latency_history: list[float] | None = None,
    ) -> list[AssertionResult]:
        """Replay events, check each assertion, return results.

        Args:
            db: Async database session
            run_id: UUID string identifying the execution run
            expected_behaviors: List of assertion dicts from the template
            current_baseline_version: If provided, check against stored baseline
                version in expected_behaviors. Baseline drift → auto-invalidation.
            latency_history: Historical latencies (seconds) for p95 rolling-
                aggregate breach detection. If not provided, single-violation
                mode is used (legacy behavior).

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
                        results.append(
                            self._check_latency(
                                state,
                                assertion,
                                latency_history=latency_history,
                            )
                        )
                    case AssertionType.TASK_COMPLETION:
                        results.append(self._check_completion(state, assertion))
                    case AssertionType.NO_CIRCUIT_BREAKER:
                        results.append(self._check_no_circuit_breaker(events, assertion))
                    case AssertionType.BASELINE_VERSION:
                        results.append(
                            self._check_baseline_version(
                                assertion,
                                current=current_baseline_version,
                            )
                        )
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
        """Check that the expected tools were called in the right order.

        Supports constrained partial order (Item #9):
        - ``required_edges``: list of [before, after] pairs — the ``before`` tool
          must appear before ``after`` in the actual sequence.
        - ``forbidden_tools``: tools that must NOT appear.
        - ``equivalence_classes``: dict mapping a canonical name → list of aliases
          that are treated as the same tool for ordering/counting.
        """
        expected_tools = assertion.get("expected_tools", [])
        order = assertion.get("order", "subset")
        max_calls = assertion.get("max_calls_per_tool", {})
        required_edges: list[list[str]] = assertion.get("required_edges", [])
        forbidden_tools: set[str] = set(assertion.get("forbidden_tools", []))
        equivalence_classes: dict[str, list[str]] = assertion.get("equivalence_classes", {})

        # Build alias → canonical mapping
        alias_map: dict[str, str] = {}
        for canonical, aliases in equivalence_classes.items():
            for alias in aliases:
                alias_map[alias] = canonical
            alias_map[canonical] = canonical

        def _canonical(name: str) -> str:
            return alias_map.get(name, name)

        # Extract tool call events
        tool_events = [e for e in events if e.type == SubstrateEventType.TOOL_CALL]
        raw_tools = [e.payload.get("tool_name") or e.payload.get("tool_id", "") for e in tool_events]
        actual_tools = [_canonical(t) for t in raw_tools]
        actual_counts = Counter(actual_tools)

        # Apply equivalence to expected/forgiven sets
        canonical_expected = [_canonical(t) for t in expected_tools]
        expected_set = set(canonical_expected)
        actual_set = set(actual_tools)
        missing = expected_set - actual_set
        extra = actual_set - expected_set

        # Check forbidden tools
        canonical_forbidden = {_canonical(t) for t in forbidden_tools}
        forbidden_found = actual_set & canonical_forbidden

        # Check order if exact
        order_ok = True
        if order == "exact" and not missing:
            filtered = [t for t in actual_tools if t in expected_set]
            order_ok = filtered == canonical_expected

        # Check required edges (partial ordering constraints)
        edge_violations: list[dict[str, Any]] = []
        for edge in required_edges:
            if len(edge) < 2:
                continue
            before, after = _canonical(edge[0]), _canonical(edge[1])
            try:
                before_idx = actual_tools.index(before)
                after_idx = actual_tools.index(after)
                if before_idx >= after_idx:
                    edge_violations.append(
                        {
                            "before": before,
                            "after": after,
                            "actual_before_idx": before_idx,
                            "actual_after_idx": after_idx,
                        }
                    )
            except ValueError:
                # One or both tools not found — already tracked by missing set
                pass

        # Check max call counts
        call_violations: dict[str, dict[str, int]] = {}
        for tool_name, limit in max_calls.items():
            canonical_name = _canonical(tool_name)
            actual_count = actual_counts.get(canonical_name, 0)
            if actual_count > limit:
                call_violations[tool_name] = {
                    "actual": actual_count,
                    "max": limit,
                }

        passed = not missing and order_ok and not call_violations and not forbidden_found and not edge_violations

        # Build message
        parts: list[str] = []
        if missing:
            parts.append(f"Missing tools: {', '.join(sorted(missing))}")
        if extra:
            parts.append(f"Extra tools: {', '.join(sorted(extra))}")
        if not order_ok:
            parts.append("Tool call order mismatch")
        if forbidden_found:
            parts.append(f"Forbidden tools found: {', '.join(sorted(forbidden_found))}")
        if edge_violations:
            parts.extend(f"Ordering violation: '{v['before']}' must precede '{v['after']}'" for v in edge_violations)
        if call_violations:
            for name, info in call_violations.items():
                parts.append(f"Tool '{name}' called {info['actual']}x (max {info['max']})")
        if not parts:
            parts.append(f"All {len(canonical_expected)} expected tools called correctly")

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
                "forbidden_found": sorted(forbidden_found),
                "edge_violations": edge_violations,
            },
            expected={
                "tools": expected_tools,
                "order": order,
                "max_calls_per_tool": max_calls,
                "required_edges": required_edges,
                "forbidden_tools": sorted(forbidden_tools),
                "equivalence_classes": equivalence_classes,
            },
            message="; ".join(parts),
        )

    def _check_cost(
        self,
        state: Any,
        assertion: dict[str, Any],
    ) -> AssertionResult:
        """Check that cost is within ceiling.

        Supports two modes (Item #9):
        - ``max_cost_usd``: absolute dollar ceiling (legacy)
        - ``max_tokens`` + ``pricing_table``: tight token ceiling (1.1-1.2x)
          computed from current pricing.  When both are present, the
          token-based ceiling takes precedence.
        """
        max_cost = assertion.get("max_cost_usd", float("inf"))
        warn_at_pct = assertion.get("warn_at_pct", 80)

        actual_cost = state.total_cost_usd or 0.0
        actual_tokens = state.total_tokens or 0

        # Token-ceiling mode (Item #9): recompute ceiling from current pricing
        max_tokens = assertion.get("max_tokens")
        pricing_table = assertion.get("pricing_table", {})
        model_id = assertion.get("model_id", "")
        if max_tokens is not None and pricing_table and model_id:
            # Look up current pricing
            entry = pricing_table.get(model_id) or pricing_table.get("default", {})
            input_rate = float(entry.get("input", 0.0))
            output_rate = float(entry.get("output", 0.0))
            # Conservative: assume worst-case (all tokens at higher rate)
            max_rate = max(input_rate, output_rate) if (input_rate or output_rate) else 0.0
            # Recompute dollar ceiling from token ceiling × current pricing
            if max_rate > 0:
                dynamic_ceiling = (max_tokens / 1_000_000) * max_rate
                # Prefer dynamic ceiling when token-based assertion is present
                max_cost = dynamic_ceiling

        pct_used = (actual_cost / max_cost * 100) if max_cost > 0 else 0

        # Token usage check (independent of dollar ceiling)
        token_pct = (actual_tokens / max_tokens * 100) if max_tokens else 0
        tokens_exceeded = max_tokens is not None and actual_tokens > max_tokens

        passed = actual_cost <= max_cost and not tokens_exceeded
        if pct_used >= warn_at_pct and passed:
            severity = Severity.WARNING
        elif passed:
            severity = Severity.INFO
        else:
            severity = Severity.FAILURE

        if passed:
            message = f"Cost ${actual_cost:.4f} within ${max_cost:.4f} ceiling"
            if max_tokens is not None:
                message += f" ({actual_tokens}/{max_tokens} tokens)"
        else:
            parts = []
            if actual_cost > max_cost:
                parts.append(f"Cost ${actual_cost:.4f} exceeds ${max_cost:.4f} ceiling")
            if tokens_exceeded:
                parts.append(f"Tokens {actual_tokens} exceeds ceiling {max_tokens}")
            message = "; ".join(parts)

        return AssertionResult(
            assertion_type=AssertionType.COST_CEILING,
            passed=passed,
            severity=severity,
            actual={
                "cost_usd": round(actual_cost, 6),
                "pct_used": round(pct_used, 1),
                "total_tokens": actual_tokens,
                "token_pct_used": round(token_pct, 1),
            },
            expected={
                "max_cost_usd": max_cost,
                "max_tokens": max_tokens,
                "warn_at_pct": warn_at_pct,
            },
            message=message,
        )

    def _check_latency(
        self,
        state: Any,
        assertion: dict[str, Any],
        *,
        latency_history: list[float] | None = None,
    ) -> AssertionResult:
        """Check that run duration is within limit.

        Supports two modes (Item #9):
        - ``max_duration_seconds``: absolute ceiling (legacy)
        - ``p95_headroom``: assert against p95 of baseline distribution ×
          headroom.  Requires ``consecutive_violations`` (default 3) before
          failing — single spikes are warnings only (survives provider jitter).
        """
        max_seconds = assertion.get("max_duration_seconds", float("inf"))
        warn_at_pct = assertion.get("warn_at_pct", 80)

        # Compute duration from state timestamps
        actual_seconds = 0.0
        if state.started_at and state.last_event_at:
            delta = state.last_event_at - state.started_at
            actual_seconds = delta.total_seconds()

        # p95-based ceiling (Item #9)
        p95_headroom = assertion.get("p95_headroom")
        consecutive_required = assertion.get(
            "consecutive_violations",
            DEFAULT_CONSECUTIVE_VIOLATIONS,
        )
        if p95_headroom is not None and latency_history and len(latency_history) >= 3:
            sorted_history = sorted(latency_history)
            p95_idx = int(len(sorted_history) * 0.95)
            p95_latency = sorted_history[min(p95_idx, len(sorted_history) - 1)]
            max_seconds = p95_latency * p95_headroom

            # Rolling-aggregate breach: count trailing consecutive violations
            # in the history (append current run duration to check)
            all_runs = [*latency_history, actual_seconds]
            consecutive_breaches = 0
            for run_latency in reversed(all_runs):
                if run_latency > max_seconds:
                    consecutive_breaches += 1
                else:
                    break

            if consecutive_breaches >= consecutive_required:
                passed = False
                severity = Severity.FAILURE
            elif consecutive_breaches > 0:
                passed = True  # single spike — warning only
                severity = Severity.WARNING
            else:
                passed = True
                severity = Severity.INFO

            pct_used = (actual_seconds / max_seconds * 100) if max_seconds > 0 else 0

            message = (
                f"Duration {actual_seconds:.0f}s vs p95x{p95_headroom} ceiling {max_seconds:.0f}s"
                f" ({consecutive_breaches}/{consecutive_required} consecutive breaches)"
            )
            return AssertionResult(
                assertion_type=AssertionType.LATENCY,
                passed=passed,
                severity=severity,
                actual={
                    "duration_seconds": round(actual_seconds, 1),
                    "pct_used": round(pct_used, 1),
                    "consecutive_breaches": consecutive_breaches,
                },
                expected={
                    "max_duration_seconds": round(max_seconds, 1),
                    "p95_latency": round(p95_latency, 1),
                    "p95_headroom": p95_headroom,
                    "consecutive_violations": consecutive_required,
                },
                message=message,
            )

        # Legacy absolute ceiling
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

    def _check_baseline_version(
        self,
        assertion: dict[str, Any],
        *,
        current: BaselineVersion | None = None,
    ) -> AssertionResult:
        """Check that the stored baseline version matches the current environment.

        Item #9: auto-invalidate on (model_id, pricing_table_version,
        template_version) change.  Separate token/cost drift (re-baseline
        on pricing) from behavioral drift (human review).
        """
        stored = BaselineVersion(
            model_id=assertion.get("model_id", ""),
            pricing_table_version=assertion.get("pricing_table_version", ""),
            template_version=assertion.get("template_version", ""),
        )
        if not stored.is_valid():
            return AssertionResult(
                assertion_type=AssertionType.BASELINE_VERSION,
                passed=True,
                severity=Severity.INFO,
                message="No baseline version stored — skipping check",
                expected=stored.to_dict(),
            )

        if current is None:
            return AssertionResult(
                assertion_type=AssertionType.BASELINE_VERSION,
                passed=False,
                severity=Severity.WARNING,
                message="Current baseline version not provided for comparison",
                expected=stored.to_dict(),
            )

        drift_fields = []
        if stored.model_id != current.model_id:
            drift_fields.append(f"model_id: {stored.model_id} → {current.model_id}")
        if stored.pricing_table_version != current.pricing_table_version:
            drift_fields.append(f"pricing: {stored.pricing_table_version} → {current.pricing_table_version}")
        if stored.template_version != current.template_version:
            drift_fields.append(f"template: {stored.template_version} → {current.template_version}")

        if drift_fields:
            return AssertionResult(
                assertion_type=AssertionType.BASELINE_VERSION,
                passed=False,
                severity=Severity.WARNING,
                actual=current.to_dict(),
                expected=stored.to_dict(),
                message=(
                    f"Baseline drift detected: {'; '.join(drift_fields)}. " f"Re-extract baseline from a fresh run."
                ),
            )

        return AssertionResult(
            assertion_type=AssertionType.BASELINE_VERSION,
            passed=True,
            severity=Severity.INFO,
            actual=current.to_dict(),
            expected=stored.to_dict(),
            message="Baseline version matches current environment",
        )


# ── Singleton ──────────────────────────────────────────────────────

_engine: ReplayAssertionEngine | None = None


def get_assertion_engine() -> ReplayAssertionEngine:
    """Get or create the ReplayAssertionEngine singleton."""
    global _engine
    if _engine is None:
        _engine = ReplayAssertionEngine()
    return _engine
