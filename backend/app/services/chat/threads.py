# ─────────────────────────────────────────────────────────────────────────
# Auto-decomposed from app/services/chat_service.py (CARD 3 refactor).
# Part of the `chat` package. Sibling cross-references and original imports
# are preserved so behavior/signatures stay byte-for-byte identical.
# ─────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.chat import ChatBranch, ChatFile, ChatMessage, ChatThread
from app.services.background_task_manager import background_task_manager

from .messages import create_chat_message, get_chat_messages

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "create_chat_branch",
    "create_chat_thread",
    "delete_chat_branch",
    "delete_chat_thread",
    "get_chat_branch",
    "get_chat_thread",
    "list_chat_branches",
    "list_chat_threads",
    "require_chat_thread_access",
    "update_chat_thread",
]


async def create_chat_thread(
    db: AsyncSession,
    user_id: int,
    username: str,
    title: str,
    model_preference: str | None = None,
    workspace_id: str | None = None,
) -> ChatThread:
    metadata = {"model_preference": model_preference} if model_preference else None
    thread = ChatThread(
        title=title,
        user_id=user_id,
        username=username,
        metadata_=metadata,
        workspace_id=workspace_id,
    )
    db.add(thread)
    await db.flush()
    await db.refresh(thread)
    return thread


async def get_chat_thread(db: AsyncSession, thread_id: int) -> ChatThread | None:
    result = await db.execute(select(ChatThread).where(ChatThread.id == thread_id))
    return result.scalar_one_or_none()


async def require_chat_thread_access(
    db: AsyncSession,
    thread_id: int,
    user_id: int,
) -> ChatThread:
    """Fetch a chat thread and verify the user has access.

    Access rules:
    1. If the thread has a workspace_id → verify the user is an active member
       of that workspace.
    2. If the thread has no workspace_id → fall back to user_id ownership.
    3. If the thread doesn't exist → 404.
    """
    from fastapi import HTTPException

    thread = await get_chat_thread(db, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Not found")

    if thread.workspace_id:
        from app.models.workspace_models import WorkspaceMember

        result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == thread.workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.is_active == True,
            )
        )
        if result.scalar_one_or_none() is None:
            # Check cross-workspace grants across all user's workspaces
            from app.services.cross_workspace_service import (
                check_entity_access,
                find_user_workspaces,
            )

            user_workspaces = await find_user_workspaces(db, user_id)
            has_cross_access = False
            for ws_id in user_workspaces:
                if ws_id == thread.workspace_id:
                    continue
                grant = await check_entity_access(
                    db,
                    user_id=user_id,
                    target_workspace_id=ws_id,
                    entity_type="chat_thread",
                    entity_id=str(thread_id),
                    required_permission="read",
                )
                if grant:
                    has_cross_access = True
                    break
            if not has_cross_access:
                logger.warning(
                    "entity_access_denied"
                    " user_id=%s entity_type=chat_thread entity_id=%s"
                    " workspace_id=%s reason=no_membership",
                    user_id,
                    thread_id,
                    thread.workspace_id,
                )
                try:
                    from app.api.middleware.audit import log_event
                    from app.services.background_task_manager import background_task_manager

                    background_task_manager.spawn(
                        log_event(
                            user_id=user_id,
                            action="entity.access_denied",
                            details={
                                "entity_type": "chat_thread",
                                "entity_id": str(thread_id),
                                "workspace_id": str(thread.workspace_id),
                                "reason": "no_membership",
                            },
                        ),
                        label="access_denied_audit_no_membership",
                    )
                except Exception:
                    pass
                raise HTTPException(status_code=404, detail="Not found")
    else:
        if thread.user_id != user_id:
            logger.warning(
                "entity_access_denied"
                " user_id=%s entity_type=chat_thread entity_id=%s"
                " owner_user_id=%s reason=owner_mismatch",
                user_id,
                thread_id,
                thread.user_id,
            )
            try:
                from app.api.middleware.audit import log_event
                from app.services.background_task_manager import background_task_manager

                background_task_manager.spawn(
                    log_event(
                        user_id=user_id,
                        action="entity.access_denied",
                        details={
                            "entity_type": "chat_thread",
                            "entity_id": str(thread_id),
                            "reason": "owner_mismatch",
                        },
                    ),
                    label="access_denied_audit_owner_mismatch",
                )
            except Exception:
                pass
            raise HTTPException(status_code=404, detail="Not found")

    return thread


