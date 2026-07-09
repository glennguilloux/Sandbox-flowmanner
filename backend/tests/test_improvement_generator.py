"""TDD tests for ImprovementGenerator (D30-60, T26).

The :class:`ImprovementGenerator` is a **pure-logic** transformer that
takes a :class:`CriticOutput` (from T25) + a :class:`MissionContext`
and emits an :class:`ImprovementBatch` of concrete, actionable
adjustments that T27 can merge into a ``MissionProgram.learning_brief``.

Key invariants under test:

* **No LLM call, no DB write, no async.** All public methods are sync
  pure functions. Calling ``.generate()`` twice with the same input
  must return equal output (determinism).
* **No ``db.commit()`` / no ``db.execute()`` / no AsyncSession.** The
  module is side-effect free.
* **All dataclasses have sensible defaults** so ``ImprovementBatch()``
  works with no args.
* **The class is decoupled from the HTTP layer** — no ``app.api.*``
  imports.
* **Score clamping + recommendation thresholds** match the spec.
* **Tool-keyword extraction** works on improvement/alternative
  descriptions.
* **Common-failure grouping** groups misses by their first 50 chars.
* **Description truncation** keeps descriptions within ~500 chars.

Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_improvement_generator.py -v
"""

from __future__ import annotations

import os
from typing import Any

# Set DATABASE_URL BEFORE importing app modules that need it.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner",
)

import pytest

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _ctx() -> Any:
    """A reasonable MissionContext payload for the tests."""
    from app.services.improvement_generator import MissionContext

    return MissionContext(
        mission_id="m-1",
        goal="Refactor the auth module to use OIDC.",
        plan={"tasks": [{"id": "t1", "type": "code"}]},
        outcome={"status": "completed", "tasks_completed": 1, "tasks_failed": 0},
        user_id=1,
        workspace_id="ws-1",
    )


# ═══════════════════════════════════════════════════════════════════════════
# (A) Dataclass shape & construction
# ═══════════════════════════════════════════════════════════════════════════


class TestDataclasses:
    """Validate the four public dataclasses (ToolSuggestion,
    PlanAdjustment, MissionContext, ImprovementBatch)."""

    def test_improvement_batch_defaults(self) -> None:
        """ImprovementBatch() with no args returns sensible defaults."""
        from app.services.improvement_generator import ImprovementBatch

        batch = ImprovementBatch()
        # All list fields default to empty lists (not None).
        assert batch.plan_adjustments == []
        assert batch.tool_suggestions == []
        assert batch.common_failure_patterns == []
        # Summary is the empty string; the *generator* fills in
        # "No summary" when the input is empty.
        assert batch.summary == ""
        # overall_recommendation is a safe middle default — the
        # generator overrides it based on score_overall.
        assert isinstance(batch.overall_recommendation, str)
        assert batch.overall_recommendation != ""

    def test_tool_suggestion_dataclass(self) -> None:
        """ToolSuggestion has the documented fields and they take values."""
        from app.services.improvement_generator import ToolSuggestion

        s = ToolSuggestion(
            tool_name="browser",
            reason="Visit the upstream docs to confirm config syntax.",
            confidence=0.7,
        )
        assert s.tool_name == "browser"
        assert "upstream docs" in s.reason
        assert s.confidence == 0.7

    def test_plan_adjustment_dataclass(self) -> None:
        """PlanAdjustment has the documented fields."""
        from app.services.improvement_generator import PlanAdjustment

        pa = PlanAdjustment(
            description="Add a rollback task before deploy.",
            category="improvement",
            confidence=0.85,
            source="Add a rollback task before deploy.",
        )
        assert pa.description == "Add a rollback task before deploy."
        assert pa.category == "improvement"
        assert pa.confidence == 0.85
        assert pa.source == "Add a rollback task before deploy."

    def test_mission_context_dataclass(self) -> None:
        """MissionContext has the documented fields."""
        from app.services.improvement_generator import MissionContext

        ctx = MissionContext(
            mission_id="m-1",
            goal="g",
            plan={"tasks": ["t1"]},
            outcome={"status": "ok"},
            user_id=42,
            workspace_id="ws-1",
        )
        assert ctx.mission_id == "m-1"
        assert ctx.goal == "g"
        assert ctx.plan == {"tasks": ["t1"]}
        assert ctx.outcome == {"status": "ok"}
        assert ctx.user_id == 42
        assert ctx.workspace_id == "ws-1"

    def test_module_exports_required_symbols(self) -> None:
        """The four public symbols are importable in isolation."""
        from app.services.improvement_generator import (
            ImprovementBatch,
            ImprovementGenerator,
            MissionContext,
            PlanAdjustment,
            ToolSuggestion,
        )

        assert ImprovementGenerator is not None
        assert ImprovementBatch is not None
        assert PlanAdjustment is not None
        assert ToolSuggestion is not None
        assert MissionContext is not None

    def test_improvement_generator_constructable_no_args(self) -> None:
        """ImprovementGenerator() works with no args."""
        from app.services.improvement_generator import ImprovementGenerator

        g = ImprovementGenerator()
        assert g is not None

    def test_improvement_generator_constructable_with_threshold(self) -> None:
        """ImprovementGenerator(min_confidence_threshold=...) works."""
        from app.services.improvement_generator import ImprovementGenerator

        g = ImprovementGenerator(min_confidence_threshold=0.5)
        assert g.min_confidence_threshold == 0.5


