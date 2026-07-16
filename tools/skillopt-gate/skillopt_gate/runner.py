"""Runner: one validated optimization session.

Orchestrates the offline loop:

    current_skill
      │
      ▼
    optimizer.propose(skill)  ──► candidate Patch
      │
      ▼
    apply_patch(skill, patch)  ──► candidate_skill
      │
      ▼
    checker(candidate_skill)  ──► (hard, soft)  held-out score
      │
      ▼
    evaluate_gate(...)  ──► accept / reject (strict improvement only)

The ``checker`` is YOUR held-out test (a pytest, a linter, a harness).
It is the only thing that decides "better". The optimizer never touches
the live file — results are staged for review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .core import (
    GateMetric,
    GateResult,
    apply_patch,
    evaluate_gate,
    select_gate_score,
)
from .optimizer import Optimizer
from .staging import StageResult, write_staging
from .types import Patch


class Checker(Protocol):
    def __call__(self, skill: str) -> tuple[float, float]:
        """Return (hard_score, soft_score) for the given skill text, each 0..1."""
        ...


@dataclass
class SessionResult:
    gate: GateResult
    candidate_skill: str
    per_edit_reports: list[dict] = field(default_factory=list)
    staged: StageResult | None = None
    checker_scores: tuple[float, float] = (0.0, 0.0)


def _score_checker(checker: Checker, skill: str) -> tuple[float, float]:
    out = checker(skill)
    hard, soft = float(out[0]), float(out[1])
    return max(0.0, min(1.0, hard)), max(0.0, min(1.0, soft))


def run_session(
    *,
    current_skill: str,
    optimizer: Optimizer,
    checker: Checker,
    live_skill_path: str | None = None,
    metric: str = "hard",
    mixed_weight: float = 0.5,
    step: int = 1,
    verbose: bool = True,
) -> SessionResult:
    gate_metric: GateMetric = metric  # type: ignore[assignment]
    """Run one gated optimization step. Staged; never mutates live skill here."""

    patch: Patch = optimizer.propose(current_skill)
    candidate_skill, per_edit = apply_patch(current_skill, patch)

    cand_hard, cand_soft = _score_checker(checker, candidate_skill)
    curr_hard, curr_soft = _score_checker(checker, current_skill)

    gate = evaluate_gate(
        candidate_skill=candidate_skill,
        cand_hard=cand_hard,
        current_skill=current_skill,
        current_score=select_gate_score(
            curr_hard, curr_soft, gate_metric, mixed_weight
        ),
        best_skill=current_skill,  # single-step: current == best
        best_score=select_gate_score(curr_hard, curr_soft, gate_metric, mixed_weight),
        best_step=step,
        global_step=step,
        cand_soft=cand_soft,
        metric=gate_metric,
        mixed_weight=mixed_weight,
    )

    if verbose:
        print(
            f"[skillopt-gate] step={step} "
            f"curr={curr_hard:.3f}/{curr_soft:.3f} "
            f"cand={cand_hard:.3f}/{cand_soft:.3f} "
            f"→ {gate.action}"
        )
        for r in per_edit:
            print(f"    edit#{r.get('index')} [{r.get('op')}] {r.get('status')}")

    staged: StageResult | None = None
    if live_skill_path and gate.action != "reject":
        report = {
            "action": gate.action,
            "candidate_score": gate.candidate_score,
            "current_score": gate.current_score,
            "best_score": gate.best_score,
        }
        staged = write_staging(
            live_skill_path=live_skill_path,
            report=report,
            candidate_skill=candidate_skill,
            per_edit_reports=per_edit,
        )
        if verbose:
            print(f"    staged → {staged.staging_dir}")

    return SessionResult(
        gate=gate,
        candidate_skill=candidate_skill,
        per_edit_reports=per_edit,
        staged=staged,
        checker_scores=(cand_hard, cand_soft),
    )
