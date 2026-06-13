"""RecoveryPolicy — maps error classes to recovery actions for self-correction.

Each ErrorClass gets a primary RecoveryAction with conditions.  The policy is
deterministic (no LLM call) and is consulted by SelfCorrectionLoop on every
failure to decide what to do next.

Recovery actions:
  RETRY             — re-execute the same task (useful for transient errors)
  REFLECT           — re-execute with modified parameters/context (useful for logic errors)
  ASK_HITL          — pause the mission and escalate to a human
  FALLBACK_PROVIDER — switch to an alternative LLM provider and retry
  ABORT             — mark the task (or mission) as permanently failed
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from app.services.nexus.failure_analyzer import ErrorClass, FailureAnalysisResult

logger = logging.getLogger(__name__)


# ── Recovery actions ───────────────────────────────────────────────


class RecoveryAction(str, Enum):
    """Possible recovery actions when a task fails."""

    RETRY = "retry"
    REFLECT = "reflect"
    ASK_HITL = "ask_hitl"
    FALLBACK_PROVIDER = "fallback_provider"
    ABORT = "abort"


# ── Policy mapping ─────────────────────────────────────────────────

# Primary action per ErrorClass.  Conditions (budget, attempt count) are
# checked by SelfCorrectionLoop *after* the policy returns an action.
# This keeps the policy itself stateless and testable.

_DEFAULT_POLICY: dict[ErrorClass, RecoveryAction] = {
    # Transient errors → retry (budget enforcer limits attempts)
    ErrorClass.TIMEOUT: RecoveryAction.RETRY,
    ErrorClass.NETWORK: RecoveryAction.RETRY,
    ErrorClass.RATE_LIMIT: RecoveryAction.FALLBACK_PROVIDER,
    ErrorClass.RESOURCE: RecoveryAction.RETRY,

    # Structural errors → reflect and modify approach
    ErrorClass.VALIDATION: RecoveryAction.REFLECT,
    ErrorClass.LOGIC: RecoveryAction.REFLECT,
    ErrorClass.NOT_FOUND: RecoveryAction.REFLECT,

    # Hard errors → escalate or abort
    ErrorClass.PERMISSION: RecoveryAction.ASK_HITL,
    ErrorClass.UNKNOWN: RecoveryAction.RETRY,
}


class RecoveryPolicy:
    """Deterministic mapping from error analysis to recovery action.

    Usage::

        policy = RecoveryPolicy()
        action = policy.decide(analysis_result)
    """

    def __init__(
        self,
        overrides: dict[ErrorClass, RecoveryAction] | None = None,
    ) -> None:
        self._policy = {**_DEFAULT_POLICY, **(overrides or {})}

    def decide(self, analysis: FailureAnalysisResult) -> RecoveryAction:
        """Return the recovery action for a given failure analysis.

        If the analysis says the error is non-recoverable (budget exhausted),
        the action is always ABORT regardless of the policy mapping.
        """
        if not analysis.is_recoverable:
            return RecoveryAction.ABORT

        action = self._policy.get(analysis.error_class, RecoveryAction.ABORT)

        # If the analysis says retry is not recommended, downgrade to REFLECT
        if action == RecoveryAction.RETRY and not analysis.retry_recommended:
            return RecoveryAction.REFLECT

        return action

    def get_policy(self) -> dict[str, str]:
        """Return the current policy as a dict for audit/logging."""
        return {ec.value: action.value for ec, action in self._policy.items()}
