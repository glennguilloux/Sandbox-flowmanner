from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_current_user, get_workspace_id
from app.database import get_db
from app.schemas.graph import (
    GraphExecutionCreate,
    GraphExecutionDetailResponse,
    GraphExecutionResponse,
    GraphStateResponse,
    GraphWorkflowCreate,
    GraphWorkflowResponse,
    GraphWorkflowUpdate,
)
from app.services.graph_service import (
    create_graph_workflow,
    execute_graph_workflow,
    get_graph_execution,
    get_graph_states,
    list_graph_executions,
    list_graph_workflows,
    require_graph_access,
    resume_graph_execution,
)
from app.services.mission_errors import GraphNotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


def _add_deprecation_headers(response: Response):
    """Phase 5.5: Inject deprecation headers on every v1 graph response."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-09-01"
    response.headers["Link"] = '</api/v2/blueprints>; rel="successor-version"'


router = APIRouter(prefix="/graphs", tags=["graphs"], dependencies=[Depends(_add_deprecation_headers)])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _graph_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph workflow not found")


@router.get("")
@router.get("/")
async def list_items(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    offset = (page - 1) * per_page
    items, total = await list_graph_workflows(db, user.id, offset=offset, limit=per_page, workspace_id=workspace_id)
    pages = (total + per_page - 1) // per_page
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: GraphWorkflowCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    return await create_graph_workflow(
        db,
        user.id,
        payload.name,
        payload.graph_definition,
        payload.description,
        workspace_id=workspace_id,
    )


@router.get("/{workflow_id}", response_model=GraphWorkflowResponse)
async def get_item(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await require_graph_access(db, workflow_id, user.id)
    except GraphNotFoundError:
        raise _graph_not_found()


@router.patch("/{workflow_id}", response_model=GraphWorkflowResponse)
async def patch_item(
    workflow_id: uuid.UUID,
    payload: GraphWorkflowUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        workflow = await require_graph_access(db, workflow_id, user.id)
    except GraphNotFoundError:
        raise _graph_not_found()
    if payload.name is not None:
        workflow.name = payload.name
    if payload.description is not None:
        workflow.description = payload.description
    if payload.graph_definition is not None:
        workflow.graph_definition = payload.graph_definition
    if payload.status is not None:
        workflow.status = payload.status
    await db.flush()
    await db.refresh(workflow)
    return workflow


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        workflow = await require_graph_access(db, workflow_id, user.id)
    except GraphNotFoundError:
        raise _graph_not_found()
    await db.delete(workflow)
    await db.flush()
    return None


# --- Graph Executions ---


@router.post(
    "/{workflow_id}/execute",
    response_model=GraphExecutionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_graph(
    workflow_id: uuid.UUID,
    payload: GraphExecutionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await require_graph_access(db, workflow_id, user.id)
    except GraphNotFoundError:
        raise _graph_not_found()
    return await execute_graph_workflow(db, workflow_id, user.id, payload.input_data)


@router.post("/{workflow_id}/resume/{execution_id}", response_model=GraphExecutionResponse)
async def resume_graph(
    workflow_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await require_graph_access(db, workflow_id, user.id)
    except GraphNotFoundError:
        raise _graph_not_found()
    result = await resume_graph_execution(db, execution_id, user.id)
    if result is None:
        raise _not_found()
    return result


@router.get("/{workflow_id}/executions")
async def list_executions(
    workflow_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await require_graph_access(db, workflow_id, user.id)
    except GraphNotFoundError:
        raise _graph_not_found()
    offset = (page - 1) * per_page
    items, total = await list_graph_executions(db, workflow_id, user.id, offset=offset, limit=per_page)
    pages = (total + per_page - 1) // per_page
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get(
    "/{workflow_id}/executions/{execution_id}",
    response_model=GraphExecutionDetailResponse,
)
async def get_execution(
    workflow_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await require_graph_access(db, workflow_id, user.id)
    except GraphNotFoundError:
        raise _graph_not_found()
    execution = await get_graph_execution(db, execution_id)
    if execution is None:
        raise _not_found()

    states = await get_graph_states(db, execution_id)
    node_states = [s.state_data for s in states]

    return GraphExecutionDetailResponse(
        id=execution.id,
        workflow_id=execution.workflow_id,
        status=execution.status,
        input_data=execution.input_data,
        output_data=execution.output_data,
        error_message=execution.error_message,
        started_at=execution.started_at,
        created_at=execution.created_at,
        completed_at=execution.completed_at,
        node_states=node_states,
    )


# --- Graph States ---


@router.get(
    "/{workflow_id}/executions/{execution_id}/states",
    response_model=list[GraphStateResponse],
)
async def list_states(
    workflow_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await require_graph_access(db, workflow_id, user.id)
    except GraphNotFoundError:
        raise _graph_not_found()
    return await get_graph_states(db, execution_id)


@router.get("/{workflow_id}/executions/{execution_id}/nodes")
async def list_execution_nodes(
    workflow_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await require_graph_access(db, workflow_id, user.id)
    except GraphNotFoundError:
        raise _graph_not_found()
    states = await get_graph_states(db, execution_id)
    nodes = [
        {
            "nodeId": (s.state_data or {}).get("node_id", ""),
            "nodeLabel": (s.state_data or {}).get("label", (s.state_data or {}).get("node_id", "")),
            "nodeType": (s.state_data or {}).get("type", "unknown"),
            "status": (s.state_data or {}).get("status", "pending"),
            "latencyMs": (s.state_data or {}).get("latency_ms", 0),
            "tokensIn": (s.state_data or {}).get("tokens_in", 0),
            "tokensOut": (s.state_data or {}).get("tokens_out", 0),
            "cost": float((s.state_data or {}).get("cost", 0)),
            "output": (s.state_data or {}).get("output"),
            "error": (s.state_data or {}).get("error"),
        }
        for s in states
        if "node_id" in (s.state_data or {})
    ]
    if not nodes:
        execution = await get_graph_execution(db, execution_id)
        if execution and isinstance(execution.output_data, dict) and "nodes" in execution.output_data:
            nodes = execution.output_data["nodes"]
    return nodes


# H6 — Execution comparison endpoint
@router.get("/compare/{execution_a_id}/{execution_b_id}")
async def compare_executions(
    execution_a_id: str,
    execution_b_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Compare two graph executions with node output diffs. Uses state_data JSONB."""
    from sqlalchemy import select

    from app.models.graph import GraphExecution, WorkflowState

    # Fetch both executions
    result_a = await db.execute(select(GraphExecution).where(GraphExecution.id == execution_a_id))
    exec_a = result_a.scalar_one_or_none()
    if not exec_a:
        raise HTTPException(404, "Execution A not found")

    result_b = await db.execute(select(GraphExecution).where(GraphExecution.id == execution_b_id))
    exec_b = result_b.scalar_one_or_none()
    if not exec_b:
        raise HTTPException(404, "Execution B not found")

    # Verify both belong to same workflow
    if exec_a.workflow_id != exec_b.workflow_id:
        raise HTTPException(400, "Executions must belong to the same workflow")

    # Verify access via parent workflow (single call since same workflow)
    try:
        await require_graph_access(db, exec_a.workflow_id, user.id)
    except GraphNotFoundError:
        raise _graph_not_found()

    async def _get_nodes(execution_id: str):
        result = await db.execute(
            select(WorkflowState).where(WorkflowState.execution_id == execution_id).order_by(WorkflowState.created_at)
        )
        states = []
        for ws in result.scalars().all():
            sd = ws.state_data or {}
            if "node_id" in sd:
                states.append(
                    {
                        "nodeId": sd.get("node_id", ""),
                        "nodeLabel": sd.get("label", sd.get("node_id", "")),
                        "nodeType": sd.get("type", "unknown"),
                        "status": sd.get("status", "pending"),
                        "latencyMs": sd.get("latency_ms", 0),
                        "tokensIn": sd.get("tokens_in", 0),
                        "tokensOut": sd.get("tokens_out", 0),
                        "cost": float(sd.get("cost", 0)),
                        "output": sd.get("output"),
                        "error": sd.get("error"),
                    }
                )
        return states

    nodes_a = await _get_nodes(execution_a_id)
    nodes_b = await _get_nodes(execution_b_id)

    # Fallback: if no node states, use execution output_data
    if not nodes_a and exec_a.output_data:
        od = exec_a.output_data
        if isinstance(od, dict) and "nodes" in od:
            nodes_a = od["nodes"]
    if not nodes_b and exec_b.output_data:
        od = exec_b.output_data
        if isinstance(od, dict) and "nodes" in od:
            nodes_b = od["nodes"]

    def _totals(nodes):
        tc = sum(float(n.get("cost", 0) or 0) for n in nodes)
        tt = sum(int(n.get("tokensIn", 0) or 0) + int(n.get("tokensOut", 0) or 0) for n in nodes)
        tl = sum(int(n.get("latencyMs", 0) or 0) for n in nodes)
        return tc, tt, tl

    c_a, tk_a, l_a = _totals(nodes_a)
    c_b, tk_b, l_b = _totals(nodes_b)

    return {
        "runA": {
            "runId": exec_a.id,
            "startedAt": exec_a.started_at.isoformat() if exec_a.started_at else None,
            "completedAt": (exec_a.completed_at.isoformat() if exec_a.completed_at else None),
            "totalCost": c_a,
            "totalTokens": tk_a,
            "totalLatencyMs": l_a,
            "nodes": nodes_a,
        },
        "runB": {
            "runId": exec_b.id,
            "startedAt": exec_b.started_at.isoformat() if exec_b.started_at else None,
            "completedAt": (exec_b.completed_at.isoformat() if exec_b.completed_at else None),
            "totalCost": c_b,
            "totalTokens": tk_b,
            "totalLatencyMs": l_b,
            "nodes": nodes_b,
        },
    }
