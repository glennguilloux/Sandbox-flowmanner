"""Mission Trigger API routes (FLO-118).

Authenticated CRUD + pause/resume/fire for triggers.
Public webhook endpoint for inbound triggers.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.trigger import (
    TriggerCreate,
    TriggerListResponse,
    TriggerLogListResponse,
    TriggerResponse,
    TriggerUpdate,
    WebhookFireResponse,
)
from app.services import trigger_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/triggers", tags=["triggers"])


def _not_found():
    return HTTPException(status_code=404, detail="Trigger not found")


def _to_response(t) -> dict:
    return {
        "id": str(t.id),
        "user_id": t.user_id,
        "mission_id": str(t.mission_id),
        "trigger_type": t.trigger_type,
        "name": t.name,
        "status": t.status,
        "cron_expression": t.cron_expression,
        "cron_timezone": t.cron_timezone,
        "webhook_path": t.webhook_path,
        "config": t.config,
        "fire_count": t.fire_count,
        "last_fired_at": t.last_fired_at,
        "next_fire_at": t.next_fire_at,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


def _to_log_response(log) -> dict:
    return {
        "id": str(log.id),
        "trigger_id": str(log.trigger_id),
        "mission_run_id": str(log.mission_run_id) if log.mission_run_id else None,
        "status": log.status,
        "trigger_type": log.trigger_type,
        "error_message": log.error_message,
        "duration_ms": log.duration_ms,
        "webhook_signature_valid": log.webhook_signature_valid,
        "fired_at": log.fired_at,
    }


# ── Authenticated endpoints ──────────────────────────────────────────────────


@router.post("", response_model=TriggerResponse, status_code=status.HTTP_201_CREATED)
async def create_trigger(
    payload: TriggerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trigger = await svc.create_trigger(db, user.id, payload)
    return _to_response(trigger)


@router.get("", response_model=TriggerListResponse)
async def list_triggers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    triggers = await svc.list_triggers(db, user.id)
    return {"triggers": [_to_response(t) for t in triggers], "total": len(triggers)}


@router.get("/{trigger_id}", response_model=TriggerResponse)
async def get_trigger(
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trigger = await svc.get_trigger(db, trigger_id, user.id)
    if not trigger:
        raise _not_found()
    return _to_response(trigger)


@router.patch("/{trigger_id}", response_model=TriggerResponse)
async def update_trigger(
    trigger_id: str,
    payload: TriggerUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trigger = await svc.update_trigger(db, trigger_id, user.id, payload)
    if not trigger:
        raise _not_found()
    return _to_response(trigger)


@router.delete("/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trigger(
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await svc.delete_trigger(db, trigger_id, user.id):
        raise _not_found()


@router.post("/{trigger_id}/pause", response_model=TriggerResponse)
async def pause_trigger(
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trigger = await svc.pause_trigger(db, trigger_id, user.id)
    if not trigger:
        raise _not_found()
    return _to_response(trigger)


@router.post("/{trigger_id}/resume", response_model=TriggerResponse)
async def resume_trigger(
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trigger = await svc.resume_trigger(db, trigger_id, user.id)
    if not trigger:
        raise _not_found()
    return _to_response(trigger)


@router.post("/{trigger_id}/fire", response_model=WebhookFireResponse)
async def manual_fire(
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trigger = await svc.get_trigger(db, trigger_id, user.id)
    if not trigger:
        raise _not_found()
    log = await svc.fire_trigger(db, trigger, payload={"source": "manual"})
    await db.commit()
    return {
        "trigger_id": str(trigger.id),
        "mission_id": str(trigger.mission_id),
        "log_id": str(log.id),
        "status": "fired",
    }


@router.post("/{trigger_id}/fire-graph")
async def fire_graph(
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fire a trigger that executes a graph workflow instead of a mission."""
    trigger = await svc.get_trigger(db, trigger_id, user.id)
    if not trigger:
        raise _not_found()

    # Check if trigger has a graph workflow configured
    config = trigger.config or {}
    graph_workflow_id = config.get("graph_workflow_id")
    if not graph_workflow_id:
        raise HTTPException(
            status_code=400,
            detail="Trigger not configured for graph execution. Set graph_workflow_id in trigger config.",
        )

    from app.services.graph_service import execute_graph_workflow

    execution = await execute_graph_workflow(
        db,
        graph_workflow_id,
        user.id,
        input_data={"trigger_id": str(trigger.id), "source": "trigger"},
    )
    await db.commit()

    return {
        "trigger_id": str(trigger.id),
        "graph_workflow_id": str(graph_workflow_id),
        "execution_id": str(execution.id),
        "status": "fired",
    }


@router.get("/{trigger_id}/logs", response_model=TriggerLogListResponse)
async def get_trigger_logs(
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logs = await svc.get_trigger_logs(db, trigger_id, user.id)
    return {"logs": [_to_log_response(l) for l in logs], "total": len(logs)}


# ── Public webhook endpoint ───────────────────────────────────────────────────


@router.post("/webhook/{webhook_path}", response_model=WebhookFireResponse)
async def webhook_fire(
    webhook_path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint: external systems POST here to fire a webhook trigger.

    Authenticates via HMAC-SHA256 signature in X-Signature header.
    Phase 8.5: Rate-limited to 30 requests per minute per source IP.
    """
    # Phase 8.5: Rate limit inbound webhooks by source IP
    client_ip = request.client.host if request.client else "unknown"
    _rate_key = f"webhook_trigger:{webhook_path}:{client_ip}"
    try:
        from app.services.auth_rate_limiter import check_rate_limit

        is_allowed, remaining, retry_after = check_rate_limit(
            _rate_key, max_requests=30, window_seconds=60
        )
        if not is_allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
    except ImportError:
        pass  # Rate limiter not available — skip
    except HTTPException:
        raise
    except Exception:
        pass  # Rate limiter error — don't block webhook

    trigger = await svc.get_trigger_by_webhook_path(db, webhook_path)
    if not trigger:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Read body for signature verification
    body = await request.body()
    signature = request.headers.get("X-Signature") or request.headers.get(
        "X-Hub-Signature-256", ""
    )

    sig_valid = None
    if trigger.webhook_secret:
        if not signature:
            raise HTTPException(status_code=401, detail="Missing X-Signature header")
        sig_valid = svc.verify_webhook_signature(
            body, trigger.webhook_secret, signature
        )
        if not sig_valid:
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse body as JSON for payload logging
    payload = None
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw_body": body.decode("utf-8", errors="replace")[:1000]}

    log = await svc.fire_trigger(
        db,
        trigger,
        payload={"source": "webhook", "body": payload, "signature_valid": sig_valid},
    )
    await db.commit()

    return {
        "trigger_id": str(trigger.id),
        "mission_id": str(trigger.mission_id),
        "log_id": str(log.id),
        "status": "fired",
    }
