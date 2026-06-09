"""Integrations API router — list, connect, disconnect, test, and OAuth authorize/callback."""

import json
import logging
import secrets
import time
from datetime import UTC, datetime
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.core.oauth import OAUTH_PROVIDERS, encrypt_token
from app.database import get_db
from app.models.phase4_models import IntegrationConnection
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

# ── Redis-backed OAuth state store (shared across all workers) ──────────

_OAUTH_STATE_TTL = 600  # 10 minutes — enough for user to auth on GitHub


def _get_redis():
    """Get a Redis client for OAuth state storage."""
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _store_state(key: str, data: dict) -> None:
    """Store an OAuth state/auth-token in Redis with a TTL."""
    r = _get_redis()
    r.setex(f"oauth:{key}", _OAUTH_STATE_TTL, json.dumps(data))


def _pop_state(key: str) -> dict | None:
    """Atomic pop: return the stored data or None if missing/expired."""
    r = _get_redis()
    raw = r.get(f"oauth:{key}")
    if raw is None:
        return None
    r.delete(f"oauth:{key}")
    return json.loads(raw)


# ── Schemas ──────────────────────────────────────────────────────────────


class Integration(BaseModel):
    slug: str
    name: str
    description: str
    category: str
    icon_url: str
    auth_type: str


class ConnectRequest(BaseModel):
    """Optional body for API-key / credential-based integrations."""

    instance_url: str | None = None
    api_key: str | None = None


class Connection(BaseModel):
    id: str
    integration: str
    account_name: str | None = None
    account_id: str | None = None
    scopes: str | None = None
    is_active: bool
    created_at: str
    expires_at: str | None = None

    model_config = {"from_attributes": True}


# ── Available Integrations (static registry) ─────────────────────────────

AVAILABLE_INTEGRATIONS = [
    Integration(
        slug="slack",
        name="Slack",
        description="Send messages, create channels, and manage workflows directly from Slack.",
        category="communication",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="github",
        name="GitHub",
        description="Automate PRs, issues, and code reviews with GitHub integration.",
        category="development",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="google",
        name="Google",
        description="Access Drive, Gmail, and Calendar from your workflows.",
        category="productivity",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="google_drive",
        name="Google Drive",
        description="Access and manage files in Google Drive from your workflows.",
        category="storage",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="notion",
        name="Notion",
        description="Read and write Notion pages, databases, and tasks.",
        category="productivity",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="discord",
        name="Discord",
        description="Send messages, manage channels, and interact with Discord servers via bot.",
        category="communication",
        icon_url="",
        auth_type="bot_token",
    ),
    Integration(
        slug="apiflow",
        name="Apiflow",
        description="Connect your self-hosted Apiflow instance — manage API collections, run tests, and automate API workflows via agent.",
        category="development",
        icon_url="",
        auth_type="api_key",
    ),
]


def _conn_to_response(c: IntegrationConnection) -> Connection:
    return Connection(
        id=c.id,
        integration=c.integration_slug,
        account_name=c.account_name,
        account_id=c.account_id,
        scopes=c.scopes,
        is_active=c.is_active,
        created_at=c.created_at.isoformat() if c.created_at else "",
        expires_at=c.expires_at.isoformat() if c.expires_at else None,
    )


@router.get("")
async def list_integrations(
    user: User = Depends(get_current_user),
):
    return {"integrations": [i.model_dump() for i in AVAILABLE_INTEGRATIONS]}


@router.get("/connections")
async def list_connections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationConnection)
        .where(IntegrationConnection.user_id == user.id)
        .order_by(IntegrationConnection.created_at.desc())
    )
    conns = result.scalars().all()
    return {"connections": [_conn_to_response(c).model_dump() for c in conns]}


@router.post("/{slug}/connect")
async def connect_integration(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
    body: ConnectRequest | None = None,
):
    integration = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == slug), None)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    if integration.auth_type == "oauth2":
        # Generate one-time auth token so the browser-based authorize redirect works
        auth_token = secrets.token_urlsafe(32)
        _store_state(
            auth_token,
            {
                "user_id": user.id,
                "slug": slug,
                "created_at": time.time(),
            },
        )
        authorize_url = str(request.url_for("oauth_authorize", slug=slug))
        return {"authorize_url": f"{authorize_url}?auth={auth_token}"}

    # API-key / credential-based integrations
    encrypted_key = None
    account_name = None
    if slug == "apiflow" and body:
        if body.api_key:
            encrypted_key = encrypt_token(body.api_key)
        account_name = body.instance_url

    conn = IntegrationConnection(
        id=str(uuid4()),
        user_id=user.id,
        integration_slug=slug,
        encrypted_access_token=encrypted_key,
        account_name=account_name,
        is_active=True,
    )
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return {"status": "connected", "connection_id": conn.id}


