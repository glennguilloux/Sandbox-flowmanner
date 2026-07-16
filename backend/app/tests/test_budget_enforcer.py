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
from unittest.mock import AsyncMock, patch

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
        # Item #6: provenance on failed calls
        assert result["requested_model"] == "openai/gpt-4o"
        assert result["served_model"] is None
        assert result["substituted_from"] is None
        assert result["degraded"] is False

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
        # Item #6: provenance — local→local is NOT degraded
        assert result["requested_model"] == "llamacpp/qwen3.6-27b"
        assert result["served_model"] == "llamacpp/qwen3.6-27b"
        assert result["degraded"] is False

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
        # Item #6: provenance — cloud→local IS degraded
        assert result["requested_model"] == "openai/gpt-4o"
        assert result["served_model"] == "llamacpp/qwen3.6-27b"
        assert result["substituted_from"] == "openai/gpt-4o"
        assert result["degraded"] is True


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
        # Item #6: provenance fields in event log
        assert captured.get("requested_model") == "openai/gpt-4o"
        assert captured.get("degraded") is True


class TestPreEstimateBudgetCap:
    async def test_overshoot_estimate_raises_before_provider_call(self):
        """R-5 (I.14): a call whose estimated cost exceeds the remaining budget
        must raise BudgetExhausted BEFORE any provider/model round-trip.

        We use a tiny budget and a pricey model with a large prompt so the
        conservative pre-estimate blows the cap. The ModelRouter is patched
        with a beacon that fails the test if it is ever reached.
        """
        router_hit = {"called": False}

        class _BeaconRouter:
            def __init__(self, *a, **k):
                pass

            async def route_request(self, *a, **k):
                router_hit["called"] = True
                raise AssertionError("router must NOT be called when estimate exceeds budget")

        # $0.05 cap; gpt-4o input $5/M, output $15/M, 2000 completion ceiling.
        # A 2000-char prompt alone prices ~ (2000/4=500 tokens)*$5/1e6 = $0.0025
        # plus 2000 completion tokens * $15/1e6 = $0.03 -> ~$0.0325 > $0.05? No.
        # Make the cap tiny so it is guaranteed over: cap = $0.005.
        budget = Budget(max_cost_usd=Decimal("0.005"))
        enforcer = BudgetEnforcer()

        with patch("app.services.llm_router.ModelRouter", new=_BeaconRouter):
            with pytest.raises(Exception) as excinfo:
                await enforcer.call(
                    budget=budget,
                    model_id="gpt-4o",
                    messages=[
                        {"role": "user", "content": "x" * 4000},
                        {"role": "system", "content": "y" * 4000},
                    ],
                    max_tokens=4000,
                )

        # The raised error must be the budget guard, and the router must be
        # untouched (no LLM/httpx call happened).
        assert router_hit["called"] is False
        assert "Budget" in type(excinfo.value).__name__

    async def test_under_cap_proceeds_and_records(self):
        """Sanity: a call well within budget still proceeds through the router
        and records spend (pre-estimate gate does not block valid calls)."""
        enforcer = BudgetEnforcer()
        captured = {}

        async def fake_record_llm_event(**kwargs):
            captured.update(kwargs)

        # Reset shared router state so this test does not depend on order.
        _FakeRouter.route_error = None
        with (
            patch("app.services.llm_router.ModelRouter", new=_FakeRouter),
            patch.object(enforcer, "_record_llm_event", new=fake_record_llm_event),
        ):
            result = await enforcer.call(
                budget=Budget(max_cost_usd=Decimal("10.00")),
                model_id="deepseek-chat",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert result["success"] is True
        assert captured.get("cost_usd") is not None


class TestReasoningParam:
    async def test_call_accepts_reasoning_kwarg(self):
        """RC (t_c4678988): node_executor calls call(..., reasoning=...) — the
        signature must accept it (and forward it to the router) without
        raising TypeError. Regression guard for the 'unexpected keyword
        argument reasoning' crash that blocked all blueprint runs."""
        captured = {}

        class _CaptureRouter:
            def __init__(self, *a, **k):
                pass

            async def route_request(self, *a, **k):
                captured.update(kwargs={})
                captured["kwargs"] = {"reasoning" if kk == "reasoning" else kk: vv for kk, vv in k.items()}
                return {
                    "success": True,
                    "response": "ok",
                    "model": "x",
                    "provider": "deepseek",
                    "cost": {"input_tokens": 1, "output_tokens": 1},
                }

        enforcer = BudgetEnforcer()
        fake_reasoning = {"effort": "high"}
        with patch("app.services.llm_router.ModelRouter", new=_CaptureRouter):
            result = await enforcer.call(
                budget=Budget(max_cost_usd=Decimal("10.00")),
                model_id="deepseek-chat",
                messages=[{"role": "user", "content": "hi"}],
                reasoning=fake_reasoning,
            )

        assert result["success"] is True
        assert captured["kwargs"].get("reasoning") is fake_reasoning
