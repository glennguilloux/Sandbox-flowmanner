from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.dashboard import (
    DashboardAnalyticsResponse,
    FirefightingMetricsResponse,
)
from app.services.dashboard_service import (
    get_dashboard_analytics,
    get_firefighting_metrics,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


async def get_current_admin_user(user: dict = Depends(get_current_user)):
    """Dependency to ensure user is an admin."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return user


@router.get("/analytics", response_model=DashboardAnalyticsResponse)
async def read_dashboard_analytics(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin_user),
):
    try:
        return await get_dashboard_analytics(db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/firefighting-metrics", response_model=FirefightingMetricsResponse)
async def read_firefighting_metrics(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_current_admin_user),
):
    try:
        """
        Retrieve firefighting metrics for failed missions in the last `hours` period.
        Satisfies: AC-1, AC-2, AC-3, AC-4
        """
        return await get_firefighting_metrics(db, hours)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
