"""Auth v3 cookie helpers — set, clear, and read httpOnly refresh token cookies.

Used by the auth route handlers to set/clear the refresh_token httpOnly cookie
on login, register, refresh, and logout responses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from fastapi import Request
    from fastapi.responses import Response


def set_refresh_cookie(response: Response, token: str):
    """Set httpOnly refresh token cookie on response.

    Cookie attributes:
    - HttpOnly: prevents JavaScript access (XSS protection)
    - Secure: only sent over HTTPS (production only)
    - SameSite=Strict: prevents CSRF attacks
    - Path=/api/v3/auth: only sent to v3 auth endpoints (not every API call)
    """
    max_age = settings.JWT_REFRESH_TOKEN_EXPIRES  # seconds (604800 = 7 days)
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=settings.AUTH_V3_COOKIE_SECURE,  # True in production
        samesite="strict",
        path="/api/v3/auth",
        max_age=max_age,
        domain=settings.AUTH_V3_COOKIE_DOMAIN,  # None in dev, ".flowmanner.com" in prod
    )


def clear_refresh_cookie(response: Response):
    """Clear the refresh token cookie (logout)."""
    response.delete_cookie(
        key="refresh_token",
        path="/api/v3/auth",
        domain=settings.AUTH_V3_COOKIE_DOMAIN,
        secure=settings.AUTH_V3_COOKIE_SECURE,
        httponly=True,
    )


def get_refresh_from_request(request: Request) -> str | None:
    """Get refresh token from httpOnly cookie (primary) or request state.

    Resolution order:
    1. AuthCookieMiddleware → request.state.refresh_token_cookie
    2. Direct cookie read (fallback for test environments without middleware)
    """
    # Primary: httpOnly cookie (extracted by AuthCookieMiddleware)
    cookie_token: str | None = getattr(request.state, "refresh_token_cookie", None)
    if cookie_token:
        return cookie_token
    # Fallback: direct cookie read (test env, no middleware)
    return request.cookies.get("refresh_token")
