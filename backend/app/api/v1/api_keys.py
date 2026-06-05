from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import get_current_user, get_workspace_id
from app.database import get_db
from app.models.byok_models import UserAPIKey
from app.schemas.byok import BYOKValidateRequest, BYOKValidateResponse, ModelInfo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def _mask_key(encrypted: str) -> str:
    """Return a masked representation of an encrypted key for display."""
    if len(encrypted) <= 8:
        return "****"
    return f"{encrypted[:4]}...{encrypted[-4:]}"
user_keys_router = APIRouter(prefix="/user/keys", tags=["user-keys"])

# In-module cache: {provider_key: (timestamp, List[ModelInfo])}
_model_cache: dict[str, tuple[float, list[ModelInfo]]] = {}
_CACHE_TTL = 300  # 5 minutes

_PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

_NON_CHAT_KEYWORDS = ("embedding", "whisper", "dall-e", "tts", "moderation")


def _is_chat_model(model_id: str) -> bool:
    lower_id = model_id.lower()
    return not any(kw in lower_id for kw in _NON_CHAT_KEYWORDS)


def _get_base_url(provider: str, base_url: str | None = None) -> str:
    if base_url:
        return base_url.rstrip("/")
    return _PROVIDER_BASE_URLS.get(provider.lower(), _PROVIDER_BASE_URLS["openai"])


_MODEL_CATALOG: dict[str, list[dict]] = {
    "openai": [
        {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai", "context_window": 128000},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "openai", "context_window": 128000},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "provider": "openai", "context_window": 128000},
        {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "provider": "openai", "context_window": 16385},
    ],
    "openai-compatible": [
        {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai-compatible", "context_window": 128000},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "openai-compatible", "context_window": 128000},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "provider": "openai-compatible", "context_window": 128000},
        {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "provider": "openai-compatible", "context_window": 16385},
    ],
}

_OPENAI_MODELS_URL = "https://api.openai.com/v1/models"


@router.post("/validate", response_model=BYOKValidateResponse)
async def validate_api_key(request: BYOKValidateRequest) -> BYOKValidateResponse:
    provider = request.provider.lower()
    api_key = request.api_key

    if provider not in ("openai", "openai-compatible"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {provider}. Only 'openai' and 'openai-compatible' are supported.",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                _OPENAI_MODELS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.TimeoutException:
        return BYOKValidateResponse(
            status="invalid",
            models=[],
            error="Request timed out while validating API key",
        )
    except httpx.RequestError as exc:
        logger.warning("HTTP request error during BYOK validation: %s", exc)
        return BYOKValidateResponse(
            status="invalid",
            models=[],
            error=f"Network error: {exc}",
        )

    if response.status_code in (401, 403):
        error_detail = "Invalid API key"
        try:
            body = response.json()
            error_detail = body.get("error", {}).get("message", error_detail)
        except Exception:
            logger.debug("byok_error_body_parse_failed", exc_info=True)
        return BYOKValidateResponse(status="invalid", models=[], error=error_detail)

    if not response.is_success:
        logger.warning("Unexpected status %s from provider during BYOK validation", response.status_code)
        return BYOKValidateResponse(
            status="invalid",
            models=[],
            error=f"Provider returned HTTP {response.status_code}",
        )

    models: list[ModelInfo] = []
    try:
        data = response.json()
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if model_id:
                models.append(ModelInfo(id=model_id, name=model_id, provider=provider, context_window=None))
    except Exception as exc:
        logger.warning("Failed to parse models from provider response: %s", exc)
        return BYOKValidateResponse(status="valid", models=[], error=None)

    return BYOKValidateResponse(status="valid", models=models, error=None)


@router.get("/models/{provider}", response_model=list[ModelInfo])
async def get_provider_models(provider: str) -> list[ModelInfo]:
    catalog = _MODEL_CATALOG.get(provider.lower())
    if catalog is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No model catalog found for provider: {provider}",
        )
    return [
        ModelInfo(id=m["id"], name=m["name"], provider=m["provider"], context_window=m.get("context_window"))
        for m in catalog
    ]


@router.post("/discover-models", response_model=list[ModelInfo])
async def discover_models(request: BYOKValidateRequest) -> list[ModelInfo]:
    provider = request.provider.lower()
    cache_key = provider
    if cache_key in _model_cache:
        ts, models = _model_cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return models

    base_url = _get_base_url(provider)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {request.api_key}"},
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request timed out while fetching models",
        )
    except httpx.RequestError as exc:
        logger.warning("HTTP request error during model discovery: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Network error: {exc}",
        )

    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    if not response.is_success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider returned HTTP {response.status_code}",
        )

    filtered_models: list[ModelInfo] = []
    try:
        data = response.json()
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if model_id and _is_chat_model(model_id):
                filtered_models.append(ModelInfo(id=model_id, name=model_id, provider=provider, context_window=None))
    except Exception as exc:
        logger.warning("Failed to parse models from provider response: %s", exc)
        return []

    _model_cache[cache_key] = (time.time(), filtered_models)
    return filtered_models


