"""V2 Workspaces endpoints — workspace + team management, standardized envelope."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import get_current_user, require_tenant_admin
from app.api.v2.base import ok
from app.database import get_db
from app.models.user import User
from app.models.workspace_models import (
    Team,
    TeamMember,
    Workspace,
    WorkspaceMember,
    WorkspaceToolAllowlist,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["v2-workspaces"])


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    owner_id: int
    plan: str = "free"
    member_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    model_config = ConfigDict(from_attributes=True)


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
    created_at: str = ""


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


async def _get_user_workspaces(db: AsyncSession, user_id: int):
    result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.user_id == user_id))
    memberships = result.scalars().all()
    workspace_ids = [m.workspace_id for m in memberships]
    if not workspace_ids:
        return []
    result = await db.execute(select(Workspace).where(Workspace.id.in_(workspace_ids)))
    return result.scalars().all()


async def _check_workspace_access(db: AsyncSession, workspace_id: str, user_id: int):
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


@router.get("")
@router.get("/")
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspaces = await _get_user_workspaces(db, user.id)
    items = []
    for ws in workspaces:
        member_count_result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == ws.id))
        member_count = len(member_count_result.scalars().all())
        items.append(
            WorkspaceResponse(
                id=ws.id,
                name=ws.name,
                slug=ws.slug,
                owner_id=ws.owner_id,
                plan=ws.plan,
                member_count=member_count,
                created_at=str(ws.created_at) if ws.created_at else "",
                updated_at=str(ws.updated_at) if ws.updated_at else "",
            ).model_dump()
        )
    return ok(items)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ws_id = str(uuid4())
    slug = payload.slug or re.sub(r"[^a-z0-9]+", "-", payload.name.lower()).strip("-") or f"workspace-{ws_id[:8]}"

    existing = await db.execute(select(Workspace).where(Workspace.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workspace slug already taken")

    ws = Workspace(id=ws_id, name=payload.name, slug=slug, owner_id=user.id)
    db.add(ws)
    db.add(WorkspaceMember(workspace_id=ws_id, user_id=user.id, role="owner"))
    await db.flush()
    await db.refresh(ws)

    return ok(
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            owner_id=ws.owner_id,
            plan=ws.plan,
            member_count=1,
            created_at=str(ws.created_at) if ws.created_at else "",
        ).model_dump()
    )


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = await _check_workspace_access(db, workspace_id, user.id)
    if not membership:
        raise _not_found()

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise _not_found()

    member_count_result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
    member_count = len(member_count_result.scalars().all())

    return ok(
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            owner_id=ws.owner_id,
            plan=ws.plan,
            member_count=member_count,
            created_at=str(ws.created_at) if ws.created_at else "",
            updated_at=str(ws.updated_at) if ws.updated_at else "",
        ).model_dump()
    )


@router.patch("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = await _check_workspace_access(db, workspace_id, user.id)
    if not membership or membership.role not in ("owner", "admin"):
        raise _not_found()

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise _not_found()

    if payload.name is not None:
        ws.name = payload.name
    await db.flush()
    await db.refresh(ws)

    return ok(
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            owner_id=ws.owner_id,
            plan=ws.plan,
            created_at=str(ws.created_at) if ws.created_at else "",
            updated_at=str(ws.updated_at) if ws.updated_at else "",
        ).model_dump()
    )


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = await _check_workspace_access(db, workspace_id, user.id)
    if not membership or membership.role != "owner":
        raise _not_found()

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise _not_found()

    await db.delete(ws)


@router.get("/{workspace_id}/members")
async def list_members(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = await _check_workspace_access(db, workspace_id, user.id)
    if not membership:
        raise _not_found()

    result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
    members = result.scalars().all()

    items = []
    for m in members:
        user_result = await db.execute(select(User).where(User.id == m.user_id))
        u = user_result.scalar_one_or_none()
        items.append(
            MemberResponse(
                id=m.id,
                user_id=m.user_id,
                workspace_id=m.workspace_id,
                role=m.role,
                user_email=u.email if u else "",
                user_name=u.full_name or u.username if u else "",
                joined_at=str(m.joined_at) if m.joined_at else "",
            ).model_dump()
        )

    return ok(items)


@router.get("/{workspace_id}/teams")
async def list_teams(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = await _check_workspace_access(db, workspace_id, user.id)
    if not membership:
        raise _not_found()

    result = await db.execute(select(Team).where(Team.workspace_id == workspace_id))
    teams = result.scalars().all()

    items = []
    for t in teams:
        member_count_result = await db.execute(select(TeamMember).where(TeamMember.team_id == t.id))
        member_count = len(member_count_result.scalars().all())
        items.append(
            TeamResponse(
                id=t.id,
                workspace_id=t.workspace_id,
                name=t.name,
                description=t.description,
                member_count=member_count,
                created_at=str(t.created_at) if t.created_at else "",
            ).model_dump()
        )

    return ok(items)


# ── Phase 5: Workspace Tool Allowlist ──────────────────────────────


class ToolAllowlistResponse(BaseModel):
    tool_id: str
    name: str
    description: str
    category: str = "general"
    enabled: bool = True
    required_scopes: list[str] = []


class UpdateToolsRequest(BaseModel):
    tools: list[str]  # list of tool_id values to enable


class RequestToolAccessRequest(BaseModel):
    tool_name: str
    reason: str = ""


@router.get("/{workspace_id}/tools")
async def list_workspace_tools(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all tools and their enabled status for this workspace."""
    membership = await _check_workspace_access(db, workspace_id, user.id)
    if not membership:
        raise _not_found()

    from app.models.workspace_models import get_workspace_tool_allowlist
    from app.tools.base import get_tool_registry

    registry = get_tool_registry()
    allowlist = await get_workspace_tool_allowlist(db, workspace_id)

    items = []
    for t in registry.list_all():
        # If allowlist is None, all tools are permitted
        is_enabled = t.tool_id in allowlist if allowlist is not None else True
        items.append(
            ToolAllowlistResponse(
                tool_id=t.tool_id,
                name=t.name,
                description=t.description,
                category=t.category,
                enabled=is_enabled,
                required_scopes=t.metadata.required_scopes,
            ).model_dump()
        )
    return ok({"tools": items, "total": len(items)})


