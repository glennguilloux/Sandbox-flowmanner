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
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.core.oauth import OAUTH_PROVIDERS, encrypt_token
from app.database import get_db
from app.models.phase4_models import IntegrationConnection
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

# NOTE: marketplace.py handles user-generated workflow listings (publish, install, rate).
# Integrations handles first-party service connections (Slack, GitHub, etc.). No overlap.

# ── Feature-flag gate for manifest-driven integrations ───────────────────
# (flag caching now shared via _is_flag_enabled below)


async def _is_manifest_flag_enabled(db: AsyncSession) -> bool:
    """Check whether the integration_manifests_v1 feature flag is on."""
    return await _is_flag_enabled(db, "integration_manifests_v1")


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
    Integration(
        slug="linear",
        name="Linear",
        description="Issue tracking and project management for engineering teams. Create, update, and track issues with AI agent automation.",
        category="development",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="sentry",
        name="Sentry",
        description="Error monitoring and performance tracking. Receive error alerts, triage issues, analyze stack traces, and trigger debugging agents automatically.",
        category="development",
        icon_url="",
        auth_type="api_key",
    ),
    Integration(
        slug="vercel",
        name="Vercel",
        description="Deployment monitoring and management. Track deployments, monitor build status, trigger rollbacks, and manage domains for your Vercel projects.",
        category="development",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="jira",
        name="Jira",
        description="Enterprise issue tracking and project management. Create, update, and search issues, manage sprints, and automate triage workflows with AI agent integration.",
        category="development",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="confluence",
        name="Confluence",
        description="Knowledge base and wiki management. Create, update, and search pages, manage spaces, and automate documentation workflows with AI agent integration.",
        category="productivity",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="figma",
        name="Figma",
        description="Design file access and collaboration. Read files, list comments, post feedback, track versions, and bridge design-to-dev workflows with AI agent integration.",
        category="design",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="stripe",
        name="Stripe",
        description="Payment and billing platform. Manage charges, customers, invoices, subscriptions, and revenue data with AI agent integration.",
        category="development",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="pagerduty",
        name="PagerDuty",
        description="Incident management and on-call platform. Create, triage, and resolve incidents, manage services, schedules, and escalation policies with AI agent integration.",
        category="development",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="datadog",
        name="Datadog",
        description="Monitoring and observability platform. Manage monitors, incidents, dashboards, metrics, and events with AI agent integration.",
        category="development",
        icon_url="",
        auth_type="oauth2",
    ),
    Integration(
        slug="airtable",
        name="Airtable",
        description="Low-code database platform. Manage bases, tables, and records with AI agent integration for database-driven workflows.",
        category="productivity",
        icon_url="",
        auth_type="oauth2",
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
    db: AsyncSession = Depends(get_db),
):
    if await _is_manifest_flag_enabled(db):
        from app.services.integration_manifest_service import manifest_service

        return {"integrations": manifest_service.load_all(), "source": "manifests"}
    return {"integrations": [i.model_dump() for i in AVAILABLE_INTEGRATIONS], "source": "static"}


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
    # Look up integration from manifest (if flag enabled) or fallback to static list
    if await _is_manifest_flag_enabled(db):
        from app.services.integration_manifest_service import manifest_service

        manifest = manifest_service.get(slug)
        if not manifest:
            raise HTTPException(status_code=404, detail="Integration not found")
        auth_type = manifest.get("auth_type", "oauth2")
    else:
        integration = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == slug), None)
        if not integration:
            raise HTTPException(status_code=404, detail="Integration not found")
        auth_type = integration.auth_type

    if auth_type == "oauth2":
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

    if slug == "sentry" and body:
        if body.api_key:
            encrypted_key = encrypt_token(body.api_key)
        account_name = body.instance_url or "sentry.io"

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
        str(request.url_for("oauth_callback", slug=slug)).replace("http://", f"{scheme}://")
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

    # Jira uses a custom OAuth callback (site discovery step)
    if slug == "jira":
        redirect_uri = redirect_uri.replace(
            f"/api/integrations/jira/oauth/callback",
            "/api/jira/oauth/callback",
        )
        params["redirect_uri"] = redirect_uri

    # Confluence uses a custom OAuth callback (same Atlassian 3LO site discovery as Jira)
    if slug == "confluence":
        redirect_uri = redirect_uri.replace(
            "/api/integrations/confluence/oauth/callback",
            "/api/confluence/oauth/callback",
        )
        params["redirect_uri"] = redirect_uri

    # Stripe uses a custom OAuth callback (stripe_user_id extraction)
    if slug == "stripe":
        redirect_uri = redirect_uri.replace(
            "/api/integrations/stripe/oauth/callback",
            "/api/stripe/oauth/callback",
        )
        params["redirect_uri"] = redirect_uri

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
        logger.warning("Failed to register Nexus capabilities for %s: %s", slug, e)

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
        logger.warning("Failed to unregister Nexus capabilities for %s: %s", slug, e)

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
                "actions": [{"id": c["id"], "name": c["name"], "description": c["description"]} for c in caps],
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
async def check_integration_connection(
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


# ── Health Status Endpoints (Phase 2) ─────────────────────────────────────


import asyncio as _asyncio

# ── Shared feature-flag helper ──────────────────────────────────────────────

_flag_cache: dict[str, tuple[float, bool]] = {}
_FLAG_TTL = 60.0  # seconds — matches the feature-flags in-process cache


async def _is_flag_enabled(db: AsyncSession, key: str) -> bool:
    """Check whether a feature flag is enabled (cached in-process for 60 s)."""
    now = time.monotonic()
    entry = _flag_cache.get(key)
    if entry is not None:
        ts, value = entry
        if (now - ts) < _FLAG_TTL:
            return value
    try:
        result = await db.execute(
            text("SELECT enabled_globally FROM feature_flags WHERE key = :key"),
            {"key": key},
        )
        row = result.scalar()
        enabled = bool(row) if row is not None else False
    except Exception:
        enabled = False
    _flag_cache[key] = (now, enabled)
    return enabled


# ── Health status caching ───────────────────────────────────────────────────

_health_cache: dict | None = None
_health_cache_ts: float = 0.0
_HEALTH_CACHE_TTL = 60.0  # seconds
_health_cache_lock = _asyncio.Lock()


async def _is_health_flag_enabled(db: AsyncSession) -> bool:
    """Check whether the integration_health_v1 feature flag is on."""
    return await _is_flag_enabled(db, "integration_health_v1")


async def _build_health_response(db: AsyncSession) -> dict:
    """Build the full health status response (expensive — cache this)."""
    from app.services.integration_health_service import IntegrationHealthService
    from app.services.integration_manifest_service import manifest_service

    service = IntegrationHealthService(db)
    latest = await service.get_all_latest()

    integrations = []
    for slug in manifest_service.slug_list:
        manifest = manifest_service.get(slug)
        record = latest.get(slug)
        uptime = await service.compute_uptime_pct(slug)
        integrations.append(
            {
                "slug": slug,
                "name": manifest["name"] if manifest else slug,
                "trust_level": manifest.get("trust_level", "verified") if manifest else "verified",
                "status": record.status if record else "unknown",
                "latency_ms": record.latency_ms if record else None,
                "uptime_30d": uptime,
                "last_checked": record.checked_at.isoformat() if record else None,
            }
        )
    return {"integrations": integrations}


async def _get_cached_health(db: AsyncSession) -> dict:
    """Return health response from cache, refreshing if stale."""
    global _health_cache, _health_cache_ts
    now = time.monotonic()
    if _health_cache is not None and (now - _health_cache_ts) < _HEALTH_CACHE_TTL:
        return _health_cache
    async with _health_cache_lock:
        now = time.monotonic()
        if _health_cache is not None and (now - _health_cache_ts) < _HEALTH_CACHE_TTL:
            return _health_cache
        result = await _build_health_response(db)
        _health_cache = result
        _health_cache_ts = time.monotonic()
        return result


@router.get("/health")
async def get_all_health_statuses(
    db: AsyncSession = Depends(get_db),
):
    """Returns health status for all integrations.

    Unauthenticated — public trust signal.  Gated by the
    ``integration_health_v1`` feature flag.  Cached for 60 seconds.
    """
    if not await _is_health_flag_enabled(db):
        raise HTTPException(status_code=404, detail="Health status not available")
    return await _get_cached_health(db)


# ── Public Status Endpoint (Phase 5) ──────────────────────────────────────


# Separate cache for the public status endpoint (no auth, different shape)
_status_cache: dict | None = None
_status_cache_ts: float = 0.0
_STATUS_CACHE_TTL = 60.0  # seconds
_status_cache_lock = _asyncio.Lock()


async def _is_status_page_flag_enabled(db: AsyncSession) -> bool:
    """Check whether the integration_status_page_v1 feature flag is on."""
    return await _is_flag_enabled(db, "integration_status_page_v1")


async def _build_status_response(db: AsyncSession) -> dict:
    """Build the public status response (cached for 60 s)."""
    from datetime import UTC, datetime

    from sqlalchemy import desc, select

    from app.models.integration_models import IntegrationIncident
    from app.services.integration_health_service import IntegrationHealthService
    from app.services.integration_manifest_service import manifest_service

    service = IntegrationHealthService(db)
    latest = await service.get_all_latest()

    integrations = []
    for slug in manifest_service.slug_list:
        manifest = manifest_service.get(slug)
        record = latest.get(slug)
        uptime = await service.compute_uptime_pct(slug)
        integrations.append(
            {
                "slug": slug,
                "name": manifest["name"] if manifest else slug,
                "status": record.status if record else "unknown",
                "uptime_30d": uptime,
                "last_checked": record.checked_at.isoformat() if record else None,
            }
        )

    # Fetch recent open incidents (last 30 days)
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(days=30)
    incident_result = await db.execute(
        select(IntegrationIncident)
        .where(IntegrationIncident.created_at >= cutoff)
        .where(IntegrationIncident.status != "resolved")
        .order_by(desc(IntegrationIncident.created_at))
        .limit(20)
    )
    incidents = [
        {
            "integration_slug": inc.integration_slug,
            "severity": inc.severity,
            "title": inc.title,
            "status": inc.status,
            "created_at": inc.created_at.isoformat(),
            "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
        }
        for inc in incident_result.scalars().all()
    ]

    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "integrations": integrations,
        "incidents": incidents,
    }


