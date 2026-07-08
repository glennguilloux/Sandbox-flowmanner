"""
OIDC (OpenID Connect) SSO Login Service

Implements the OIDC Authorization Code Flow for SSO login with:
- PKCE (Proof Key for Code Exchange) support
- State/nonce validation for CSRF/replay protection
- Token storage and refresh
- Logout support

Uses the auth_models.py tables:
- oidc_providers: provider configs
- user_oidc_accounts: linked user accounts with tokens
"""

import base64
import hashlib
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_models import OIDCProvider, UserOIDCAccount
from app.models.user import User
from app.services.auth_service import (
    create_access_token,
    create_refresh_token_value,
    hash_password,
    store_refresh_token,
)
from app.services.auth_v3_service import (
    create_access_token as v3_create_access_token,
)
from app.services.auth_v3_service import (
    create_session as v3_create_session,
)

logger = logging.getLogger(__name__)


# In-memory cache for discovered provider endpoints
_discovery_cache: dict[str, dict[str, Any]] = {}
CACHE_TTL = 3600  # 1 hour

# In-memory store for OIDC login state (state -> {nonce, code_verifier, provider, ...})
# In production, use Redis with TTL
_state_store: dict[str, dict[str, Any]] = {}
STATE_TTL = 600  # 10 minutes
MAX_STATE_KEYS = 5000


def _cleanup_state_store() -> None:
    """Remove expired entries and enforce max size."""
    now = time.time()
    expired = [k for k, v in _state_store.items() if v.get("_ts", 0) + STATE_TTL < now]
    for k in expired:
        del _state_store[k]
    if len(_state_store) > MAX_STATE_KEYS:
        sorted_keys = sorted(_state_store.keys(), key=lambda k: _state_store[k].get("_ts", 0))
        for old_key in sorted_keys[: len(_state_store) - MAX_STATE_KEYS]:
            del _state_store[old_key]


# ---------------------------------------------------------------------------
# Provider Config
# ---------------------------------------------------------------------------


async def get_provider_config(
    db: AsyncSession,
    provider_name: str,
) -> OIDCProvider | None:
    """Get OIDC provider config from database."""
    result = await db.execute(
        select(OIDCProvider).where(
            OIDCProvider.name == provider_name,
            OIDCProvider.is_active == True,
        )
    )
    return result.scalar_one_or_none()


async def list_providers(db: AsyncSession) -> list[dict[str, str]]:
    """List all active OIDC providers."""
    result = await db.execute(select(OIDCProvider).where(OIDCProvider.is_active == True))
    providers = result.scalars().all()
    return [
        {
            "name": p.name,
            "display_name": p.display_name or p.name,
            "issuer": p.issuer_url,
        }
        for p in providers
    ]


# ---------------------------------------------------------------------------
# OIDC Discovery
# ---------------------------------------------------------------------------


async def discover_provider_endpoints(
    issuer_url: str,
) -> dict[str, str]:
    """
    Discover OIDC provider endpoints from the well-known URL.

    Fetches from: {issuer}/.well-known/openid-configuration
    """
    now = time.time()
    cached = _discovery_cache.get(issuer_url)

    if cached and (now - cached.get("timestamp", 0)) < CACHE_TTL:
        return cached

    well_known_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(well_known_url)
        response.raise_for_status()
        discovery = response.json()

    endpoints = {
        "authorization_endpoint": discovery["authorization_endpoint"],
        "token_endpoint": discovery["token_endpoint"],
        "userinfo_endpoint": discovery.get("userinfo_endpoint", ""),
        "jwks_uri": discovery.get("jwks_uri", ""),
        "end_session_endpoint": discovery.get("end_session_endpoint", ""),
        "timestamp": now,
    }

    _discovery_cache[issuer_url] = endpoints
    logger.info("Discovered OIDC endpoints for %s", issuer_url)
    return endpoints


# ---------------------------------------------------------------------------
# PKCE Support
# ---------------------------------------------------------------------------


