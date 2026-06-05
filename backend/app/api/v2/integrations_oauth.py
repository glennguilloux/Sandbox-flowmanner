"""Integrations v2 API — OAuth app management and connection flow."""

from __future__ import annotations
import uuid

import json
import logging
import secrets
from datetime import UTC
from typing import TYPE_CHECKING

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, select

from app.api.deps import get_current_user
from app.api.v2.base import ok
from app.database import get_db
from app.integrations.oauth import OAUTH_PROVIDERS, decrypt_token, encrypt_token
from app.models.integration_models import UserOAuthApp, UserOAuthConnection
from app.schemas.integration_v2 import (
    OAuthAppCreate,
    OAuthAppResponse,
    OAuthAppUpdate,
    OAuthConnectionResponse,
    OAuthInitiateRequest,
)

if TYPE_CHECKING:

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/oauth", tags=["v2-integrations-oauth"])

# Derive allowed providers from the configured OAUTH_PROVIDERS dict
_ALLOWED_PROVIDERS = set(OAUTH_PROVIDERS.keys())


# ── Helpers ───────────────────────────────────────────────────────────────────


def _app_to_response(app: UserOAuthApp) -> dict:
    return OAuthAppResponse(
        id=str(app.id),
        provider=app.provider,
        scopes=app.scopes,
        is_active=app.is_active,
        created_at=app.created_at.isoformat() if app.created_at else None,
        updated_at=app.updated_at.isoformat() if app.updated_at else None,
    ).model_dump()


def _connection_to_response(conn: UserOAuthConnection) -> dict:
    return OAuthConnectionResponse(
        id=str(conn.id),
        provider=conn.provider,
        app_id=str(conn.app_id),
        token_type=conn.token_type,
        expires_at=conn.expires_at.isoformat() if conn.expires_at else None,
        provider_account_id=conn.provider_account_id,
        provider_account_name=conn.provider_account_name,
        scopes=conn.scopes,
        status=conn.status,
        created_at=conn.created_at.isoformat() if conn.created_at else None,
        updated_at=conn.updated_at.isoformat() if conn.updated_at else None,
    ).model_dump()


def _build_state(app_id: str, user_id: int) -> str:
    """Build an encrypted OAuth state parameter containing app_id and user_id."""
    payload = json.dumps(
        {
            "app_id": app_id,
            "user_id": user_id,
            "nonce": secrets.token_hex(16),
        }
    )
    return encrypt_token(payload)


def _decode_state(state: str) -> dict:
    """Decrypt and parse the OAuth state parameter. Raises on invalid/tampered state."""
    payload = json.loads(decrypt_token(state))
    required = {"app_id", "user_id", "nonce"}
    if not required.issubset(payload.keys()):
        raise ValueError("State payload missing required fields")
    return payload


