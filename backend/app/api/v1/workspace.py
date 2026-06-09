"""Workspace API — DB-backed workspace, team, and invitation management."""

import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.workspace_activity import record_workspace_activity
from app.database import get_db
from app.models.user import User
from app.models.workspace_models import (
    Team,
    TeamMember,
    Workspace,
    WorkspaceInvitation,
    WorkspaceMember,
)

logger = logging.getLogger(__name__)

# ── Schemas ──────────────────────────────────────────────────────────────────


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    owner_id: int
    plan: str = "free"
    member_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class WorkspaceCreate(BaseModel):
    name: str
    slug: str | None = None


class WorkspaceUpdate(BaseModel):
    name: str | None = None


class MemberResponse(BaseModel):
    id: int
    user_id: int
    workspace_id: str
    role: str = "member"
    user_email: str = ""
    user_name: str = ""
    joined_at: str = ""


class TeamResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str = ""
    member_count: int = 0
    created_at: str = ""


class TeamCreate(BaseModel):
    name: str
    description: str = ""


class TeamUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class InvitationResponse(BaseModel):
    id: str
    workspace_id: str
    email: str
    role: str = "member"
    status: str = "pending"
    invited_by: int | None = None
    inviter_name: str = ""
    expires_at: str = ""
    created_at: str = ""


class InvitationCreate(BaseModel):
    email: str
    role: str = "member"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "workspace"


def _ws_to_response(ws: Workspace, member_count: int = 0) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        owner_id=ws.owner_id,
        plan=ws.plan,
        member_count=member_count,
        created_at=ws.created_at.isoformat() if ws.created_at else "",
        updated_at=ws.updated_at.isoformat() if ws.updated_at else "",
    )


