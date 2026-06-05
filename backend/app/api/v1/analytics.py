"""Analytics API routes."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.analytics_service import track_event, track_events_batch

router = APIRouter(tags=["analytics"])


@router.get("/runs")
async def get_run_history(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return run history entries — mission runs joined with mission titles."""
    offset = (page - 1) * per_page

    # Count total runs for this user
    count_query = text("""
        SELECT COUNT(*) FROM mission_runs mr
        JOIN missions m ON m.id::text = mr.mission_id::text
        WHERE m.user_id = :uid
    """)
    total_result = await db.execute(count_query, {"uid": current_user.id})
    total = total_result.scalar() or 0

    # Fetch paginated runs with mission title
    data_query = text("""
        SELECT
            mr.id::text,
            mr.mission_id::text,
            m.title AS mission_name,
            mr.status,
            mr.started_at,
            mr.completed_at,
            mr.duration_seconds,
            mr.error_message,
            mr.tokens_used,
            mr.actual_cost
        FROM mission_runs mr
        JOIN missions m ON m.id::text = mr.mission_id::text
        WHERE m.user_id = :uid
        ORDER BY mr.created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    rows_result = await db.execute(
        data_query,
        {"uid": current_user.id, "limit": per_page, "offset": offset},
    )

    runs = []
    for row in rows_result.fetchall():
        started = row[4]
        ended = row[5]
        dur = row[6]
        duration_ms = None
        if dur is not None:
            duration_ms = int(dur * 1000)
        elif started and ended:
            duration_ms = int((ended - started).total_seconds() * 1000)
        elif started:
            duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)

        runs.append({
            "id": row[0],
            "mission_id": row[1],
            "mission_name": row[2],
            "status": row[3],
            "started_at": row[4].isoformat() if row[4] else None,
            "ended_at": row[5].isoformat() if row[5] else None,
            "duration_ms": duration_ms,
            "error_message": row[7],
            "tokens_used": row[8],
            "actual_cost": row[9],
        })

    return {
        "data": runs,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


class TrackEventRequest(BaseModel):
    user_id: str
    event_type: str
    properties: dict[str, Any] | None = None
    session_id: str | None = None


class TrackBatchRequest(BaseModel):
    events: list[TrackEventRequest]


@router.post("/events")
async def track_single_event(
    req: TrackEventRequest,
    db: AsyncSession = Depends(get_db),
):
    """Track a single analytics event. Fire-and-forget from frontend."""
    await track_event(db, req.user_id, req.event_type, req.properties, req.session_id)
    return {"status": "ok"}


@router.post("/events/batch")
async def track_batch_events(
    req: TrackBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Track multiple events at once (e.g., on page unload)."""
    events = [
        {"user_id": e.user_id, "event_type": e.event_type,
         "properties": e.properties, "session_id": e.session_id}
        for e in req.events
    ]
    await track_events_batch(db, events)
    return {"status": "ok", "count": len(events)}
