"""Integration tests for Auth v3 endpoints — login, register, refresh, sessions, API keys, 2FA.

Uses FastAPI TestClient with mocked dependencies. All async service functions
are patched using AsyncMock (NOT MagicMock) because the route handlers await them.
Sync functions use regular patch return_value.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user

# ═══════════════════════════════════════════════
# Helpers — build mock ORM objects & patch utilities
# ═══════════════════════════════════════════════


def _am(retval):
    """Shorthand: AsyncMock(return_value=retval) for patching async functions."""
    return AsyncMock(return_value=retval)


def _make_user(**overrides):
    defaults = dict(
        id=1,
        email="test@example.com",
        username="testuser",
        full_name="Test User",
        role="pro",
        is_admin=False,
        is_superuser=False,
        is_active=True,
        avatar_url=None,
        totp_enabled=False,
        totp_secret=None,
        totp_backup_codes=None,
        tenant_id=None,
        hashed_password="$2b$...",
        login_count=5,
        last_login_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        onboarding_step=None,
        onboarding_completed=False,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_session(**overrides):
    defaults = dict(
        id="sess_test123",
        user_id=1,
        refresh_token_hash="abc123...",
        ip_address="127.0.0.1",
        device_name="pytest",
        device_os="Linux",
        browser="Chrome",
        location=None,
        scopes=json.dumps(["sessions:read", "sessions:write", "api_keys:read", "api_keys:write"]),
        is_active=True,
        revoked_at=None,
        last_used_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        expires_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_api_key(**overrides):
    """Create a mock API key. name is set after construction because it's a
    reserved MagicMock constructor parameter."""
    defaults = dict(
        id="key_test123",
        key_hash="abc...",
        key_prefix="fm_a1b2c3",
        scopes=json.dumps(["missions:read"]),
        is_active=True,
        last_used_at=None,
        created_at=datetime.now(UTC),
        expires_at=None,
    )
    defaults.update(overrides)
    name = defaults.pop("name", "CI Key")
    m = MagicMock(**defaults)
    m.name = name
    return m


# ═══════════════════════════════════════════════
# Register Tests
# ═══════════════════════════════════════════════


class TestRegister:
    """POST /api/v3/auth/users"""

    def test_register_returns_201_with_session(self, v3_client: TestClient):
        """Happy path: new email + strong password → 201 + session + set-cookie."""
        with (
            patch("app.api.v3.auth.get_user_by_email", new=_am(None)),
            patch("app.api.v3.auth.get_user_by_username", new=_am(None)),
            patch("app.api.v3.auth.validate_password_strength", return_value=[]),
            patch("app.api.v3.auth.create_user", new=_am(_make_user())),
            patch("app.api.v3.auth.create_session", new=_am((_make_session(), "refresh-abc"))),
            patch("app.api.v3.auth.create_access_token", return_value="acc-token"),
        ):
            resp = v3_client.post(
                "/api/v3/auth/users",
                json={
                    "email": "new@example.com",
                    "password": "ValidPass123!",
                    "full_name": "New User",
                },
            )

            assert resp.status_code == 201
            data = resp.json()
            assert data["data"]["access_token"] == "acc-token"
            assert data["data"]["session_id"] == "sess_test123"
            assert "set-cookie" in resp.headers

    def test_register_duplicate_email_returns_409(self, v3_client: TestClient):
        """Existing email → 409 Conflict."""
        with (
            patch("app.api.v3.auth.validate_password_strength", return_value=[]),
            patch("app.api.v3.auth.get_user_by_email", new=_am(_make_user())),
        ):
            resp = v3_client.post(
                "/api/v3/auth/users",
                json={
                    "email": "existing@example.com",
                    "password": "ValidPass123!",
                },
            )
            assert resp.status_code == 409

    def test_register_weak_password_returns_422(self, v3_client: TestClient):
        """Password fails strength check → 422."""
        with patch(
            "app.api.v3.auth.validate_password_strength",
            return_value=["Password too short"],
        ):
            resp = v3_client.post(
                "/api/v3/auth/users",
                json={
                    "email": "a@b.com",
                    "password": "short",
                },
            )
            assert resp.status_code == 422


# ═══════════════════════════════════════════════
# Login Tests
# ═══════════════════════════════════════════════
#
# NOTE: Login route handlers use inline db.execute(select(User).where(...))
# directly (not via service functions), so these tests mock the DB session
# chain rather than patching service functions. The mock_db_session.execute
# chain uses a regular MagicMock (not AsyncMock) for the return_value to
# avoid scalar_one_or_none() returning a coroutine.


class TestLogin:
    """POST /api/v3/auth/sessions"""

    def test_login_email_returns_201_with_session(self, v3_client: TestClient, mock_db_session):
        """Valid email + password → 201 + session + set-cookie."""
        mock_user = _make_user()
        mock_db_session.execute.return_value = MagicMock()
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_user

        with (
            patch("app.api.v3.auth.verify_password", return_value=True),
            patch("app.api.v3.auth.create_session", new=_am((_make_session(), "refresh-xyz"))),
            patch("app.api.v3.auth.create_access_token", return_value="acc-token"),
        ):
            resp = v3_client.post(
                "/api/v3/auth/sessions",
                json={
                    "login": "test@example.com",
                    "password": "CorrectPass123!",
                },
            )

            assert resp.status_code == 201
            data = resp.json()
            assert data["data"]["access_token"] == "acc-token"
            assert "set-cookie" in resp.headers

    def test_login_username_returns_201(self, v3_client: TestClient, mock_db_session):
        """Valid username + password → 201."""
        mock_user = _make_user()
        mock_db_session.execute.return_value = MagicMock()
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_user

        with (
            patch("app.api.v3.auth.verify_password", return_value=True),
            patch("app.api.v3.auth.create_session", new=_am((_make_session(), "refresh-xyz"))),
            patch("app.api.v3.auth.create_access_token", return_value="acc-token"),
        ):
            resp = v3_client.post(
                "/api/v3/auth/sessions",
                json={
                    "login": "testuser",
                    "password": "CorrectPass123!",
                },
            )
            assert resp.status_code == 201

    def test_login_invalid_password_returns_401(self, v3_client: TestClient, mock_db_session):
        """Wrong password → 401."""
        mock_user = _make_user()
        mock_db_session.execute.return_value = MagicMock()
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_user

        with patch("app.api.v3.auth.verify_password", return_value=False):
            resp = v3_client.post(
                "/api/v3/auth/sessions",
                json={
                    "login": "test@example.com",
                    "password": "WrongPass!",
                },
            )
            assert resp.status_code == 401

    def test_login_nonexistent_user_returns_401(self, v3_client: TestClient, mock_db_session):
        """Non-existent user → 401."""
        mock_db_session.execute.return_value = MagicMock()
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None

        resp = v3_client.post(
            "/api/v3/auth/sessions",
            json={
                "login": "ghost@example.com",
                "password": "DoesntMatter!",
            },
        )
        assert resp.status_code == 401

    def test_login_disabled_account_returns_403(self, v3_client: TestClient, mock_db_session):
        """Disabled account → 403."""
        mock_user = _make_user(is_active=False)
        mock_db_session.execute.return_value = MagicMock()
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_user

        with patch("app.api.v3.auth.verify_password", return_value=True):
            resp = v3_client.post(
                "/api/v3/auth/sessions",
                json={
                    "login": "test@example.com",
                    "password": "CorrectPass123!",
                },
            )
            assert resp.status_code == 403


# ═══════════════════════════════════════════════
# 2FA Flow Tests
# ═══════════════════════════════════════════════


class TestTwoFactorAuth:
    """POST /api/v3/auth/sessions/verify"""

    def test_login_with_2fa_returns_temp_token(self, v3_client: TestClient, mock_db_session):
        """2FA-enabled user → temp_token instead of session."""
        mock_user = _make_user(totp_enabled=True)
        mock_db_session.execute.return_value = MagicMock()
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_user

        with (
            patch("app.api.v3.auth.verify_password", return_value=True),
            patch("app.api.v3.auth.create_temp_token", return_value="temp-abc-456"),
        ):
            resp = v3_client.post(
                "/api/v3/auth/sessions",
                json={
                    "login": "test@example.com",
                    "password": "CorrectPass123!",
                },
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["data"]["requires_2fa"] is True
            assert data["data"]["temp_token"] == "temp-abc-456"

    def test_verify_2fa_invalid_token_returns_401(self, v3_client: TestClient):
        """Invalid temp_token → 401."""
        with patch("app.api.v3.auth.decode_temp_token", return_value=None):
            resp = v3_client.post(
                "/api/v3/auth/sessions/verify",
                json={
                    "temp_token": "bad-token",
                    "code": "123456",
                },
            )
            assert resp.status_code == 401

    def test_verify_2fa_valid_code_creates_session(self, v3_client: TestClient, mock_db_session):
        """Valid TOTP code → session created."""
        mock_user = _make_user(totp_enabled=True, totp_secret="BASE32SECRET")
        mock_db_session.execute.return_value = MagicMock()
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_user

        with (
            patch(
                "app.api.v3.auth.decode_temp_token",
                return_value={"sub": "1", "role": "pro"},
            ),
            patch("app.api.v3.auth.verify_code", return_value=True),
            patch("app.api.v3.auth.create_session", new=_am((_make_session(), "refresh-xyz"))),
            patch("app.api.v3.auth.create_access_token", return_value="acc-token"),
        ):
            resp = v3_client.post(
                "/api/v3/auth/sessions/verify",
                json={
                    "temp_token": "valid-temp",
                    "code": "123456",
                },
            )

            assert resp.status_code == 200
            assert resp.json()["data"]["access_token"] == "acc-token"

    def test_verify_2fa_backup_code_works(self, v3_client: TestClient, mock_db_session):
        """Valid backup code → session created."""
        mock_user = _make_user(totp_enabled=True, totp_backup_codes="backup1,backup2")
        mock_db_session.execute.return_value = MagicMock()
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_user

        with (
            patch(
                "app.api.v3.auth.decode_temp_token",
                return_value={"sub": "1", "role": "pro"},
            ),
            patch("app.api.v3.auth.verify_code", return_value=False),
            patch("app.api.v3.auth.consume_backup_code", return_value=(True, ["backup2"])),
            patch("app.api.v3.auth.create_session", new=_am((_make_session(), "refresh-xyz"))),
            patch("app.api.v3.auth.create_access_token", return_value="acc-token"),
        ):
            resp = v3_client.post(
                "/api/v3/auth/sessions/verify",
                json={
                    "temp_token": "valid-temp",
                    "code": "backup1",
                },
            )
            assert resp.status_code == 200


# ═══════════════════════════════════════════════
# Refresh Token Tests
# ═══════════════════════════════════════════════


class TestRefreshSession:
    """POST /api/v3/auth/sessions/refresh"""

    def test_refresh_with_cookie_returns_200(self, v3_client: TestClient):
        """Refresh via httpOnly cookie → 200 + new tokens."""
        mock_user = _make_user()
        with (
            patch(
                "app.api.v3.auth.refresh_session",
                new=_am((_make_session(id="sess_refreshed"), "new-refresh")),
            ),
            patch("app.api.v3.auth.create_access_token", return_value="new-acc-token"),
            patch("app.api.v3.auth.get_user_by_id", new=_am(mock_user)),
        ):
            resp = v3_client.post(
                "/api/v3/auth/sessions/refresh",
                cookies={"refresh_token": "old-refresh-token"},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["data"]["access_token"] == "new-acc-token"
            assert data["data"]["session_id"] == "sess_refreshed"

    def test_refresh_with_body_fallback_returns_200(self, v3_client: TestClient):
        """Refresh via JSON body (no cookie) → 200."""
        mock_user = _make_user()
        with (
            patch("app.api.v3.auth.refresh_session", new=_am((_make_session(), "new-refresh"))),
            patch("app.api.v3.auth.create_access_token", return_value="new-acc-token"),
            patch("app.api.v3.auth.get_user_by_id", new=_am(mock_user)),
        ):
            resp = v3_client.post(
                "/api/v3/auth/sessions/refresh",
                json={
                    "refresh_token": "old-refresh-body",
                },
            )
            assert resp.status_code == 200

    def test_refresh_expired_token_returns_401(self, v3_client: TestClient):
        """Expired/revoked refresh token → 401."""
        with patch("app.api.v3.auth.refresh_session", new=_am(None)):
            resp = v3_client.post(
                "/api/v3/auth/sessions/refresh",
                cookies={"refresh_token": "expired-token"},
            )
            assert resp.status_code == 401


# ═══════════════════════════════════════════════
# Session Management Tests
# ═══════════════════════════════════════════════


class TestSessionManagement:
    """GET /api/v3/auth/sessions, DELETE /api/v3/auth/sessions/{id}"""

    def test_list_sessions_returns_200(self, v3_client: TestClient):
        """List active sessions → 200 with array."""
        sessions = [_make_session(id="s1"), _make_session(id="s2")]
        with (
            patch("app.api.v3.auth.get_active_sessions", new=_am(sessions)),
            patch("app.api.v3.auth.decode_access_token", return_value={"session_id": "s1"}),
        ):
            resp = v3_client.get(
                "/api/v3/auth/sessions",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["data"], list)
            assert len(data["data"]) == 2
            assert data["data"][0]["id"] == "s1"

    def test_list_sessions_unauthenticated_returns_401(self, v3_client: TestClient):
        """No auth → 401."""
        saved = v3_client.app.dependency_overrides.pop(get_current_user, None)
        try:
            resp = v3_client.get("/api/v3/auth/sessions")
            assert resp.status_code == 401
        finally:
            if saved:
                v3_client.app.dependency_overrides[get_current_user] = saved

    def test_revoke_session_returns_204(self, v3_client: TestClient):
        """Revoke own session → 204 No Content."""
        with patch("app.api.v3.auth.revoke_session", new=_am(True)):
            resp = v3_client.delete(
                "/api/v3/auth/sessions/sess_to_revoke",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 204

    def test_revoke_nonexistent_session_returns_404(self, v3_client: TestClient):
        """Revoke non-existent session → 404."""
        with patch("app.api.v3.auth.revoke_session", new=_am(False)):
            resp = v3_client.delete(
                "/api/v3/auth/sessions/bogus_id",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 404


# ═══════════════════════════════════════════════
# User Profile Tests
# ═══════════════════════════════════════════════


class TestUserProfile:
    """GET /api/v3/auth/users/me, PATCH /api/v3/auth/users/me"""

    def test_get_me_returns_200(self, v3_client: TestClient):
        """Authenticated GET /users/me → 200 with user data."""
        resp = v3_client.get(
            "/api/v3/auth/users/me",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["email"] == "test@example.com"
        assert data["data"]["id"] == 1

    def test_get_me_unauthenticated_returns_401(self, v3_client: TestClient):
        """No auth → 401."""
        saved = v3_client.app.dependency_overrides.pop(get_current_user, None)
        try:
            resp = v3_client.get("/api/v3/auth/users/me")
            assert resp.status_code == 401
        finally:
            if saved:
                v3_client.app.dependency_overrides[get_current_user] = saved

    def test_update_me_returns_200(self, v3_client: TestClient):
        """PATCH /users/me full_name → 200."""
        resp = v3_client.patch(
            "/api/v3/auth/users/me",
            json={"full_name": "Updated Name"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200

    def test_update_me_password_revokes_sessions(self, v3_client: TestClient):
        """Password change → revokes all sessions."""
        with (
            patch("app.api.v3.auth.validate_password_strength", return_value=[]),
            patch("app.api.v3.auth.hash_password", return_value="hash"),
            patch("app.api.v3.auth.revoke_all_user_sessions", new=_am(1)) as mk_revoke_all,
        ):
            resp = v3_client.patch(
                "/api/v3/auth/users/me",
                json={"password": "NewValidPass123!"},
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 200
            mk_revoke_all.assert_called_once()


# ═══════════════════════════════════════════════
# API Key Tests
# ═══════════════════════════════════════════════


class TestApiKeys:
    """POST/GET/DELETE /api/v3/auth/api-keys"""

    def test_create_api_key_returns_201_with_full_key(self, v3_client: TestClient):
        """Create API key → 201 with full key returned once."""
        mock_key = _make_api_key()
        mock_key.scopes = json.dumps(["missions:read"])
        with patch("app.api.v3.auth.create_api_key", new=_am((mock_key, "fm_full_key_abc123"))):
            resp = v3_client.post(
                "/api/v3/auth/api-keys",
                json={"name": "CI Key", "scopes": ["missions:read"]},
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["data"]["key"] == "fm_full_key_abc123"
            assert data["data"]["name"] == "CI Key"
            assert "missions:read" in data["data"]["scopes"]

    def test_create_api_key_invalid_scopes_returns_400(self, v3_client: TestClient):
        """Invalid scopes → 400."""
        with patch(
            "app.api.v3.auth.create_api_key",
            new=AsyncMock(side_effect=ValueError("Invalid scopes")),
        ):
            resp = v3_client.post(
                "/api/v3/auth/api-keys",
                json={"name": "Bad Key", "scopes": ["superadmin:destroy"]},
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 400

    def test_list_api_keys_returns_200_no_full_key(self, v3_client: TestClient):
        """List API keys → 200, full key NOT present."""
        mock_key = _make_api_key()
        mock_key.scopes = json.dumps(["missions:read", "missions:write"])
        with patch("app.api.v3.auth.get_user_api_keys", new=_am([mock_key])):
            resp = v3_client.get(
                "/api/v3/auth/api-keys",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["data"], list)
            assert len(data["data"]) == 1
            assert "key" not in data["data"][0]
            assert data["data"][0]["key_prefix"] == "fm_a1b2c3"
            assert "missions:read" in data["data"][0]["scopes"]

    def test_revoke_api_key_returns_204(self, v3_client: TestClient):
        """Revoke API key → 204."""
        with patch("app.api.v3.auth.revoke_api_key", new=_am(True)):
            resp = v3_client.delete(
                "/api/v3/auth/api-keys/key_to_revoke",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 204

    def test_revoke_nonexistent_api_key_returns_404(self, v3_client: TestClient):
        """Revoke non-existent key → 404."""
        with patch("app.api.v3.auth.revoke_api_key", new=_am(False)):
            resp = v3_client.delete(
                "/api/v3/auth/api-keys/bogus_key",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code == 404


# ═══════════════════════════════════════════════
# Error Envelope Tests
# ═══════════════════════════════════════════════


class TestErrorEnvelope:
    """Verify v3 error response format: { data, meta, error }."""

    def test_401_has_error_envelope(self, v3_client: TestClient):
        """401 response includes error.trace_id for log correlation."""
        saved = v3_client.app.dependency_overrides.pop(get_current_user, None)
        try:
            resp = v3_client.get("/api/v3/auth/users/me")
            assert resp.status_code == 401
            body = resp.json()
            assert "error" in body
            # trace_id is nested inside the error object per v3 envelope
            assert "trace_id" in body["error"]
        finally:
            if saved:
                v3_client.app.dependency_overrides[get_current_user] = saved

    def test_422_schema_error_returns_details(self, v3_client: TestClient):
        """422 response on invalid schema."""
        resp = v3_client.post(
            "/api/v3/auth/users",
            json={
                "email": "not-an-email",
                "password": "short",
            },
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════
# Feature Flag Tests
# ═══════════════════════════════════════════════


class TestFeatureFlags:
    """Verify that v3 endpoints exist (no 404) even with flags off."""

    def test_v3_endpoints_exist_even_with_flags_off(self, v3_client: TestClient):
        """Endpoints route to v3 router — no 404 regardless of flag state."""
        sessions = [_make_session(id="s1")]
        with (
            patch("app.api.v3.auth.get_active_sessions", new=_am(sessions)),
            patch("app.api.v3.auth.decode_access_token", return_value={"session_id": "s1"}),
        ):
            resp = v3_client.get(
                "/api/v3/auth/sessions",
                headers={"Authorization": "Bearer test-token"},
            )
            assert resp.status_code != 404
