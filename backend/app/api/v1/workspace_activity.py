"""
Workspace Activity Feed API — returns recent workspace activity events
by querying the analytics_events table (no new DB schema needed).

GET /api/workspaces/{workspace_id}/activity  — paginated activity feed
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.analytics import AnalyticsEvent
from app.models.user import User
from app.models.workspace_models import WorkspaceMember

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspace_activity"])

ACTIVITY_EVENT_TYPES = [
    "role_changed",
    "message_sent",
    "member_online",
    "mission_started",
    "mission_completed",
    "mission_failed",
    "mission_aborted",
    "member_joined",
    "member_invited",
    "team_created",
    "agent_deployed",
]


class ActivityItemResponse(BaseModel):
    id: int
    event_type: str
    user_id: str
    actor_name: str | None = None
    target_name: str | None = None
    description: str | None = None
    created_at: str
    properties: dict | None = None


async def _verify_membership(db: AsyncSession, workspace_id: str, user_id: int) -> None:
    """Raise 403 if user is not an active workspace member."""
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.is_active == True,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a member of this workspace")


@router.get("/{workspace_id}/activity")
async def get_workspace_activity(
    workspace_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: str | None = Query(
        None,
        description="Filter by event type: role_changed, message_sent, member_online, mission_event",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return recent workspace activity events.

    Filters analytics_events by workspace_id (stored in JSON properties)
    and event_type using database-level JSON operators.
    """
    await _verify_membership(db, workspace_id, current_user.id)

    types_to_fetch = [event_type] if event_type else ACTIVITY_EVENT_TYPES

    # Use SQLAlchemy JSON path operator to filter at the database level
    stmt = (
        select(AnalyticsEvent)
        .where(
            AnalyticsEvent.event_type.in_(types_to_fetch),
            AnalyticsEvent.properties["workspace_id"].as_string() == workspace_id,
        )
        .order_by(desc(AnalyticsEvent.timestamp))
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(stmt)
    events = result.scalars().all()

    return [
        ActivityItemResponse(
            id=e.id,
            event_type=e.event_type,
            user_id=e.user_id,
            actor_name=(e.properties or {}).get("actor_name"),
            target_name=(e.properties or {}).get("target_name"),
            description=(e.properties or {}).get("description"),
            created_at=e.timestamp.isoformat() if e.timestamp else "",
            properties=e.properties,
        )
        for e in events
    ]


# ---------------------------------------------------------------------------
# Helper — record a workspace activity event (caller manages transaction)
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/overview")
async def get_workspace_overview(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Workspace Command Center overview — aggregated stats in one call.

    Returns active mission count, total agents, pending inbox items,
    online members, monthly cost, and recent activity.
    """
    from sqlalchemy import func

    from app.models.agent import Agent
    from app.models.hitl_models import InboxItem, InboxItemStatus
    from app.models.mission_models import Mission
    from app.services.cost_attribution_service import CostAttributionService

    await _verify_membership(db, workspace_id, current_user.id)

    # Active missions count
    mission_result = await db.execute(
        select(func.count())
        .select_from(Mission)
        .where(
            Mission.workspace_id == workspace_id,
            Mission.status.in_(["running", "executing", "pending", "planned"]),
        )
    )
    active_missions = mission_result.scalar() or 0

    # Total missions
    total_missions_result = await db.execute(
        select(func.count())
        .select_from(Mission)
        .where(
            Mission.workspace_id == workspace_id,
        )
    )
    total_missions = total_missions_result.scalar() or 0

    # Total agents
    agent_result = await db.execute(
        select(func.count())
        .select_from(Agent)
        .where(
            Agent.workspace_id == workspace_id,
        )
    )
    total_agents = agent_result.scalar() or 0

    # Pending inbox items
    inbox_result = await db.execute(
        select(func.count())
        .select_from(InboxItem)
        .where(
            InboxItem.user_id == current_user.id,
            InboxItem.workspace_id == workspace_id,
            InboxItem.status == InboxItemStatus.PENDING.value,
        )
    )
    pending_inbox = inbox_result.scalar() or 0

    # Online members
    from app.models.workspace_models import WorkspaceMember

    member_count_result = await db.execute(
        select(func.count())
        .select_from(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.is_active == True,
        )
    )
    total_members = member_count_result.scalar() or 0

    # Monthly cost
    cost_service = CostAttributionService(db)
    try:
        cost_data = await cost_service.get_aggregates(
            workspace_id=workspace_id,
            group_by="day",
            days=30,
        )
        monthly_cost = cost_data.get("totals", {}).get("total_cost_usd", 0)
    except Exception:
        monthly_cost = 0

    # Recent activity (last 10 events)
    types_to_fetch = ACTIVITY_EVENT_TYPES
    activity_stmt = (
        select(AnalyticsEvent)
        .where(
            AnalyticsEvent.event_type.in_(types_to_fetch),
            AnalyticsEvent.properties["workspace_id"].as_string() == workspace_id,
        )
        .order_by(desc(AnalyticsEvent.timestamp))
        .limit(10)
    )
    activity_result = await db.execute(activity_stmt)
    recent_events = activity_result.scalars().all()

    recent_activity = [
        {
            "id": e.id,
            "event_type": e.event_type,
            "user_id": e.user_id,
            "actor_name": (e.properties or {}).get("actor_name"),
            "description": (e.properties or {}).get("description"),
            "created_at": e.timestamp.isoformat() if e.timestamp else "",
        }
        for e in recent_events
    ]

    return {
        "active_missions": active_missions,
        "total_missions": total_missions,
        "total_agents": total_agents,
        "total_members": total_members,
        "pending_inbox": pending_inbox,
        "monthly_cost_usd": round(monthly_cost, 4),
        "recent_activity": recent_activity,
    }


async def record_workspace_activity(
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
    event_type: str,
    *,
    actor_name: str | None = None,
    target_name: str | None = None,
    description: str | None = None,
    extra_properties: dict | None = None,
) -> None:
    """Record a workspace activity event — fire-and-forget, never raises.

    Adds an AnalyticsEvent to *db* but does NOT commit — the caller
    should commit/rollback its own transaction as needed.
    """
    try:
        props: dict = {"workspace_id": workspace_id}
        if actor_name:
            props["actor_name"] = actor_name
        if target_name:
            props["target_name"] = target_name
        if description:
            props["description"] = description
        if extra_properties:
            props.update(extra_properties)

        event = AnalyticsEvent(
            user_id=user_id,
            event_type=event_type,
            properties=props,
        )
        db.add(event)
    except Exception as e:
        logger.warning(
            "Failed to record workspace activity %s for ws %s: %s",
            event_type,
            workspace_id,
            e,
        )
