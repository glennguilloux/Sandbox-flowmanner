"""Tests for the evaluation system — models, services, API (sync + auth)."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.routing import APIRouter
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.evaluation import router as evaluation_router
from app.database import get_db
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


# ── Auth enforcement tests (P0 — lock down evaluation.py) ────────────────
#
# These build a focused FastAPI app with ONLY the evaluation router mounted
# so app startup is cheap and deterministic. Dependencies are overridden:
#   - get_db        → AsyncMock session (real object, mocked query methods)
#   - get_current_user → returns an injected user or raises 401 when
#     no token is supplied (mirrors the real dependency's 401 path).
# Service classes (DatasetBuilder / EvaluationRunner) are patched by their
# bound name inside app.api.v1.evaluation so the endpoints serialize real
# return values instead of blowing up on a MagicMock DB session.

AUTH_BASE = "/api/evaluation"

# Endpoint → (method, path, json-body / None). Every one of the 11
# previously-unauthenticated mutating endpoints must now 401 without auth.
MUTATING_ENDPOINTS = {
    "create_dataset": ("POST", "/datasets", {"name": "ds", "category": "code"}),
    "delete_dataset": ("DELETE", "/datasets/ds-1", None),
    "add_test_case": ("POST", "/datasets/ds-1/test-cases", {
        "input_prompt": "p", "expected_behavior": "b", "task_type": "general"}),
    "add_test_cases_bulk": ("POST", "/datasets/ds-1/test-cases/bulk", {
        "cases": [{"input_prompt": "p", "expected_behavior": "b", "task_type": "general"}]}),
    "update_test_case": ("PATCH", "/test-cases/tc-1", {"difficulty": "hard"}),
    "delete_test_case": ("DELETE", "/test-cases/tc-1", None),
    "run_evaluation": ("POST", "/runs", {"dataset_id": "ds-1"}),
    "compare_models": ("POST", "/compare", {"dataset_id": "ds-1", "model_a": "a", "model_b": "b"}),
    "import_from_langfuse": ("POST", "/import/langfuse", {
        "dataset_name": "ds", "traces": [{"input": "x", "output": "y"}]}),
    "create_dataset_from_template": ("POST", "/templates/code-review/create-dataset", None),
    "run_benchmark": ("POST", "/benchmarks", {"dataset_id": "ds-1", "models": ["a"]}),
}

# The two high-blast-radius endpoints — admin only (plain user → 403).
ADMIN_ONLY = {"import_from_langfuse", "run_benchmark"}


@pytest.fixture
def auth_app():
    """Focused app with the evaluation router mounted + deps overridden."""
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(evaluation_router)
    app.include_router(api)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        # Truthy sentinel so endpoints that look up a dataset (DELETE /datasets,
        # POST .../test-cases, etc.) don't raise 404 before reaching the mocked
        # service layer.
        scalar_one_or_none=MagicMock(return_value=MagicMock(id="ds-1")),
        scalar=MagicMock(return_value=None),
        first=MagicMock(return_value=None),
    ))

    # Authenticated user injected into the request context. When the box is
    # empty (no user injected) the override raises 401 — mirroring the real
    # get_current_user 401 path when no valid token is supplied.
    user_box: dict[str, object] = {}

    async def override_get_db():
        yield db

    async def override_get_current_user() -> MagicMock:
        u = user_box.get("user")
        if u is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return u

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    app.state._user_box = user_box
    return app


def _make_user(role: str = "user", is_admin: bool = False) -> MagicMock:
    return MagicMock(
        id=42,
        role=role,
        is_admin=is_admin,
        is_active=True,
        email="u@example.com",
    )


def _client(auth_app, user=None):
    """Return a TestClient with get_current_user resolving to `user` (or 401)."""
    auth_app.state._user_box["user"] = user
    return TestClient(auth_app)


def _request(client, method, path, json_body):
    fn = getattr(client, method.lower())
    kwargs = {}
    if json_body is not None:
        kwargs["json"] = json_body
    return fn(AUTH_BASE + path, **kwargs)


# ── 401 without auth ──────────────────────────────────────────────────────


@pytest.mark.parametrize("endpoint", list(MUTATING_ENDPOINTS))
def test_endpoint_requires_auth_401(endpoint, auth_app):
    """Every mutating evaluation endpoint must return 401 with no token."""
    method, path, body = MUTATING_ENDPOINTS[endpoint]
    client = _client(auth_app, user=None)  # get_current_user raises 401
    resp = _request(client, method, path, body)
    assert resp.status_code == 401, (
        f"{endpoint} returned {resp.status_code} (expected 401 without auth): {resp.text}"
    )


# ── 200/201 with a valid (non-admin) token ───────────────────────────────


@pytest.mark.parametrize("endpoint", [e for e in MUTATING_ENDPOINTS if e not in ADMIN_ONLY])
def test_endpoint_allows_authenticated_user(endpoint, auth_app):
    """The 9 non-admin endpoints return success for any authenticated user."""
    method, path, body = MUTATING_ENDPOINTS[endpoint]
    user = _make_user(role="user", is_admin=False)

    with patch("app.api.v1.evaluation.DatasetBuilder") as MockBuilder, patch(
        "app.api.v1.evaluation.EvaluationRunner"
    ) as MockRunner:
        # DatasetBuilder-backed endpoints.
        ds = MagicMock(id="ds-1", name="ds", category="code", version=1,
                       description="", created_at=None)
        tc = MagicMock(id="tc-1", task_type="general", difficulty="medium")
        builder = MockBuilder.return_value
        builder.create_dataset = AsyncMock(return_value=ds)
        builder.get_dataset = AsyncMock(return_value=ds)
        builder.add_test_case = AsyncMock(return_value=tc)
        builder.add_test_cases_bulk = AsyncMock(return_value=[tc])
        builder.update_test_case = AsyncMock(return_value=tc)
        builder.delete_test_case = AsyncMock(return_value=True)
        builder.import_from_langfuse_traces = AsyncMock(return_value=ds)

        # EvaluationRunner-backed endpoints.
        run = MagicMock(
            id="run-1", status="pending", model_name="m", aggregate_score=None,
            scores_by_category={}, started_at=None, completed_at=None,
            model_config_hash=None, per_case_scores=None, langfuse_trace_id=None,
            error_message=None,
        )
        runner = MockRunner.return_value
        runner.run_evaluation = AsyncMock(return_value=run)
        runner.compare_models = AsyncMock(return_value={"winner": "a"})

        client = _client(auth_app, user=user)
        resp = _request(client, method, path, body)
        assert resp.status_code in (200, 201), (
            f"{endpoint} returned {resp.status_code} for an authed user: {resp.text}"
        )


# ── admin-scoped endpoints ────────────────────────────────────────────────


@pytest.mark.parametrize("endpoint", list(ADMIN_ONLY))
def test_admin_endpoint_rejects_non_admin_403(endpoint, auth_app):
    """import_from_langfuse / run_benchmark must 403 for a non-admin user."""
    method, path, body = MUTATING_ENDPOINTS[endpoint]
    user = _make_user(role="user", is_admin=False)

    with patch("app.api.v1.evaluation.DatasetBuilder") as MockBuilder, patch(
        "app.api.v1.evaluation.EvaluationRunner"
    ) as MockRunner:
        ds = MagicMock(id="ds-1", name="ds", category="code", version=1,
                       description="", created_at=None)
        MockBuilder.return_value.import_from_langfuse_traces = AsyncMock(return_value=ds)
        run = MagicMock(id="run-1", status="pending", model_name="m", aggregate_score=None,
                        scores_by_category={}, started_at=None, completed_at=None)
        MockRunner.return_value.run_evaluation = AsyncMock(return_value=run)

        client = _client(auth_app, user=user)
        resp = _request(client, method, path, body)
        assert resp.status_code == 403, (
            f"{endpoint} returned {resp.status_code} for non-admin (expected 403): {resp.text}"
        )


@pytest.mark.parametrize("endpoint", list(ADMIN_ONLY))
def test_admin_endpoint_allows_admin(endpoint, auth_app):
    """import_from_langfuse / run_benchmark succeed for an admin user."""
    method, path, body = MUTATING_ENDPOINTS[endpoint]
    user = _make_user(role="admin", is_admin=True)

    with patch("app.api.v1.evaluation.DatasetBuilder") as MockBuilder, patch(
        "app.api.v1.evaluation.EvaluationRunner"
    ) as MockRunner:
        ds = MagicMock(id="ds-1", name="ds", category="code", version=1,
                       description="", created_at=None)
        MockBuilder.return_value.import_from_langfuse_traces = AsyncMock(return_value=ds)
        run = MagicMock(id="run-1", status="pending", model_name="m", aggregate_score=None,
                        scores_by_category={}, started_at=None, completed_at=None,
                        model_config_hash=None, per_case_scores=None, langfuse_trace_id=None,
                        error_message=None)
        runner = MockRunner.return_value
        runner.run_evaluation = AsyncMock(return_value=run)
        runner.compare_models = AsyncMock(return_value={"winner": "a"})

        client = _client(auth_app, user=user)
        resp = _request(client, method, path, body)
        assert resp.status_code in (200, 201), (
            f"{endpoint} returned {resp.status_code} for admin: {resp.text}"
        )
