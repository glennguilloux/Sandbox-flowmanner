"""V2 Notifications router — standardized envelope over the existing Notification model.

This is an additive surface that reuses the EXISTING ``Notification`` model
(``app/models/notification_models.py``) and the existing emission helper
``send_notification`` (``app/services/notification_service.py``). It does NOT
duplicate notification logic and does NOT alter the v1 response shapes.

Envelope contract (``app/api.v2.base``):
    ok()        -> {"data": <payload>, "meta": {...}, "error": null}
    paginated() -> {"data": {items, total, page, per_page, pages}, "meta": {...}, "error": null}
    err()       -> {"data": null, "error": {code, message, details}, "meta": {...}}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select

from app.api.deps import get_current_user
from app.api.v2.base import err, ok, paginated
from app.database import get_db
from app.models.notification_models import Notification

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


router = APIRouter(prefix="/notifications", tags=["v2-notifications"])


class NotificationItem(BaseModel):
    """Pydantic schema for notification responses (mirrors v1 shape, envelope-wrapped)."""

    id: int
    user_id: int
    title: str
    message: str = ""
    body: str = ""  # keep for backward compat
    type: str = "info"  # frontend expects 'type', not 'notification_type'
    notification_type: str = "info"
    severity: str = "info"
    is_read: bool = False
    read_at: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    meta: str | None = None
    created_at: str = ""

    @field_validator("read_at", mode="before")
    @classmethod
    def coerce_read_at(cls, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    @field_validator("created_at", mode="before")
    @classmethod
    def coerce_created_at(cls, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    model_config = {"from_attributes": True}


def _serialize(item: Notification) -> NotificationItem:
    """Build a NotificationItem, coercing datetimes to ISO strings defensively."""
    return NotificationItem(
        id=item.id,
        user_id=item.user_id,
        title=item.title,
        message=item.message or "",
        body=item.message or "",
        type=item.notification_type,
        notification_type=item.notification_type,
        severity=item.severity,
        is_read=item.is_read,
        read_at=item.read_at.isoformat() if item.read_at else None,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        meta=item.meta,
        created_at=item.created_at.isoformat() if item.created_at else "",
    )


@router.get("")
async def list_notifications(
    read: bool | None = Query(None, description="Filter by read state"),
    type: str | None = Query(None, description="Filter by notification_type"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's notifications, paginated and filtered."""
    query = select(Notification).where(Notification.user_id == user.id)
    if read is not None:
        query = query.where(Notification.is_read == read)
    if type:
        query = query.where(Notification.notification_type == type)

    # Total count (over the filtered base query).
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    rows = (
        await db.execute(
            query.order_by(Notification.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).scalars().all()

    items = [_serialize(r) for r in rows]
    return paginated(items=[i.model_dump() for i in items], total=total, page=page, per_page=per_page)


@router.get("/unread-count")
async def unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's unread notification badge count."""
    c = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.is_read == False)  # noqa: E712
        )
    ).scalar() or 0
    return ok({"unread_count": c})


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification read. Owner-checked (404 if not the owner's)."""
    item = (
        await db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not item:
        return err("NOT_FOUND", "Notification not found", status_code=404)
    item.is_read = True
    item.read_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(item)
    return ok(_serialize(item).model_dump())


@router.post("/read-all")
async def mark_all_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all of the current user's unread notifications as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    items = result.scalars().all()
    now = datetime.now(UTC)
    n = 0
    for item in items:
        item.is_read = True
        item.read_at = now
        n += 1
    await db.flush()
    return ok({"updated": n})
