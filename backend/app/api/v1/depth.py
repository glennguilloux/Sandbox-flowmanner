"""Depth policy API endpoints (Q2-Q3 Chunk 4).

Two routers are exposed:
- POST /depth/decide — compute a depth decision for given inputs (admin/testing)
- GET /missions/{mission_id}/depth-events — list depth_decided events for a mission

The events endpoint is on its own router (events_router) so its path is
/api/missions/{mission_id}/depth-events and NOT /api/depth/missions/...
(this was a routing bug fixed by the orchestrator on 2026-06-12).
"""

import logging
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.depth_models import DepthDecision, DepthLevel
from app.models.substrate_models import SubstrateEvent, SubstrateEventType
from app.services.depth_policy import DepthPolicy

logger = logging.getLogger(__name__)

# /depth/decide — admin/testing endpoint for the policy itself
router = APIRouter(prefix="/depth", tags=["depth"])

# /missions/{mission_id}/depth-events — mission-scoped replay endpoint.
# Kept on a separate router so its path resolves to /api/missions/...
# (NOT /api/depth/missions/...).  Q2-Q3 chunk 4 orchestrator fix.
events_router = APIRouter(tags=["depth-events"])

# ── Request / Response models ──────────────────────────────────────


class DepthDecideRequest(BaseModel):
    """Request body for the depth decision endpoint."""

    risk: Literal["low", "medium", "high"] = Field(..., description="Risk level: low, medium, or high")
    uncertainty: float = Field(..., ge=0.0, le=1.0, description="Uncertainty signal (0.0-1.0)")
    budget_remaining_usd: float = Field(..., ge=0, description="Remaining budget in USD")
    prior_failures: int = Field(default=0, ge=0, description="Number of prior failures")
    tool_requires_approval: bool = Field(default=False, description="Whether the tool requires HITL approval")
    retry_count: int = Field(default=0, ge=0, description="Number of retries attempted")
    policy_override: bool = Field(default=False, description="Bypass HITL for approval-requiring tools")


class DepthDecisionResponse(BaseModel):
    """Response body for a depth decision."""

    level: str
    reason: str
    escalate_to_hitl: bool
    hitl_reason: str | None
    policy_version: str
    estimated_reflection_iterations: int


class DepthEventResponse(BaseModel):
    """Response body for a depth audit event."""

    id: str
    sequence: int
    type: str
    payload: dict
    actor: str
    timestamp: str
    mission_id: str | None
    task_id: str | None


# ── Endpoints ──────────────────────────────────────────────────────


@router.post("/decide", response_model=DepthDecisionResponse)
async def decide_depth(request: DepthDecideRequest) -> DepthDecisionResponse:
    """Compute a depth decision for the given inputs.

    This is an admin/testing endpoint that exposes the depth policy
    directly.  In production, the policy is called by MissionExecutor.
    """
    policy = DepthPolicy()

    decision = policy.decide(
        risk=request.risk,  # type: ignore[arg-type]
        uncertainty=request.uncertainty,
        budget_remaining_usd=Decimal(str(request.budget_remaining_usd)),
        prior_failures=request.prior_failures,
        tool_requires_approval=request.tool_requires_approval,
        retry_count=request.retry_count,
        policy_override=request.policy_override,
    )

    return DepthDecisionResponse(
        level=decision.level.value,
        reason=decision.reason,
        escalate_to_hitl=decision.escalate_to_hitl,
        hitl_reason=decision.hitl_reason,
        policy_version=decision.policy_version,
        estimated_reflection_iterations=decision.estimated_reflection_iterations,
    )


@events_router.get("/missions/{mission_id}/depth-events", response_model=list[DepthEventResponse])
async def get_depth_events(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[DepthEventResponse]:
    """List all depth_decided substrate events for a mission.

    Used for replay audit — shows why shallow vs deep was chosen
    for each step in a mission.
    """
    stmt = (
        select(SubstrateEvent)
        .where(
            SubstrateEvent.mission_id == mission_id,
            SubstrateEvent.type == SubstrateEventType.DEPTH_DECIDED,
        )
        .order_by(SubstrateEvent.sequence)
    )
    result = await db.execute(stmt)
    events = list(result.scalars().all())

    return [
        DepthEventResponse(
            id=str(event.id),
            sequence=event.sequence,
            type=event.type,
            payload=event.payload or {},
            actor=event.actor,
            timestamp=event.timestamp.isoformat() if event.timestamp else "",
            mission_id=str(event.mission_id) if event.mission_id else None,
            task_id=str(event.task_id) if event.task_id else None,
        )
        for event in events
    ]
