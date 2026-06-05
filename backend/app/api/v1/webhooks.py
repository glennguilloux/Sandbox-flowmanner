"""Webhook subscription and delivery API routes."""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.webhook_models import WebhookEndpoint, WebhookLog, WebhookStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


# ── Subscriptions (mapped to WebhookEndpoint) ───────────────────────────────


@router.get("/subscriptions")
async def list_subscriptions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * limit
    count_q = select(func.count(WebhookEndpoint.id)).where(
        WebhookEndpoint.created_by == user.id
    )
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(WebhookEndpoint)
        .where(WebhookEndpoint.created_by == user.id)
        .order_by(WebhookEndpoint.id.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    endpoints = result.scalars().all()

    return {
        "subscriptions": [
            {
                "id": str(ep.id),
                "user_id": str(ep.created_by),
                "url": ep.path,
                "events": [ep.source] if ep.source else [],
                "secret": None,  # never expose
                "is_active": ep.is_active,
                "created_at": ep.created_at.isoformat() if ep.created_at else "",
                "updated_at": ep.updated_at.isoformat() if ep.updated_at else "",
                "last_triggered_at": None,
                "failure_count": 0,
            }
            for ep in endpoints
        ],
        "total": total,
    }


@router.post("/subscriptions")
async def create_subscription(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    url = payload.get("url", "")
    events = payload.get("events", [])
    secret = payload.get("secret") or uuid4().hex

    if not url:
        raise HTTPException(status_code=400, detail="url is required")

    from sqlalchemy.exc import IntegrityError

    endpoint = WebhookEndpoint(
        name=f"wh-{uuid4().hex[:8]}",
        source=events[0] if events else "custom",
        path=url,
        secret=secret,
        description=payload.get("description"),
        verify_signature=True,
        is_active=True,
        created_by=user.id,
    )
    db.add(endpoint)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="A webhook with this URL already exists"
        )
    await db.refresh(endpoint)

    return {
        "subscription": {
            "id": str(endpoint.id),
            "user_id": str(user.id),
            "url": endpoint.path,
            "events": events,
            "secret": secret,
            "is_active": True,
            "created_at": (
                endpoint.created_at.isoformat() if endpoint.created_at else ""
            ),
            "updated_at": (
                endpoint.updated_at.isoformat() if endpoint.updated_at else ""
            ),
            "last_triggered_at": None,
            "failure_count": 0,
        }
    }


@router.get("/subscriptions/{subscription_id}")
async def get_subscription(
    subscription_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == int(subscription_id),
            WebhookEndpoint.created_by == user.id,
        )
    )
    ep = result.scalar_one_or_none()
    if not ep:
        raise _not_found()

    return {
        "subscription": {
            "id": str(ep.id),
            "user_id": str(ep.created_by),
            "url": ep.path,
            "events": [ep.source] if ep.source else [],
            "secret": None,
            "is_active": ep.is_active,
            "created_at": ep.created_at.isoformat() if ep.created_at else "",
            "updated_at": ep.updated_at.isoformat() if ep.updated_at else "",
            "last_triggered_at": None,
            "failure_count": 0,
        }
    }


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == int(subscription_id),
            WebhookEndpoint.created_by == user.id,
        )
    )
    ep = result.scalar_one_or_none()
    if not ep:
        raise _not_found()

    await db.delete(ep)
    await db.flush()
    return {"detail": "Deleted"}


# ── Deliveries (mapped to WebhookLog) ───────────────────────────────────────


