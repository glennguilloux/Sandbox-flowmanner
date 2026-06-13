"""Substrate event API — H5.2 replay endpoints.

Provides:
- GET /missions/{mission_id}/events — fetch substrate event log for a mission
- GET /missions/{mission_id}/replay-state — rebuild run state from event log
- GET /missions/{mission_id}/event/{sequence} — fetch a single event and its state
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.database import get_db
from app.models.mission_advanced_models import MissionTemplate
from app.services.mission_errors import MissionNotFoundError
from app.services.mission_service import require_mission_access
from app.services.substrate.assertion_engine import get_assertion_engine
from app.services.substrate.replay_engine import get_replay_engine
from app.services.substrate.replay_query import get_replay_query

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.mission_models import Mission
    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/missions", tags=["substrate"])

DEFAULT_EVENT_LIMIT = 100
MAX_EVENT_LIMIT = 1_000


def _not_found(detail: str = "Not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


async def _require_mission_access(db: AsyncSession, mission_id: UUID, user: User) -> Mission:
    try:
        return await require_mission_access(db, mission_id, user.id)
    except MissionNotFoundError as exc:
        raise _not_found(str(exc)) from exc


def _mission_summary(mission: Mission) -> dict:
    return {
        "id": str(mission.id),
        "title": mission.title,
        "status": mission.status,
    }


def _parse_csv_event_types(event_type: str | None) -> list[str] | None:
    if event_type is None:
        return None

    event_types: list[str] = []
    seen: set[str] = set()
    for raw_type in event_type.split(","):
        normalized = raw_type.strip()
        if not normalized or normalized in seen:
            continue
        event_types.append(normalized)
        seen.add(normalized)

    return event_types or None


def _parse_int_param(value: int | str | None, *, name: str, default: int | None = None) -> int | None:
    if value is None:
        if default is None:
            return None
        value = default

    if isinstance(value, str):
        value = value.strip()
        if value == "":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} must be an integer")

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} must be an integer") from exc

    if parsed < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} must be >= 0")

    return parsed


def _parse_limit(value: int | str | None) -> int:
    parsed = _parse_int_param(value, name="limit", default=DEFAULT_EVENT_LIMIT)
    if parsed < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be >= 1")
    if parsed > MAX_EVENT_LIMIT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"limit must be <= {MAX_EVENT_LIMIT}")
    return parsed


def _validate_event_range(*, after_sequence: int | None, from_sequence: int, to_sequence: int | None) -> None:
    lower = from_sequence if after_sequence is None else after_sequence + 1
    if to_sequence is not None and to_sequence < lower:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="to_sequence must be >= from_sequence")


def _serialize_event(event) -> dict:
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


def _normalize_replay_page(page: Any) -> tuple[list[Any], int, int | None]:
    if isinstance(page, dict):
        events = list(page.get("events", []))
        total = page.get("total", len(events))
        cursor = page.get("next_after_sequence", page.get("cursor"))
        return events, int(total) if total is not None else len(events), cursor

    if isinstance(page, tuple):
        if len(page) == 2:
            events, total = page
            return list(events), int(total), None
        if len(page) == 3:
            events, total, cursor = page
            return list(events), int(total), cursor
        raise ValueError("Replay query page tuple must contain 2 or 3 values")

    events = list(getattr(page, "events", []))
    total = getattr(page, "total", len(events))
    cursor = getattr(page, "next_after_sequence", getattr(page, "cursor", None))
    return events, int(total), cursor


async def _get_replay_query_page(
    db: AsyncSession,
    *,
    mission: Mission,
    run_id: str,
    event_types: list[str] | None,
    after_sequence: int | None,
    from_sequence: int,
    to_sequence: int | None,
    limit: int,
) -> tuple[list[Any], int, int | None]:
    page = await get_replay_query().get_events_for_mission(
        db,
        mission=mission,
        run_id=run_id,
        event_types=event_types,
        after_sequence=after_sequence,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
        limit=limit,
    )
    return _normalize_replay_page(page)


async def _get_replay_event_page(
    db: AsyncSession,
    *,
    mission: Mission,
    run_id: str,
    sequence: int,
) -> tuple[list[Any], int, int | None]:
    page = await get_replay_query().get_event_at_sequence(db, mission=mission, run_id=run_id, sequence=sequence)
    events, total, cursor = _normalize_replay_page(page)
    return events[:1], 1 if events else total, cursor

@router.get("/{mission_id}/events")
async def get_mission_events(
    mission_id: UUID,
    from_sequence: int | str = "0",
    to_sequence: int | str | None = None,
    event_type: str | None = None,
    after_sequence: int | str | None = None,
    limit: int | str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch the substrate event log for a mission.

    Args:
        mission_id: Mission UUID.
        from_sequence: Inclusive lower bound (default: 0).
        to_sequence: Inclusive upper bound (default: no bound).
        event_type: Optional CSV filter by event type (e.g., "task.completed,tool.call").
        after_sequence: Inclusive cursor; returns events with sequence > after_sequence.
        limit: Max events to return (default: 100, max: 1000).

    Returns:
        dict with:
        - events: list of serialized events
        - total: total event count for this run
        - mission: { id, title, status }
        - run_id: the substrate run ID
        - next_after_sequence: cursor for the next page, when another page exists
    """
    parsed_from_sequence = _parse_int_param(from_sequence, name="from_sequence", default=0) or 0
    parsed_to_sequence = _parse_int_param(to_sequence, name="to_sequence")
    parsed_after_sequence = _parse_int_param(after_sequence, name="after_sequence")
    parsed_limit = _parse_limit(limit)
    event_types = _parse_csv_event_types(event_type)
    _validate_event_range(
        after_sequence=parsed_after_sequence,
        from_sequence=parsed_from_sequence,
        to_sequence=parsed_to_sequence,
    )

    mission = await _require_mission_access(db, mission_id, user)

    run_id = mission.plan.get("substrate_run_id") if mission.plan else None
    if not run_id:
        return {
            "events": [],
            "total": 0,
            "mission": _mission_summary(mission),
            "run_id": None,
            "message": "Mission has no substrate run (may not have been executed with substrate)",
        }

    events, total, cursor = await _get_replay_query_page(
        db,
        mission=mission,
        run_id=str(run_id),
        event_types=event_types,
        after_sequence=parsed_after_sequence,
        from_sequence=parsed_from_sequence,
        to_sequence=parsed_to_sequence,
        limit=parsed_limit,
    )

    return {
        "events": [_serialize_event(event) for event in events],
        "total": total,
        "mission": _mission_summary(mission),
        "run_id": str(run_id),
        "next_after_sequence": cursor,
    }


