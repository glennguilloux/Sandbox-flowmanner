"""Dashboard v2 API — user-facing execution history, costs, logs, stats."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select, text

from app.api.deps import get_current_user
from app.api.v2.base import ok, paginated
from app.database import get_db
from app.models.llm_call_record import LLMCallRecord
from app.models.mission_models import (
    Mission,
    MissionLog,
    MissionStatus,
    MissionTask,
    MissionTaskStatus,
)
from app.observability.cost_engine import CostAttributionEngine
from app.schemas.dashboard_v2 import (
    CostAnalyticsResponse,
    CostByAgent,
    CostByModel,
    DashboardStats,
    LogEntry,
    MissionHistoryItem,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["v2-dashboard"])


# ── Mission History ───────────────────────────────────────────────────────────


@router.get("/missions")
@router.get("/missions/")
async def list_missions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter by mission status"),
    search: str | None = Query(None, description="Search by title"),
    sort_by: str = Query("started_at", pattern="^(started_at|completed_at|actual_cost|duration)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    date_from: str | None = Query(None, description="ISO date filter start"),
    date_to: str | None = Query(None, description="ISO date filter end"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Paginated mission history for the current user."""
    # Base query — only this user's missions
    query = (
        select(
            Mission.id,
            Mission.title,
            Mission.status,
            Mission.mission_type,
            Mission.started_at,
            Mission.completed_at,
            Mission.actual_cost,
            Mission.tokens_used,
            Mission.error_message,
            func.count(MissionTask.id).label("task_count"),
            func.count().filter(MissionTask.status == MissionTaskStatus.COMPLETED).label("completed_tasks"),
            func.count().filter(MissionTask.status == MissionTaskStatus.FAILED).label("failed_tasks"),
            func.extract(
                "epoch",
                func.coalesce(Mission.completed_at, datetime.now(UTC))
                - func.coalesce(Mission.started_at, Mission.created_at),
            ).label("duration_seconds"),
        )
        .outerjoin(
            MissionTask,
            MissionTask.mission_id == Mission.id,
        )
        .where(
            Mission.user_id == user.id,
            Mission.deleted_at.is_(None),
        )
        .group_by(Mission.id)
    )

    # Filters
    if status:
        query = query.where(Mission.status == status)
    if search:
        query = query.where(Mission.title.ilike(f"%{search}%"))
    if date_from:
        query = query.where(Mission.created_at >= date_from)
    if date_to:
        query = query.where(Mission.created_at <= date_to)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Sort
    sort_cols: dict[str, Any] = {
        "started_at": Mission.started_at,
        "completed_at": Mission.completed_at,
        "actual_cost": Mission.actual_cost,
        "duration": text("duration_seconds"),
    }
    sort_col = sort_cols.get(sort_by, Mission.started_at)
    query = query.order_by(desc(sort_col)) if sort_order == "desc" else query.order_by(sort_col)

    # Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    rows = (await db.execute(query)).all()

    items = []
    for row in rows:
        items.append(
            MissionHistoryItem(
                id=str(row.id),
                title=row.title,
                status=str(row.status) if row.status else "unknown",
                mission_type=row.mission_type,
                started_at=row.started_at.isoformat() if row.started_at else None,
                completed_at=row.completed_at.isoformat() if row.completed_at else None,
                duration_seconds=round(float(row.duration_seconds or 0), 1),
                actual_cost=round(row.actual_cost, 6) if row.actual_cost else None,
                tokens_used=row.tokens_used,
                task_count=row.task_count,
                completed_tasks=row.completed_tasks,
                failed_tasks=row.failed_tasks,
                error_message=row.error_message,
            ).model_dump()
        )

    return paginated(items=items, total=total, page=page, per_page=per_page)


# ── Cost Analytics ────────────────────────────────────────────────────────────