async def _get_cached_status(db: AsyncSession) -> dict:
    """Return status response from cache, refreshing if stale."""
    global _status_cache, _status_cache_ts
    now = time.monotonic()
    if _status_cache is not None and (now - _status_cache_ts) < _STATUS_CACHE_TTL:
        return _status_cache
    async with _status_cache_lock:
        now = time.monotonic()
        if _status_cache is not None and (now - _status_cache_ts) < _STATUS_CACHE_TTL:
            return _status_cache
        result = await _build_status_response(db)
        _status_cache = result
        _status_cache_ts = time.monotonic()
        return result


@router.get("/status", tags=["public"])
async def public_status(
    db: AsyncSession = Depends(get_db),
):
    """Public status page endpoint — no auth required.

    Returns health status for all integrations plus recent incidents.
    Cached for 60 seconds.  Gated by the ``integration_status_page_v1``
    feature flag.
    """
    if not await _is_status_page_flag_enabled(db):
        raise HTTPException(status_code=404, detail="Status page not available")
    return await _get_cached_status(db)


@router.get("/{slug}/health")
async def get_integration_health(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Returns detailed health status for a single integration."""
    from app.services.integration_health_service import IntegrationHealthService
    from app.services.integration_manifest_service import manifest_service

    if not await _is_health_flag_enabled(db):
        raise HTTPException(status_code=404, detail="Health status not available")

    manifest = manifest_service.get(slug)
    if not manifest:
        raise HTTPException(status_code=404, detail="Integration not found")

    service = IntegrationHealthService(db)
    record = await service.get_latest_status(slug)
    history = await service.get_history(slug, limit=24)
    uptime = await service.compute_uptime_pct(slug)

    return {
        "slug": slug,
        "name": manifest["name"],
        "trust_level": manifest.get("trust_level", "verified"),
        "status": record.status if record else "unknown",
        "latency_ms": record.latency_ms if record else None,
        "status_code": record.status_code if record else None,
        "error_message": record.error_message if record else None,
        "uptime_30d": uptime,
        "last_checked": record.checked_at.isoformat() if record else None,
        "history": [
            {
                "status": r.status,
                "latency_ms": r.latency_ms,
                "checked_at": r.checked_at.isoformat(),
            }
            for r in history
        ],
    }


# ── Playground Endpoints (Phase 4) ────────────────────────────────────────


class PlaygroundActionRequest(BaseModel):
    """Request body for playground actions."""

    params: dict = {}


async def _is_playground_flag_enabled(db: AsyncSession) -> bool:
    """Check whether the integration_playground_v1 feature flag is on."""
    return await _is_flag_enabled(db, "integration_playground_v1")


@router.post("/{slug}/playground/{action}")
async def playground_action(
    slug: str,
    action: str,
    body: PlaygroundActionRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a demo action using Flowmanner's sandbox credentials.

    Rate-limited to 5 requests/minute per user per integration.
    Returns the real or mock API response for display.
    Gated by the ``integration_playground_v1`` feature flag.
    """
    from app.services.integration_manifest_service import manifest_service
    from app.services.integration_playground_service import (
        check_playground_rate_limit,
        execute_playground_action,
    )

    if not await _is_playground_flag_enabled(db):
        raise HTTPException(status_code=404, detail="Playground not available")

    manifest = manifest_service.get(slug)
    if not manifest:
        raise HTTPException(status_code=404, detail="Integration not found")

    playground = manifest.get("playground", {})
    if not playground.get("enabled"):
        raise HTTPException(
            status_code=404,
            detail="Playground not available for this integration",
        )

    # Validate action is in the manifest's demo_actions
    demo_actions = playground.get("demo_actions", [])
    valid_actions = {da["action"] for da in demo_actions}
    if action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown playground action '{action}'. Valid: {sorted(valid_actions)}",
        )

    # Rate limit: 5 per minute per user per integration
    from app.core.demo_credentials import get_demo_credential

    cred = get_demo_credential(slug)
    rate_limit = cred.rate_limit if cred else 5
    allowed, _remaining = check_playground_rate_limit(
        user_id=str(user.id),
        slug=slug,
        max_requests=rate_limit,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Playground rate limit exceeded. Try again in a minute.",
        )

    params = body.params if body else {}
    result = await execute_playground_action(
        slug=slug,
        action=action,
        params=params,
    )
    return result


