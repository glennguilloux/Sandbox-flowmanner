"""CriticAgent + RedTeamAgent — D30-60, T25.

These are the *adversarial* LLM-calling services that score a
``(mission_goal, plan, outcome)`` triple and return a structured
``CriticOutput`` DTO ready to be persisted by T27.

Design notes (see plan §D30-60):

* **LLM is the real path.** The system prompt asks the model for
  structured JSON output (scores, summary, misses, risks, improvements,
  alternatives). The ``deepseek-chat`` default keeps each call cheap
  (~$0.001 per run). Temperature is ``0.2`` for the critic (deterministic
  scoring) and ``0.4`` for the red-team variant (exploratory attacks).
* **No DB access.** This is a pure-logic service. T27 owns persistence.
* **BudgetEnforcer is the ONLY LLM path** (project rule — services/AGENTS.md
  rule 8). The agent never calls ``ModelRouter`` or ``httpx`` directly.
* **Late-binding enforcer.** ``get_budget_enforcer`` is a module-level
  callable (not the instance itself), so tests can inject a mock
  (``patch("app.services.critic.get_budget_enforcer", ...)``) without
  monkey-patching the global singleton. Production code uses the
  module-level function which delegates to the singleton accessor.
* **Permissive JSON parsing.** The LLM is told to wrap output in a JSON
  fence, but in practice it often returns prose-wrapped JSON. The parser
  tries three fall-throughs: ``json.loads(content)`` → extract the
  first ``{...}`` block → ``{}`` (silent — never raises on bad LLM
  output, just records the absence of fields).
* **Score clamping.** All four scores are clamped to ``[0.0, 1.0]``.
  Missing scores stay ``None`` so the persistence layer (T27) can
  distinguish "the critic didn't score this" from "the critic scored
  this as zero".
* **No ``db.commit()`` anywhere** (services/AGENTS.md rule 3).
* **Async-first** (services/AGENTS.md rule 1) — every public method is
  ``async def``.
* **Parameterised logging** (project rule) — no ``f"..."`` in
  ``logger.()`` calls.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.models.capability_models import Budget, BudgetExhausted

logger = logging.getLogger(__name__)


# ── Module-level constants (tunable defaults) ─────────────────────────────


#: Default model. Cheap + fast; the critic is mostly JSON-shape work, not
#: reasoning. Override per-instance via ``CriticAgent(model_id=...)``.
CRITIC_DEFAULT_MODEL: str = "deepseek-v4-flash"

#: Default temperature. Low (0.2) so the critic is *deterministic* — the
#: same (goal, plan, outcome) tuple should produce the same scores.
CRITIC_DEFAULT_TEMPERATURE: float = 0.2

#: Default max output tokens. 2000 is enough for ~20 improvements +
#: ~20 risks + prose; 4000 would be the "long-form" knob.
CRITIC_DEFAULT_MAX_TOKENS: int = 2000

#: RedTeamAgent temperature. Higher (0.4) — the red team is *meant* to
#: explore, not reproduce. Tweak in future T-cycles if needed.
RED_TEAM_DEFAULT_TEMPERATURE: float = 0.4

#: Default per-call budget. ``$0.10`` is plenty for a single
#: ``deepseek-chat`` JSON-shape call.
CRITIC_DEFAULT_BUDGET_USD: Decimal = Decimal("0.10")


# ── Prompts (module-level so tests can introspect them) ────────────────────


# System prompt — static (no template variables). It instructs the LLM
# to act as an adversarial critic and return a single JSON object with
# the documented field set.
CRITIC_SYSTEM_PROMPT: str = """\
You are an adversarial critic for an AI mission-execution system.

Your job: read the (mission_goal, plan, outcome) triple below and
return a SINGLE JSON object with the following fields:

- "score_overall"      (float in [0.0, 1.0]) — overall plan quality.
- "score_alignment"    (float in [0.0, 1.0]) — how well the plan \
addresses the mission_goal.
- "score_safety"       (float in [0.0, 1.0]) — safety/risk score \
(higher = safer).
- "score_completeness" (float in [0.0, 1.0]) — how complete the \
outcome is vs. the plan.
- "summary"            (string, ≤ 300 chars) — one-sentence verdict.
- "misses"             (list[str]) — requirements the plan failed to \
address.
- "risks"              (list[str]) — concrete risks in the plan/outcome.
- "improvements"       (list[dict]) — suggested fixes, each as \
{"description": str, "confidence": float in [0.0, 1.0]}.
- "alternatives"       (list[dict]) — alternative plan outlines, each \
as {"approach": str, "tradeoffs": str, "score": float in [0.0, 1.0]}.