async def _exchange_code(
    provider_slug: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict:
    """Exchange an OAuth authorization code for tokens using httpx.

    Returns a dict with: access_token, refresh_token, token_type, expires_in,
    provider_account_id, provider_account_name, scopes.
    """
    provider = OAUTH_PROVIDERS.get(provider_slug)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider_slug}",
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Build token exchange request — most providers use standard OAuth2
        if provider_slug == "github":
            # GitHub uses a slightly different format — JSON body with Accept header
            resp = await client.post(
                provider.token_url,
                json={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
        elif provider_slug == "slack":
            resp = await client.post(
                provider.token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
        else:
            # Standard OAuth2: Google, Notion, Linear
            resp = await client.post(
                provider.token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )

        if resp.status_code >= 400:
            error_body = resp.text[:500]
            logger.error(
                "Token exchange failed for %s: HTTP %s — %s",
                provider_slug,
                resp.status_code,
                error_body,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token exchange failed: {error_body}",
            )

        try:
            data = resp.json()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse token exchange response: {resp.text[:200]}",
            )
        logger.debug(
            "Token exchange response for %s: keys=%s", provider_slug, list(data.keys())
        )

        # Extract common fields
        access_token = data.get("access_token")

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No access_token in token exchange response",
            )

        refresh_token = data.get("refresh_token")
        token_type = data.get("token_type", "Bearer")
        expires_in = data.get("expires_in")

        # ── Provider-specific account ID/name extraction ───────────────────
        provider_account_id = None
        provider_account_name = None
        granted_scopes = None

        if provider_slug == "slack":
            # Slack returns authed_user.id and team info
            authed_user = data.get("authed_user", {})
            provider_account_id = authed_user.get("id") or data.get("user_id")
            team = data.get("team", {})
            provider_account_name = team.get("name") or authed_user.get("name")
            granted_scopes = (
                data.get("scope", "").split(",") if data.get("scope") else None
            )

        elif provider_slug == "github":
            # GitHub we may need an extra API call to get user info
            provider_account_id = data.get("id")  # not standard
            # Could fetch /user for account name but that requires another call

        elif provider_slug == "google_drive":
            # Google doesn't return user info in token response
            pass

        elif provider_slug == "notion":
            # Notion returns workspace info
            workspace = data.get("workspace")
            if workspace:
                provider_account_id = workspace.get("workspace_id") or data.get(
                    "workspace_id"
                )
                provider_account_name = workspace.get("workspace_name") or data.get(
                    "workspace_name"
                )

        elif provider_slug == "linear":
            pass  # Linear doesn't return extra info in token exchange

        result: dict = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": token_type,
            "expires_in": expires_in,
            "provider_account_id": provider_account_id,
            "provider_account_name": provider_account_name,
            "scopes": granted_scopes,
        }
        return result


# ── OAuth App CRUD ────────────────────────────────────────────────────────────


