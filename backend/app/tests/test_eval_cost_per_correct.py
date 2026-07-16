"""Comment 10: eval harness must capture cost-per-correct-answer.

We mock the budget enforcer (model call) and the LLM judge so no network is
touched, then assert per-case usage, run-level cost/correct aggregation, and
the candidate comparison ranking.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("LLM_API_KEY", "test-dummy-key")

from app.services.evaluation.eval_runner import EvaluationRunner


class _FakeEnforcer:
    def __init__(self, cost=0.01, provider="deepseek", model="deepseek-v4-flash"):
        self._cost = cost
        self._provider = provider
        self._model = model

    async def call_simple(self, **kwargs):
        return {
            "success": True,
            "response": "generated output for the case",
            "content": "generated output for the case",
            "model": kwargs.get("model_id"),
            "served_model": kwargs.get("model_id"),
            "provider": self._provider,
            "cost": {"input_tokens": 100, "output_tokens": 200, "usd": self._cost},
            "degraded": False,
        }


class _FakeJudge:
    def __init__(self, model=None, score=4.0, judge_model="gpt-4o"):
        self.model = model or judge_model
        self._default_score = score

    async def score(self, input_prompt="", **kwargs):
        # "prompt 3" is the deliberately-failing case (score 1.0 < threshold).
        score = 1.0 if input_prompt.strip().endswith("3") else self._default_score
        return {
            "scores": {"accuracy": {"score": score}},
            "overall_score": score,
            "summary": "ok",
        }


def _fake_judge(model=None, score=4.0, judge_model="gpt-4o", **kwargs):
    return _FakeJudge(model=model, score=score, judge_model=judge_model)


def _make_db_and_cases(n=3, threshold_passing=2):
    """Build a fake DB session + test cases; threshold_passing cases pass."""
    cases = []
    for i in range(n):
        score = 4.0 if i < threshold_passing else 1.0
        cases.append(
            SimpleNamespace(
                id=f"tc-{i}",
                task_type="code_generation" if i % 2 == 0 else "rag_accuracy",
                input_prompt=f"prompt {i}",
                expected_behavior="do the thing",
                rubric={"accuracy": 1.0},
            )
        )
    ds = SimpleNamespace(id="ds-1")
    run = SimpleNamespace(
        id="run-1",
        model_name="deepseek-v4-flash",
        model_config_hash="h",
        status="running",
        aggregate_score=None,
        scores_by_category=None,
        per_case_scores=None,
        total_cost_usd=None,
        total_latency_ms=None,
        routed_provider=None,
        judge_model=None,
        pass_rate=None,
        correct_count=None,
        completed_at=None,
        started_at=None,
        error_message=None,
    )

    async def _execute(stmt, **kw):
        class _R:
            def scalar_one_or_none(self_inner):
                return ds

            def scalars(self):
                return self

            def all(self):
                return cases

            def first(self):
                return cases[0] if cases else None

        return _R()

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db, run, cases


@pytest.mark.asyncio
async def test_run_captures_cost_and_correct():
    db, run, cases = _make_db_and_cases(n=4, threshold_passing=3)
    # Patch runner to use our fake run object + fake db.
    runner = EvaluationRunner(db)
    runner._run_cost_usd = 0.0
    runner._run_latency_ms = 0
    runner._run_correct = 0
    runner._run_providers = {}

    with (
        patch(
            "app.services.budget_enforcer.get_budget_enforcer", lambda: _FakeEnforcer(cost=0.02, provider="deepseek")
        ),
        patch("app.services.evaluation.eval_runner.LLMJudge", _fake_judge),
    ):
        result = await runner.run_evaluation("ds-1", model_name="deepseek-v4-flash", judge_model="gpt-4o")

    # The runner returns the ORM object it created; we assert on attributes.
    assert result.status == "completed"
    assert result.total_cost_usd is not None
    # 4 cases * 0.02 = 0.08
    assert abs(result.total_cost_usd - 0.08) < 1e-6
    assert result.correct_count == 3
    assert result.routed_provider == "deepseek"
    assert result.judge_model == "gpt-4o"
    # pass_rate = 3 / 4
    assert abs(result.pass_rate - 0.75) < 1e-6
    assert len(result.per_case_scores) == 4
    for c in result.per_case_scores:
        assert "correct" in c
        assert "cost_usd" in c
        assert "usage" in c


@pytest.mark.asyncio
async def test_compare_candidates_ranks_by_cost_per_correct():
    db, run, cases = _make_db_and_cases(n=2, threshold_passing=2)

    # Two candidates: cheap (local, $0) and expensive (opus, $5). Both pass all.
    class _ModelAwareEnforcer(_FakeEnforcer):
        async def call_simple(self, **kwargs):
            mid = kwargs.get("model_id")
            if mid == "claude-3-opus":
                cost, provider = 5.0, "anthropic"
            else:
                cost, provider = 0.0, "local"
            return {
                "success": True,
                "response": "generated output for the case",
                "content": "generated output for the case",
                "model": mid,
                "served_model": mid,
                "provider": provider,
                "cost": {"input_tokens": 100, "output_tokens": 200, "usd": cost},
                "degraded": False,
            }

    runner = EvaluationRunner(db)
    runner._run_cost_usd = 0.0
    runner._run_latency_ms = 0
    runner._run_correct = 0
    runner._run_providers = {}

    with (
        patch("app.services.budget_enforcer.get_budget_enforcer", lambda: _ModelAwareEnforcer()),
        patch("app.services.evaluation.eval_runner.LLMJudge", _fake_judge),
    ):
        comparison = await runner.compare_candidates(
            "ds-1", ["llamacpp-qwen3.6-27b", "claude-3-opus"], judge_model="gpt-4o"
        )

    assert comparison["candidate_count"] == 2
    # Cheap (cost per correct 0) must rank first.
    assert comparison["ranked_by_cost_per_correct"][0] == "llamacpp-qwen3.6-27b"
    models = {c["model"] for c in comparison["candidates"]}
    assert models == {"llamacpp-qwen3.6-27b", "claude-3-opus"}
