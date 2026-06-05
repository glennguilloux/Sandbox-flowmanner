"""
Delegation API Routes.

Provides endpoints for managing role delegations:
- POST /delegations - Create delegation
- GET /delegations - List delegations (filtered by delegator/delegatee/tenant)
- GET /delegations/{id} - Get delegation details
- DELETE /delegations/{id} - Revoke delegation
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.database import get_db
from app.models.user import User
from app.schemas.delegation import (
    DelegationCreate,
    DelegationListResponse,
    DelegationResponse,
)
from app.services.delegation_service import (
    create_delegation,
    get_delegation,
    list_delegations,
    revoke_delegation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/delegations", tags=["delegations"])


@router.post("", response_model=DelegationResponse, status_code=status.HTTP_201_CREATED)
async def create_new_delegation(
    payload: DelegationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("delegations.manage")),
):
    """
    Create a new role delegation.

    The authenticated user becomes the delegator. Only users with
    'delegations.manage' permission can create delegations.
    """
    try:
        delegation = await create_delegation(
            db=db,
            delegator_id=user.id,
            delegatee_id=payload.delegatee_id,
            role_id=payload.role_id,
            workspace_id=payload.workspace_id,
            reason=payload.reason,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
        return DelegationResponse.model_validate(delegation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=DelegationListResponse)
async def list_all_delegations(
    delegator_id: int | None = Query(None, description="Filter by delegator user ID"),
    delegatee_id: int | None = Query(None, description="Filter by delegatee user ID"),
    workspace_id: str | None = Query(None, description="Filter by workspace ID"),
    active_only: bool = Query(True, description="Only return active delegations"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List delegations with optional filters.

    Users can see delegations where they are the delegator or delegatee.
    Admins can see all delegations.
    """
    # Non-admins can only see their own delegations
    if not user.is_admin:
        delegator_delegations, _ = await list_delegations(
            db, delegator_id=user.id, active_only=active_only, offset=0, limit=1000
        )
        delegatee_delegations, _ = await list_delegations(
            db, delegatee_id=user.id, active_only=active_only, offset=0, limit=1000
        )
        all_delegations = {d.id: d for d in delegator_delegations + delegatee_delegations}
        delegations = list(all_delegations.values())
        total = len(delegations)
        delegations = delegations[offset : offset + limit]
    else:
        delegations, total = await list_delegations(
            db,
            delegator_id=delegator_id,
            delegatee_id=delegatee_id,
            workspace_id=workspace_id,
            active_only=active_only,
            offset=offset,
            limit=limit,
        )

    return DelegationListResponse(
        delegations=[DelegationResponse.model_validate(d) for d in delegations],
        total=total,
    )


@router.get("/{delegation_id}", response_model=DelegationResponse)
async def get_delegation_by_id(
    delegation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get delegation details by ID."""
    delegation = await get_delegation(db, delegation_id)
    if not delegation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delegation not found")

    # Only delegator, delegatee, or admin can view
    if not user.is_admin and user.id not in (delegation.delegator_id, delegation.delegatee_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return DelegationResponse.model_validate(delegation)


@router.delete("/{delegation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_delegation_by_id(
    delegation_id: str,
    audit_notes: str | None = Query(None, description="Reason for revocation"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Revoke (deactivate) a delegation.

    Only the delegator or an admin can revoke a delegation.
    """
    delegation = await get_delegation(db, delegation_id)
    if not delegation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delegation not found")

    if not user.is_admin and user.id != delegation.delegator_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only delegator or admin can revoke")

    success = await revoke_delegation(
        db, delegation_id, revoked_by=user.id, audit_notes=audit_notes
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to revoke delegation")
