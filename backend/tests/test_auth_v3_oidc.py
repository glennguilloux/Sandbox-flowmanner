"""Unit tests for Auth v3 OIDC routes.

Tests feature flag gating, provider listing, PKCE login flow,
callback with session creation, and logout.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


# ── Feature flag gating ─────────────────────────────────────────────────────


class TestOIDCFeatureFlag:
    """_require_oidc_enabled returns 404 when flag is off."""

    @pytest.mark.asyncio
    async def test_flag_off_returns_404(self, v3_client, mock_db_session):
        """When AUTH_V3_OIDC is disabled, all OIDC endpoints return 404."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = v3_client.get("/api/v3/auth/oidc/providers")
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == "Endpoint not found"

    @pytest.mark.asyncio
    async def test_flag_off_login_returns_404(self, v3_client, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = v3_client.post(
            "/api/v3/auth/oidc/google/login",
            json={"redirect_uri": "http://localhost:3000/callback"},
        )
        assert resp.status_code == 404


# ── GET /auth/oidc/providers ─────────────────────────────────────────────────


class TestListProviders:
    """List OIDC providers endpoint."""

    def test_returns_providers(self, v3_client, mock_db_session):
        """When flag is on, returns provider list from oidc_service."""
        # First call: feature flag check (returns True)
        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        # Second call: list_providers query
        provider = MagicMock()
        provider.name = "google"
        provider.display_name = "Google"
        provider.issuer_url = "https://accounts.google.com"
        provider_result = MagicMock()
        provider_result.scalars.return_value.all.return_value = [provider]

        mock_db_session.execute = AsyncMock(side_effect=[flag_result, provider_result])

        resp = v3_client.get("/api/v3/auth/oidc/providers")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["name"] == "google"
        assert data[0]["display_name"] == "Google"

    def test_empty_providers(self, v3_client, mock_db_session):
        """When no providers configured, returns empty list."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        provider_result = MagicMock()
        provider_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[flag_result, provider_result])

        resp = v3_client.get("/api/v3/auth/oidc/providers")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ── POST /auth/oidc/{provider}/login ─────────────────────────────────────────


class TestOIDCLogin:
    """OIDC login — authorization URL generation with PKCE."""

    def test_login_returns_authorization_url(self, v3_client, mock_db_session):
        """Successful login returns authorization_url and state."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        mock_db_session.execute = AsyncMock(return_value=flag_result)

        with patch("app.services.oidc_service.get_authorization_url", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = {
                "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
                "state": "abc123",
                "nonce": "def456",
            }

            resp = v3_client.post(
                "/api/v3/auth/oidc/google/login",
                json={"redirect_uri": "http://localhost:3000/callback"},
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "authorization_url" in data
        assert data["state"] == "abc123"

    def test_login_unknown_provider_returns_400(self, v3_client, mock_db_session):
        """Unknown provider raises 400."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True
        mock_db_session.execute = AsyncMock(return_value=flag_result)

        with patch("app.services.oidc_service.get_authorization_url", new_callable=AsyncMock) as mock_auth:
            mock_auth.side_effect = ValueError("Unknown or inactive OIDC provider: badprovider")

            resp = v3_client.post(
                "/api/v3/auth/oidc/badprovider/login",
                json={"redirect_uri": "http://localhost:3000/callback"},
            )

        assert resp.status_code == 400
        assert "Unknown" in resp.json()["error"]["message"]

    def test_login_service_error_returns_500(self, v3_client, mock_db_session):
        """Unexpected service error returns 500."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True
        mock_db_session.execute = AsyncMock(return_value=flag_result)

        with patch("app.services.oidc_service.get_authorization_url", new_callable=AsyncMock) as mock_auth:
            mock_auth.side_effect = RuntimeError("Network error")

            resp = v3_client.post(
                "/api/v3/auth/oidc/google/login",
                json={"redirect_uri": "http://localhost:3000/callback"},
            )

        assert resp.status_code == 500


# ── GET /auth/oidc/{provider}/callback ───────────────────────────────────────


class TestOIDCCallback:
    """OIDC callback — code exchange, session creation, cookie setting."""

    def test_callback_missing_code_returns_400(self, v3_client, mock_db_session):
        """Missing authorization code returns 400."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True
        mock_db_session.execute = AsyncMock(return_value=flag_result)

        resp = v3_client.get("/api/v3/auth/oidc/google/callback?state=abc")
        assert resp.status_code == 400
        assert "Missing authorization code" in resp.json()["error"]["message"]

    def test_callback_missing_state_returns_400(self, v3_client, mock_db_session):
        """Missing state parameter returns 400."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True
        mock_db_session.execute = AsyncMock(return_value=flag_result)

        resp = v3_client.get("/api/v3/auth/oidc/google/callback?code=auth_code")
        assert resp.status_code == 400
        assert "Missing state parameter" in resp.json()["error"]["message"]

    def test_callback_provider_error_redirects(self, v3_client, mock_db_session):
        """Provider error redirects to frontend with error params."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True
        mock_db_session.execute = AsyncMock(return_value=flag_result)

        resp = v3_client.get(
            "/api/v3/auth/oidc/google/callback?error=access_denied&error_description=User+denied",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "error=access_denied" in location

    def test_callback_auth_failure_redirects(self, v3_client, mock_db_session):
        """Authentication failure redirects with error."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True
        mock_db_session.execute = AsyncMock(return_value=flag_result)

        with patch(
            "app.services.oidc_service.authenticate_with_oidc",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.side_effect = ValueError("Invalid state parameter")

            resp = v3_client.get(
                "/api/v3/auth/oidc/google/callback?code=auth_code&state=bad_state",
                follow_redirects=False,
            )

        assert resp.status_code == 302
        assert "authentication_failed" in resp.headers["location"]

    def test_callback_success_creates_session(self, v3_client, mock_db_session):
        """Successful callback creates session and sets cookie."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.role = "member"
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = mock_user

        mock_session = MagicMock()
        mock_session.id = "sess-abc123"
        mock_session.expires_at = "2026-07-15T00:00:00Z"

        mock_db_session.execute = AsyncMock(side_effect=[flag_result, user_result])

        with (
            patch(
                "app.services.oidc_service.authenticate_with_oidc",
                new_callable=AsyncMock,
            ) as mock_auth,
            patch(
                "app.services.auth_v3_service.create_session",
                new_callable=AsyncMock,
            ) as mock_create_session,
            patch(
                "app.services.auth_v3_service.create_access_token",
            ) as mock_create_token,
        ):
            mock_auth.return_value = {
                "user_id": 42,
                "email": "user@example.com",
                "access_token": "oidc_access",
                "refresh_token": "oidc_refresh",
            }
            mock_create_session.return_value = (mock_session, "refresh_token_value")
            mock_create_token.return_value = "v3_access_token"

            resp = v3_client.get(
                "/api/v3/auth/oidc/google/callback?code=auth_code&state=valid_state",
                follow_redirects=False,
            )

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "access_token=v3_access_token" in location
        assert "session_id=sess-abc123" in location
        # Check httpOnly cookie is set (use raw header since httpx rejects
        # secure cookies over HTTP test server)
        set_cookie = resp.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie


# ── POST /auth/oidc/{provider}/logout ────────────────────────────────────────


class TestOIDCLogout:
    """OIDC logout endpoint."""

    def test_logout_returns_end_session_url(self, v3_client, mock_db_session):
        """Successful logout returns end_session_url."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True
        mock_db_session.execute = AsyncMock(return_value=flag_result)

        with patch("app.services.oidc_service.logout_oidc", new_callable=AsyncMock) as mock_logout:
            mock_logout.return_value = {
                "end_session_url": "https://accounts.google.com/logout?...",
            }

            resp = v3_client.post("/api/v3/auth/oidc/google/logout")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "end_session_url" in data

    def test_logout_unknown_provider_returns_400(self, v3_client, mock_db_session):
        """Unknown provider returns 400."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True
        mock_db_session.execute = AsyncMock(return_value=flag_result)

        with patch("app.services.oidc_service.logout_oidc", new_callable=AsyncMock) as mock_logout:
            mock_logout.side_effect = ValueError("Unknown OIDC provider: bad")

            resp = v3_client.post("/api/v3/auth/oidc/bad/logout")

        assert resp.status_code == 400
