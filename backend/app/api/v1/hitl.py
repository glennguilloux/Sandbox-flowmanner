"""HITL Inbox API — Phase 6.2.

Endpoints:
- GET  /inbox/           — List pending inbox items
- GET  /inbox/counts     — Count of pending items for current user
- POST /inbox/bulk-resolve — Bulk resolve multiple inbox items
- GET  /inbox/by-mission/{mission_id} — Get inbox items for a mission
- GET  /inbox/{id}       — Get a specific inbox item
- POST /inbox/{id}/approve  — Approve an approval request
- POST /inbox/{id}/reject   — Reject an approval request
- POST /inbox/{id}/clarify  — Respond to a clarification request
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_workspace_id
from app.database import get_db
from app.models.hitl_models import HumanInterruptType, InboxItemStatus
from app.services.hitl_service import HITLService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inbox", tags=["inbox"])


# ── Error helper ───────────────────────────────────────────────────


def _error_response(status_code: int, code: str, error: str, details: dict | None = None) -> HTTPException:
    """Return a structured error response matching project conventions."""
    return HTTPException(
        status_code=status_code,
        detail={"error": error, "code": code, "details": details},
    )


# ── Request/response schemas ───────────────────────────────────────


class ResolveRequest(BaseModel):
    resolution_note: str | None = None
    resolution_payload: dict | None = None


class ClarifyRequest(BaseModel):
    response_text: str
    resolution_payload: dict | None = None


class BulkResolveRequest(BaseModel):
    """Request body for bulk inbox item resolution."""

    item_ids: list[str] = Field(..., min_length=1, max_length=100)
    action: Literal["approve", "reject"]
    resolution_note: str | None = Field(None, max_length=2000)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "item_ids": ["uuid-1", "uuid-2"],
                    "action": "approve",
                    "resolution_note": "LGTM — bulk-approved after code review",
                }
            ]
        }
    }


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
    """List pending inbox items for the current user.

    Hardened (Q1-B chunk 3):
    - Validates interrupt_type against HumanInterruptType enum (422 on invalid)
    - Optional workspace_id filter for defense-in-depth
    """
    # Validate interrupt_type
    if interrupt_type is not None:
        valid_types = {t.value for t in HumanInterruptType}
        if interrupt_type not in valid_types:
            raise _error_response(
                422,
                "VALIDATION_ERROR",
                f"Invalid interrupt_type: {interrupt_type}",
                details={"valid_types": sorted(valid_types)},
            )

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
) -> dict[str, int]:
    """Count of pending items for the current user.

    Hardened (Q1-B chunk 3): when workspace_id is supplied, counts only
    items in that workspace.
    """
    service = HITLService(db)
    count = await service.count_pending(user_id=user.id, workspace_id=workspace_id)
    return {"pending_count": count}


@router.post("/bulk-resolve")
async def bulk_resolve_items(
    body: BulkResolveRequest,
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bulk resolve multiple inbox items.

    Approve or reject up to 100 items in one request. Items that cannot be
    resolved (not found, wrong status, forbidden) are skipped rather than
    failing the entire batch.
    """
    service = HITLService(db)

    status = InboxItemStatus.APPROVED if body.action == "approve" else InboxItemStatus.REJECTED

    result = await service.bulk_resolve(
        item_ids=body.item_ids,
        resolved_by=user.id,
        status=status,
        workspace_id=workspace_id,
        resolution_note=body.resolution_note,
    )

    return result


