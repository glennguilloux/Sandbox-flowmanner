"""
Delegation Service.

Manages temporary role delegations between users within a tenant.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_models import CustomRole, RoleDelegation

logger = logging.getLogger(__name__)


async def create_delegation(
    db: AsyncSession,
    delegator_id: int,
    delegatee_id: int,
    role_id: str,
    workspace_id: str | None = None,
    reason: str | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> RoleDelegation:
    """Create a new role delegation."""
    # Verify role exists
    role_result = await db.execute(select(CustomRole).where(CustomRole.id == role_id))
    role = role_result.scalar_one_or_none()
    if not role:
        raise ValueError(f"Role not found: {role_id}")

    # Prevent self-delegation
    if delegator_id == delegatee_id:
        raise ValueError("Cannot delegate to yourself")

    delegation = RoleDelegation(
        delegator_id=delegator_id,
        delegatee_id=delegatee_id,
        workspace_id=workspace_id,
        role_id=role_id,
        reason=reason,
        starts_at=starts_at,
        ends_at=ends_at,
        is_active=True,
    )
    db.add(delegation)
    await db.flush()
    await db.refresh(delegation)

    logger.info(
        "Delegation created: %s -> %s, role=%s, workspace=%s",
        delegator_id,
        delegatee_id,
        role.name,
        workspace_id,
    )
    return delegation


async def get_delegation(db: AsyncSession, delegation_id: str) -> RoleDelegation | None:
    """Get a delegation by ID."""
    result = await db.execute(select(RoleDelegation).where(RoleDelegation.id == delegation_id))
    return result.scalar_one_or_none()


async def list_delegations(
    db: AsyncSession,
    delegator_id: int | None = None,
    delegatee_id: int | None = None,
    workspace_id: str | None = None,
    active_only: bool = True,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[RoleDelegation], int]:
    """List delegations with optional filters."""
    query = select(RoleDelegation)
    count_query = select(func.count(RoleDelegation.id))

    if delegator_id is not None:
        query = query.where(RoleDelegation.delegator_id == delegator_id)
        count_query = count_query.where(RoleDelegation.delegator_id == delegator_id)

    if delegatee_id is not None:
        query = query.where(RoleDelegation.delegatee_id == delegatee_id)
        count_query = count_query.where(RoleDelegation.delegatee_id == delegatee_id)

    if workspace_id is not None:
        query = query.where(RoleDelegation.workspace_id == workspace_id)
        count_query = count_query.where(RoleDelegation.workspace_id == workspace_id)

    if active_only:
        query = query.where(RoleDelegation.is_active == True)
        count_query = count_query.where(RoleDelegation.is_active == True)

    query = query.offset(offset).limit(limit).order_by(RoleDelegation.created_at.desc())
    result = await db.execute(query)
    delegations = list(result.scalars().all())

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return delegations, total


async def revoke_delegation(
    db: AsyncSession,
    delegation_id: str,
    revoked_by: int | None = None,
    audit_notes: str | None = None,
) -> bool:
    """Revoke (deactivate) a delegation."""
    delegation = await get_delegation(db, delegation_id)
    if not delegation:
        return False

    delegation.is_active = False
    if audit_notes:
        delegation.audit_notes = audit_notes

    await db.flush()
    logger.info("Delegation %s revoked by user %s", delegation_id, revoked_by)
    return True


async def get_active_delegations_for_user(
    db: AsyncSession,
    user_id: int,
    workspace_id: str | None = None,
) -> list[RoleDelegation]:
    """Get all active delegations where user is the delegatee."""
    now = datetime.now(UTC)
    query = select(RoleDelegation).where(
        RoleDelegation.delegatee_id == user_id,
        RoleDelegation.is_active == True,
    )
    if workspace_id:
        query = query.where(RoleDelegation.workspace_id == workspace_id)

    result = await db.execute(query)
    delegations = []

    for d in result.scalars().all():
        # Check time bounds
        if d.starts_at and d.starts_at > now:
            continue
        if d.ends_at and d.ends_at < now:
            continue
        delegations.append(d)

    return delegations


async def expire_stale_delegations(db: AsyncSession) -> int:
    """Deactivate delegations whose end_at has passed. Returns count."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(RoleDelegation).where(
            RoleDelegation.is_active == True,
            RoleDelegation.ends_at != None,
            RoleDelegation.ends_at < now,
        )
    )
    expired = result.scalars().all()
    count = 0
    for d in expired:
        d.is_active = False
        count += 1

    if count:
        await db.flush()
        logger.info("Expired %s stale delegations", count)

    return count
