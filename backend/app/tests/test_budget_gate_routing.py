"""Regression tests for Comment 4 — LLM paths must honor the budget gate.

Planning and chat/title generation previously bypassed BudgetEnforcer: the
planner called ModelRouter (and a raw httpx fallback) directly; chat/title
called the provider client with no budget check. Now both routes go through
the budget gate and MUST fail BEFORE the provider call when the budget is
exhausted.
"""

from __future__ import annotations

import os

# chat_service constructs an AsyncOpenAI client at import time, which needs a
# (possibly dummy) API key in this environment.
os.environ.setdefault("LLM_API_KEY", "test-dummy-key")

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.capability_models import Budget, BudgetExhausted
from app.services.budget_enforcer import BudgetEnforcer, enforce_budget_before_llm


def _exhausted_budget() -> Budget:
    b = Budget(max_cost_usd=Decimal("0.00"), max_wall_time_seconds=1, max_iterations=0, max_depth=1)
    return b


async def test_planner_routes_through_budget_enforcer_and_raises_when_exhausted():
    from app.services.mission_planner import MissionPlanner

    planner = MissionPlanner(cost_tracker=None, get_model_router=lambda: None)

    # Force the budget enforcer to raise BudgetExhausted on any call.
    fake = MagicMock(spec=BudgetEnforcer)
    fake.call = AsyncMock(side_effect=BudgetExhausted("exhausted", _exhausted_budget()))

    with patch("app.services.budget_enforcer.get_budget_enforcer", return_value=fake):
        with pytest.raises(BudgetExhausted):
            await planner._generate_plan(
                "break this into tasks",
                db=AsyncMock(),
                user_id=1,
                mission_id="m1",
            )
    # The enforcer.call path was used (not the raw httpx/ModelRouter bypass).
    assert fake.call.await_count >= 1


async def test_chat_title_enforces_budget_before_provider():
    from app.services import chat_service

    provider_called = {"n": 0}

    async def fake_create(*args, **kwargs):
        provider_called["n"] += 1
        raise AssertionError("provider must not be called when budget exhausted")

    db = AsyncMock()
    # get_chat_thread -> a thread; first_messages -> 2 fake messages.
    m1 = MagicMock()
    m1.content = "hello"
    m2 = MagicMock()
    m2.content = "hi there"
    res = MagicMock()
    res.scalars.return_value.all.return_value = [m1, m2]
    db.execute.return_value = res
    with patch.object(chat_service._client.chat.completions, "create", fake_create), pytest.raises(BudgetExhausted):
        await chat_service.generate_thread_title(
                db=db,
                thread_id=1,
                budget=_exhausted_budget(),
            )
    assert provider_called["n"] == 0, "provider call must not happen before the budget gate"


async def test_enforce_budget_before_llm_rejects_none():
    with pytest.raises(BudgetExhausted):
        enforce_budget_before_llm(None, model_id="deepseek-v4-flash")
