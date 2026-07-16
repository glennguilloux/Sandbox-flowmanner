"""Regression tests for R-4 / R-11 — circuit breaker fail-closed.

R-4 (HIGH): ``UnifiedExecutor.check_circuit_breaker`` and
``record_circuit_breaker_call`` must NOT swallow errors and silently allow
the call / drop the accounting. A guardrail that throws must DENY by default
(fail-closed), logged at ERROR and metered.

R-11 (in scope): when the per-workspace provider circuit breaker reports
``AllProvidersOpen`` (every provider in the fallback chain is down), the
resolution failure must NOT be swallowed into a fallback-to-intended-model —
it must propagate so the call is denied (fail closed).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.capability_models import Budget
from app.services.substrate.executor import UnifiedExecutor
from app.services.substrate.provider_fallback import AllProvidersOpen
from app.services.budget_enforcer import BudgetEnforcer


# ── R-4: check_circuit_breaker fails closed ────────────────────────────────


def _make_executor() -> UnifiedExecutor:
    ex = UnifiedExecutor()
    return ex


class _AsyncCtx:
    """Minimal async context manager for mocking db.begin_nested()."""

    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


def _boom_db() -> AsyncSession:
    """An AsyncSession whose begin_nested / execute raises, simulating a
    DB/serialization failure inside the circuit breaker check."""

    db = MagicMock(spec=AsyncSession)
    db.begin_nested = MagicMock(return_value=_AsyncCtx())
    db.execute = MagicMock(side_effect=RuntimeError("DB connection lost"))
    return db


class TestCheckCircuitBreakerFailClosed:
    async def test_check_raises_returns_deny(self):
        """A DB error in the breaker check must deny the call, not allow it."""
        ex = _make_executor()
        db = _boom_db()
        allowed, reason = await ex.check_circuit_breaker(db=db, mission_id="m1")
        assert allowed is False, "guardrail failure must DENY (fail-closed)"
        assert "failed" in reason.lower()

    async def test_check_fail_open_config_allows_but_is_loud(self):
        """Deliberate fail-open escape hatch still returns allow but is
        explicitly opted into and surfaced (we assert behaviour only; the
        loud logging is covered by the fail-closed default path)."""
        ex = _make_executor()
        db = _boom_db()
        with patch.object(settings, "FLOWMANNER_CIRCUIT_BREAKER_FAIL_CLOSED", False):
            allowed, _ = await ex.check_circuit_breaker(db=db, mission_id="m1")
        assert allowed is True

    async def test_no_breaker_still_allows(self):
        """Normal path: a mission with no breaker row is allowed to proceed."""
        ex = _make_executor()
        db = MagicMock(spec=AsyncSession)
        db.begin_nested = MagicMock(return_value=_AsyncCtx())

        # get_breaker returns None -> allowed.
        with patch(
            "app.services.circuit_breaker_service.CircuitBreakerService.get_breaker",
            new=AsyncMock(return_value=None),
        ):
            allowed, reason = await ex.check_circuit_breaker(db=db, mission_id="m1")
        assert allowed is True


# ── R-4: record_circuit_breaker_call no longer swallows ─────────────────────


class TestRecordCircuitBreakerCallFailure:
    async def test_record_failure_is_logged_not_silent(self, caplog):
        """A recording failure must be surfaced (ERROR log + metric), not
        silently swallowed at debug. The method returns None, so we assert the
        failure is observable in the logs at ERROR level (previously it was
        swallowed at debug)."""
        import logging

        ex = _make_executor()
        db = _boom_db()
        with caplog.at_level(logging.ERROR, logger="app.services.substrate.executor"):
            await ex.record_circuit_breaker_call(db=db, mission_id="m1")

        assert any(
            "Circuit breaker record FAILED" in rec.message and rec.levelno >= logging.ERROR
            for rec in caplog.records
        ), "recording failure must be logged at ERROR, not swallowed"


# ── R-11: provider AllProvidersOpen is not swallowed ────────────────────────


class TestProviderResolutionFailClosed:
    async def test_all_providers_open_propagates(self):
        """When resolve_provider raises AllProvidersOpen, BudgetEnforcer.call
        must propagate it (deny) rather than falling back to the intended
        model and reporting success."""
        enforcer = BudgetEnforcer()
        # No real LLM call: patch ModelRouter so we can detect if the call
        # ever reached the provider path (it must NOT).
        router_hit = {"called": False}

        class _FakeRouter:
            def __init__(self, *a, **k):
                pass

            async def route_request(self, *a, **k):
                router_hit["called"] = True
                return {
                    "success": True,
                    "response": "x",
                    "model": "x",
                    "provider": "deepseek",
                    "cost": {"input_tokens": 1, "output_tokens": 1},
                }

        db = MagicMock(spec=AsyncSession)
        from app.services.substrate.provider_fallback import ProviderProvenance

        async def _resolve_open(*a, **k):
            raise AllProvidersOpen(
                tried=["deepseek"],
                provenance=ProviderProvenance(
                    requested_provider="deepseek-chat", served_provider="deepseek-chat"
                ),
            )

        with (
            patch("app.services.llm_router.ModelRouter", new=_FakeRouter),
            patch(
                "app.services.substrate.provider_fallback.resolve_provider",
                new=_resolve_open,
            ),
            patch.object(settings, "FLOWMANNER_CIRCUIT_BREAKER_ENABLED", True),
        ):
            with pytest.raises(AllProvidersOpen):
                await enforcer.call(
                    budget=Budget(max_cost_usd=Decimal("10.00")),
                    model_id="deepseek-chat",
                    messages=[{"role": "user", "content": "hi"}],
                    db_session=db,
                    workspace_id="ws-1",
                    mission_id="m-1",
                )

        assert router_hit["called"] is False, "provider call must not fire when AllProvidersOpen"
