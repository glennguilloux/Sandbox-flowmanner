from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.mission_models import Mission

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_mission_analytics(db: AsyncSession, user_id: int | None = None) -> dict:
    filters = []
    if user_id is not None:
        filters.append(Mission.user_id == user_id)

    total = (
        await db.execute(select(func.count()).select_from(Mission).where(*filters))
    ).scalar() or 0

    completed_filters = [*filters, Mission.status == "completed"]
    completed = (
        await db.execute(
            select(func.count()).select_from(Mission).where(*completed_filters)
        )
    ).scalar() or 0

    tokens_filters = filters[:]
    total_tokens = (
        await db.execute(
            select(func.coalesce(func.sum(Mission.tokens_used), 0)).where(
                *tokens_filters
            )
        )
    ).scalar() or 0

    success_rate = completed / total if total > 0 else 0.0

    avg_completion = None
    avg_seconds = (
        await db.execute(
            select(
                func.avg(
                    func.extract("epoch", Mission.completed_at)
                    - func.extract("epoch", Mission.started_at)
                )
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


async def get_mission_analytics_over_time(
    db: AsyncSession, user_id: int | None = None, days: int = 30
) -> list:
    return []


async def get_failure_analysis(db: AsyncSession, user_id: int | None = None) -> list:
    return []


async def get_token_usage_breakdown(
    db: AsyncSession, user_id: int | None = None
) -> list:
    return []