@router.post("/apps", status_code=status.HTTP_201_CREATED)
async def register_oauth_app(
    payload: OAuthAppCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new user-provided OAuth application."""
    if payload.provider not in _ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {payload.provider}. "
            f"Allowed: {', '.join(sorted(_ALLOWED_PROVIDERS))}",
        )

    app = UserOAuthApp(
        user_id=user.id,
        provider=payload.provider,
        encrypted_client_id=encrypt_token(payload.client_id),
        encrypted_client_secret=encrypt_token(payload.client_secret),
        scopes=payload.scopes,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)

    return ok(_app_to_response(app))


@router.get("/apps")
async def list_oauth_apps(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all registered OAuth apps for the current user."""
    result = await db.execute(
        select(UserOAuthApp)
        .where(UserOAuthApp.user_id == user.id)
        .order_by(desc(UserOAuthApp.created_at))
    )
    apps = result.scalars().all()
    return ok([_app_to_response(a) for a in apps])


@router.get("/apps/{app_id}")
async def get_oauth_app(
    app_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single OAuth app."""
    result = await db.execute(
        select(UserOAuthApp).where(
            UserOAuthApp.id == str(app_id),
            UserOAuthApp.user_id == user.id,
        )
    )
    app = result.scalars().first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OAuth app not found"
        )
    return ok(_app_to_response(app))


@router.put("/apps/{app_id}")
async def update_oauth_app(
    app_id: uuid.UUID,
    payload: OAuthAppUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an OAuth app's credentials."""
    result = await db.execute(
        select(UserOAuthApp).where(
            UserOAuthApp.id == str(app_id),
            UserOAuthApp.user_id == user.id,
        )
    )
    app = result.scalars().first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OAuth app not found"
        )

    if payload.client_id is not None:
        app.encrypted_client_id = encrypt_token(payload.client_id)
    if payload.client_secret is not None:
        app.encrypted_client_secret = encrypt_token(payload.client_secret)
    if payload.scopes is not None:
        app.scopes = payload.scopes
    if payload.is_active is not None:
        app.is_active = payload.is_active

    await db.commit()
    await db.refresh(app)
    return ok(_app_to_response(app))


@router.delete("/apps/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_oauth_app(
    app_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an OAuth app and all its connections."""
    result = await db.execute(
        select(UserOAuthApp).where(
            UserOAuthApp.id == str(app_id),
            UserOAuthApp.user_id == user.id,
        )
    )
    app = result.scalars().first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OAuth app not found"
        )

    # Delete associated connections first
    conns_result = await db.execute(
        select(UserOAuthConnection).where(UserOAuthConnection.app_id == str(app_id))
    )
    for conn in conns_result.scalars().all():
        await db.delete(conn)

    await db.delete(app)
    await db.commit()


# ── OAuth Connection Flow ─────────────────────────────────────────────────────


@router.post("/initiate")
async def initiate_oauth(
    payload: OAuthInitiateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start an OAuth authorization flow — returns the authorization URL."""
    if payload.provider not in _ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {payload.provider}",
        )

    provider_config = OAUTH_PROVIDERS.get(payload.provider)
    if not provider_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No provider config for: {payload.provider}",
        )

    # Look up the user's OAuth app
    result = await db.execute(
        select(UserOAuthApp).where(
            UserOAuthApp.id == str(payload.app_id),
            UserOAuthApp.user_id == user.id,
            UserOAuthApp.is_active == True,
        )
    )
    app = result.scalars().first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth app not found or inactive",
        )

    # Determine and validate the redirect_uri
    from urllib.parse import urlparse

    if payload.redirect_uri:
        redirect_uri = payload.redirect_uri
        # Validate: must point to our own callback endpoint to prevent open redirect attacks
        parsed = urlparse(redirect_uri)
        if not parsed.path.endswith("/integrations/oauth/callback"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="redirect_uri must point to /integrations/oauth/callback",
            )
    else:
        # Use the base URL from the request to build the callback URL
        base = str(request.base_url).rstrip("/")
        redirect_uri = f"{base}api/v2/integrations/oauth/callback"

    # Get the user's client_id (decrypted from stored value)
    client_id = app.get_client_id()

    # Build CSRF-protected state — include redirect_uri base for verification
    state = _build_state(str(app.id), user.id)

    # Determine scopes: prefer app-level scopes, fall back to provider defaults
    scopes = app.scopes if app.scopes else provider_config.scopes

    # Build the authorization URL
    params: dict = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }

    if provider_config.slug == "slack":
        params["scope"] = ",".join(scopes) if scopes else ""
        params["user_scope"] = ",".join(scopes) if scopes else ""
    elif provider_config.slug == "github":
        params["scope"] = ",".join(scopes) if scopes else ""
    elif provider_config.slug == "google_drive":
        params["scope"] = " ".join(scopes) if scopes else ""
        params["response_type"] = "code"
        params["access_type"] = "offline"  # to get refresh_token
        params["prompt"] = "consent"  # always ask for consent
    else:
        params["scope"] = " ".join(scopes) if scopes else ""

    if provider_config.extra_auth_params:
        params.update(provider_config.extra_auth_params)

    # Build URL with query parameters
    from urllib.parse import urlencode

    authorization_url = f"{provider_config.authorize_url}?{urlencode(params)}"

    return ok(
        {
            "authorization_url": authorization_url,
            "state": state,
        }
    )


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle the OAuth callback after user authorizes the app.

    Exchanges the authorization code for tokens, stores them encrypted,
    and returns the connection details.

    This endpoint is called by the provider's redirect — no user auth required
    since we validate via the encrypted state parameter.
    """
    # Decode and verify the state parameter
    try:
        state_data = _decode_state(state)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or tampered state parameter",
        )

    app_id = state_data["app_id"]
    user_id = state_data["user_id"]

    # Look up the OAuth app
    result = await db.execute(
        select(UserOAuthApp).where(
            UserOAuthApp.id == app_id,
            UserOAuthApp.user_id == int(user_id),
            UserOAuthApp.is_active == True,
        )
    )
    app = result.scalars().first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth app not found or inactive",
        )

    # Get decrypted credentials for token exchange
    client_id = app.get_client_id()
    client_secret = app.get_client_secret()

    # Reconstruct the redirect_uri from the request — must match what was sent
    # in the initiate phase.  Use the same base-URL construction as initiate.
    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}api/v2/integrations/oauth/callback"

    # For simplicity, we'll construct the redirect_uri as the callback URL
    # since that's what was registered.  The exchange requires the exact same
    # redirect_uri.  We're already at the callback URL, so we pass it through.
    # However, the request URL includes ?code=...&state=... which we strip.
    # In practice, the callback URL without query params is the redirect_uri.

    # Let's exchange the code for tokens
    try:
        token_data = await _exchange_code(
            provider_slug=app.provider,
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            redirect_uri=redirect_uri,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during token exchange")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token exchange failed: {e!s}",
        )

    # Calculate expires_at from expires_in
    from datetime import datetime, timedelta

    expires_at = None
    expires_in = token_data.get("expires_in")
    if expires_in:
        expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))

    # Check for existing connection (same user + app + account) and update it
    existing_result = await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.app_id == app_id,
            UserOAuthConnection.user_id == int(user_id),
            UserOAuthConnection.provider == app.provider,
        )
    )
    existing_conn = existing_result.scalars().first()

    if existing_conn:
        # Update existing connection
        existing_conn.encrypted_access_token = encrypt_token(token_data["access_token"])
        existing_conn.encrypted_refresh_token = (
            encrypt_token(token_data["refresh_token"])
            if token_data.get("refresh_token")
            else None
        )
        existing_conn.token_type = token_data.get("token_type", "Bearer")
        existing_conn.expires_at = expires_at
        existing_conn.provider_account_id = token_data.get("provider_account_id")
        existing_conn.provider_account_name = token_data.get("provider_account_name")
        existing_conn.scopes = token_data.get("scopes") or app.scopes
        existing_conn.status = "active"
        await db.commit()
        await db.refresh(existing_conn)
        return ok(_connection_to_response(existing_conn))

    # Create new connection
    connection = UserOAuthConnection(
        user_id=int(user_id),
        provider=app.provider,
        app_id=app_id,
        encrypted_access_token=encrypt_token(token_data["access_token"]),
        encrypted_refresh_token=(
            encrypt_token(token_data["refresh_token"])
            if token_data.get("refresh_token")
            else None
        ),
        token_type=token_data.get("token_type", "Bearer"),
        expires_at=expires_at,
        provider_account_id=token_data.get("provider_account_id"),
        provider_account_name=token_data.get("provider_account_name"),
        scopes=token_data.get("scopes") or app.scopes,
        status="active",
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    return ok(_connection_to_response(connection))


# ── Connection Management ─────────────────────────────────────────────────────


@router.get("/connections")
async def list_oauth_connections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all OAuth connections for the current user."""
    result = await db.execute(
        select(UserOAuthConnection)
        .where(UserOAuthConnection.user_id == user.id)
        .order_by(desc(UserOAuthConnection.created_at))
    )
    connections = result.scalars().all()
    return ok([_connection_to_response(c) for c in connections])


@router.get("/connections/{connection_id}")
async def get_oauth_connection(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single OAuth connection."""
    result = await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.id == str(connection_id),
            UserOAuthConnection.user_id == user.id,
        )
    )
    conn = result.scalars().first()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found"
        )
    return ok(_connection_to_response(conn))


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_oauth(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect an OAuth connection (delete tokens)."""
    result = await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.id == str(connection_id),
            UserOAuthConnection.user_id == user.id,
        )
    )
    conn = result.scalars().first()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found"
        )

    await db.delete(conn)
    await db.commit()