@router.get("/by-mission/{mission_id}")
async def list_by_mission(
    mission_id: str,
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get all inbox items for a mission, scoped to the current user."""
    service = HITLService(db)

    items = await service.get_by_mission(
        mission_id=mission_id,
        user_id=user.id,
        workspace_id=workspace_id,
    )

    return [HITLService._item_to_dict(item) for item in items]


# ── SSE Stream (real-time inbox updates) ──────────────────────────


@router.get("/stream")
async def inbox_stream(
    token: str = "",
):
    """SSE endpoint for real-time HITL inbox updates.

    Accepts token as query parameter for EventSource compatibility.
    Subscribes to the user's Redis notification channel and forwards
    only HITL inbox events (interrupt_raised, interrupt_resolved).

    Uses hitl_inbox_sse_stream which filters for inbox-specific events
    and sends them with event type 'hitl_inbox'.
    """
    from fastapi.responses import StreamingResponse

    # Validate token
    if not token:
        raise _error_response(401, "TOKEN_REQUIRED", "Token required")

    try:
        from app.api.v1.auth import decode_access_token

        user_id_str = decode_access_token(token)
        if not user_id_str:
            raise _error_response(401, "INVALID_TOKEN", "Invalid token")
        user_id = int(user_id_str)
    except HTTPException:
        raise
    except Exception:
        raise _error_response(401, "INVALID_TOKEN", "Invalid token")

    from app.services.sse_service import hitl_inbox_sse_stream

    return StreamingResponse(
        hitl_inbox_sse_stream(user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{item_id}")
async def get_inbox_item(
    item_id: str,
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a specific inbox item.

    Hardened (Q1-B chunk 3): workspace-scoped — if item exists but
    workspace_id does not match, returns 404 (not 403) to prevent
    cross-workspace existence leaks.
    """
    service = HITLService(db)
    item = await service.get_item(item_id)
    if item is None:
        raise _error_response(404, "INBOX_ITEM_NOT_FOUND", "Inbox item not found")
    if item.user_id != user.id:
        raise _error_response(404, "INBOX_ITEM_NOT_FOUND", "Inbox item not found")
    if workspace_id and item.workspace_id != workspace_id:
        # 404, not 403 — don't leak existence across workspaces
        raise _error_response(404, "INBOX_ITEM_NOT_FOUND", "Inbox item not found")
    return HITLService._item_to_dict(item)


async def _maybe_resolve_memory_write(
    item: Any,
    db: Any,
    *,
    approve: bool,
    resolved_by: int,
) -> bool:
    """GOV-1.1: if this inbox item is a memory-write approval, apply/reject the
    staged write through the memory drain instead of signalling a mission.

    Returns True when the item was a MEMORY_APPROVAL (caller must skip the
    executor resume/abort signal). Best-effort: never raises.
    """
    if item.interrupt_type != HumanInterruptType.MEMORY_APPROVAL.value:
        return False
    pwid = (item.context or {}).get("pending_write_id") or ((item.proposed_action or {}).get("pending_write_id"))
    if pwid:
        try:
            from app.services.memory.background_review_service import (
                BackgroundReviewService,
                _MemoryCorrectionReviewAudit,
            )

            # GOV-1.4 (C3): human approve/reject of a memory write must be
            # recorded in the memory-domain audit trail, not just the inbox
            # row flip. Inject the in-session audit sink so the decision
            # persists in the caller's transaction.
            svc = BackgroundReviewService()
            svc.audit = _MemoryCorrectionReviewAudit()
            await svc.resolve_pending_write(
                db,
                pending_write_id=pwid,
                approve=approve,
                resolved_by=resolved_by,
            )
        except Exception as exc:  # best-effort: never raise
            logger.warning(
                "hitl approve/reject: memory write resolve failed pwid=%s: %s",
                pwid,
                exc,
            )
    return True


@router.post("/{item_id}/approve", response_model=dict)
async def approve_item(
    item_id: str,
    body: ResolveRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Approve an approval request. Resumes the paused mission."""
    service = HITLService(db)
    item = await service.get_item(item_id)
    if item is None:
        raise _error_response(404, "INBOX_ITEM_NOT_FOUND", "Inbox item not found")
    if item.user_id != user.id:
        raise _error_response(404, "INBOX_ITEM_NOT_FOUND", "Inbox item not found")
    if item.status != InboxItemStatus.PENDING.value:
        raise _error_response(
            409,
            "INBOX_ITEM_WRONG_STATUS",
            f"Item already {item.status}",
            details={"current_status": item.status},
        )

    # ── Planner-trust: rubber-stamp approval audit ──
    # (side-effect-safety-and-planner-trust skill) A human cannot read and
    # approve an interrupt in under a second. Sub-second resolutions are
    # flagged for sample audit (possible automation/accidental click) and
    # tripped as an observability alarm.
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    from app.services.nexus.observability import get_observability_service

    _now = _datetime.now(_UTC)
    _decision_latency = (_now - (item.created_at or _now)).total_seconds()
    _rubber_stamp = _decision_latency < 1.0
    if _rubber_stamp:
        logger.warning(
            "Rubber-stamp approval detected for inbox item %s: "
            "resolved after %.3fs (< 1.0s). Flagging for sample audit.",
            item.id,
            _decision_latency,
        )
        try:
            obs = get_observability_service()
            await obs.increment_counter(
                "hitl_rubber_stamp_approval",
                labels={"user_id": str(user.id), "item_id": str(item.id)},
            )
        except Exception:
            logger.debug("observability_rubber_stamp_counter_failed", exc_info=True)

    # GOV-1.1: memory-write approvals apply the staged write, never resume a
    # mission. Skip the executor resume signal when this is a memory approval.
    is_memory = await _maybe_resolve_memory_write(item, db, approve=True, resolved_by=user.id)

    _base_payload: dict = (body.resolution_payload if body else None) or {}
    resolved = await service.resolve_interrupt(
        item_id,
        resolved_by=user.id,
        status=InboxItemStatus.APPROVED,
        resolution_note=body.resolution_note if body else None,
        resolution_payload={
            **_base_payload,
            "rubber_stamp_audit": _rubber_stamp,
            "decision_latency_s": round(_decision_latency, 3),
        },
    )

    # Signal the executor to resume (mission approvals only)
    if not is_memory:
        await _signal_executor_resume(item.mission_id, item.run_id, "approved", resolved)

    return HITLService._item_to_dict(resolved)


@router.post("/{item_id}/reject", response_model=dict)
async def reject_item(
    item_id: str,
    body: ResolveRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reject an approval request. The mission will be aborted."""
    service = HITLService(db)
    item = await service.get_item(item_id)
    if item is None:
        raise _error_response(404, "INBOX_ITEM_NOT_FOUND", "Inbox item not found")
    if item.user_id != user.id:
        raise _error_response(404, "INBOX_ITEM_NOT_FOUND", "Inbox item not found")
    if item.status != InboxItemStatus.PENDING.value:
        raise _error_response(
            409,
            "INBOX_ITEM_WRONG_STATUS",
            f"Item already {item.status}",
            details={"current_status": item.status},
        )

    # ── Planner-trust: rubber-stamp approval audit (applies to reject too) ──
    # (side-effect-safety-and-planner-trust skill) Flag sub-second resolutions
    # for sample audit + observability alarm.
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    from app.services.nexus.observability import get_observability_service

    _now = _datetime.now(_UTC)
    _decision_latency = (_now - (item.created_at or _now)).total_seconds()
    _rubber_stamp = _decision_latency < 1.0
    if _rubber_stamp:
        logger.warning(
            "Rubber-stamp rejection detected for inbox item %s: "
            "resolved after %.3fs (< 1.0s). Flagging for sample audit.",
            item.id,
            _decision_latency,
        )
        try:
            obs = get_observability_service()
            await obs.increment_counter(
                "hitl_rubber_stamp_approval",
                labels={"user_id": str(user.id), "item_id": str(item.id)},
            )
        except Exception:
            logger.debug("observability_rubber_stamp_counter_failed", exc_info=True)

    # GOV-1.1: memory-write rejections reject the staged write, never abort a
    # mission. Skip the executor abort signal when this is a memory approval.
    is_memory = await _maybe_resolve_memory_write(item, db, approve=False, resolved_by=user.id)

    _base_payload: dict = (body.resolution_payload if body else None) or {}
    resolved = await service.resolve_interrupt(
        item_id,
        resolved_by=user.id,
        status=InboxItemStatus.REJECTED,
        resolution_note=body.resolution_note if body else None,
        resolution_payload={
            **_base_payload,
            "rubber_stamp_audit": _rubber_stamp,
            "decision_latency_s": round(_decision_latency, 3),
        },
    )

    # Signal the executor — rejection means abort (mission approvals only)
    if not is_memory:
        await _signal_executor_abort(item.mission_id, item.run_id, "rejected_by_human")

    return HITLService._item_to_dict(resolved)


@router.post("/{item_id}/clarify", response_model=dict)
async def clarify_item(
    item_id: str,
    body: ClarifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Respond to a clarification request. Resumes the paused mission with the response."""
    service = HITLService(db)
    item = await service.get_item(item_id)
    if item is None:
        raise _error_response(404, "INBOX_ITEM_NOT_FOUND", "Inbox item not found")
    if item.user_id != user.id:
        raise _error_response(404, "INBOX_ITEM_NOT_FOUND", "Inbox item not found")
    if item.status != InboxItemStatus.PENDING.value:
        raise _error_response(
            409,
            "INBOX_ITEM_WRONG_STATUS",
            f"Item already {item.status}",
            details={"current_status": item.status},
        )
    if item.interrupt_type != HumanInterruptType.CLARIFICATION.value:
        raise _error_response(
            400,
            "INBOX_ITEM_WRONG_TYPE",
            "Item is not a clarification request",
            details={"actual_type": item.interrupt_type},
        )

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
