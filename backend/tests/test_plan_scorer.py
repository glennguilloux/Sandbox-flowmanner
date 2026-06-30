"""Unit tests for app/services/plan_selection/plan_scorer.py."""

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.services.plan_selection.plan_candidate import PlanCandidate
from app.services.plan_selection.plan_scorer import (
    detect_risk_flags,
    estimate_latency_ms,
    estimate_tokens_for_tasks,
    score_plan,
)


class TestEstimateTokensForTasks:
    """estimate_tokens_for_tasks: deterministic token estimation."""

    def test_single_llm_task(self):
        tasks = [{"title": "T1", "task_type": "llm", "description": "Do something"}]
        tokens = estimate_tokens_for_tasks(tasks)
        # base 1200 + desc_bonus (len("Do something")=12 → 1)
        assert tokens == 1201

    def test_multiple_task_types(self):
        tasks = [
            {"task_type": "llm", "description": ""},
            {"task_type": "tool", "description": ""},
            {"task_type": "code", "description": ""},
        ]
        tokens = estimate_tokens_for_tasks(tasks)
        assert tokens == 1200 + 400 + 1500  # base tokens only (empty desc)

    def test_long_description_adds_bonus(self):
        tasks = [{"task_type": "llm", "description": "x" * 5000}]
        tokens = estimate_tokens_for_tasks(tasks)
        # base 1200 + min(5000//10, 500) = 1200 + 500
        assert tokens == 1700

    def test_unknown_task_type_defaults(self):
        tasks = [{"task_type": "unknown_type", "description": ""}]
        tokens = estimate_tokens_for_tasks(tasks)
        assert tokens == 800  # default

    def test_empty_tasks(self):
        assert estimate_tokens_for_tasks([]) == 0


class TestEstimateLatencyMs:
    """estimate_latency_ms: deterministic latency estimation."""

    def test_single_task_no_deps(self):
        tasks = [{"task_type": "llm", "dependencies": []}]
        assert estimate_latency_ms(tasks) == 2000

    def test_task_with_dependencies(self):
        tasks = [
            {"task_type": "llm", "dependencies": []},
            {"task_type": "tool", "dependencies": [0]},
        ]
        # 2000 + (2000 + 500) = 4500
        assert estimate_latency_ms(tasks) == 4500

    def test_empty_tasks(self):
        assert estimate_latency_ms([]) == 0


class TestDetectRiskFlags:
    """detect_risk_flags: risk flag detection from task structure."""

    def test_no_fallback_on_tool_task(self):
        tasks = [{"task_type": "tool", "description": "search"}]
        flags = detect_risk_flags(tasks)
        assert "no_fallback" in flags

    def test_no_flag_when_fallback_present(self):
        tasks = [{"task_type": "tool", "fallback": "use_cache"}]
        flags = detect_risk_flags(tasks)
        assert "no_fallback" not in flags

    def test_human_input_blocking(self):
        tasks = [{"task_type": "llm", "approval_required": True}]
        flags = detect_risk_flags(tasks)
        assert "human_input_blocking" in flags

    def test_unbounded_retry(self):
        tasks = [{"task_type": "llm", "max_retries": 100}]
        flags = detect_risk_flags(tasks)
        assert "unbounded_retry" in flags

    def test_normal_retries_no_flag(self):
        tasks = [{"task_type": "llm", "max_retries": 3}]
        flags = detect_risk_flags(tasks)
        assert "unbounded_retry" not in flags

    def test_empty_tasks(self):
        assert detect_risk_flags([]) == []


class TestScorePlan:
    """score_plan: deterministic heuristic scoring."""

    def test_score_in_range(self):
        cand = PlanCandidate(plan_id="test", generation_strategy="heuristic", tasks=[])
        score = score_plan(cand)
        assert 0.0 <= score <= 1.0

    def test_lower_cost_higher_score(self):
        cheap = PlanCandidate(
            plan_id="cheap",
            generation_strategy="heuristic",
            tasks=[],
            estimated_cost_usd=0.0,
        )
        expensive = PlanCandidate(
            plan_id="expensive",
            generation_strategy="llm_persona",
            tasks=[],
            estimated_cost_usd=0.50,
        )
        assert score_plan(cheap) > score_plan(expensive)

    def test_risk_flags_penalize(self):
        no_risk = PlanCandidate(
            plan_id="safe",
            generation_strategy="heuristic",
            tasks=[{"task_type": "llm", "fallback": "ok"}],
            risk_flags=[],
        )
        risky = PlanCandidate(
            plan_id="risky",
            generation_strategy="heuristic",
            tasks=[{"task_type": "llm", "fallback": "ok"}],
            risk_flags=["unbounded_retry", "no_fallback", "human_input_blocking"],
        )
        assert score_plan(no_risk) > score_plan(risky)

    def test_fewer_tasks_slightly_better(self):
        few = PlanCandidate(
            plan_id="few",
            generation_strategy="heuristic",
            tasks=[{"task_type": "llm"}],
        )
        many = PlanCandidate(
            plan_id="many",
            generation_strategy="heuristic",
            tasks=[{"task_type": "llm"}] * 10,
        )
        assert score_plan(few) > score_plan(many)

    def test_fallback_bonus_for_tool_tasks(self):
        with_fallback = PlanCandidate(
            plan_id="fb",
            generation_strategy="heuristic",
            tasks=[{"task_type": "tool", "fallback": "cache"}],
        )
        without_fallback = PlanCandidate(
            plan_id="nofb",
            generation_strategy="heuristic",
            tasks=[{"task_type": "tool"}],
        )
        assert score_plan(with_fallback) > score_plan(without_fallback)

    def test_budget_awareness_bonus(self):
        with_budget = PlanCandidate(
            plan_id="aware",
            generation_strategy="heuristic",
            tasks=[{"task_type": "llm", "max_budget": 5.0}],
        )
        without_budget = PlanCandidate(
            plan_id="unaware",
            generation_strategy="heuristic",
            tasks=[{"task_type": "llm"}],
        )
        assert score_plan(with_budget) > score_plan(without_budget)
