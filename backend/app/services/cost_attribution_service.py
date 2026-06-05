"""Cost Attribution service — Phase 6.3.

Provides:
- get_aggregates(): Query cost aggregates by agent, mission, user, workspace, time period
- enrich_record(): Add workspace_id and agent_id to an LLMCallRecord before write

The actual recording is already handled by BudgetEnforcer → CostTracker.
This service enriches records with attribution metadata and provides
aggregation queries for the dashboard.

Usage:
    service = CostAttributionService(db)
    # Aggregate by workspace for last 30 days
    aggregates = await service.get_aggregates(
        workspace_id="ws-123",
        group_by="agent",
        days=30,
    )
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, select, text

from app.models.llm_call_record import LLMCallRecord
from app.models.mission_models import Mission

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CostAttributionService:
    """Cost attribution queries for the dashboard."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_aggregates(
        self,
        *,
        workspace_id: str | None = None,
        user_id: int | None = None,
        agent_id: str | None = None,
        mission_id: str | None = None,
        group_by: str = "day",
        days: int = 30,
    ) -> dict[str, Any]:
        """Get cost aggregates with flexible grouping.

        Args:
            workspace_id: Filter by workspace.
            user_id: Filter by user (via mission ownership — not direct on LLMCallRecord).
            agent_id: Filter by agent.
            mission_id: Filter by mission.
            group_by: Grouping dimension — "day", "agent", "mission", "model", "provider", "workspace".
            days: Number of days to look back.

        Returns:
            Dict with breakdown list, totals, and period info.
        """
        since = datetime.now(UTC) - timedelta(days=days)
        conditions = [LLMCallRecord.timestamp >= since]

        if user_id:
            conditions.append(LLMCallRecord.mission_id.in_(
                select(Mission.id).where(Mission.user_id == user_id)
            ))
        if workspace_id:
            conditions.append(LLMCallRecord.workspace_id == workspace_id)
        if agent_id:
            conditions.append(LLMCallRecord.agent_id == agent_id)
        if mission_id:
            conditions.append(LLMCallRecord.mission_id == mission_id)

        where = and_(*conditions)

        # ── Totals ───────────────────────────────────────────────────
        totals_stmt = (
            select(
                func.count(LLMCallRecord.id).label("total_calls"),
                func.coalesce(func.sum(LLMCallRecord.prompt_tokens), 0).label("total_prompt_tokens"),
                func.coalesce(func.sum(LLMCallRecord.completion_tokens), 0).label("total_completion_tokens"),
                func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0).label("total_cost_usd"),
                func.coalesce(func.avg(LLMCallRecord.latency_ms), 0).label("avg_latency_ms"),
            )
            .where(where)
        )
        totals_row = (await self.db.execute(totals_stmt)).one()

        # ── Breakdown ────────────────────────────────────────────────
        breakdown = []
        if group_by == "day":
            breakdown = await self._aggregate_by_day(where, days)
        elif group_by == "agent":
            breakdown = await self._aggregate_by_field(where, LLMCallRecord.agent_id)
        elif group_by == "mission":
            breakdown = await self._aggregate_by_field(where, LLMCallRecord.mission_id)
        elif group_by == "model":
            breakdown = await self._aggregate_by_field(where, LLMCallRecord.model_id)
        elif group_by == "provider":
            breakdown = await self._aggregate_by_field(where, LLMCallRecord.provider)
        elif group_by == "workspace":
            breakdown = await self._aggregate_by_field(where, LLMCallRecord.workspace_id)

        return {
            "period": {
                "days": days,
                "since": since.isoformat(),
                "until": datetime.now(UTC).isoformat(),
            },
            "totals": {
                "total_calls": totals_row.total_calls,
                "total_prompt_tokens": int(totals_row.total_prompt_tokens),
                "total_completion_tokens": int(totals_row.total_completion_tokens),
                "total_cost_usd": round(float(totals_row.total_cost_usd), 6),
                "avg_latency_ms": round(float(totals_row.avg_latency_ms), 1),
            },
            "breakdown": breakdown,
        }

    async def _aggregate_by_day(self, where, days: int) -> list[dict]:
        """Aggregate costs by day."""
        stmt = (
            select(
                func.date_trunc("day", LLMCallRecord.timestamp).label("day"),
                func.count(LLMCallRecord.id).label("calls"),
                func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0).label("cost_usd"),
                func.coalesce(func.sum(LLMCallRecord.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(LLMCallRecord.completion_tokens), 0).label("completion_tokens"),
            )
            .where(where)
            .group_by(text("day"))
            .order_by(text("day"))
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "day": r.day.isoformat() if r.day else None,
                "calls": r.calls,
                "cost_usd": round(float(r.cost_usd), 6),
                "prompt_tokens": int(r.prompt_tokens),
                "completion_tokens": int(r.completion_tokens),
            }
            for r in rows
        ]

    async def _aggregate_by_field(self, where, field) -> list[dict]:
        """Aggregate costs by a given field."""
        stmt = (
            select(
                field.label("key"),
                func.count(LLMCallRecord.id).label("calls"),
                func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0).label("cost_usd"),
                func.coalesce(func.sum(LLMCallRecord.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(LLMCallRecord.completion_tokens), 0).label("completion_tokens"),
            )
            .where(where)
            .group_by(field)
            .order_by(text("cost_usd DESC"))
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "key": str(r.key) if r.key is not None else "unknown",
                "calls": r.calls,
                "cost_usd": round(float(r.cost_usd), 6),
                "prompt_tokens": int(r.prompt_tokens),
                "completion_tokens": int(r.completion_tokens),
            }
            for r in rows
        ]

    async def get_mission_cost(self, mission_id: str) -> dict[str, Any]:
        """Get total cost for a single mission."""
        stmt = (
            select(
                func.count(LLMCallRecord.id).label("calls"),
                func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0).label("cost_usd"),
                func.coalesce(func.sum(LLMCallRecord.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(LLMCallRecord.completion_tokens), 0).label("completion_tokens"),
            )
            .where(LLMCallRecord.mission_id == mission_id)
        )
        row = (await self.db.execute(stmt)).one()
        return {
            "mission_id": mission_id,
            "total_calls": row.calls,
            "total_cost_usd": round(float(row.cost_usd), 6),
            "total_prompt_tokens": int(row.prompt_tokens),
            "total_completion_tokens": int(row.completion_tokens),
        }
