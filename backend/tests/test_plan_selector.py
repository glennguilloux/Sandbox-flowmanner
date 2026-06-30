"""Unit tests for app/services/plan_selection/plan_selector.py."""

import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.services.plan_selection.plan_candidate import PlanCandidate
from app.services.plan_selection.plan_selector import select_plan


def _make_candidate(
    plan_id: str,
    *,
    cost: float = 0.0,
    quality: float = 0.7,
    tasks: list | None = None,
) -> PlanCandidate:
    return PlanCandidate(
        plan_id=plan_id,
        generation_strategy="heuristic",
        tasks=tasks or [{"title": "T1", "task_type": "llm"}],
        estimated_cost_usd=cost,
        quality_score=quality,
    )


class TestSelectPlanAuto:
    """select_plan with policy='auto' (balanced)."""

    @pytest.mark.asyncio
    async def test_picks_highest_quality(self):
        a = _make_candidate("a", quality=0.5)
        b = _make_candidate("b", quality=0.9)
        c = _make_candidate("c", quality=0.7)

        winner, sorted_all = await select_plan([a, b, c], policy="auto", min_quality_threshold=0.0)
        assert winner.plan_id == "b"
        assert sorted_all[0].plan_id == "b"

    @pytest.mark.asyncio
    async def test_sorted_descending_by_quality(self):
        a = _make_candidate("a", quality=0.3)
        b = _make_candidate("b", quality=0.8)
        c = _make_candidate("c", quality=0.6)

        _, sorted_all = await select_plan([a, b, c], policy="auto", min_quality_threshold=0.0)
        scores = [c.quality_score for c in sorted_all]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_respects_quality_threshold(self):
        a = _make_candidate("a", quality=0.4)
        b = _make_candidate("b", quality=0.8)

        winner, _ = await select_plan([a, b], policy="auto", min_quality_threshold=0.6)
        # 'a' is below threshold, so 'b' wins even if 'a' were cheaper
        assert winner.plan_id == "b"

    @pytest.mark.asyncio
    async def test_falls_back_when_nothing_meets_threshold(self):
        a = _make_candidate("a", quality=0.3)
        b = _make_candidate("b", quality=0.4)

        winner, _ = await select_plan([a, b], policy="auto", min_quality_threshold=0.9)
        # Falls back to best overall
        assert winner.plan_id == "b"


class TestSelectPlanMinCost:
    """select_plan with policy='min_cost'."""

    @pytest.mark.asyncio
    async def test_picks_cheapest_among_eligible(self):
        a = _make_candidate("a", cost=0.10, quality=0.7)
        b = _make_candidate("b", cost=0.01, quality=0.8)
        c = _make_candidate("c", cost=0.05, quality=0.75)

        winner, _ = await select_plan([a, b, c], policy="min_cost", min_quality_threshold=0.6)
        assert winner.plan_id == "b"

    @pytest.mark.asyncio
    async def test_ignores_below_threshold_even_if_cheapest(self):
        a = _make_candidate("a", cost=0.001, quality=0.3)
        b = _make_candidate("b", cost=0.50, quality=0.9)

        winner, _ = await select_plan([a, b], policy="min_cost", min_quality_threshold=0.6)
        assert winner.plan_id == "b"


class TestSelectPlanMaxQuality:
    """select_plan with policy='max_quality'."""

    @pytest.mark.asyncio
    async def test_picks_highest_quality_regardless_of_cost(self):
        a = _make_candidate("a", cost=0.01, quality=0.6)
        b = _make_candidate("b", cost=1.00, quality=0.95)

        winner, _ = await select_plan([a, b], policy="max_quality", min_quality_threshold=0.5)
        assert winner.plan_id == "b"


class TestSelectPlanEdgeCases:
    """select_plan: edge cases."""

    @pytest.mark.asyncio
    async def test_single_candidate(self):
        a = _make_candidate("only", quality=0.5)
        winner, sorted_all = await select_plan([a], policy="auto", min_quality_threshold=0.0)
        assert winner.plan_id == "only"
        assert len(sorted_all) == 1

    @pytest.mark.asyncio
    async def test_empty_candidates_raises(self):
        with pytest.raises(ValueError, match="empty"):
            await select_plan([], policy="auto")

    @pytest.mark.asyncio
    async def test_unknown_policy_falls_back(self):
        a = _make_candidate("a", quality=0.8)
        winner, _ = await select_plan([a], policy="unknown_policy", min_quality_threshold=0.0)
        assert winner.plan_id == "a"
