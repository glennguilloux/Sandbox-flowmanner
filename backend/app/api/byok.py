from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.byok_models import UserAPIKey
from app.utils.encryption import decrypt_api_key, encrypt_api_key, validate_provider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/byok", tags=["BYOK"])


class APIKeyCreate(BaseModel):
    provider: str
    api_key: str
    label: str | None = None
    base_url: str | None = None
    models: list[str] | None = None  # List of model IDs this key can access


class APIKeyResponse(BaseModel):
    id: int
    provider: str
    key_label: str | None
    is_active: bool
    created_at: str
    updated_at: str


@router.post("/", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: APIKeyCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        """Store a new API key (encrypted at rest)."""
        if not validate_provider(data.provider):
            raise HTTPException(
                status_code=400, detail=f"Unsupported provider: {data.provider}"
            )

        encrypted = encrypt_api_key(data.api_key)

        import json

        key = UserAPIKey(
            user_id=user.id,
            provider=data.provider.lower(),
            encrypted_key=encrypted,
            key_label=data.label,
            base_url=data.base_url,
            models=json.dumps(data.models) if data.models else None,
        )
        db.add(key)
        await db.commit()
        await db.refresh(key)

        return {
            "id": key.id,
            "provider": key.provider,
            "key_label": key.key_label,
            "is_active": key.is_active,
            "created_at": key.created_at.isoformat(),
            "updated_at": key.updated_at.isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/", response_model=list[APIKeyResponse])
async def list_api_keys(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        """List all API keys for the current user (keys are not decrypted)."""
        result = await db.execute(
            select(UserAPIKey).where(
                UserAPIKey.user_id == user.id, UserAPIKey.is_active == True
            )
        )
        keys = result.scalars().all()
        return [
            {
                "id": k.id,
                "provider": k.provider,
                "key_label": k.key_label,
                "is_active": k.is_active,
                "created_at": k.created_at.isoformat(),
                "updated_at": k.updated_at.isoformat(),
            }
            for k in keys
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        """Soft-delete an API key (set is_active=False)."""
        result = await db.execute(
            select(UserAPIKey).where(
                UserAPIKey.id == key_id, UserAPIKey.user_id == user.id
            )
        )
        key = result.scalar_one_or_none()
        if not key:
            raise HTTPException(status_code=404, detail="API key not found")

        key.is_active = False
        await db.commit()
        return None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# Internal helper for other services to get decrypted keys
async def get_decrypted_key(
    db: AsyncSession, user_id: int, provider: str
) -> str | None:
    """Retrieve and decrypt an API key for internal use."""
    result = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.user_id == user_id,
            UserAPIKey.provider == provider.lower(),
            UserAPIKey.is_active == True,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        return None
    return decrypt_api_key(key.encrypted_key)
