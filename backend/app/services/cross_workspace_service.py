"""Cross-workspace permission grants — share specific entities across workspaces.

Allows workspace A to grant read or write access to a specific mission,
workflow, or chat thread to members of workspace B.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from app.models.workspace_models import WorkspaceMember, WorkspaceShare

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Valid entity types that can be shared
VALID_ENTITY_TYPES = frozenset(("mission", "workflow", "chat_thread"))

# Valid permission levels
VALID_PERMISSIONS = frozenset(("read", "write"))


class CrossWorkspaceError(Exception):
    """Base error for cross-workspace operations."""

    pass


class ShareNotFoundError(CrossWorkspaceError):
    """Share grant not found."""

    pass


class SharePermissionError(CrossWorkspaceError):
    """User lacks permission to manage shares."""

    pass


async def grant_share(
    db: AsyncSession,
    *,
    source_workspace_id: str,
    target_workspace_id: str,
    entity_type: str,
    entity_id: str,
    permission: str = "read",
    granted_by: int | None = None,
) -> WorkspaceShare:
    """Create or update a cross-workspace share grant.

    The caller must be an admin/owner of the source workspace.
    Idempotent: if a share already exists for this entity+target, updates it.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise CrossWorkspaceError(
            f"Invalid entity_type: {entity_type}. Must be one of {VALID_ENTITY_TYPES}"
        )
    if permission not in VALID_PERMISSIONS:
        raise CrossWorkspaceError(
            f"Invalid permission: {permission}. Must be one of {VALID_PERMISSIONS}"
        )
    if source_workspace_id == target_workspace_id:
        raise CrossWorkspaceError("Cannot share an entity with its own workspace")

    # Check for existing share
    result = await db.execute(
        select(WorkspaceShare).where(
            WorkspaceShare.source_workspace_id == source_workspace_id,
            WorkspaceShare.target_workspace_id == target_workspace_id,
            WorkspaceShare.entity_type == entity_type,
            WorkspaceShare.entity_id == str(entity_id),
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.permission = permission
        existing.is_active = True
        existing.granted_by = granted_by
        await db.flush()
        await db.refresh(existing)
        logger.info(
            "cross_workspace_share_updated source=%s target=%s entity_type=%s entity_id=%s permission=%s",
            source_workspace_id,
            target_workspace_id,
            entity_type,
            entity_id,
            permission,
        )
        return existing

    share = WorkspaceShare(
        id=str(uuid4()),
        source_workspace_id=source_workspace_id,
        target_workspace_id=target_workspace_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        permission=permission,
        granted_by=granted_by,
        is_active=True,
    )
    db.add(share)
    await db.flush()
    await db.refresh(share)

    logger.info(
        "cross_workspace_share_granted source=%s target=%s entity_type=%s entity_id=%s permission=%s granted_by=%s",
        source_workspace_id,
        target_workspace_id,
        entity_type,
        entity_id,
        permission,
        granted_by,
    )
    return share


async def revoke_share(
    db: AsyncSession,
    share_id: str,
    *,
    revoked_by: int | None = None,
) -> bool:
    """Deactivate a cross-workspace share grant (soft-revoke)."""
    result = await db.execute(
        select(WorkspaceShare).where(WorkspaceShare.id == str(share_id))
    )
    share = result.scalar_one_or_none()
    if share is None:
        raise ShareNotFoundError(f"Share {share_id} not found")

    share.is_active = False
    await db.flush()

    logger.info(
        "cross_workspace_share_revoked share_id=%s revoked_by=%s",
        share_id,
        revoked_by,
    )
    return True


async def check_entity_access(
    db: AsyncSession,
    *,
    user_id: int,
    target_workspace_id: str,
    entity_type: str,
    entity_id: str,
    required_permission: str = "read",
) -> WorkspaceShare | None:
    """Check if a user has cross-workspace access to an entity.

    Returns the WorkspaceShare grant if access is allowed, None otherwise.

    The user must be an active member of the target_workspace_id (the workspace
    being granted access). This function only checks the cross-workspace grant
    itself — the caller is responsible for verifying that the entity actually
    belongs to the source workspace.

    Args:
        user_id: The user requesting access.
        target_workspace_id: The workspace the user belongs to (grantee).
        entity_type: Type of entity (mission, workflow, chat_thread).
        entity_id: The entity ID.
        required_permission: Minimum permission needed ('read' or 'write').
    """
    if entity_type not in VALID_ENTITY_TYPES:
        return None

    # Verify user is an active member of the target workspace
    member_result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == target_workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.is_active == True,
        )
    )
    if member_result.scalar_one_or_none() is None:
        return None

    # Find an active share grant for this entity
    result = await db.execute(
        select(WorkspaceShare).where(
            WorkspaceShare.target_workspace_id == target_workspace_id,
            WorkspaceShare.entity_type == entity_type,
            WorkspaceShare.entity_id == str(entity_id),
            WorkspaceShare.is_active == True,
        )
    )
    share = result.scalar_one_or_none()
    if share is None:
        return None

    # Check permission level: write implies read
    if required_permission == "read" and share.permission in ("read", "write"):
        return share
    if required_permission == "write" and share.permission == "write":
        return share

    return None


async def list_shares_for_entity(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
) -> list[WorkspaceShare]:
    """List all active cross-workspace shares for a specific entity."""
    result = await db.execute(
        select(WorkspaceShare).where(
            WorkspaceShare.entity_type == entity_type,
            WorkspaceShare.entity_id == str(entity_id),
            WorkspaceShare.is_active == True,
        )
    )
    return list(result.scalars().all())


async def list_shares_for_workspace(
    db: AsyncSession,
    workspace_id: str,
    *,
    direction: str = "outgoing",
) -> list[WorkspaceShare]:
    """List cross-workspace shares for a workspace.

    direction='outgoing': shares granted BY this workspace (source).
    direction='incoming': shares granted TO this workspace (target).
    """
    col = (
        WorkspaceShare.source_workspace_id
        if direction == "outgoing"
        else WorkspaceShare.target_workspace_id
    )

    result = await db.execute(
        select(WorkspaceShare).where(
            col == workspace_id,
            WorkspaceShare.is_active == True,
        )
    )
    return list(result.scalars().all())


async def find_user_workspaces(db: AsyncSession, user_id: int) -> list[str]:
    """Return all workspace IDs the user is an active member of.

    Used by access check helpers to find cross-workspace grants across
    all of a user's workspaces.
    """
    result = await db.execute(
        select(WorkspaceMember.workspace_id).where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.is_active == True,
        )
    )
    return [row[0] for row in result.all()]
