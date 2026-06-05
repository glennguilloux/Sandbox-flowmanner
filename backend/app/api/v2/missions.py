"""V2 Missions endpoints — thin wrappers using CQRS handler DI.

Cross-cutting concerns: idempotency, per-user rate limiting, auditing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api._mission_cqrs.deps import get_mission_commands, get_mission_queries
from app.api.deps import get_current_user
from app.api.v2.base import ok, paginated
from app.api.v2.cursor_pagination import CursorParams, cursor_paginated
from app.api.v2.idempotency import idempotency
from app.api.v2.rate_limit import rate_limit
from app.database import get_db
from app.schemas.mission import (
    MissionCreate,
    MissionExecuteRequest,
    MissionImprovementCreate,
    MissionLogCreate,
    MissionLogResponse,
    MissionResponse,
    MissionTaskCreate,
    MissionTaskResponse,
    MissionTaskUpdate,
    MissionUpdate,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.api._mission_cqrs.commands import MissionCommandHandlers
    from app.api._mission_cqrs.queries import MissionQueryHandlers
    from app.models.user import User

router = APIRouter(prefix="/missions", tags=["v2-missions"])


# ── List / Create (CQRS DI) ───────────────────────────────────────────────────

@router.get("")
@router.get("/")
async def list_items(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, description="Opaque cursor token from a previous response (enables keyset pagination)"),
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    if cursor:
        # Keyset pagination: decode cursor and fetch after the referenced item
        from app.models.mission_models import Mission
        cp = CursorParams(cursor=cursor, direction="after", limit=per_page)
        decoded = cp.decoded
        query = select(Mission).where(
            Mission.user_id == user.id,
            Mission.deleted_at.is_(None),
            Mission.id > str(decoded["id"]),
        ).order_by(Mission.id.asc()).limit(per_page + 1)
        result = await q.session.execute(query)
        items = list(result.scalars().all())
        serialized = [MissionResponse.model_validate(m).model_dump() for m in items]
        return cursor_paginated(
            items=serialized,
            limit=per_page,
            cursor_params=cp,
            item_id_fn=lambda x: x["id"],
            item_ts_fn=lambda x: x.get("created_at"),
        )
    # Offset pagination (default)
    r = await q.list_missions(user.id, page, per_page)
    return paginated(items=[i.model_dump() for i in r.items], total=r.total, page=r.page, per_page=r.per_page)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: MissionCreate,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
    _idem: Any = Depends(idempotency()),
    _rate: Any = Depends(rate_limit("mission:create")),
):
    if isinstance(_idem, JSONResponse):
        return _idem
    if isinstance(_rate, JSONResponse):
        return _rate
    m = await c.create_mission(user, payload)
    return ok(MissionResponse.model_validate(m).model_dump())


# ── Active (CQRS DI) ──────────────────────────────────────────────────────────

@router.get("/active")
async def list_active(
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    missions = await q.list_active(user.id)
    return ok([MissionResponse.model_validate(m).model_dump() for m in missions])


# ── CRUD (CQRS DI) ────────────────────────────────────────────────────────────

@router.get("/{mission_id}")
@router.get("/{mission_id}/")
async def get_item(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return ok((await q.get_mission_response(user.id, mission_id)).model_dump())


@router.patch("/{mission_id}")
async def patch_item(
    mission_id: uuid.UUID,
    payload: MissionUpdate,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
    _idem: Any = Depends(idempotency()),
    _rate: Any = Depends(rate_limit("mission:update")),
):
    if isinstance(_idem, JSONResponse):
        return _idem
    if isinstance(_rate, JSONResponse):
        return _rate
    return ok(MissionResponse.model_validate(await c.update_mission(user, mission_id, payload)).model_dump())


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
    _idem: Any = Depends(idempotency()),
    _rate: Any = Depends(rate_limit("mission:delete")),
):
    if isinstance(_idem, JSONResponse):
        return _idem
    if isinstance(_rate, JSONResponse):
        return _rate
    await c.delete_mission(user, mission_id)


# ── Tasks (CQRS DI) ───────────────────────────────────────────────────────────

@router.get("/{mission_id}/tasks")
@router.get("/{mission_id}/tasks/")
async def list_tasks(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    tasks = await q.list_tasks(user.id, mission_id)
    return ok([MissionTaskResponse.model_validate(t).model_dump() for t in tasks])


@router.post("/{mission_id}/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(
    mission_id: uuid.UUID,
    payload: MissionTaskCreate,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok(MissionTaskResponse.model_validate(await c.create_task(user, mission_id, payload)).model_dump())


@router.patch("/{mission_id}/tasks/{task_id}")
async def update_task(
    mission_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: MissionTaskUpdate,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok(MissionTaskResponse.model_validate(await c.update_task(user, mission_id, task_id, payload)).model_dump())


# ── Logs (CQRS DI) ────────────────────────────────────────────────────────────

@router.get("/{mission_id}/logs")
@router.get("/{mission_id}/logs/")
async def list_logs(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    logs = await q.list_logs(user.id, mission_id)
    return ok([l.model_dump() for l in logs])


@router.post("/{mission_id}/logs", status_code=status.HTTP_201_CREATED)
async def create_log(
    mission_id: uuid.UUID,
    payload: MissionLogCreate,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok(MissionLogResponse.model_validate(await c.create_log(user, mission_id, payload)).model_dump())


# ── Planning (CQRS DI) ────────────────────────────────────────────────────────

@router.post("/{mission_id}/plan")
async def plan_mission(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok((await c.plan_mission(user, mission_id)).model_dump())


# ── Execution (CQRS DI) ───────────────────────────────────────────────────────

@router.post("/{mission_id}/execute")
async def execute_mission(
    mission_id: uuid.UUID,
    payload: MissionExecuteRequest | None = None,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
    _idem: Any = Depends(idempotency()),
    _rate: Any = Depends(rate_limit("mission:execute")),
):
    if isinstance(_idem, JSONResponse):
        return _idem
    if isinstance(_rate, JSONResponse):
        return _rate
    return ok((await c.execute_mission(user, mission_id, payload)).model_dump())


@router.post("/{mission_id}/execute-async")
async def execute_mission_async(
    mission_id: uuid.UUID,
    payload: MissionExecuteRequest | None = None,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok((await c.execute_async(user, mission_id, payload)).model_dump())


# ── Abort (CQRS DI) ───────────────────────────────────────────────────────────

@router.post("/{mission_id}/abort")
async def abort_mission(
    mission_id: uuid.UUID,
    reason: str = "user_requested",
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
    _idem: Any = Depends(idempotency()),
    _rate: Any = Depends(rate_limit("mission:abort")),
):
    if isinstance(_idem, JSONResponse):
        return _idem
    if isinstance(_rate, JSONResponse):
        return _rate
    return ok((await c.abort_mission(user, mission_id, reason)).model_dump())


# ── Status / Streaming ────────────────────────────────────────────────────────

@router.get("/{mission_id}/status")
@router.get("/{mission_id}/status/")
async def get_mission_status(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return ok((await q.get_status(user.id, mission_id)).model_dump())


@router.get("/{mission_id}/stream")
@router.get("/{mission_id}/stream/")
async def stream_mission_status(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    """SSE stream — CQRS handler polls mission status until terminal."""
    mission = await q.get_mission(user.id, mission_id)
    return q.stream_status(user.id, mission_id, mission)


# ── Lifecycle: Pause / Resume / Retry (CQRS DI) ───────────────────────────────

@router.post("/{mission_id}/pause")
async def pause_mission(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok((await c.pause_mission(user, mission_id)).model_dump())


@router.post("/{mission_id}/resume")
async def resume_mission(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok((await c.resume_mission(user, mission_id)).model_dump())


@router.post("/{mission_id}/retry")
async def retry_mission(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok((await c.retry_mission(user, mission_id)).model_dump())


@router.post("/batch-abort")
async def batch_abort(
    mission_ids: list[uuid.UUID],
    reason: str = "user_requested",
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok(await c.batch_abort(user, mission_ids, reason))


@router.post("/from-template/{template_id}", status_code=status.HTTP_201_CREATED)
async def create_from_template(
    template_id: uuid.UUID,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok(MissionResponse.model_validate(await c.create_from_template(user, template_id)).model_dump())


# ── Improvements (CQRS DI) ────────────────────────────────────────────────────

@router.get("/{mission_id}/improvements")
@router.get("/{mission_id}/improvements/")
async def list_improvements(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return ok([i.model_dump() for i in await q.list_improvements(user.id, mission_id)])


@router.post("/{mission_id}/improvements", status_code=status.HTTP_201_CREATED)
async def create_improvement(
    mission_id: uuid.UUID,
    payload: MissionImprovementCreate,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok((await c.create_improvement(user, mission_id, payload)).model_dump())


@router.post("/{mission_id}/improvements/{improvement_id}/apply")
async def apply_improvement(
    mission_id: uuid.UUID,
    improvement_id: uuid.UUID,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return ok(await c.apply_improvement(user, mission_id, improvement_id))


# ── Analytics (CQRS DI) ───────────────────────────────────────────────────────

@router.get("/{mission_id}/analytics")
@router.get("/{mission_id}/analytics/")
async def get_mission_analytics_endpoint(
    mission_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return ok(await q.mission_analytics(user.id, mission_id, days))


@router.get("/analytics")
async def get_global_analytics(
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return ok(await q.global_analytics(user.id))


# ── Human Approval (HITL) ─────────────────────────────────────────────────────

@router.post("/{mission_id}/tasks/{task_id}/approve")
async def approve_task(
    mission_id: uuid.UUID,
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
    db: AsyncSession = Depends(get_db),
):
    """Approve a task awaiting human approval — resolves interrupt and resumes mission."""
    from app.models.mission_models import Mission, MissionStatus, MissionTask
    from app.orchestration.human_interrupt import get_hitl_manager

    # Verify mission exists and belongs to user
    mission = await q.get_mission(user.id, mission_id)
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found")

    # Find pending interrupt for this specific task
    hitl = get_hitl_manager()
    pending = await hitl.list_pending(db, str(mission_id))
    matching = [
        p for p in pending
        if (p.get("proposed_action") or {}).get("task_id") == str(task_id)
    ]
    if not matching:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending approval found for this task")

    interrupt_id = matching[0]["id"]
    await hitl.resolve_interrupt(db, interrupt_id, "approved", resolved_by=str(user.id))

    # Clear approval flag and resume mission
    task_obj = (await db.execute(
        select(MissionTask).where(MissionTask.id == str(task_id))
    )).scalars().first()
    if task_obj:
        task_obj.approval_required = False

    mission_obj = (await db.execute(
        select(Mission).where(Mission.id == str(mission_id))
    )).scalars().first()
    if mission_obj and mission_obj.status == MissionStatus.PAUSED:
        mission_obj.status = MissionStatus.QUEUED
    await db.commit()

    return ok({"status": "approved", "mission_id": str(mission_id), "interrupt_id": interrupt_id})


@router.post("/{mission_id}/tasks/{task_id}/reject")
async def reject_task(
    mission_id: uuid.UUID,
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
    db: AsyncSession = Depends(get_db),
):
    """Reject a task awaiting human approval — fails the task and marks mission for retry."""
    from app.models.mission_models import Mission, MissionStatus, MissionTask, MissionTaskStatus
    from app.orchestration.human_interrupt import get_hitl_manager

    # Verify mission exists and belongs to user
    mission = await q.get_mission(user.id, mission_id)
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found")

    # Find pending interrupt for this specific task
    hitl = get_hitl_manager()
    pending = await hitl.list_pending(db, str(mission_id))
    matching = [
        p for p in pending
        if (p.get("proposed_action") or {}).get("task_id") == str(task_id)
    ]
    if not matching:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending approval found for this task")

    interrupt_id = matching[0]["id"]
    await hitl.resolve_interrupt(db, interrupt_id, "rejected", resolved_by=str(user.id))

    # Fail the task (transition PENDING → RUNNING → FAILED to respect state machine)
    task_obj = (await db.execute(
        select(MissionTask).where(MissionTask.id == str(task_id))
    )).scalars().first()
    if task_obj:
        task_obj.approval_required = False
        task_obj.status = MissionTaskStatus.RUNNING  # valid: PENDING → RUNNING
        await db.flush()
        task_obj.status = MissionTaskStatus.FAILED   # valid: RUNNING → FAILED
        task_obj.error_message = "Rejected by user"

    mission_obj = (await db.execute(
        select(Mission).where(Mission.id == str(mission_id))
    )).scalars().first()
    if mission_obj:
        mission_obj.status = MissionStatus.FAILED
        mission_obj.error_message = f"Task '{task_obj.title if task_obj else task_id}' rejected by user"
        await db.commit()

    return ok({"status": "rejected", "mission_id": str(mission_id), "interrupt_id": interrupt_id})
