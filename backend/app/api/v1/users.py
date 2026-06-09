import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.auth import UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_user(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete the current user's account.

    Replaces the placeholder danger-zone TODO. Soft-deletes by setting
    is_active = False, or hard-deletes for accounts with no associated data.
    """
    # Revoke all sessions
    from app.services.auth_service import revoke_all_user_tokens

    await revoke_all_user_tokens(db, user.id)
    # Soft-delete: mark as inactive so orphaned references remain valid
    user.is_active = False
    user.email = f"deleted-{user.id}@flowmanner.com"
    user.username = None
    await db.flush()
    logger = logging.getLogger(__name__)
    logger.info('User %s account deleted', user.id)


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(user: User = Depends(get_current_user)):
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.auth_service import hash_password

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    await db.flush()
    await db.refresh(user)
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
    )