@router.get("/{slug}/playground/actions")
async def list_playground_actions(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List available playground actions for an integration."""
    from app.services.integration_manifest_service import manifest_service

    if not await _is_playground_flag_enabled(db):
        raise HTTPException(status_code=404, detail="Playground not available")

    manifest = manifest_service.get(slug)
    if not manifest:
        raise HTTPException(status_code=404, detail="Integration not found")

    playground = manifest.get("playground", {})
    return {
        "slug": slug,
        "enabled": playground.get("enabled", False),
        "actions": playground.get("demo_actions", []),
    }


# ── Usage Analytics Endpoints (Phase 3) ──────────────────────────────────


async def _is_usage_flag_enabled(db: AsyncSession) -> bool:
    """Check whether the integration_usage_v1 feature flag is on."""
    return await _is_flag_enabled(db, "integration_usage_v1")


@router.get("/{slug}/usage")
async def get_integration_usage(
    slug: str,
    period: str = Query("30d", description="Time period: 7d, 30d, 90d"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns usage analytics for a user's connection to an integration.

    Includes call counts, success rate, latency stats, and top actions.
    Gated by the ``integration_usage_v1`` feature flag.
    """
    from app.services.integration_manifest_service import manifest_service
    from app.services.integration_usage_service import IntegrationUsageService

    if not await _is_usage_flag_enabled(db):
        raise HTTPException(status_code=404, detail="Usage analytics not available")

    if period not in ("7d", "30d", "90d"):
        raise HTTPException(status_code=400, detail="period must be 7d, 30d, or 90d")

    manifest = manifest_service.get(slug)
    if not manifest:
        raise HTTPException(status_code=404, detail="Integration not found")

    service = IntegrationUsageService(db)
    stats = await service.get_usage_stats(
        user_id=user.id,
        integration_slug=slug,
        period=period,
    )
    return stats