# ═══════════════════════════════════════════════════════════════════════════
# (B) Recommendation thresholds
# ═══════════════════════════════════════════════════════════════════════════


class TestRecommendation:
    """Validate the score_overall → overall_recommendation mapping."""

    def test_generate_recommendation_discard_when_score_none(self) -> None:
        """score_overall=None → 'discard'."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        batch = gen.generate(CriticOutput(score_overall=None), _ctx())
        assert batch.overall_recommendation == "discard"

    def test_generate_recommendation_discard_when_score_low(self) -> None:
        """score_overall=0.1 → 'discard' (below 0.3)."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        batch = gen.generate(CriticOutput(score_overall=0.1), _ctx())
        assert batch.overall_recommendation == "discard"

    def test_generate_recommendation_review_manually_when_score_mid(self) -> None:
        """score_overall=0.4 → 'review_manually' (0.3–0.6)."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        batch = gen.generate(CriticOutput(score_overall=0.4), _ctx())
        assert batch.overall_recommendation == "review_manually"

    def test_generate_recommendation_apply_suggested_when_score_high(self) -> None:
        """score_overall=0.7 → 'apply_suggested' (0.6–0.8)."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        batch = gen.generate(CriticOutput(score_overall=0.7), _ctx())
        assert batch.overall_recommendation == "apply_suggested"

    def test_generate_recommendation_apply_all_when_score_very_high(self) -> None:
        """score_overall=0.85 → 'apply_all' (>= 0.8)."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        batch = gen.generate(CriticOutput(score_overall=0.85), _ctx())
        assert batch.overall_recommendation == "apply_all"


# ═══════════════════════════════════════════════════════════════════════════
# (C) Plan adjustments from each critic field
# ═══════════════════════════════════════════════════════════════════════════


class TestPlanAdjustments:
    """Validate that improvements/misses/risks/alternatives become
    PlanAdjustments with the right category."""

    def test_generate_plan_adjustments_from_improvements(self) -> None:
        """improvements=[{description, confidence:0.8}] → 1 improvement."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        critic = CriticOutput(
            score_overall=0.8,
            improvements=[{"description": "Add a rollback task.", "confidence": 0.8}],
        )
        batch = gen.generate(critic, _ctx())
        assert len(batch.plan_adjustments) == 1
        adj = batch.plan_adjustments[0]
        assert adj.category == "improvement"
        assert adj.description == "Add a rollback task."
        assert adj.confidence == 0.8

    def test_generate_plan_adjustments_from_misses(self) -> None:
        """misses=['did not check X'] → 1 miss."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        critic = CriticOutput(
            score_overall=0.6,
            misses=["did not check X"],
        )
        batch = gen.generate(critic, _ctx())
        assert len(batch.plan_adjustments) == 1
        adj = batch.plan_adjustments[0]
        assert adj.category == "miss"
        assert "did not check X" in adj.description

    def test_generate_plan_adjustments_from_risks(self) -> None:
        """risks=['race condition in Y'] → 1 risk."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        critic = CriticOutput(
            score_overall=0.6,
            score_safety=0.5,
            risks=["race condition in Y"],
        )
        batch = gen.generate(critic, _ctx())
        assert len(batch.plan_adjustments) == 1
        adj = batch.plan_adjustments[0]
        assert adj.category == "risk"
        assert "race condition" in adj.description

    def test_generate_plan_adjustments_from_alternatives(self) -> None:
        """alternatives=[{approach, tradeoffs, score:0.7}] → 1 alternative."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        critic = CriticOutput(
            score_overall=0.7,
            alternatives=[
                {
                    "approach": "use feature flag",
                    "tradeoffs": "added complexity",
                    "score": 0.7,
                }
            ],
        )
        batch = gen.generate(critic, _ctx())
        assert len(batch.plan_adjustments) == 1
        adj = batch.plan_adjustments[0]
        assert adj.category == "alternative"
        assert "feature flag" in adj.description
        assert "added complexity" in adj.description
        assert adj.confidence == 0.7


# ═══════════════════════════════════════════════════════════════════════════
# (D) Dedupe, truncation, summary
# ═══════════════════════════════════════════════════════════════════════════


class TestDedupeAndTruncation:
    """Validate dedupe-by-description, description truncation,
    and summary truncation."""

    def test_generate_dedupes_similar_adjustments(self) -> None:
        """Two improvements with the same description + different
        confidences → 1 entry with the higher confidence."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        critic = CriticOutput(
            score_overall=0.7,
            improvements=[
                {"description": "Use feature flag", "confidence": 0.5},
                {"description": "Use feature flag", "confidence": 0.9},
            ],
        )
        batch = gen.generate(critic, _ctx())
        assert len(batch.plan_adjustments) == 1
        assert batch.plan_adjustments[0].confidence == 0.9

    def test_generate_truncates_long_descriptions(self) -> None:
        """Description > 500 chars → truncated (length < 600)."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        long_desc = "x" * 600
        gen = ImprovementGenerator()
        critic = CriticOutput(
            score_overall=0.7,
            improvements=[{"description": long_desc, "confidence": 0.5}],
        )
        batch = gen.generate(critic, _ctx())
        assert len(batch.plan_adjustments) == 1
        # The original was 600 chars; the result must be shorter.
        assert len(batch.plan_adjustments[0].description) < 600
        # And it must start with the original prefix.
        assert batch.plan_adjustments[0].description.startswith("x" * 100)

    def test_generate_summary_truncates_to_200(self) -> None:
        """summary with 500 chars → truncated to ≤ 200 chars."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        long_summary = "a" * 500
        gen = ImprovementGenerator()
        critic = CriticOutput(score_overall=0.7, summary=long_summary)
        batch = gen.generate(critic, _ctx())
        assert len(batch.summary) <= 200
        # It starts with the original prefix.
        assert batch.summary.startswith("a" * 50)

    def test_generate_summary_handles_empty(self) -> None:
        """empty summary → 'No summary'."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        # CriticOutput defaults summary to None.
        critic = CriticOutput(score_overall=0.7, summary=None)
        batch = gen.generate(critic, _ctx())
        assert batch.summary == "No summary"

        # Also handles empty string.
        critic2 = CriticOutput(score_overall=0.7, summary="")
        batch2 = gen.generate(critic2, _ctx())
        assert batch2.summary == "No summary"


# ═══════════════════════════════════════════════════════════════════════════
# (E) Tool-suggestion extraction
# ═══════════════════════════════════════════════════════════════════════════


class TestToolSuggestions:
    """Validate tool-keyword extraction from descriptions."""

    def test_generate_tool_suggestions_extract_keywords(self) -> None:
        """An improvement mentioning 'browser' → 1 ToolSuggestion."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        critic = CriticOutput(
            score_overall=0.7,
            improvements=[
                {
                    "description": "Use the browser to verify the page renders correctly.",
                    "confidence": 0.8,
                }
            ],
        )
        batch = gen.generate(critic, _ctx())
        # At least one tool suggestion contains "browser".
        assert len(batch.tool_suggestions) >= 1
        names = [s.tool_name for s in batch.tool_suggestions]
        assert "browser" in names

    def test_generate_tool_suggestions_handles_unknown_tool(self) -> None:
        """An improvement mentioning 'unicorn_tool' → no ToolSuggestion."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        critic = CriticOutput(
            score_overall=0.7,
            improvements=[
                {
                    "description": "Use the unicorn_tool to frobnicate the widgets.",
                    "confidence": 0.8,
                }
            ],
        )
        batch = gen.generate(critic, _ctx())
        assert batch.tool_suggestions == []


# ═══════════════════════════════════════════════════════════════════════════
# (F) Common-failure grouping
# ═══════════════════════════════════════════════════════════════════════════


class TestCommonFailures:
    """Validate common-failure pattern grouping."""

    def test_generate_common_failure_patterns_groups_misses(self) -> None:
        """misses that share a 50-char prefix are grouped into one pattern."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        # The first two misses share the first 50 chars of their
        # normalized text ("failed to connect to upstream auth service on
        # retry"), so they should be grouped. The third miss differs in
        # the first 50 chars and is its own group.
        critic = CriticOutput(
            score_overall=0.6,
            misses=[
                "Failed to connect to upstream auth service on retry 1",
                "Failed to connect to upstream auth service on retry 2",
                "Timeout exceeded while waiting for the worker pool to start",
            ],
        )
        batch = gen.generate(critic, _ctx())
        # 3 misses → 2 groups (the "Failed to connect..." group has 2,
        # the "Timeout exceeded..." group has 1).
        assert len(batch.common_failure_patterns) == 2
        # Each group has the documented fields.
        for pattern in batch.common_failure_patterns:
            assert "pattern" in pattern
            assert "occurrences" in pattern
            assert "mitigation" in pattern
        # The "Failed to connect..." group has 2 occurrences and is
        # sorted first (highest count).
        assert batch.common_failure_patterns[0]["occurrences"] == 2
        assert "failed to connect" in batch.common_failure_patterns[0]["pattern"]
        assert batch.common_failure_patterns[1]["occurrences"] == 1
        assert "timeout exceeded" in batch.common_failure_patterns[1]["pattern"]


