from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.v3.base import ok
from app.database import get_db
from app.models.workspace_activity_log import WorkspaceActivityLog
from app.models.workspace_models import WorkspaceMember
from app.schemas.workspace_v3 import AuditLogEntry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/workspaces", tags=["v3-workspace-audit"])


async def _require_audit_enabled(db: AsyncSession) -> None:
    from sqlalchemy import text

    result = await db.execute(
        text(
            "SELECT enabled_globally FROM feature_flags WHERE key = 'WORKSPACES_V3_AUDIT'"
        )
    )
    if not result.scalar():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found"
        )


@router.get("/{workspace_id}/audit-log", status_code=status.HTTP_200_OK)
async def get_audit_log(
    workspace_id: str,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_audit_enabled(db)

    membership = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if not membership.scalar_one_or_none():
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    result = await db.execute(
        select(WorkspaceActivityLog)
        .where(WorkspaceActivityLog.workspace_id == workspace_id)
        .order_by(WorkspaceActivityLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    entries = result.scalars().all()

    return ok(
        [
            AuditLogEntry(
                id=e.id,
                actor_id=e.actor_id,
                action=e.action,
                target_type=e.target_type,
                target_id=e.target_id,
                activity_metadata=e.activity_metadata or {},
                created_at=e.created_at,
            ).model_dump(mode="json")
            for e in entries
        ]
    )
