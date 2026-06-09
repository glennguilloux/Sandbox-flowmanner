"""Tests for cost attribution engine (H5.3)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.observability.cost_engine import (
    CostAttributionEngine,
    CostEvent,
    get_cost_engine,
)
from app.models.llm_call_record import LLMCallRecord

pytestmark = pytest.mark.integration


def _make_record(**overrides) -> LLMCallRecord:
    return LLMCallRecord(
        id=str(uuid4()),
        mission_id=str(uuid4()),
        task_id=str(uuid4()),
        model_id="deepseek-chat",
        provider="deepseek",
        prompt_tokens=1000,
        completion_tokens=500,
        cost_usd=0.21,
        latency_ms=120,
        success=True,
        timestamp=datetime(2026, 6, 15),
        **overrides,
    )


# ═══════════════════════════════════════════════════════════════════
# CostEvent normalization
# ═══════════════════════════════════════════════════════════════════


class TestCostEvent:

    def test_from_record_normalizes_all_fields(self):
        rec = _make_record()
        event = CostEvent.from_record(
            rec, agent_id="agent-1", user_id=42, workspace_id="ws-1"
        )
        assert event.provider == "deepseek"
        assert event.model == "deepseek-chat"
        assert event.cost_usd == 0.21
        assert event.agent_id == "agent-1"
        assert event.mission_id == rec.mission_id
        assert event.user_id == 42

    def test_defaults_for_missing_ids(self):
        rec = _make_record()
        event = CostEvent.from_record(rec)
        assert event.agent_id == ""
        assert event.user_id == 0


# ═══════════════════════════════════════════════════════════════════
# agent_cost()
# ═══════════════════════════════════════════════════════════════════


class TestAgentCost:

    @pytest.mark.asyncio
    async def test_computes_sum_for_agent_in_month(self):
        engine = CostAttributionEngine()
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar.return_value = 1.23
        db.execute = AsyncMock(return_value=result_mock)

        cost = await engine.agent_cost(db, agent_id="agent-x", year=2026, month=6)
        assert cost == 1.23

    @pytest.mark.asyncio
    async def test_returns_zero_for_no_data(self):
        engine = CostAttributionEngine()
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        cost = await engine.agent_cost(db, agent_id="agent-x", year=2026, month=1)
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_correct_month_boundaries_december(self):
        engine = CostAttributionEngine()
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar.return_value = 0.0
        db.execute = AsyncMock(return_value=result_mock)

        cost = await engine.agent_cost(db, agent_id="agent-x", year=2026, month=12)
        assert cost == 0.0


# ═══════════════════════════════════════════════════════════════════
# agent_cost_by_period()
# ═══════════════════════════════════════════════════════════════════


class TestAgentCostByPeriod:

    @pytest.mark.asyncio
    async def test_returns_per_agent_dict(self):
        engine = CostAttributionEngine()
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.all.return_value = [("agent-a", 0.50), ("agent-b", 1.25)]
        db.execute = AsyncMock(return_value=result_mock)

        costs = await engine.agent_cost_by_period(db, year=2026, month=6)
        assert costs == {"agent-a": 0.50, "agent-b": 1.25}

    @pytest.mark.asyncio
    async def test_filters_by_agent_ids(self):
        engine = CostAttributionEngine()
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.all.return_value = [("agent-a", 0.50)]
        db.execute = AsyncMock(return_value=result_mock)

        costs = await engine.agent_cost_by_period(
            db, agent_ids=["agent-a"], year=2026, month=6
        )
        assert costs == {"agent-a": 0.50}


# ═══════════════════════════════════════════════════════════════════
# mission_cost()
# ═══════════════════════════════════════════════════════════════════


class TestMissionCost:

    @pytest.mark.asyncio
    async def test_returns_sum_for_mission(self):
        engine = CostAttributionEngine()
        db = AsyncMock(spec=AsyncSession)
        mid = str(uuid4())
        result_mock = MagicMock()
        result_mock.scalar.return_value = 2.50
        db.execute = AsyncMock(return_value=result_mock)

        cost = await engine.mission_cost(db, mid)
        assert cost == 2.50


# ═══════════════════════════════════════════════════════════════════
# user_cost()
# ═══════════════════════════════════════════════════════════════════


class TestUserCost:

    @pytest.mark.asyncio
    async def test_returns_per_user_dict(self):
        engine = CostAttributionEngine()
        db = AsyncMock(spec=AsyncSession)
        # First query returns mission costs
        result1 = MagicMock()
        result1.all.return_value = [("mid-1", 3.00), ("mid-2", 0.75)]
        # Second/third queries return user IDs
        result2 = MagicMock()
        result2.scalar.return_value = 42
        result3 = MagicMock()
        result3.scalar.return_value = 99
        db.execute = AsyncMock(side_effect=[result1, result2, result3])

        costs = await engine.user_cost(db, year=2026, month=6)
        assert costs == {42: 3.00, 99: 0.75}


# ═══════════════════════════════════════════════════════════════════
# workspace_cost()
# ═══════════════════════════════════════════════════════════════════


class TestWorkspaceCost:

    @pytest.mark.asyncio
    async def test_returns_empty_not_implemented(self):
        engine = CostAttributionEngine()
        db = AsyncMock(spec=AsyncSession)
        costs = await engine.workspace_cost(db, year=2026, month=6)
        assert costs == {}


# ═══════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════


class TestSingleton:

    def test_get_cost_engine_returns_same_instance(self):
        e1 = get_cost_engine()
        e2 = get_cost_engine()
        assert e1 is e2
        assert isinstance(e1, CostAttributionEngine)
