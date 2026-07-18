from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import func, select

from app.models.mission_models import Mission, MissionLog, MissionTask, MissionStatus, MissionTaskStatus
from app.services.mission_errors import MissionNotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def create_mission(
    db: AsyncSession,
    title: str,
    description: str = "",
    mission_type: str | None = None,
    priority: str | None = None,
    user_id: int | None = None,
    status: str = "pending",
    workspace_id: str | None = None,
) -> Mission:
    mission = Mission(
        id=uuid4(),
        title=title,
        description=description or "",
        mission_type=mission_type,
        priority=priority,
        user_id=user_id or 1,
        status=status,
        workspace_id=workspace_id,
    )
    db.add(mission)
    await db.flush()
    await db.refresh(mission)
    return mission


async def get_mission(db: AsyncSession, mission_id, *, include_deleted: bool = False) -> Mission | None:
    stmt = select(Mission).where(Mission.id == str(mission_id))
    if not include_deleted:
        stmt = stmt.where(Mission.deleted_at.is_(None))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def require_mission_access(
    db: AsyncSession,
    mission_id,
    user_id: int,
    *,
    include_deleted: bool = False,
) -> Mission:
    """Fetch a mission and verify the user has access.

    Access rules:
    1. If the mission has a workspace_id → verify the user is an active member
       of that workspace.
    2. If the mission has no workspace_id → fall back to user_id ownership.
    3. If the mission doesn't exist → 404.
    """
    mission = await get_mission(db, mission_id, include_deleted=include_deleted)
    if mission is None:
        raise MissionNotFoundError("Mission not found")

    if mission.workspace_id:
        from app.models.workspace_models import WorkspaceMember

        result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == mission.workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.is_active == True,
            )
        )
        if result.scalar_one_or_none() is None:
            # Check cross-workspace grants across all user's workspaces
            from app.services.cross_workspace_service import (
                check_entity_access,
                find_user_workspaces,
            )

            user_workspaces = await find_user_workspaces(db, user_id)
            has_cross_access = False
            for ws_id in user_workspaces:
                if ws_id == mission.workspace_id:
                    continue
                grant = await check_entity_access(
                    db,
                    user_id=user_id,
                    target_workspace_id=ws_id,
                    entity_type="mission",
                    entity_id=str(mission_id),
                    required_permission="read",
                )
                if grant:
                    has_cross_access = True
                    break
            if not has_cross_access:
                logger.warning(
                    "entity_access_denied"
                    " user_id=%s entity_type=mission entity_id=%s"
                    " workspace_id=%s reason=no_membership",
                    user_id,
                    mission_id,
                    mission.workspace_id,
                )
                try:
                    import asyncio

                    from app.api.middleware.audit import log_event

                    asyncio.create_task(
                        log_event(
                            user_id=user_id,
                            action="entity.access_denied",
                            details={
                                "entity_type": "mission",
                                "entity_id": str(mission_id),
                                "workspace_id": str(mission.workspace_id),
                                "reason": "no_membership",
                            },
                        )
                    )
                except Exception:
                    pass
                raise MissionNotFoundError("Mission not found")
    else:
        if mission.user_id != user_id:
            logger.warning(
                "entity_access_denied"
                " user_id=%s entity_type=mission entity_id=%s"
                " owner_user_id=%s reason=owner_mismatch",
                user_id,
                mission_id,
                mission.user_id,
            )
            try:
                import asyncio

                from app.api.middleware.audit import log_event

                asyncio.create_task(
                    log_event(
                        user_id=user_id,
                        action="entity.access_denied",
                        details={
                            "entity_type": "mission",
                            "entity_id": str(mission_id),
                            "reason": "owner_mismatch",
                        },
                    )
                )
            except Exception:
                pass
            raise MissionNotFoundError("Mission not found")

    return mission


async def list_missions(
    db: AsyncSession,
    user_id: int | None = None,
    *,
    offset: int = 0,
    limit: int = 20,
    include_deleted: bool = False,
    workspace_id: str | None = None,
) -> tuple[list[Mission], int]:
    base = select(Mission)
    if not include_deleted:
        base = base.where(Mission.deleted_at.is_(None))
    if workspace_id is not None:
        base = base.where(Mission.workspace_id == workspace_id)
    elif user_id is not None:
        base = base.where(Mission.user_id == user_id)

    count_q = select(func.count()).select_from(Mission)
    if not include_deleted:
        count_q = count_q.where(Mission.deleted_at.is_(None))
    if workspace_id is not None:
        count_q = count_q.where(Mission.workspace_id == workspace_id)
    elif user_id is not None:
        count_q = count_q.where(Mission.user_id == user_id)
    total = (await db.execute(count_q)).scalar() or 0

    items_q = base.order_by(Mission.created_at.desc()).offset(offset).limit(limit)
    items = list((await db.execute(items_q)).scalars().all())
    return items, total


