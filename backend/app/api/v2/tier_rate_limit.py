"""Tier-aware rate limiting for API v2.

Reads the user's workspace subscription tier to determine per-endpoint rate limits.
Falls back to free-tier defaults when no subscription exists.

Uses a MODULE-LEVEL shared sliding window so the window state persists across
requests (unlike delegating to rate_limit() which creates a fresh inmem dict
per call). Tier resolution from DB is cached on the user object.

Usage:
    from app.api.v2.tier_rate_limit import tier_rate_limit

    @router.post("/missions")
    async def create_mission(
        _rate = Depends(tier_rate_limit("mission:create")),
    ):
        if isinstance(_rate, JSONResponse):
            return _rate
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog
from fastapi import Depends, Request

from app.api.deps import get_current_user
from app.api.v2.rate_limit import _build_429, _inmem_allowed

if TYPE_CHECKING:
    from fastapi.responses import JSONResponse

    from app.models.user import User

logger = structlog.get_logger(__name__)

# ── Tier multipliers ──────────────────────────────────────────────────────────

_TIER_MULTIPLIERS: dict[str, float] = {
    "free": 1.0,
    "starter": 2.0,
    "pro": 5.0,
    "business": 10.0,
    "enterprise": 20.0,
}

# Endpoint category -> base rate (requests per window) for free tier
_BASE_LIMITS: dict[str, int] = {
    "mission:create": 30,
    "mission:update": 30,
    "mission:delete": 15,
    "mission:execute": 20,
    "mission:abort": 15,
    "mission:plan": 20,
    "agent:create": 10,
    "agent:update": 10,
    "chat:message": 30,
    "chat:stream": 10,
    "search": 20,
    "integration:execute": 15,
    "_DEFAULT": 60,
}

_WINDOW_SECONDS = 60
_BURST_MULTIPLIER = 2

# ── Module-level shared sliding window ────────────────────────────────────────
# This dict persists across requests within the same process.
# Periodic cleanup prevents unbounded growth under high load.
_shared_windows: dict[str, list[float]] = {}
_cleanup_counter: int = 0
_CLEANUP_EVERY = 500  # Clean up every N rate limit checks


def _maybe_cleanup_windows() -> None:
    """Periodically prune stale entries from the shared windows dict."""
    global _cleanup_counter
    _cleanup_counter += 1
    if _cleanup_counter < _CLEANUP_EVERY:
        return
    _cleanup_counter = 0
    now = time.monotonic()
    stale_keys = [k for k, v in _shared_windows.items() if not v or v[-1] < now - 300]
    for k in stale_keys:
        del _shared_windows[k]
    if stale_keys:
        logger.debug("tier_rate_limit_cleanup", pruned=len(stale_keys))


# ── Tier resolution ──────────────────────────────────────────────────────────


def _get_cached_tier(user: User) -> str | None:
    """Read tier from the user object if it was already resolved."""
    return getattr(user, "_effective_tier", None)


async def _resolve_tier_from_db(user: User) -> str:
    """Look up the user's subscription tier from the database."""
    try:
        from sqlalchemy import select

        from app.database import AsyncSessionLocal
        from app.models.subscription_models import SubscriptionTier, UserSubscription
        from app.models.workspace_models import Workspace, WorkspaceMember

        async with AsyncSessionLocal() as session:
            # Check active subscription
            sub_result = await session.execute(
                select(UserSubscription)
                .where(UserSubscription.user_id == user.id)
                .where(UserSubscription.status == "active")
                .order_by(UserSubscription.id.desc())
                .limit(1)
            )
            sub = sub_result.scalar_one_or_none()
            if sub:
                tier_result = await session.execute(select(SubscriptionTier).where(SubscriptionTier.id == sub.tier_id))
                tier = tier_result.scalar_one_or_none()
                if tier:
                    return tier.name.lower()

            # Fall back to workspace plan
            member_result = await session.execute(
                select(WorkspaceMember).where(WorkspaceMember.user_id == user.id).limit(1)
            )
            member = member_result.scalar_one_or_none()
            if member:
                ws_result = await session.execute(select(Workspace).where(Workspace.id == member.workspace_id))
                ws = ws_result.scalar_one_or_none()
                if ws and ws.plan:
                    return ws.plan.lower()

    except Exception:
        logger.debug("tier_resolution_failed", user_id=user.id, exc_info=True)

    return "free"


# ── Dependency factory ────────────────────────────────────────────────────────


def tier_rate_limit(
    endpoint_key: str,
    *,
    limit: int | None = None,
    window_seconds: int | None = None,
):
    """FastAPI dependency factory for tier-aware rate limiting.

    Resolves the user's subscription tier, computes the effective limit,
    and checks a MODULE-LEVEL shared sliding window. The window state
    persists across requests within the same process.
    """
    base = limit or _BASE_LIMITS.get(endpoint_key, _BASE_LIMITS["_DEFAULT"])
    window = window_seconds or _WINDOW_SECONDS

    async def _check(
        request: Request,
        user: User = Depends(get_current_user),
    ) -> JSONResponse | None:
        # Resolve tier (cached on user object if available, else DB lookup)
        tier_name = _get_cached_tier(user)
        if tier_name is None:
            tier_name = await _resolve_tier_from_db(user)
            # Cache on user object so subsequent calls in same request skip DB
            user._effective_tier = tier_name  # type: ignore[attr-defined]

        multiplier = _TIER_MULTIPLIERS.get(tier_name, 1.0)
        effective_limit = int(base * multiplier)
        burst_max = effective_limit * _BURST_MULTIPLIER

        # Build a user-specific key for this endpoint
        key = f"rl:v2:tier:{endpoint_key}:user:{user.id}"

        # Periodic cleanup to prevent unbounded memory growth
        _maybe_cleanup_windows()

        # Check the module-level shared window
        allowed, remaining, retry_after = _inmem_allowed(
            _shared_windows,
            key,
            effective_limit,
            window,
            _BURST_MULTIPLIER,
        )

        # Store state on request.state for the RateLimitHeadersMiddleware
        request.state.rate_limit_limit = effective_limit
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_reset = int(time.time()) + window

        if not allowed:
            return _build_429(effective_limit, window, retry_after)

        return None

    return _check
