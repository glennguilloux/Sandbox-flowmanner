"""Resilience API — expose the withResilience helper over REST.

Endpoints (mounted under /api/v2/mission-templates):
- POST /{template_id}/resilience/preview
    Apply a gate to a built-in (or any) template and return the wrapped plan
    WITHOUT persisting. Use this from the canvas to show the user the
    escalation subgraph before they commit.
- POST /{template_id}/resilience/apply
    Apply a gate and persist a new user-owned template variant (is_builtin=False).
    This is the thin UI toggle's "Add resilience" commit action.

Both accept a JSON body with ``gate`` (pass_through | escalate |
log_and_continue), plus optional ``approver_role``, ``approval_timeout``,
``escalation_policy`` (escalate gate only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.api.v2.base import ok
from app.database import get_db
from app.services.substrate.resilience_service import ResilienceService

if TYPE_CHECKING:
    from app.models.user import User
    from app.services.substrate.resilience import ResilienceGate

router = APIRouter(prefix="/mission-templates", tags=["v2-resilience"])


async def _not_found(template_id: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"MissionTemplate {template_id} not found",
    )


async def _service(db=Depends(get_db)) -> ResilienceService:
    return ResilienceService(db)


@router.post("/{template_id}/resilience/preview")
async def preview_resilience(
    template_id: str,
    body: dict[str, Any],
    svc: ResilienceService = Depends(_service),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the wrapped plan without persisting a variant."""
    gate: ResilienceGate = body.get("gate", "escalate")
    if gate not in ("pass_through", "escalate", "log_and_continue"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="gate must be one of: pass_through, escalate, log_and_continue",
        )
    result = await svc.preview(
        template_id,
        gate=gate,
        approver_role=body.get("approver_role"),
        approval_timeout=int(body.get("approval_timeout", 2)),
        escalation_policy=body.get("escalation_policy", "escalate"),
    )
    if not result.get("found"):
        await _not_found(template_id)
    return ok(result)


@router.post("/{template_id}/resilience/apply")
async def apply_resilience(
    template_id: str,
    body: dict[str, Any],
    svc: ResilienceService = Depends(_service),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Apply a gate and persist a new user-owned variant."""
    gate: ResilienceGate = body.get("gate", "escalate")
    if gate not in ("pass_through", "escalate", "log_and_continue"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="gate must be one of: pass_through, escalate, log_and_continue",
        )
    result = await svc.apply_and_persist(
        template_id,
        user,
        gate=gate,
        approver_role=body.get("approver_role"),
        approval_timeout=int(body.get("approval_timeout", 2)),
        escalation_policy=body.get("escalation_policy", "escalate"),
    )
    if not result.get("found"):
        await _not_found(template_id)
    return ok(result)
