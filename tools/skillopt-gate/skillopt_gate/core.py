"""SkillOpt-Gate core: the validation gate + protected-region edit ops.

The gate (``evaluate_gate``) is the honesty mechanism. It is pure and
needs no LLM. The edit ops honor SkillOpt's *protected regions*: a
step-level edit may not mutate text inside a marked region (the skill-defect
vs execution-lapse discipline lives upstream; here we just enforce the
boundary, mirroring ``skillopt/optimizer/skill.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .types import Edit, Patch

GateAction = Literal["accept_new_best", "accept", "reject"]
GateMetric = Literal["hard", "soft", "mixed"]


# ── Protected regions (SkillOpt slow-update / appendix markers) ───────────────
SLOW_UPDATE_START = "<!-- SKILLOPT_SLOW_UPDATE_START -->"
SLOW_UPDATE_END = "<!-- SKILLOPT_SLOW_UPDATE_END -->"
APPENDIX_START = "<!-- SKILLOPT_APPENDIX_START -->"
APPENDIX_END = "<!-- SKILLOPT_APPENDIX_END -->"

_PROTECTED = (
    (SLOW_UPDATE_START, SLOW_UPDATE_END),
    (APPENDIX_START, APPENDIX_END),
)


# ── Gate score projection ────────────────────────────────────────────────────────
def select_gate_score(
    hard: float,
    soft: float,
    metric: GateMetric = "hard",
    mixed_weight: float = 0.5,
) -> float:
    """Project (hard, soft) onto a single comparison score.

    * ``hard``  — exact-match accuracy (0..1)
    * ``soft``  — F1 / partial credit (0..1)
    * ``mixed`` — (1-w)*hard + w*soft, w in [0,1]
    """
    if metric == "hard":
        return float(hard)
    if metric == "soft":
        return float(soft)
    if metric == "mixed":
        w = max(0.0, min(1.0, float(mixed_weight)))
        return (1.0 - w) * float(hard) + w * float(soft)
    raise ValueError(f"unknown gate metric {metric!r}; expected hard/soft/mixed")


@dataclass(frozen=True)
class GateResult:
    """Immutable outcome of the validation gate (mirrors skillopt/evaluation/gate.py)."""

    action: GateAction
    current_skill: str
    current_score: float
    best_skill: str
    best_score: float
    best_step: int
    candidate_skill: str = ""
    candidate_score: float = 0.0


def evaluate_gate(
    candidate_skill: str,
    cand_hard: float,
    current_skill: str,
    current_score: float,
    best_skill: str,
    best_score: float,
    best_step: int,
    global_step: int,
    *,
    cand_soft: float = 0.0,
    metric: GateMetric = "hard",
    mixed_weight: float = 0.5,
) -> GateResult:
    """Pure gate decision: compare candidate score to current/best.

    Accepts ONLY on strict improvement (candidate > current, and separately
    candidate > best for a new-best). A candidate that merely ties is
    rejected — that is what keeps training from drifting.
    """
    cand_score = select_gate_score(cand_hard, cand_soft, metric, mixed_weight)
    if cand_score > current_score:
        if cand_score > best_score:
            return GateResult(
                action="accept_new_best",
                current_skill=candidate_skill,
                current_score=cand_score,
                best_skill=candidate_skill,
                best_score=cand_score,
                best_step=global_step,
                candidate_skill=candidate_skill,
                candidate_score=cand_score,
            )
        return GateResult(
            action="accept",
            current_skill=candidate_skill,
            current_score=cand_score,
            best_skill=best_skill,
            best_score=best_score,
            best_step=best_step,
            candidate_skill=candidate_skill,
            candidate_score=cand_score,
        )
    return GateResult(
        action="reject",
        current_skill=current_skill,
        current_score=current_score,
        best_skill=best_skill,
        best_score=best_score,
        best_step=best_step,
        candidate_skill=candidate_skill,
        candidate_score=cand_score,
    )


# ── Protected-region helpers ────────────────────────────────────────────────
def _earliest_protected_start(skill: str) -> int:
    positions = [
        idx for idx in (skill.find(start) for start, _ in _PROTECTED) if idx != -1
    ]
    return min(positions) if positions else -1


def _is_in_protected_region(skill: str, target: str) -> bool:
    if not target:
        return False
    target_idx = skill.find(target)
    if target_idx == -1:
        return False
    for start_marker, end_marker in _PROTECTED:
        start_idx = skill.find(start_marker)
        end_idx = skill.find(end_marker)
        if start_idx == -1 or end_idx == -1:
            continue
        region_end = end_idx + len(end_marker)
        if start_idx <= target_idx < region_end:
            return True
    return False


def _strip_markers(text: str) -> str:
    for s, e in _PROTECTED:
        text = text.replace(s, "").replace(e, "")
    return text


# ── Edit application (mirrors skillopt/optimizer/skill.py) ─────────────────
def apply_edit(skill: str, edit: Edit) -> tuple[str, dict]:
    """Apply one edit; returns (new_skill, report).

    Edits targeting a protected region are skipped (status records the skip).
    """
    op = edit.op
    content = _strip_markers(edit.content.strip())
    target = edit.target
    report = {
        "op": op,
        "target": target[:200],
        "content_preview": content[:200],
        "status": "unknown",
    }

    if target and _is_in_protected_region(skill, target):
        report["status"] = "skipped_protected_region"
        return skill, report

    if op == "add":
        prot_start = _earliest_protected_start(skill)
        if prot_start != -1:
            before = skill[:prot_start].rstrip()
            after = skill[prot_start:]
            report["status"] = "applied_add_before_protected"
            return before + "\n\n" + content + "\n\n" + after, report
        report["status"] = "applied_add"
        return skill.rstrip() + "\n\n" + content + "\n", report

    if op == "replace":
        if not target:
            report["status"] = "skipped_replace_missing_target"
            return skill, report
        if target not in skill:
            report["status"] = "skipped_replace_target_not_found"
            return skill, report
        report["status"] = "applied_replace"
        return skill.replace(target, content, 1), report

    if op == "delete":
        if not target:
            report["status"] = "skipped_delete_missing_target"
            return skill, report
        if target not in skill:
            report["status"] = "skipped_delete_target_not_found"
            return skill, report
        report["status"] = "applied_delete"
        return skill.replace(target, "", 1), report

    report["status"] = "skipped_unknown_op"
    return skill, report


def apply_patch(skill: str, patch: Patch) -> tuple[str, list[dict]]:
    """Apply a patch (list of edits) sequentially; return (skill, reports)."""
    reports: list[dict] = []
    for idx, edit in enumerate(patch.edits, 1):
        try:
            skill, report = apply_edit(skill, edit)
            report["index"] = idx
        except Exception as exc:  # noqa: BLE001
            report = {
                "index": idx,
                "op": "",
                "target": "",
                "content_preview": "",
                "status": "error",
                "error": str(exc),
            }
        reports.append(report)
    return skill, reports


# ── SkillDoc: a skill + helpers to inject empty protected regions ─────────────
class SkillDoc:
    """Thin wrapper holding the markdown text + region scaffolding."""

    def __init__(self, text: str) -> None:
        self.text = text

    @classmethod
    def scaffold(cls, title: str = "agent skill") -> "SkillDoc":
        base = (
            f"# {title}\n\n"
            "Core rules the agent must follow.\n\n"
            "<!-- SKILLOPT_APPENDIX_START -->\n"
            "## Execution Notes Appendix\n"
            "<!-- SKILLOPT_APPENDIX_END -->\n"
        )
        return cls(base)

    def has_appendix(self) -> bool:
        return APPENDIX_START in self.text and APPENDIX_END in self.text
