"""Auth v3 OIDC routes — workspace-scoped OIDC SSO login + callback.

Wires the v3 OIDC endpoints to the existing :mod:`oidc_service` which
implements the full OIDC Authorization Code Flow with PKCE, discovery,
token exchange, user info, and session creation.

Feature-flagged behind ``AUTH_V3_OIDC`` (404 when disabled).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from app.api.deps import get_current_user
from app.api.v3.auth_cookies import set_refresh_cookie
from app.api.v3.base import ok
from app.database import get_db
from app.schemas.auth_v3 import OIDCLoginRequest  # FastAPI needs at runtime for body parsing

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["v3-auth-oidc"])

# ── Allowed providers ────────────────────────────────────────────────────────
# Only providers with a row in oidc_providers (is_active=true) are accepted.
# The provider name is validated against the DB in the login handler, so
# arbitrary path traversal is impossible.

_FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


async def _require_oidc_enabled(db: AsyncSession) -> None:
    """404 if AUTH_V3_OIDC feature flag is off."""
    result = await db.execute(text("SELECT enabled_globally FROM feature_flags WHERE key = 'AUTH_V3_OIDC'"))
    if not result.scalar():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not found",
        )


# ── GET /auth/oidc/providers ─────────────────────────────────────────────────


@router.get("/oidc/providers", status_code=status.HTTP_200_OK)
async def list_oidc_providers(
    db: AsyncSession = Depends(get_db),
):
    """List active OIDC providers available for SSO login.

    Returns:
        200: { data: [{ name, display_name, issuer }], ... }
    """
    await _require_oidc_enabled(db)

    from app.services.oidc_service import list_providers

    providers = await list_providers(db)
    return ok(providers)


# ── POST /auth/oidc/{provider}/login ─────────────────────────────────────────


@router.post("/oidc/{provider}/login", status_code=status.HTTP_200_OK)
async def oidc_login(
    provider: str,
    payload: OIDCLoginRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initiate OIDC login flow with PKCE.

    Generates the authorization URL with PKCE challenge and returns it
    along with state.  The frontend should redirect the user to the
    ``authorization_url``.

    Returns:
        200: { data: { authorization_url, state }, ... }
        400: Unknown or inactive provider
    """
    await _require_oidc_enabled(db)

    from app.services.oidc_service import get_authorization_url

    # Build callback URL — must match what the OIDC provider has registered
    base_url = str(request.base_url).rstrip("/")
    callback_uri = f"{base_url}/api/v3/auth/oidc/{provider}/callback"

    try:
        result = await get_authorization_url(
            db=db,
            provider_name=provider,
            redirect_uri=callback_uri,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception:
        logger.exception("Failed to initiate OIDC login for %s", provider)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate OIDC login",
        )

    return ok(
        {
            "authorization_url": result["authorization_url"],
            "state": result["state"],
        }
    )


# ── GET /auth/oidc/{provider}/callback ───────────────────────────────────────


@router.get("/oidc/{provider}/callback", status_code=status.HTTP_302_FOUND)
async def oidc_callback(
    provider: str,
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Handle OIDC callback after authentication.

    Exchanges the authorization code for tokens, finds or creates the user,
    creates a v3 session with httpOnly cookie, and redirects to the frontend.

    Returns:
        302: Redirect to frontend with session cookie set
        400: Missing code/state or authentication failure
    """
    await _require_oidc_enabled(db)

    # Handle error from provider
    if error:
        logger.warning("OIDC callback error: %s - %s", error, error_description)
        return RedirectResponse(
            url=f"{_FRONTEND_URL}?error={error}&error_description={error_description}",
            status_code=status.HTTP_302_FOUND,
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code",
        )
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing state parameter",
        )

    # Build callback URI (must match what was sent in the authorization request)
    base_url = str(request.base_url).rstrip("/")
    callback_uri = f"{base_url}/api/v3/auth/oidc/{provider}/callback"

    try:
        from app.services.oidc_service import authenticate_with_oidc

        result = await authenticate_with_oidc(
            db=db,
            provider_name=provider,
            code=code,
            redirect_uri=callback_uri,
            state=state,
        )
    except ValueError as e:
        logger.error("OIDC authentication failed: %s", e)
        return RedirectResponse(
            url=f"{_FRONTEND_URL}?error=authentication_failed&error_description={e}",
            status_code=status.HTTP_302_FOUND,
        )
    except Exception:
        logger.exception("OIDC callback error")
        return RedirectResponse(
            url=f"{_FRONTEND_URL}?error=server_error",
            status_code=status.HTTP_302_FOUND,
        )

    # Create a v3 session with httpOnly cookie
    from sqlalchemy import select

    from app.api.utils import get_client_ip, get_device_name, parse_browser, parse_os
    from app.models.user import User as UserModel
    from app.services.auth_v3_service import create_access_token, create_session

    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")

    user_result = await db.execute(select(UserModel).where(UserModel.id == result["user_id"]))
    user_obj = user_result.scalar_one_or_none()
    if not user_obj:
        return RedirectResponse(
            url=f"{_FRONTEND_URL}?error=user_not_found",
            status_code=status.HTTP_302_FOUND,
        )

    session, refresh_token = await create_session(
        db,
        user_obj,
        ip_address=ip,
        device_name=get_device_name(request),
        device_os=parse_os(ua),
        browser=parse_browser(ua),
    )

    access_token = create_access_token(
        user_obj.id,
        session_id=session.id,
        role=user_obj.role,
    )

    # Redirect to frontend with tokens in query params
    redirect_url = f"{_FRONTEND_URL}" f"?access_token={access_token}" f"&session_id={session.id}"

    resp = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    set_refresh_cookie(resp, refresh_token)
    return resp


# ── POST /auth/oidc/{provider}/logout ────────────────────────────────────────


@router.post("/oidc/{provider}/logout", status_code=status.HTTP_200_OK)
async def oidc_logout(
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout from OIDC provider.

    Clears local OIDC tokens and returns the provider's end_session_url
    for the frontend to redirect to.

    Returns:
        200: { data: { end_session_url }, ... }
    """
    await _require_oidc_enabled(db)

    from app.services.oidc_service import logout_oidc

    try:
        result = await logout_oidc(
            db=db,
            provider_name=provider,
            user_id=user.id,
        )
        return ok({"end_session_url": result.get("end_session_url")})
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
