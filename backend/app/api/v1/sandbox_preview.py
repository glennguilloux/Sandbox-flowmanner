"""sandboxd Preview API — return live preview URL for a sandbox.

GET /api/v1/sandbox/{sandbox_id}/preview → {preview_url, status, sandbox_id}

This endpoint wraps ``SandboxdClient.get()`` (Phase 1) and returns the
preview URL that Traefik exposes for the running dev server inside the
sandbox container.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response

from app.api.deps import get_current_user
from app.config import settings
from app.integrations.sandboxd_client import get_sandboxd_client

logger = logging.getLogger(__name__)

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
    # configured public preview domain.  sandboxd may return URLs like
    # ``http://s-abc-3000.preview.localhost`` — we rewrite to
    # ``https://s-abc-3000.preview.flowmanner.com``.
    raw_url = preview.get("url")
    public_url = _rewrite_preview_url(raw_url) if raw_url else None

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


async def _authenticate_preview_request(req: Request) -> str | None:
    """Authenticate a preview request via Bearer token or cookie.

    Returns the user_id if authenticated, None otherwise.
    """
    from app.api.deps import decode_access_token
    from app.database import get_db_session
    from app.services.auth_service import get_user_by_id

    token: str | None = None

    # 1. Try Authorization header first
    auth_header = req.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    # 2. Fall back to fm_refresh_token cookie
    if not token:
        token = req.cookies.get("fm_refresh_token")

    if not token:
        return None

    # Decode and validate
    user_id = decode_access_token(token)
    if user_id is None:
        return None

    try:
        async for db in get_db_session():
            user = await get_user_by_id(db, int(user_id))
            if user and user.is_active:
                return str(user.id)
    except (ValueError, TypeError, KeyError):
        logger.warning("forward-auth user lookup failed for %s", user_id)

    return None


def _rewrite_preview_url(raw_url: str) -> str:
    """Rewrite sandboxd preview URL to the public preview domain.

    sandboxd returns URLs like ``http://s-abc-3000.preview.localhost``
    (or ``https://...`` when TLS is enabled).  We rewrite the host to
    ``<subdomain>.preview.flowmanner.com`` and force HTTPS.
    """
    # Extract the subdomain prefix (e.g. "s-abc-3000") from the URL
    match = re.search(r"://([^/]+)", raw_url)
    if not match:
        return raw_url

    host = match.group(1)
    # Strip port if present
    subdomain = host.split(":")[0]
    # Remove any existing ".preview" suffix (with optional domain after it)
    # to get just the sandbox prefix (e.g. "s-abc-3000")
    subdomain = re.sub(r"\.preview.*$", "", subdomain)

    # SANDBOXD_PREVIEW_DOMAIN is already "preview.flowmanner.com"
    domain = settings.SANDBOXD_PREVIEW_DOMAIN or "preview.flowmanner.com"
    return f"https://{subdomain}.{domain}"
