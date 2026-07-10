"""Q6-D — Systemic degradation tracking + fixed canary transcript set.

Per-claim checks (Q6-A / Q6-B) catch individual hallucinations, but they
miss *systemic* drift: when a model/provider update quietly makes the
verifier *worse*, single-claim pass rates look fine while real
hallucinations start leaking.  Q6-D adds the system-level signal:

* **Grounding-pass rate** — fraction of claims that survive groundedness.
* **HITL-rejection rate** — fraction of escalated claims a human later
  rejects (the reviewer was wrong).
* **Verifier-disagreement rate** — fraction of claims where Q6-A (lexical)
  and Q6-B (semantic) disagree.  A *jump* here after a model/provider
  change is the "model got worse" alarm that per-claim checks miss.

Plus a **fixed, hand-labelled CANARY transcript set**: a small set of
transcripts + claims with known ground-truth (supported / not) that we
re-run on *every* model/provider change.  Because the labels are fixed,
any drop in canary accuracy is attributable to the model update, not to
data drift.

The module is pure logic + an in-memory ring buffer (no DB writes).  The
caller (Q6-E, or a cron/re-deploy hook) records events; Q6-D returns the
current rates and raises a :class:`DegradationAlarm` when a canary re-run
regresses or disagreement jumps.  Persistence of the rolling stats is the
caller's concern (it can snapshot :meth:`DegradationTracker.to_dict`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Rolling window for rate computation (most-recent-N events).
DEFAULT_WINDOW = 500

# If verifier-disagreement rate exceeds this, raise an alarm (the two
# passes should mostly agree; a spike means one model shifted).
DISAGREEMENT_ALARM_RATE = 0.25

# Canary re-run: if accuracy drops by more than this vs the last good run,
# raise an alarm.  0.10 = a >10pt absolute drop in canary accuracy.
CANARY_REGRESSION_DROP = 0.10


@dataclass
class CanaryClaim:
    """A hand-labelled claim in the fixed canary set.

    ``ground_truth`` is the known answer (True = the transcript *does*
    support the claim).  ``alleged_span_id`` is optional.
    """

    claim_id: str
    content: str
    ground_truth: bool
    alleged_span_id: str | None = None
    stated_confidence: float = 1.0


@dataclass
class CanaryTranscript:
    """A fixed, labelled canary transcript + its claims."""

    transcript_id: str
    spans: list[Any]  # list[TranscriptSpan] — kept generic to avoid cycle
    claims: list[CanaryClaim]


@dataclass
class DegradationAlarm:
    """Raised/returned when a systemic degradation signal trips."""

    kind: str  # "disagreement_spike" | "canary_regression" | "hitl_rejection_spike"
    metric: str
    value: float
    threshold: float
    detail: str


@dataclass
class SystemRates:
    """Current systemic rates over the rolling window."""

    window_size: int
    grounding_pass_rate: float
    hitl_rejection_rate: float
    verifier_disagreement_rate: float
    # Counts backing the rates.
    n_grounding: int
    n_hitl_resolved: int
    n_disagreement: int


class DegradationTracker:
    """Rolling, in-memory tracker of the three systemic rates + canary.

    All ``record_*`` methods are O(1) appends to bounded deques.  No I/O.
    """

    def __init__(self, window: int = DEFAULT_WINDOW) -> None:
        self.window = window
        # grounding outcomes: True=passed, False=rejected
        self._grounding: list[bool] = []
        # hitl outcomes: True=rejected-by-human (reviewer was wrong), False=approved
        self._hitl_rejected: list[bool] = []
        # disagreement outcomes: True=Q6-A and Q6-B disagreed
        self._disagreement: list[bool] = []
        # last canary accuracy for regression comparison
        self._last_canary_accuracy: float | None = None

    # ── Recording ────────────────────────────────────────────────────

    def record_grounding(self, passed: bool) -> None:
        self._grounding.append(bool(passed))
        self._trim(self._grounding)

    def record_hitl_resolution(self, human_rejected: bool) -> None:
        self._hitl_rejected.append(bool(human_rejected))
        self._trim(self._hitl_rejected)

    def record_disagreement(self, disagreed: bool) -> None:
        self._disagreement.append(bool(disagreed))
        self._trim(self._disagreement)

    def _trim(self, buf: list[bool]) -> None:
        while len(buf) > self.window:
            buf.pop(0)

    # ── Rate computation ─────────────────────────────────────────────

    def rates(self) -> SystemRates:
        g = self._grounding
        h = self._hitl_rejected
        d = self._disagreement
        return SystemRates(
            window_size=self.window,
            grounding_pass_rate=_rate(g),
            hitl_rejection_rate=_rate(h),
            verifier_disagreement_rate=_rate(d),
            n_grounding=len(g),
            n_hitl_resolved=len(h),
            n_disagreement=len(d),
        )

    def check_alarms(self) -> list[DegradationAlarm]:
        """Return any tripped alarms (does NOT raise — caller decides)."""
        alarms: list[DegradationAlarm] = []
        rates = self.rates()
        if rates.n_disagreement >= 10 and rates.verifier_disagreement_rate > DISAGREEMENT_ALARM_RATE:
            alarms.append(
                DegradationAlarm(
                    kind="disagreement_spike",
                    metric="verifier_disagreement_rate",
                    value=rates.verifier_disagreement_rate,
                    threshold=DISAGREEMENT_ALARM_RATE,
                    detail=(
                        "Q6-A (lexical) and Q6-B (semantic) disagree on "
                        f"{rates.verifier_disagreement_rate:.0%} of recent claims "
                        f"({rates.n_disagreement} events) — a model/provider update "
                        "likely shifted one pass."
                    ),
                )
            )
        if rates.n_hitl_resolved >= 10 and rates.hitl_rejection_rate > 0.40:
            alarms.append(
                DegradationAlarm(
                    kind="hitl_rejection_spike",
                    metric="hitl_rejection_rate",
                    value=rates.hitl_rejection_rate,
                    threshold=0.40,
                    detail=(
                        f"Humans rejected {rates.hitl_rejection_rate:.0%} of escalated "
                        f"claims ({rates.n_hitl_resolved} resolved) — the reviewer is "
                        "frequently wrong."
                    ),
                )
            )
        return alarms

    # ── Canary re-run ────────────────────────────────────────────────

    def record_canary_run(self, accuracy: float) -> DegradationAlarm | None:
        """Record a canary re-run accuracy; alarm on regression.

        ``accuracy`` is the fraction of canary claims whose predicted
        groundedness matched ``ground_truth``.  Compared against the last
        good run; a drop of more than ``CANARY_REGRESSION_DROP`` trips an
        alarm.  Returns the alarm (or None) and always stores the new value.
        """
        acc = max(0.0, min(1.0, float(accuracy)))
        prev = self._last_canary_accuracy
        self._last_canary_accuracy = acc
        if prev is None:
            return None
        drop = prev - acc
        if drop > CANARY_REGRESSION_DROP:
            return DegradationAlarm(
                kind="canary_regression",
                metric="canary_accuracy",
                value=acc,
                threshold=prev - CANARY_REGRESSION_DROP,
                detail=(
                    f"Canary accuracy dropped {drop:.0%} (from {prev:.0%} to {acc:.0%}) after a model/provider change."
                ),
            )
        return None

    @property
    def last_canary_accuracy(self) -> float | None:
        return self._last_canary_accuracy

    # ── Serialisation ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "window": self.window,
            "grounding": list(self._grounding)[-self.window :],
            "hitl_rejected": list(self._hitl_rejected)[-self.window :],
            "disagreement": list(self._disagreement)[-self.window :],
            "last_canary_accuracy": self._last_canary_accuracy,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DegradationTracker:
        t = cls(window=int(data.get("window", DEFAULT_WINDOW)))
        t._grounding = list(data.get("grounding", []))
        t._hitl_rejected = list(data.get("hitl_rejected", []))
        t._disagreement = list(data.get("disagreement", []))
        t._last_canary_accuracy = data.get("last_canary_accuracy")
        return t


def _rate(buf: list[bool]) -> float:
    """Fraction of True values; 0.0 for an empty buffer."""
    if not buf:
        return 0.0
    return sum(1 for x in buf if x) / len(buf)