@router.get("/{slug}/oauth/authorize", name="oauth_authorize")
async def oauth_authorize(
    slug: str,
    auth: str = Query(...),
    request: Request = None,
):
    """Initiate OAuth2 authorization flow for the given integration slug."""
    # Validate one-time auth token (set by authenticated POST /connect)
    auth_data = _pop_state(auth)
    if not auth_data or auth_data.get("slug") != slug:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired auth token — please reconnect from the integrations page",
        )

    user_id = auth_data["user_id"]

    provider = OAUTH_PROVIDERS.get(slug)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Unknown integration: {slug}")

    if not provider.is_configured:
        raise HTTPException(
            status_code=503,
            detail=f"{provider.name} OAuth is not configured (missing client credentials)",
        )

    # Determine redirect URI (always HTTPS in production behind Nginx)
    scheme = "https"
    if request and request.headers.get("x-forwarded-proto"):
        scheme = request.headers["x-forwarded-proto"]
    redirect_uri = (
        str(request.url_for("oauth_callback", slug=slug)).replace(
            "http://", f"{scheme}://"
        )
        if request
        else f"https://flowmanner.com/api/integrations/{slug}/oauth/callback"
    )

    # Generate and store state for CSRF protection
    state = secrets.token_urlsafe(32)
    _store_state(
        state,
        {
            "user_id": user_id,
            "slug": slug,
            "created_at": time.time(),
            "redirect_uri": redirect_uri,
        },
    )

    # Build the authorize URL
    params = {
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
    }
    # Slack OAuth v2 uses user_scope for user tokens on already-installed apps
    if slug == "slack":
        params["user_scope"] = " ".join(provider.scopes)
    else:
        params["scope"] = " ".join(provider.scopes)
    if provider.extra_auth_params:
        params.update(provider.extra_auth_params)

    authorize_url = f"{provider.authorize_url}?{urlencode(params)}"
    return RedirectResponse(url=authorize_url, status_code=302)


@router.get("/{slug}/oauth/callback", name="oauth_callback")
async def oauth_callback(
    slug: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth2 callback — exchange code for tokens and store connection."""
    # Validate state (from Redis — shared across all workers)
    stored = _pop_state(state)
    if not stored:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    provider = OAUTH_PROVIDERS.get(slug)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Unknown integration: {slug}")

    # Exchange code for tokens
    token_data = {
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "code": code,
        "redirect_uri": stored["redirect_uri"],
        "grant_type": "authorization_code",
    }

    # GitHub requires a different Accept header
    headers = {"Accept": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.post(provider.token_url, data=token_data, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Token exchange failed: {resp.status_code} {resp.text[:200]}",
        )

    token_json = resp.json()
    access_token = token_json.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=502,
            detail=f"Token exchange returned no access_token: {resp.text[:200]}",
        )

    refresh_token = token_json.get("refresh_token")
    token_type = token_json.get("token_type", "Bearer")

    # Encrypt tokens before storing
    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

    # Create IntegrationConnection
    conn = IntegrationConnection(
        id=str(uuid4()),
        user_id=stored["user_id"],
        integration_slug=slug,
        encrypted_access_token=encrypted_access,
        encrypted_refresh_token=encrypted_refresh,
        token_type=token_type,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)

    # Wire the connection into Nexus so agents can use it
    try:
        from app.services.integration_bridge import get_integration_bridge

        bridge = get_integration_bridge()
        await bridge.register_capabilities_for_user(
            user_id=stored["user_id"],
            slug=slug,
        )
    except Exception as e:
        logger.warning('Failed to register Nexus capabilities for %s: %s', slug, e)

    # Redirect to frontend
    return RedirectResponse(
        url=f"https://flowmanner.com/dashboard/settings/integrations?connected={slug}",
        status_code=302,
    )


@router.delete("/{slug}/disconnect")
async def disconnect_integration(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.user_id == user.id,
            IntegrationConnection.integration_slug == slug,
        )
    )
    conns = result.scalars().all()
    for c in conns:
        await db.delete(c)
    await db.commit()

    # Unregister Nexus capabilities for this integration
    try:
        from app.services.integration_bridge import get_integration_bridge

        bridge = get_integration_bridge()
        await bridge.unregister_capabilities_for_user(
            user_id=user.id,
            slug=slug,
        )
    except Exception as e:
        logger.warning('Failed to unregister Nexus capabilities for %s: %s', slug, e)

    return {"status": "disconnected"}


@router.get("/connected")
async def get_connected_integrations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's connected integrations with available actions (same data the agent sees)."""
    from app.services.integration_bridge import (
        _INTEGRATION_CAPABILITIES,
        _NON_OAUTH_CONFIGS,
    )

    connected: list[dict] = []

    # 1. Active OAuth connections from DB
    result = await db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.user_id == user.id,
            IntegrationConnection.is_active.is_(True),
        )
    )
    for conn in result.scalars().all():
        slug = conn.integration_slug
        caps = _INTEGRATION_CAPABILITIES.get(slug, [])
        connected.append(
            {
                "slug": slug,
                "name": slug.title(),
                "account_name": conn.account_name,
                "account_id": conn.account_id,
                "auth_type": "oauth2",
                "actions": [
                    {"id": c["id"], "name": c["name"], "description": c["description"]}
                    for c in caps
                ],
                "action_count": len(caps),
            }
        )

    # 2. Non-OAuth integrations (API key / bot token)
    _NON_OAUTH_SETTINGS: dict[str, str] = {
        "linear": "LINEAR_API_KEY",
        "discord": "DISCORD_BOT_TOKEN",
    }

    for slug, cfg in _NON_OAUTH_CONFIGS.items():
        setting_key = _NON_OAUTH_SETTINGS.get(slug)
        if setting_key and getattr(settings, setting_key, ""):
            caps = _INTEGRATION_CAPABILITIES.get(slug, [])
            connected.append(
                {
                    "slug": slug,
                    "name": slug.title(),
                    "account_name": cfg.get("name"),
                    "account_id": None,
                    "auth_type": cfg.get("auth_type"),
                    "actions": [
                        {
                            "id": c["id"],
                            "name": c["name"],
                            "description": c["description"],
                        }
                        for c in caps
                    ],
                    "action_count": len(caps),
                }
            )

    return {"connected": connected, "total": len(connected)}


@router.post("/{slug}/test")
async def test_integration(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.user_id == user.id,
            IntegrationConnection.integration_slug == slug,
            IntegrationConnection.is_active == True,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="No active connection found")
    return {"status": "ok", "message": f"{slug} connection is active"}
