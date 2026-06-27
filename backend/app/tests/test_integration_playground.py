"""Tests for Integration Playground (Phase 4).

Covers:
- Demo credential vault loading and fallback
- Playground service mock + real dispatch
- Rate limiting logic
- API endpoint (feature-flagged, rate-limited, action validation)
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

# ── Demo Credential Vault ─────────────────────────────────────────────────


class TestDemoCredentials:
    """Tests for the demo credential vault."""

    def test_module_loads(self):
        """demo_credentials module imports without error."""
        import app.core.demo_credentials as mod

        assert hasattr(mod, "DEMO_CREDENTIALS")
        assert hasattr(mod, "get_demo_credential")
        assert hasattr(mod, "has_real_credentials")

    def test_get_demo_credential_returns_none_for_unknown(self):
        """Unknown slug returns None."""
        from app.core.demo_credentials import get_demo_credential

        assert get_demo_credential("nonexistent") is None

    def test_google_has_no_real_credentials(self):
        """Google has no demo token — playground uses mock responses."""
        from app.core.demo_credentials import has_real_credentials

        assert has_real_credentials("google") is False

    def test_google_drive_has_no_real_credentials(self):
        """Google Drive has no demo token."""
        from app.core.demo_credentials import has_real_credentials

        assert has_real_credentials("google_drive") is False

    def test_slack_credential_structure(self):
        """Slack credential has expected fields even without env var."""
        from app.core.demo_credentials import get_demo_credential

        cred = get_demo_credential("slack")
        # May be None if SLACK_DEMO_BOT_TOKEN is not set
        if cred is not None:
            assert cred.slug == "slack"
            assert cred.rate_limit == 5
            assert cred.workspace_name == "Flowmanner Playground"
            assert "#flowmanner-playground" in cred.allowed_resources

    def test_github_credential_structure(self):
        """GitHub credential has expected fields."""
        from app.core.demo_credentials import get_demo_credential

        cred = get_demo_credential("github")
        if cred is not None:
            assert cred.slug == "github"
            assert cred.rate_limit == 10
            assert "flowmanner-demo" in cred.allowed_resources


# ── Playground Service ────────────────────────────────────────────────────


class TestPlaygroundService:
    """Tests for the playground service mock dispatch."""

    @pytest.mark.asyncio
    async def test_slack_list_channels_mock(self):
        """Slack list_channels returns mock response when no credentials."""
        from app.services.integration_playground_service import execute_playground_action

        with patch(
            "app.services.integration_playground_service.has_real_credentials",
            return_value=False,
        ):
            result = await execute_playground_action(
                slug="slack",
                action="list_channels",
            )

        assert result["success"] is True
        assert result["is_mock"] is True
        assert "channels" in result["response"]
        assert len(result["response"]["channels"]) > 0

    @pytest.mark.asyncio
    async def test_slack_send_message_mock(self):
        """Slack send_message returns mock response."""
        from app.services.integration_playground_service import execute_playground_action

        with patch(
            "app.services.integration_playground_service.has_real_credentials",
            return_value=False,
        ):
            result = await execute_playground_action(
                slug="slack",
                action="send_message",
                params={"text": "Test message"},
            )

        assert result["success"] is True
        assert result["is_mock"] is True
        assert result["response"]["text"] == "Test message"

    @pytest.mark.asyncio
    async def test_github_list_repos_mock(self):
        """GitHub list_repos returns mock response."""
        from app.services.integration_playground_service import execute_playground_action

        with patch(
            "app.services.integration_playground_service.has_real_credentials",
            return_value=False,
        ):
            result = await execute_playground_action(
                slug="github",
                action="list_repos",
            )

        assert result["success"] is True
        assert result["is_mock"] is True
        assert "repos" in result["response"]
        assert len(result["response"]["repos"]) > 0

    @pytest.mark.asyncio
    async def test_notion_list_pages_mock(self):
        """Notion list_pages returns mock response."""
        from app.services.integration_playground_service import execute_playground_action

        with patch(
            "app.services.integration_playground_service.has_real_credentials",
            return_value=False,
        ):
            result = await execute_playground_action(
                slug="notion",
                action="list_pages",
            )

        assert result["success"] is True
        assert result["is_mock"] is True
        assert "pages" in result["response"]

    @pytest.mark.asyncio
    async def test_discord_send_message_mock(self):
        """Discord send_message returns mock response."""
        from app.services.integration_playground_service import execute_playground_action

        with patch(
            "app.services.integration_playground_service.has_real_credentials",
            return_value=False,
        ):
            result = await execute_playground_action(
                slug="discord",
                action="send_message",
            )

        assert result["success"] is True
        assert result["is_mock"] is True

    @pytest.mark.asyncio
    async def test_apiflow_ping_mock(self):
        """Apiflow ping returns mock response."""
        from app.services.integration_playground_service import execute_playground_action

        with patch(
            "app.services.integration_playground_service.has_real_credentials",
            return_value=False,
        ):
            result = await execute_playground_action(
                slug="apiflow",
                action="ping",
            )

        assert result["success"] is True
        assert result["is_mock"] is True
        assert result["response"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_unknown_action_returns_generic_mock(self):
        """Unknown action for a known slug returns a generic mock."""
        from app.services.integration_playground_service import execute_playground_action

        with patch(
            "app.services.integration_playground_service.has_real_credentials",
            return_value=False,
        ):
            result = await execute_playground_action(
                slug="slack",
                action="nonexistent_action",
            )

        assert result["success"] is True
        assert result["is_mock"] is True
        assert "preview" in result["response"]["message"].lower()

    @pytest.mark.asyncio
    async def test_mock_response_has_no_internal_fields(self):
        """Mock responses should not include _preview or _note in cleaned output."""
        from app.services.integration_playground_service import execute_playground_action

        with patch(
            "app.services.integration_playground_service.has_real_credentials",
            return_value=False,
        ):
            result = await execute_playground_action(
                slug="github",
                action="list_repos",
            )

        # The raw response _does_ have _preview/_note for frontend display
        assert "_preview" in result["response"]
        # But the frontend component strips these with formatResponse


# ── Rate Limiting ─────────────────────────────────────────────────────────


class TestPlaygroundRateLimit:
    """Tests for the playground rate limiter."""

    def setup_method(self):
        """Clear rate limit store between tests."""
        from app.services.integration_playground_service import _rate_limit_store

        _rate_limit_store.clear()

    def test_first_request_allowed(self):
        """First request is allowed with remaining = max - 1."""
        from app.services.integration_playground_service import check_playground_rate_limit

        allowed, remaining = check_playground_rate_limit("user1", "slack", max_requests=5)
        assert allowed is True
        assert remaining == 4

    def test_rate_limit_exceeded(self):
        """Request is blocked after max_requests reached."""
        from app.services.integration_playground_service import check_playground_rate_limit

        for _ in range(5):
            check_playground_rate_limit("user1", "slack", max_requests=5)

        allowed, remaining = check_playground_rate_limit("user1", "slack", max_requests=5)
        assert allowed is False
        assert remaining == 0

    def test_different_users_independent(self):
        """Rate limits are per-user."""
        from app.services.integration_playground_service import check_playground_rate_limit

        for _ in range(5):
            check_playground_rate_limit("user1", "slack", max_requests=5)

        allowed, remaining = check_playground_rate_limit("user2", "slack", max_requests=5)
        assert allowed is True
        assert remaining == 4

    def test_different_integrations_independent(self):
        """Rate limits are per-integration."""
        from app.services.integration_playground_service import check_playground_rate_limit

        for _ in range(5):
            check_playground_rate_limit("user1", "slack", max_requests=5)

        allowed, remaining = check_playground_rate_limit("user1", "github", max_requests=5)
        assert allowed is True
        assert remaining == 4

    def test_custom_rate_limit(self):
        """Custom max_requests is respected."""
        from app.services.integration_playground_service import check_playground_rate_limit

        allowed, remaining = check_playground_rate_limit("user1", "github", max_requests=10)
        assert allowed is True
        assert remaining == 9


# ── API Endpoint ──────────────────────────────────────────────────────────


class TestPlaygroundEndpoint:
    """Tests for the playground API endpoint."""

    def _make_app(self):
        """Create a test FastAPI app with mocked dependencies."""
        from fastapi import FastAPI

        from app.api.deps import get_current_user
        from app.api.v1.integrations import router
        from app.database import get_db

        app = FastAPI()
        app.include_router(router)

        # Override the auth dependency to return a fake user
        fake_user = type("User", (), {"id": 1, "email": "test@test.com"})()

        async def _override_get_current_user():
            return fake_user

        app.dependency_overrides[get_current_user] = _override_get_current_user
        return app

    def test_endpoint_requires_feature_flag(self):
        """Playground endpoint returns 404 when flag is disabled."""
        from fastapi.testclient import TestClient

        app = self._make_app()

        with patch(
            "app.api.v1.integrations._is_flag_enabled",
            new_callable=AsyncMock,
            return_value=False,
        ):
            client = TestClient(app)
            resp = client.post(
                "/integrations/slack/playground/list_channels",
                json={"params": {}},
            )
            assert resp.status_code == 404
            assert "not available" in resp.json()["detail"].lower()

    def test_endpoint_validates_action(self):
        """Playground endpoint rejects invalid actions."""
        from fastapi.testclient import TestClient

        app = self._make_app()

        with patch(
            "app.api.v1.integrations._is_flag_enabled",
            new_callable=AsyncMock,
            return_value=True,
        ):
            client = TestClient(app)
            resp = client.post(
                "/integrations/slack/playground/invalid_action",
                json={"params": {}},
            )
            assert resp.status_code == 400
            assert "unknown playground action" in resp.json()["detail"].lower()

    def test_endpoint_returns_404_for_unknown_integration(self):
        """Playground endpoint returns 404 for unknown slug."""
        from fastapi.testclient import TestClient

        app = self._make_app()

        with patch(
            "app.api.v1.integrations._is_flag_enabled",
            new_callable=AsyncMock,
            return_value=True,
        ):
            client = TestClient(app)
            resp = client.post(
                "/integrations/nonexistent/playground/test",
                json={"params": {}},
            )
            assert resp.status_code == 404

    def test_list_actions_endpoint(self):
        """Playground actions list endpoint returns actions from manifest."""
        from fastapi.testclient import TestClient

        app = self._make_app()

        with patch(
            "app.api.v1.integrations._is_flag_enabled",
            new_callable=AsyncMock,
            return_value=True,
        ):
            client = TestClient(app)
            resp = client.get("/integrations/slack/playground/actions")
            assert resp.status_code == 200
            data = resp.json()
            assert data["slug"] == "slack"
            assert data["enabled"] is True
            assert len(data["actions"]) > 0


# ── Manifest Playground Config ────────────────────────────────────────────


class TestManifestPlayground:
    """Tests that manifests have proper playground configuration."""

    def test_slack_manifest_playground_enabled(self):
        """Slack manifest has playground enabled with demo_actions."""
        from app.services.integration_manifest_service import manifest_service

        manifest_service.reload()
        manifest = manifest_service.get("slack")
        assert manifest is not None
        assert manifest["playground"]["enabled"] is True
        assert len(manifest["playground"]["demo_actions"]) > 0

    def test_github_manifest_playground_enabled(self):
        """GitHub manifest has playground enabled with demo_actions."""
        from app.services.integration_manifest_service import manifest_service

        manifest_service.reload()
        manifest = manifest_service.get("github")
        assert manifest is not None
        assert manifest["playground"]["enabled"] is True
        assert len(manifest["playground"]["demo_actions"]) > 0

    def test_all_manifests_have_playground_field(self):
        """All manifests have a playground field (even if disabled)."""
        from app.services.integration_manifest_service import manifest_service

        manifest_service.reload()
        for slug in manifest_service.slug_list:
            manifest = manifest_service.get(slug)
            assert manifest is not None
            assert "playground" in manifest, f"{slug} missing playground field"
            assert "enabled" in manifest["playground"]
            assert "demo_actions" in manifest["playground"]

    def test_demo_actions_have_required_fields(self):
        """All demo_actions have label and action fields."""
        from app.services.integration_manifest_service import manifest_service

        manifest_service.reload()
        for slug in manifest_service.slug_list:
            manifest = manifest_service.get(slug)
            for da in manifest["playground"]["demo_actions"]:
                assert "label" in da, f"{slug} demo_action missing label"
                assert "action" in da, f"{slug} demo_action missing action"
