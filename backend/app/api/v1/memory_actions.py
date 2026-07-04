"""Memory Action API — episode traces and proficiency scores (AutoMem Phase 1).

GET /memory-actions/mission/{mission_id}        → list memory actions for a mission
GET /memory-actions/mission/{mission_id}/score   → memory proficiency score
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.memory_action_service import MemoryActionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory-actions", tags=["memory-actions"])


@router.get("/mission/{mission_id}")
async def get_mission_memory_actions(
    mission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return all memory actions for a mission, ordered by time.

    Requires the user to own or have access to the mission.
    """
    from app.services.mission_errors import MissionNotFoundError
    from app.services.mission_service import require_mission_access

    try:
        await require_mission_access(db, mission_id, user.id)
    except MissionNotFoundError:
        raise HTTPException(status_code=404, detail="Mission not found")

    service = MemoryActionService(db)
    events = await service.get_episode_traces(str(mission_id))

    return [
        {
            "id": str(e.id),
            "workspace_id": str(e.workspace_id),
            "user_id": e.user_id,
            "mission_id": str(e.mission_id) if e.mission_id else None,
            "action_type": e.action_type,
            "action_input": e.action_input,
            "action_result": e.action_result,
            "action_latency_ms": e.action_latency_ms,
            "action_success": e.action_success,
            "agent_confidence": e.agent_confidence,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.get("/mission/{mission_id}/score")
async def get_mission_memory_score(
    mission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return memory proficiency score for a mission's episode.

    Includes total/successful/failed counts, average latency,
    and per-action-type breakdown.
    """
    from app.services.mission_errors import MissionNotFoundError
    from app.services.mission_service import require_mission_access

    try:
        await require_mission_access(db, mission_id, user.id)
    except MissionNotFoundError:
        raise HTTPException(status_code=404, detail="Mission not found")

    service = MemoryActionService(db)
    return await service.score_episode(str(mission_id))
