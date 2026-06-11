"""
OIDC SSO Login Routes

Implements the OIDC Authorization Code Flow endpoints:
- GET /auth/oidc/providers - List available OIDC providers
- GET /auth/oidc/{provider}/login - Initiate OIDC login (with PKCE)
- GET /auth/oidc/{provider}/callback - Handle OIDC callback
- POST /auth/oidc/{provider}/token - Exchange code for tokens (SPA endpoint)
- GET /auth/oidc/{provider}/logout - Logout from OIDC provider
- POST /auth/oidc/{provider}/refresh - Refresh OIDC tokens
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.oidc_service import (
    authenticate_with_oidc,
    generate_nonce,
    generate_state,
    get_authorization_url,
    list_providers,
    logout_oidc,
    refresh_oidc_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oidc", tags=["OIDC SSO"])


# Pydantic models
class OIDCProviderInfo(BaseModel):
    name: str
    display_name: str
    issuer: str


class OIDCLoginResponse(BaseModel):
    authorization_url: str
    state: str
    nonce: str
    code_verifier: str


class OIDCCallbackResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    email: str
    username: str


class OIDCLogoutResponse(BaseModel):
    end_session_url: str | None


class OIDCRefreshRequest(BaseModel):
    provider: str


@router.get("/providers", response_model=list[OIDCProviderInfo])
async def get_providers(db: AsyncSession = Depends(get_db)):
    """
    List available OIDC providers.

    Returns a list of configured OIDC providers that users can use for SSO login.
    """
    providers = await list_providers(db)
    return [OIDCProviderInfo(**p) for p in providers]


@router.get("/{provider}/login", response_model=OIDCLoginResponse)
async def oidc_login(
    provider: str,
    request: Request,
    redirect_uri: str | None = Query(None, description="Custom redirect URI after callback"),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate OIDC login flow with PKCE.

    Generates the authorization URL with PKCE challenge and returns it along with
    state/nonce. The frontend should redirect the user to the authorization_url.

    Query Parameters:
    - redirect_uri: Optional custom redirect URI for after authentication
    """
    # Build the callback URL
    base_url = str(request.base_url).rstrip("/")
    callback_uri = f"{base_url}/api/auth/oidc/{provider}/callback"

    # Use custom redirect_uri if provided, otherwise use default
    if redirect_uri:
        import base64
        import json

        state_data = {
            "redirect_uri": redirect_uri,
            "state": generate_state(),
        }
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()
    else:
        state = generate_state()

    nonce = generate_nonce()

    try:
        result = await get_authorization_url(
            db=db,
            provider_name=provider,
            redirect_uri=callback_uri,
            state=state,
            nonce=nonce,
        )
        return OIDCLoginResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to initiate OIDC login for %s: %s", provider, e)
        raise HTTPException(status_code=500, detail="Failed to initiate OIDC login")


