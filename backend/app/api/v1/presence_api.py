"""
REST API endpoint for workspace presence status.

GET /api/v1/workspaces/{workspace_id}/presence
  Returns the list of online user IDs in a workspace.

This complements the WebSocket presence events by providing the initial
state when a user loads the Team page.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.workspace_models import WorkspaceMember
from app.websocket.presence import get_online_users

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["presence"])


@router.get("/{workspace_id}/presence")
async def get_workspace_presence(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the list of online users in a workspace.

    Requires authentication and workspace membership.
    Returns user IDs and basic user info for all online members.
    """
    # Verify workspace membership
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.is_active == True,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    # Get online user IDs from Redis
    online_user_ids = await get_online_users(workspace_id)

    # Fetch user info for online members
    online_users = []
    if online_user_ids:
        user_result = await db.execute(select(User).where(User.id.in_(online_user_ids), User.is_active == True))
        users = user_result.scalars().all()
        online_users = [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "username": u.username,
                "avatar_url": u.avatar_url,
            }
            for u in users
        ]

    return {
        "workspace_id": workspace_id,
        "online_count": len(online_user_ids),
        "online_user_ids": online_user_ids,
        "online_users": online_users,
    }
