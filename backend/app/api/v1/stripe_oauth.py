"""Custom Stripe OAuth callback — handles stripe_user_id extraction.

Standard OAuth callbacks only exchange code for tokens. Stripe Connect returns
a stripe_user_id (e.g., acct_1234abcd) in the token response that must be
stored in IntegrationConnection.account_id for agent reference.

This is simpler than Jira's callback (no site discovery step). Just:
1. Validate state (from Redis)
2. Exchange code for tokens
3. Extract stripe_user_id from response
4. Encrypt tokens and store connection with account_id = stripe_user_id
5. Register Nexus capabilities
6. Redirect to frontend
"""

import json
import logging
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

router = APIRouter(prefix="/stripe", tags=["stripe"])


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


@router.get("/oauth/callback")
async def stripe_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Custom OAuth callback for Stripe with stripe_user_id extraction.

    After the standard token exchange, this endpoint:
    1. Extracts stripe_user_id from the token response
    2. Stores it in IntegrationConnection.account_id
    """
    # 1. Validate state (from Redis)
    stored = _pop_state(state)
    if not stored:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    provider = OAUTH_PROVIDERS.get("stripe")
    if not provider:
        raise HTTPException(status_code=404, detail="Stripe OAuth provider not configured")

    # 2. Exchange code for tokens (Stripe Connect OAuth)
    token_data = {
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "code": code,
        "redirect_uri": stored["redirect_uri"],
        "grant_type": "authorization_code",
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
            detail=f"Stripe token exchange failed: {resp.status_code} {resp.text[:200]}",
        )

    token_json = resp.json()
    access_token = token_json.get("access_token")
    refresh_token = token_json.get("refresh_token")

    if not access_token:
        raise HTTPException(
            status_code=502,
            detail=f"Stripe token exchange returned no access_token: {resp.text[:200]}",
        )

    # 3. Extract stripe_user_id from token response
    stripe_user_id = token_json.get("stripe_user_id", "")
    stripe_publishable_key = token_json.get("stripe_publishable_key", "")
    livemode = token_json.get("livemode", False)
    scope = token_json.get("scope", "")

    account_name = stripe_user_id
    if stripe_publishable_key:
        mode = "live" if livemode else "test"
        account_name = f"{stripe_user_id} ({mode})"

    logger.info(
        "Stripe OAuth callback: user %s connected to account %s (livemode=%s, scope=%s)",
        stored["user_id"],
        stripe_user_id,
        livemode,
        scope,
    )

    # 4. Encrypt tokens before storing
    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

    # 5. Store connection with stripe_user_id in account_id
    conn = IntegrationConnection(
        id=str(uuid4()),
        user_id=stored["user_id"],
        integration_slug="stripe",
        encrypted_access_token=encrypted_access,
        encrypted_refresh_token=encrypted_refresh,
        token_type="Bearer",
        account_name=account_name,
        account_id=stripe_user_id,  # e.g. acct_1234abcd
        scopes=scope,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)

    # 6. Wire the connection into Nexus so agents can use it
    try:
        from app.services.integration_bridge import get_integration_bridge

        bridge = get_integration_bridge()
        await bridge.register_capabilities_for_user(
            user_id=stored["user_id"],
            slug="stripe",
        )
    except Exception as e:
        logger.warning("Failed to register Nexus capabilities for stripe: %s", e)

    # 7. Redirect to frontend
    return RedirectResponse(
        url=f"https://flowmanner.com/dashboard/settings/integrations?connected=stripe",
        status_code=302,
    )
