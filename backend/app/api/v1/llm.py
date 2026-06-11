from __future__ import annotations

import os
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_user, get_current_user_optional
from app.database import get_db
from app.services.llm_router import LLMRouteResult, ModelRouter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(tags=["llm"])


class ModelInfo(BaseModel):
    name: str
    provider: str
    is_default: bool = False


class ProviderHealth(BaseModel):
    name: str
    healthy: bool = True
    error_count: int = 0


class TestRequest(BaseModel):
    message: str = "Hello, this is a test."
    model: str | None = None


class TestResponse(BaseModel):
    success: bool
    content: str = ""
    model: str = ""
    token_count: int = 0
    error: str = ""


@router.get("/models", response_model=list[ModelInfo])
async def list_models():
    from app.services.chat_service import PROVIDER_MAP

    provider_models = {
        "deepseek": ["deepseek-v4-flash"],
        "llamacpp": ["Qwen3.6-27B-Q5_K_M-mtp.gguf"],
        "glennguilloux": ["demo-llm"],
    }

    models = []
    for provider_id, (_base_url, key_env) in PROVIDER_MAP.items():
        api_key = os.getenv(key_env) if key_env else "no-key-needed"
        if key_env and (
            not api_key or api_key in ("", "sk-no-key-required", "sk-xxx", "sk-or-v1-your-openrouter-api-key")
        ):
            continue
        for model_name in provider_models.get(provider_id, []):
            models.append(
                ModelInfo(
                    name=f"{provider_id}/{model_name}",
                    provider=provider_id,
                    is_default=(provider_id == "deepseek" and model_name == "deepseek-v4-flash"),
                )
            )
    return models


class FrontendModelInfo(BaseModel):
    model_id: str
    display_name: str
    status: str = "available"
    context_length: int = 0
    vram_usage_gb: float | None = None
    quantization: str | None = None
    provider: str | None = None
    description: str | None = None
    is_byok: bool = False


class ModelListResponse(BaseModel):
    models: list[FrontendModelInfo]
    total: int


@router.get("/models/frontend", response_model=ModelListResponse)
async def list_models_frontend(
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    from app.models.byok_models import UserAPIKey
    from app.services.chat_service import PROVIDER_MAP

    provider_models = {
        "deepseek": ["deepseek-v4-flash"],
        "llamacpp": ["Qwen3.6-27B-Q5_K_M-mtp.gguf"],
        "glennguilloux": ["demo-llm"],
    }

    model_context_lengths = {
        "deepseek-v4-flash": 1000000,
        "Qwen3.6-27B-Q5_K_M-mtp.gguf": 32768,
        "demo-llm": 128000,
    }

    models = []
    # ── Platform models ──
    for provider_id, (_base_url, key_env) in PROVIDER_MAP.items():
        api_key = os.getenv(key_env) if key_env else "no-key-needed"
        if key_env and (
            not api_key or api_key in ("", "sk-no-key-required", "sk-xxx", "sk-or-v1-your-openrouter-api-key")
        ):
            continue
        for model_name in provider_models.get(provider_id, []):
            full_name = f"{provider_id}/{model_name}"
            context_len = model_context_lengths.get(model_name, 0)
            models.append(
                FrontendModelInfo(
                    model_id=full_name,
                    display_name=model_name,
                    status="available",
                    context_length=context_len,
                    provider=provider_id,
                    description=f"{model_name} via {provider_id}",
                )
            )

    # ── BYOK models ──
    if user and user.id:
        result = await db.execute(
            select(UserAPIKey).where(UserAPIKey.user_id == user.id).where(UserAPIKey.is_active == True)
        )
        byok_keys = result.scalars().all()
        for key in byok_keys:
            key_models = key.get_models_list()
            if key_models:
                for model_id in key_models:
                    # Don't duplicate if already in platform models
                    if not any(m.model_id == model_id for m in models):
                        models.append(
                            FrontendModelInfo(
                                model_id=model_id,
                                display_name=model_id.split("/")[-1],
                                status="available",
                                provider=key.provider,
                                description=f"Your {key.provider.upper()} key · {key.key_label or 'BYOK'}",
                                is_byok=True,
                            )
                        )
            else:
                # User has a key but no specific models — show the provider
                wildcard = f"{key.provider}/*"
                if not any(m.model_id == wildcard for m in models):
                    models.append(
                        FrontendModelInfo(
                            model_id=wildcard,
                            display_name=f"All {key.provider} models",
                            status="available",
                            provider=key.provider,
                            description=f"Your {key.provider.upper()} key · {key.key_label or 'BYOK'}",
                            is_byok=True,
                        )
                    )

    return ModelListResponse(models=models, total=len(models))


@router.get("/providers", response_model=list[ProviderHealth])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    model_router = ModelRouter(db_session=db, user_id=str(user.id))
    health = await model_router.check_all_providers_health()
    return [
        ProviderHealth(
            name=s.name,
            healthy=s.healthy,
            error_count=s.error_count,
        )
        for s in health.values()
    ]


@router.post("/test", response_model=TestResponse)
async def test_llm(
    payload: TestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    model_router = ModelRouter(db_session=db, user_id=str(user.id))
    messages = [{"role": "user", "content": payload.message}]
    result: LLMRouteResult = await model_router.route_request(messages, payload.model)

    return TestResponse(
        success=result.success,
        content=result.content[:500] if result.content else "",
        model=result.model,
        token_count=result.usage.get("total_tokens", 0),
        error=result.error,
    )