async def _verify_membership(
    db: AsyncSession, workspace_id: str, user_id: int
) -> WorkspaceMember:
    result = await db.execute(
        select(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.is_active == True,
            )
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    return member


# ── Workspace Router ─────────────────────────────────────────────────────────

workspace_router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@workspace_router.get("/my")
async def list_my_workspaces(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all workspaces the current user belongs to."""
    result = await db.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            and_(
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.is_active == True,
                Workspace.is_active == True,
            )
        )
        .order_by(Workspace.created_at)
    )
    workspaces = result.scalars().all()

    items = []
    for ws in workspaces:
        count_result = await db.execute(
            select(WorkspaceMember).where(
                and_(
                    WorkspaceMember.workspace_id == ws.id,
                    WorkspaceMember.is_active == True,
                )
            )
        )
        member_count = len(count_result.scalars().all())
        items.append(_ws_to_response(ws, member_count))

    return items


@workspace_router.post("", status_code=201)
async def create_workspace(
    payload: WorkspaceCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workspace and add the creator as owner."""
    slug = payload.slug or _slugify(payload.name)

    # Check slug uniqueness
    existing = await db.execute(select(Workspace).where(Workspace.slug == slug))
    if existing.scalar_one_or_none():
        slug = f"{slug}-{uuid4().hex[:6]}"

    ws_id = str(uuid4())
    ws = Workspace(
        id=ws_id,
        name=payload.name,
        slug=slug,
        owner_id=user.id,
    )
    db.add(ws)

    member = WorkspaceMember(
        workspace_id=ws_id,
        user_id=user.id,
        role="owner",
    )
    db.add(member)

    await db.commit()
    await db.refresh(ws)

    logger.info('Workspace created: %s (%s) by user %s', ws_id, payload.name, user.id)
    return _ws_to_response(ws, member_count=1)


@workspace_router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get workspace details."""
    await _verify_membership(db, workspace_id, user.id)

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    count_result = await db.execute(
        select(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == ws.id, WorkspaceMember.is_active == True
            )
        )
    )
    return _ws_to_response(ws, member_count=len(count_result.scalars().all()))


@workspace_router.patch("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update workspace name (owner only)."""
    member = await _verify_membership(db, workspace_id, user.id)
    if member.role != "owner":
        raise HTTPException(
            status_code=403, detail="Only the owner can update the workspace"
        )

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if payload.name is not None:
        ws.name = payload.name

    await db.commit()
    await db.refresh(ws)
    return _ws_to_response(ws)


@workspace_router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete workspace (owner only)."""
    member = await _verify_membership(db, workspace_id, user.id)
    if member.role != "owner":
        raise HTTPException(
            status_code=403, detail="Only the owner can delete the workspace"
        )

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    ws.is_active = False
    await db.commit()


# ── Workspace Settings Schemas ──────────────────────────────────────────────


class CircuitBreakerDefaults(BaseModel):
    max_llm_calls: int = 100
    max_cost_usd: float = 10.0
    max_duration_seconds: int = 3600
    max_tool_calls: int = 200
    destructive_actions_require_approval: bool = True


class ApprovalPolicy(BaseModel):
    require_approval_for_deployments: bool = False
    require_approval_for_destructive_actions: bool = True
    require_approval_above_cost_usd: float = 5.0
    auto_approve_low_risk: bool = True


class WorkspaceSettingsResponse(BaseModel):
    circuit_breaker_defaults: CircuitBreakerDefaults
    approval_policies: ApprovalPolicy


class WorkspaceSettingsUpdate(BaseModel):
    circuit_breaker_defaults: CircuitBreakerDefaults | None = None
    approval_policies: ApprovalPolicy | None = None


# ── Workspace Settings Endpoints ─────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "circuit_breaker_defaults": {
        "max_llm_calls": 100,
        "max_cost_usd": 10.0,
        "max_duration_seconds": 3600,
        "max_tool_calls": 200,
        "destructive_actions_require_approval": True,
    },
    "approval_policies": {
        "require_approval_for_deployments": False,
        "require_approval_for_destructive_actions": True,
        "require_approval_above_cost_usd": 5.0,
        "auto_approve_low_risk": True,
    },
}


@workspace_router.get("/{workspace_id}/settings")
async def get_workspace_settings(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get workspace settings including circuit breaker defaults and approval policies."""
    await _verify_membership(db, workspace_id, user.id)

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Merge stored settings with defaults (stored values take precedence)
    stored = ws.settings or {}
    cb_defaults = {
        **DEFAULT_SETTINGS["circuit_breaker_defaults"],
        **stored.get("circuit_breaker_defaults", {}),
    }
    approval = {
        **DEFAULT_SETTINGS["approval_policies"],
        **stored.get("approval_policies", {}),
    }

    return {
        "circuit_breaker_defaults": cb_defaults,
        "approval_policies": approval,
    }


@workspace_router.patch("/{workspace_id}/settings")
async def update_workspace_settings(
    workspace_id: str,
    payload: WorkspaceSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update workspace settings. Owner/admin only. Merges with existing settings."""
    member = await _verify_membership(db, workspace_id, user.id)
    if member.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Only owners and admins can update workspace settings",
        )

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Merge with existing settings
    current = ws.settings or {}
    updated = dict(current)

    if payload.circuit_breaker_defaults is not None:
        updated["circuit_breaker_defaults"] = (
            payload.circuit_breaker_defaults.model_dump()
        )
    if payload.approval_policies is not None:
        updated["approval_policies"] = payload.approval_policies.model_dump()

    ws.settings = updated
    await db.commit()
    await db.refresh(ws)

    # Merge with defaults for response
    cb_defaults = {
        **DEFAULT_SETTINGS["circuit_breaker_defaults"],
        **updated.get("circuit_breaker_defaults", {}),
    }
    approval = {
        **DEFAULT_SETTINGS["approval_policies"],
        **updated.get("approval_policies", {}),
    }

    logger.info('Workspace %s settings updated by user %s', workspace_id, user.id)
    return {
        "circuit_breaker_defaults": cb_defaults,
        "approval_policies": approval,
    }


@workspace_router.post("/{workspace_id}/switch")
async def switch_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Switch to a workspace (verifies membership, returns workspace)."""
    await _verify_membership(db, workspace_id, user.id)

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return _ws_to_response(ws)


@workspace_router.get("/{workspace_id}/members")
async def list_members(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List workspace members."""
    await _verify_membership(db, workspace_id, user.id)

    result = await db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(
            and_(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.is_active == True,
            )
        )
        .order_by(WorkspaceMember.joined_at)
    )
    rows = result.all()

    return [
        MemberResponse(
            id=m.id,
            user_id=m.user_id,
            workspace_id=m.workspace_id,
            role=m.role,
            user_email=u.email,
            user_name=u.full_name or u.username or u.email,
            joined_at=m.joined_at.isoformat() if m.joined_at else "",
        )
        for m, u in rows
    ]


# ── Team Router ─────────────────────────────────────────────────────────────

team_router = APIRouter(prefix="/teams", tags=["teams"])


def _team_to_response(team: Team, member_count: int = 0) -> TeamResponse:
    return TeamResponse(
        id=team.id,
        workspace_id=team.workspace_id,
        name=team.name,
        description=team.description,
        member_count=member_count,
        created_at=team.created_at.isoformat() if team.created_at else "",
    )


@team_router.get("/{workspace_id}")
async def list_teams(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_membership(db, workspace_id, user.id)

    result = await db.execute(
        select(Team)
        .where(and_(Team.workspace_id == workspace_id, Team.is_active == True))
        .order_by(Team.created_at)
    )
    teams = result.scalars().all()

    items = []
    for t in teams:
        count_result = await db.execute(
            select(TeamMember).where(TeamMember.team_id == t.id)
        )
        member_count = len(count_result.scalars().all())
        items.append(_team_to_response(t, member_count))

    return items


@team_router.post("/{workspace_id}", status_code=201)
async def create_team(
    workspace_id: str,
    payload: TeamCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    member = await _verify_membership(db, workspace_id, user.id)
    if member.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403, detail="Only owners and admins can create teams"
        )

    team = Team(
        id=str(uuid4()),
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(team)

    # Add creator as team admin
    team_member = TeamMember(team_id=team.id, user_id=user.id, role="admin")
    db.add(team_member)

    await db.commit()
    await db.refresh(team)

    logger.info('Team created: %s (%s) in workspace %s', team.id, payload.name, workspace_id)
    return _team_to_response(team, member_count=1)


@team_router.get("/{workspace_id}/{team_id}")
async def get_team(
    workspace_id: str,
    team_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_membership(db, workspace_id, user.id)

    result = await db.execute(
        select(Team).where(
            and_(
                Team.id == team_id,
                Team.workspace_id == workspace_id,
                Team.is_active == True,
            )
        )
    )
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    count_result = await db.execute(
        select(TeamMember).where(TeamMember.team_id == team.id)
    )
    return _team_to_response(team, member_count=len(count_result.scalars().all()))


@team_router.patch("/{workspace_id}/{team_id}")
async def update_team(
    workspace_id: str,
    team_id: str,
    payload: TeamUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_membership(db, workspace_id, user.id)

    result = await db.execute(
        select(Team).where(
            and_(
                Team.id == team_id,
                Team.workspace_id == workspace_id,
                Team.is_active == True,
            )
        )
    )
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if payload.name is not None:
        team.name = payload.name
    if payload.description is not None:
        team.description = payload.description

    await db.commit()
    await db.refresh(team)
    return _team_to_response(team)


@team_router.delete("/{workspace_id}/{team_id}", status_code=204)
async def delete_team(
    workspace_id: str,
    team_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    member = await _verify_membership(db, workspace_id, user.id)
    if member.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403, detail="Only owners and admins can delete teams"
        )

    result = await db.execute(
        select(Team).where(
            and_(
                Team.id == team_id,
                Team.workspace_id == workspace_id,
                Team.is_active == True,
            )
        )
    )
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    team.is_active = False
    await db.commit()


@team_router.get("/{workspace_id}/{team_id}/members")
async def list_team_members(
    workspace_id: str,
    team_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_membership(db, workspace_id, user.id)

    result = await db.execute(
        select(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id)
        .order_by(TeamMember.joined_at)
    )
    rows = result.all()

    return [
        {
            "id": m.id,
            "user_id": m.user_id,
            "team_id": m.team_id,
            "role": m.role,
            "user_email": u.email,
            "user_name": u.full_name or u.username or u.email,
            "joined_at": m.joined_at.isoformat() if m.joined_at else "",
        }
        for m, u in rows
    ]


@team_router.post("/{workspace_id}/{team_id}/members", status_code=201)
async def add_team_member(
    workspace_id: str,
    team_id: str,
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_membership(db, workspace_id, user.id)

    result = await db.execute(
        select(Team).where(
            and_(
                Team.id == team_id,
                Team.workspace_id == workspace_id,
                Team.is_active == True,
            )
        )
    )
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    target_user_id = payload.get("user_id")
    if not target_user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    # Verify target is a workspace member
    ws_member = await db.execute(
        select(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == target_user_id,
                WorkspaceMember.is_active == True,
            )
        )
    )
    if not ws_member.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is not a workspace member")

    existing = await db.execute(
        select(TeamMember).where(
            and_(TeamMember.team_id == team_id, TeamMember.user_id == target_user_id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a team member")

    team_member = TeamMember(
        team_id=team_id,
        user_id=target_user_id,
        role=payload.get("role", "member"),
    )
    db.add(team_member)
    await db.commit()

    return {"message": "Member added"}


@team_router.delete("/{workspace_id}/{team_id}/members/{user_id}", status_code=204)
async def remove_team_member(
    workspace_id: str,
    team_id: str,
    user_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_membership(db, workspace_id, user.id)

    result = await db.execute(
        select(TeamMember).where(
            and_(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        )
    )
    team_member = result.scalar_one_or_none()
    if not team_member:
        raise HTTPException(status_code=404, detail="Team member not found")

    await db.delete(team_member)
    await db.commit()


# ── Invitation Router ───────────────────────────────────────────────────────

invitation_router = APIRouter(prefix="/invitations", tags=["invitations"])

INVITATION_EXPIRY_DAYS = 7


def _invitation_to_response(
    inv: WorkspaceInvitation, inviter_name: str = ""
) -> InvitationResponse:
    return InvitationResponse(
        id=inv.id,
        workspace_id=inv.workspace_id,
        email=inv.email,
        role=inv.role,
        status=inv.status,
        invited_by=inv.invited_by,
        inviter_name=inviter_name,
        expires_at=inv.expires_at.isoformat() if inv.expires_at else "",
        created_at=inv.created_at.isoformat() if inv.created_at else "",
    )


@invitation_router.get("/workspace/{workspace_id}")
async def list_invitations(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_membership(db, workspace_id, user.id)

    result = await db.execute(
        select(WorkspaceInvitation, User)
        .join(User, User.id == WorkspaceInvitation.invited_by, isouter=True)
        .where(
            and_(
                WorkspaceInvitation.workspace_id == workspace_id,
                WorkspaceInvitation.status == "pending",
            )
        )
        .order_by(WorkspaceInvitation.created_at)
    )
    rows = result.all()

    return [
        _invitation_to_response(
            inv, inviter.full_name or inviter.email if inviter else ""
        )
        for inv, inviter in rows
    ]


@invitation_router.get("/my")
async def my_invitations(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(WorkspaceInvitation, Workspace, User)
        .join(Workspace, Workspace.id == WorkspaceInvitation.workspace_id)
        .join(User, User.id == WorkspaceInvitation.invited_by, isouter=True)
        .where(
            and_(
                WorkspaceInvitation.email == user.email,
                WorkspaceInvitation.status == "pending",
                WorkspaceInvitation.expires_at > datetime.now(UTC),
            )
        )
        .order_by(WorkspaceInvitation.created_at)
    )
    rows = result.all()

    return [
        {
            **_invitation_to_response(
                inv, inviter.full_name or inviter.email if inviter else ""
            ).model_dump(),
            "workspace_name": ws.name,
        }
        for inv, ws, inviter in rows
    ]


@invitation_router.get("/{invitation_id}")
async def get_invitation(
    invitation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkspaceInvitation, User)
        .join(User, User.id == WorkspaceInvitation.invited_by, isouter=True)
        .where(WorkspaceInvitation.id == invitation_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Invitation not found")

    inv, inviter = row
    return _invitation_to_response(
        inv, inviter.full_name or inviter.email if inviter else ""
    )


@invitation_router.get("/token/{token}/preview")
async def preview_invitation(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WorkspaceInvitation, Workspace)
        .join(Workspace, Workspace.id == WorkspaceInvitation.workspace_id)
        .where(
            and_(
                WorkspaceInvitation.token == token,
                WorkspaceInvitation.status == "pending",
                WorkspaceInvitation.expires_at > datetime.now(UTC),
            )
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Invitation not found or expired")

    inv, ws = row
    return {
        "id": inv.id,
        "workspace_name": ws.name,
        "email": inv.email,
        "role": inv.role,
        "expires_at": inv.expires_at.isoformat(),
    }


@invitation_router.post("/token/{token}/accept")
async def accept_invitation(
    token: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkspaceInvitation).where(
            and_(
                WorkspaceInvitation.token == token,
                WorkspaceInvitation.status == "pending",
                WorkspaceInvitation.expires_at > datetime.now(UTC),
            )
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found or expired")

    if inv.email.lower() != user.email.lower():
        raise HTTPException(
            status_code=403, detail="This invitation is for a different email address"
        )

    # Check if already a member
    existing = await db.execute(
        select(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == inv.workspace_id,
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.is_active == True,
            )
        )
    )
    if existing.scalar_one_or_none():
        inv.status = "accepted"
        inv.accepted_at = datetime.now(UTC)
        await db.commit()
        return {"message": "Already a member", "workspace_id": inv.workspace_id}

    # Add as workspace member
    member = WorkspaceMember(
        workspace_id=inv.workspace_id,
        user_id=user.id,
        role=inv.role,
    )
    db.add(member)

    # Record role_changed activity event (fire-and-forget)
    await record_workspace_activity(
        db,
        workspace_id=inv.workspace_id,
        user_id=str(user.id),
        event_type="role_changed",
        actor_name=user.email or str(user.id),
        description=f"Joined workspace as {inv.role}",
    )

    inv.status = "accepted"
    inv.accepted_at = datetime.now(UTC)

    await db.commit()

    logger.info('Invitation accepted: %s — user %s joined workspace %s', inv.id, user.id, inv.workspace_id)
    return {"message": "Invitation accepted", "workspace_id": inv.workspace_id}


@invitation_router.post("/token/{token}/decline")
async def decline_invitation(
    token: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkspaceInvitation).where(
            and_(
                WorkspaceInvitation.token == token,
                WorkspaceInvitation.status == "pending",
            )
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")

    inv.status = "declined"
    await db.commit()

    return {"message": "Invitation declined"}


@invitation_router.delete("/{invitation_id}", status_code=204)
async def cancel_invitation(
    invitation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkspaceInvitation).where(WorkspaceInvitation.id == invitation_id)
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")

    # Only workspace owner/admin or the inviter can cancel
    member = await _verify_membership(db, inv.workspace_id, user.id)
    if member.role not in ("owner", "admin") and inv.invited_by != user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to cancel this invitation"
        )

    await db.delete(inv)
    await db.commit()


@invitation_router.post("/{invitation_id}/resend")
async def resend_invitation(
    invitation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkspaceInvitation).where(
            and_(
                WorkspaceInvitation.id == invitation_id,
                WorkspaceInvitation.status == "pending",
            )
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")

    # Extend expiry
    inv.expires_at = datetime.now(UTC) + timedelta(days=INVITATION_EXPIRY_DAYS)
    inv.token = uuid4().hex
    await db.commit()

    return {"message": "Invitation resent", "token": inv.token}


@invitation_router.post("/link")
async def create_invite_link(
    workspace_id: str,
    payload: InvitationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    member = await _verify_membership(db, workspace_id, user.id)
    if member.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403, detail="Only owners and admins can create invitations"
        )

    # Check if already invited
    existing = await db.execute(
        select(WorkspaceInvitation).where(
            and_(
                WorkspaceInvitation.workspace_id == workspace_id,
                WorkspaceInvitation.email == payload.email.lower(),
                WorkspaceInvitation.status == "pending",
                WorkspaceInvitation.expires_at > datetime.now(UTC),
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="An active invitation already exists for this email"
        )

    # Check if already a member
    ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = ws_result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check if user with this email is already a member
    user_result = await db.execute(
        select(User).where(User.email == payload.email.lower())
    )
    target_user = user_result.scalar_one_or_none()
    if target_user:
        member_check = await db.execute(
            select(WorkspaceMember).where(
                and_(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == target_user.id,
                    WorkspaceMember.is_active == True,
                )
            )
        )
        if member_check.scalar_one_or_none():
            raise HTTPException(
                status_code=409, detail="User is already a workspace member"
            )

    token = uuid4().hex
    inv = WorkspaceInvitation(
        id=str(uuid4()),
        workspace_id=workspace_id,
        email=payload.email.lower(),
        role=payload.role,
        token=token,
        invited_by=user.id,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=INVITATION_EXPIRY_DAYS),
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)

    logger.info('Invitation created: %s for %s to workspace %s', inv.id, payload.email, workspace_id)
    return {"id": inv.id, "token": token, "url": f"/invite/{token}"}