# ═══════════════════════════════════════════════════════════════════════════
# (G) Edge cases — empty input, determinism, score clamping
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Validate the hard edge cases listed in the T26 spec."""

    def test_generate_returns_improvement_batch(self) -> None:
        """Minimum input (empty CriticOutput) returns an ImprovementBatch."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import (
            ImprovementBatch,
            ImprovementGenerator,
        )

        gen = ImprovementGenerator()
        critic = CriticOutput(score_overall=0.5, summary="ok")
        batch = gen.generate(critic, _ctx())
        assert isinstance(batch, ImprovementBatch)

    def test_generate_handles_empty_critic_output(self) -> None:
        """All-empty CriticOutput → empty lists + 'discard' + 'No summary'."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        # CriticOutput() with no args → all defaults (None / []).
        batch = gen.generate(CriticOutput(), _ctx())
        assert batch.plan_adjustments == []
        assert batch.tool_suggestions == []
        assert batch.common_failure_patterns == []
        assert batch.overall_recommendation == "discard"
        assert batch.summary == "No summary"

    def test_generate_pure_no_side_effects(self) -> None:
        """Calling .generate() twice with the same input returns equal
        output (deterministic; no side effects on the input)."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        critic = CriticOutput(
            score_overall=0.7,
            summary="plan looks good",
            misses=["miss A"],
            risks=["risk A"],
            improvements=[{"description": "improve A", "confidence": 0.6}],
            alternatives=[{"approach": "alt A", "tradeoffs": "t", "score": 0.5}],
        )
        ctx = _ctx()
        # Snapshot the input so we can prove the generator didn't mutate it.
        snapshot_score = critic.score_overall
        snapshot_misses = list(critic.misses)
        snapshot_plan = dict(ctx.plan)

        batch1 = gen.generate(critic, ctx)
        batch2 = gen.generate(critic, ctx)

        # Input was not mutated.
        assert critic.score_overall == snapshot_score
        assert critic.misses == snapshot_misses
        assert ctx.plan == snapshot_plan
        # Two calls produced equal output.
        assert batch1 == batch2

    def test_score_clamping(self) -> None:
        """A score_overall=1.5 is clamped to 1.0 → 'apply_all'."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        critic = CriticOutput(score_overall=1.5)
        batch = gen.generate(critic, _ctx())
        # 1.5 → clamp to 1.0 → ≥ 0.8 → "apply_all"
        assert batch.overall_recommendation == "apply_all"

    def test_negative_score_clamped(self) -> None:
        """A score_overall=-0.5 is clamped to 0.0 → 'discard'."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        critic = CriticOutput(score_overall=-0.5)
        batch = gen.generate(critic, _ctx())
        # -0.5 → clamp to 0.0 → < 0.3 → "discard"
        assert batch.overall_recommendation == "discard"

    def test_confidence_default_when_missing(self) -> None:
        """An improvement dict without a 'confidence' key defaults to 0.5."""
        from app.services.critic import CriticOutput
        from app.services.improvement_generator import ImprovementGenerator

        gen = ImprovementGenerator()
        critic = CriticOutput(
            score_overall=0.7,
            improvements=[{"description": "no confidence key"}],
        )
        batch = gen.generate(critic, _ctx())
        assert len(batch.plan_adjustments) == 1
        assert batch.plan_adjustments[0].confidence == 0.5

    def test_no_db_access(self) -> None:
        """The module does not import AsyncSession and does not call
        any database write operation (spec §T26 tight rule)."""
        import re

        import app.services.improvement_generator as mod

        source = open(mod.__file__).read()
        # TIGHT RULE: no DB access in this module. These patterns
        # match the spec's grep verification (`db.commit`, `db.execute`,
        # `async with engine`) and an explicit AsyncSession import.
        for forbidden in (
            "AsyncSession",
            "db.commit",
            "db.execute",
            "async with engine",
        ):
            assert forbidden not in source, f"Spec §T26 violation: {forbidden!r} found in " f"{mod.__file__}"
        # AST-level check: no ImportFrom/Import mentions AsyncSession.
        import ast

        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "AsyncSession" not in alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert "AsyncSession" not in node.module
                for alias in node.names:
                    assert "AsyncSession" not in alias.name

    def test_no_fstring_in_logger(self) -> None:
        """No logger call uses an f-string (project rule)."""
        import re

        import app.services.improvement_generator as mod

        source = open(mod.__file__).read()
        # The spec allows the module to log nothing — but if it does,
        # the logger calls must use parameterised formatting.
        # The pattern `logger.<method>(f"` catches the violation.
        fstring_in_logger = re.findall(r"logger\.\w+\(f[\"']", source)
        assert fstring_in_logger == [], f"Found f-strings in logger calls: {fstring_in_logger}"
