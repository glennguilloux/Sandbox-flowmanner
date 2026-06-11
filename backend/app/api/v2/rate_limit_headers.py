"""Rate-limit response headers middleware for API v2.

Injects X-RateLimit-Limit, X-RateLimit-Remaining, and X-RateLimit-Reset
headers into every v2 response so clients can self-throttle.

For rate-limited responses (429), also adds Retry-After.
Reads rate limit state from request.state set by the rate_limit dependency.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RateLimitHeadersMiddleware(BaseHTTPMiddleware):
    """Injects rate limit headers into all /api/v2/* responses.

    This middleware reads state set by the rate_limit/tier_rate_limit
    dependencies (request.state.rate_limit_*) and adds standard
    rate-limit response headers.

    For requests that don't go through a rate-limit dependency,
    it adds default "unlimited" headers based on the user's tier.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Only apply to v2 endpoints
        if not request.url.path.startswith("/api/v2"):
            return response

        # Read rate limit state set by the dependency
        remaining = getattr(request.state, "rate_limit_remaining", None)
        limit = getattr(request.state, "rate_limit_limit", None)
        reset_ts = getattr(request.state, "rate_limit_reset", None)

        # If no rate limit dependency ran, don't add headers
        # (e.g., unauthenticated endpoints like /auth/login)
        if limit is None:
            return response

        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining or 0))
        response.headers["X-RateLimit-Reset"] = str(reset_ts or int(time.time()) + 60)

        # For 429 responses, ensure Retry-After is set
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if not retry_after:
                response.headers["Retry-After"] = str(max(1, (reset_ts or int(time.time()) + 60) - int(time.time())))

        return response
