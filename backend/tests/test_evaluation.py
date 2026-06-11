"""Tests for the evaluation system — models, services, API (sync only)."""

import json
from datetime import datetime, timezone

import pytest

from app.models.evaluation_models import EvalRun, GoldenDataset, GoldenTestCase

# ── Model tests ─────────────────────────────────────────────────────────


def test_golden_dataset_fields():
    ds = GoldenDataset(
        name="Test Dataset",
        category="code",
        description="A test",
        version=1,
    )
    assert ds.name == "Test Dataset"
    assert ds.category == "code"
    assert ds.version == 1


def test_golden_test_case_fields():
    tc = GoldenTestCase(
        dataset_id="fake-uuid",
        input_prompt="test prompt",
        expected_behavior="good output",
        task_type="code_generation",
        difficulty="medium",
        tags=["python"],
    )
    assert tc.input_prompt == "test prompt"
    assert tc.difficulty == "medium"
    assert tc.tags == ["python"]


def test_eval_run_fields():
    run = EvalRun(
        dataset_id="fake-uuid",
        model_name="deepseek/deepseek-v4-flash",
        model_config_hash="abc123",
        status="pending",
    )
    assert run.status == "pending"
    assert run.aggregate_score is None
    assert run.per_case_scores is None


# ── DatasetBuilder tests ────────────────────────────────────────────────


def test_dataset_builder_default_rubric():
    from app.services.evaluation.dataset_builder import DatasetBuilder

    rubric = DatasetBuilder._default_rubric()
    assert "criteria" in rubric
    assert "accuracy" in rubric["criteria"]
    assert rubric["criteria"]["accuracy"]["weight"] == 0.35
    assert rubric["scale"]["max"] == 5


def test_dataset_builder_config_hash():
    from app.services.evaluation.dataset_builder import DatasetBuilder

    hash1 = DatasetBuilder.compute_config_hash({"temp": 0.7, "model": "test"})
    hash2 = DatasetBuilder.compute_config_hash({"model": "test", "temp": 0.7})
    hash3 = DatasetBuilder.compute_config_hash({"temp": 0.8, "model": "test"})

    assert hash1 == hash2  # same content, different order = same hash
    assert hash1 != hash3  # different content = different hash
    assert len(hash1) == 16


# ── LLMJudge tests ──────────────────────────────────────────────────────


def test_llm_judge_build_user_message():
    from app.services.evaluation.llm_judge import LLMJudge

    msg = LLMJudge._build_user_message(
        input_prompt="Write hello world",
        expected_behavior="Prints hello world",
        actual_output="print('hello world')",
        rubric=LLMJudge._default_rubric(),
    )
    assert "Write hello world" in msg
    assert "Prints hello world" in msg
    assert "print('hello world')" in msg
    assert "accuracy" in msg


def test_llm_judge_parse_valid_json():
    from app.services.evaluation.llm_judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    raw = '{"scores": {"accuracy": {"score": 4, "reasoning": "good"}}, "overall_score": 4.0, "summary": "Well done"}'
    rubric = LLMJudge._default_rubric()

    result = judge._parse_response(raw, rubric)
    assert result["overall_score"] == 4.0
    assert result["summary"] == "Well done"


def test_llm_judge_parse_markdown_fenced_json():
    from app.services.evaluation.llm_judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    raw = '```json\n{"scores": {}, "overall_score": 0.0, "summary": "test"}\n```'
    rubric = LLMJudge._default_rubric()

    result = judge._parse_response(raw, rubric)
    assert result["overall_score"] == 0.0


def test_llm_judge_parse_invalid_json():
    from app.services.evaluation.llm_judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    rubric = LLMJudge._default_rubric()

    result = judge._parse_response("not json at all", rubric)
    assert result["overall_score"] == 0.0


def test_llm_judge_weighted_score_recalculation():
    from app.services.evaluation.llm_judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    raw = '{"scores": {"accuracy": {"score": 5}, "completeness": {"score": 3}, "relevance": {"score": 4}, "safety": {"score": 5}}, "overall_score": 0, "summary": "test"}'
    rubric = LLMJudge._default_rubric()

    result = judge._parse_response(raw, rubric)
    # weighted: 5*0.35 + 3*0.25 + 4*0.25 + 5*0.15 = 1.75 + 0.75 + 1.0 + 0.75 = 4.25
    assert result["overall_score"] == 4.25


def test_llm_judge_default_rubric():
    from app.services.evaluation.llm_judge import LLMJudge

    rubric = LLMJudge._default_rubric()
    assert "criteria" in rubric
    assert len(rubric["criteria"]) == 4
    assert rubric["scale"] == {"min": 1, "max": 5}


# ── EvalRunner tests ────────────────────────────────────────────────────


def test_eval_runner_config_hash():
    from app.services.evaluation.eval_runner import EvaluationRunner

    h1 = EvaluationRunner._compute_config_hash({"system_prompt": "test", "temperature": 0.7})
    h2 = EvaluationRunner._compute_config_hash({"temperature": 0.7, "system_prompt": "test"})
    assert h1 == h2


# ── Model relationship tests ────────────────────────────────────────────


def test_dataset_has_test_cases_relationship():
    ds = GoldenDataset(name="test", category="code")
    # Relationship attribute should exist
    assert hasattr(ds, "test_cases")
    assert hasattr(ds, "eval_runs")


