from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user
from app.api.v3.base import ok, paginated
from app.database import get_db
from app.models.user import User
from app.models.workspace_models import Team, TeamMember, WorkspaceMember
from app.schemas.workspace_v3 import (
    TeamCreateRequest,
    TeamMemberCreateRequest,
    TeamMemberResponse,
    TeamResponse,
    TeamUpdateRequest,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/teams", tags=["v3-teams"])


async def _require_teams_v3(db: AsyncSession) -> None:
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT enabled_globally FROM feature_flags WHERE key = 'WORKSPACES_V3_TEAMS_TOPLEVEL'")
    )
    if not result.scalar():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")


@router.get("", status_code=status.HTTP_200_OK)
async def list_teams(
    workspace_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_teams_v3(db)

    membership = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if not membership.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    result = await db.execute(select(Team).where(Team.workspace_id == workspace_id))
    teams = result.scalars().all()

    return ok(
        [
            TeamResponse(
                id=t.id,
                workspace_id=t.workspace_id,
                name=t.name,
                description=t.description,
                created_at=t.created_at,
            ).model_dump(mode="json")
            for t in teams
        ]
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_teams_v3(db)

    membership = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == payload.workspace_id,
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.role.in_(["admin", "owner"]),
        )
    )
    if not membership.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

    team = Team(
        id=str(uuid.uuid4()),
        workspace_id=payload.workspace_id,
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
            created_at=team.created_at,
        ).model_dump(mode="json")
    )


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_teams_v3(db)

    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    membership = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == team.workspace_id,
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.role.in_(["admin", "owner"]),
        )
    )
    if not membership.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

    await db.delete(team)
    await db.flush()


async def _team_and_member(team_id: str, user: User, db: AsyncSession, require_admin: bool) -> Team:
    """Resolve the team and enforce the WorkspaceMember check.

    404 if the team's workspace is not a workspace the user belongs to.
    403 if ``require_admin`` and the user's workspace role is not admin/owner.
    """
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    membership = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == team.workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    m = membership.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if require_admin and m.role not in ("admin", "owner"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return team


@router.get("/{team_id}/members", status_code=status.HTTP_200_OK)
async def list_team_members(
    team_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_teams_v3(db)
    await _team_and_member(team_id, user, db, require_admin=False)

    result = await db.execute(select(TeamMember).where(TeamMember.team_id == team_id))
    members = result.scalars().all()
    total = len(members)
    start = (page - 1) * per_page
    end = start + per_page
    items = [
        TeamMemberResponse(user_id=m.user_id, role=m.role, joined_at=m.joined_at).model_dump(mode="json")
        for m in members[start:end]
    ]
    return paginated(items=items, total=total, page=page, per_page=per_page)


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: str,
    payload: TeamMemberCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_teams_v3(db)
    team = await _team_and_member(team_id, user, db, require_admin=True)

    user_result = await db.execute(select(User).where(User.id == payload.user_id))
    if not user_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    dup = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == payload.user_id,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already a member")

    member = TeamMember(team_id=team.id, user_id=payload.user_id, role=payload.role)
    db.add(member)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already a member")
    await db.refresh(member)

    return ok(
        TeamMemberResponse(user_id=member.user_id, role=member.role, joined_at=member.joined_at).model_dump(mode="json")
    )


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: str,
    user_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_teams_v3(db)
    await _team_and_member(team_id, user, db, require_admin=True)

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    await db.delete(member)
    await db.flush()


@router.patch("/{team_id}", status_code=status.HTTP_200_OK)
async def update_team(
    team_id: str,
    payload: TeamUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_teams_v3(db)
    team = await _team_and_member(team_id, user, db, require_admin=True)

    if payload.name is not None:
        team.name = payload.name
    if payload.description is not None:
        team.description = payload.description
    await db.flush()

    return ok(
        TeamResponse(
            id=team.id,
            workspace_id=team.workspace_id,
            name=team.name,
            description=team.description,
            created_at=team.created_at,
        ).model_dump(mode="json")
    )
