"""V1 Missions endpoints — thin wrappers using CQRS handler DI."""

from __future__ import annotations

import uuid  # FastAPI/Pydantic v2 needs uuid at runtime for path param resolution
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, Response, status

from app.api._mission_cqrs.deps import get_mission_commands, get_mission_queries
from app.api.deps import get_current_user, get_workspace_id
from app.schemas.mission import (
    MissionAnalyticsResponse,
    MissionCreate,
    MissionExecuteRequest,
    MissionExecutionStatus,
    MissionImprovementCreate,
    MissionImprovementResponse,
    MissionLogCreate,
    MissionLogResponse,
    MissionResponse,
    MissionTaskCreate,
    MissionTaskResponse,
    MissionTaskUpdate,
    MissionUpdate,
    SelectPlanCandidateRequest,
)

if TYPE_CHECKING:
    from app.api._mission_cqrs.commands import MissionCommandHandlers
    from app.api._mission_cqrs.queries import MissionQueryHandlers
    from app.models.user import User


def _add_deprecation_headers(response: Response):
    """Phase 5.5: Inject deprecation headers on every v1 mission response."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-09-01"
    response.headers["Link"] = '</api/v2/blueprints>; rel="successor-version"'


router = APIRouter(
    prefix="/missions",
    tags=["missions"],
    dependencies=[Depends(_add_deprecation_headers)],
)


# ── List / Create (CQRS DI) ───────────────────────────────────────────────────


@router.get("")
@router.get("/")
async def list_items(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    r = await q.list_missions(user.id, page, per_page, workspace_id=workspace_id)
    return {
        "items": r.items,
        "total": r.total,
        "page": r.page,
        "per_page": r.per_page,
        "pages": r.pages,
    }


@router.post("/", response_model=MissionResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: MissionCreate,
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return await c.create_mission(user, payload, workspace_id=workspace_id)


# ── Active (CQRS DI) ──────────────────────────────────────────────────────────


@router.get("/active", response_model=list[MissionResponse])
async def list_active_missions(
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    """Active missions with progress/ETA (pro required)."""
    is_pro = getattr(user, "is_pro", False) or getattr(user, "role", None) == "pro"
    result = await q.active_missions(user.id, getattr(user, "role", ""), is_pro, workspace_id=workspace_id)
    return result.missions


# ── CRUD (CQRS DI) ────────────────────────────────────────────────────────────


@router.get("/{mission_id}/", response_model=MissionResponse)
@router.get("/{mission_id}", response_model=MissionResponse)
async def get_item(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return await q.get_mission(user.id, mission_id)


@router.patch("/{mission_id}", response_model=MissionResponse)
async def patch_item(
    mission_id: uuid.UUID,
    payload: MissionUpdate,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return await c.update_mission(user, mission_id, payload)


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    await c.delete_mission(user, mission_id)


# ── Tasks (CQRS DI) ───────────────────────────────────────────────────────────


@router.get("/{mission_id}/tasks/", response_model=list[MissionTaskResponse])
@router.get("/{mission_id}/tasks", response_model=list[MissionTaskResponse])
async def list_tasks(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return await q.list_tasks(user.id, mission_id)


@router.post(
    "/{mission_id}/tasks",
    response_model=MissionTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    mission_id: uuid.UUID,
    payload: MissionTaskCreate,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return await c.create_task(user, mission_id, payload)


@router.patch("/{mission_id}/tasks/{task_id}", response_model=MissionTaskResponse)
async def update_task(
    mission_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: MissionTaskUpdate,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return await c.update_task(user, mission_id, task_id, payload)


# ── Logs (CQRS DI) ────────────────────────────────────────────────────────────


@router.get("/{mission_id}/logs/", response_model=list[MissionLogResponse])
@router.get("/{mission_id}/logs", response_model=list[MissionLogResponse])
async def list_logs(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return await q.list_logs(user.id, mission_id)


@router.post(
    "/{mission_id}/logs",
    response_model=MissionLogResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_log(
    mission_id: uuid.UUID,
    payload: MissionLogCreate,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return await c.create_log(user, mission_id, payload)


# ── Planning (CQRS DI) ────────────────────────────────────────────────────────


@router.post("/{mission_id}/plan", response_model=MissionExecutionStatus)
async def plan_mission(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return await c.plan_mission(user, mission_id)


# ── Execution (CQRS DI) ───────────────────────────────────────────────────────


@router.post("/{mission_id}/execute", response_model=MissionExecutionStatus)
async def execute_mission(
    mission_id: uuid.UUID,
    payload: MissionExecuteRequest | None = None,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return await c.execute_mission(user, mission_id, payload)


@router.post("/{mission_id}/abort", response_model=MissionExecutionStatus)
async def abort_mission(
    mission_id: uuid.UUID,
    reason: str = "user_requested",
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return await c.abort_mission(user, mission_id, reason)


@router.post("/{mission_id}/execute-async")
async def execute_mission_async(
    mission_id: uuid.UUID,
    payload: MissionExecuteRequest | None = None,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return await c.execute_async(user, mission_id, payload)


@router.post("/{mission_id}/select-plan")
async def select_plan_candidate(
    mission_id: uuid.UUID,
    payload: SelectPlanCandidateRequest,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    """Pre-select a non-default plan candidate. v1 mirror of v2 route."""
    tasks = await c.select_plan_candidate(user, mission_id, payload)
    return [t.model_dump() for t in tasks]


# ── Status / Streaming ────────────────────────────────────────────────────────


@router.get("/{mission_id}/status/", response_model=MissionExecutionStatus)
@router.get("/{mission_id}/status", response_model=MissionExecutionStatus)
async def get_mission_status(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return await q.get_status(user.id, mission_id)


@router.get("/{mission_id}/stream/")
@router.get("/{mission_id}/stream")
async def stream_mission_status(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    """SSE stream — CQRS handler polls mission status until terminal."""
    mission = await q.get_mission(user.id, mission_id)
    return q.stream_status(user.id, mission_id, mission)


# ── Improvements (CQRS DI) ────────────────────────────────────────────────────


@router.get("/{mission_id}/improvements/", response_model=list[MissionImprovementResponse])
@router.get("/{mission_id}/improvements", response_model=list[MissionImprovementResponse])
async def list_improvements(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return await q.list_improvements(user.id, mission_id)


@router.post(
    "/{mission_id}/improvements",
    response_model=MissionImprovementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_improvement(
    mission_id: uuid.UUID,
    payload: MissionImprovementCreate,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return await c.create_improvement(user, mission_id, payload)


@router.post("/{mission_id}/improvements/{improvement_id}/apply")
async def apply_improvement(
    mission_id: uuid.UUID,
    improvement_id: uuid.UUID,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    return await c.apply_improvement(user, mission_id, improvement_id)


# ── Event History & State (Phase 3.2 — CQRS DI) ─────────────────────────────


@router.get("/{mission_id}/events")
async def get_mission_events(
    mission_id: uuid.UUID,
    from_sequence: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    """Retrieve substrate event history for a mission.

    Returns the append-only event log from the substrate_events table.
    Events are ordered by sequence ascending.
    """
    events = await q.get_events(user.id, mission_id, from_sequence=from_sequence, limit=limit)
    return {"mission_id": str(mission_id), "events": events, "count": len(events)}


@router.get("/{mission_id}/state")
async def get_mission_substrate_state(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    """Reconstruct mission state from the substrate event log.

    Uses the ReplayEngine to replay all events and build the current
    state.  Useful for debugging, time-travel inspection, and crash
    recovery verification.
    """
    return await q.get_substrate_state(user.id, mission_id)


# ── Analytics (CQRS DI) ───────────────────────────────────────────────────────


@router.get("/{mission_id}/analytics/")
@router.get("/{mission_id}/analytics")
async def get_mission_analytics_endpoint(
    mission_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return await q.mission_analytics(user.id, mission_id, days)


@router.get("/analytics", response_model=MissionAnalyticsResponse)
async def get_global_analytics(
    user: User = Depends(get_current_user),
    q: MissionQueryHandlers = Depends(get_mission_queries),
):
    return await q.global_analytics(user.id)


# ── Runtime imports for OpenAPI annotation resolution ───────────────────────
# `mission.py` uses `from __future__ import annotations`; handler params like
# `q: MissionQueryHandlers`, `c: MissionCommandHandlers`, `user: User` are stored
# as strings. FastAPI resolves them against this module's runtime globals at
# OpenAPI-gen time, but they are only imported under `TYPE_CHECKING` above (not
# present at runtime), so get_typed_signature raises and the resilient OpenAPI
# wrapper SKIPS those routes. These runtime imports fix spec generation
# (behavior-preserving; no circular import — verified).
from app.api._mission_cqrs.commands import MissionCommandHandlers
from app.api._mission_cqrs.queries import MissionQueryHandlers
from app.models.user import User
