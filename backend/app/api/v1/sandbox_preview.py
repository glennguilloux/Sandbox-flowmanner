"""sandboxd Preview API — return live preview URL for a sandbox.

GET /api/v1/sandbox/{sandbox_id}/preview → {preview_url, status, sandbox_id}

This endpoint wraps ``SandboxdClient.get()`` (Phase 1) and returns the
preview URL that Traefik exposes for the running dev server inside the
sandbox container.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.requests import Request  # noqa: TC002 — needed at runtime for FastAPI DI
from starlette.responses import Response

from app.api.deps import get_current_user
from app.config import settings
from app.integrations.sandboxd_client import get_sandboxd_client, rewrite_sandboxd_url

logger = logging.getLogger(__name__)

# ── Forward-auth response cache ────────────────────────────────────────
# Traefik hits /api/sandbox/forward-auth on every request to a sandbox
# preview URL (~13 req/30s).  Caching successful auth results avoids a
# DB round-trip per request.  Entries expire after _AUTH_CACHE_TTL seconds.
_AUTH_CACHE_TTL = 30  # seconds — matches Traefik polling interval
_AUTH_CACHE_MAX_SIZE = 256  # max cached tokens
_auth_cache: dict[str, tuple[str, float]] = {}  # token_hash → (user_id, expires_at)


def _token_hash(token: str) -> str:
    """Hash a token for use as a cache key (never store raw tokens in memory)."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _cache_get(token: str) -> str | None:
    """Return cached user_id if the token is in the cache and not expired."""
    key = _token_hash(token)
    entry = _auth_cache.get(key)
    if entry is None:
        return None
    user_id, expires_at = entry
    if time.monotonic() > expires_at:
        _auth_cache.pop(key, None)
        return None
    return user_id


def _cache_set(token: str, user_id: str) -> None:
    """Cache a successful auth result."""
    # Evict oldest entries if cache is full
    if len(_auth_cache) >= _AUTH_CACHE_MAX_SIZE:
        # Remove expired entries first, then oldest if still full
        now = time.monotonic()
        expired = [k for k, (_, exp) in _auth_cache.items() if now > exp]
        for k in expired:
            _auth_cache.pop(k, None)
        if len(_auth_cache) >= _AUTH_CACHE_MAX_SIZE:
            # Drop the oldest entry by expiry time
            oldest_key = min(_auth_cache, key=lambda k: _auth_cache[k][1])
            _auth_cache.pop(oldest_key, None)
    _auth_cache[_token_hash(token)] = (user_id, time.monotonic() + _AUTH_CACHE_TTL)


router = APIRouter(prefix="/sandbox", tags=["sandbox-preview"])


# ── Response schema ───────────────────────────────────────────────────


class SandboxPreviewResponse(BaseModel):
    """Preview info for a running sandbox."""

    sandbox_id: str
    status: str
    preview_url: str | None = None
    preview_status: str | None = None


# ── Route ─────────────────────────────────────────────────────────────


@router.get(
    "/{sandbox_id}/preview",
    response_model=SandboxPreviewResponse,
)
async def get_preview_url(
    sandbox_id: str,
    _current_user=Depends(get_current_user),
) -> SandboxPreviewResponse:
    """Return the live preview info for a sandbox.

    Proxies to sandboxd's ``GET /v1/sandboxes/{id}`` and extracts the
    ``preview`` sub-object.  The preview URL format is::

        s-<sandbox-id>-<port>.preview.<domain>

    Each exposed port gets its own subdomain; Traefik routes based on
    the ``Host`` header.
    """
    client = get_sandboxd_client()

    try:
        info = await client.get(sandbox_id)
    except Exception as exc:
        logger.warning("sandboxd get(%s) failed: %s", sandbox_id, exc)
        raise HTTPException(
            status_code=404,
            detail=f"Sandbox not found: {exc}",
        ) from exc

    preview: dict = info.get("preview") or {}

    # Rewrite the preview URL from sandboxd's internal domain to the
    # configured public preview domain.  Uses the shared rewriter from
    # sandboxd_preview.py so the tool and API always agree.
    raw_url = preview.get("url")
    public_url = rewrite_sandboxd_url(raw_url) if raw_url else None

    return SandboxPreviewResponse(
        sandbox_id=sandbox_id,
        status=info.get("status", "unknown"),
        preview_url=public_url,
        preview_status=preview.get("status"),
    )


