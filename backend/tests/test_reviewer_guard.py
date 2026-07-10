"""TDD tests for Q6 reviewer-guard (groundedness + calibration + orchestrator).

Covers the hallucination-prevention mechanisms from §8 of the Q1–Q6
decomposition:

* Q6-A — lexical groundedness: an ungrounded claim (even at stated
  confidence 0.9) is REJECTED, never accepted on confidence.
* Q6-C — calibration map: cold-start shrinks a 0.9 toward uncertainty;
  a fitted isotonic/Platt map is monotonic and serialisable.
* Q6-E — orchestrator: escalate-only composition; grounded + verifier
  supports → accept; anything else → escalate.

Pure + deterministic: no DB, no network.  The verifier is injected as a
fake so Q6-B is exercised without an LLM.

Run via::
    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner" \
      .venv/bin/python -m pytest tests/test_reviewer_guard.py -v
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner",
)

from app.services.reviewer_guard.calibration import CalibrationMap, Label
from app.services.reviewer_guard.groundedness import (
    Claim,
    GroundednessVerifier,
    TranscriptSpan,
)
from app.services.reviewer_guard.orchestrator import ReviewerGuard
from app.services.reviewer_guard.verifier import SecondPassVerifier

# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


def _sample_transcript() -> list[TranscriptSpan]:
    return [
        TranscriptSpan("s1", "The user said the API token is secret123 and expires in July."),
        TranscriptSpan("s2", "We should deploy the service at 3pm after the database migration."),
        TranscriptSpan("s3", "The rollback plan must include a snapshot of the postgres volume."),
    ]


def _fake_verifier(supports: bool, *, degraded: bool = False) -> SecondPassVerifier:
    """A Q6-B verifier backed by a fake LLM caller."""

    def _call(messages: list[dict[str, str]]) -> str:
        if degraded:
            return ""
        return '{"supports": ' + str(supports).lower() + ', "evidence": "quote", "reason": "fake"}'

    return SecondPassVerifier(model_id="anthropic/claude-3-5-haiku", call_llm=_call)


# ═══════════════════════════════════════════════════════════════════════════
# Q6-A — groundedness reject (the core trap)
# ═══════════════════════════════════════════════════════════════════════════


class TestGroundednessReject:
    """Ungrounded claims are rejected REGARDLESS of stated confidence."""

    def test_ungrounded_claim_rejected_at_confidence_0_9(self) -> None:
        gv = GroundednessVerifier(_sample_transcript())
        # A confident hallucination: claims a password the transcript never had.
        claim = Claim(
            claim_id="mem.pw",
            content="The user said the database password is hunter2",
            stated_confidence=0.9,
        )
        v = gv.verify(claim)
        assert v.grounded is False
        assert v.rejected is True
        assert v.supporting_span_id is None

    def test_empty_transcript_rejects_everything(self) -> None:
        gv = GroundednessVerifier([])
        claim = Claim("c", "anything at all", stated_confidence=1.0)
        v = gv.verify(claim)
        assert v.grounded is False
        assert v.rejected is True

    def test_grounded_claim_accepted_and_spans(self) -> None:
        gv = GroundednessVerifier(_sample_transcript())
        claim = Claim(
            claim_id="mem.token",
            content="The API token is secret123 and expires in July",
            stated_confidence=0.9,
        )
        v = gv.verify(claim)
        assert v.grounded is True
        assert v.supporting_span_id == "s1"
        assert v.best_overlap >= 0.5

    def test_alleged_span_still_verified_not_trusted(self) -> None:
        gv = GroundednessVerifier(_sample_transcript())
        # Reviewer *claims* s2 supports it, but the content is about a pw.
        claim = Claim(
            claim_id="mem.pw2",
            content="The database password is letmein",
            stated_confidence=0.95,
            alleged_span_id="s2",
        )
        v = gv.verify(claim)
        # Even with an explicit alleged span, no support -> rejected.
        assert v.grounded is False
        assert v.rejected is True

    def test_partial_overlap_boilerplate_does_not_ground(self) -> None:
        gv = GroundednessVerifier(_sample_transcript())
        # "user said" overlaps but the substantive claim does not.
        claim = Claim(
            claim_id="mem.x",
            content="The user said the payment webhook secret is abc999",
            stated_confidence=0.85,
        )
        v = gv.verify(claim)
        assert v.grounded is False


# ═══════════════════════════════════════════════════════════════════════════
# Q6-C — calibration map
# ═══════════════════════════════════════════════════════════════════════════


class TestCalibrationMap:
    """Stated confidence is never stored raw; it is calibrated."""

    def test_cold_start_shrinks_0_9(self) -> None:
        # No labels -> conservative fallback. A 0.9 must NOT stay 0.9.
        cm = CalibrationMap.fit([])
        assert cm.stats.used_fallback is True
        cal = cm.calibrate(0.9)
        assert cal < 0.9
        assert cal >= 0.5
        assert cal <= 1.0

    def test_calibrate_always_in_01(self) -> None:
        cm = CalibrationMap.fit([])
        for s in (-1.0, 0.0, 0.3, 0.7, 1.5, float("nan")):
            assert 0.0 <= cm.calibrate(s) <= 1.0

    def test_isotonic_fitted_is_monotonic(self) -> None:
        # Well-calibrated labels: stated == empirical.
        labels = [
            Label(0.1, False),
            Label(0.2, False),
            Label(0.3, True),
            Label(0.4, True),
            Label(0.5, True),
            Label(0.6, True),
            Label(0.7, True),
            Label(0.8, True),
            Label(0.9, True),
            Label(1.0, True),
        ]
        # Pad to >= MIN_FIT_SAMPLES with repeated patterns.
        labels = labels * 3
        cm = CalibrationMap.fit(labels, method="isotonic")
        assert cm.stats.used_fallback is False
        prev = -1.0
        for s in (0.1, 0.3, 0.5, 0.7, 0.9, 1.0):
            val = cm.calibrate(s)
            assert val >= prev - 1e-9, f"map not monotonic at {s}"
            prev = val

    def test_overconfident_labels_shrink_high_end(self) -> None:
        # Model is over-confident: high stated values are usually WRONG,
        # low stated values usually RIGHT.  Build a graded label set so the
        # isotonic map has a clear decreasing trend.
        labels: list[Label] = []
        for stated, correctness_rate in ((0.1, 0.9), (0.3, 0.8), (0.5, 0.6), (0.7, 0.4), (0.9, 0.1)):
            n = 20
            n_right = round(correctness_rate * n)
            labels += [Label(stated, True) for _ in range(n_right)]
            labels += [Label(stated, False) for _ in range(n - n_right)]
        cm = CalibrationMap.fit(labels, method="isotonic")
        # High-end calibrated trust must be well below the low-end.
        assert cm.calibrate(0.9) < cm.calibrate(0.2) - 0.2
        assert cm.calibrate(0.9) < 0.5

    def test_roundtrip_serialisation(self) -> None:
        labels = [Label(0.1 * (i % 10), (i % 3) == 0) for i in range(30)]
        cm = CalibrationMap.fit(labels, method="isotonic")
        data = cm.to_dict()
        rebuilt = CalibrationMap.from_dict(data)
        for s in (0.1, 0.4, 0.7, 0.95):
            assert abs(rebuilt.calibrate(s) - cm.calibrate(s)) < 1e-6

    def test_platt_fitted_serialises(self) -> None:
        labels = [Label(0.1 * (i % 10), (i % 2) == 0) for i in range(30)]
        cm = CalibrationMap.fit(labels, method="platt")
        rebuilt = CalibrationMap.from_dict(cm.to_dict())
        # Platt coefs persisted; calibration reproduces.
        assert abs(rebuilt.calibrate(0.5) - cm.calibrate(0.5)) < 1e-6


# ═══════════════════════════════════════════════════════════════════════════
# Q6-E — orchestrator (escalate-only)
# ═══════════════════════════════════════════════════════════════════════════


class TestReviewerGuardOrchestrator:
    def test_grounded_and_verifier_supports_accepts(self) -> None:
        guard = ReviewerGuard(
            _sample_transcript(),
            calibration=CalibrationMap.fit([]),  # cold start shrinks but >=0.5 floor
            verifier=_fake_verifier(supports=True),
            reviewer_model="deepseek-v4-flash",
        )
        claims = [
            Claim("mem.ok", "The API token is secret123", stated_confidence=0.9),
        ]
        batch = guard.verify_batch(claims)
        assert batch.decisions[0].action == "accept"
        assert not batch.decisions[0].escalate

    def test_ungrounded_escalates_regardless_of_confidence(self) -> None:
        guard = ReviewerGuard(
            _sample_transcript(),
            calibration=CalibrationMap.fit([]),
            verifier=_fake_verifier(supports=True),  # verifier would accept, but
            reviewer_model="deepseek-v4-flash",
        )
        claims = [
            # A 0.99-confidence hallucination.
            Claim("mem.bad", "The admin password is p@ssw0rd", stated_confidence=0.99),
        ]
        batch = guard.verify_batch(claims)
        d = batch.decisions[0]
        assert d.action == "escalate"
        assert d.grounded is False
        # Confidence must NOT be the reason it passed.
        assert "stated_confidence" in d.reason

    def test_verifier_contradiction_escalates(self) -> None:
        # Lexically grounded, but cross-family verifier says NO.
        guard = ReviewerGuard(
            _sample_transcript(),
            calibration=CalibrationMap.fit([]),
            verifier=_fake_verifier(supports=False),
            reviewer_model="deepseek-v4-flash",
        )
        claims = [
            Claim("mem.tok", "The API token is secret123", stated_confidence=0.9),
        ]
        batch = guard.verify_batch(claims)
        d = batch.decisions[0]
        assert d.escalate is True
        assert d.verifier_contradicts is True

    def test_same_family_verifier_disabled(self) -> None:
        # Reviewer deepseek + verifier deepseek -> verifier inert (lexical only).
        same_family_verifier = SecondPassVerifier(
            model_id="deepseek/deepseek-v4-flash", call_llm=lambda m: '{"supports": false}'
        )
        guard = ReviewerGuard(
            _sample_transcript(),
            calibration=CalibrationMap.fit([]),
            verifier=same_family_verifier,
            reviewer_model="deepseek-v4-flash",
        )
        # The injected verifier is same-family, so guard.verifier is None.
        assert guard.verifier is None

    def test_verifier_degraded_escalates_on_uncertainty(self) -> None:
        guard = ReviewerGuard(
            _sample_transcript(),
            calibration=CalibrationMap.fit([]),
            verifier=_fake_verifier(supports=False, degraded=True),
            reviewer_model="deepseek-v4-flash",
        )
        claims = [Claim("mem.tok", "The API token is secret123", stated_confidence=0.9)]
        d = guard.verify_batch(claims).decisions[0]
        assert d.escalate is True

    def test_lexical_only_mode_still_escalate_only(self) -> None:
        # No verifier at all -> grounded claims still need calibrated trust;
        # an ungrounded claim escalates.
        guard = ReviewerGuard(_sample_transcript(), calibration=CalibrationMap.fit([]))
        claims = [
            Claim("mem.bad", "The database password is letmein", stated_confidence=1.0),
            Claim("mem.ok", "The API token is secret123", stated_confidence=0.9),
        ]
        batch = guard.verify_batch(claims, run_verifier=False)
        assert batch.decisions[0].escalate is True
        # The lexically-grounded claim is accepted (cold-start calib >= floor).
        assert batch.decisions[1].action == "accept"

    def test_calibration_floor_escalates_low_trust(self) -> None:
        # Build a calibration map where even grounded claims map low.
        labels = [Label(0.9, False) for _ in range(20)] + [Label(0.1, True) for _ in range(20)]
        cm = CalibrationMap.fit(labels, method="isotonic")
        guard = ReviewerGuard(
            _sample_transcript(),
            calibration=cm,
            verifier=_fake_verifier(supports=True),
            reviewer_model="deepseek-v4-flash",
            calibrated_trust_floor=0.6,
        )
        claims = [Claim("mem.tok", "The API token is secret123", stated_confidence=0.9)]
        d = guard.verify_batch(claims).decisions[0]
        # Even though grounded + verifier supports, calibrated trust < floor -> escalate.
        assert d.escalate is True
        assert "CALIBRATED TRUST" in d.reason