@router.get("")
async def list_keys(
    user=Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    query = select(UserAPIKey).where(UserAPIKey.user_id == user.id)
    if workspace_id:
        query = query.where(
            (UserAPIKey.workspace_id == workspace_id) | (UserAPIKey.workspace_id.is_(None))
        )
    query = query.order_by(UserAPIKey.id)
    result = await db.execute(query)
    keys = result.scalars().all()
    return {
        "keys": [
            {
                "id": k.id,
                "provider": k.provider,
                "key_name": k.key_label or k.provider,
                "masked_key": _mask_key(k.encrypted_key),
                "base_url": k.base_url,
                "is_active": k.is_active,
                "models": k.get_models_list(),
                "created_at": k.created_at.isoformat() if k.created_at else "",
                "last_used_at": None,
            }
            for k in keys
        ]
    }


@router.post("")
async def add_key(
    data: dict,
    user=Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    # Phase 8.4: Check subscription tier allows API key generation
    from app.services.subscription_service import check_api_key_allowed
    limit_check = await check_api_key_allowed(db, user.id, workspace_id)
    if not limit_check.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=limit_check.reason,
        )

    from app.utils.encryption import encrypt_api_key
    api_key = data.get("api_key") or data.get("key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")
    encrypted = encrypt_api_key(api_key)
    db_key = UserAPIKey(
        user_id=user.id,
        workspace_id=workspace_id,
        provider=data.get("provider", "openai"),
        encrypted_key=encrypted,
        key_label=data.get("key_name") or data.get("label"),
        base_url=data.get("base_url"),
        is_active=True,
    )
    db.add(db_key)
    await db.flush()
    await db.refresh(db_key)
    return {
        "key": {
            "id": db_key.id,
            "provider": db_key.provider,
            "key_name": db_key.key_label or db_key.provider,
            "masked_key": _mask_key(db_key.encrypted_key),
            "base_url": db_key.base_url,
            "is_active": db_key.is_active,
            "models": db_key.get_models_list(),
            "created_at": db_key.created_at.isoformat() if db_key.created_at else "",
            "last_used_at": None,
        }
    }


@router.delete("/{key_id}")
async def delete_key(
    key_id: int,
    user=Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    query = select(UserAPIKey).where(UserAPIKey.id == key_id, UserAPIKey.user_id == user.id)
    if workspace_id:
        query = query.where(
            (UserAPIKey.workspace_id == workspace_id) | (UserAPIKey.workspace_id.is_(None))
        )
    result = await db.execute(query)
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    await db.delete(key)
    return {"detail": "Deleted"}


@router.post("/{key_id}/test")
async def test_key(
    key_id: int,
    user=Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    query = select(UserAPIKey).where(UserAPIKey.id == key_id, UserAPIKey.user_id == user.id)
    if workspace_id:
        query = query.where(
            (UserAPIKey.workspace_id == workspace_id) | (UserAPIKey.workspace_id.is_(None))
        )
    result = await db.execute(query)
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    # Test the key by calling the provider's models endpoint
    try:
        api_key = key.get_api_key()
        base_url = key.base_url or _PROVIDER_BASE_URLS.get(key.provider.lower(), _PROVIDER_BASE_URLS["openai"])
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code in (401, 403):
            return {"provider": key.provider, "key_name": key.key_label, "valid": False, "message": "Invalid API key"}
        if resp.is_success:
            return {"provider": key.provider, "key_name": key.key_label, "valid": True, "message": "Key is valid"}
        return {"provider": key.provider, "key_name": key.key_label, "valid": False, "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"provider": key.provider, "key_name": key.key_label, "valid": False, "message": str(e)}


@user_keys_router.get("")
async def user_list_keys(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_keys(user=user, db=db)


@user_keys_router.post("")
async def user_add_key(
    data: dict,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await add_key(data=data, user=user, db=db)


@user_keys_router.delete("/{key_id}")
async def user_delete_key(
    key_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await delete_key(key_id=key_id, user=user, db=db)


@user_keys_router.post("/{key_id}/test")
async def user_test_key(
    key_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await test_key(key_id=key_id, user=user, db=db)
