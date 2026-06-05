import os
import pytest
import httpx

pytestmark = pytest.mark.integration

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-123")

VPS_BASE_URL = os.getenv("SMOKE_BASE_URL", "https://flowmanner.com")

@pytest.fixture(scope="module")
def vps_client():
    """HTTP client for VPS proxy endpoints."""
    with httpx.Client(base_url=VPS_BASE_URL, timeout=10.0) as client:
        yield client

def test_vps_health_endpoint(vps_client):
    """GET /health via VPS returns 200 (proxied to home lab)."""
    try:
        response = vps_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "ok", "degraded"]
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
        assert "not authenticated" in response.json().get("detail", "").lower()
    except httpx.ConnectError:
        pytest.skip("VPS unreachable from test environment")

def test_vps_cors_headers(vps_client):
    """ OPTIONS /api/health returns proper CORS headers."""
    try:
        response = vps_client.options("/api/health")
        assert response.status_code in [200, 204]
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers
    except httpx.ConnectError:
        pytest.skip("VPS unreachable from test environment")