@router.get("/{mission_id}/replay-state")
async def get_mission_replay_state(
    mission_id: UUID,
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
    mission = await _require_mission_access(db, mission_id, user)

    run_id = mission.plan.get("substrate_run_id") if mission.plan else None
    if not run_id:
        raise _not_found("Mission has no substrate run ID")

    replay = get_replay_engine()

    if at_sequence is not None:
        state = await replay.rebuild_state_at_sequence(db, str(run_id), at_sequence)
    else:
        state = await replay.rebuild_state(db, str(run_id))

    response = {
        "run_id": str(run_id),
        "mission_id": str(mission.id),
        "state": state.to_dict(),
    }

    template_id = (mission.plan or {}).get("template_id")
    if template_id:
        template = await db.get(MissionTemplate, str(template_id))
        if template and template.expected_behaviors:
            engine = get_assertion_engine()
            results = await engine.evaluate(db, str(run_id), template.expected_behaviors)
            response["assertion_results"] = [r.to_dict() for r in results]

    return response


@router.get("/{mission_id}/event/{sequence}")
async def get_mission_event_at_sequence(
    mission_id: UUID,
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
    if sequence < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sequence must be >= 0")

    mission = await _require_mission_access(db, mission_id, user)

    run_id = mission.plan.get("substrate_run_id") if mission.plan else None
    if not run_id:
        raise _not_found("Mission has no substrate run ID")

    events, _, _ = await _get_replay_event_page(db, mission=mission, run_id=str(run_id), sequence=sequence)

    if not events:
        raise _not_found(f"No event at sequence {sequence}")

    replay = get_replay_engine()
    state = await replay.rebuild_state_at_sequence(db, str(run_id), sequence)

    return {
        "event": _serialize_event(events[0]),
        "state_at_sequence": state.to_dict(),
    }
