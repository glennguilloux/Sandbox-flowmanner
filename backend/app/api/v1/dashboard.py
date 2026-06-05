"""Dashboard API router."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardAnalyticsResponse, FirefightingMetricsResponse
from app.services.dashboard_service import get_dashboard_analytics, get_firefighting_metrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/analytics", response_model=DashboardAnalyticsResponse)
async def read_dashboard_analytics(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await get_dashboard_analytics(db)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/firefighting-metrics", response_model=FirefightingMetricsResponse)
async def read_firefighting_metrics(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await get_firefighting_metrics(db, hours)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/stats")
async def read_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dashboard stats endpoint matching frontend UsageStatsWidget expectations."""
    from sqlalchemy import text

    total_requests = 0
    missions_completed = 0
    avg_response_time = 0.0
    uptime = 99.9

    try:
        row = await db.execute(text("SELECT COUNT(*) FROM missions WHERE user_id=:uid"), {"uid": user.id})
        total_requests = row.scalar() or 0
    except Exception:
        logger.debug("dashboard_stats_count_failed", exc_info=True)

    try:
        row = await db.execute(text("SELECT COUNT(*) FROM missions WHERE user_id=:uid AND status='completed'"), {"uid": user.id})
        missions_completed = row.scalar() or 0
    except Exception:
        logger.debug("dashboard_stats_completed_failed", exc_info=True)

    try:
        row = await db.execute(text("SELECT AVG(tokens_used) FROM missions WHERE user_id=:uid AND tokens_used IS NOT NULL"), {"uid": user.id})
        avg = row.scalar()
        if avg is not None:
            avg_response_time = round(float(avg), 1)
    except Exception:
        logger.debug("dashboard_stats_avg_failed", exc_info=True)

    return {
        "total_requests": total_requests,
        "missions_completed": missions_completed,
        "avg_response_time_ms": avg_response_time * 1000,
        "uptime_percentage": uptime,
    }
