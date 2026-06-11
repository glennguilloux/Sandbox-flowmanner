import os

import httpx
import pytest

pytestmark = pytest.mark.integration

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-123")

# These are live smoke tests that require the VPS to be reachable.
# Set SMOKE_BASE_URL to enable; defaults to the production URL.
VPS_BASE_URL = os.getenv("SMOKE_BASE_URL", "https://flowmanner.com")


@pytest.fixture(scope="module")
def vps_client():
    """HTTP client for VPS proxy endpoints."""
    with httpx.Client(base_url=VPS_BASE_URL, timeout=10.0) as client:
        yield client


def test_vps_root_returns_non_404(vps_client):
    """GET / via VPS returns a non-404 response (frontend or redirect)."""
    try:
        response = vps_client.get("/")
        # Root should serve the frontend or redirect, not 404
        assert response.status_code in [200, 301, 302, 307, 308]
    except httpx.ConnectError:
        pytest.skip("VPS unreachable from test environment")


def test_vps_api_health_endpoint(vps_client):
    """GET /api/health via VPS returns 200 (proxied to home lab)."""
    try:
        response = vps_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
    except httpx.ConnectError:
        pytest.skip("VPS unreachable from test environment")


def test_vps_proxy_forwards_api_requests(vps_client):
    """GET /api/auth/me without auth returns 401 (proxied to home lab backend)."""
    try:
        response = vps_client.get("/api/auth/me")
        assert response.status_code == 401
        detail = response.json().get("detail", "").lower()
        assert "unauthorized" in detail or "not authenticated" in detail
    except httpx.ConnectError:
        pytest.skip("VPS unreachable from test environment")


def test_vps_cors_headers(vps_client):
    """OPTIONS /api/health returns proper CORS headers (if Nginx handles preflight)."""
    try:
        response = vps_client.options("/api/health")
        # Nginx may return 405 for OPTIONS if CORS preflight is handled
        # at the Nginx config level rather than the backend. Accept either.
        assert response.status_code in [200, 204, 405]
        if response.status_code != 405:
            assert "access-control-allow-origin" in response.headers
    except httpx.ConnectError:
        pytest.skip("VPS unreachable from test environment")
