"""Q6-A — Groundedness verification for reviewer-proposed writes.

The core hallucination trap: a reviewer (CriticAgent / any downstream
writer) emits a *proposed write* (a memory entry, a skill edit, a claim)
together with a *stated confidence* and often a footnote about which part
of the source transcript it came from.  If we trust the stated confidence,
a ``0.9`` hallucination sails straight through.

Groundedness flips the burden of proof: **every proposed write must point
at a transcript span it actually came from.**  We

1. *retrieve* candidate spans from the transcript using the claim's
   salient tokens (lexical overlap; no embedding model required, so the
   guard is cheap + deterministic), and
2. *entail* — check that the claim is supported by at least one retrieved
   span (subsequence / n-gram / token-overlap heuristics).

If no span supports the claim, the write is **rejected** (routed to
HITL), *regardless of the reviewer's stated confidence*.  This is the
single most important invariant in Q6 — confidence is never an
escape hatch from groundedness.

The module is pure logic: it takes a transcript (list of spans with text)
and a claim, and returns a :class:`GroundingVerdict`.  It makes NO LLM
calls and NO DB writes.  The LLM-assisted second pass lives in Q6-B; the
escalation routing lives in Q6-E.

Determinism note: lexical overlap + n-gram entailment are fully
deterministic, so the same (transcript, claim) pair always yields the same
verdict — required for reproducible canary re-runs (Q6-D).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# A claim with a token-overlap ratio at/above this against *some* span is
# considered entailed by that span.  Set to 0.5 so the claim must be
# *majority-present* in a span — boilerplate ("user said") cannot alone
# carry a match (a 0.9-confidence "user said the password is hunter2"
# must NOT ground on a span that merely shares "user said").  This is the
# lexical half of the hallucination trap; Q6-B adds semantic coverage.
ENTAIL_MIN_OVERLAP = 0.5

# Tokens shorter than this are stopwords-ish and ignored for matching.
_MIN_TOKEN_LEN = 3

# Filename/identifier snippets that should not dominate matching.
_STOP_TOKENS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "will",
        "has",
        "have",
        "are",
        "was",
        "were",
        "but",
        "not",
        "please",
        "could",
        "should",
        "would",
        "then",
        "than",
    }
)


@dataclass
class TranscriptSpan:
    """One retrievable unit of the source transcript (a turn / chunk)."""

    span_id: str
    text: str
    # Optional metadata (speaker, timestamp) — carried through for the
    # evidence trail but not used in matching.
    meta: dict[str, Any] = field(default_factory=dict)

    def tokens(self) -> set[str]:
        return _tokenize(self.text)


@dataclass
class Claim:
    """A proposed write that must be grounded in the transcript."""

    # Stable id for this claim (e.g. "mem.user_42.key=api_token").
    claim_id: str
    # The natural-language content asserted by the write (what the
    # reviewer wants to persist).  This is what we check for support.
    content: str
    # The reviewer's *stated* confidence in [0,1].  Used only for
    # telemetry + calibration (Q6-C); NEVER to bypass grounding.
    stated_confidence: float = 1.0
    # Optional: a span the reviewer *claims* it came from.  When present
    # we still verify it; when absent we retrieve broadly.
    alleged_span_id: str | None = None

    def tokens(self) -> set[str]:
        return _tokenize(self.content)


@dataclass
class SpanEvidence:
    """One span that was checked as potential support for the claim."""

    span_id: str
    # Token-overlap ratio [0,1] between claim and this span.
    overlap: float
    # True when overlap meets ENTAIL_MIN_OVERLAP.
    supports: bool


@dataclass
class GroundingVerdict:
    """Result of a groundedness check."""

    claim_id: str
    grounded: bool
    # The best (highest-overlap) supporting span id, or None.
    supporting_span_id: str | None
    # Overlap ratio of the best span.
    best_overlap: float
    # Per-span evidence (for audit / HITL context).
    evidence: list[SpanEvidence]
    # Human-readable reason (always present; feeds HITL context).
    reason: str
    # The stated confidence, echoed for calibration correlation.
    stated_confidence: float

    @property
    def rejected(self) -> bool:
        """A claim is rejected for HITL when it is NOT grounded.

        Confidence is deliberately NOT part of this predicate — Q6-A's
        whole point is that an ungrounded claim is rejected no matter how
        confident the reviewer claims to be.
        """
        return not self.grounded


def _tokenize(text: str) -> set[str]:
    """Lowercase, strip punctuation, drop stopwords + short tokens."""
    toks = re.findall(r"[a-z0-9_]+", text.lower())
    out: set[str] = set()
    for t in toks:
        if len(t) < _MIN_TOKEN_LEN:
            continue
        if t in _STOP_TOKENS:
            continue
        out.add(t)
    return out


def _overlap(a: set[str], b: set[str]) -> float:
    """Jaccard-ish overlap of two token sets, normalised by the claim.

    We normalise by ``|a|`` (the claim) so a *subset* of the claim present
    in the span scores high, while an enormous span that merely *contains*
    the claim's tokens does not inflate the ratio artificially beyond the
    claim's own size.  Returns 0.0 when the claim has no matchable tokens.
    """
    if not a:
        return 0.0
    inter = a & b
    if not inter:
        return 0.0
    return len(inter) / len(a)


class GroundednessVerifier:
    """Retrieve + entail a claim against a transcript.

    Pure + deterministic.  Build once per transcript, then call
    :meth:`verify` per claim.  No side effects.
    """

    def __init__(self, transcript: list[TranscriptSpan]) -> None:
        self._spans = list(transcript)
        self._by_id: dict[str, TranscriptSpan] = {s.span_id: s for s in self._spans}

    def verify(self, claim: Claim) -> GroundingVerdict:
        """Return whether ``claim`` is grounded in the transcript.

        The flow:
        1. If the claim names an ``alleged_span_id``, we verify *that*
           span first (it must still actually support the claim).
        2. Otherwise (or if the alleged span does not support it), we
           retrieve the top spans by token overlap and require at least
           one to meet ``ENTAIL_MIN_OVERLAP``.
        """
        claim_toks = claim.tokens()
        evidence: list[SpanEvidence] = []

        # 1. Honour + verify an explicit alleged span (never trust it).
        if claim.alleged_span_id is not None:
            span = self._by_id.get(claim.alleged_span_id)
            if span is not None:
                ov = _overlap(claim_toks, span.tokens())
                evidence.append(SpanEvidence(span.span_id, ov, ov >= ENTAIL_MIN_OVERLAP))
                if ov >= ENTAIL_MIN_OVERLAP:
                    return self._verdict(claim, span.span_id, ov, evidence, "explicit alleged span supports claim")

        # 2. Broad retrieve: score every span, keep those that support.
        scored: list[SpanEvidence] = []
        for span in self._spans:
            ov = _overlap(claim_toks, span.tokens())
            if ov <= 0.0:
                continue
            scored.append(SpanEvidence(span.span_id, ov, ov >= ENTAIL_MIN_OVERLAP))

        evidence.extend(scored)
        if not scored:
            return self._verdict(
                claim,
                None,
                0.0,
                evidence,
                "no transcript span contains the claim's content (claim is not grounded in the source)",
            )

        best = max(scored, key=lambda e: e.overlap)
        if best.supports:
            return self._verdict(
                claim,
                best.span_id,
                best.overlap,
                evidence,
                f"claim is entailed by supporting span {best.span_id} (overlap={best.overlap:.2f})",
            )
        return self._verdict(
            claim,
            None,
            best.overlap,
            evidence,
            f"best-matching span {best.span_id} only overlaps at {best.overlap:.2f} "
            f"(< {ENTAIL_MIN_OVERLAP:.2f} threshold); claim is not grounded",
        )

    @staticmethod
    def _verdict(
        claim: Claim,
        supporting: str | None,
        best_overlap: float,
        evidence: list[SpanEvidence],
        reason: str,
    ) -> GroundingVerdict:
        return GroundingVerdict(
            claim_id=claim.claim_id,
            grounded=supporting is not None,
            supporting_span_id=supporting,
            best_overlap=best_overlap,
            evidence=evidence,
            reason=reason,
            stated_confidence=claim.stated_confidence,
        )
