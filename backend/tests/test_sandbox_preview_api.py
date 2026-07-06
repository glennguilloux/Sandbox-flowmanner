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
    assert data["preview_url"] == "https://s-abc123-8081.preview.flowmanner.com"
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
    """sandboxd unreachable returns 502."""
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.side_effect = ConnectionError("Connection refused")
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-abc/preview")

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["error"] == "sandboxd_unreachable"
    assert "request_id" in detail


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


# ── Port normalization contract tests ──────────────────────────────────
#
# The port normalization regex lives in the API endpoint
# (sandbox_preview.py) and runs BEFORE rewrite_sandboxd_url.  These
# tests go through the full endpoint to verify the regex turns stale
# template ports into the canonical serve port (settings.SANDBOXD_PREVIEW_PORT).
#
# rewrite_sandboxd_url itself does NOT normalize ports — it preserves
# whatever port is in the subdomain and only swaps domain + scheme.
# The tests above (test_rewrite_*) document that contract.


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("raw_port", "expected_port"),
    [
        ("3000", "8081"),  # stale python-img template default
        ("8080", "8081"),  # stale react-standard template default
        ("5173", "8081"),  # Vite dev server default
        ("3001", "8081"),  # Express alt port
        ("8081", "8081"),  # already correct — should be idempotent
        ("4173", "8081"),  # Vite preview port
    ],
    ids=["stale-3000", "stale-8080", "vite-5173", "express-3001", "already-8081", "vite-preview-4173"],
)
async def test_port_normalization_through_endpoint(client, raw_port, expected_port):
    """Stale template ports are normalized to SANDBOXD_PREVIEW_PORT via the
    endpoint's regex, then domain-rewritten by rewrite_sandboxd_url.

    This is the contract test that guards the port-mismatch regression:
    sandboxd templates report their own default port (3000, 8080, 5173,
    etc.) but the actual http.server started by entrypoint-wrapper.sh
    listens on SANDBOXD_PREVIEW_PORT (default 8081).  If the regex or
    the setting drifts, these tests fail loudly.
    """
    mock_info = {
        "id": "sb-porttest",
        "status": "running",
        "preview": {
            "url": f"http://s-abc123-{raw_port}.preview.localhost",
            "status": "running",
        },
    }
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_info
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-porttest/preview")

    assert resp.status_code == 200
    data = resp.json()
    assert (
        data["preview_url"] == f"https://s-abc123-{expected_port}.preview.flowmanner.com"
    ), f"Port {raw_port} from sandboxd should be normalized to {expected_port}"


@pytest.mark.anyio
async def test_port_normalization_custom_setting(client):
    """When SANDBOXD_PREVIEW_PORT is overridden, the endpoint normalizes
    to the custom port instead of the hardcoded 8081."""
    mock_info = {
        "id": "sb-custom",
        "status": "running",
        "preview": {
            "url": "http://s-abc123-3000.preview.localhost",
            "status": "running",
        },
    }
    with (
        patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client,
        patch("app.api.v1.sandbox_preview.settings") as mock_settings,
    ):
        mock_settings.SANDBOXD_PREVIEW_PORT = 9999
        mock_settings.SANDBOXD_PREVIEW_DOMAIN = "preview.flowmanner.com"
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_info
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-custom/preview")

    assert resp.status_code == 200
    assert resp.json()["preview_url"] == "https://s-abc123-9999.preview.flowmanner.com"


def test_rewrite_preserves_custom_port():
    """rewrite_sandboxd_url must NOT normalize ports — it only swaps
    domain and forces HTTPS.  Port normalization is the caller's job
    (the API endpoint regex).  This documents that contract so nobody
    re-adds port logic to the rewriter (commit 972ba826 removed it)."""
    with patch("app.integrations.sandboxd_client.settings") as mock_settings:
        mock_settings.SANDBOXD_PREVIEW_DOMAIN = "preview.flowmanner.com"
        result = _rewrite_preview_url("http://s-abc123-5173.preview.localhost")
    # Port 5173 should survive the rewrite — it must not be clobbered to 8081.
    assert result == "https://s-abc123-5173.preview.flowmanner.com"