@router.get("/deliveries")
async def list_deliveries(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * limit

    # Get user's endpoint IDs first
    ep_ids_q = select(WebhookEndpoint.id).where(WebhookEndpoint.created_by == user.id)
    ep_ids_result = await db.execute(ep_ids_q)
    ep_ids = [row[0] for row in ep_ids_result.all()]

    if not ep_ids:
        return {"deliveries": [], "total": 0, "page": page, "limit": limit}

    count_q = select(func.count(WebhookLog.id)).where(
        WebhookLog.endpoint_id.in_(ep_ids)
    )
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(WebhookLog)
        .where(WebhookLog.endpoint_id.in_(ep_ids))
        .order_by(WebhookLog.id.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    logs = result.scalars().all()

    return {
        "deliveries": [
            {
                "id": str(log.id),
                "subscription_id": str(log.endpoint_id),
                "event_type": log.event_type or "",
                "payload": log.payload or {},
                "response_status": log.response_code,
                "response_body": log.response_body,
                "status": log.status,
                "delivered": log.status == WebhookStatus.SUCCESS.value,
                "retry_count": log.retry_count,
                "created_at": log.created_at.isoformat() if log.created_at else "",
                "delivered_at": (
                    log.delivered_at.isoformat() if log.delivered_at else None
                ),
                "next_retry_at": (
                    log.next_retry_at.isoformat() if log.next_retry_at else None
                ),
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/deliveries/{delivery_id}")
async def get_delivery(
    delivery_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WebhookLog).where(WebhookLog.id == int(delivery_id))
    )
    log = result.scalar_one_or_none()
    if not log:
        raise _not_found()

    return {
        "delivery": {
            "id": str(log.id),
            "subscription_id": str(log.endpoint_id),
            "event_type": log.event_type or "",
            "payload": log.payload or {},
            "response_status": log.response_code,
            "response_body": log.response_body,
            "status": log.status,
            "delivered": log.status == WebhookStatus.SUCCESS.value,
            "retry_count": log.retry_count,
            "created_at": log.created_at.isoformat() if log.created_at else "",
            "delivered_at": log.delivered_at.isoformat() if log.delivered_at else None,
            "next_retry_at": (
                log.next_retry_at.isoformat() if log.next_retry_at else None
            ),
        }
    }


# ── Emit & Events ───────────────────────────────────────────────────────────


@router.post("/emit")
async def emit_event(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Emit a webhook event to all active subscriptions.

    Phase 8.5: Dispatches via Celery task for reliable delivery with
    HMAC-SHA256 signing, exponential backoff retries, and DLQ.
    """
    event_type = payload.get("event_type", "custom")
    event_data = payload.get("data", {})

    # Find active endpoints for this user
    q = select(WebhookEndpoint).where(
        WebhookEndpoint.is_active == True,
        WebhookEndpoint.created_by == user.id,
    )
    result = await db.execute(q)
    endpoints = result.scalars().all()

    if not endpoints:
        return {"detail": "No active endpoints", "dispatched": 0}

    dispatched = 0
    for ep in endpoints:
        # Create log entry with PENDING status
        log = WebhookLog(
            endpoint_id=ep.id,
            source=ep.source,
            event_type=event_type,
            payload=event_data,
            status=WebhookStatus.PENDING.value,
            max_retries=ep.retry_count or 3,
        )
        db.add(log)
        await db.flush()

        # Dispatch via Celery for reliable delivery with retries
        try:
            from app.tasks.webhook_tasks import deliver_webhook

            deliver_webhook.delay(log.id)
            dispatched += 1
        except Exception:
            # Fallback: inline delivery if Celery is unavailable
            logger.warning("Celery dispatch failed, falling back to inline delivery")
            try:
                async with httpx.AsyncClient(
                    timeout=ep.timeout_seconds or 30
                ) as client:
                    body_bytes = json.dumps(event_data, default=str).encode()
                    headers = {
                        "Content-Type": "application/json",
                        "User-Agent": "Flowmanner-Webhook/1.0",
                    }
                    if ep.secret:
                        sig = hmac.new(
                            ep.secret.encode(), body_bytes, hashlib.sha256
                        ).hexdigest()
                        headers["X-Webhook-Signature"] = f"sha256={sig}"
                        headers["X-Webhook-ID"] = str(log.id)
                        headers["X-Webhook-Timestamp"] = (
                            str(int(log.created_at.timestamp()))
                            if log.created_at
                            else ""
                        )

                    resp = await client.post(
                        ep.path, content=body_bytes, headers=headers
                    )
                    log.response_code = resp.status_code
                    log.response_body = {"body": resp.text[:5000]}
                    if 200 <= resp.status_code < 300:
                        log.status = WebhookStatus.SUCCESS.value
                        log.delivered_at = datetime.now(UTC)
                    else:
                        log.status = WebhookStatus.FAILED.value
                        log.last_error = f"HTTP {resp.status_code}"
            except Exception as e:
                log.status = WebhookStatus.FAILED.value
                log.last_error = str(e)[:1000]
                log.last_error_at = datetime.now(UTC)

            log.processing_completed_at = datetime.now(UTC)
            await db.flush()
            dispatched += 1

    return {
        "detail": f"Event emitted to {len(endpoints)} endpoints",
        "dispatched": dispatched,
    }


@router.get("/event")
async def get_event_types():
    return {
        "events": [
            "mission.created",
            "mission.completed",
            "mission.failed",
            "flow.started",
            "flow.completed",
            "agent.created",
        ]
    }


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ep_ids_q = select(WebhookEndpoint.id).where(WebhookEndpoint.created_by == user.id)
    ep_ids_result = await db.execute(ep_ids_q)
    ep_ids = [row[0] for row in ep_ids_result.all()]

    total_subscriptions = len(ep_ids)

    if not ep_ids:
        return {
            "total_subscriptions": 0,
            "total_deliveries": 0,
            "success_rate": 0.0,
            "avg_delivery_time_ms": 0,
            "p95_delivery_time_ms": 0,
            "status_breakdown": {},
        }

    total_q = select(func.count(WebhookLog.id)).where(
        WebhookLog.endpoint_id.in_(ep_ids)
    )
    total_deliveries = (await db.execute(total_q)).scalar() or 0

    success_q = select(func.count(WebhookLog.id)).where(
        WebhookLog.endpoint_id.in_(ep_ids),
        WebhookStatus.SUCCESS.value == WebhookLog.status,
    )
    success_count = (await db.execute(success_q)).scalar() or 0

    avg_time_q = select(func.avg(WebhookLog.processing_time_ms)).where(
        WebhookLog.endpoint_id.in_(ep_ids),
        WebhookLog.processing_time_ms.isnot(None),
    )
    avg_time = (await db.execute(avg_time_q)).scalar() or 0

    # p95 latency via percentile_cont
    from sqlalchemy import text as sa_text

    p95_q = sa_text(
        "SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY processing_time_ms) "
        "FROM webhook_logs WHERE endpoint_id = ANY(:ids) AND processing_time_ms IS NOT NULL"
    )
    p95_result = await db.execute(p95_q, {"ids": list(ep_ids)})
    p95_time = p95_result.scalar() or 0

    # Status breakdown
    status_q = (
        select(WebhookLog.status, func.count(WebhookLog.id))
        .where(WebhookLog.endpoint_id.in_(ep_ids))
        .group_by(WebhookLog.status)
    )
    status_result = await db.execute(status_q)
    status_breakdown = {row[0]: row[1] for row in status_result.all()}

    return {
        "total_subscriptions": total_subscriptions,
        "total_deliveries": total_deliveries,
        "success_rate": (
            round(success_count / total_deliveries, 2) if total_deliveries else 0.0
        ),
        "avg_delivery_time_ms": round(avg_time, 1),
        "p95_delivery_time_ms": round(float(p95_time), 1),
        "status_breakdown": status_breakdown,
    }


# ── Admin: Webhook Logs (Phase 8.5) ────────────────────────────────────────


@router.get("/admin/logs")
async def admin_webhook_logs(
    limit: int = Query(100, ge=1, le=500),
    status_filter: str | None = Query(
        None, description="Filter by status: pending, success, failed, retrying"
    ),
    endpoint_id: int | None = Query(None, description="Filter by endpoint ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Admin endpoint: last N webhook deliveries with aggregated stats.

    Returns the most recent deliveries across all (or filtered) endpoints,
    plus success rate, p95 latency, and per-status counts.
    """
    # Build query — scoped to user's endpoints
    ep_ids_q = select(WebhookEndpoint.id).where(WebhookEndpoint.created_by == user.id)
    ep_ids_result = await db.execute(ep_ids_q)
    ep_ids = [row[0] for row in ep_ids_result.all()]

    if not ep_ids:
        return {
            "logs": [],
            "total": 0,
            "success_rate": 0.0,
            "p95_latency_ms": 0,
            "status_counts": {},
        }

    q = select(WebhookLog).where(WebhookLog.endpoint_id.in_(ep_ids))

    if status_filter:
        q = q.where(WebhookLog.status == status_filter)
    if endpoint_id and endpoint_id in ep_ids:
        q = q.where(WebhookLog.endpoint_id == endpoint_id)

    q = q.order_by(WebhookLog.id.desc()).limit(limit)
    result = await db.execute(q)
    logs = result.scalars().all()

    # Aggregated stats across all user deliveries (unfiltered)
    total_q = select(func.count(WebhookLog.id)).where(
        WebhookLog.endpoint_id.in_(ep_ids)
    )
    total = (await db.execute(total_q)).scalar() or 0

    success_q = select(func.count(WebhookLog.id)).where(
        WebhookLog.endpoint_id.in_(ep_ids),
        WebhookLog.status == WebhookStatus.SUCCESS.value,
    )
    success_count = (await db.execute(success_q)).scalar() or 0

    from sqlalchemy import text as sa_text

    p95_q = sa_text(
        "SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY processing_time_ms) "
        "FROM webhook_logs WHERE endpoint_id = ANY(:ids) AND processing_time_ms IS NOT NULL"
    )
    p95_result = await db.execute(p95_q, {"ids": list(ep_ids)})
    p95_time = p95_result.scalar() or 0

    # Per-status counts
    status_q = (
        select(WebhookLog.status, func.count(WebhookLog.id))
        .where(WebhookLog.endpoint_id.in_(ep_ids))
        .group_by(WebhookLog.status)
    )
    status_result = await db.execute(status_q)
    status_counts = {row[0]: row[1] for row in status_result.all()}

    return {
        "logs": [
            {
                "id": str(log.id),
                "endpoint_id": log.endpoint_id,
                "event_type": log.event_type or "",
                "status": log.status,
                "response_code": log.response_code,
                "retry_count": log.retry_count,
                "processing_time_ms": log.processing_time_ms,
                "last_error": log.last_error,
                "created_at": log.created_at.isoformat() if log.created_at else "",
                "delivered_at": (
                    log.delivered_at.isoformat() if log.delivered_at else None
                ),
                "next_retry_at": (
                    log.next_retry_at.isoformat() if log.next_retry_at else None
                ),
            }
            for log in logs
        ],
        "total": total,
        "success_rate": round(success_count / total, 2) if total else 0.0,
        "p95_latency_ms": round(float(p95_time), 1),
        "status_counts": status_counts,
    }
