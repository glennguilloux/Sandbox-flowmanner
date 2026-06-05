"""Auth cookie middleware — extracts httpOnly refresh token for v3 auth endpoints.

Must be registered BEFORE CORS middleware in main_fastapi.py because Starlette
executes middleware in REVERSE order of registration. If CORS runs after the
cookie middleware, cookies won't be readable on cross-origin requests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from fastapi import Request


class AuthCookieMiddleware(BaseHTTPMiddleware):
    """Extracts the refresh token from the 'refresh_token' httpOnly cookie
    and stores it in request.state.refresh_token_cookie.

    Cookie attributes: HttpOnly, Secure, SameSite=Strict, Path=/api/v3/auth
    """

    COOKIE_NAME = "refresh_token"

    async def dispatch(self, request: Request, call_next):
        # Extract cookie for /api/v3/auth/sessions/refresh
        cookie_value = request.cookies.get(self.COOKIE_NAME)
        request.state.refresh_token_cookie = cookie_value
        response = await call_next(request)
        return response