@router.put("/{workspace_id}/tools")
async def update_workspace_tools(
    workspace_id: str,
    body: UpdateToolsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update the tool allowlist for this workspace.

    Admin/owner only.  Uses sentinel INSERT pattern — never DELETE.
    """
    membership = await _check_workspace_access(db, workspace_id, user.id)
    if not membership or membership.role not in ("owner", "admin"):
        raise _not_found()

    # Validate tool names against registry
    from app.tools.base import get_tool_registry

    registry = get_tool_registry()
    valid_tool_ids = {t.tool_id for t in registry.list_all()}
    requested = set(body.tools)
    invalid = requested - valid_tool_ids
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tool IDs: {', '.join(sorted(invalid))}",
        )

    # Fetch existing allowlist entries
    result = await db.execute(
        select(WorkspaceToolAllowlist).where(
            WorkspaceToolAllowlist.workspace_id == workspace_id,
        )
    )
    existing = {row.tool_name: row for row in result.scalars().all()}

    # Enable requested tools (insert or re-activate)
    for tool_name in requested:
        if tool_name in existing:
            existing[tool_name].is_active = True
            existing[tool_name].granted_by = user.id
        else:
            db.add(
                WorkspaceToolAllowlist(
                    workspace_id=workspace_id,
                    tool_name=tool_name,
                    is_active=True,
                    granted_by=user.id,
                )
            )

    # Deactivate tools not in the requested set (sentinel — no DELETE)
    for tool_name, row in existing.items():
        if tool_name not in requested:
            row.is_active = False

    await db.flush()

    # Invalidate Redis cache so the next chat message sees the updated allowlist
    try:
        from app.models.workspace_models import invalidate_workspace_tool_allowlist_cache

        await invalidate_workspace_tool_allowlist_cache(workspace_id)
    except Exception:
        pass  # cache invalidation is best-effort

    return ok({"enabled_tools": sorted(requested), "count": len(requested)})


@router.post("/{workspace_id}/tools/request")
async def request_tool_access(
    workspace_id: str,
    body: RequestToolAccessRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Request access to a tool that is not enabled for this workspace.

    Logs the request and returns a confirmation.  Admins can enable it via
    PUT /{workspace_id}/tools.
    """
    membership = await _check_workspace_access(db, workspace_id, user.id)
    if not membership:
        raise _not_found()

    logger.info(
        "tool_access_request user_id=%s workspace_id=%s tool=%s reason=%s",
        user.id,
        workspace_id,
        body.tool_name,
        body.reason,
    )
    try:
        import asyncio

        from app.api.middleware.audit import log_event

        asyncio.create_task(
            log_event(
                user_id=user.id,
                action="tool.access_requested",
                details={
                    "workspace_id": workspace_id,
                    "tool_name": body.tool_name,
                    "reason": body.reason,
                },
            )
        )
    except Exception:
        pass  # audit logging must never break the request

    return ok({"status": "requested", "tool_name": body.tool_name})


@router.post("/{workspace_id}/teams", status_code=status.HTTP_201_CREATED)
async def create_team(
    workspace_id: str,
    payload: TeamCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = await _check_workspace_access(db, workspace_id, user.id)
    if not membership or membership.role not in ("owner", "admin"):
        raise _not_found()

    team = Team(
        id=str(uuid4()),
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(team)
    await db.flush()
    await db.refresh(team)

    return ok(
        TeamResponse(
            id=team.id,
            workspace_id=team.workspace_id,
            name=team.name,
            description=team.description,
            member_count=0,
            created_at=str(team.created_at) if team.created_at else "",
        ).model_dump()
    )
