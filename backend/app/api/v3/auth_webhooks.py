"""Auth v3 webhook routes — workspace-scoped auth event webhook subscriptions.

Provides HMAC-SHA256 signed webhook delivery for auth events (session.created,
session.revoked, user.created, etc.).  Subscriptions are workspace-scoped and
feature-flagged behind ``AUTH_V3_WEBHOOKS`` (404 when disabled).

Delivery is inline (synchronous httpx POST) with exponential backoff retries
scheduled via a simple retry counter.  For production scale, swap the inline
delivery for a Celery task.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app.api.deps import get_current_user
from app.api.v3.base import ok
from app.database import get_db
from app.models.auth_v3_models import AuthWebhookSubscription

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["v3-auth-webhooks"])


# ── HMAC signing ─────────────────────────────────────────────────────────────


def compute_webhook_signature(secret: str, payload_bytes: bytes) -> str:
    """Compute HMAC-SHA256 signature for a webhook payload.

    Returns the hex digest prefixed with ``sha256=`` so receivers can
    verify with ``hmac.compare_digest``.
    """
    return (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
    )


def verify_webhook_signature(secret: str, payload_bytes: bytes, signature_header: str) -> bool:
    """Verify an incoming webhook signature (for inbound webhook verification).

    Args:
        secret: The shared signing secret.
        payload_bytes: Raw request body bytes.
        signature_header: Value of the ``X-Webhook-Signature`` header.

    Returns:
        True if the signature matches.
    """
    expected = compute_webhook_signature(secret, payload_bytes)
    return hmac.compare_digest(expected, signature_header)


# ── Delivery ─────────────────────────────────────────────────────────────────

# Retry delays in seconds: 10s, 60s, 300s (5 min), 900s (15 min)
_RETRY_DELAYS = [10, 60, 300, 900]


async def _deliver_webhook(
    subscription: AuthWebhookSubscription,
    event_type: str,
    payload: dict,
) -> tuple[bool, int | None, str | None]:
    """Deliver a webhook event to a subscription URL.

    Signs the payload with HMAC-SHA256 and POSTs with standard headers.

    Returns:
        (success, http_status_code, error_message)
    """
    body = json.dumps(
        {
            "event": event_type,
            "data": payload,
            "timestamp": datetime.now(UTC).isoformat(),
            "webhook_id": str(uuid4()),
        },
        default=str,
    ).encode("utf-8")

    signature = compute_webhook_signature(subscription.secret, body)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Flowmanner-Webhook/1.0",
        "X-Webhook-Signature": signature,
        "X-Webhook-Event": event_type,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(subscription.url, content=body, headers=headers)

        success = 200 <= resp.status_code < 300
        if not success:
            logger.warning(
                "Webhook delivery failed: %s → %d %s",
                subscription.url,
                resp.status_code,
                resp.text[:200],
            )
        return success, resp.status_code, None if success else resp.text[:500]

    except Exception as e:
        logger.warning("Webhook delivery error: %s → %s", subscription.url, e)
        return False, None, str(e)[:500]


# ── Pydantic schemas ────────────────────────────────────────────────────────


class CreateWebhookBody(BaseModel):
    """POST /auth/webhooks — create webhook subscription."""

    url: str = Field(..., max_length=2000)
    events: list[str] = Field(..., min_length=1)
    workspace_id: str = Field(..., min_length=1)


class WebhookListResponse(BaseModel):
    """Webhook subscription in list view."""

    id: str
    workspace_id: str
    url: str
    events: list[str]
    is_active: bool
    created_at: str
    last_delivery_at: str | None
    failure_count: int


class WebhookCreateResponse(BaseModel):
    """Webhook subscription on creation (includes secret — shown ONCE)."""

    id: str
    workspace_id: str
    url: str
    events: list[str]
    secret: str  # shown ONCE on creation
    is_active: bool
    created_at: str


# ── Feature flag gate ────────────────────────────────────────────────────────


async def _require_webhooks_enabled(db: AsyncSession) -> None:
    """404 if AUTH_V3_WEBHOOKS feature flag is off."""
    result = await db.execute(text("SELECT enabled_globally FROM feature_flags WHERE key = 'AUTH_V3_WEBHOOKS'"))
    if not result.scalar():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not found",
        )


# ── POST /auth/webhooks ──────────────────────────────────────────────────────


@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: CreateWebhookBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a webhook subscription for auth events.

    The signing ``secret`` is returned ONCE in this response.  Store it
    securely — it cannot be retrieved later.

    Returns:
        201: { data: { id, workspace_id, url, events, secret, is_active, created_at }, ... }
    """
    await _require_webhooks_enabled(db)

    secret = AuthWebhookSubscription.generate_secret()

    webhook = AuthWebhookSubscription(
        id=str(uuid4()),
        workspace_id=payload.workspace_id,
        url=payload.url,
        secret=secret,
        events=json.dumps(payload.events),
        is_active=True,
    )
    db.add(webhook)
    await db.flush()

    return ok(
        WebhookCreateResponse(
            id=webhook.id,
            workspace_id=webhook.workspace_id,
            url=webhook.url,
            events=payload.events,
            secret=secret,
            is_active=True,
            created_at=datetime.now(UTC).isoformat(),
        ).model_dump(mode="json")
    )


# ── GET /auth/webhooks ───────────────────────────────────────────────────────


