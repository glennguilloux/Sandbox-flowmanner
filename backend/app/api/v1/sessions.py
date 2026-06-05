"""Session management API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.session_management import (
    get_user_sessions,
    revoke_all_other_sessions,
    revoke_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/sessions", tags=["sessions"])


@router.get("/")
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active sessions for the current user."""
    sessions = await get_user_sessions(db, user.id)
    return {"sessions": sessions, "count": len(sessions)}


@router.delete("/{session_id}")
async def delete_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific session."""
    success = await revoke_session(db, user.id, session_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or already revoked.",
        )
    return {"message": "Session revoked successfully."}


@router.delete("/")
async def delete_all_other_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all sessions except the current one."""
    # Get current refresh token from request body
    try:
        body = await request.json()
        current_token = body.get("refresh_token", "")
    except Exception:
        current_token = ""

    if not current_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="refresh_token required in request body.",
        )

    count = await revoke_all_other_sessions(db, user.id, current_token)
    return {"message": f"Revoked {count} other sessions."}
