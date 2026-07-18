from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.llm_call_record import LLMCallRecord
from app.models.mission_models import Mission

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_mission_analytics(db: AsyncSession, user_id: int | None = None) -> dict:
    filters = []
    if user_id is not None:
        filters.append(Mission.user_id == user_id)

    total = (await db.execute(select(func.count()).select_from(Mission).where(*filters))).scalar() or 0

    completed_filters = [*filters, Mission.status == "completed"]
    completed = (await db.execute(select(func.count()).select_from(Mission).where(*completed_filters))).scalar() or 0

    tokens_filters = filters[:]
    total_tokens = (
        await db.execute(select(func.coalesce(func.sum(Mission.tokens_used), 0)).where(*tokens_filters))
    ).scalar() or 0

    success_rate = completed / total if total > 0 else 0.0

    avg_completion = None
    avg_seconds = (
        await db.execute(
            select(
                func.avg(func.extract("epoch", Mission.completed_at) - func.extract("epoch", Mission.started_at))
            ).where(
                Mission.status == "completed",
                Mission.started_at.isnot(None),
                Mission.completed_at.isnot(None),
                *filters,
            )
        )
    ).scalar()
    if avg_seconds is not None:
        avg_completion = float(avg_seconds)

    return {
        "total_missions": total,
        "success_rate": success_rate,
        "avg_completion_time": avg_completion,
        "total_tokens_used": total_tokens,
    }


async def get_mission_analytics_over_time(db: AsyncSession, user_id: int | None = None, days: int = 30) -> list[dict]:
    """Return daily mission counts (total + completed) over the last N days."""
    from datetime import UTC, datetime, timedelta

    cutoff = datetime.now(UTC) - timedelta(days=days)
    filters = [Mission.created_at >= cutoff]
    if user_id is not None:
        filters.append(Mission.user_id == user_id)

    rows = await db.execute(
        select(
            func.date_trunc("day", Mission.created_at).label("day"),
            func.count().label("total"),
            func.count().filter(Mission.status == "completed").label("completed"),
        )
        .where(*filters)
        .group_by(func.date_trunc("day", Mission.created_at))
        .order_by(func.date_trunc("day", Mission.created_at))
    )
    return [
        {
            "day": row.day.isoformat() if row.day else None,
            "total": row.total,
            "completed": row.completed,
        }
        for row in rows.all()
    ]


async def get_failure_analysis(db: AsyncSession, user_id: int | None = None) -> list[dict]:
    """Group failed missions by failure_reason for the failure breakdown chart."""
    filters = [Mission.status == "failed"]
    if user_id is not None:
        filters.append(Mission.user_id == user_id)

    rows = await db.execute(
        select(
            func.coalesce(Mission.error_message, "unknown").label("category"),
            func.count().label("count"),
        )
        .where(*filters)
        .group_by("category")
        .order_by(func.count().desc())
    )
    return [{"category": row.category, "count": row.count} for row in rows.all()]


async def get_token_usage_breakdown(db: AsyncSession, user_id: int | None = None) -> list[dict]:
    """Break down token usage and cost by model from LLMCallRecord."""
    filters = []
    if user_id is not None:
        # LLMCallRecord doesn't have user_id directly; join via mission
        from sqlalchemy import and_

        filters.append(LLMCallRecord.mission_id.in_(select(Mission.id).where(Mission.user_id == user_id)))

    rows = await db.execute(
        select(
            LLMCallRecord.model_id,
            func.sum(LLMCallRecord.prompt_tokens + LLMCallRecord.completion_tokens).label("total_tokens"),
            func.sum(LLMCallRecord.cost_usd).label("total_cost"),
            func.count().label("call_count"),
        )
        .where(*filters)
        .group_by(LLMCallRecord.model_id)
        .order_by(func.sum(LLMCallRecord.prompt_tokens + LLMCallRecord.completion_tokens).desc())
    )
    return [
        {
            "model_id": row.model_id,
            "total_tokens": row.total_tokens or 0,
            "total_cost": float(row.total_cost or 0),
            "call_count": row.call_count,
        }
        for row in rows.all()
    ]