def generate_code_verifier() -> str:
    """Generate a cryptographically random code_verifier for PKCE."""
    return secrets.token_urlsafe(32)


def generate_code_challenge(code_verifier: str) -> str:
    """Generate S256 code_challenge from code_verifier."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# State/Nonce Management
# ---------------------------------------------------------------------------


def generate_state() -> str:
    """Generate a cryptographically secure state parameter."""
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    """Generate a cryptographically secure nonce."""
    return secrets.token_urlsafe(32)


def store_state(
    state: str,
    nonce: str,
    provider_name: str,
    code_verifier: str,
    redirect_uri: str | None = None,
) -> None:
    """Store state data for validation in callback."""
    _cleanup_state_store()
    _state_store[state] = {
        "nonce": nonce,
        "_ts": time.time(),
        "code_verifier": code_verifier,
        "provider": provider_name,
        "redirect_uri": redirect_uri,
        "created_at": time.time(),
    }
    _cleanup_expired_states()


def consume_state(state: str) -> dict[str, Any] | None:
    """Retrieve and remove state data (one-time use)."""
    _cleanup_expired_states()
    return _state_store.pop(state, None)


def _cleanup_expired_states() -> None:
    """Remove expired state entries."""
    now = time.time()
    expired = [k for k, v in _state_store.items() if now - v.get("created_at", 0) > STATE_TTL]
    for k in expired:
        del _state_store[k]


# ---------------------------------------------------------------------------
# Authorization URL
# ---------------------------------------------------------------------------


async def get_authorization_url(
    db: AsyncSession,
    provider_name: str,
    redirect_uri: str,
    state: str | None = None,
    nonce: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Generate the OIDC authorization URL with PKCE.

    Returns:
        Dict with 'authorization_url', 'state', 'nonce', and 'code_verifier'.
    """
    provider = await get_provider_config(db, provider_name)
    if not provider:
        raise ValueError(f"Unknown or inactive OIDC provider: {provider_name}")

    endpoints = await discover_provider_endpoints(provider.issuer_url)

    state = state or generate_state()
    nonce = nonce or generate_nonce()
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)

    scopes = provider.scopes or "openid email profile"

    params = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "nonce": nonce,
        "_ts": time.time(),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    if extra_params:
        params.update(extra_params)

    authorization_url = f"{endpoints['authorization_endpoint']}?{urlencode(params)}"

    # Store state for validation in callback
    store_state(
        state=state,
        nonce=nonce,
        provider_name=provider_name,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
    )

    return {
        "authorization_url": authorization_url,
        "state": state,
        "nonce": nonce,
        "_ts": time.time(),
        "code_verifier": code_verifier,
    }


# ---------------------------------------------------------------------------
# Token Exchange
# ---------------------------------------------------------------------------


async def exchange_code_for_tokens(
    db: AsyncSession,
    provider_name: str,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> dict[str, Any]:
    """
    Exchange authorization code for tokens.

    Args:
        code_verifier: PKCE code_verifier (required if PKCE was used)

    Returns:
        Dict with 'access_token', 'id_token', 'token_type', 'expires_in', etc.
    """
    provider = await get_provider_config(db, provider_name)
    if not provider:
        raise ValueError(f"Unknown OIDC provider: {provider_name}")

    endpoints = await discover_provider_endpoints(provider.issuer_url)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
    }

    # Add PKCE code_verifier if provided
    if code_verifier:
        data["code_verifier"] = code_verifier

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            endpoints["token_endpoint"],
            data=data,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        token_response = response.json()

    if "error" in token_response:
        error = token_response["error"]
        error_desc = token_response.get("error_description", "")
        logger.error("OIDC token exchange failed: %s - %s", error, error_desc)
        raise ValueError(f"Token exchange failed: {error} - {error_desc}")

    return token_response


# ---------------------------------------------------------------------------
# User Info
# ---------------------------------------------------------------------------


