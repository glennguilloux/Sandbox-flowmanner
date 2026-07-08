"""Tests for BudgetEnforcer.call() — local-model fallback gating.

Regression coverage for the silent-model-substitution bug: a failed
cloud/BYOK primary route must NOT be silently swapped for the local
llama.cpp model while reporting success=True.

Setup notes:
- Circuit breaker is bypassed by passing db_session=None, workspace_id=None
  (the CB branch only runs when all three of cb_enabled/db_session/workspace_id
  are truthy).
- ModelRouter is imported inside call(), so we patch the class method.
- The local httpx fallback hits the network; we monkeypatch
  BudgetEnforcer._local_llamacpp_fallback to avoid real calls.
"""

import os

# chat_service (imported transitively by llm_router -> budget_enforcer) builds
# a module-level AsyncOpenAI client at import time, which raises on missing
# credentials. Existing router tests set a dummy key first.
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.capability_models import Budget
from app.services.budget_enforcer import BudgetEnforcer, _is_local_model


def _make_budget() -> Budget:
    return Budget(max_cost_usd=Decimal("10.00"))


FAKE_FALLBACK_RESPONSE = {
    "success": True,
    "response": "local-model-output",
    "model": "llamacpp/qwen3.6-27b",
    "provider": "llamacpp",
    "cost": {"input_tokens": 1, "output_tokens": 1},
    "substituted_from": None,
}


class _FakeRouter:
    """Stand-in for ModelRouter that never constructs a real AsyncOpenAI
    client (which would raise on missing credentials at import time).
    route_request's behaviour is controlled per-test via the class attr."""

    route_error: Any = None  # set per-test

    def __init__(self, *args, **kwargs):
        pass

    async def route_request(self, *args, **kwargs):
        if self.route_error is not None:
            raise self.route_error
        return {
            "success": True,
            "response": "ok",
            "model": "x",
            "provider": "deepseek",
            "cost": {"input_tokens": 1, "output_tokens": 1},
        }


class TestIsLocalModel:
    def test_local_prefixes(self):
        assert _is_local_model("llamacpp/qwen3.6-27b") is True
        assert _is_local_model("local/foo") is True
        assert _is_local_model("ollama/llama3") is True

    def test_cloud_prefixes(self):
        assert _is_local_model("openai/gpt-4o") is False
        assert _is_local_model("deepseek-chat") is False
        assert _is_local_model("anthropic/claude-3-5-sonnet") is False

    def test_none_and_empty(self):
        assert _is_local_model(None) is False
        assert _is_local_model("") is False


class TestFallbackGating:
    async def test_failed_cloud_model_is_not_silent_success(self):
        """RC2-residual: a cloud/BYOK model whose primary route fails must
        surface success=False, NOT a silent llama.cpp success."""
        _FakeRouter.route_error = RuntimeError("BYOK key rejected")
        enforcer = BudgetEnforcer()

        with patch("app.services.llm_router.ModelRouter", new=_FakeRouter):
            result = await enforcer.call(
                budget=_make_budget(),
                model_id="openai/gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                user_id="user-1",
                # Default: allow_fallback=False, non-local model.
            )

        assert result["success"] is False, "failed cloud model must not become success"
        assert result["provider"] != "llamacpp"
        assert "BYOK key rejected" in (result.get("error") or "")

    async def test_failed_cloud_model_without_fallback_raises_to_caller(self):
        """The inner router failure is re-raised so the outer handler records
        a real failure (no local substitution)."""
        _FakeRouter.route_error = ValueError("No models available")
        enforcer = BudgetEnforcer()

        with patch("app.services.llm_router.ModelRouter", new=_FakeRouter):
            result = await enforcer.call(
                budget=_make_budget(),
                model_id="deepseek-chat",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert result["success"] is False
        assert "No models available" in (result.get("error") or "")

    async def test_local_model_falls_back_to_llamacpp(self):
        """A model that was already local is allowed to use the local
        fallback when its primary route fails."""
        _FakeRouter.route_error = RuntimeError("local router hiccup")
        enforcer = BudgetEnforcer()
        with (
            patch("app.services.llm_router.ModelRouter", new=_FakeRouter),
            patch.object(
                enforcer,
                "_local_llamacpp_fallback",
                new=AsyncMock(return_value=dict(FAKE_FALLBACK_RESPONSE)),
            ),
        ):
            result = await enforcer.call(
                budget=_make_budget(),
                model_id="llamacpp/qwen3.6-27b",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert result["success"] is True
        assert result["provider"] == "llamacpp"

    async def test_explicit_allow_fallback_runs_local_model(self):
        """When the caller explicitly opts in via allow_fallback=True, a
        cloud model's failure is allowed to substitute the local model."""
        _FakeRouter.route_error = RuntimeError("cloud down")
        enforcer = BudgetEnforcer()
        with (
            patch("app.services.llm_router.ModelRouter", new=_FakeRouter),
            patch.object(
                enforcer,
                "_local_llamacpp_fallback",
                new=AsyncMock(return_value=dict(FAKE_FALLBACK_RESPONSE, substituted_from="openai/gpt-4o")),
            ),
        ):
            result = await enforcer.call(
                budget=_make_budget(),
                model_id="openai/gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                allow_fallback=True,
            )

        assert result["success"] is True
        assert result["provider"] == "llamacpp"


class TestSubstitutionTagging:
    async def test_substitution_tagged_in_event_log(self):
        """When the fallback fires for a non-local intended model, the event
        log payload carries substituted_from + a warning."""
        _FakeRouter.route_error = RuntimeError("cloud down")
        enforcer = BudgetEnforcer()
        captured = {}

        async def fake_record_llm_event(**kwargs):
            captured.update(kwargs)

        with (
            patch("app.services.llm_router.ModelRouter", new=_FakeRouter),
            patch.object(
                enforcer,
                "_local_llamacpp_fallback",
                new=AsyncMock(return_value=dict(FAKE_FALLBACK_RESPONSE, substituted_from="openai/gpt-4o")),
            ),
            patch.object(enforcer, "_record_llm_event", new=fake_record_llm_event),
        ):
            await enforcer.call(
                budget=_make_budget(),
                model_id="openai/gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                allow_fallback=True,
                run_id="run-1",
                mission_id="mission-1",
                task_id="task-1",
            )

        assert captured.get("substituted_from") == "openai/gpt-4o"