@router.get("/webhooks", status_code=status.HTTP_200_OK)
async def list_webhooks(
    workspace_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List webhook subscriptions for a workspace.

    Returns:
        200: { data: [{ id, workspace_id, url, events, is_active, ... }], ... }
    """
    await _require_webhooks_enabled(db)

    result = await db.execute(
        select(AuthWebhookSubscription).where(AuthWebhookSubscription.workspace_id == workspace_id)
    )
    webhooks = result.scalars().all()

    items = []
    for w in webhooks:
        try:
            events = json.loads(w.events) if w.events else []
        except (json.JSONDecodeError, TypeError):
            events = []
        items.append(
            WebhookListResponse(
                id=w.id,
                workspace_id=w.workspace_id,
                url=w.url,
                events=events,
                is_active=w.is_active,
                created_at=w.created_at.isoformat() if w.created_at else "",
                last_delivery_at=w.last_delivery_at.isoformat() if w.last_delivery_at else None,
                failure_count=w.failure_count,
            ).model_dump(mode="json")
        )

    return ok(items)


# ── DELETE /auth/webhooks/{webhook_id} ───────────────────────────────────────


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a webhook subscription.

    Returns:
        204: No content
        404: Webhook not found
    """
    await _require_webhooks_enabled(db)

    result = await db.execute(select(AuthWebhookSubscription).where(AuthWebhookSubscription.id == webhook_id))
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    await db.delete(webhook)
    await db.flush()


# ── GET /auth/webhooks/{webhook_id}/deliveries ───────────────────────────────


@router.get("/webhooks/{webhook_id}/deliveries", status_code=status.HTTP_200_OK)
async def list_webhook_deliveries(
    webhook_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List recent deliveries for a webhook subscription.

    Returns delivery log entries with status, response code, and retry info.
    The webhook delivery log is stored in the ``auth_webhook_delivery_logs``
    table (created by the delivery helper).

    Returns:
        200: { data: [{ id, event_type, status, response_code, attempt, ... }], ... }
        404: Webhook not found
    """
    await _require_webhooks_enabled(db)

    # Verify webhook exists
    result = await db.execute(select(AuthWebhookSubscription).where(AuthWebhookSubscription.id == webhook_id))
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    # Query delivery logs from the auth_webhook_delivery_logs table
    try:
        from sqlalchemy import text as sa_text

        logs_result = await db.execute(
            sa_text(
                "SELECT id, event_type, status, response_code, error_message, "
                "attempt, created_at FROM auth_webhook_delivery_logs "
                "WHERE webhook_id = :wid ORDER BY created_at DESC LIMIT :lim"
            ),
            {"wid": webhook_id, "lim": limit},
        )
        rows = logs_result.fetchall()
        items = [
            {
                "id": str(row[0]),
                "event_type": row[1],
                "status": row[2],
                "response_code": row[3],
                "error_message": row[4],
                "attempt": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
            }
            for row in rows
        ]
    except Exception:
        # Table may not exist yet — return empty
        items = []

    return ok(items)


# ── Auth event emission helper ───────────────────────────────────────────────


async def emit_auth_webhook_event(
    db: AsyncSession,
    workspace_id: str,
    event_type: str,
    payload: dict,
) -> int:
    """Emit an auth event to all active webhook subscriptions for a workspace.

    Called from auth handlers (session creation, revocation, user creation, etc.)
    to deliver webhook events to subscribers.

    Args:
        db: Database session (same one used by the auth handler).
        workspace_id: The workspace whose subscriptions should receive the event.
        event_type: Event type string (e.g. ``"session.created"``).
        payload: Event payload dict.

    Returns:
        Number of subscriptions the event was delivered to.
    """
    result = await db.execute(
        select(AuthWebhookSubscription).where(
            AuthWebhookSubscription.workspace_id == workspace_id,
            AuthWebhookSubscription.is_active == True,
        )
    )
    subscriptions = result.scalars().all()

    if not subscriptions:
        return 0

    delivered = 0
    for sub in subscriptions:
        # Check if this subscription wants this event type
        try:
            subscribed_events = json.loads(sub.events) if sub.events else []
        except (json.JSONDecodeError, TypeError):
            subscribed_events = []

        if subscribed_events and event_type not in subscribed_events:
            continue

        # Deliver (with retry on failure)
        success = await _deliver_with_retry(sub, event_type, payload)

        # Update subscription metadata
        sub.last_delivery_at = datetime.now(UTC)
        if not success:
            sub.failure_count = (sub.failure_count or 0) + 1
            sub.last_failure_at = datetime.now(UTC)
        await db.flush()

        delivered += 1

    return delivered


async def _deliver_with_retry(
    subscription: AuthWebhookSubscription,
    event_type: str,
    payload: dict,
    max_retries: int = 3,
) -> bool:
    """Deliver a webhook with exponential backoff retries.

    Returns True if delivery succeeded (any attempt).
    """
    for attempt in range(max_retries + 1):
        success, _status_code, _error = await _deliver_webhook(subscription, event_type, payload)

        if success:
            return True

        if attempt < max_retries:
            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            logger.debug(
                "Webhook delivery retry %d/%d in %ds for %s",
                attempt + 1,
                max_retries,
                delay,
                subscription.url,
            )
            import asyncio

            await asyncio.sleep(delay)

    return False
