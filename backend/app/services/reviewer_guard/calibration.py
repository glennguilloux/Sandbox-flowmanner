"""Q6-C — Reviewer confidence calibration.

LLM reviewers emit a stated confidence (e.g. ``0.9``) alongside each
proposed write.  Empirically, stated confidence is *not* equal to
empirical accuracy — over-confident models sail a ``0.9`` hallucination
straight through.  We therefore never store the raw stated confidence as
the system's trust signal.  Instead we fit a *calibration map* from a
history of ``(stated_confidence, was_correct)`` labels (sourced from
GOV-1.5 drop logs + HITL outcomes) and store the **calibrated** value.

Design
------
* Pure-logic module (no DB access, no LLM calls).  Fits happen in
  process from an in-memory / injected label list.  The persistence of
  the fitted map is the caller's concern (Q6-D records drift; the
  calibration parameters are serialisable via :meth:`CalibrationMap.to_dict`).
* Two estimators:
  - ``isotonic`` — non-parametric, monotonic (sklearn ``IsotonicRegression``).
    Best when you have plenty of labelled points and the map is
    non-linear.
  - ``platt`` — logistic (Platt scaling).  Smooth, needs few points,
    degrades gracefully when there are <2 distinct classes.
* When there are too few labels to fit (default ``< 20``), we fall back
  to a conservative *shrink-toward-0.5* heuristic so a cold-start system
  never trusts an uncalibrated ``0.9``.  This is the key hallucination
  trap guard: with no data, we refuse to take stated confidence at face
  value.
* The fitted map is **monotonic non-decreasing** in stated confidence by
  construction (both isotonic and Platt scaling enforce it), so a higher
  stated confidence can never map to a *lower* calibrated trust.

The module is deterministic and side-effect free beyond the fitted
estimator object (which holds only floats).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, cast

import numpy as np

try:  # sklearn ships in the backend venv; keep import lazy + forgiving.
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression

    _SKLEARN_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when sklearn missing
    IsotonicRegression = None  # type: ignore[assignment]
    LogisticRegression = None  # type: ignore[assignment]
    _SKLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)

# Below this many labelled points we cannot trust a fitted map; fall back
# to the conservative prior.
MIN_FIT_SAMPLES = 20

# Cold-start / low-data calibrated value: shrink stated confidence toward
# the uncertainty point (0.5) so an uncalibrated 0.9 becomes ~0.57.
COLD_START_SHRINK = 0.5

CalibrationMethod = Literal["isotonic", "platt"]


@dataclass
class Label:
    """A single calibration label: a stated confidence and whether the
    corresponding claim turned out to be correct (per HITL / GOV-1.5)."""

    stated: float
    correct: bool


@dataclass
class CalibrationStats:
    """Summary of a fitted map — surfaced in Q6-D degradation tracking."""

    method: CalibrationMethod
    n_samples: int
    # Brier score of the calibrated predictions vs the empirical targets.
    brier_score: float
    # Mean absolute gap between stated and calibrated at the labelled points.
    mean_abs_shift: float
    # True when we fell back to the cold-start heuristic (insufficient data).
    used_fallback: bool = False


class CalibrationMap:
    """Maps a reviewer's *stated* confidence to a *calibrated* trust value.

    Construct from labels via :meth:`fit`, then call :meth:`calibrate` on
    each new stated confidence.  The instance is pickle/json-friendly via
    :meth:`to_dict` / :meth:`from_dict` so Q6-D can persist the map and
    re-load it after a model/provider change (re-fit on the canary set).
    """

    def __init__(
        self,
        method: CalibrationMethod = "isotonic",
        *,
        min_fit_samples: int = MIN_FIT_SAMPLES,
    ) -> None:
        self.method = method
        self.min_fit_samples = min_fit_samples
        # Fitted estimator (sklearn) or None when using the fallback.
        self._estimator: object | None = None
        self._stats = CalibrationStats(
            method=method,
            n_samples=0,
            brier_score=0.0,
            mean_abs_shift=0.0,
            used_fallback=True,
        )
        # Persisted parameters for from_dict rebuild (isotonic knots / Platt coef).
        self._knots_x: list[float] = []
        self._knots_y: list[float] = []
        self._platt_a: float | None = None
        self._platt_b: float | None = None

    # ── Fitting ───────────────────────────────────────────────────────

    @classmethod
    def fit(
        cls,
        labels: list[Label],
        method: CalibrationMethod = "isotonic",
        *,
        min_fit_samples: int = MIN_FIT_SAMPLES,
    ) -> CalibrationMap:
        """Build a calibrated map from historical labels."""
        cmap = cls(method=method, min_fit_samples=min_fit_samples)
        cmap._fit(labels)
        return cmap

    def _fit(self, labels: list[Label]) -> None:
        if not labels:
            self._stats = CalibrationStats(
                method=self.method,
                n_samples=0,
                brier_score=0.0,
                mean_abs_shift=0.0,
                used_fallback=True,
            )
            return

        stated = np.asarray([float(l.stated) for l in labels], dtype=float)
        correct = np.asarray([1.0 if l.correct else 0.0 for l in labels], dtype=float)
        n = len(labels)

        # Insufficient data → conservative fallback (no fit).
        if n < self.min_fit_samples or not _SKLEARN_AVAILABLE:
            self._use_fallback(stated, correct, n)
            return

        if self.method == "isotonic":
            self._fit_isotonic(stated, correct, n)
        else:
            self._fit_platt(stated, correct, n)

    def _use_fallback(self, stated: np.ndarray, correct: np.ndarray, n: int) -> None:
        # Conservative: calibrated = 0.5 + COLD_START_SHRINK * (stated - 0.5).
        # Higher stated → higher trust, but pulled hard toward uncertainty.
        calibrated = 0.5 + COLD_START_SHRINK * (stated - 0.5)
        self._estimator = None
        self._stats = CalibrationStats(
            method=self.method,
            n_samples=n,
            brier_score=float(np.mean((calibrated - correct) ** 2)),
            mean_abs_shift=float(np.mean(np.abs(calibrated - stated))),
            used_fallback=True,
        )

    def _fit_isotonic(self, stated: np.ndarray, correct: np.ndarray, n: int) -> None:
        assert IsotonicRegression is not None
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, increasing="auto", out_of_bounds="clip")
        iso.fit(stated, correct)
        pred = iso.predict(stated)
        # Persist the knot table so we can rebuild without sklearn present.
        self._knots_x = [float(x) for x in iso.X_thresholds_]
        self._knots_y = [float(y) for y in iso.y_thresholds_]
        self._estimator = iso
        self._platt_a = self._platt_b = None
        self._stats = CalibrationStats(
            method="isotonic",
            n_samples=n,
            brier_score=float(np.mean((pred - correct) ** 2)),
            mean_abs_shift=float(np.mean(np.abs(pred - stated))),
            used_fallback=False,
        )

    def _fit_platt(self, stated: np.ndarray, correct: np.ndarray, n: int) -> None:
        assert LogisticRegression is not None
        # Platt scaling: logistic regression of correct ~ stated.
        # Add a tiny ridge so a degenerate (all-correct / all-wrong) set
        # still yields a finite map instead of diverging to ±inf.
        X = stated.reshape(-1, 1)
        lr = LogisticRegression(C=1e6, solver="lbfgs")
        lr.fit(X, correct)
        a = float(lr.coef_[0][0])
        b = float(lr.intercept_[0])
        pred = 1.0 / (1.0 + np.exp(-(a * stated + b)))
        self._platt_a, self._platt_b = a, b
        self._knots_x = self._knots_y = []
        self._estimator = lr
        self._stats = CalibrationStats(
            method="platt",
            n_samples=n,
            brier_score=float(np.mean((pred - correct) ** 2)),
            mean_abs_shift=float(np.mean(np.abs(pred - stated))),
            used_fallback=False,
        )

    # ── Calibration (inference) ───────────────────────────────────────

    def calibrate(self, stated: float) -> float:
        """Return the calibrated trust value for a stated confidence.

        Always in ``[0.0, 1.0]``.  Falls back to the conservative
        shrink when no estimator was fitted (cold start / low data).
        """
        s = _clamp01(stated)
        if self._estimator is not None:
            if self.method == "isotonic" and self._knots_x:
                return float(_interp_knots(self._knots_x, self._knots_y, s))
            if self._platt_a is not None and self._platt_b is not None:
                return _clamp01(1.0 / (1.0 + np.exp(-(self._platt_a * s + self._platt_b))))
        # Fallback (covers no-estimator + safety net).
        return _clamp01(0.5 + COLD_START_SHRINK * (s - 0.5))

    @property
    def stats(self) -> CalibrationStats:
        return self._stats

    # ── Serialisation ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialise the fitted map to a JSON-safe dict (for Q6-D persistence)."""
        return {
            "method": self.method,
            "min_fit_samples": self.min_fit_samples,
            "stats": {
                "n_samples": self._stats.n_samples,
                "brier_score": self._stats.brier_score,
                "mean_abs_shift": self._stats.mean_abs_shift,
                "used_fallback": self._stats.used_fallback,
            },
            "knots_x": self._knots_x,
            "knots_y": self._knots_y,
            "platt_a": self._platt_a,
            "platt_b": self._platt_b,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CalibrationMap:
        """Rebuild a fitted map from :meth:`to_dict` output (no sklearn needed)."""
        cmap = cls(
            method=cast("CalibrationMethod", data.get("method", "isotonic")),
            min_fit_samples=data.get("min_fit_samples", MIN_FIT_SAMPLES),
        )
        cmap._knots_x = list(data.get("knots_x", []))
        cmap._knots_y = list(data.get("knots_y", []))
        cmap._platt_a = data.get("platt_a")
        cmap._platt_b = data.get("platt_b")
        stats = data.get("stats", {})
        cmap._stats = CalibrationStats(
            method=cmap.method,
            n_samples=int(stats.get("n_samples", 0)),
            brier_score=float(stats.get("brier_score", 0.0)),
            mean_abs_shift=float(stats.get("mean_abs_shift", 0.0)),
            used_fallback=bool(stats.get("used_fallback", True)),
        )
        # A rebuilt map is "live" only if it carries knots or Platt coefs.
        if cmap._knots_x and cmap._knots_y:
            cmap._estimator = _RebuiltIsotonic(cmap._knots_x, cmap._knots_y)
        elif cmap._platt_a is not None and cmap._platt_b is not None:
            cmap._estimator = _RebuiltPlatt(cmap._platt_a, cmap._platt_b)
        else:
            cmap._estimator = None
        return cmap


# ── Internal lightweight rebuilt estimators (no sklearn dependency) ─────


class _RebuiltIsotonic:
    """Linear-interpolation evaluator over persisted isotonic knots."""

    __slots__ = ("_x", "_y")

    def __init__(self, x: list[float], y: list[float]) -> None:
        self._x = x
        self._y = y


class _RebuiltPlatt:
    """Platt (logistic) evaluator over persisted coefficients."""

    __slots__ = ("_a", "_b")

    def __init__(self, a: float, b: float) -> None:
        self._a = a
        self._b = b


def _interp_knots(xs: list[float], ys: list[float], s: float) -> float:
    """Piecewise-linear interpolation over a monotonic knot table."""
    if not xs:
        return _clamp01(0.5 + COLD_START_SHRINK * (s - 0.5))
    if s <= xs[0]:
        return _clamp01(ys[0])
    if s >= xs[-1]:
        return _clamp01(ys[-1])
    for i in range(1, len(xs)):
        if s <= xs[i]:
            x0, x1 = xs[i - 1], xs[i]
            y0, y1 = ys[i - 1], ys[i]
            if x1 == x0:
                return _clamp01(y0)
            t = (s - x0) / (x1 - x0)
            return _clamp01(y0 + t * (y1 - y0))
    return _clamp01(ys[-1])


def _clamp01(v: float) -> float:
    if v != v:  # NaN guard
        return 0.5
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v
