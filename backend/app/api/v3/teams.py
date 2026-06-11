from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.v3.base import ok
from app.database import get_db
from app.models.workspace_models import Team, WorkspaceMember
from app.schemas.workspace_v3 import TeamCreateRequest, TeamResponse

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

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