# ── Helpers ───────────────────────────────────────────────────────────


# ── Forward Auth (Traefik forward-auth endpoint) ─────────────────────


@router.api_route(
    "/forward-auth",
    methods=["GET", "HEAD"],
)
async def sandbox_forward_auth(
    request: Request,
):
    """Traefik forward-auth endpoint for gating sandbox preview URLs.

    Traefik calls this endpoint before proxying to a sandbox container.
    Checks for a valid FlowManner session via:
      1. ``Authorization: Bearer <token>`` header
      2. ``fm_refresh_token`` httpOnly cookie

    Returns 200 + ``X-Forwarded-User`` if authenticated, 401 if not.
    Traefik denies the request on non-2xx responses.
    """
    user_id = await _authenticate_preview_request(request)
    if user_id:
        return Response(
            status_code=200,
            headers={"X-Forwarded-User": str(user_id)},
        )
    return Response(status_code=401)


def _is_jwt(token: str) -> bool:
    """Heuristic: JWTs contain dots and are 50+ chars; UUIDs are 36-char hex with no dots."""
    return "." in token and len(token) > 50


async def _authenticate_preview_request(req: Request) -> str | None:
    """Authenticate a preview request via Bearer token or cookie.

    Token source determines the validation path:
    - ``Authorization: Bearer`` header → always a JWT (``decode_access_token``)
    - ``?token=`` query param → JWT if it looks like one, else DB lookup
    - ``refresh_token`` / ``fm_refresh_token`` cookie → UUID refresh token →
      DB lookup via ``get_refresh_token``

    Successful results are cached for ``_AUTH_CACHE_TTL`` seconds to avoid
    redundant DB round-trips on repeated Traefik forward-auth requests.

    Returns the ``user_id`` as a string if authenticated, ``None`` otherwise.
    """
    from app.api.deps import decode_access_token
    from app.database import get_db_session
    from app.services.auth_service import get_refresh_token, get_user_by_id

    token: str | None = None

    # 1. Try Authorization header first (always a JWT)
    auth_header = req.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    # 2. Try ?token= query parameter
    if not token:
        token = req.query_params.get("token")

    # 3. Fall back to httpOnly cookies (v3 refresh_token + legacy fm_refresh_token)
    if not token:
        token = req.cookies.get("refresh_token") or req.cookies.get("fm_refresh_token")

    if not token:
        return None

    # ── Check cache first ────────────────────────────────────────────
    cached = _cache_get(token)
    if cached is not None:
        return cached

    # ── Branch on token source ────────────────────────────────────────
    # Bearer header (index 1) always arrives here as a JWT.
    # Query param (index 2) may be a JWT (new path) or UUID (legacy).
    # Cookie (index 3) is always a UUID refresh token.

    user_id_str: str | None = None

    # If the token looks like a JWT, decode it directly — no DB roundtrip.
    if _is_jwt(token):
        user_id = decode_access_token(token)
        if user_id is None:
            return None
        try:
            async for db in get_db_session():
                user = await get_user_by_id(db, int(user_id))
                if user and user.is_active:
                    user_id_str = str(user.id)
        except (ValueError, TypeError, KeyError):
            logger.warning("forward-auth user lookup failed for %s", user_id)
    else:
        # UUID refresh token — resolve via DB lookup.
        try:
            async for db in get_db_session():
                record = await get_refresh_token(db, token)
                if record is None:
                    return None
                # get_refresh_token already filters is_revoked == False
                if record.expires_at and record.expires_at < datetime.now(UTC).replace(tzinfo=None):
                    return None
                user = await get_user_by_id(db, record.user_id)
                if user and user.is_active:
                    user_id_str = str(user.id)
        except Exception:
            logger.warning("forward-auth refresh-token lookup failed", exc_info=True)

    # ── Cache successful result ──────────────────────────────────────
    if user_id_str is not None:
        _cache_set(token, user_id_str)

    return user_id_str