Output format:
- Wrap the JSON object in a ```json ... ``` fence.
- If you have nothing to flag, return an empty list for the list \
fields and null for the score fields.
- Do NOT add commentary outside the fence.

Scoring guidance:
- 0.0–0.3  = serious problems; mission is likely to fail.
- 0.4–0.6  = workable but with notable gaps.
- 0.7–0.8  = solid; minor improvements available.
- 0.9–1.0  = exceptional; ship as-is.
"""


# User prompt template — placeholders are filled at call time. The
# placeholders must include every key CriticAgent / RedTeamAgent
# substitutes in (so the .format() call doesn't KeyError).
CRITIC_USER_PROMPT_TEMPLATE: str = """\
MISSION_GOAL:
{goal}

PLAN:
{plan}

OUTCOME:
{outcome}

ADDITIONAL CONTEXT:
{context}

Return a single ```json ... ``` block with the structure described in \
the system prompt. Scores must be floats in [0.0, 1.0].
"""


# ── Permissive JSON extraction ────────────────────────────────────────────


# Matches the first balanced-looking JSON object in a string. We don't
# parse "balanced" — we use a non-greedy match and rely on the JSON
# parser to fail if the bracket depth is wrong. The non-greedy modifier
# is important: LLM prose is full of `{` characters we don't want to
# capture into the JSON.
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)


def _extract_json_object(content: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from an LLM response.

    Three fall-throughs, in order:
      1. The whole content is valid JSON.
      2. The first ``{...}`` block in the content is valid JSON.
      3. ``None`` (silent — caller treats this as "no fields returned").

    Never raises on bad LLM output.
    """
    if not content or not content.strip():
        return None

    # 1) Try the whole content first.
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        return parsed

    # 2) Try the first {...} block.
    m = _JSON_OBJECT_RE.search(content)
    if m:
        candidate = m.group(0)
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            return parsed

    return None


# ── DTOs ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CriticInput:
    """The triple (and optional context) the critic scores.

    ``plan`` and ``outcome`` accept either a dict (the structured form)
    or a plain string (a free-form summary). The agent serialises both
    forms into the user prompt the same way (json.dumps for dicts, str
    for strings).
    """

    mission_goal: str
    plan: Any  # dict | str
    outcome: Any  # dict | str
    context: dict[str, Any] | None = None


@dataclass
class CriticOutput:
    """Structured output of one critic run.

    Field names are 1:1 with the ``critiques`` table columns in
    ``app/models/critique_models.py`` (T24). T27 (persistence) reads
    these via :meth:`to_critique_kwargs` and writes a ``Critique`` row.

    Defaults:
      * Scores default to ``None`` (NOT 0.0) so a missing score is
        distinguishable from a real zero.
      * List fields default to ``[]`` (NOT ``None``) so consumers can
        iterate them unconditionally.
      * Provenance / audit fields default to ``None``.
    """

    # Scores
    score_overall: float | None = None
    score_alignment: float | None = None
    score_safety: float | None = None
    score_completeness: float | None = None

    # Verdict text + structured findings.
    summary: str | None = None
    misses: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    improvements: list[dict[str, Any]] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    raw_response: dict[str, Any] | None = None

    # LLM provenance / cost telemetry.
    model_id: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int | None = None

    def to_critique_kwargs(self) -> dict[str, Any]:
        """Return a dict keyed by ``Critique`` column names.

        T27's persistence path takes this dict and constructs a
        ``Critique(**kwargs)``. The keys are intentionally the SQLAlchemy
        column names (not the dataclass field names, which happen to
        match anyway) so that the persistence layer is decoupled from
        the dataclass shape.
        """
        return {
            "score_overall": self.score_overall,
            "score_alignment": self.score_alignment,
            "score_safety": self.score_safety,
            "score_completeness": self.score_completeness,
            "summary": self.summary,
            "misses": list(self.misses),
            "risks": list(self.risks),
            "improvements": [dict(i) for i in self.improvements],
            "alternatives": [dict(a) for a in self.alternatives],
            "raw_response": dict(self.raw_response) if self.raw_response else None,
            "model_id": self.model_id,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "duration_ms": self.duration_ms,
        }


