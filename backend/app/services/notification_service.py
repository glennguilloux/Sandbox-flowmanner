from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.notification_models import (
    NotificationSettings as DBNotificationSettings,
)
from app.services.sse_service import publish_user_notification

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


class NotificationSettings(BaseModel):
    """User notification settings (Pydantic schema)."""

    in_app_enabled: bool = True
    email_enabled: bool = False
    push_enabled: bool = False
    event_mission_completed: bool = True
    event_mission_failed: bool = True
    event_mention: bool = True
    event_system: bool = True
    digest_mode: str = "realtime"
    digest_time_utc: str | None = None
    digest_day_of_week: int | None = None
    email_address: str | None = None
    push_enabled_channels: str | None = None
    # Frontend aliases (mapped from event_ fields)
    mission_completed: bool = True
    mission_failed: bool = True
    slack_enabled: bool = False
    slack_webhook_url: str | None = None

    model_config = {"from_attributes": True}


class NotificationSettingsUpdate(BaseModel):
    """Update notification settings."""

    in_app_enabled: bool | None = None
    email_enabled: bool | None = None
    push_enabled: bool | None = None
    event_mission_completed: bool | None = None
    event_mission_failed: bool | None = None
    event_mention: bool | None = None
    event_system: bool | None = None
    digest_mode: str | None = None
    digest_time_utc: str | None = None
    digest_day_of_week: int | None = None
    email_address: str | None = None
    push_enabled_channels: str | None = None
    # Frontend aliases
    mission_completed: bool | None = None
    mission_failed: bool | None = None
    slack_enabled: bool | None = None
    slack_webhook_url: str | None = None


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── Notification Pydantic schema ─────────────────────────────────────────────

class NotificationItem(BaseModel):
    """Pydantic schema for notification responses."""
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

    entity_type: str | None = None
    entity_id: str | None = None
    meta: str | None = None
    created_at: str = ""

    model_config = {"from_attributes": True}


async def _add_notification(
    db: AsyncSession,
    user_id: int,
    title: str,
    body: str,
    notification_type: str = "info",
    severity: str = "info",
) -> NotificationItem:
    """Create a notification in the database."""
    from app.models.notification_models import Notification
    now = datetime.now(UTC)
    db_item = Notification(
        user_id=user_id,
        title=title,
        message=body,
        notification_type=notification_type,
        severity=severity,
        is_read=False,
        created_at=now,
        updated_at=now,
    )
    db.add(db_item)
    await db.flush()
    await db.refresh(db_item)
    return NotificationItem(
        id=db_item.id,
        user_id=db_item.user_id,
        title=db_item.title,
        message=db_item.message,
        body=db_item.message,
        type=db_item.notification_type,
        notification_type=db_item.notification_type,
        severity=db_item.severity,
        is_read=db_item.is_read,
        read_at=db_item.read_at.isoformat() if db_item.read_at else None,
        entity_type=db_item.entity_type,
        entity_id=db_item.entity_id,
        meta=db_item.meta,
        created_at=db_item.created_at.isoformat() if db_item.created_at else "",
    )


# ── Notification list & CRUD ────────────────────────────────────────────────

@router.get("/")
async def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.notification_models import Notification
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read == False)
    query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    # Optimized total count using count() instead of fetching all rows
    from sqlalchemy import func as sa_func
    count_query = select(sa_func.count()).select_from(Notification).where(Notification.user_id == user.id)
    if unread_only:
        count_query = count_query.where(Notification.is_read == False)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return {
        "items": [NotificationItem.model_validate(n) for n in items],
        "total": total,
    }


@router.get("/unread-count")
async def unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func as sa_func

    from app.models.notification_models import Notification
    result = await db.execute(
        select(sa_func.count()).select_from(Notification).where(
            Notification.user_id == user.id,
            Notification.is_read == False,
        )
    )
    count = result.scalar() or 0
    return {"unread_count": count}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.notification_models import Notification
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    item.is_read = True
    item.read_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(item)
    return NotificationItem.model_validate(item)


@router.post("/read-all")
async def mark_all_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.notification_models import Notification
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user.id,
            Notification.is_read == False,
        )
    )
    items = result.scalars().all()
    now = datetime.now(UTC)
    for item in items:
        item.is_read = True
        item.read_at = now
    await db.flush()
    return {"status": "ok"}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.notification_models import Notification
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(item)
    await db.flush()


# ── Push subscription CRUD (DB-backed) ──────────────────────────────────────

# Cache for auto-generated VAPID keys to avoid regenerating on every request
_vapid_keys: dict[str, str] = {}

