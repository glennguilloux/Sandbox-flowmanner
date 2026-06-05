"""Cost attribution engine (H5.3).

Normalizes LLMCallRecord events and provides aggregation queries
by agent, mission, user, workspace, and period.

Answers the question: "How much did agent X cost this month?"
Uses the existing ``LLMCallRecord`` and ``MissionTask`` models.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select

from app.models.llm_call_record import LLMCallRecord
from app.models.mission_models import Mission, MissionTask

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Normalized event ───────────────────────────────────────────────


@dataclass
class CostEvent:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    agent_id: str = ""
    mission_id: str = ""
    user_id: int = 0
    workspace_id: str = ""
    timestamp: datetime | None = None

    @classmethod
    def from_record(
        cls,
        record: LLMCallRecord,
        agent_id: str = "",
        user_id: int = 0,
        workspace_id: str = "",
    ) -> CostEvent:
        return cls(
            provider=record.provider,
            model=record.model_id,
            input_tokens=record.prompt_tokens,
            output_tokens=record.completion_tokens,
            cost_usd=record.cost_usd,
            agent_id=agent_id,
            mission_id=record.mission_id or "",
            user_id=user_id,
            workspace_id=workspace_id,
            timestamp=record.timestamp,
        )


# ── Engine ─────────────────────────────────────────────────────────


class CostAttributionEngine:
    """Aggregates costs across LLMCallRecord rows.

    Usage::

        engine = CostAttributionEngine()
        cost = await engine.agent_cost(db, agent_id="abc", year=2026, month=6)
    """

    async def compute(self, record: LLMCallRecord) -> CostEvent:
        """Normalize a single LLMCallRecord into a CostEvent."""
        return CostEvent.from_record(record)

    # ── Aggregation by agent ───────────────────────────────────────

    async def agent_cost(
        self,
        db: AsyncSession,
        agent_id: str,
        year: int,
        month: int,
    ) -> float:
        """Total cost in USD for *agent_id* in the given year/month."""
        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

        result = await db.execute(
            select(func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0))
            .join(MissionTask, LLMCallRecord.task_id == MissionTask.id)
            .where(
                and_(
                    MissionTask.assigned_agent_id == agent_id,
                    LLMCallRecord.timestamp >= start,
                    LLMCallRecord.timestamp < end,
                )
            )
        )
        return float(result.scalar() or 0.0)

    async def agent_cost_by_period(
        self,
        db: AsyncSession,
        agent_ids: list[str] | None = None,
        year: int | None = None,
        month: int | None = None,
    ) -> dict[str, float]:
        """Cost per agent, optionally filtered by period.

        Returns ``{agent_id: total_cost_usd}``.
        """
        stmt = (
            select(
                MissionTask.assigned_agent_id,
                func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0),
            )
            .join(MissionTask, LLMCallRecord.task_id == MissionTask.id)
            .where(MissionTask.assigned_agent_id.isnot(None))
        )
        if year and month:
            start = datetime(year, month, 1)
            end = (
                datetime(year + 1, 1, 1)
                if month == 12
                else datetime(year, month + 1, 1)
            )
            stmt = stmt.where(
                and_(
                    LLMCallRecord.timestamp >= start,
                    LLMCallRecord.timestamp < end,
                )
            )
        if agent_ids:
            stmt = stmt.where(MissionTask.assigned_agent_id.in_(agent_ids))

        stmt = stmt.group_by(MissionTask.assigned_agent_id)

        result = await db.execute(stmt)
        rows = result.all()
        return {row[0]: float(row[1]) for row in rows if row[0]}

    # ── Aggregation by mission ─────────────────────────────────────

    async def mission_cost(
        self,
        db: AsyncSession,
        mission_id: str,
    ) -> float:
        """Total cost for a single mission."""
        result = await db.execute(
            select(func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0)).where(
                LLMCallRecord.mission_id == mission_id
            )
        )
        return float(result.scalar() or 0.0)

    async def mission_costs_by_period(
        self,
        db: AsyncSession,
        year: int,
        month: int,
    ) -> dict[str, float]:
        """Cost per mission for the given year/month."""
        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

        result = await db.execute(
            select(
                LLMCallRecord.mission_id,
                func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0),
            )
            .where(
                and_(
                    LLMCallRecord.timestamp >= start,
                    LLMCallRecord.timestamp < end,
                    LLMCallRecord.mission_id.isnot(None),
                )
            )
            .group_by(LLMCallRecord.mission_id)
        )
        rows = result.all()
        return {row[0]: float(row[1]) for row in rows if row[0]}

    # ── Aggregation by user ────────────────────────────────────────

    async def user_cost(
        self,
        db: AsyncSession,
        year: int,
        month: int,
    ) -> dict[int, float]:
        """Cost per user for the given year/month.

        Returns ``{user_id: total_cost_usd}``.
        """
        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

        result = await db.execute(
            select(
                LLMCallRecord.mission_id,
                func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0),
            )
            .where(
                and_(
                    LLMCallRecord.timestamp >= start,
                    LLMCallRecord.timestamp < end,
                    LLMCallRecord.mission_id.isnot(None),
                )
            )
            .group_by(LLMCallRecord.mission_id)
        )
        rows = result.all()
        missions = {row[0]: float(row[1]) for row in rows if row[0]}

        # Map missions → users via separate query (avoids workspace_id dependency)
        user_costs: dict[int, float] = {}
        for mission_id, cost in missions.items():
            user_result = await db.execute(
                select(Mission.user_id).where(Mission.id == mission_id)
            )
            uid = user_result.scalar()
            if uid is not None:
                user_costs[int(uid)] = user_costs.get(int(uid), 0.0) + cost

        return user_costs

    async def workspace_cost(
        self,
        db: AsyncSession,
        year: int,
        month: int,
        workspace_id: str | None = None,
    ) -> dict[str, float]:
        """Cost per workspace for the given year/month.

        Returns ``{workspace_id: total_cost_usd}``.
        Uses the ``workspace_id`` column on ``LLMCallRecord``
        (enriched during cost attribution) or falls back to
        ``Mission.workspace_id`` via mission_id join.
        """
        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

        # Try direct workspace_id on LLMCallRecord first
        stmt = (
            select(
                LLMCallRecord.workspace_id,
                func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0),
            )
            .where(
                and_(
                    LLMCallRecord.timestamp >= start,
                    LLMCallRecord.timestamp < end,
                    LLMCallRecord.workspace_id.isnot(None),
                )
            )
            .group_by(LLMCallRecord.workspace_id)
        )
        if workspace_id:
            stmt = stmt.where(LLMCallRecord.workspace_id == workspace_id)

        result = await db.execute(stmt)
        rows = result.all()
        direct_costs: dict[str, float] = {
            row[0]: float(row[1]) for row in rows if row[0]
        }

        # Also aggregate via Mission.workspace_id for records without direct attribution
        mission_stmt = (
            select(
                Mission.workspace_id,
                func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0),
            )
            .join(Mission, LLMCallRecord.mission_id == Mission.id)
            .where(
                and_(
                    LLMCallRecord.timestamp >= start,
                    LLMCallRecord.timestamp < end,
                    Mission.workspace_id.isnot(None),
                    LLMCallRecord.workspace_id.is_(None),  # only unattributed records
                )
            )
            .group_by(Mission.workspace_id)
        )
        if workspace_id:
            mission_stmt = mission_stmt.where(Mission.workspace_id == workspace_id)

        mission_result = await db.execute(mission_stmt)
        for row in mission_result.all():
            ws_id = row[0]
            if ws_id:
                direct_costs[ws_id] = direct_costs.get(ws_id, 0.0) + float(row[1])

        return direct_costs


# ── Singleton ──────────────────────────────────────────────────────

_engine: CostAttributionEngine | None = None


def get_cost_engine() -> CostAttributionEngine:
    global _engine
    if _engine is None:
        _engine = CostAttributionEngine()
    return _engine
