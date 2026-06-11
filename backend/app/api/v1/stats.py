"""Dashboard stats endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate dashboard stats from all tables for the current user."""
    uid = current_user.id
    stats = {}

    # Missions counts
    try:
        rows = await db.execute(
            text("SELECT status, COUNT(*) FROM missions WHERE user_id=:uid GROUP BY status"),
            {"uid": uid},
        )
        stats["missions"] = {row[0]: row[1] for row in rows.fetchall()}
    except Exception:
        stats["missions"] = {}

    # Workflow runs counts
    try:
        rows = await db.execute(
            text("SELECT status, COUNT(*) FROM workflow_runs WHERE user_id=:uid GROUP BY status"),
            {"uid": uid},
        )
        stats["workflow_runs"] = {row[0]: row[1] for row in rows.fetchall()}
    except Exception:
        stats["workflow_runs"] = {}

    # Agents count
    try:
        rows = await db.execute(
            text("SELECT COUNT(*) FROM ai_agents WHERE user_id=:uid"),
            {"uid": uid},
        )
        stats["agents"] = rows.scalar() or 0
    except Exception:
        stats["agents"] = 0

    return {
        "total_requests": stats.get("missions", {}).get("completed", 0)
        + stats.get("workflow_runs", {}).get("completed", 0),
        "active_agents": stats.get("agents", 0),
        "missions_completed": stats.get("missions", {}).get("completed", 0),
        "avg_response_ms": 0,
        "raw": stats,
    }