def _get_vapid_keys():
    """Return (public_key, private_key) from config or auto-generate if empty.

    For pywebpush >= 2.x, Vapid.generate_keys() + public_pem()/private_pem()
    produces PEM-encoded keys. The public key for browsers (applicationServerKey)
    is derived from the raw EC public key point as URL-safe base64.
    """
    if _vapid_keys.get("public") and _vapid_keys.get("private"):
        return _vapid_keys["public"], _vapid_keys["private"]
    from app.config import settings
    pub = settings.VAPID_PUBLIC_KEY
    prv = settings.VAPID_PRIVATE_KEY
    if not pub or not prv:
        try:
            from pywebpush import Vapid
            v = Vapid()
            v.generate_keys()
            # private_pem() returns bytes like b'-----BEGIN PRIVATE KEY-----...'
            prv = v.private_pem().decode()
            # Derive URL-safe base64 public key for browser
            import base64

            from cryptography.hazmat.primitives.serialization import (
                Encoding,
                PublicFormat,
            )
            raw = v.public_key.public_bytes(
                Encoding.X962, PublicFormat.UncompressedPoint
            )
            pub = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
            import logging
            _log = logging.getLogger(__name__)
            _log.warning(
                "Auto-generated VAPID keys. For production, persist these in .env:\n"
                f"  VAPID_PUBLIC_KEY={pub}\n"
                f"  VAPID_PRIVATE_KEY={prv}"
            )
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to auto-generate VAPID keys — web push notifications disabled. "
                "Install pywebpush or set VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY in .env."
            )
            return "", ""
    _vapid_keys["public"] = pub
    _vapid_keys["private"] = prv
    return pub, prv


@router.post("/push/subscribe")
async def push_subscribe(
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.notification_models import PushSubscription

    endpoint = payload.get("endpoint", "")
    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint is required")

    keys = payload.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")

    # Check if subscription already exists for this endpoint
    existing = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.endpoint == endpoint,
        )
    )
    existing_sub = existing.scalar_one_or_none()
    if existing_sub:
        # Update keys in case they rotated
        existing_sub.p256dh_key = p256dh
        existing_sub.auth_key = auth
        existing_sub.is_active = True
        await db.flush()
        return {"status": "updated"}

    sub = PushSubscription(
        user_id=user.id,
        endpoint=endpoint,
        p256dh_key=p256dh,
        auth_key=auth,
        is_active=True,
    )
    db.add(sub)
    await db.flush()
    return {"status": "subscribed"}


@router.post("/push/unsubscribe")
async def push_unsubscribe(
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.notification_models import PushSubscription

    endpoint = payload.get("endpoint")
    if endpoint:
        existing = await db.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == user.id,
                PushSubscription.endpoint == endpoint,
            )
        )
        sub = existing.scalar_one_or_none()
        if sub:
            sub.is_active = False
            await db.flush()

    return {"status": "unsubscribed"}


@router.get("/push/vapid-public-key")
async def vapid_public_key():
    pub, _ = _get_vapid_keys()
    return {"public_key": pub}


# ── SSE Stream ──────────────────────────────────────────────────────────────

