"""Substrate event API — H5.2 replay endpoints.

Provides:
- GET /missions/{mission_id}/events — fetch substrate event log for a mission
- GET /missions/{mission_id}/replay-state — rebuild run state from event log
- GET /missions/{mission_id}/event/{sequence} — fetch a single event and its state
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select as sa_select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.mission_advanced_models import MissionTemplate
from app.services.mission_service import get_mission
from app.services.substrate.assertion_engine import get_assertion_engine
from app.services.substrate.event_log import get_event_log
from app.services.substrate.replay_engine import get_replay_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/missions", tags=["substrate"])


def _not_found(detail: str = "Not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _require_owner(mission, user: User) -> None:
    if mission is None or mission.user_id != user.id:
        raise _not_found()


def _serialize_event(event) -> dict:
    """Serialize a SubstrateEvent ORM object to a JSON-safe dict."""
    return {
        "id": str(event.id) if event.id else None,
        "sequence": event.sequence,
        "run_id": str(event.run_id) if event.run_id else None,
        "mission_id": str(event.mission_id) if event.mission_id else None,
        "task_id": str(event.task_id) if event.task_id else None,
        "type": event.type,
        "payload": event.payload,
        "causal_parent": event.causal_parent,
        "actor": event.actor,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
    }


@router.get("/{mission_id}/events")
async def get_mission_events(
    mission_id: uuid.UUID,
    from_sequence: int = 0,
    to_sequence: int | None = None,
    event_type: str | None = None,
    limit: int = 1_000,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch the substrate event log for a mission.

    Args:
        mission_id: Mission UUID.
        from_sequence: Inclusive lower bound (default: 0).
        to_sequence: Inclusive upper bound (default: no bound).
        event_type: Optional filter by event type (e.g., "task.completed").
        limit: Max events to return (default: 1000).

    Returns:
        dict with:
        - events: list of serialized events
        - total: total event count for this run
        - mission: { id, title, status }
        - run_id: the substrate run ID
    """
    mission = await get_mission(db, mission_id)
    _require_owner(mission, user)

    # Find the substrate run_id from the mission plan
    run_id = mission.plan.get("substrate_run_id") if mission.plan else None
    if not run_id:
        return {
            "events": [],
            "total": 0,
            "mission": {
                "id": str(mission.id),
                "title": mission.title,
                "status": mission.status,
            },
            "run_id": None,
            "message": "Mission has no substrate run (may not have been executed with substrate)",
        }

    event_log = get_event_log()
    events = await event_log.get_events(
        db,
        run_id,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
        event_type=event_type,
        limit=limit,
    )

    serialized = [_serialize_event(e) for e in events]

    return {
        "events": serialized,
        "total": len(serialized),
        "mission": {
            "id": str(mission.id),
            "title": mission.title,
            "status": mission.status,
        },
        "run_id": run_id,
    }


@router.get("/{mission_id}/replay-state")
async def get_mission_replay_state(
    mission_id: uuid.UUID,
    at_sequence: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Rebuild the run state from the event log.

    This enables time-travel debugging: "what did mission X look like
    after event 42?"

    Args:
        mission_id: Mission UUID.
        at_sequence: If set, rebuild state as of this sequence.
                     If None, rebuild to the latest state.

    Returns:
        dict with run state: status, sequence, completed_tasks, etc.
    """
    mission = await get_mission(db, mission_id)
    _require_owner(mission, user)

    run_id = mission.plan.get("substrate_run_id") if mission.plan else None
    if not run_id:
        raise _not_found("Mission has no substrate run ID")

    replay = get_replay_engine()

    if at_sequence is not None:
        state = await replay.rebuild_state_at_sequence(db, run_id, at_sequence)
    else:
        state = await replay.rebuild_state(db, run_id)

    response = {
        "run_id": run_id,
        "mission_id": str(mission.id),
        "state": state.to_dict(),
    }

    # Include assertion results if the mission's template has expected_behaviors
    template_id = (mission.plan or {}).get("template_id")
    if template_id:
        try:
            tpl_result = await db.execute(sa_select(MissionTemplate).where(MissionTemplate.id == str(template_id)))
            template = tpl_result.scalar_one_or_none()
            if template and template.expected_behaviors:
                engine = get_assertion_engine()
                results = await engine.evaluate(db, run_id, template.expected_behaviors)
                response["assertion_results"] = [r.to_dict() for r in results]
        except Exception as exc:
            logger.warning("Could not evaluate assertions for mission %s: %s", mission_id, exc)

    return response


@router.get("/{mission_id}/event/{sequence}")
async def get_mission_event_at_sequence(
    mission_id: uuid.UUID,
    sequence: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch a single event and the state as of that event.

    Args:
        mission_id: Mission UUID.
        sequence: The event sequence number.

    Returns:
        dict with event and state_at_sequence.
    """
    mission = await get_mission(db, mission_id)
    _require_owner(mission, user)

    run_id = mission.plan.get("substrate_run_id") if mission.plan else None
    if not run_id:
        raise _not_found("Mission has no substrate run ID")

    event_log = get_event_log()
    events = await event_log.get_events(
        db,
        run_id,
        from_sequence=sequence,
        to_sequence=sequence,
        limit=1,
    )

    if not events:
        raise _not_found(f"No event at sequence {sequence}")

    replay = get_replay_engine()
    state = await replay.rebuild_state_at_sequence(db, run_id, sequence)

    return {
        "event": _serialize_event(events[0]),
        "state_at_sequence": state.to_dict(),
    }
