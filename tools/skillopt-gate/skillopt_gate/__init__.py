"""SkillOpt-Gate — a validation-gated skill optimizer (SkillOpt pattern, offline-safe).

Implements the honest core of microsoft/SkillOpt without touching model
weights: the *trainable parameter* is a single markdown skill document; an
*optimizer* proposes bounded add/delete/replace edits; a *validation gate*
accepts an edited skill only if it STRICTLY improves a held-out score.

The gate is pure and needs no LLM, so the honesty mechanism runs fully
offline. The optimizer step is pluggable:

  * ``DeterministicOptimizer`` — accepts pre-supplied candidate edits
    (e.g. hypotheses you wrote, or edits from another agent). Always runnable,
    no API key required.
  * ``LLMOptimizer`` — asks an OpenAI-compatible chat model for edits.
    Key-gated; never imported at module load so the tool works without the
    ``openai`` package or a key.

By default proposals are written to a STAGING dir for human review; adoption
is an explicit ``--adopt`` step. This matches Hermes autonomy rules
(ASK FIRST on prod/destructive changes) — the optimizer never mutates a
live skill on its own.

See ``SKILL.md`` for the wrapped-agent usage.
"""

from __future__ import annotations

from .core import (
    Edit,
    GateAction,
    GateMetric,
    Patch,
    SkillDoc,
    apply_edit,
    apply_patch,
    evaluate_gate,
    select_gate_score,
)
from .optimizer import DeterministicOptimizer, LLMOptimizer, Optimizer
from .runner import run_session
from .staging import redact_secrets, write_staging

__all__ = [
    "Edit",
    "Patch",
    "SkillDoc",
    "GateAction",
    "GateMetric",
    "apply_edit",
    "apply_patch",
    "evaluate_gate",
    "select_gate_score",
    "Optimizer",
    "DeterministicOptimizer",
    "LLMOptimizer",
    "run_session",
    "write_staging",
    "redact_secrets",
]