def test_test_case_belongs_to_dataset():
    tc = GoldenTestCase(
        dataset_id="fake",
        input_prompt="test",
        expected_behavior="good",
        task_type="code_generation",
    )
    assert hasattr(tc, "dataset")


def test_eval_run_belongs_to_dataset():
    run = EvalRun(
        dataset_id="fake",
        model_name="test",
        model_config_hash="abc",
    )
    assert hasattr(run, "dataset")


# ── LLM Judge calibration tests ─────────────────────────────────────────


def test_judge_scoring_known_good_output():
    """Judge should give high scores to a correct, complete response."""
    from app.services.evaluation.llm_judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    # Simulate judge response for a perfect answer
    raw = json.dumps(
        {
            "scores": {
                "accuracy": {"score": 5, "reasoning": "Factually correct"},
                "completeness": {"score": 5, "reasoning": "Covers all aspects"},
                "relevance": {"score": 5, "reasoning": "Directly answers the question"},
                "safety": {"score": 5, "reasoning": "No harmful content"},
            },
            "overall_score": 5.0,
            "summary": "Excellent response",
        }
    )
    rubric = LLMJudge._default_rubric()
    result = judge._parse_response(raw, rubric)
    assert result["overall_score"] == 5.0
    assert result["summary"] == "Excellent response"


def test_judge_scoring_known_bad_output():
    """Judge should give low scores to an incorrect or harmful response."""
    from app.services.evaluation.llm_judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    raw = json.dumps(
        {
            "scores": {
                "accuracy": {"score": 1, "reasoning": "Completely wrong"},
                "completeness": {"score": 1, "reasoning": "Missing all required parts"},
                "relevance": {"score": 2, "reasoning": "Partially related"},
                "safety": {"score": 1, "reasoning": "Contains harmful advice"},
            },
            "overall_score": 1.0,
            "summary": "Dangerously incorrect response",
        }
    )
    rubric = LLMJudge._default_rubric()
    result = judge._parse_response(raw, rubric)
    # weighted: 1*0.35 + 1*0.25 + 2*0.25 + 1*0.15 = 1.25
    assert result["overall_score"] == 1.25
    assert result["summary"] == "Dangerously incorrect response"


def test_judge_scoring_mixed_output():
    """Judge should correctly weight mixed scores."""
    from app.services.evaluation.llm_judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    raw = json.dumps(
        {
            "scores": {
                "accuracy": {"score": 4, "reasoning": "Mostly correct"},
                "completeness": {"score": 3, "reasoning": "Some gaps"},
                "relevance": {"score": 5, "reasoning": "Directly answers"},
                "safety": {"score": 4, "reasoning": "Minor concerns"},
            },
            "overall_score": 0,  # will be recalculated
            "summary": "Good but incomplete",
        }
    )
    rubric = LLMJudge._default_rubric()
    result = judge._parse_response(raw, rubric)
    # weighted: 4*0.35 + 3*0.25 + 5*0.25 + 4*0.15 = 1.4 + 0.75 + 1.25 + 0.6 = 4.0
    assert result["overall_score"] == 4.0


def test_judge_scoring_custom_rubric():
    """Judge should handle custom rubrics correctly."""
    from app.services.evaluation.llm_judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    custom_rubric = {
        "criteria": {
            "speed": {"weight": 0.5, "description": "Fast response"},
            "accuracy": {"weight": 0.5, "description": "Correct answer"},
        },
        "scale": {"min": 1, "max": 5},
    }
    raw = json.dumps(
        {
            "scores": {
                "speed": {"score": 3, "reasoning": "Moderate speed"},
                "accuracy": {"score": 5, "reasoning": "Perfect answer"},
            },
            "overall_score": 0,
            "summary": "Accurate but slow",
        }
    )
    result = judge._parse_response(raw, custom_rubric)
    # weighted: 3*0.5 + 5*0.5 = 1.5 + 2.5 = 4.0
    assert result["overall_score"] == 4.0


def test_judge_scoring_missing_criterion():
    """Judge should handle missing criteria gracefully."""
    from app.services.evaluation.llm_judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    raw = json.dumps(
        {
            "scores": {
                "accuracy": {"score": 4, "reasoning": "Good"},
                # missing: completeness, relevance, safety
            },
            "overall_score": 0,
            "summary": "Partial scoring",
        }
    )
    rubric = LLMJudge._default_rubric()
    result = judge._parse_response(raw, rubric)
    # Only accuracy scored: 4 * 0.35 / 0.35 = 4.0 (normalized by actual weight sum)
    assert result["overall_score"] == 4.0


def test_judge_malformed_score_clamped():
    """Judge should handle out-of-range scores without crashing."""
    from app.services.evaluation.llm_judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    raw = json.dumps(
        {
            "scores": {
                "accuracy": {"score": 10, "reasoning": "Gave 10 somehow"},
                "completeness": {"score": 0, "reasoning": "Gave 0"},
            },
            "overall_score": 5.0,
            "summary": "Out of range scores",
        }
    )
    rubric = LLMJudge._default_rubric()
    result = judge._parse_response(raw, rubric)
    # Should not crash, recalculated with raw values
    assert "overall_score" in result


def test_judge_empty_response():
    """Judge should handle completely empty response."""
    from app.services.evaluation.llm_judge import LLMJudge

    judge = LLMJudge.__new__(LLMJudge)
    rubric = LLMJudge._default_rubric()
    result = judge._parse_response("{}", rubric)
    assert result["overall_score"] == 0.0
    assert result["scores"] == {}
    assert result["summary"] == ""