@router.get("/stream")
async def notification_stream(
    token: str = "",
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint for real-time notifications.

    Accepts token as query parameter for EventSource compatibility.
    Subscribes to user-specific Redis channel and pushes real notification events.
    Sends initial unread_count event on connect, then streams notification events.
    """
    from fastapi.responses import StreamingResponse

    # Validate token
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    # Verify token is valid
    try:
        from app.api.v1.auth import decode_access_token
        user_id_str = decode_access_token(token)
        if not user_id_str:
            raise HTTPException(status_code=401, detail="Invalid token")
        user_id = int(user_id_str)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    from sqlalchemy import func as sa_func

    from app.models.notification_models import Notification
    from app.services.sse_service import user_notification_sse_stream

    # Compute initial unread count from DB
    count_result = await db.execute(
        select(sa_func.count()).select_from(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
    )
    initial_unread = count_result.scalar() or 0

    return StreamingResponse(
        user_notification_sse_stream(user_id, initial_unread_count=initial_unread),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Settings (preserved) ────────────────────────────────────────────────────

@router.get("/settings")
async def get_notification_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(
            select(DBNotificationSettings).where(
                DBNotificationSettings.user_id == user.id
            )
        )
        settings = result.scalar_one_or_none()
        s = NotificationSettings() if not settings else NotificationSettings.model_validate(settings)
        # Map backend event_ fields to frontend aliases
        return {
            "mission_completed": s.event_mission_completed,
            "mission_failed": s.event_mission_failed,
            "email_enabled": s.email_enabled,
            "email_address": s.email_address,
            "slack_enabled": s.slack_enabled,
            "slack_webhook_url": s.slack_webhook_url,
            "in_app_enabled": s.in_app_enabled,
            "push_enabled": s.push_enabled,
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load notification settings",
        )


@router.patch("/settings")
async def update_notification_settings(
    payload: NotificationSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(
            select(DBNotificationSettings).where(
                DBNotificationSettings.user_id == user.id
            )
        )
        settings = result.scalar_one_or_none()

        if not settings:
            settings = DBNotificationSettings(user_id=user.id)
            db.add(settings)

        # Map frontend aliases to backend fields
        alias_map = {
            "mission_completed": "event_mission_completed",
            "mission_failed": "event_mission_failed",
        }
        for alias, db_field in alias_map.items():
            value = getattr(payload, alias, None)
            if value is not None:
                setattr(settings, db_field, value)

        # Update standard fields
        for field in [
            "in_app_enabled", "email_enabled", "push_enabled",
            "event_mission_completed", "event_mission_failed",
            "event_mention", "event_system", "digest_mode",
            "digest_time_utc", "digest_day_of_week",
            "email_address", "push_enabled_channels",
        ]:
            value = getattr(payload, field, None)
            if value is not None:
                setattr(settings, field, value)

        await db.flush()
        await db.refresh(settings)
        s = NotificationSettings.model_validate(settings)
        return {
            "mission_completed": s.event_mission_completed,
            "mission_failed": s.event_mission_failed,
            "email_enabled": s.email_enabled,
            "email_address": s.email_address,
            "slack_enabled": s.slack_enabled,
            "slack_webhook_url": s.slack_webhook_url,
            "in_app_enabled": s.in_app_enabled,
            "push_enabled": s.push_enabled,
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update notification settings",
        )


async def send_notification(
    user_id: int, notification_type: str, data: dict, db: AsyncSession
) -> None:
    """
    Send notification to user based on their settings.
    Called when mission status changes.
    """
    result = await db.execute(
        select(DBNotificationSettings).where(DBNotificationSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = NotificationSettings()  # defaults
    else:
        settings = NotificationSettings.model_validate(settings)

    # Check if this notification type is enabled
    if notification_type == "mission_completed" and not settings.event_mission_completed:
        return
    if notification_type == "mission_failed" and not settings.event_mission_failed:
        return

    # Send SSE notification (in-app) via user notification channel
    if settings.in_app_enabled:
        notification_item = await _add_notification(
            db=db,
            user_id=user_id,
            title=data.get("title", notification_type),
            body=data.get("message", str(data)),
            notification_type=notification_type,
            severity=notification_type.split("_")[-1] if "_" in notification_type else "info",
        )
        await publish_user_notification(user_id, {
            "event": "notification",
            "data": notification_item.model_dump(),
        })

    # Send web push (via PushSubscription)
    if settings.push_enabled:
        try:
            from app.models.notification_models import PushSubscription
            subs_result = await db.execute(
                select(PushSubscription).where(
                    PushSubscription.user_id == user_id,
                    PushSubscription.is_active == True,
                )
            )
            subs = subs_result.scalars().all()
            if subs:
                pub, prv = _get_vapid_keys()
                if pub:
                    import json

                    from pywebpush import webpush
                    push_payload = json.dumps({
                        "title": data.get("title", notification_type),
                        "body": data.get("message", str(data)),
                        "icon": "/favicon.ico",
                        "badge": "/badge.png",
                    })
                    for sub in subs:
                        try:
                            webpush(
                                subscription_info=sub.to_push_dict(),
                                data=push_payload,
                                vapid_private_key=prv,
                                vapid_claims={
                                    "sub": "mailto:admin@flowmanner.com",
                                },
                            )
                        except Exception as push_err:
                            # Subscription may be expired — deactivate
                            sub.is_active = False
                            logger.warning(
                                f"Web push failed for user {user_id}: {push_err}"
                            )
                await db.flush()
        except Exception as e:
            import logging
            logger.warning(f"Web push error: {e}")

    # Send email
    if settings.email_enabled and settings.email_address:
        await send_email_notification(settings.email_address, notification_type, data)


async def send_email_notification(
    email: str, notification_type: str, data: dict
) -> None:
    """Send email notification using the email service."""
    try:
        from app.services.email_service import get_email_service

        service = get_email_service()

        # Map notification types to email templates
        template_map = {
            "mission_completed": "mission_completed",
            "mission_failed": "mission_failed",
            "event_mission_completed": "mission_completed",
            "event_mission_failed": "mission_failed",
        }

        template_name = template_map.get(notification_type)
        if not template_name:
            # Generic notification — send raw email
            title = data.get("title", notification_type)
            message = data.get("message", str(data))
            await service.send_raw(
                to=email,
                subject=f"Flowmanner: {title}",
                html=f"<p>{message}</p>",
            )
            return

        variables = {
            "mission_name": data.get("mission_name", data.get("mission_id", "Unknown")),
            "mission_id": data.get("mission_id", ""),
            "duration": data.get("duration", "N/A"),
            "tasks_completed": data.get("tasks_completed", "N/A"),
            "error_message": data.get("error", "Unknown error"),
            "dashboard_url": data.get("dashboard_url", "https://flowmanner.com"),
        }

        await service.send_email(
            to=email,
            template_name=template_name,
            variables=variables,
        )

    except Exception as e:
        logger.warning(f"Email notification failed: {e}")


async def send_slack_notification(
    webhook_url: str, notification_type: str, data: dict
) -> None:
    """Send Slack webhook notification (Story 1.3)."""
    try:
        mission_id = data.get("mission_id", "unknown")

        if notification_type == "mission_completed":
            text = f"✅ Mission {mission_id} completed successfully!"
        else:
            text = (
                f"❌ Mission {mission_id} failed! Error: {data.get('error', 'Unknown')}"
            )

        payload = {"text": text}

        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=payload)

    except Exception as e:
        print(f"Slack notification failed: {e}")
