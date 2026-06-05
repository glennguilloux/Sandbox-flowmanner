"""Mission decomposition and DAG execution API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.decomposition import (
    DAGNode,
    DAGResponse,
    DecomposeRequest,
    ExecuteDAGResponse,
)
from app.services.decomposition_service import (
    decompose_mission,
    execute_dag,
)
from app.services.mission_service import get_mission, get_mission_tasks

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/missions/decomposition", tags=["mission-decomposition"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.post("/{mission_id}/decompose")
async def decompose_endpoint(
    mission_id: str,
    payload: DecomposeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Decompose a mission into tasks with dependency edges."""
    mission = await get_mission(db, mission_id)
    if mission is None or mission.user_id != user.id:
        raise _not_found()

    tasks_data = None
    if payload.tasks:
        tasks_data = [t.model_dump() for t in payload.tasks]

    result = await decompose_mission(
        db, mission_id, mode=payload.mode, tasks=tasks_data
    )

    if result["errors"]:
        raise _bad_request(result["errors"])

    return result


@router.post("/{mission_id}/execute-dag", response_model=ExecuteDAGResponse)
async def execute_dag_endpoint(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Execute mission tasks in dependency order."""
    mission = await get_mission(db, mission_id)
    if mission is None or mission.user_id != user.id:
        raise _not_found()

    result = await execute_dag(db, mission_id)

    if result["errors"] and result["completed"] == 0 and result["failed"] == 0:
        raise _bad_request(result["errors"])

    return ExecuteDAGResponse(
        completed=result["completed"],
        failed=result["failed"],
        skipped=result["skipped"],
        errors=result["errors"],
    )


@router.get("/{mission_id}/dag", response_model=DAGResponse)
async def get_dag_endpoint(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return DAG structure for visualization."""
    mission = await get_mission(db, mission_id)
    if mission is None or mission.user_id != user.id:
        raise _not_found()

    tasks = await get_mission_tasks(db, mission_id)

    nodes = []
    edges = []
    task_ids = {str(t.id) for t in tasks}

    for task in tasks:
        deps = task.dependencies or {}
        dep_list = [d for d in deps.get("depends_on", []) if d in task_ids]

        nodes.append(DAGNode(
            id=str(task.id),
            title=task.title,
            status=task.status,
            dependencies=dep_list,
        ))

        for dep_id in dep_list:
            edges.append({"from": dep_id, "to": str(task.id)})

    return DAGResponse(nodes=nodes, edges=edges)
