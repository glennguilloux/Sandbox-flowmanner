from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.graph import GraphExecution, GraphWorkflow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

# Attempt to import graph executor at module level
try:
    from app.services.graph_executor import GraphInterpreter

    _HAS_GRAPH_EXECUTOR = True
except ImportError:
    _HAS_GRAPH_EXECUTOR = False
    GraphInterpreter = None  # type: ignore

logger = logging.getLogger(__name__)


def _add_deprecation_headers(response: Response):
    """Phase 5.5: Inject deprecation headers on every v1 flow-compat response."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-09-01"
    response.headers["Link"] = '</api/v2/blueprints>; rel="successor-version"'


router = APIRouter(tags=["flow-compat"], dependencies=[Depends(_add_deprecation_headers)])


@router.get("/runs")
async def get_flow_runs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return paginated flow runs for the current user.

    .. deprecated:: Use ``GET /api/v2/blueprints`` instead.
    """
    offset = (page - 1) * limit
    count_result = await db.execute(
        select(func.count()).select_from(GraphExecution).where(GraphExecution.user_id == current_user.id)
    )
    total = count_result.scalar() or 0

    page_r = await db.execute(
        select(GraphExecution)
        .where(GraphExecution.user_id == current_user.id)
        .order_by(GraphExecution.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    runs = []
    for ex in page_r.scalars().all():
        runs.append(
            {
                "id": str(ex.id),
                "workflow_id": str(ex.workflow_id),
                "status": ex.status,
                "input_data": ex.input_data or {},
                "output_data": ex.output_data or {},
                "created_at": ex.created_at.isoformat() if ex.created_at else None,
            }
        )
    return {"runs": runs, "total": total, "page": page, "limit": limit}


@router.post("/run/stream")
async def stream_flow_run(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    goal = body.get("goal", "")
    run_id = str(uuid4())

    async def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'run_id': run_id})}\n\n"

        # Attempt real execution via graph executor
        try:
            if not _HAS_GRAPH_EXECUTOR:
                yield f"data: {json.dumps({'type': 'error', 'detail': 'Execution engine not available'})}\n\n"
                return

            # Find an active workflow for this user
            workflow_result = await db.execute(
                select(GraphWorkflow)
                .where(
                    GraphWorkflow.user_id == current_user.id,
                    GraphWorkflow.status == "active",
                )
                .limit(1)
            )
            workflow = workflow_result.scalars().first()

            if workflow is None:
                yield f"data: {json.dumps({'type': 'error', 'detail': 'No active workflow found for this user'})}\n\n"
                return

            execution = GraphExecution(
                id=uuid4(),
                workflow_id=workflow.id,
                user_id=current_user.id,
                status="running",
                input_data={"goal": goal},
            )
            db.add(execution)
            await db.commit()

            interpreter = GraphInterpreter(db, workflow, execution)
            result = await interpreter.execute()

            yield f"data: {json.dumps({'type': 'complete', 'full_response': str(result), 'tokens': 0})}\n\n"
        except ImportError:
            yield f"data: {json.dumps({'type': 'error', 'detail': 'Execution engine not available'})}\n\n"
        except Exception as e:
            logger.warning("Flow execution failed for run %s: %s", run_id, e)
            yield f"data: {json.dumps({'type': 'error', 'detail': f'Execution failed: {e!s}'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
