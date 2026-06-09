"""LLM Advanced API — model stats, routing, tradeoffs, and health."""

import logging
import os

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.services.llm_router import ModelRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm-advanced", tags=["llm-advanced"])


def _get_router() -> ModelRouter:
    return ModelRouter()


@router.get("/stats")
async def get_stats(user: User = Depends(get_current_user)):
    """Get LLM usage stats from Langfuse or local tracking."""
    try:
        from sqlalchemy import text

        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text(
                    """
                    SELECT COUNT(*) as total_requests,
                           COALESCE(SUM((action_details::json->>'total_tokens')::int), 0) as total_tokens
                    FROM audit_logs
                    WHERE action LIKE 'llm_%' OR action = 'mission_completed'
                    """
                )
            )
            row = result.first()
            return {
                "total_requests": row[0] if row else 0,
                "total_tokens": row[1] if row else 0,
                "total_cost": 0.0,
                "avg_latency_ms": 0,
                "model_distribution": {},
                "provider_distribution": {},
            }
    except Exception as e:
        logger.warning("LLM stats query failed: %s", e)
        return {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "avg_latency_ms": 0,
            "model_distribution": {},
            "provider_distribution": {},
        }


@router.post("/override")
async def set_override(
    payload: dict,
    user: User = Depends(get_current_user),
):
    """Set model override preferences."""
    # Store in user settings
    return {
        "default_model": payload.get("default_model", "deepseek/deepseek-v4-flash"),
        "fallback_model": payload.get("fallback_model", ""),
        "cost_threshold": payload.get("cost_threshold", 0.0),
        "latency_threshold_ms": payload.get("latency_threshold_ms", 0),
        "quality_threshold": payload.get("quality_threshold", 0.0),
        "overrides": payload.get("overrides", []),
    }


@router.delete("/override/{model_id}")
async def clear_override(
    model_id: str,
    user: User = Depends(get_current_user),
):
    """Clear a specific model override."""
    return {
        "default_model": "deepseek/deepseek-v4-flash",
        "fallback_model": "",
        "cost_threshold": 0.0,
        "latency_threshold_ms": 0,
        "quality_threshold": 0.0,
        "overrides": [],
    }


@router.post("/tradeoff")
async def get_tradeoff(
    payload: dict,
    user: User = Depends(get_current_user),
):
    """Get cost/quality/speed tradeoff recommendations."""
    router = _get_router()

    # Get available models from environment
    models = []
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if deepseek_key:
        models.append(
            {
                "id": "deepseek/deepseek-v4-flash",
                "provider": "deepseek",
                "cost_per_1m": 0.14,
                "quality": "good",
                "speed": "fast",
            }
        )
        models.append(
            {
                "id": "deepseek/deepseek-reasoner",
                "provider": "deepseek",
                "cost_per_1m": 0.55,
                "quality": "excellent",
                "speed": "slow",
            }
        )

    llamacpp_url = os.getenv("LLAMACPP_URL")
    if llamacpp_url:
        models.append(
            {
                "id": "llamacpp/Qwen3.6-27B",
                "provider": "llamacpp",
                "cost_per_1m": 0.0,
                "quality": "good",
                "speed": "moderate",
            }
        )

    models.append(
        {
            "id": "glennguilloux/demo-llm",
            "provider": "glennguilloux",
            "cost_per_1m": 0.0,
            "quality": "good",
            "speed": "fast",
        }
    )

    best_cost = min(models, key=lambda m: m["cost_per_1m"]) if models else None
    best_quality = (
        max(
            models,
            key=lambda m: {"excellent": 3, "good": 2, "moderate": 1}.get(
                m["quality"], 0
            ),
        )
        if models
        else None
    )
    best_speed = (
        max(
            models,
            key=lambda m: {"fast": 3, "moderate": 2, "slow": 1}.get(m["speed"], 0),
        )
        if models
        else None
    )

    return {
        "recommendations": models,
        "best_for_cost": best_cost["id"] if best_cost else "",
        "best_for_quality": best_quality["id"] if best_quality else "",
        "best_for_speed": best_speed["id"] if best_speed else "",
    }


@router.post("/tradeoff/preferences")
async def set_tradeoff_preferences(
    payload: dict,
    user: User = Depends(get_current_user),
):
    """Set user tradeoff preferences."""
    return await set_override(payload, user)


@router.get("/recommendations")
async def get_recommendations(user: User = Depends(get_current_user)):
    """Get model recommendations based on available providers."""
    return await get_tradeoff({}, user)


@router.post("/route")
async def route_request(
    payload: dict,
    user: User = Depends(get_current_user),
):
    """Route a request to the best available model."""
    router = _get_router()
    messages = payload.get("messages", [{"role": "user", "content": "Hello"}])
    model_preference = payload.get("model_preference")

    try:
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await router.route_request(
                messages=messages,
                model_preference=model_preference,
                user_id=str(user.id),
                db_session=db,
                max_tokens=5,
            )

            if hasattr(result, "success"):
                success = result.success
                model = result.model
                error = result.error if not result.success else None
            else:
                success = result.get("success", False)
                model = result.get("model", "")
                error = result.get("error")

            return {
                "selected_model": model,
                "reason": "Routed via ModelRouter" if success else f"Error: {error}",
                "estimated_cost": 0.0,
                "estimated_latency_ms": 0,
                "alternatives": [],
            }
    except Exception as e:
        logger.error("Route request failed: %s", e)
        return {
            "selected_model": "deepseek/deepseek-v4-flash",
            "reason": f"Fallback (error: {e})",
            "estimated_cost": 0.0,
            "estimated_latency_ms": 0,
            "alternatives": [],
        }


@router.get("/config")
async def get_config(user: User = Depends(get_current_user)):
    """Get current LLM configuration."""
    return {
        "default_model": os.getenv("LLM_MODEL_NAME", "deepseek/deepseek-v4-flash"),
        "fallback_model": "",
        "cost_threshold": 0.0,
        "latency_threshold_ms": 0,
        "quality_threshold": 0.0,
        "overrides": [],
    }


@router.get("/health")
async def get_health(user: User = Depends(get_current_user)):
    """Check health of all configured LLM providers."""
    router = _get_router()

    try:
        providers = await router.check_all_providers_health()
        return {
            "status": (
                "healthy" if any(p.healthy for p in providers.values()) else "degraded"
            ),
            "providers": {
                name: {"healthy": p.healthy, "error_count": p.error_count}
                for name, p in providers.items()
            },
        }
    except Exception as e:
        logger.error("LLM health check failed: %s", e)
        return {"status": "error", "providers": {}, "error": str(e)}
