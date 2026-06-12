"""Depth Policy — deterministic reasoning depth decisions (Q2-Q3 Chunk 4).

Replaces the implicit "one reasoning depth for all steps" behavior with a
policy-driven depth decision per step.  The policy is deterministic (no LLM
call), takes risk/uncertainty/budget/prior-failures as inputs, and returns
one of three depth levels: shallow, normal, or deep.

When the action is high-risk, when depth is exhausted, or when uncertainty
is high, the policy escalates to HITL instead of silently degrading.

Every depth decision is audit-logged to the substrate event log for replay.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.models.depth_models import DepthDecision, DepthLevel, DepthTriggeredEvent

logger = logging.getLogger(__name__)

# Reflection iteration counts per depth level
REFLECTION_ITERATIONS: dict[DepthLevel, int] = {
    DepthLevel.SHALLOW: 0,  # direct act, no reflection
    DepthLevel.NORMAL: 1,  # plan/act with one reflection pass
    DepthLevel.DEEP: 3,  # plan/act with full reflection loop
}


@dataclass
class _CandidateDecision:
    """Internal candidate from a single signal."""

    level: DepthLevel
    reason: str
    priority: int  # higher = more important


class DepthPolicy:
    """Deterministic, priority-based depth policy.

    The policy evaluates multiple signals (risk, uncertainty, budget,
    prior failures, tool approval, retry count) and combines them using
    a deterministic priority order.  The highest-priority signal wins
    for the level selection.  HITL escalation is evaluated separately
    as a hard rule.

    Args:
        policy_version: Version string stored in every decision.
        shallow_budget_threshold_usd: Budget below which we force shallow.
        deep_uncertainty_threshold: Uncertainty above which we force deep.
        deep_prior_failure_threshold: Prior failures at which we force deep.
        hitl_retry_threshold: Retry count at which we escalate to HITL.
    """

    def __init__(
        self,
        *,
        policy_version: str = "v1.0.0",
        shallow_budget_threshold_usd: Decimal = Decimal("0.10"),
        deep_uncertainty_threshold: float = 0.7,
        deep_prior_failure_threshold: int = 2,
        hitl_retry_threshold: int = 3,
    ) -> None:
        self.policy_version = policy_version
        self.shallow_budget_threshold_usd = shallow_budget_threshold_usd
        self.deep_uncertainty_threshold = deep_uncertainty_threshold
        self.deep_prior_failure_threshold = deep_prior_failure_threshold
        self.hitl_retry_threshold = hitl_retry_threshold

    def decide(
        self,
        *,
        risk: Literal["low", "medium", "high"],
        uncertainty: float,
        budget_remaining_usd: Decimal,
        prior_failures: int,
        tool_requires_approval: bool,
        retry_count: int,
        policy_override: bool = False,
    ) -> DepthDecision:
        """Make a deterministic depth decision for a single step.

        Priority order for level selection (highest first):
        1. High risk → deep
        2. High uncertainty (>threshold) → deep
        3. Many prior failures (>=threshold) → deep
        4. Low budget (<threshold) → shallow (budget preservation)
        5. Low risk + low uncertainty + no failures → shallow
        6. Default → normal

        HITL escalation is evaluated separately:
        - tool_requires_approval AND NOT policy_override → HITL
        - retry_count >= hitl_retry_threshold → HITL
        - prior_failures >= hitl_retry_threshold → HITL

        Args:
            risk: Risk level of the action.
            uncertainty: Uncertainty signal (0.0-1.0).
            budget_remaining_usd: Remaining budget in USD.
            prior_failures: Number of prior failures for this task type.
            tool_requires_approval: Whether the tool requires human approval.
            retry_count: Number of retries attempted so far.
            policy_override: If True, bypasses the automatic HITL escalation
                for tool_requires_approval (explicit override by calling code).

        Returns:
            DepthDecision with level, reason, escalation flags, and metadata.
        """
        reasons: list[str] = []

        # ── Step 1: Evaluate HITL escalation (hard rules) ─────────────
        escalate_to_hitl, hitl_reason = self._should_escalate_to_hitl(
            tool_requires_approval=tool_requires_approval,
            retry_count=retry_count,
            prior_failures=prior_failures,
            policy_override=policy_override,
        )

        # ── Step 2: Gather candidate decisions from each signal ───────
        candidates: list[_CandidateDecision] = []

        # Signal 1: Risk
        risk_candidate = self._risk_to_depth(risk)
        candidates.append(risk_candidate)
        reasons.append(risk_candidate.reason)

        # Signal 2: Uncertainty
        unc_candidate = self._uncertainty_to_depth(uncertainty)
        candidates.append(unc_candidate)
        reasons.append(unc_candidate.reason)

        # Signal 3: Prior failures
        fail_candidate = self._prior_failures_to_depth(prior_failures)
        candidates.append(fail_candidate)
        reasons.append(fail_candidate.reason)

        # Signal 4: Budget
        budget_candidate = self._budget_to_depth(budget_remaining_usd)
        candidates.append(budget_candidate)
        reasons.append(budget_candidate.reason)

        # ── Step 3: Combine candidates (highest priority wins) ────────
        level = self._combine_decisions(candidates)

        # ── Step 4: HITL escalation overrides level to deep ──────────
        if escalate_to_hitl:
            level = DepthLevel.DEEP
            reasons.append(f"HITL escalation: {hitl_reason}")

        # Build human-readable reason
        reason = "; ".join(reasons)

        # Map level to reflection iterations
        iterations = REFLECTION_ITERATIONS[level]

        return DepthDecision(
            level=level,
            reason=reason,
            escalate_to_hitl=escalate_to_hitl,
            hitl_reason=hitl_reason,
            policy_version=self.policy_version,
            estimated_reflection_iterations=iterations,
        )

    def build_audit_event(
        self,
        decision: DepthDecision,
        *,
        risk: str,
        uncertainty: float,
        budget_remaining_usd: Decimal,
        prior_failures: int,
        retry_count: int,
        step_id: str | None = None,
        mission_id: str | None = None,
        workspace_id: str | None = None,
        user_id: int | None = None,
    ) -> DepthTriggeredEvent:
        """Build an audit event payload from a depth decision.

        Returns a DepthTriggeredEvent with field-level data only.
        No raw task text or tool input is included.
        """
        return DepthTriggeredEvent(
            level=decision.level.value,
            reason=decision.reason,
            risk=risk,
            uncertainty=uncertainty,
            budget_remaining_usd=float(budget_remaining_usd),
            prior_failures=prior_failures,
            retry_count=retry_count,
            escalate_to_hitl=decision.escalate_to_hitl,
            hitl_reason=decision.hitl_reason,
            policy_version=decision.policy_version,
            step_id=step_id,
            mission_id=mission_id,
            workspace_id=workspace_id,
            user_id=user_id,
            estimated_reflection_iterations=decision.estimated_reflection_iterations,
        )

    # ── Private helpers (one per signal) ─────────────────────────────

    def _risk_to_depth(self, risk: Literal["low", "medium", "high"]) -> _CandidateDecision:
        """Map risk level to a candidate depth."""
        if risk == "high":
            return _CandidateDecision(
                level=DepthLevel.DEEP,
                reason="risk=high → deep",
                priority=100,
            )
        elif risk == "medium":
            return _CandidateDecision(
                level=DepthLevel.NORMAL,
                reason="risk=medium → normal",
                priority=40,
            )
        else:
            return _CandidateDecision(
                level=DepthLevel.SHALLOW,
                reason="risk=low",
                priority=10,
            )

    def _uncertainty_to_depth(self, uncertainty: float) -> _CandidateDecision:
        """Map uncertainty to a candidate depth."""
        if uncertainty > self.deep_uncertainty_threshold:
            return _CandidateDecision(
                level=DepthLevel.DEEP,
                reason=f"uncertainty={uncertainty:.2f} > {self.deep_uncertainty_threshold} → deep",
                priority=90,
            )
        elif uncertainty >= 0.3:
            return _CandidateDecision(
                level=DepthLevel.NORMAL,
                reason=f"uncertainty={uncertainty:.2f} ≥ 0.3 → normal",
                priority=30,
            )
        else:
            return _CandidateDecision(
                level=DepthLevel.SHALLOW,
                reason=f"uncertainty={uncertainty:.2f} < 0.3",
                priority=10,
            )

    def _budget_to_depth(self, budget_remaining_usd: Decimal) -> _CandidateDecision:
        """Map remaining budget to a candidate depth."""
        if budget_remaining_usd < self.shallow_budget_threshold_usd:
            return _CandidateDecision(
                level=DepthLevel.SHALLOW,
                reason=f"budget=${budget_remaining_usd} < ${self.shallow_budget_threshold_usd} → shallow (budget preservation)",
                priority=80,
            )
        else:
            return _CandidateDecision(
                level=DepthLevel.NORMAL,
                reason=f"budget=${budget_remaining_usd:.2f} (adequate)",
                priority=5,
            )

    def _prior_failures_to_depth(self, prior_failures: int) -> _CandidateDecision:
        """Map prior failures to a candidate depth."""
        if prior_failures >= self.deep_prior_failure_threshold:
            return _CandidateDecision(
                level=DepthLevel.DEEP,
                reason=f"prior_failures={prior_failures} ≥ {self.deep_prior_failure_threshold} → deep",
                priority=70,
            )
        elif prior_failures > 0:
            return _CandidateDecision(
                level=DepthLevel.NORMAL,
                reason=f"prior_failures={prior_failures} → normal",
                priority=20,
            )
        else:
            return _CandidateDecision(
                level=DepthLevel.SHALLOW,
                reason="prior_failures=0",
                priority=10,
            )

    def _should_escalate_to_hitl(
        self,
        *,
        tool_requires_approval: bool,
        retry_count: int,
        prior_failures: int,
        policy_override: bool,
    ) -> tuple[bool, str | None]:
        """Determine if this step should escalate to HITL.

        Priority order:
        1. tool_requires_approval AND NOT policy_override → HITL
        2. retry_count >= hitl_retry_threshold → HITL (retry_exhausted)
        3. prior_failures >= hitl_retry_threshold → HITL (persistent_failure)

        Returns:
            (escalate, hitl_reason) tuple.
        """
        if tool_requires_approval and not policy_override:
            return True, "tool_requires_approval"

        if retry_count >= self.hitl_retry_threshold:
            return True, "retry_exhausted"

        if prior_failures >= self.hitl_retry_threshold:
            return True, "persistent_failure"

        # policy_override with tool_requires_approval: log the override
        if tool_requires_approval and policy_override:
            logger.warning(
                "HITL escalation bypassed by policy_override for approval-requiring tool"
            )

        return False, None

    def _combine_decisions(self, candidates: list[_CandidateDecision]) -> DepthLevel:
        """Combine candidate decisions using deterministic priority order.

        The candidate with the highest priority wins.
        If there's a tie, deeper depth wins (conservative default).
        """
        if not candidates:
            return DepthLevel.NORMAL

        # Sort by priority descending, then by depth (deep > normal > shallow)
        depth_order = {DepthLevel.DEEP: 3, DepthLevel.NORMAL: 2, DepthLevel.SHALLOW: 1}
        best = max(candidates, key=lambda c: (c.priority, depth_order[c.level]))
        return best.level
