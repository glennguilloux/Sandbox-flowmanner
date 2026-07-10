"""Tests for the v2 marketplace uninstall endpoint.

Covers DELETE /api/v2/marketplace/listings/{listing_id}/install:
  - 200 on success
  - 404 when the service reports "Not installed"
  - 400 on any other failure

The route delegates to ``MarketplaceService.uninstall`` (sync DB call run via
``asyncio.to_thread``); we patch ``get_marketplace_service`` so no real DB is
needed. Mirrors the setup in ``tests/test_v2_chat_delete_message.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main_fastapi import app

pytestmark = pytest.mark.integration

LISTING_ID = "00000000-0000-0000-0000-000000000001"
UNINSTALL_URL = f"/api/v2/marketplace/listings/{LISTING_ID}/install"


@pytest.fixture
def auth_client(mock_db_session, sample_user):
    """Real app with get_db / get_current_user overridden (no external services)."""

    async def override_get_db():
        yield mock_db_session

    async def override_get_current_user():
        return sample_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _patch_service(result: dict) -> patch:
    """Patch ``get_marketplace_service`` to return a service whose ``uninstall`` returns ``result``."""
    service = MagicMock()
    service.uninstall.return_value = result
    return patch("app.api.v2.marketplace.get_marketplace_service", return_value=service)


def test_uninstall_listing_success(auth_client: TestClient):
    with _patch_service({"success": True, "message": "Uninstalled"}):
        response = auth_client.delete(UNINSTALL_URL)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["error"] is None
    assert body["data"]["success"] is True
    assert body["data"]["message"] == "Uninstalled"


def test_uninstall_listing_not_installed_returns_404(auth_client: TestClient):
    with _patch_service({"success": False, "error": "Not installed"}):
        response = auth_client.delete(UNINSTALL_URL)

    assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
    assert "Not installed" in response.text


def test_uninstall_listing_generic_failure_returns_400(auth_client: TestClient):
    with _patch_service({"success": False, "error": "db connection lost"}):
        response = auth_client.delete(UNINSTALL_URL)

    assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
    assert "db connection lost" in response.text
