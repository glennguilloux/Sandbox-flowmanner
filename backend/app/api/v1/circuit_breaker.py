"""Circuit Breaker API — Phase 6.4.

Endpoints:
- GET  /missions/{id}/circuit-breaker  — Get breaker state for a mission
- POST /missions/{id}/circuit-breaker/reset  — Manual reset
- PATCH /missions/{id}/circuit-breaker  — Update limits
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.database import get_db
from app.models.circuit_breaker_models import CircuitBreakerState
from app.services.circuit_breaker_service import CircuitBreakerService
from app.services.mission_service import require_mission_access

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/missions", tags=["circuit-breaker"])


class CircuitBreakerUpdate(BaseModel):
    max_llm_calls: int | None = Field(None, ge=0)
    max_cost_usd: float | None = Field(None, ge=0)
    max_duration_seconds: int | None = Field(None, ge=0)
    max_tool_calls: int | None = Field(None, ge=0)
    destructive_actions_require_approval: bool | None = None
    destructive_actions: list[str] | None = None


@router.get("/{mission_id}/circuit-breaker")
async def get_circuit_breaker(
    mission_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the circuit breaker state for a mission."""
    await require_mission_access(db, mission_id, user.id)
    service = CircuitBreakerService(db)
    breaker = await service.get_breaker(mission_id)
    if breaker is None:
        return {
            "mission_id": mission_id,
            "state": "none",
            "message": "No circuit breaker configured for this mission",
        }
    return _breaker_to_dict(breaker)


@router.post("/{mission_id}/circuit-breaker/reset")
async def reset_circuit_breaker(
    mission_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manual reset of the circuit breaker to ARMED state."""
    await require_mission_access(db, mission_id, user.id)
    service = CircuitBreakerService(db)
    breaker = await service.get_breaker(mission_id)
    if breaker is None:
        raise HTTPException(status_code=404, detail="No circuit breaker for this mission")
    if breaker.state == CircuitBreakerState.ARMED.value:
        return {"message": "Breaker is already armed", **_breaker_to_dict(breaker)}

    await service.reset(breaker)
    return {"message": "Circuit breaker reset", **_breaker_to_dict(breaker)}


@router.patch("/{mission_id}/circuit-breaker")
async def update_circuit_breaker(
    mission_id: str,
    body: CircuitBreakerUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update circuit breaker limits. Only updates provided fields."""
    await require_mission_access(db, mission_id, user.id)
    service = CircuitBreakerService(db)

    breaker = await service.get_breaker(mission_id)
    if breaker is None:
        # Create one with defaults, then apply updates
        breaker = await service.get_or_create(mission_id=mission_id)

    if body.max_llm_calls is not None:
        breaker.max_llm_calls = body.max_llm_calls
    if body.max_cost_usd is not None:
        breaker.max_cost_usd = body.max_cost_usd
    if body.max_duration_seconds is not None:
        breaker.max_duration_seconds = body.max_duration_seconds
    if body.max_tool_calls is not None:
        breaker.max_tool_calls = body.max_tool_calls
    if body.destructive_actions_require_approval is not None:
        breaker.destructive_actions_require_approval = body.destructive_actions_require_approval
    if body.destructive_actions is not None:
        breaker.destructive_actions = body.destructive_actions  # type: ignore[assignment]

    await db.flush()
    return _breaker_to_dict(breaker)


def _breaker_to_dict(breaker) -> dict[str, Any]:
    return {
        "id": breaker.id,
        "mission_id": breaker.mission_id,
        "state": breaker.state,
        "max_llm_calls": breaker.max_llm_calls,
        "max_cost_usd": breaker.max_cost_usd,
        "max_duration_seconds": breaker.max_duration_seconds,
        "max_tool_calls": breaker.max_tool_calls,
        "destructive_actions_require_approval": breaker.destructive_actions_require_approval,
        "llm_calls_made": breaker.llm_calls_made,
        "tool_calls_made": breaker.tool_calls_made,
        "cost_accumulated_usd": round(breaker.cost_accumulated_usd, 6),
        "started_at": breaker.started_at.isoformat() if breaker.started_at else None,
        "trigger_reason": breaker.trigger_reason,
        "triggered_at": (breaker.triggered_at.isoformat() if breaker.triggered_at else None),
        "trigger_count": breaker.trigger_count,
        "destructive_actions": breaker.destructive_actions,
    }
