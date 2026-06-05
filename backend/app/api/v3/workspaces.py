from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.v3.base import ok
from app.database import get_db
from app.models.user import User
from app.models.workspace_models import Workspace, WorkspaceMember
from app.schemas.workspace_v3 import (
    WorkspaceCreateRequest,
    WorkspaceListItem,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/workspaces", tags=["v3-workspaces"])


async def _require_workspaces_v3(db: AsyncSession) -> None:
    result = await db.execute(
        __import__("sqlalchemy").text(
            "SELECT enabled_globally FROM feature_flags WHERE key = 'WORKSPACES_V3_ENDPOINTS'"
        )
    )
    if not result.scalar():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found"
        )


async def _check_workspace_access(
    db: AsyncSession,
    workspace_id: str,
    user_id: int,
    required_roles: list[str] | None = None,
) -> WorkspaceMember:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    if required_roles and membership.role not in required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role"
        )
    return membership


@router.get("", status_code=status.HTTP_200_OK)
async def list_workspaces(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)

    result = await db.execute(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
    )
    memberships = result.scalars().all()

    workspaces = []
    for m in memberships:
        ws_result = await db.execute(
            select(Workspace).where(Workspace.id == m.workspace_id)
        )
        ws = ws_result.scalar_one_or_none()
        if ws and ws.is_active:
            workspaces.append(
                WorkspaceListItem(
                    id=ws.id,
                    name=ws.name,
                    slug=ws.slug,
                    plan=ws.plan,
                    member_count=0,
                    logo_url=ws.logo_url,
                    role=m.role,
                    created_at=ws.created_at,
                ).model_dump(mode="json")
            )

    return ok(workspaces)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)

    ws_id = str(uuid.uuid4())
    slug = payload.slug or payload.name.lower().replace(" ", "-").replace("_", "-")

    existing = await db.execute(select(Workspace).where(Workspace.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Slug already taken"
        )

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
            member_limit=ws.member_limit or 5,
            logo_url=ws.logo_url,
            settings=ws.settings or {},
            storage_used_bytes=ws.storage_used_bytes or 0,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        ).model_dump(mode="json")
    )


@router.get("/{workspace_id}", status_code=status.HTTP_200_OK)
async def get_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)
    await _check_workspace_access(db, workspace_id, user.id)

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    member_count_result = await db.execute(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
    )
    member_count = len(member_count_result.scalars().all())

    return ok(
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            owner_id=ws.owner_id,
            plan=ws.plan,
            member_count=member_count,
            member_limit=ws.member_limit or 5,
            logo_url=ws.logo_url,
            settings=ws.settings or {},
            storage_used_bytes=ws.storage_used_bytes or 0,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        ).model_dump(mode="json")
    )


@router.patch("/{workspace_id}", status_code=status.HTTP_200_OK)
async def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)
    await _check_workspace_access(db, workspace_id, user.id, ["admin", "owner"])

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    if payload.name is not None:
        ws.name = payload.name
    if payload.logo_url is not None:
        ws.logo_url = payload.logo_url
    if payload.settings is not None:
        ws.settings = payload.settings

    await db.flush()
    await db.refresh(ws)

    return ok(
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            owner_id=ws.owner_id,
            plan=ws.plan,
            member_count=0,
            member_limit=ws.member_limit or 5,
            logo_url=ws.logo_url,
            settings=ws.settings or {},
            storage_used_bytes=ws.storage_used_bytes or 0,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        ).model_dump(mode="json")
    )


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)
    await _check_workspace_access(db, workspace_id, user.id, ["owner"])

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    await db.delete(ws)
    await db.flush()


@router.get("/{workspace_id}/members", status_code=status.HTTP_200_OK)
async def list_members(
    workspace_id: str,
    include: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)
    await _check_workspace_access(db, workspace_id, user.id)

    result = await db.execute(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
    )
    members = result.scalars().all()

    member_list = []
    for m in members:
        entry = {
            "user_id": m.user_id,
            "role": m.role,
            "joined_at": m.joined_at.isoformat(),
        }
        if include and "user" in include:
            user_result = await db.execute(select(User).where(User.id == m.user_id))
            u = user_result.scalar_one_or_none()
            if u:
                entry["email"] = u.email
                entry["full_name"] = u.full_name
                entry["avatar_url"] = u.avatar_url
        member_list.append(entry)

    return ok(member_list)