async def list_chat_threads(
    db: AsyncSession,
    user_id: int,
    *,
    offset: int = 0,
    limit: int = 20,
    workspace_id: str | None = None,
) -> tuple[list[ChatThread], int]:
    base_filter = ChatThread.workspace_id == workspace_id if workspace_id is not None else ChatThread.user_id == user_id
    count_q = select(func.count()).select_from(ChatThread).where(base_filter)
    total = (await db.execute(count_q)).scalar() or 0
    items_q = select(ChatThread).where(base_filter).order_by(ChatThread.updated_at.desc()).offset(offset).limit(limit)
    items = list((await db.execute(items_q)).scalars().all())
    return items, total


async def update_chat_thread(
    db: AsyncSession,
    thread_id: int,
    *,
    title: str | None = None,
    is_archived: bool | None = None,
) -> ChatThread | None:
    thread = await get_chat_thread(db, thread_id)
    if thread is None:
        return None
    if title is not None:
        thread.title = title
    if is_archived is not None:
        thread.is_archived = is_archived
    await db.flush()
    await db.refresh(thread)
    return thread


async def delete_chat_thread(db: AsyncSession, thread_id: int) -> bool:
    thread = await get_chat_thread(db, thread_id)
    if thread is None:
        return False
    await db.delete(thread)
    await db.flush()
    return True


async def create_chat_branch(
    db: AsyncSession,
    user_id: int,
    parent_thread_id: int,
    parent_message_id: int,
    title: str,
) -> ChatBranch:
    """Create a new branch: copies messages up to parent_message_id into a new thread."""

    # Verify parent thread exists and belongs to user
    parent_thread = await get_chat_thread(db, parent_thread_id)
    if parent_thread is None:
        raise ValueError("Parent thread not found")

    # Create new thread for the branch
    branch_thread = await create_chat_thread(db, user_id, parent_thread.username, title)

    # Copy messages up to and including parent_message_id
    all_msgs, _ = await get_chat_messages(db, parent_thread_id)
    msgs_to_copy = [m for m in all_msgs if m.id <= parent_message_id]
    for msg in msgs_to_copy:
        await create_chat_message(db, branch_thread.id, msg.role, msg.content, user_id=msg.user_id)

    # Create branch record
    branch = ChatBranch(
        thread_id=branch_thread.id,
        parent_thread_id=parent_thread_id,
        parent_message_id=parent_message_id,
        user_id=user_id,
        title=title,
    )
    db.add(branch)
    await db.flush()
    await db.refresh(branch)
    return branch


async def list_chat_branches(
    db: AsyncSession,
    parent_thread_id: int,
) -> list[ChatBranch]:
    """List all branches from a given thread."""
    result = await db.execute(select(ChatBranch).where(ChatBranch.parent_thread_id == parent_thread_id))
    return list(result.scalars().all())


async def get_chat_branch(db: AsyncSession, branch_id: int) -> ChatBranch | None:
    """Get a single branch by ID."""
    result = await db.execute(select(ChatBranch).where(ChatBranch.id == branch_id))
    return result.scalar_one_or_none()


async def delete_chat_branch(db: AsyncSession, branch_id: int) -> bool:
    """Delete a branch and its thread."""
    branch = await get_chat_branch(db, branch_id)
    if branch is None:
        return False
    # Delete the branch thread (cascades messages)
    await delete_chat_thread(db, branch.thread_id)
    # Delete the branch record
    await db.delete(branch)
    await db.flush()
    return True
