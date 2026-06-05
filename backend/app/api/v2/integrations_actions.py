"""Integrations Actions API — discover and execute pre-built integration actions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.api.v2.base import ok
from app.database import get_db
from app.services.action_registry import execute_action, get_available_actions

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/actions", tags=["v2-integrations-actions"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class ExecuteActionRequest(BaseModel):
    connection_id: str = Field(..., description="OAuth connection ID to use")
    action_name: str = Field(..., description="Action slug, e.g. 'send_message'")
    params: dict = Field(default_factory=dict, description="Action parameters")


class ExecuteActionResponse(BaseModel):
    success: bool
    response: dict | None = None
    error: str | None = None


class AvailableAction(BaseModel):
    provider: str
    name: str
    label: str
    description: str
    required_params: list[str]
    optional_params: list[str]
    connection_id: str
    provider_account_name: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/available")
async def list_available_actions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all integration actions available to the current user.

    Returns one entry per (connection × action) pair.  Only active
    OAuth connections are included.
    """
    actions = await get_available_actions(str(user.id), db)
    return ok([{
        "provider": a["provider"],
        "name": a["name"],
        "label": a["label"],
        "description": a["description"],
        "required_params": a["required_params"],
        "optional_params": a["optional_params"],
        "connection_id": a["connection_id"],
        "provider_account_name": a["provider_account_name"],
    } for a in actions])


@router.post("/execute")
async def execute_integration_action(
    req: ExecuteActionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute an integration action against a connected service.

    The action uses the stored OAuth token associated with
    ``connection_id``.  Only the owner of the connection may use it.
    """
    result = await execute_action(
        user_id=str(user.id),
        connection_id=req.connection_id,
        action_name=req.action_name,
        params=req.params,
        db=db,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST
            if "not found" not in str(result.get("error", "")).lower()
            else status.HTTP_404_NOT_FOUND,
            detail=result.get("error", "Action execution failed"),
        )

    return ok(result.get("response", {}))