@router.get("/costs")
@router.get("/costs/")
async def get_cost_analytics(
    period: str = Query("month", pattern="^(month|week|all)$"),
    workspace_id: str | None = Query(None, description="Filter by workspace ID"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cost analytics for the current user using CostAttributionEngine."""
    engine = CostAttributionEngine()
    now = datetime.now(UTC)

    # Determine date range
    if period == "week":
        start = now - timedelta(days=7)
        period_days = 7
    elif period == "month":
        start = now - timedelta(days=30)
        period_days = 30
    else:
        start = None
        period_days = None

    # Total cost for user's missions
    total_cost = 0.0
    missions_query = select(Mission.id).where(
        Mission.user_id == user.id,
        Mission.deleted_at.is_(None),
    )
    if start:
        missions_query = missions_query.where(Mission.created_at >= start)
    if workspace_id:
        missions_query = missions_query.where(Mission.workspace_id == workspace_id)
    mission_rows = (await db.execute(missions_query)).all()
    mission_ids = [str(row[0]) for row in mission_rows]

    # Previous period cost for trend calculation (computed after total_cost)
    previous_period_cost: float | None = None
    trend_pct: float | None = None

    if mission_ids:
        # Sum cost from LLMCallRecord
        cost_result = await db.execute(
            select(func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0)).where(
                LLMCallRecord.mission_id.in_(mission_ids)
            )
        )
        total_cost = round(float(cost_result.scalar() or 0), 6)

        # Cost by agent
        agent_cost_rows = await db.execute(
            select(
                MissionTask.assigned_agent_id,
                func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0),
            )
            .join(MissionTask, LLMCallRecord.task_id == MissionTask.id)
            .where(
                LLMCallRecord.mission_id.in_(mission_ids),
                MissionTask.assigned_agent_id.isnot(None),
            )
            .group_by(MissionTask.assigned_agent_id)
        )
        by_agent = [CostByAgent(agent_id=row[0], cost_usd=round(float(row[1]), 6)) for row in agent_cost_rows.all()]

        # Cost by model
        model_cost_rows = await db.execute(
            select(
                LLMCallRecord.model_id,
                func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0),
            )
            .where(LLMCallRecord.mission_id.in_(mission_ids))
            .group_by(LLMCallRecord.model_id)
        )
        by_model = [CostByModel(model_id=row[0], cost_usd=round(float(row[1]), 6)) for row in model_cost_rows.all()]
    else:
        by_agent = []
        by_model = []

    # Calculate trend after total_cost is known
    if period_days and start:
        prev_start = start - timedelta(days=period_days)
        prev_missions_query = select(Mission.id).where(
            Mission.user_id == user.id,
            Mission.deleted_at.is_(None),
            Mission.created_at >= prev_start,
            Mission.created_at < start,
        )
        if workspace_id:
            prev_missions_query = prev_missions_query.where(Mission.workspace_id == workspace_id)
        prev_mission_rows = (await db.execute(prev_missions_query)).all()
        prev_mission_ids = [str(row[0]) for row in prev_mission_rows]
        if prev_mission_ids:
            prev_cost_result = await db.execute(
                select(func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0)).where(
                    LLMCallRecord.mission_id.in_(prev_mission_ids)
                )
            )
            previous_period_cost = round(float(prev_cost_result.scalar() or 0), 6)
            if previous_period_cost > 0:
                trend_pct = round((total_cost - previous_period_cost) / previous_period_cost * 100, 1)

    return ok(
        CostAnalyticsResponse(
            total_cost=total_cost,
            previous_period_cost=previous_period_cost,
            trend_pct=trend_pct,
            by_agent=by_agent,
            by_model=by_model,
        ).model_dump()
    )


# ── Search Logs ───────────────────────────────────────────────────────────────


@router.get("/logs")
@router.get("/logs/")
async def search_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, description="Search message text"),
    mission_id: str | None = Query(None, description="Filter by mission"),
    level: str | None = Query(None, description="Filter by log level"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search mission execution logs for the current user."""
    query = (
        select(
            MissionLog.id,
            MissionLog.mission_id,
            MissionLog.task_id,
            Mission.title.label("mission_title"),
            MissionTask.title.label("task_title"),
            MissionLog.level,
            MissionLog.message,
            MissionLog.data,
            MissionLog.timestamp,
        )
        .join(Mission, Mission.id == MissionLog.mission_id)
        .outerjoin(MissionTask, MissionTask.id == MissionLog.task_id)
        .where(Mission.user_id == user.id)
    )

    # Filters
    if mission_id:
        query = query.where(MissionLog.mission_id == mission_id)
    if level:
        query = query.where(MissionLog.level == level)
    if search:
        query = query.where(MissionLog.message.ilike(f"%{search}%"))

    # Count
    count_subq = query.subquery()
    total = (await db.execute(select(func.count()).select_from(count_subq))).scalar() or 0

    # Paginate
    query = query.order_by(desc(MissionLog.timestamp))
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    rows = (await db.execute(query)).all()

    items = [
        LogEntry(
            id=str(row.id),
            mission_id=str(row.mission_id),
            task_id=str(row.task_id) if row.task_id else None,
            mission_title=row.mission_title,
            task_title=row.task_title,
            level=row.level or "info",
            message=row.message,
            timestamp=row.timestamp.isoformat() if row.timestamp else "",
            data=row.data,
        ).model_dump()
        for row in rows
    ]

    return paginated(items=items, total=total, page=page, per_page=per_page)


# ── Aggregate Stats ───────────────────────────────────────────────────────────


@router.get("/stats")
@router.get("/stats/")
async def get_dashboard_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate dashboard statistics for the current user."""
    # Total and status counts
    status_result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Mission.status == MissionStatus.COMPLETED).label("completed"),
            func.count().filter(Mission.status == MissionStatus.FAILED).label("failed"),
        ).where(
            Mission.user_id == user.id,
            Mission.deleted_at.is_(None),
        )
    )
    status_row = status_result.one()

    total_missions = status_row.total or 0
    completed = status_row.completed or 0
    failed = status_row.failed or 0
    success_rate = round(completed / total_missions * 100, 1) if total_missions > 0 else 0.0

    # Average duration
    dur_result = await db.execute(
        select(
            func.avg(
                func.extract(
                    "epoch",
                    Mission.completed_at - func.coalesce(Mission.started_at, Mission.created_at),
                )
            )
        ).where(
            Mission.user_id == user.id,
            Mission.status.in_([MissionStatus.COMPLETED, MissionStatus.FAILED]),
            Mission.deleted_at.is_(None),
        )
    )
    avg_duration = round(float(dur_result.scalar() or 0), 1)

    # Total cost
    cost_result = await db.execute(
        select(func.coalesce(func.sum(LLMCallRecord.cost_usd), 0.0))
        .join(Mission, Mission.id == LLMCallRecord.mission_id)
        .where(Mission.user_id == user.id)
    )
    total_cost = round(float(cost_result.scalar() or 0), 6)

    # Total tokens
    tokens_result = await db.execute(
        select(func.coalesce(func.sum(Mission.tokens_used), 0)).where(
            Mission.user_id == user.id, Mission.deleted_at.is_(None)
        )
    )
    total_tokens = int(tokens_result.scalar() or 0)

    return ok(
        DashboardStats(
            total_missions=total_missions,
            completed_missions=completed,
            failed_missions=failed,
            success_rate=success_rate,
            avg_duration_seconds=avg_duration,
            total_cost=total_cost,
            total_tokens=total_tokens,
        ).model_dump()
    )
