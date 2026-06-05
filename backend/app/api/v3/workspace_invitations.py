from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.v3.base import ok
from app.database import get_db
from app.models.workspace_models import WorkspaceInvitation, WorkspaceMember
from app.schemas.workspace_v3 import (
    AcceptInvitationRequest,
    InvitationCreatedResponse,
    InvitationResponse,
    InviteMemberRequest,
)
from app.services.auth_v3_service import generate_invite_token

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/workspaces", tags=["v3-workspace-invitations"])


async def _require_invites_enabled(db: AsyncSession) -> None:
    from sqlalchemy import text
    result = await db.execute(text("SELECT enabled_globally FROM feature_flags WHERE key = 'WORKSPACES_V3_INVITES'"))
    if not result.scalar():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")


@router.post("/{workspace_id}/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    workspace_id: str,
    payload: InviteMemberRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_invites_enabled(db)

    membership = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if not membership.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    existing = await db.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.email == payload.email,
            WorkspaceInvitation.status == "pending",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation already pending")

    invite_id = str(uuid.uuid4())
    token = generate_invite_token()
    expires_at = datetime.now(UTC) + timedelta(days=7)

    invitation = WorkspaceInvitation(
        id=invite_id,
        workspace_id=workspace_id,
        email=payload.email,
        role=payload.role,
        token=token,
        invited_by=user.id,
        status="pending",
        expires_at=expires_at,
        invitation_message=payload.message,
    )
    db.add(invitation)
    await db.flush()
    await db.refresh(invitation)

    return ok(
        InvitationCreatedResponse(
            id=invitation.id,
            workspace_id=invitation.workspace_id,
            email=invitation.email,
            role=invitation.role,
            status=invitation.status,
            message=invitation.invitation_message,
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
            token=token,
        ).model_dump(mode="json")
    )


@router.get("/{workspace_id}/invitations", status_code=status.HTTP_200_OK)
async def list_invitations(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_invites_enabled(db)

    result = await db.execute(
        select(WorkspaceInvitation).where(WorkspaceInvitation.workspace_id == workspace_id)
    )
    invitations = result.scalars().all()

    return ok([
        InvitationResponse(
            id=i.id,
            workspace_id=i.workspace_id,
            email=i.email,
            role=i.role,
            status=i.status,
            message=i.invitation_message,
            created_at=i.created_at,
            expires_at=i.expires_at,
        ).model_dump(mode="json")
        for i in invitations
    ])


@router.delete("/{workspace_id}/invitations/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    workspace_id: str,
    invite_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_invites_enabled(db)

    result = await db.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.id == invite_id,
            WorkspaceInvitation.workspace_id == workspace_id,
        )
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    invitation.status = "revoked"
    await db.flush()


@router.post("/{workspace_id}/invitations/{invite_id}/accept", status_code=status.HTTP_200_OK)
async def accept_invitation(
    workspace_id: str,
    invite_id: str,
    payload: AcceptInvitationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_invites_enabled(db)

    result = await db.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.id == invite_id,
            WorkspaceInvitation.workspace_id == workspace_id,
        )
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    if invitation.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation already processed")

    if invitation.expires_at < datetime.now(UTC):
        invitation.status = "expired"
        await db.flush()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation expired")

    if invitation.token != payload.token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    existing_member = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if existing_member.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already a member")

    member = WorkspaceMember(workspace_id=workspace_id, user_id=user.id, role=invitation.role)
    db.add(member)
    invitation.status = "accepted"
    invitation.accepted_at = datetime.now(UTC)
    await db.flush()

    return ok({"workspace_id": workspace_id, "role": invitation.role, "message": f"Welcome to workspace"})