async def get_userinfo(
    db: AsyncSession,
    provider_name: str,
    access_token: str,
) -> dict[str, Any]:
    """
    Fetch user info from the OIDC userinfo endpoint.

    Returns:
        Dict with user claims (sub, email, name, etc.)
    """
    provider = await get_provider_config(db, provider_name)
    if not provider:
        raise ValueError(f"Unknown OIDC provider: {provider_name}")

    endpoints = await discover_provider_endpoints(provider.issuer_url)

    userinfo_endpoint = endpoints.get("userinfo_endpoint")
    if not userinfo_endpoint:
        raise ValueError(f"Provider {provider_name} does not have a userinfo endpoint")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


def decode_id_token(id_token: str) -> dict[str, Any]:
    """
    Decode an ID token without verification (for development).

    WARNING: In production, use proper JWKS verification.
    """
    return jwt.decode(id_token, options={"verify_signature": False})


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------


async def find_or_create_user(
    db: AsyncSession,
    userinfo: dict[str, Any],
    provider: OIDCProvider,
) -> User:
    """
    Find existing user by OIDC subject or create a new one.

    Maps OIDC claims to User fields:
    - sub -> user_oidc_accounts.subject
    - email -> email
    - name / preferred_username -> username
    - given_name + family_name -> full_name
    - picture -> avatar_url
    """
    oidc_sub = userinfo.get("sub")
    if not oidc_sub:
        raise ValueError("OIDC userinfo missing 'sub' claim")

    # Try to find existing user by OIDC subject
    result = await db.execute(
        select(UserOIDCAccount).where(
            UserOIDCAccount.provider_id == provider.id,
            UserOIDCAccount.subject == oidc_sub,
        )
    )
    account = result.scalar_one_or_none()

    if account:
        # Update account tokens
        user_result = await db.execute(select(User).where(User.id == account.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            _update_user_from_claims(user, userinfo)
            account.email = userinfo.get("email")
            account.name = userinfo.get("name")
            await db.flush()
            await db.refresh(user)
            logger.info("Found existing OIDC user: %s (%s)", user.id, user.email)
            return user

    # Try to find by email (link existing account)
    email = userinfo.get("email")
    if email:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            # Create OIDC account link
            account = UserOIDCAccount(
                user_id=user.id,
                provider_id=provider.id,
                subject=oidc_sub,
                email=email,
                name=userinfo.get("name"),
            )
            db.add(account)
            _update_user_from_claims(user, userinfo)
            await db.flush()
            await db.refresh(user)
            logger.info("Linked existing user %s to OIDC provider %s", user.id, provider.name)
            return user

    # Create new user
    username = _generate_username(userinfo)
    full_name = _build_full_name(userinfo)

    user = User(
        email=email or f"{oidc_sub}@{provider.name}.local",
        username=username,
        password_hash=hash_password(secrets.token_urlsafe(32)),  # Random password for OIDC users
        full_name=full_name,
        avatar_url=userinfo.get("picture"),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Create OIDC account link
    account = UserOIDCAccount(
        user_id=user.id,
        provider_id=provider.id,
        subject=oidc_sub,
        email=email,
        name=userinfo.get("name"),
    )
    db.add(account)
    await db.flush()

    logger.info(
        "Created new OIDC user: %s (%s) from provider %s",
        user.id,
        user.email,
        provider.name,
    )
    return user


async def update_oidc_account_tokens(
    db: AsyncSession,
    user: User,
    provider: OIDCProvider,
    token_response: dict[str, Any],
) -> None:
    """Store OIDC tokens in user_oidc_accounts table."""
    result = await db.execute(
        select(UserOIDCAccount).where(
            UserOIDCAccount.user_id == user.id,
            UserOIDCAccount.provider_id == provider.id,
        )
    )
    account = result.scalar_one_or_none()

    if account:
        account.access_token = token_response.get("access_token")
        account.id_token = token_response.get("id_token")
        account.refresh_token = token_response.get("refresh_token")
        await db.flush()
        logger.info("Updated OIDC tokens for user %s", user.id)


# ---------------------------------------------------------------------------
# Authentication Flow
# ---------------------------------------------------------------------------


async def authenticate_with_oidc(
    db: AsyncSession,
    provider_name: str,
    code: str,
    redirect_uri: str,
    state: str | None = None,
    code_verifier: str | None = None,
) -> dict[str, Any]:
    """
    Complete OIDC authentication flow.

    1. Validate state parameter
    2. Exchange code for tokens (with PKCE if code_verifier provided)
    3. Validate nonce in ID token
    4. Get user info (from userinfo endpoint or ID token)
    5. Find or create user
    6. Store OIDC tokens
    7. Generate local JWT tokens

    Returns:
        Dict with 'access_token', 'refresh_token', 'user_id', 'email', 'username'
    """
    # Validate state parameter
    state_data = None
    if state:
        state_data = consume_state(state)
        if not state_data:
            raise ValueError("Invalid or expired state parameter")

    # Get provider config
    provider = await get_provider_config(db, provider_name)
    if not provider:
        raise ValueError(f"Unknown OIDC provider: {provider_name}")

    # Use code_verifier from state if not provided
    if not code_verifier and state_data:
        code_verifier = state_data.get("code_verifier")

    # Exchange code for tokens
    token_response = await exchange_code_for_tokens(db, provider_name, code, redirect_uri, code_verifier)

    # Validate nonce in ID token
    nonce = state_data.get("nonce") if state_data else None
    if nonce and token_response.get("id_token"):
        try:
            id_claims = decode_id_token(token_response["id_token"])
            if id_claims.get("nonce") and id_claims["nonce"] != nonce:
                raise ValueError("Nonce mismatch in ID token")
        except ValueError:
            raise
        except Exception as e:
            logger.warning("Could not validate nonce in ID token: %s", e)

    # Get user info
    userinfo = None

    # Try userinfo endpoint first
    access_token = token_response.get("access_token")
    if access_token:
        try:
            userinfo = await get_userinfo(db, provider_name, access_token)
        except Exception as e:
            logger.warning("Failed to get userinfo from endpoint: %s", e)

    # Fall back to ID token claims
    if not userinfo and token_response.get("id_token"):
        try:
            userinfo = decode_id_token(token_response["id_token"])
        except Exception as e:
            logger.warning("Failed to decode ID token: %s", e)

    if not userinfo:
        raise ValueError("Could not retrieve user information from OIDC provider")

    # Find or create user
    user = await find_or_create_user(db, userinfo, provider)

    # Store OIDC tokens
    await update_oidc_account_tokens(db, user, provider, token_response)

    # Generate local tokens (Item #10: dual-write v3 AuthSession)
    try:
        v3_session, _v3_refresh = await v3_create_session(db, user)
        local_access = v3_create_access_token(user_id=user.id, session_id=str(v3_session.id))
    except Exception:
        logger.debug("v3 dual-write in OIDC failed, falling back to v1", exc_info=True)
        local_access = create_access_token(user.id)
    local_refresh = create_refresh_token_value()
    await store_refresh_token(db, user.id, local_refresh)

    return {
        "access_token": local_access,
        "refresh_token": local_refresh,
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
    }


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


async def logout_oidc(
    db: AsyncSession,
    provider_name: str,
    user_id: int,
    id_token_hint: str | None = None,
) -> dict[str, str]:
    """
    Logout from OIDC provider.

    Returns:
        Dict with 'end_session_url' for redirect
    """
    provider = await get_provider_config(db, provider_name)
    if not provider:
        raise ValueError(f"Unknown OIDC provider: {provider_name}")

    endpoints = await discover_provider_endpoints(provider.issuer_url)
    end_session_endpoint = endpoints.get("end_session_endpoint")

    if not end_session_endpoint:
        # Provider doesn't support end_session_endpoint
        # Just clear local tokens
        await _clear_user_oidc_tokens(db, user_id, provider.id)
        return {"end_session_url": None}

    # Build end session URL
    params = {
        "client_id": provider.client_id,
    }

    if id_token_hint:
        params["id_token_hint"] = id_token_hint

    frontend_url = _get_frontend_base_url()
    if frontend_url:
        params["post_logout_redirect_uri"] = frontend_url

    end_session_url = f"{end_session_endpoint}?{urlencode(params)}"

    # Clear local tokens
    await _clear_user_oidc_tokens(db, user_id, provider.id)

    return {"end_session_url": end_session_url}


async def _clear_user_oidc_tokens(
    db: AsyncSession,
    user_id: int,
    provider_id: str,
) -> None:
    """Clear stored OIDC tokens for a user."""
    result = await db.execute(
        select(UserOIDCAccount).where(
            UserOIDCAccount.user_id == user_id,
            UserOIDCAccount.provider_id == provider_id,
        )
    )
    account = result.scalar_one_or_none()
    if account:
        account.access_token = None
        account.id_token = None
        account.refresh_token = None
        await db.flush()
        logger.info("Cleared OIDC tokens for user %s", user_id)


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------


async def refresh_oidc_token(
    db: AsyncSession,
    provider_name: str,
    user_id: int,
) -> dict[str, Any] | None:
    """
    Refresh OIDC access token using stored refresh token.

    Returns:
        New token response or None if refresh not possible
    """
    provider = await get_provider_config(db, provider_name)
    if not provider:
        raise ValueError(f"Unknown OIDC provider: {provider_name}")

    # Get stored refresh token
    result = await db.execute(
        select(UserOIDCAccount).where(
            UserOIDCAccount.user_id == user_id,
            UserOIDCAccount.provider_id == provider.id,
        )
    )
    account = result.scalar_one_or_none()

    if not account or not account.refresh_token:
        return None

    endpoints = await discover_provider_endpoints(provider.issuer_url)

    data = {
        "grant_type": "refresh_token",
        "refresh_token": account.refresh_token,
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                endpoints["token_endpoint"],
                data=data,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            token_response = response.json()

        if "error" in token_response:
            logger.error("OIDC token refresh failed: %s", token_response)
            return None

        # Update stored tokens
        account.access_token = token_response.get("access_token")
        account.id_token = token_response.get("id_token")
        if token_response.get("refresh_token"):
            account.refresh_token = token_response["refresh_token"]
        await db.flush()

        return token_response

    except Exception as e:
        logger.error("Failed to refresh OIDC token: %s", e)
        return None


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _update_user_from_claims(user: User, userinfo: dict[str, Any]) -> None:
    """Update user fields from OIDC claims."""
    if userinfo.get("name") and not user.full_name:
        user.full_name = userinfo["name"]
    elif userinfo.get("given_name") or userinfo.get("family_name"):
        user.full_name = _build_full_name(userinfo)

    if userinfo.get("picture") and not user.avatar_url:
        user.avatar_url = userinfo["picture"]


def _build_full_name(userinfo: dict[str, Any]) -> str | None:
    """Build full name from OIDC claims."""
    if userinfo.get("name"):
        return userinfo["name"]
    given = userinfo.get("given_name", "")
    family = userinfo.get("family_name", "")
    if given or family:
        return f"{given} {family}".strip()
    return None


def _generate_username(userinfo: dict[str, Any]) -> str:
    """Generate a username from OIDC claims."""
    if userinfo.get("preferred_username"):
        return userinfo["preferred_username"]
    if userinfo.get("email"):
        return userinfo["email"].split("@")[0]
    return f"user_{secrets.token_hex(4)}"


def _get_frontend_base_url() -> str:
    """Get frontend base URL from environment."""
    import os

    return os.getenv("FRONTEND_URL", "http://localhost:3000")