@router.get("/{provider}/callback")
async def oidc_callback(
    provider: str,
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle OIDC callback after authentication.

    This endpoint is called by the OIDC provider after the user authenticates.
    It validates the state parameter, exchanges the authorization code for tokens,
    and creates/finds the user.

    Query Parameters:
    - code: Authorization code from the OIDC provider
    - state: State parameter for CSRF protection
    - error: Error code if authentication failed
    - error_description: Human-readable error description
    """
    # Handle error from provider
    if error:
        logger.warning("OIDC callback error: %s - %s", error, error_description)
        frontend_url = _get_frontend_error_url(error, error_description)
        return RedirectResponse(url=frontend_url, status_code=302)

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter")

    # Build the callback URL (must match what was sent in the authorization request)
    base_url = str(request.base_url).rstrip("/")
    callback_uri = f"{base_url}/api/auth/oidc/{provider}/callback"

    try:
        # Authenticate with OIDC (includes state validation and PKCE)
        result = await authenticate_with_oidc(
            db=db,
            provider_name=provider,
            code=code,
            redirect_uri=callback_uri,
            state=state,
        )

        # Build redirect URL with tokens
        redirect_url = _build_success_redirect(result, state)
        return RedirectResponse(url=redirect_url, status_code=302)

    except ValueError as e:
        logger.error("OIDC authentication failed: %s", e)
        frontend_url = _get_frontend_error_url("authentication_failed", str(e))
        return RedirectResponse(url=frontend_url, status_code=302)
    except Exception as e:
        logger.error("OIDC callback error: %s", e, exc_info=True)
        frontend_url = _get_frontend_error_url("server_error", "An unexpected error occurred")
        return RedirectResponse(url=frontend_url, status_code=302)


@router.post("/{provider}/token", response_model=OIDCCallbackResponse)
async def oidc_token_exchange(
    provider: str,
    code: str,
    redirect_uri: str,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange authorization code for tokens (API endpoint).

    This is an alternative to the callback endpoint for SPAs that handle
    the redirect client-side and want to exchange the code via API.

    Request Body:
    - code: Authorization code from the OIDC provider
    - redirect_uri: The redirect URI used in the authorization request
    - state: State parameter for CSRF protection
    """
    try:
        result = await authenticate_with_oidc(
            db=db,
            provider_name=provider,
            code=code,
            redirect_uri=redirect_uri,
            state=state,
        )
        return OIDCCallbackResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("OIDC token exchange failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Token exchange failed")


@router.get("/{provider}/logout", response_model=OIDCLogoutResponse)
async def oidc_logout(
    provider: str,
    request: Request,
    id_token_hint: str | None = Query(None, description="ID token hint for logout"),
    db: AsyncSession = Depends(get_db),
):
    """
    Logout from OIDC provider.

    Clears local tokens and returns the provider's end_session_url for redirect.

    Query Parameters:
    - id_token_hint: Optional ID token to include in logout request
    """
    # In a real implementation, get user_id from the JWT token
    # For now, we'll need the user to be authenticated
    # This is a simplified version - in production, use proper auth middleware

    try:
        # Get user from auth header (simplified)
        user_id = _get_user_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")

        result = await logout_oidc(
            db=db,
            provider_name=provider,
            user_id=user_id,
            id_token_hint=id_token_hint,
        )

        return OIDCLogoutResponse(end_session_url=result.get("end_session_url"))

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("OIDC logout failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Logout failed")


@router.post("/{provider}/refresh")
async def oidc_refresh(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh OIDC tokens.

    Uses the stored refresh token to get new access/refresh tokens from the provider.
    """
    try:
        user_id = _get_user_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")

        result = await refresh_oidc_token(
            db=db,
            provider_name=provider,
            user_id=user_id,
        )

        if not result:
            raise HTTPException(status_code=400, detail="Token refresh not possible")

        return {
            "access_token": result.get("access_token"),
            "refresh_token": result.get("refresh_token"),
            "token_type": "bearer",
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("OIDC token refresh failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Token refresh failed")


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _build_success_redirect(result: dict, state: str) -> str:
    """Build redirect URL with tokens for successful authentication."""
    import base64
    import json

    # Try to extract custom redirect_uri from state
    try:
        state_data = json.loads(base64.urlsafe_b64decode(state))
        frontend_base = state_data.get("redirect_uri", "")
    except Exception:
        frontend_base = ""

    if not frontend_base:
        frontend_base = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Build callback URL with tokens
    params = (
        f"access_token={result['access_token']}&refresh_token={result['refresh_token']}&user_id={result['user_id']}"
    )
    separator = "&" if "?" in frontend_base else "?"
    return f"{frontend_base}{separator}{params}"


def _get_frontend_error_url(error: str, description: str | None = None) -> str:
    """Build frontend URL with error information."""
    frontend_base = os.getenv("FRONTEND_URL", "http://localhost:3000")
    params = f"error={error}"
    if description:
        params += f"&error_description={description}"
    separator = "&" if "?" in frontend_base else "?"
    return f"{frontend_base}{separator}{params}"


def _get_user_from_request(request: Request) -> int | None:
    """
    Extract user ID from request.

    In production, this should use proper JWT validation middleware.
    This is a simplified version for the OIDC endpoints.
    """
    from app.services.auth_service import decode_access_token

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]
    user_id = decode_access_token(token)
    return int(user_id) if user_id else None
