from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user
from app.api.envelope import envelope as _envelope
from app.database import get_db
from app.models.byok_models import UserAPIKey
from app.utils.encryption import decrypt_api_key, encrypt_api_key, validate_provider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(tags=["BYOK"])

logger = logging.getLogger(__name__)

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
    models: list[str] | None = None
    base_url: str | None = None

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: APIKeyCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.debug("BYOK create: user=%s provider=%s has_models=%s has_base_url=%s",
                 user.id, data.provider, bool(data.models), bool(data.base_url))

    if not validate_provider(data.provider):
        logger.warning("BYOK create: unsupported provider=%s user=%s", data.provider, user.id)
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {data.provider}")

    logger.debug("BYOK create: provider validated, encrypting key...")
    encrypted = encrypt_api_key(data.api_key)
    logger.debug("BYOK create: key encrypted (len=%d), inserting to DB...", len(encrypted))

    import json

    # Capture values before any DB commit/rollback — rollback expires ORM objects
    uid = user.id
    provider_lower = data.provider.lower()

    key = UserAPIKey(
        user_id=uid,
        provider=provider_lower,
        encrypted_key=encrypted,
        key_label=data.label,
        base_url=data.base_url,
        models=json.dumps(data.models) if data.models else None,
    )
    db.add(key)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning("BYOK create: DUPLICATE user=%s provider=%s", uid, provider_lower)
        raise HTTPException(
            status_code=409,
            detail=f"You already have an active {provider_lower} key. Delete the existing one first."
        )
    await db.refresh(key)
    logger.info("BYOK created: user=%s provider=%s key_id=%s models=%s",
                uid, provider_lower, key.id, data.models)

    # Audit log
    from app.api.middleware.audit import log_event
    await log_event(uid, "byok_key_created", {"provider": provider_lower, "key_id": key.id})

    return _envelope({
        "id": key.id,
        "provider": key.provider,
        "key_label": key.key_label,
        "is_active": key.is_active,
        "created_at": key.created_at.isoformat(),
        "updated_at": key.updated_at.isoformat(),
        "models": key.get_models_list() or None,
        "base_url": key.base_url,
    })

@router.get("/")
async def list_api_keys(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        logger.debug("BYOK list: user=%s", user.id)
        result = await db.execute(
            select(UserAPIKey).where(UserAPIKey.user_id == user.id, UserAPIKey.is_active == True)
        )
        keys = result.scalars().all()
        logger.debug("BYOK list: user=%s returned %d keys", user.id, len(keys))
        return [
        {
            "id": k.id,
            "provider": k.provider,
            "key_label": k.key_label,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat(),
            "updated_at": k.updated_at.isoformat(),
            "models": k.get_models_list() or None,
            "base_url": k.base_url,
        }
        for k in keys
    ]
    except Exception as e:
        logger.error("BYOK list failed: user=%s error=%s", user.id, e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list API keys")

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(
            select(UserAPIKey).where(UserAPIKey.id == key_id, UserAPIKey.user_id == user.id)
        )
        key = result.scalar_one_or_none()
        if not key:
            raise HTTPException(status_code=404, detail="API key not found")

        key.is_active = False
        await db.commit()
        logger.info("BYOK deleted: user=%s provider=%s key_id=%s", user.id, key.provider, key_id)

        # Audit log
        from app.api.middleware.audit import log_event
        await log_event(user.id, "byok_key_deleted", {"provider": key.provider, "key_id": key.id})

        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("BYOK delete failed: user=%s key_id=%s error=%s", user.id, key_id, e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete API key")

# Internal helper for other services to get decrypted keys

@router.get("/models")
async def list_available_models(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List available models from user active BYOK keys."""
    from sqlalchemy import select

    from app.models.byok_models import UserAPIKey
    
    result = await db.execute(
        select(UserAPIKey).where(UserAPIKey.user_id == user.id, UserAPIKey.is_active == True)
    )
    keys = result.scalars().all()
    
    models = []
    for k in keys:
        model_list = k.get_models_list()
        for m in model_list:
            models.append({
                "id": m,
                "name": m,
                "provider": k.provider,
                "key_id": k.id,
                "key_label": k.key_label or f"{k.provider} key #{k.id}",
            })
    
    return models


async def get_decrypted_key(db: AsyncSession, user_id: int, provider: str) -> str | None:
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
