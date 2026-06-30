"""External Events API — observability and replay for the durable event bus.

Provides endpoints to query inbound integration events (ExternalEvent rows)
and replay failed/processed events through the consumer pipeline.

This is the observability layer for the durable event bus: every webhook
delivery from 21+ integrations is persisted here before any side-effects,
giving a complete audit trail with replay capability.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.external_event_model import ExternalEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/external-events", tags=["external-events"])


@router.get("")
async def list_external_events(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    source: str | None = Query(None, description="Filter by integration source (e.g. 'github', 'stripe')"),
    event_type: str | None = Query(None, description="Filter by event type (e.g. 'pull_request.opened')"),
    status: str | None = Query(None, description="Filter by status: pending, processed, failed"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List inbound integration events with filtering and pagination.

    Returns events scoped to the current user (if user_id is set on the event).
    Events without a user_id are visible to all authenticated users (system-wide events).
    """
    offset = (page - 1) * limit

    # Build filter conditions
    conditions = []
    if source:
        conditions.append(ExternalEvent.source == source)
    if event_type:
        conditions.append(ExternalEvent.event_type == event_type)
    if status:
        conditions.append(ExternalEvent.status == status)

    # Scope to user's events + system-wide events (user_id IS NULL)
    user_scope = or_(ExternalEvent.user_id == user.id, ExternalEvent.user_id.is_(None))
    conditions.append(user_scope)

    # Count
    count_q = select(func.count(ExternalEvent.id)).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch
    q = select(ExternalEvent).where(*conditions).order_by(ExternalEvent.received_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    events = result.scalars().all()

    return {
        "events": [
            {
                "id": str(ev.id),
                "source": ev.source,
                "event_type": ev.event_type,
                "delivery_id": ev.delivery_id,
                "user_id": ev.user_id,
                "status": ev.status,
                "triggers_fired": ev.triggers_fired,
                "error_message": ev.error_message,
                "payload": ev.payload,
                "received_at": ev.received_at.isoformat() if ev.received_at else None,
                "processed_at": ev.processed_at.isoformat() if ev.processed_at else None,
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
            }
            for ev in events
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/stats")
async def get_external_event_stats(
    days: int = Query(7, ge=1, le=90, description="Time window in days for time-series data"),
    bucket: str = Query("day", description="Time bucket: hour, day, or week"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Aggregated stats for inbound integration events.

    Returns per-source counts, status breakdown, per-event-type breakdown,
    time-series data (events per bucket), and recent activity.
    """
    from datetime import timedelta

    from sqlalchemy import text as sa_text

    user_scope = or_(ExternalEvent.user_id == user.id, ExternalEvent.user_id.is_(None))
    now = datetime.now(UTC)
    window_start = now - timedelta(days=days)

    # ── Totals (all time) ──────────────────────────────────────────
    total_q = select(func.count(ExternalEvent.id)).where(user_scope)
    total = (await db.execute(total_q)).scalar() or 0

    # ── Per-source breakdown (all time) ────────────────────────────
    source_q = (
        select(ExternalEvent.source, func.count(ExternalEvent.id))
        .where(user_scope)
        .group_by(ExternalEvent.source)
        .order_by(func.count(ExternalEvent.id).desc())
    )
    source_result = await db.execute(source_q)
    by_source = {row[0]: row[1] for row in source_result.all()}

    # ── Per-status breakdown (all time) ────────────────────────────
    status_q = (
        select(ExternalEvent.status, func.count(ExternalEvent.id)).where(user_scope).group_by(ExternalEvent.status)
    )
    status_result = await db.execute(status_q)
    by_status = {row[0]: row[1] for row in status_result.all()}

    # ── Per-event-type breakdown (window) ──────────────────────────
    type_q = (
        select(ExternalEvent.event_type, func.count(ExternalEvent.id))
        .where(user_scope, ExternalEvent.received_at >= window_start)
        .group_by(ExternalEvent.event_type)
        .order_by(func.count(ExternalEvent.id).desc())
        .limit(20)
    )
    type_result = await db.execute(type_q)
    by_event_type = {row[0]: row[1] for row in type_result.all()}

    # ── Per-source error rate (window) ─────────────────────────────
    source_total_q = (
        select(ExternalEvent.source, func.count(ExternalEvent.id))
        .where(user_scope, ExternalEvent.received_at >= window_start)
        .group_by(ExternalEvent.source)
    )
    source_failed_q = (
        select(ExternalEvent.source, func.count(ExternalEvent.id))
        .where(user_scope, ExternalEvent.status == "failed", ExternalEvent.received_at >= window_start)
        .group_by(ExternalEvent.source)
    )
    source_totals = {row[0]: row[1] for row in (await db.execute(source_total_q)).all()}
    source_failures = {row[0]: row[1] for row in (await db.execute(source_failed_q)).all()}
    error_rates = {
        src: round(source_failures.get(src, 0) / count, 3) if count else 0.0 for src, count in source_totals.items()
    }

    # ── Total triggers fired (all time) ────────────────────────────
    triggers_q = select(func.sum(ExternalEvent.triggers_fired)).where(user_scope)
    total_triggers = (await db.execute(triggers_q)).scalar() or 0

    # ── Time-series: events per bucket (window) ────────────────────
    bucket_interval = {"hour": "hour", "day": "day", "week": "week"}.get(bucket, "day")
    ts_q = sa_text(
        "SELECT date_trunc(:bucket, received_at) AS bucket, "
        "       source, "
        "       COUNT(*) AS count, "
        "       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failures "
        "FROM external_events "
        "WHERE (user_id = :uid OR user_id IS NULL) "
        "  AND received_at >= :window_start "
        "GROUP BY bucket, source "
        "ORDER BY bucket, source"
    )
    ts_result = await db.execute(
        ts_q,
        {
            "bucket": bucket_interval,
            "uid": user.id,
            "window_start": window_start,
        },
    )
    time_series = [
        {
            "bucket": row[0].isoformat() if row[0] else None,
            "source": row[1],
            "count": row[2],
            "failures": row[3],
        }
        for row in ts_result.all()
    ]

    return {
        "total_events": total,
        "total_triggers_fired": total_triggers,
        "by_source": by_source,
        "by_status": by_status,
        "by_event_type": by_event_type,
        "error_rates": error_rates,
        "time_series": time_series,
        "window_days": days,
        "bucket": bucket,
    }


@router.get("/{event_id}")
async def get_external_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a single external event by ID, including the raw webhook body."""
    result = await db.execute(select(ExternalEvent).where(ExternalEvent.id == event_id))
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="External event not found")

    return {
        "event": {
            "id": str(ev.id),
            "source": ev.source,
            "event_type": ev.event_type,
            "delivery_id": ev.delivery_id,
            "user_id": ev.user_id,
            "status": ev.status,
            "triggers_fired": ev.triggers_fired,
            "error_message": ev.error_message,
            "payload": ev.payload,
            "raw_body": ev.raw_body,
            "received_at": ev.received_at.isoformat() if ev.received_at else None,
            "processed_at": ev.processed_at.isoformat() if ev.processed_at else None,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "updated_at": ev.updated_at.isoformat() if ev.updated_at else None,
        }
    }


@router.post("/{event_id}/replay")
async def replay_external_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replay a failed or processed event through the consumer pipeline.

    Resets the event status to 'pending' and re-dispatches to all registered
    consumers (trigger matching, etc.).  Useful for manual retry after fixing
    a trigger configuration, or for testing new trigger rules against historical events.
    """
    from app.services.event_bus import get_event_bus

    result = await db.execute(select(ExternalEvent).where(ExternalEvent.id == event_id))
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="External event not found")

    bus = get_event_bus()
    replayed = await bus.replay(db, event_id)

    if replayed is None:
        raise HTTPException(status_code=404, detail="External event not found")

    return {
        "event": {
            "id": str(replayed.id),
            "source": replayed.source,
            "event_type": replayed.event_type,
            "status": replayed.status,
            "triggers_fired": replayed.triggers_fired,
            "error_message": replayed.error_message,
            "processed_at": replayed.processed_at.isoformat() if replayed.processed_at else None,
        },
        "message": f"Event replayed — status: {replayed.status}",
    }
