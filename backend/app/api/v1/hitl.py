"""HITL Inbox API — Phase 6.2.

Endpoints:
- GET  /inbox/           — List pending inbox items
- GET  /inbox/{id}       — Get a specific inbox item
- POST /inbox/{id}/approve  — Approve an approval request
- POST /inbox/{id}/reject   — Reject an approval request
- POST /inbox/{id}/clarify  — Respond to a clarification request
- GET  /inbox/counts     — Count of pending items for current user
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user, get_workspace_id
from app.database import get_db
from app.models.hitl_models import HumanInterruptType, InboxItemStatus
from app.services.hitl_service import HITLService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inbox", tags=["inbox"])


# ── Request/response schemas ───────────────────────────────────────


class ResolveRequest(BaseModel):
    resolution_note: str | None = None
    resolution_payload: dict | None = None


class ClarifyRequest(BaseModel):
    response_text: str
    resolution_payload: dict | None = None


# ── Endpoints ──────────────────────────────────────────────────────


@router.get("/")
async def list_inbox(
    interrupt_type: str | None = Query(None, description="Filter by type: approval, clarification, escalation"),
    mission_id: str | None = Query(None, description="Filter by mission"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    workspace_id: str | None = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List pending inbox items for the current user."""
    service = HITLService(db)

    # For listing, we show pending items by default
    effective_status = status or "pending"

    if effective_status == "pending":
        result = await service.list_pending(
            user_id=user.id,
            workspace_id=workspace_id,
            interrupt_type=interrupt_type,
            mission_id=mission_id,
            limit=limit,
            offset=offset,
        )
    else:
        # For non-pending statuses, use a broader query
        from sqlalchemy import and_, func, select

        from app.models.hitl_models import InboxItem

        conditions = [InboxItem.user_id == user.id]
        if workspace_id:
            conditions.append(InboxItem.workspace_id == workspace_id)
        if interrupt_type:
            conditions.append(InboxItem.interrupt_type == interrupt_type)
        if mission_id:
            conditions.append(InboxItem.mission_id == mission_id)
        if effective_status != "all":
            conditions.append(InboxItem.status == effective_status)

        where = and_(*conditions)
        count_stmt = select(func.count()).select_from(InboxItem).where(where)
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = select(InboxItem).where(where).order_by(InboxItem.created_at.desc()).offset(offset).limit(limit)
        items = (await db.execute(stmt)).scalars().all()
        result = {
            "items": [HITLService._item_to_dict(i) for i in items],
            "total": total,
        }

    return result


@router.get("/counts")
async def inbox_counts(
    workspace_id: str | None = Depends(get_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Count of pending items for the current user."""
    service = HITLService(db)
    count = await service.count_pending(user_id=user.id, workspace_id=workspace_id)
    return {"pending_count": count}


@router.get("/{item_id}")
async def get_inbox_item(
    item_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific inbox item."""
    service = HITLService(db)
    item = await service.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inbox item not found")
    if item.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your inbox item")
    return HITLService._item_to_dict(item)


@router.post("/{item_id}/approve")
async def approve_item(
    item_id: str,
    body: ResolveRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve an approval request. Resumes the paused mission."""
    service = HITLService(db)
    item = await service.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inbox item not found")
    if item.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your inbox item")
    if item.status != InboxItemStatus.PENDING.value:
        raise HTTPException(status_code=409, detail=f"Item already {item.status}")

    resolved = await service.resolve_interrupt(
        item_id,
        resolved_by=user.id,
        status=InboxItemStatus.APPROVED,
        resolution_note=body.resolution_note if body else None,
        resolution_payload=body.resolution_payload if body else None,
    )

    # Signal the executor to resume
    await _signal_executor_resume(item.mission_id, item.run_id, "approved", resolved)

    return HITLService._item_to_dict(resolved)


@router.post("/{item_id}/reject")
async def reject_item(
    item_id: str,
    body: ResolveRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject an approval request. The mission will be aborted."""
    service = HITLService(db)
    item = await service.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inbox item not found")
    if item.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your inbox item")
    if item.status != InboxItemStatus.PENDING.value:
        raise HTTPException(status_code=409, detail=f"Item already {item.status}")

    resolved = await service.resolve_interrupt(
        item_id,
        resolved_by=user.id,
        status=InboxItemStatus.REJECTED,
        resolution_note=body.resolution_note if body else None,
        resolution_payload=body.resolution_payload if body else None,
    )

    # Signal the executor — rejection means abort
    await _signal_executor_abort(item.mission_id, item.run_id, "rejected_by_human")

    return HITLService._item_to_dict(resolved)


@router.post("/{item_id}/clarify")
async def clarify_item(
    item_id: str,
    body: ClarifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Respond to a clarification request. Resumes the paused mission with the response."""
    service = HITLService(db)
    item = await service.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inbox item not found")
    if item.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your inbox item")
    if item.status != InboxItemStatus.PENDING.value:
        raise HTTPException(status_code=409, detail=f"Item already {item.status}")
    if item.interrupt_type != HumanInterruptType.CLARIFICATION.value:
        raise HTTPException(status_code=400, detail="Item is not a clarification request")

    payload = body.resolution_payload or {}
    payload["response_text"] = body.response_text

    resolved = await service.resolve_interrupt(
        item_id,
        resolved_by=user.id,
        status=InboxItemStatus.CLARIFIED,
        resolution_payload=payload,
        resolution_note=body.response_text,
    )

    # Signal the executor to resume with the clarification
    await _signal_executor_resume(item.mission_id, item.run_id, "clarified", resolved)

    return HITLService._item_to_dict(resolved)


# ── Executor signal helpers ─────────────────────────────────────────


async def _signal_executor_resume(
    mission_id: str,
    run_id: str | None,
    resolution: str,
    item: Any,
) -> None:
    """Signal the executor to resume after HITL resolution.

    Q1-B chunk 1: Dispatches a durable Celery task that re-enters the
    UnifiedExecutor with the existing run_id.  The executor uses crash
    recovery to rebuild state and re-enter the HITL node, which checks
    the inbox item status and continues.
    """
    if not run_id:
        logger.warning("No run_id for HITL resume — mission %s", mission_id)
        return

    try:
        from app.tasks.hitl_resume import dispatch_hitl_resume

        inbox_item_id = item.id if hasattr(item, "id") else "unknown"
        dispatch_hitl_resume(
            mission_id=mission_id,
            run_id=run_id,
            inbox_item_id=inbox_item_id,
            resolution=resolution,
        )
    except Exception as e:
        logger.warning("Failed to dispatch HITL resume task: %s", e)


async def _signal_executor_abort(
    mission_id: str,
    run_id: str | None,
    reason: str,
) -> None:
    """Signal the executor to abort after HITL rejection."""
    try:
        import json

        from app.services.sse_service import get_redis_client

        redis = await get_redis_client()
        try:
            channel = f"hitl:aborted:{mission_id}"
            message = json.dumps(
                {
                    "mission_id": mission_id,
                    "run_id": run_id,
                    "reason": reason,
                }
            )
            await redis.publish(channel, message)
        finally:
            await redis.aclose()
    except Exception as e:
        logger.debug("Failed to signal executor abort: %s", e)
