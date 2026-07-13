"""Tests for skillopt-gate core: gate, score projection, redaction.

No network, no API key — the whole honesty mechanism runs offline.
"""

from __future__ import annotations

import pytest

from skillopt_gate.core import (
    evaluate_gate,
    select_gate_score,
)


# ── Gate score projection ──────────────────────────────────────────────
def test_select_gate_score_hard():
    assert select_gate_score(0.5, 0.9, "hard") == 0.5
    assert select_gate_score(0.5, 0.9, "soft") == 0.9


def test_select_gate_score_mixed_weights():
    assert select_gate_score(0.5, 1.0, "mixed", 0.0) == 0.5
    assert select_gate_score(0.5, 1.0, "mixed", 1.0) == 1.0
    # w=0.5 midpoint
    assert select_gate_score(0.4, 0.6, "mixed", 0.5) == pytest.approx(0.5)


def test_select_gate_score_mixed_clamps_weight():
    # out-of-range weight is clamped to [0,1]
    assert select_gate_score(0.5, 0.9, "mixed", 5.0) == 0.9
    assert select_gate_score(0.5, 0.9, "mixed", -3.0) == 0.5


# ── Gate decision: strict improvement only ──────────────────────────────
def _gate(
    cand_hard, curr_hard, best_hard, metric="hard", mixed_weight=0.5, cand_soft=0.0
):
    return evaluate_gate(
        candidate_skill=f"S_cand_{cand_hard}",
        cand_hard=cand_hard,
        current_skill="S_curr",
        current_score=curr_hard,
        best_skill="S_best",
        best_score=best_hard,
        best_step=0,
        global_step=1,
        metric=metric,
        mixed_weight=mixed_weight,
        cand_soft=cand_soft,
    )


def test_gate_rejects_when_not_strictly_better():
    g = _gate(cand_hard=0.5, curr_hard=0.6, best_hard=0.6)
    assert g.action == "reject"
    # the live skill is NOT swapped in: current_skill is unchanged
    assert g.current_skill == "S_curr"


def test_gate_rejects_a_tie():
    # a candidate that merely ties current must be rejected (no drift)
    g = _gate(cand_hard=0.6, curr_hard=0.6, best_hard=0.6)
    assert g.action == "reject"


def test_gate_accepts_when_beats_current_but_not_best():
    g = _gate(cand_hard=0.65, curr_hard=0.6, best_hard=0.8)
    assert g.action == "accept"
    assert g.current_skill.startswith("S_cand")
    assert g.best_skill == "S_best"  # best untouched


def test_gate_accepts_new_best():
    g = _gate(cand_hard=0.9, curr_hard=0.6, best_hard=0.8)
    assert g.action == "accept_new_best"
    assert g.best_skill.startswith("S_cand")
    assert g.best_step == 1


def test_gate_mixed_metric_uses_softmax():
    # cand hard=0.4 soft=1.0, w=0.5 -> mixed = 0.7 ; curr mixed = 0.4 -> accept
    g = _gate(
        cand_hard=0.4,
        curr_hard=0.4,
        best_hard=0.4,
        metric="mixed",
        mixed_weight=0.5,
        cand_soft=1.0,
    )
    assert g.action.startswith("accept")
