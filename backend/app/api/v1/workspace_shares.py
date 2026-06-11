"""Cross-workspace sharing API endpoints.

Allows workspace admins/owners to grant read or write access to specific
entities (missions, workflows, chat threads) to members of other workspaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_current_user, get_workspace_id
from app.database import get_db
from app.services.cross_workspace_service import (
    VALID_ENTITY_TYPES,
    VALID_PERMISSIONS,
    CrossWorkspaceError,
    ShareNotFoundError,
    grant_share,
    list_shares_for_workspace,
    revoke_share,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/workspace-shares", tags=["workspace-shares"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class ShareCreateRequest(BaseModel):
    target_workspace_id: str = Field(..., description="Workspace to grant access to")
    entity_type: str = Field(..., description="Entity type: mission, workflow, chat_thread")
    entity_id: str = Field(..., description="Entity ID to share")
    permission: str = Field("read", description="Permission level: read or write")


class ShareResponse(BaseModel):
    id: str
    source_workspace_id: str
    target_workspace_id: str
    entity_type: str
    entity_id: str
    permission: str
    granted_by: int | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=ShareResponse)
async def create_share(
    payload: ShareCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    """Grant cross-workspace access to a specific entity.

    The caller must be a member of the source workspace (the workspace that
    owns the entity). The entity_type and entity_id are validated against the
    source workspace's ownership.
    """
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Workspace-Id header required to identify the source workspace",
        )

    if payload.entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity_type. Must be one of: {', '.join(VALID_ENTITY_TYPES)}",
        )
    if payload.permission not in VALID_PERMISSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid permission. Must be one of: {', '.join(VALID_PERMISSIONS)}",
        )

    try:
        share = await grant_share(
            db,
            source_workspace_id=workspace_id,
            target_workspace_id=payload.target_workspace_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            permission=payload.permission,
            granted_by=user.id,
        )
        return share
    except CrossWorkspaceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share_endpoint(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Revoke (deactivate) a cross-workspace share grant."""
    try:
        await revoke_share(db, share_id, revoked_by=user.id)
    except ShareNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")


@router.get("/", response_model=list[ShareResponse])
async def list_shares(
    direction: str = "outgoing",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    """List cross-workspace shares for the current workspace.

    direction='outgoing': shares granted BY this workspace (default).
    direction='incoming': shares granted TO this workspace.
    """
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Workspace-Id header required",
        )
    if direction not in ("outgoing", "incoming"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="direction must be 'outgoing' or 'incoming'",
        )
    return await list_shares_for_workspace(db, workspace_id, direction=direction)
