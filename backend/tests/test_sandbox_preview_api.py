"""Tests for GET /api/v1/sandbox/{sandbox_id}/preview.

Covers:
- Happy path (sandbox running, preview URL available)
- Sandbox starting (no preview URL yet)
- Sandbox not found (404)
- URL rewriting from localhost to public domain
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.sandbox_preview import router
from app.integrations.sandboxd_client import (
    rewrite_sandboxd_url as _rewrite_preview_url,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def test_app():
    _app = FastAPI()
    _app.include_router(router, prefix="/api/v1")

    # Stub auth dependency so tests don't need real JWT
    from app.api.deps import get_current_user

    async def _fake_user():
        return type("User", (), {"id": "test-user", "email": "t@t.com"})()

    _app.dependency_overrides[get_current_user] = _fake_user
    return _app


@pytest.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_preview_running_sandbox(client):
    """Running sandbox returns preview URL rewritten to public domain."""
    mock_info = {
        "id": "sb-abc123",
        "status": "running",
        "preview": {
            "url": "http://s-abc123-3000.preview.localhost",
            "status": "running",
        },
    }
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_info
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-abc123/preview")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sandbox_id"] == "sb-abc123"
    assert data["status"] == "running"
    assert data["preview_url"] == "https://s-abc123-3000.preview.flowmanner.com"
    assert data["preview_status"] == "running"


@pytest.mark.anyio
async def test_preview_starting_sandbox(client):
    """Starting sandbox returns null preview_url."""
    mock_info = {
        "id": "sb-def456",
        "status": "starting",
        "preview": {
            "url": None,
            "status": "starting",
        },
    }
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_info
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-def456/preview")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sandbox_id"] == "sb-def456"
    assert data["status"] == "starting"
    assert data["preview_url"] is None
    assert data["preview_status"] == "starting"


@pytest.mark.anyio
async def test_preview_no_preview_field(client):
    """Sandbox with no preview field returns nulls."""
    mock_info = {
        "id": "sb-no-preview",
        "status": "running",
    }
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_info
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-no-preview/preview")

    assert resp.status_code == 200
    data = resp.json()
    assert data["preview_url"] is None
    assert data["preview_status"] is None


# ── Error cases ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_preview_sandbox_not_found(client):
    """Sandbox not found returns 404."""
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("404 Not Found")
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-nonexistent/preview")

    assert resp.status_code == 404
    assert "Sandbox not found" in resp.json()["detail"]


@pytest.mark.anyio
async def test_preview_sandboxd_unavailable(client):
    """sandboxd unreachable returns 404."""
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.side_effect = ConnectionError("Connection refused")
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-abc/preview")

    assert resp.status_code == 404


# ── URL rewriting ─────────────────────────────────────────────────────


def test_rewrite_localhost_url():
    """Rewrites localhost preview URL to public domain."""
    result = _rewrite_preview_url("http://s-abc123-3000.preview.localhost")
    assert result == "https://s-abc123-3000.preview.flowmanner.com"


def test_rewrite_url_with_port():
    """Handles URL with port number."""
    result = _rewrite_preview_url("http://s-abc123-3000.preview.localhost:8080")
    assert result == "https://s-abc123-3000.preview.flowmanner.com"


def test_rewrite_already_public_url():
    """Already-public URL stays as-is (just forces HTTPS)."""
    result = _rewrite_preview_url("http://s-abc123-3000.preview.flowmanner.com")
    assert result == "https://s-abc123-3000.preview.flowmanner.com"


def test_rewrite_https_url():
    """HTTPS URL is preserved."""
    result = _rewrite_preview_url("https://s-abc123-3000.preview.localhost")
    assert result == "https://s-abc123-3000.preview.flowmanner.com"


def test_rewrite_malformed_url():
    """Malformed URL is returned as-is."""
    result = _rewrite_preview_url("not-a-url")
    assert result == "not-a-url"
