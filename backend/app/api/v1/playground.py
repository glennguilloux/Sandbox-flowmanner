"""Playground API — anonymous sandbox creation, claiming, and file browsing."""

from __future__ import annotations

import logging
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.requests import Request

from app.api.deps import get_current_user, get_current_user_optional
from app.config import settings
from app.database import get_db
from app.services.playground_service import PlaygroundService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/playground", tags=["playground"])
_playground_service = PlaygroundService()


# ── Response models ─────────────────────────────────────────────────


class PlaygroundSandboxResponse(BaseModel):
    sandbox_id: str
    session_token: str
    status: str
    template: str
    expires_at: str
    preview_url: str | None = None
    claimed: bool = False


class ClaimRequest(BaseModel):
    session_token: str = Field(..., min_length=8)


class ClaimResponse(BaseModel):
    sandbox_id: str
    claimed: bool = True
    message: str = "Sandbox claimed successfully"


class FileEntry(BaseModel):
    name: str
    path: str
    type: str  # "file" or "directory"
    size: int | None = None
    modified_at: str | None = None


class FileContentResponse(BaseModel):
    path: str
    content: str
    sandbox_id: str


# ── Helper ──────────────────────────────────────────────────────────


def _rewrite_preview_url(raw_url: str | None) -> str | None:
    """Rewrite sandboxd internal URL to public preview domain.

    Mirrors the logic in sandbox_preview.py.
    """
    if not raw_url:
        return None

    match = re.search(r"://([^/]+)", raw_url)
    if not match:
        return raw_url

    host = match.group(1)
    subdomain = host.split(":")[0]
    subdomain = re.sub(r"\.preview.*$", "", subdomain)

    domain = settings.SANDBOXD_PREVIEW_DOMAIN or "preview.flowmanner.com"
    return f"https://{subdomain}.{domain}"


# ── Routes ──────────────────────────────────────────────────────────


@router.post("/sandboxes", response_model=PlaygroundSandboxResponse)
async def create_playground_sandbox(
    request: Request,
    template: str = Query("react-standard"),
    db=Depends(get_db),
):
    """Create an anonymous playground sandbox. No auth required. Rate-limited."""
    client_ip = request.client.host if request.client else None

    # Check cooldown: max 1 sandbox per IP per 60 seconds
    if client_ip:
        recent = await _playground_service.count_recent_by_ip(
            client_ip,
            minutes=1,
            db=db,
        )
        if recent >= 1:
            raise HTTPException(
                status_code=429,
                detail="Too many sandbox requests. Please wait before creating another.",
            )

    # Check hourly cap: max 10 anonymous sandboxes per IP per hour
    if client_ip:
        hourly = await _playground_service.count_recent_by_ip(
            client_ip,
            minutes=60,
            db=db,
        )
        if hourly >= 10:
            raise HTTPException(
                status_code=429,
                detail="Hourly sandbox limit reached. Try again later.",
            )

    try:
        pg = await _playground_service.create_anonymous_sandbox(
            db=db,
            template=template,
            client_ip=client_ip,
        )
    except Exception as e:
        logger.error("Failed to create playground sandbox: %s", e)
        raise HTTPException(status_code=503, detail="Sandbox provisioning failed")

    # Get preview URL from sandboxd
    raw_url = None
    try:
        sandbox_info = await _playground_service._client.get(pg.sandbox_id)
        raw_url = sandbox_info.get("preview", {}).get("url") or sandbox_info.get("url")
    except Exception:
        pass

    return PlaygroundSandboxResponse(
        sandbox_id=pg.sandbox_id,
        session_token=pg.session_token,
        status=pg.status,
        template=pg.template,
        expires_at=pg.expires_at.isoformat(),
        preview_url=_rewrite_preview_url(raw_url),
        claimed=pg.user_id is not None,
    )


@router.get("/sandboxes/{sandbox_id}", response_model=PlaygroundSandboxResponse)
async def get_playground_sandbox(
    sandbox_id: str,
    db=Depends(get_db),
):
    """Get playground sandbox status by sandboxd container ID."""
    pg = await _playground_service.get_by_sandbox_id(sandbox_id, db=db)
    if pg is None:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    raw_url = None
    try:
        sandbox_info = await _playground_service._client.get(pg.sandbox_id)
        raw_url = sandbox_info.get("preview", {}).get("url") or sandbox_info.get("url")
    except Exception:
        pass

    return PlaygroundSandboxResponse(
        sandbox_id=pg.sandbox_id,
        session_token=pg.session_token,
        status=pg.status,
        template=pg.template,
        expires_at=pg.expires_at.isoformat(),
        preview_url=_rewrite_preview_url(raw_url),
        claimed=pg.user_id is not None,
    )


@router.post("/sandboxes/claim", response_model=ClaimResponse)
async def claim_playground_sandbox(
    body: ClaimRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Claim an anonymous playground sandbox. Requires authentication."""
    try:
        pg = await _playground_service.claim_sandbox(
            body.session_token,
            user.id,
            db=db,
        )
        return ClaimResponse(sandbox_id=pg.sandbox_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sandboxes/{sandbox_id}/files", response_model=list[FileEntry])
async def list_sandbox_files(
    sandbox_id: str,
    path: str = Query(""),
    user=Depends(get_current_user_optional),
    db=Depends(get_db),
):
    """List files in a playground sandbox.

    Requires session token via query param for anonymous sandboxes,
    or auth for claimed sandboxes.
    """
    pg = await _playground_service.get_by_sandbox_id(sandbox_id, db=db)
    if pg is None:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    # Anonymous sandboxes: no file access without auth
    if pg.is_anonymous and user is None:
        raise HTTPException(
            status_code=403,
            detail="File access requires claiming the sandbox",
        )

    try:
        entries = await _playground_service.list_files(sandbox_id, path, db=db)
        return [
            FileEntry(
                name=e.get("name", ""),
                path=e.get("path", ""),
                type=e.get("type", "file"),
                size=e.get("size"),
                modified_at=e.get("modified_at"),
            )
            for e in entries
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sandboxes/{sandbox_id}/files/read", response_model=FileContentResponse)
async def read_sandbox_file(
    sandbox_id: str,
    path: str = Query(..., description="File path relative to workspace"),
    user=Depends(get_current_user_optional),
    db=Depends(get_db),
):
    """Read a file from a playground sandbox workspace."""
    pg = await _playground_service.get_by_sandbox_id(sandbox_id, db=db)
    if pg is None:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    if pg.is_anonymous and user is None:
        raise HTTPException(
            status_code=403,
            detail="File access requires claiming the sandbox",
        )

    try:
        content = await _playground_service.read_file(sandbox_id, path, db=db)
        return FileContentResponse(path=path, content=content, sandbox_id=sandbox_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
