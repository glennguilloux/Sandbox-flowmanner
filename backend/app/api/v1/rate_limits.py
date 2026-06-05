"""Rate limit status and analytics API endpoint."""

from fastapi import APIRouter

from app.api.middleware.rate_limit import get_rate_limit_status

router = APIRouter(prefix="/rate-limits", tags=["rate-limits"])


@router.get("/status")
async def rate_limit_status():
    """Return current rate limit configuration, tier settings, and abuse detection analytics.

    Shows:
    - Per-endpoint rate limits (max_requests, window, key_type)
    - Tier multipliers (admin bypass, pro 2x, free 1x)
    - Hit counts per endpoint (how many 429s returned)
    - Backend type (Redis or in-memory)
    """
    return get_rate_limit_status()
