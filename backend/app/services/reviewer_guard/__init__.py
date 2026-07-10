"""Q6 — Reviewer hallucination prevention (groundedness + verifier).

Public surface for the Q6 reviewer-guard package.  Composes four
independent mechanisms into one escalate-only verification pass:

* Q6-A ``groundedness``   — lexical groundedness (span retrieve + entail).
* Q6-B ``verifier``       — cross-family second-pass semantic verifier.
* Q6-C ``calibration``    — isotonic/Platt confidence calibration.
* Q6-D ``degradation``    — systemic degradation tracking + canary set.
* Q6-E ``orchestrator``   — escalate-only composition of A..D.

None of these modules perform DB writes or LLM calls directly (the
verifier routes through BudgetEnforcer in production, or takes an injected
fake in tests).  The orchestrator returns accept/escalate decisions; the
caller drains escalations into the HITL inbox (composes with Q4-D lock).
"""

from __future__ import annotations

from app.services.reviewer_guard.calibration import (
    CalibrationMap,
    CalibrationMethod,
    CalibrationStats,
    Label,
)
from app.services.reviewer_guard.degradation import (
    CanaryClaim,
    CanaryTranscript,
    DegradationAlarm,
    DegradationTracker,
    SystemRates,
)
from app.services.reviewer_guard.groundedness import (
    Claim,
    GroundednessVerifier,
    GroundingVerdict,
    SpanEvidence,
    TranscriptSpan,
)
from app.services.reviewer_guard.orchestrator import (
    ClaimDecision,
    ReviewerGuard,
    VerificationBatch,
)
from app.services.reviewer_guard.verifier import (
    SecondPassVerifier,
    VerificationResult,
    different_family,
)

__all__ = [
    # Q6-C
    "CalibrationMap",
    "CalibrationMethod",
    "CalibrationStats",
    # Q6-D
    "CanaryClaim",
    "CanaryTranscript",
    # Q6-A
    "Claim",
    # Q6-E
    "ClaimDecision",
    "DegradationAlarm",
    "DegradationTracker",
    "GroundednessVerifier",
    "GroundingVerdict",
    "Label",
    "ReviewerGuard",
    # Q6-B
    "SecondPassVerifier",
    "SpanEvidence",
    "SystemRates",
    "TranscriptSpan",
    "VerificationBatch",
    "VerificationResult",
    "different_family",
]
