from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import func, select

from app.models.graph import GraphExecution, GraphState, GraphWorkflow
from app.services.mission_errors import GraphNotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

try:
    from app.websocket.mission_ws import sio as _socketio_server

    _sio_available = True
except Exception:
    _sio_available = False
    _socketio_server = None


def _broadcast_execution_event(execution_id: str, event: str, data: dict) -> None:
    """Emit a graph execution event to subscribed WebSocket clients."""
    if not _sio_available or _socketio_server is None:
        return
    try:
        import asyncio

        loop = asyncio.get_running_loop()
        asyncio.create_task(_socketio_server.emit(event, data, room=f"graph_exec_{execution_id}"))
    except RuntimeError:
        pass


async def create_graph_workflow(
    db: AsyncSession,
    user_id: int,
    name: str,
    graph_definition: dict | None,
    description: str | None = None,
    workspace_id: str | None = None,
) -> GraphWorkflow:
    workflow = GraphWorkflow(
        id=str(uuid4()),
        name=name,
        description=description,
        graph_definition=graph_definition,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    db.add(workflow)
    await db.flush()
    await db.refresh(workflow)
    return workflow


async def get_graph_workflow(db: AsyncSession, workflow_id) -> GraphWorkflow | None:
    result = await db.execute(select(GraphWorkflow).where(GraphWorkflow.id == str(workflow_id)))
    return result.scalar_one_or_none()


async def require_graph_access(
    db: AsyncSession,
    workflow_id,
    user_id: int,
) -> GraphWorkflow:
    """Fetch a workflow and verify the user has access.

    Access rules:
    1. If the workflow has a workspace_id → verify the user is an active member
       of that workspace.
    2. If the workflow has no workspace_id → fall back to user_id ownership.
    3. If the workflow doesn't exist → 404.
    """
    workflow = await get_graph_workflow(db, workflow_id)
    if workflow is None:
        raise GraphNotFoundError("Graph workflow not found")

    if workflow.workspace_id:
        from app.models.workspace_models import WorkspaceMember

        result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workflow.workspace_id,
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
                if ws_id == workflow.workspace_id:
                    continue
                grant = await check_entity_access(
                    db,
                    user_id=user_id,
                    target_workspace_id=ws_id,
                    entity_type="workflow",
                    entity_id=str(workflow_id),
                    required_permission="read",
                )
                if grant:
                    has_cross_access = True
                    break
            if not has_cross_access:
                logger.warning(
                    "entity_access_denied"
                    " user_id=%s entity_type=workflow entity_id=%s"
                    " workspace_id=%s reason=no_membership",
                    user_id,
                    workflow_id,
                    workflow.workspace_id,
                )
                try:
                    from app.api.middleware.audit import log_event

                    asyncio.create_task(
                        log_event(
                            user_id=user_id,
                            action="entity.access_denied",
                            details={
                                "entity_type": "workflow",
                                "entity_id": str(workflow_id),
                                "workspace_id": str(workflow.workspace_id),
                                "reason": "no_membership",
                            },
                        )
                    )
                except Exception:
                    pass
                raise GraphNotFoundError("Graph workflow not found")
    else:
        if workflow.user_id != user_id:
            logger.warning(
                "entity_access_denied"
                " user_id=%s entity_type=workflow entity_id=%s"
                " owner_user_id=%s reason=owner_mismatch",
                user_id,
                workflow_id,
                workflow.user_id,
            )
            try:
                from app.api.middleware.audit import log_event

                asyncio.create_task(
                    log_event(
                        user_id=user_id,
                        action="entity.access_denied",
                        details={
                            "entity_type": "workflow",
                            "entity_id": str(workflow_id),
                            "reason": "owner_mismatch",
                        },
                    )
                )
            except Exception:
                pass
            raise GraphNotFoundError("Graph workflow not found")

    return workflow


async def list_graph_workflows(
    db: AsyncSession,
    user_id: int,
    *,
    offset: int = 0,
    limit: int = 20,
    workspace_id: str | None = None,
) -> tuple[list[GraphWorkflow], int]:
    if workspace_id is not None:
        base_filter = GraphWorkflow.workspace_id == workspace_id
    else:
        base_filter = GraphWorkflow.user_id == user_id
    count_q = select(func.count()).select_from(GraphWorkflow).where(base_filter)
    total = (await db.execute(count_q)).scalar() or 0

    items_q = (
        select(GraphWorkflow).where(base_filter).order_by(GraphWorkflow.created_at.desc()).offset(offset).limit(limit)
    )
    items = list((await db.execute(items_q)).scalars().all())
    return items, total


async def update_graph_workflow(
    db: AsyncSession,
    workflow_id,
    *,
    name: str | None = None,
    description: str | None = None,
    graph_definition: dict | None = None,
    status: str | None = None,
) -> GraphWorkflow | None:
    workflow = await get_graph_workflow(db, workflow_id)
    if workflow is None:
        return None

    if name is not None:
        workflow.name = name
    if description is not None:
        workflow.description = description
    if graph_definition is not None:
        workflow.graph_definition = graph_definition
    if status is not None:
        workflow.status = status

    await db.flush()
    await db.refresh(workflow)
    return workflow


async def delete_graph_workflow(db: AsyncSession, workflow_id) -> bool:
    workflow = await get_graph_workflow(db, workflow_id)
    if workflow is None:
        return False
    await db.delete(workflow)
    await db.flush()
    return True


async def execute_graph_workflow(
    db: AsyncSession,
    workflow_id,
    user_id: int,
    input_data: dict | None = None,
) -> GraphExecution:
    execution = GraphExecution(
        id=str(uuid4()),
        workflow_id=str(workflow_id),
        user_id=user_id,
        status="pending",
        input_data=input_data,
        started_at=datetime.now(UTC),
    )
    db.add(execution)
    await db.flush()
    await db.refresh(execution)

    # Launch background execution
    asyncio.create_task(_execute_graph_async(None, execution.id, str(workflow_id), user_id, input_data))

    return execution


async def list_graph_executions(
    db: AsyncSession,
    workflow_id,
    user_id: int,
    *,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[GraphExecution], int]:
    base_filter = (GraphExecution.workflow_id == str(workflow_id)) & (GraphExecution.user_id == user_id)

    count_q = select(func.count()).select_from(GraphExecution).where(base_filter)
    total = (await db.execute(count_q)).scalar() or 0

    items_q = (
        select(GraphExecution).where(base_filter).order_by(GraphExecution.created_at.desc()).offset(offset).limit(limit)
    )
    items = list((await db.execute(items_q)).scalars().all())
    return items, total


async def get_graph_execution(db: AsyncSession, execution_id) -> GraphExecution | None:
    result = await db.execute(select(GraphExecution).where(GraphExecution.id == str(execution_id)))
    return result.scalar_one_or_none()


async def get_graph_states(db: AsyncSession, execution_id) -> list[GraphState]:
    result = await db.execute(
        select(GraphState).where(GraphState.execution_id == str(execution_id)).order_by(GraphState.created_at.asc())
    )
    return list(result.scalars().all())


async def resume_graph_execution(
    db: AsyncSession,
    execution_id,
    user_id: int,
) -> GraphExecution | None:
    execution = await get_graph_execution(db, execution_id)
    if execution is None:
        return None
    if execution.status not in ("paused", "failed", "pending"):
        return execution
    execution.status = "running"
    execution.started_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(execution)

    _broadcast_execution_event(
        execution_id,
        "graph:status",
        {
            "execution_id": execution_id,
            "status": "running",
        },
    )

    return execution


# ── Execution Lifecycle ──


async def update_execution_status(
    db: AsyncSession,
    execution_id: str,
    status: str,
    **kwargs,
) -> GraphExecution | None:
    execution = await get_graph_execution(db, execution_id)
    if execution is None:
        return None
    execution.status = status
    if status == "running":
        execution.started_at = datetime.now(UTC)
    if "output_data" in kwargs:
        execution.output_data = kwargs["output_data"]
    if "error_message" in kwargs:
        execution.error_message = kwargs["error_message"]
    await db.flush()
    await db.refresh(execution)

    _broadcast_execution_event(
        execution_id,
        "graph:status",
        {
            "execution_id": execution_id,
            "status": execution.status,
            "output_data": execution.output_data,
            "error_message": execution.error_message,
        },
    )

    return execution


async def complete_execution(
    db: AsyncSession,
    execution_id: str,
    output_data: dict,
) -> GraphExecution | None:
    execution = await get_graph_execution(db, execution_id)
    if execution is None:
        return None
    execution.status = "completed"
    execution.output_data = output_data
    execution.completed_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(execution)

    _broadcast_execution_event(
        execution_id,
        "graph:status",
        {
            "execution_id": execution_id,
            "status": "completed",
            "output_data": output_data,
        },
    )

    return execution


async def fail_execution(
    db: AsyncSession,
    execution_id: str,
    error_message: str,
) -> GraphExecution | None:
    execution = await get_graph_execution(db, execution_id)
    if execution is None:
        return None
    execution.status = "failed"
    execution.error_message = error_message
    execution.completed_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(execution)

    _broadcast_execution_event(
        execution_id,
        "graph:status",
        {
            "execution_id": execution_id,
            "status": "failed",
            "error_message": error_message,
        },
    )

    return execution


async def pause_execution(
    db: AsyncSession,
    execution_id: str,
) -> GraphExecution | None:
    execution = await get_graph_execution(db, execution_id)
    if execution is None:
        return None
    execution.status = "paused"
    await db.flush()
    await db.refresh(execution)

    _broadcast_execution_event(
        execution_id,
        "graph:status",
        {
            "execution_id": execution_id,
            "status": "paused",
        },
    )

    return execution


async def _execute_graph_async(
    db_factory,
    execution_id: str,
    workflow_id: str,
    user_id: int,
    input_data: dict | None = None,
) -> None:
    """Background task: run GraphInterpreter and update execution status."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            workflow = await get_graph_workflow(db, workflow_id)
            if workflow is None:
                await fail_execution(db, execution_id, "Workflow not found")
                await db.commit()
                return

            execution = await get_graph_execution(db, execution_id)
            if execution is None:
                return

            await update_execution_status(db, execution_id, "running")
            await db.commit()

            from app.services.graph_executor import GraphInterpreter

            interpreter = GraphInterpreter(db, workflow, execution)
            start_node_id = (execution.input_data or {}).get("start_node_id")
            result = await interpreter.execute(start_node_id=start_node_id)

            await complete_execution(db, execution_id, result)
            await db.commit()
        except Exception as e:
            logger.error("Graph execution failed: %s", e, exc_info=True)
            await fail_execution(db, execution_id, str(e))
            await db.commit()
