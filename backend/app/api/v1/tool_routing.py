"""Tool Routing API — Q2-Q3 Chunk 3.

Provides:
- POST /tool-routing/route — score and select top-k tool candidates
- GET /missions/{mission_id}/tool-routing-events — audit trail of routing decisions
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.database import get_db
from app.models.tool_routing_models import ToolRouteResult
from app.services.tool_router import ToolRouter, get_tool_router

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tool-routing"])


# ── Request / Response models ─────────────────────────────────────


class RouteRequest(BaseModel):
    """Request body for POST /tool-routing/route."""

    task_text: str = Field(..., min_length=1, max_length=5000, description="Natural language task description")
    workspace_id: str = Field(..., description="Workspace UUID to scope results")
    user_id: int = Field(..., description="User ID for scoping")
    k: int | None = Field(default=None, ge=1, le=50, description="Override top-k (default: 8)")


class ToolRoutingEventResponse(BaseModel):
    """Single routing audit event."""

    id: str | None = None
    sequence: int | None = None
    type: str | None = None
    payload: dict[str, Any] | None = None
    actor: str | None = None
    timestamp: str | None = None


class MissionRoutingEventsResponse(BaseModel):
    """Response for GET /missions/{mission_id}/tool-routing-events."""

    events: list[ToolRoutingEventResponse]
    count: int


# ── Endpoints ──────────────────────────────────────────────────────


def _tool_router_dep() -> ToolRouter:
    """No-arg dependency wrapper around the get_tool_router singleton factory.

    FastAPI analyzes a dependency's signature to build request params. The
    underlying `get_tool_router(registry: ToolConverter | None = None, ...)`
    factory has defaulted params whose types are plain (non-Pydantic) classes,
    which FastAPI misreads as query params and rejects ("Invalid args for
    response field"), causing the OpenAPI wrapper to SKIP /api/tool-routing/route.
    A zero-parameter wrapper gives FastAPI nothing problematic to analyze while
    preserving identical runtime behavior (the singleton is still returned).
    """
    return get_tool_router()


@router.post("/tool-routing/route", response_model=ToolRouteResult)
async def route_tools(
    body: RouteRequest,
    current_user: Any = Depends(get_current_user),
    tool_router: ToolRouter = Depends(_tool_router_dep),
) -> ToolRouteResult:
    """Score and select top-k tool candidates for a task.

    Returns a bounded candidate set when confidence is high enough,
    or falls back to the full registry when confidence is low.
    """
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        workspace_uuid = UUID(body.workspace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace_id UUID")

    result = await tool_router.route(
        task_text=body.task_text,
        workspace_id=workspace_uuid,
        user_id=body.user_id,
        k=body.k,
    )
    return result


@router.get(
    "/missions/{mission_id}/tool-routing-events",
    response_model=MissionRoutingEventsResponse,
)
async def get_mission_routing_events(
    mission_id: str,
    db: Any = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> MissionRoutingEventsResponse:
    """List tool_route_decided events for a mission.

    Used for replay audit — shows which tools were considered and why.
    """
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    from app.models.substrate_models import SubstrateEventType
    from app.services.substrate.event_log import get_event_log

    event_log = get_event_log()

    try:
        events = await event_log.get_events(
            db,
            run_id=mission_id,
            event_type=SubstrateEventType.TOOL_ROUTE_DECIDED,
            limit=100,
        )
    except Exception as exc:
        logger.warning("Failed to fetch routing events for mission %s: %s", mission_id, exc)
        events = []

    event_responses = [
        ToolRoutingEventResponse(
            id=str(e.id),
            sequence=e.sequence,
            type=e.type,
            payload=e.payload,
            actor=e.actor,
            timestamp=e.timestamp.isoformat() if e.timestamp else None,
        )
        for e in events
    ]

    return MissionRoutingEventsResponse(
        events=event_responses,
        count=len(event_responses),
    )


# ── Runtime imports for OpenAPI annotation resolution ───────────────────────
# `tool_routing.py` uses `from __future__ import annotations`; the handler param
# `tool_router: ToolRouter` is stored as the string "ToolRouter". FastAPI
# resolves it against this module's runtime globals at OpenAPI-gen time, but
# `ToolRouter` is only imported under `TYPE_CHECKING` (not at runtime), so
# get_typed_signature raises and the resilient OpenAPI wrapper SKIPS the route.
# Importing at runtime fixes spec generation (behavior-preserving).
from app.services.tool_router import ToolRouter
