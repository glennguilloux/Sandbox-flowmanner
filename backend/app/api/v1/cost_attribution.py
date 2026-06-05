"""Cost Attribution API — Phase 6.3.

Endpoints:
- GET /costs/summary       — Aggregate cost summary with flexible grouping
- GET /costs/mission/{id}  — Cost breakdown for a specific mission
- GET /costs/dashboard     — Dashboard data (daily time series + top agents)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_workspace_id
from app.database import get_db
from app.services.cost_attribution_service import CostAttributionService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/costs", tags=["cost-attribution"])


@router.get("/summary")
async def cost_summary(
    group_by: str = Query("day", description="Group by: day, agent, mission, model, provider, workspace"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    agent_id: str | None = Query(None),
    mission_id: str | None = Query(None),
    workspace_id: str | None = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get cost aggregates with flexible grouping and filtering."""
    service = CostAttributionService(db)
    return await service.get_aggregates(
        workspace_id=workspace_id,
        agent_id=agent_id,
        mission_id=mission_id,
        group_by=group_by,
        days=days,
    )


@router.get("/mission/{mission_id}")
async def mission_cost(
    mission_id: str,
    group_by: str = Query("model", description="Group by: model, provider, agent, day"),
    days: int = Query(90, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get cost breakdown for a specific mission."""
    service = CostAttributionService(db)
    total = await service.get_mission_cost(mission_id)
    breakdown = await service.get_aggregates(
        mission_id=mission_id,
        group_by=group_by,
        days=days,
    )
    return {
        "mission": total,
        "breakdown": breakdown["breakdown"],
        "period": breakdown["period"],
    }


@router.get("/dashboard")
async def cost_dashboard(
    days: int = Query(30, ge=1, le=365),
    workspace_id: str | None = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard data: daily time series + top agents + top models."""
    service = CostAttributionService(db)

    daily = await service.get_aggregates(
        workspace_id=workspace_id, group_by="day", days=days,
    )
    by_agent = await service.get_aggregates(
        workspace_id=workspace_id, group_by="agent", days=days,
    )
    by_model = await service.get_aggregates(
        workspace_id=workspace_id, group_by="model", days=days,
    )

    return {
        "period": daily["period"],
        "totals": daily["totals"],
        "daily": daily["breakdown"],
        "by_agent": by_agent["breakdown"][:10],
        "by_model": by_model["breakdown"][:10],
    }
