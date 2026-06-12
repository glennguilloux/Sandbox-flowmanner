"""Tests for sandbox preview error mapping (P0.2 Fix B).

Covers the three error branches in ``get_preview_url``:
- 404 → sandbox gone (HTTPStatusError with 404 response)
- 504 → sandboxd timeout (httpx.TimeoutException / asyncio.TimeoutError)
- 502 → sandboxd unreachable (httpx.ConnectError / OSError)

All tests use a mocked ``SandboxdClient`` that raises the specific
exception type; no network calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.sandbox_preview import router

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def test_app():
    _app = FastAPI()
    _app.include_router(router, prefix="/api/v1")

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


def _make_httpx_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Build an ``httpx.HTTPStatusError`` with a fake response."""
    request = httpx.Request("GET", "http://sandboxd:9090/v1/sandboxes/sb-xyz")
    response = httpx.Response(status_code=status_code, request=request)
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=request,
        response=response,
    )


# ── P0.2 error mapping tests ─────────────────────────────────────────


@pytest.mark.anyio
async def test_preview_sandbox_gone_returns_404_with_error_detail(client):
    """sandboxd returns 404 → frontend sees sandbox_not_found error."""
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.side_effect = _make_httpx_status_error(404)
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-gone/preview")

    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["error"] == "sandbox_not_found"
    assert detail["sandbox_id"] == "sb-gone"
    assert "request_id" in detail


@pytest.mark.anyio
async def test_preview_sandboxd_timeout_returns_504(client):
    """sandboxd times out → frontend sees sandboxd_timeout error."""
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("Read timed out")
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-slow/preview")

    assert resp.status_code == 504
    detail = resp.json()["detail"]
    assert detail["error"] == "sandboxd_timeout"
    assert "request_id" in detail


@pytest.mark.anyio
async def test_preview_sandboxd_unreachable_returns_502(client):
    """sandboxd connection refused → frontend sees sandboxd_unreachable error."""
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-noconn/preview")

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["error"] == "sandboxd_unreachable"
    assert "request_id" in detail


@pytest.mark.anyio
async def test_preview_os_error_returns_502(client):
    """OS-level network error → frontend sees sandboxd_unreachable error."""
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.side_effect = OSError("Network is unreachable")
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-oserr/preview")

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["error"] == "sandboxd_unreachable"
    assert "request_id" in detail


@pytest.mark.anyio
async def test_preview_sandboxd_500_returns_502(client):
    """sandboxd returns 500 (non-404 HTTP error) → frontend sees sandboxd_unreachable."""
    with patch("app.api.v1.sandbox_preview.get_sandboxd_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.side_effect = _make_httpx_status_error(500)
        mock_get_client.return_value = mock_client

        resp = await client.get("/api/v1/sandbox/sb-err/preview")

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["error"] == "sandboxd_unreachable"
    assert "request_id" in detail
