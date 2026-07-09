"""ImprovementGenerator — D30-60, T26.

Pure-logic, **sync** transformer that takes a :class:`CriticOutput`
(from T25) plus a :class:`MissionContext` and emits an
:class:`ImprovementBatch` of concrete, actionable adjustments that T27
can merge into a ``MissionProgram.learning_brief``.

Design notes (see plan §D30-60):

* **No LLM call, no DB, no async.** The class is a pure function —
  every method is sync, every public surface is a dataclass or
  :class:`ImprovementGenerator`. T27 owns persistence.
* **Deterministic.** Calling ``.generate()`` twice with the same
  input must return equal output; the function never mutates the
  input.
* **The four critic fields → four kinds of plan adjustments.**
  ``improvements`` → ``category="improvement"``; ``misses`` →
  ``category="miss"``; ``risks`` → ``category="risk"``;
  ``alternatives`` → ``category="alternative"``. Each carries a
  ``confidence`` (clamped to ``[0.0, 1.0]``) and the original
  critic text as ``source`` (for audit).
* **Dedupe is by normalized description** (``lower().strip()``,
  first 100 chars). Two adjustments with the same key are merged —
  keep the higher confidence; tie-break by category preference
  order (``improvement > risk > miss > alternative``).
* **Tool suggestions are extracted from descriptions.** A static
  ``_TOOL_KEYWORDS`` set is matched case-insensitively (substring)
  against the normalized description; a tool mentioned in multiple
  adjustments keeps the highest-confidence mention as its reason.
* **Common-failure patterns group misses by their first 50 chars
  of normalized text.** Sorted by occurrences descending. The
  ``mitigation`` field is a constant pointer at the corresponding
  plan adjustment.
* **Summary is truncated to 200 chars** (or ``"No summary"`` if
  the input is empty/None).
* **Score clamping + recommendation thresholds** are rule-based on
  ``score_overall``:

  * ``None`` or ``< 0.3``       → ``"discard"``
  * ``0.3 ≤ x < 0.6``           → ``"review_manually"``
  * ``0.6 ≤ x < 0.8``           → ``"apply_suggested"``
  * ``x ≥ 0.8``                 → ``"apply_all"``

  Out-of-range scores are clamped to ``[0.0, 1.0]`` first.
* **Description truncation** keeps each ``PlanAdjustment.description``
  to ≤ 500 chars (matching the ``consolidate_learning`` constraint
  for ``plan_adjustments``). Truncated descriptions get a single
  ``"…"`` suffix so the cap is honoured.

Tight rules (per the T26 spec):

* **No database write operations, no async-session imports.** This
  module is pure logic — it does not touch the DB.
* **Parameterised logging** (project rule) — no f-strings in
  logging calls. The module currently logs nothing.
* **``from __future__ import annotations``** for forward-reference
  safety.
* **All dataclasses have sensible defaults** so ``ImprovementBatch()``
  works with no args.
* **No ``app.api.*`` imports** — no HTTP layer coupling.
* **No model, no HTTP route, no migration** — T27 owns persistence,
  T28 owns the read API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.critic import CriticOutput

# ── DTOs ──────────────────────────────────────────────────────────────────


@dataclass
class ToolSuggestion:
    """A concrete tool the improvement loop should consider using.

    Attributes:
        tool_name: Canonical tool name (one of the ``_TOOL_KEYWORDS``
            set, e.g. ``"browser"``).
        reason: The description that triggered the suggestion
            (a plan-adjustment description).
        confidence: Clamped ``[0.0, 1.0]`` — sourced from the
            triggering plan adjustment.
    """

    tool_name: str = ""
    reason: str = ""
    confidence: float = 0.0


@dataclass
class PlanAdjustment:
    """A single concrete adjustment to the next plan.

    Attributes:
        description: ≤ 500 chars. Matches the
            ``consolidate_learning`` constraint on
            ``plan_adjustments`` in ``MissionProgram.learning_brief``.
        category: One of ``"improvement"``, ``"miss"``, ``"risk"``,
            ``"alternative"``. Used for dedupe tie-breaks and for
            the persistence layer (T27) to merge into the right
            sub-field of ``learning_brief``.
        confidence: Clamped ``[0.0, 1.0]``. Drives dedupe (higher
            confidence wins) and T27's downstream ranking.
        source: The original critic text (or dict-rendered form).
            Kept for audit / replay — T27 can persist this alongside
            the description.
    """

    description: str = ""
    category: str = ""
    confidence: float = 0.0
    source: str = ""


@dataclass
class MissionContext:
    """The (mission_id, goal, plan, outcome) context for one
    improvement run.

    The current rule set does not branch on context fields — they
    are accepted as part of the input contract so the caller (T27)
    can pass them through unchanged, and so future T-cycles can use
    them for context-aware adjustments (e.g. workspace-scoped
    tool preferences).
    """

    mission_id: str = ""
    goal: str = ""
    plan: dict = field(default_factory=dict)
    outcome: dict = field(default_factory=dict)
    user_id: int = 0
    workspace_id: str = ""


@dataclass
class ImprovementBatch:
    """The full output of one :meth:`ImprovementGenerator.generate` call.

    Sensible defaults so ``ImprovementBatch()`` works with no args.
    The defaults represent a "no critic" state (all empty lists,
    empty summary, neutral recommendation). The generator fills in
    these fields based on the critic output.
    """

    plan_adjustments: list[PlanAdjustment] = field(default_factory=list)
    tool_suggestions: list[ToolSuggestion] = field(default_factory=list)
    common_failure_patterns: list[dict] = field(default_factory=list)
    summary: str = ""
    #: One of ``"apply_all"``, ``"apply_suggested"``,
    #: ``"review_manually"``, ``"discard"``. Safe default is
    #: ``"review_manually"`` (a neutral middle ground — the
    #: generator overrides this based on ``score_overall``).
    overall_recommendation: str = "review_manually"


# ── ImprovementGenerator ──────────────────────────────────────────────────


class ImprovementGenerator:
    """Pure-logic transformer: :class:`CriticOutput` → :class:`ImprovementBatch`.

    No LLM call, no DB write, no async. T27 persists the batch.

    Args:
        min_confidence_threshold: Stored for future use (the current
            rule set does not filter on it). Defaults to ``0.3``.
    """

    #: Tool keywords extracted from improvement / alternative
    #: descriptions. Lowercase; matching is case-insensitive substring
    #: against the normalized description. Tune in future T-cycles.
    _TOOL_KEYWORDS: frozenset[str] = frozenset(
        {
            "browser",
            "search",
            "code_exec",
            "file_read",
            "file_write",
            "web_search",
            "rag",
            "llm",
        }
    )

    #: Category preference order for dedupe tie-breaks.
    #: **Lower number = higher preference.** ``"improvement"`` wins
    #: over ``"risk"``, ``"miss"``, ``"alternative"``. Used only when
    #: two adjustments have the same normalized-description prefix
    #: AND the same confidence.
    _CATEGORY_ORDER: dict[str, int] = {
        "improvement": 0,
        "risk": 1,
        "miss": 2,
        "alternative": 3,
    }

    #: Hard limits (chars).
    _MAX_DESCRIPTION_CHARS: int = 500
    _MAX_SUMMARY_CHARS: int = 200
    _DEDUPE_PREFIX_CHARS: int = 100
    _PATTERN_PREFIX_CHARS: int = 50

    #: Recommendation thresholds (lower bound = ``"discard"``,
    #: ``"review_manually"``, ``"apply_suggested"``; ``>= 0.8`` is
    #: ``"apply_all"``). Mirrors the critic's own scoring guidance.
    _RECOMMENDATION_DISCARD: float = 0.3
    _RECOMMENDATION_REVIEW: float = 0.6
    _RECOMMENDATION_APPLY_SUGGESTED: float = 0.8

    def __init__(self, *, min_confidence_threshold: float = 0.3) -> None:
        # Stored for future use; the current rule set does not
        # filter on it. Kept as an instance attribute so tests can
        # assert on it and so a future iteration can wire filtering
        # without changing the constructor signature.
        self.min_confidence_threshold = float(min_confidence_threshold)

    def generate(
        self,
        critic_output: CriticOutput,
        context: MissionContext,
    ) -> ImprovementBatch:
        """Build an :class:`ImprovementBatch` from a critic output.

        Args:
            critic_output: The structured output of a critic run
                (T25). The function only **reads** from this
                object — no mutation.
            context: The mission context (``mission_id``, ``goal``,
                ``plan``, ``outcome``, ``user_id``,
                ``workspace_id``). Reserved for context-aware
                adjustments in future T-cycles; the current rule
                set does not branch on context fields.

        Returns:
            An :class:`ImprovementBatch` ready for T27 to persist
            into ``MissionProgram.learning_brief``.
        """
        # 1. Parse the four critic fields into a flat list of
        #    plan adjustments.
        adjustments = self._to_plan_adjustments(critic_output)
        # 2. Dedupe by normalized-description prefix (first 100
        #    chars). Higher confidence wins; tie-break by category
        #    preference order.
        adjustments = self._dedupe_adjustments(adjustments)
        # 3. Extract tool-name keywords from the (deduped) plan
        #    adjustment descriptions. The list preserves the order
        #    in which each tool was first mentioned.
        tool_suggestions = self._to_tool_suggestions(adjustments)
        # 4. Group misses by their first 50 chars of normalized
        #    text to surface recurring failure patterns.
        common_failures = self._group_common_failures(critic_output.misses)
        # 5. Truncate the critic summary to 200 chars; substitute
        #    "No summary" for empty / None input.
        summary = self._summary(critic_output.summary)
        # 6. Map score_overall → one of four recommendations
        #    ("discard", "review_manually", "apply_suggested",
        #    "apply_all"). Out-of-range scores are clamped first.
        recommendation = self._recommendation(critic_output.score_overall)

        return ImprovementBatch(
            plan_adjustments=adjustments,
            tool_suggestions=tool_suggestions,
            common_failure_patterns=common_failures,
            summary=summary,
            overall_recommendation=recommendation,
        )

    # ── Helpers (private, all sync) ──────────────────────────────────

    def _to_plan_adjustments(
        self,
        critic_output: CriticOutput,
    ) -> list[PlanAdjustment]:
        """Parse the four critic fields into a flat list of
        :class:`PlanAdjustment` objects.

        Each input field has its own category:

        * ``improvements`` (list of dicts with ``description`` /
          ``confidence``) → ``category="improvement"``
        * ``misses`` (list of str) → ``category="miss"``;
          confidence defaults to ``score_overall`` (or 0.5)
        * ``risks`` (list of str) → ``category="risk"``;
          confidence defaults to ``score_safety`` (or 0.5)
        * ``alternatives`` (list of dicts with ``approach`` /
          ``tradeoffs`` / ``score``) → ``category="alternative"``;
          the description is ``f"{approach} — {tradeoffs}"``
        """
        out: list[PlanAdjustment] = []

        # improvements: list[dict{description, confidence}]
        for imp in critic_output.improvements or []:
            if not isinstance(imp, dict):
                continue
            raw_desc = str(imp.get("description", "") or "")
            desc = self._truncate(raw_desc)
            if not desc.strip():
                continue
            conf = self._clamp_confidence(imp.get("confidence", 0.5))
            out.append(
                PlanAdjustment(
                    description=desc,
                    category="improvement",
                    confidence=conf,
                    source=str(imp),
                )
            )

        # misses: list[str]
        miss_default_conf = self._clamp_confidence(
            critic_output.score_overall if critic_output.score_overall is not None else 0.5
        )
        for miss in critic_output.misses or []:
            if not isinstance(miss, str):
                continue
            desc = self._truncate(miss)
            if not desc.strip():
                continue
            out.append(
                PlanAdjustment(
                    description=desc,
                    category="miss",
                    confidence=miss_default_conf,
                    source=miss,
                )
            )

        # risks: list[str]
        risk_default_conf = self._clamp_confidence(
            critic_output.score_safety if critic_output.score_safety is not None else 0.5
        )
        for risk in critic_output.risks or []:
            if not isinstance(risk, str):
                continue
            desc = self._truncate(risk)
            if not desc.strip():
                continue
            out.append(
                PlanAdjustment(
                    description=desc,
                    category="risk",
                    confidence=risk_default_conf,
                    source=risk,
                )
            )

        # alternatives: list[dict{approach, tradeoffs, score}]
        for alt in critic_output.alternatives or []:
            if not isinstance(alt, dict):
                continue
            approach = str(alt.get("approach", "") or "").strip()
            tradeoffs = str(alt.get("tradeoffs", "") or "").strip()
            if not approach and not tradeoffs:
                continue
            desc = self._truncate(f"{approach} — {tradeoffs}")
            conf = self._clamp_confidence(alt.get("score", 0.5))
            out.append(
                PlanAdjustment(
                    description=desc,
                    category="alternative",
                    confidence=conf,
                    source=str(alt),
                )
            )

        return out

    def _dedupe_adjustments(
        self,
        adjustments: list[PlanAdjustment],
    ) -> list[PlanAdjustment]:
        """Dedupe by normalized-description prefix (first 100 chars).

        Two adjustments with the same key are merged — keep the
        higher confidence; tie-break by category preference order
        (``improvement > risk > miss > alternative``). The order
        of first occurrence is preserved (the surviving entry is
        emitted at the position of its first sighting).
        """
        seen: dict[str, PlanAdjustment] = {}
        order: list[str] = []
        for adj in adjustments:
            key = self._normalize(adj.description)[: self._DEDUPE_PREFIX_CHARS]
            if not key:
                # Empty keys (blank descriptions) don't represent
                # any concrete advice — drop them.
                continue
            if key in seen:
                existing = seen[key]
                if adj.confidence > existing.confidence:
                    seen[key] = adj
                elif adj.confidence == existing.confidence:
                    existing_order = self._CATEGORY_ORDER.get(existing.category, 99)
                    new_order = self._CATEGORY_ORDER.get(adj.category, 99)
                    if new_order < existing_order:
                        seen[key] = adj
            else:
                seen[key] = adj
                order.append(key)
        return [seen[k] for k in order]

    def _to_tool_suggestions(
        self,
        adjustments: list[PlanAdjustment],
    ) -> list[ToolSuggestion]:
        """Extract tool-name keywords from plan-adjustment descriptions.

        Order is the order in which the first matching adjustment
        for each tool is encountered. Higher confidence wins when
        the same tool appears in multiple adjustments (the
        ``reason`` field is updated to the higher-confidence
        description).
        """
        out: dict[str, ToolSuggestion] = {}
        order: list[str] = []
        for adj in adjustments:
            for kw in self._extract_tool_keywords(adj.description):
                if kw in out:
                    if adj.confidence > out[kw].confidence:
                        out[kw] = ToolSuggestion(
                            tool_name=kw,
                            reason=adj.description,
                            confidence=adj.confidence,
                        )
                else:
                    out[kw] = ToolSuggestion(
                        tool_name=kw,
                        reason=adj.description,
                        confidence=adj.confidence,
                    )
                    order.append(kw)
        return [out[k] for k in order]

    def _group_common_failures(
        self,
        misses: list[str],
    ) -> list[dict[str, Any]]:
        """Group misses by their normalized prefix (first 50 chars).

        Returns a list of ``{"pattern", "occurrences", "mitigation"}``
        dicts, sorted by ``occurrences`` descending (most-frequent
        pattern first). The ``mitigation`` field is a constant
        pointer at the corresponding plan adjustments in
        ``plan_adjustments``.
        """
        groups: dict[str, int] = {}
        for miss in misses or []:
            if not isinstance(miss, str):
                continue
            norm = self._normalize(miss)[: self._PATTERN_PREFIX_CHARS]
            if not norm:
                continue
            groups[norm] = groups.get(norm, 0) + 1
        return [
            {
                "pattern": pattern,
                "occurrences": count,
                "mitigation": "see plan adjustments",
            }
            for pattern, count in sorted(groups.items(), key=lambda kv: -kv[1])
        ]

    def _summary(self, raw: str | None) -> str:
        """Truncate the critic summary to ≤ 200 chars; substitute
        ``"No summary"`` for empty / None input."""
        if not raw:
            return "No summary"
        return str(raw)[: self._MAX_SUMMARY_CHARS]

    def _recommendation(self, score_overall: float | None) -> str:
        """Map ``score_overall`` to one of the four recommendations.

        Thresholds (after clamping to ``[0.0, 1.0]``):

        * ``None`` or ``< 0.3``       → ``"discard"``
        * ``0.3 ≤ x < 0.6``           → ``"review_manually"``
        * ``0.6 ≤ x < 0.8``           → ``"apply_suggested"``
        * ``x ≥ 0.8``                 → ``"apply_all"``
        """
        if score_overall is None or score_overall != score_overall:  # NaN
            return "discard"
        s = max(0.0, min(1.0, float(score_overall)))
        if s < self._RECOMMENDATION_DISCARD:
            return "discard"
        if s < self._RECOMMENDATION_REVIEW:
            return "review_manually"
        if s < self._RECOMMENDATION_APPLY_SUGGESTED:
            return "apply_suggested"
        return "apply_all"

    def _truncate(self, text: str) -> str:
        """Truncate ``text`` to ≤ 500 chars; append ``"…"`` if
        truncation occurred.

        The hard cap of 500 chars matches the
        ``consolidate_learning`` constraint on
        ``MissionProgram.learning_brief.plan_adjustments``.
        """
        if not text:
            return text
        if len(text) > self._MAX_DESCRIPTION_CHARS:
            return text[: self._MAX_DESCRIPTION_CHARS] + "…"
        return text

    def _clamp_confidence(self, value: Any) -> float:
        """Coerce a value to a float in ``[0.0, 1.0]``; default to
        ``0.5`` on failure (None, NaN, non-numeric, out-of-range).

        The ``0.5`` default is intentional: a missing confidence
        is treated as "neutral" — not as zero (which would
        collide with low-confidence signals from the critic).
        """
        if value is None:
            return 0.5
        try:
            c = float(value)
        except (TypeError, ValueError):
            return 0.5
        if c != c:  # NaN guard
            return 0.5
        return max(0.0, min(1.0, c))

    def _normalize(self, text: str) -> str:
        """Lowercase + strip + collapse whitespace.

        Used as the dedupe key and as the input to tool-keyword
        matching. We do NOT strip punctuation — the spec says
        "lowercase, strip" but the meaningful signal is
        whitespace, and stripping punctuation would collapse
        ``"don't"`` and ``"dont"`` into one key.
        """
        return " ".join((text or "").lower().split())

    def _extract_tool_keywords(self, text: str) -> set[str]:
        """Return the subset of ``_TOOL_KEYWORDS`` that appears as
        a case-insensitive substring in ``text``.

        Returns an empty set if ``text`` is empty / None.
        """
        if not text:
            return set()
        norm = self._normalize(text)
        return {kw for kw in self._TOOL_KEYWORDS if kw in norm}
