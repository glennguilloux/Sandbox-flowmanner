"""Workspace direct messages API — persistent DMs between workspace members.

GET  /api/workspaces/{id}/messages?recipient_id=X&limit=50&before_id=Y  — message history
POST /api/workspaces/{id}/messages  — send & persist a message
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.workspace_activity import record_workspace_activity
from app.database import get_db
from app.models.user import User
from app.models.workspace_models import WorkspaceMember, WorkspaceMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspace_messages"])


# ── Schemas ──────────────────────────────────────────────────────────────


class SendMessageRequest(BaseModel):
    recipient_id: int
    content: str


class MessageResponse(BaseModel):
    id: int
    sender_id: int
    recipient_id: int
    content: str
    created_at: str


# ── Helpers ──────────────────────────────────────────────────────────────


async def _verify_membership(
    db: AsyncSession, workspace_id: str, user_id: int
) -> None:
    """Raise 403 if user is not an active workspace member."""
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.is_active == True,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a member of this workspace")


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/{workspace_id}/messages")
async def list_messages(
    workspace_id: str,
    recipient_id: int = Query(..., description="The other participant in the DM conversation"),
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None, description="Pagination: get messages older than this ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get DM history between the current user and recipient_id in this workspace.

    Ordered newest-first for efficient timeline display. Reverse on the client.
    Supports cursor-based pagination via before_id.
    """
    await _verify_membership(db, workspace_id, current_user.id)

    # Build query: messages where current_user is either sender or recipient
    # and the other party is recipient_id
    clause = and_(
        WorkspaceMessage.workspace_id == workspace_id,
        or_(
            and_(
                WorkspaceMessage.sender_id == current_user.id,
                WorkspaceMessage.recipient_id == recipient_id,
            ),
            and_(
                WorkspaceMessage.sender_id == recipient_id,
                WorkspaceMessage.recipient_id == current_user.id,
            ),
        ),
    )

    if before_id:
        clause = and_(clause, WorkspaceMessage.id < before_id)

    result = await db.execute(
        select(WorkspaceMessage)
        .where(clause)
        .order_by(desc(WorkspaceMessage.id))
        .limit(limit)
    )
    messages = result.scalars().all()

    return [
        MessageResponse(
            id=m.id,
            sender_id=m.sender_id,
            recipient_id=m.recipient_id,
            content=m.content,
            created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m in reversed(messages)  # reverse to chronological order
    ]


@router.post("/{workspace_id}/messages", status_code=201)
async def send_message(
    workspace_id: str,
    payload: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Persist a DM and return the saved message.

    The caller should also emit a WebSocket event for real-time delivery.
    This endpoint ensures the message is never lost.
    """
    await _verify_membership(db, workspace_id, current_user.id)

    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    if payload.recipient_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot send a message to yourself")

    msg = WorkspaceMessage(
        workspace_id=workspace_id,
        sender_id=current_user.id,
        recipient_id=payload.recipient_id,
        content=payload.content.strip(),
    )
    db.add(msg)

    # Record workspace activity event before commit (single transaction)
    await record_workspace_activity(
        db,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        event_type="message_sent",
        description=payload.content.strip()[:120],
    )

    await db.commit()
    await db.refresh(msg)

    return MessageResponse(
        id=msg.id,
        sender_id=msg.sender_id,
        recipient_id=msg.recipient_id,
        content=msg.content,
        created_at=msg.created_at.isoformat() if msg.created_at else "",
    )
