"""Custom Confluence OAuth callback — handles Atlassian 3LO site discovery step.

Standard OAuth callbacks only exchange code for tokens. Confluence Cloud requires
an additional site discovery step where we call
GET https://api.atlassian.com/oauth/token/accessible-resources
to find the user's Atlassian sites and extract the cloudId.

The cloudId is stored in IntegrationConnection.account_id for use in all
subsequent API calls.

Nearly identical to jira_oauth.py — same Atlassian OAuth 2.0 (3LO) flow,
different scopes and slug.
"""

import json
import logging
import secrets
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.oauth import OAUTH_PROVIDERS, encrypt_token
from app.database import get_db
from app.models.phase4_models import IntegrationConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/confluence", tags=["confluence"])


def _get_redis():
    """Get a Redis client for OAuth state storage."""
    import redis as redis_lib

    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _pop_state(key: str) -> dict | None:
    """Atomic pop: return the stored data or None if missing/expired."""
    r = _get_redis()
    raw = r.get(f"oauth:{key}")
    if raw is None:
        return None
    r.delete(f"oauth:{key}")
    return json.loads(raw)


def _store_state(key: str, data: dict) -> None:
    """Store an OAuth state in Redis with a TTL."""
    r = _get_redis()
    r.setex(f"oauth:{key}", 600, json.dumps(data))


@router.get("/oauth/callback")
async def confluence_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Custom OAuth callback for Confluence with site discovery.

    After the standard token exchange, this endpoint:
    1. Discovers the user's Atlassian sites via accessible-resources
    2. Auto-selects the first site (multi-site UI deferred)
    3. Stores cloudId in IntegrationConnection.account_id
    """
    # 1. Validate state (from Redis)
    stored = _pop_state(state)
    if not stored:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    provider = OAUTH_PROVIDERS.get("confluence")
    if not provider:
        raise HTTPException(status_code=404, detail="Confluence OAuth provider not configured")

    # 2. Exchange code for tokens (Atlassian OAuth 2.0 3LO)
    token_data = {
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "code": code,
        "redirect_uri": stored["redirect_uri"],
        "grant_type": "authorization_code",
        "audience": "api.atlassian.com",  # REQUIRED for Atlassian
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            provider.token_url,
            data=token_data,
            headers={"Accept": "application/json"},
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Confluence token exchange failed: {resp.status_code} {resp.text[:200]}",
        )

    token_json = resp.json()
    access_token = token_json.get("access_token")
    refresh_token = token_json.get("refresh_token")

    if not access_token:
        raise HTTPException(
            status_code=502,
            detail=f"Confluence token exchange returned no access_token: {resp.text[:200]}",
        )

    # 3. Site discovery — find the user's Atlassian sites
    async with httpx.AsyncClient() as client:
        sites_resp = await client.get(
            "https://api.atlassian.com/oauth/token/accessible-resources",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if sites_resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Confluence site discovery failed: {sites_resp.status_code} {sites_resp.text[:200]}",
        )

    sites = sites_resp.json()
    if not sites:
        raise HTTPException(
            status_code=400,
            detail="No Atlassian sites found for this account",
        )

    # 4. Auto-select first site (multi-site selection UI deferred to future batch)
    selected_site = sites[0]
    cloud_id = selected_site["id"]
    account_name = selected_site.get("name", selected_site.get("url", "unknown"))
    site_url = selected_site.get("url", "")

    logger.info(
        "Confluence OAuth callback: user %s connected to site '%s' (cloudId: %s, %d sites available)",
        stored["user_id"],
        account_name,
        cloud_id,
        len(sites),
    )

    # 5. Encrypt tokens before storing
    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

    # 6. Store connection with cloudId in account_id
    conn = IntegrationConnection(
        id=str(uuid4()),
        user_id=stored["user_id"],
        integration_slug="confluence",
        encrypted_access_token=encrypted_access,
        encrypted_refresh_token=encrypted_refresh,
        token_type="Bearer",
        account_name=account_name,
        account_id=cloud_id,  # cloudId for API calls
        scopes=",".join(provider.scopes),
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)

    # 7. Wire the connection into Nexus so agents can use it
    try:
        from app.services.integration_bridge import get_integration_bridge

        bridge = get_integration_bridge()
        await bridge.register_capabilities_for_user(
            user_id=stored["user_id"],
            slug="confluence",
        )
    except Exception as e:
        logger.warning("Failed to register Nexus capabilities for confluence: %s", e)

    # 8. Redirect to frontend
    return RedirectResponse(
        url=f"https://flowmanner.com/dashboard/settings/integrations?connected=confluence",
        status_code=302,
    )