async def update_mission(
    db: AsyncSession,
    mission_id,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    mission_type: str | None = None,
    error_message: str | None = None,
    results: dict | None = None,
    tokens_used: int | None = None,
    actual_cost: float | None = None,
) -> Mission | None:
    mission = await get_mission(db, mission_id)
    if mission is None:
        return None

    if title is not None:
        mission.title = title
    if description is not None:
        mission.description = description
    if status is not None:
        mission.status = MissionStatus(status)
        if status == "running" and mission.started_at is None:
            mission.started_at = datetime.now(UTC)
        if status in ("completed", "failed", "cancelled"):
            mission.completed_at = datetime.now(UTC)
    if priority is not None:
        mission.priority = priority
    if mission_type is not None:
        mission.mission_type = mission_type
    if error_message is not None:
        mission.error_message = error_message
    if results is not None:
        mission.results = results
    if tokens_used is not None:
        mission.tokens_used = tokens_used
    if actual_cost is not None:
        mission.actual_cost = actual_cost

    await db.flush()
    await db.refresh(mission)
    return mission


async def delete_mission(db: AsyncSession, mission_id, deleted_by: int | None = None) -> bool:
    """Soft-delete a mission — sets deleted_at, preserves referential integrity for tasks/logs."""
    from datetime import datetime

    mission = await get_mission(db, mission_id)
    if mission is None or mission.deleted_at is not None:
        return False
    mission.deleted_at = datetime.now(UTC)
    mission.deleted_by = deleted_by
    await db.flush()
    return True


async def create_mission_task(
    db: AsyncSession,
    mission_id,
    title: str,
    task_type: str = "general",
    status: str = "pending",
    order_index: int | None = None,
    input_data: dict | None = None,
    description: str | None = None,
    assigned_agent_id: str | None = None,
    assigned_model: str | None = None,
) -> MissionTask:
    if order_index is None:
        max_idx = (
            await db.execute(
                select(func.coalesce(func.max(MissionTask.order_index), -1)).where(
                    MissionTask.mission_id == str(mission_id)
                )
            )
        ).scalar() or 0
        order_index = max_idx + 1

    task = MissionTask(
        id=uuid4(),
        mission_id=str(mission_id),
        title=title,
        description=description,
        task_type=task_type,
        status=status,
        order_index=order_index,
        input_data=input_data,
        assigned_agent_id=assigned_agent_id,
        assigned_model=assigned_model,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def get_mission_tasks(db: AsyncSession, mission_id) -> list[MissionTask]:
    result = await db.execute(
        select(MissionTask)
        .where(MissionTask.mission_id == str(mission_id))
        .order_by(MissionTask.order_index.asc(), MissionTask.created_at.asc())
    )
    return list(result.scalars().all())


async def update_mission_task(
    db: AsyncSession,
    task_id,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    output_data: dict | None = None,
    tokens_used: int | None = None,
    cost: float | None = None,
) -> MissionTask | None:
    result = await db.execute(select(MissionTask).where(MissionTask.id == str(task_id)))
    task = result.scalar_one_or_none()
    if task is None:
        return None

    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if status is not None:
        task.status = MissionTaskStatus(status)
        if status == "running" and task.started_at is None:
            task.started_at = datetime.now(UTC)
        if status in ("completed", "failed", "cancelled"):
            task.completed_at = datetime.now(UTC)
    if output_data is not None:
        task.output_data = output_data
    if tokens_used is not None:
        task.tokens_used = tokens_used
    if cost is not None:
        task.cost = cost

    await db.flush()
    await db.refresh(task)
    return task


async def create_mission_log(
    db: AsyncSession,
    mission_id,
    level: str,
    message: str,
    task_id: str | None = None,
    data: dict | None = None,
) -> MissionLog:
    log = MissionLog(
        id=uuid4(),
        mission_id=str(mission_id),
        task_id=task_id,
        level=level,
        message=message,
        data=data,
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return log


async def get_mission_logs(db: AsyncSession, mission_id, limit: int = 100) -> list[MissionLog]:
    result = await db.execute(
        select(MissionLog)
        .where(MissionLog.mission_id == str(mission_id))
        .order_by(MissionLog.timestamp.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