# ── Helpers (internal) ────────────────────────────────────────────────────


def _clamp_score(value: Any) -> float | None:
    """Coerce a value to a float in [0.0, 1.0]. Returns None on failure.

    Used for every ``score_*`` field. The LLM is told to clamp, but the
    persistence layer has a CHECK constraint on ``score_overall`` so
    we'd rather clamp here than trip the constraint at INSERT time.
    """
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score != score:  # NaN guard.
        return None
    return max(0.0, min(1.0, score))


def _coerce_list_of_str(value: Any) -> list[str]:
    """Coerce a value to ``list[str]``; non-string elements are str()-ed.

    The LLM sometimes returns lists of dicts (e.g. one improvement
    object instead of its description). We keep the top-level shape
    intact (list) but flatten any non-string to a string so the
    consumer can render the field as text.
    """
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, (int, float, bool)):
                out.append(str(item))
            else:
                # Don't try to serialise arbitrary dicts into the misses/
                # risks columns — those are ``list[str]``. Drop them.
                continue
        return out
    if isinstance(value, str):
        return [value]
    return []


def _coerce_list_of_dict(value: Any) -> list[dict[str, Any]]:
    """Coerce a value to ``list[dict]``; non-dict elements are dropped.

    The improvements / alternatives columns are ``list[dict]``. We
    accept whatever shape the LLM returns and keep only dict-shaped
    items.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [dict(value)]
    return []


def _format_payload(value: Any) -> str:
    """Format a plan / outcome value for embedding in the user prompt.

    Dicts are JSON-serialised with a 2-space indent (so the LLM can
    reason about structure). Strings and other scalars are str()-ed.
    """
    if value is None:
        return "(none)"
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, indent=2, default=str)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


# ── Agent base ────────────────────────────────────────────────────────────


class _CriticAgentBase:
    """Shared scaffolding for ``CriticAgent`` and ``RedTeamAgent``.

    Both agents share: model/temp/max_tokens overrides, a callable
    ``get_budget_enforcer`` (so tests can inject a mock), the prompt
    construction, the LLM call, and the response parsing. The subclasses
    differ only in their default temperature.
    """

    def __init__(
        self,
        *,
        model_id: str = CRITIC_DEFAULT_MODEL,
        temperature: float = CRITIC_DEFAULT_TEMPERATURE,
        max_tokens: int = CRITIC_DEFAULT_MAX_TOKENS,
        get_budget_enforcer: Callable[[], Any] | None = None,
        budget: Budget | None = None,
    ) -> None:
        self.model_id = model_id
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        # Late-binding enforcer accessor (see module docstring). The
        # override is consulted first; the fallback (the module-level
        # ``get_budget_enforcer`` re-export) is looked up *at call time*
        # so tests can ``patch("app.services.critic.get_budget_enforcer")``
        # and have the patch take effect on every ``.critique()`` call.
        self._get_budget_enforcer_override: Callable[[], Any] | None = get_budget_enforcer
        self._budget: Budget = budget or Budget(max_cost_usd=CRITIC_DEFAULT_BUDGET_USD)

    # ── Prompt construction ──────────────────────────────────────────

    def _build_user_message(self, inp: CriticInput) -> str:
        """Render the user-role prompt for one critic run."""
        ctx_str = json.dumps(inp.context, indent=2, default=str) if inp.context else "(none)"
        return CRITIC_USER_PROMPT_TEMPLATE.format(
            goal=inp.mission_goal,
            plan=_format_payload(inp.plan),
            outcome=_format_payload(inp.outcome),
            context=ctx_str,
        )

    def _build_messages(self, inp: CriticInput) -> list[dict[str, Any]]:
        """Build the [system, user] message list sent to BudgetEnforcer.call."""
        return [
            {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
            {"role": "user", "content": self._build_user_message(inp)},
        ]

    # ── Response parsing ─────────────────────────────────────────────

    def _parse_response(
        self,
        content: str,
    ) -> dict[str, Any]:
        """Extract a JSON object from the LLM response. Returns ``{}`` on failure."""
        parsed = _extract_json_object(content)
        return parsed if parsed is not None else {}

    def _build_output(
        self,
        *,
        parsed: Mapping[str, Any],
        result: Mapping[str, Any],
        duration_ms: int,
    ) -> CriticOutput:
        """Translate the LLM result + parsed JSON into a ``CriticOutput``."""
        cost_info = result.get("cost") or {}
        tokens_in = cost_info.get("input_tokens")
        tokens_out = cost_info.get("output_tokens")
        model_id = result.get("model") or self.model_id

        return CriticOutput(
            score_overall=_clamp_score(parsed.get("score_overall")),
            score_alignment=_clamp_score(parsed.get("score_alignment")),
            score_safety=_clamp_score(parsed.get("score_safety")),
            score_completeness=_clamp_score(parsed.get("score_completeness")),
            summary=(str(parsed["summary"]) if parsed.get("summary") is not None else None),
            misses=_coerce_list_of_str(parsed.get("misses")),
            risks=_coerce_list_of_str(parsed.get("risks")),
            improvements=_coerce_list_of_dict(parsed.get("improvements")),
            alternatives=_coerce_list_of_dict(parsed.get("alternatives")),
            # raw_response is the FULL parsed payload (audit/replay
            # trail), not the raw LLM string. If the LLM returned
            # garbage, parsed is ``{}`` and we record ``None`` so the
            # persistence layer doesn't store an empty dict.
            raw_response=dict(parsed) if parsed else None,
            model_id=model_id,
            tokens_in=int(tokens_in) if tokens_in is not None else None,
            tokens_out=int(tokens_out) if tokens_out is not None else None,
            duration_ms=int(duration_ms),
        )

    # ── Main entry point ─────────────────────────────────────────────

    async def critique(
        self,
        *,
        mission_goal: str,
        plan: Any,
        outcome: Any,
        context: dict[str, Any] | None = None,
        user_id: int | str | None = None,
        workspace_id: str | None = None,
    ) -> CriticOutput:
        """Run a single critic pass and return the structured output.

        Args:
            mission_goal: The mission's stated goal (the critic's
                "what was the user actually trying to do?" anchor).
            plan: The plan that was/will-be executed. Dict or str.
            outcome: What actually happened. Dict or str.
            context: Optional workspace / mission metadata to inject
                into the user prompt (not persisted).
            user_id: For cost attribution. Optional; not used for DB
                writes (T25 doesn't write to the DB).
            workspace_id: Same — only used to pass through to the
                enforcer for circuit-breaker / provider routing.

        Returns:
            :class:`CriticOutput` — ready for T27 to persist.

        Raises:
            BudgetExhausted: Re-raised from the enforcer. The agent
                does not fall back to regex (criticism requires the
                LLM).
        """
        inp = CriticInput(
            mission_goal=mission_goal,
            plan=plan,
            outcome=outcome,
            context=context,
        )
        return await self.critique_from(inp, user_id=user_id, workspace_id=workspace_id)

    async def critique_from(
        self,
        inp: CriticInput,
        *,
        user_id: int | str | None = None,
        workspace_id: str | None = None,
    ) -> CriticOutput:
        """Variant of :meth:`critique` that takes a pre-built :class:`CriticInput`."""
        # Telemetry: log start (parameterised; no f-strings in logger).
        logger.info(
            "critic.run.start model_id=%s user_id=%s workspace_id=%s",
            self.model_id,
            user_id,
            workspace_id,
        )
        start = time.monotonic()

        messages = self._build_messages(inp)
        # Per-instance override wins; else look up the module-level
        # ``get_budget_enforcer`` at call time so test patches take
        # effect (the lookup goes through ``globals()``, which is the
        # patched namespace).
        if self._get_budget_enforcer_override is not None:
            enforcer = self._get_budget_enforcer_override()
        else:
            enforcer = get_budget_enforcer()

        # IMPORTANT: do NOT catch BudgetExhausted — the spec mandates
        # re-raise. The caller (T28 route, T27 caller) is responsible
        # for translating it into a 402 / 429 / domain error.
        result = await enforcer.call(
            budget=self._budget,
            model_id=self.model_id,
            messages=messages,
            user_id=str(user_id) if user_id is not None else None,
            workspace_id=workspace_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        duration_ms = int((time.monotonic() - start) * 1000)

        # The enforcer returns ``{"success": False, ...}`` for soft
        # failures (e.g. provider error). We treat that the same as a
        # garbage response: emit telemetry, default-everything output.
        success = bool(result.get("success", False))
        if not success:
            logger.warning(
                "critic.run.enforcer_failure model_id=%s user_id=%s error=%s",
                self.model_id,
                user_id,
                result.get("error"),
            )
            return self._build_output(
                parsed={},
                result=result,
                duration_ms=duration_ms,
            )

        # The mission_program_service path reads either ``response`` or
        # ``content``; BudgetEnforcer uses ``response``. Accept both
        # to be defensive (the project mixes both keys).
        content = result.get("response") or result.get("content") or ""
        parsed = self._parse_response(content)

        out = self._build_output(
            parsed=parsed,
            result=result,
            duration_ms=duration_ms,
        )

        # Telemetry: log end (parameterised; no f-strings in logger).
        logger.info(
            "critic.run.end model_id=%s user_id=%s duration_ms=%s score_overall=%s",
            self.model_id,
            user_id,
            out.duration_ms,
            out.score_overall,
        )
        return out


# ── Public agents ─────────────────────────────────────────────────────────


class CriticAgent(_CriticAgentBase):
    """Primary critic — deterministic plan-scoring.

    Use this for: "did the plan cover the goal?", "what's missing?",
    "are the scores sane?". Low temperature (0.2) so the same triple
    produces the same scores across runs.
    """

    def __init__(
        self,
        *,
        model_id: str = CRITIC_DEFAULT_MODEL,
        temperature: float = CRITIC_DEFAULT_TEMPERATURE,
        max_tokens: int = CRITIC_DEFAULT_MAX_TOKENS,
        get_budget_enforcer: Callable[[], Any] | None = None,
        budget: Budget | None = None,
    ) -> None:
        super().__init__(
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            get_budget_enforcer=get_budget_enforcer,
            budget=budget,
        )


class RedTeamAgent(_CriticAgentBase):
    """Adversarial variant — elevated temperature, risk-emphasis.

    Use this for: "what's the worst that could happen?", "where could
    this plan be exploited?", "what assumptions are unsafe?". Higher
    temperature (0.4) so the model explores alternatives rather than
    reproducing a fixed verdict.
    """

    def __init__(
        self,
        *,
        model_id: str = CRITIC_DEFAULT_MODEL,
        temperature: float = RED_TEAM_DEFAULT_TEMPERATURE,
        max_tokens: int = CRITIC_DEFAULT_MAX_TOKENS,
        get_budget_enforcer: Callable[[], Any] | None = None,
        budget: Budget | None = None,
    ) -> None:
        super().__init__(
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            get_budget_enforcer=get_budget_enforcer,
            budget=budget,
        )


# ── Module-level late-binding accessor (re-exported) ──────────────────────


# Import the singleton accessor at module level. Production code calls
# ``get_budget_enforcer()`` directly (this re-export) so the singleton
# is shared. Tests patch ``app.services.critic.get_budget_enforcer``
# to inject a mock — the call sites in ``_CriticAgentBase`` look up
# this name *at call time* (via Python's module globals), so patches
# take effect without the production code needing to thread the
# function through every call.
from app.services.budget_enforcer import get_budget_enforcer

__all__ = [
    "CRITIC_DEFAULT_BUDGET_USD",
    "CRITIC_DEFAULT_MAX_TOKENS",
    "CRITIC_DEFAULT_MODEL",
    "CRITIC_DEFAULT_TEMPERATURE",
    "CRITIC_SYSTEM_PROMPT",
    "CRITIC_USER_PROMPT_TEMPLATE",
    "RED_TEAM_DEFAULT_TEMPERATURE",
    "CriticAgent",
    "CriticInput",
    "CriticOutput",
    "RedTeamAgent",
]
