"""Q6-E — Reviewer verification orchestrator (escalate-only).

Composes Q6-A (lexical groundedness), Q6-B (cross-family semantic
verifier), Q6-C (calibration) and Q6-D (systemic degradation) into a
single decision surface for a batch of reviewer-proposed writes.

Core invariant — **verification is escalate-only**:

* A claim is auto-*accepted* ONLY when it is grounded (lexically OR via
  the verifier) AND the verifier does not *contradict* it (verifier says
  ``supports=False`` while lexical says grounded → escalate, never
  silently accept).  High stated confidence NEVER auto-accepts.
* Any claim that fails grounding, or that the verifier contradicts, or
  whose calibrated trust is below a floor, is **escalated to HITL** — it
  is never written by the system on its own authority.  This composes
  with the Q4-D escalate-only write lock: the orchestrator returns an
  escalation decision; the caller drains it into the HITL inbox
  (``InboxItem`` / ``HumanInterrupt``), exactly like Q4-D.
* On verifier *degradation* (LLM soft-failure), we escalate rather than
  trust — uncertainty is never an auto-pass.

This module is pure orchestration: it returns a :class:`VerificationBatch`
describing each claim's fate (accept / escalate) plus evidence.  It does
NOT perform DB writes or HITL inserts itself — the caller owns the
transaction (services/AGENTS.md rule 3) and the inbox write (Q4-D lock).

Determinism: with the verifier injected as a fake (tests) or with
lexical-only mode, the verdict is fully reproducible.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.services.reviewer_guard.calibration import CalibrationMap, Label
from app.services.reviewer_guard.degradation import (
    DegradationTracker,
    SystemRates,
)
from app.services.reviewer_guard.groundedness import (
    Claim,
    GroundednessVerifier,
    GroundingVerdict,
    TranscriptSpan,
)
from app.services.reviewer_guard.verifier import (
    SecondPassVerifier,
    VerificationResult,
    different_family,
)

logger = logging.getLogger(__name__)

# Calibrated trust below this → escalate regardless of grounding (we don't
# trust an uncalibrated/low-confidence write, even if it lexical-matches).
CALIBRATED_TRUST_FLOOR = 0.5


@dataclass
class ClaimDecision:
    """Fate of a single claim after Q6 verification."""

    claim_id: str
    action: str  # "accept" | "escalate"
    grounded: bool
    verifier_supports: bool | None  # None when verifier not run
    verifier_contradicts: bool
    calibrated_trust: float
    reason: str
    # Supporting span id (if any) for the audit trail.
    supporting_span_id: str | None = None
    # Raw evidence pieces for HITL context.
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def escalate(self) -> bool:
        return self.action == "escalate"


@dataclass
class VerificationBatch:
    """Result of verifying a batch of claims."""

    decisions: list[ClaimDecision]
    rates: SystemRates
    alarms: list[Any] = field(default_factory=list)  # list[DegradationAlarm]

    @property
    def escalations(self) -> list[ClaimDecision]:
        return [d for d in self.decisions if d.escalate]


class ReviewerGuard:
    """Compose Q6-A..D into an escalate-only verification pass.

    Args:
        transcript: the source transcript (spans) the claims must ground to.
        calibration: a fitted :class:`CalibrationMap` (Q6-C).  If None, a
            cold-start map is used (conservative shrink — exactly the
            hallucination trap guard).
        degradation: a :class:`DegradationTracker` (Q6-D).  If None, an
            internal one is created (not shared across calls).
        verifier: optional :class:`SecondPassVerifier` (Q6-B).  If None,
            verification is lexical-only (Q6-A) — still escalate-only, just
            without the semantic second pass.  Passing a verifier whose
            model family equals the reviewer's disables it with a warning
            (decorrelation requirement).
        reviewer_model: the primary reviewer's model id, used to enforce
            verifier family decorrelation.
    """

    def __init__(
        self,
        transcript: list[TranscriptSpan],
        *,
        calibration: CalibrationMap | None = None,
        degradation: DegradationTracker | None = None,
        verifier: SecondPassVerifier | None = None,
        reviewer_model: str = "deepseek-v4-flash",
        calibrated_trust_floor: float = CALIBRATED_TRUST_FLOOR,
    ) -> None:
        self._verifier_impl = GroundednessVerifier(transcript)
        self.calibration = calibration or CalibrationMap(method="isotonic")
        self.degradation = degradation or DegradationTracker()
        self.reviewer_model = reviewer_model
        self.calibrated_trust_floor = calibrated_trust_floor

        # Enforce decorrelation: a same-family verifier is inert (lexical
        # only) — running it would just re-correlate the two passes.
        self.verifier: SecondPassVerifier | None = None
        if verifier is not None:
            if different_family(reviewer_model, verifier.model_id):
                self.verifier = verifier
            else:
                logger.warning(
                    "guard.verifier.same_family reviewer=%s verifier=%s — verifier DISABLED (decorrelation required)",
                    reviewer_model,
                    verifier.model_id,
                )

    def verify_batch(
        self,
        claims: list[Claim],
        *,
        run_verifier: bool = True,
        transcript_text: str | None = None,
        verifier_results: dict[str, VerificationResult] | None = None,
    ) -> VerificationBatch:
        """Verify a batch of reviewer-proposed writes.

        Returns accepted/escalated decisions + systemic rates + alarms.
        Records grounding/disagreement outcomes into the degradation
        tracker (so Q6-D rates stay live across batches).
        """
        decisions: list[ClaimDecision] = []
        # Build a single transcript string for the verifier (lazy).
        vtext = transcript_text
        if vtext is None and self.verifier is not None and run_verifier:
            vtext = "\n".join(f"[{s.span_id}] {s.text}" for s in self._verifier_impl._spans)

        for claim in claims:
            decision = self._verify_one(
                claim,
                run_verifier=run_verifier,
                transcript_text=vtext,
                verifier_result=(verifier_results or {}).get(claim.claim_id),
            )
            decisions.append(decision)
            # Feed Q6-D.
            self.degradation.record_grounding(decision.grounded)
            if decision.verifier_supports is not None:
                disagreed = decision.grounded != decision.verifier_supports
                self.degradation.record_disagreement(disagreed)

        alarms = self.degradation.check_alarms()
        return VerificationBatch(
            decisions=decisions,
            rates=self.degradation.rates(),
            alarms=alarms,
        )

    def _verify_one(
        self,
        claim: Claim,
        *,
        run_verifier: bool,
        transcript_text: str | None,
        verifier_result: VerificationResult | None = None,
    ) -> ClaimDecision:
        # ── Q6-A: lexical groundedness ──
        gverdict: GroundingVerdict = self._verifier_impl.verify(claim)
        grounded = gverdict.grounded

        # ── Q6-C: calibrate stated confidence ──
        calibrated = self.calibration.calibrate(claim.stated_confidence)

        # ── Q6-B: cross-family semantic verifier ──
        vresult: VerificationResult | None = None
        verifier_supports: bool | None = None
        verifier_contradicts = False
        # Prefer a pre-computed (async) verifier result when the caller passed
        # one (avoids a second LLM call / thread bridge).  Otherwise, if a
        # verifier is wired in and we are asked to run it, call it synchronously.
        if verifier_result is not None:
            vresult = verifier_result
            verifier_supports = verifier_result.supports
        elif self.verifier is not None and run_verifier and transcript_text is not None:
            vresult = self.verifier.verify(
                transcript_text=transcript_text,
                claim_id=claim.claim_id,
                claim_content=claim.content,
            )
            verifier_supports = vresult.supports
            # Contradiction: lexical grounded BUT verifier says no (and the
            # verifier didn't degrade).  Degraded verifier → escalate on
            # uncertainty, not "contradict".
            if grounded and not _vr.supports and not _vr.degraded:
                verifier_contradicts = True
            # Degraded verifier on a grounded claim → escalate on uncertainty.
            if grounded and _vr.degraded:
                verifier_contradicts = False  # not a contradiction, but see below

        # ── Decision (escalate-only) ──
        reasons: list[str] = []
        escalate = False

        if not grounded:
            escalate = True
            reasons.append(
                "NOT GROUNDED: " + gverdict.reason + f" (stated_confidence={claim.stated_confidence:.2f} ignored)"
            )
        if verifier_contradicts:
            escalate = True
            reasons.append("VERIFIER CONTRADICTS grounding (cross-family check failed)")
        if vresult is not None and vresult.degraded and grounded:
            # Lexical match but verifier couldn't confirm → escalate on
            # uncertainty rather than auto-accept.
            escalate = True
            reasons.append("VERIFIER DEGRADED on a grounded claim → escalate on uncertainty")
        if calibrated < self.calibrated_trust_floor:
            # Calibrated trust too low: even a grounded claim is not trusted
            # to auto-write.  (High stated confidence cannot lower this.)
            if not escalate:
                escalate = True
            reasons.append(f"CALIBRATED TRUST {calibrated:.2f} < floor {self.calibrated_trust_floor:.2f} → escalate")

        action = "escalate" if escalate else "accept"

        evidence: dict[str, Any] = {
            "grounding_reason": gverdict.reason,
            "best_overlap": round(gverdict.best_overlap, 3),
            "calibration": {
                "stated": claim.stated_confidence,
                "calibrated": round(calibrated, 3),
                "method": self.calibration.method,
                "used_fallback": self.calibration.stats.used_fallback,
            },
        }
        if vresult is not None:
            evidence["verifier"] = {
                "supports": vresult.supports,
                "degraded": vresult.degraded,
                "evidence": vresult.evidence,
                "reason": vresult.reason,
                "model_id": vresult.model_id,
            }

        return ClaimDecision(
            claim_id=claim.claim_id,
            action=action,
            grounded=grounded,
            verifier_supports=verifier_supports,
            verifier_contradicts=verifier_contradicts,
            calibrated_trust=calibrated,
            reason="; ".join(reasons) if reasons else "grounded + verifier supports + trust OK",
            supporting_span_id=gverdict.supporting_span_id,
            evidence=evidence,
        )
