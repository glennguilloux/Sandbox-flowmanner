"""Unit tests for Auth v3 schemas and service functions (no DB).

Tests Pydantic schema validation, API key generation, token hashing,
scope validation, and session token utilities.
"""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from app.models.auth_v3_models import (
    ApiKey,
    AuthSession,
    AuthWebhookSubscription,
)
from app.schemas.auth_v3 import (
    ApiKeyListResponse,
    ApiKeyResponse,
    CreateApiKeyRequest,
    LoginRequest,
    RegisterRequest,
    SessionResponse,
    UpdateUserRequest,
    UserSummary,
    Verify2FARequest,
)
from app.services.auth_v3_service import (
    generate_invite_token,
    hash_refresh_token,
    validate_api_key_scopes,
    validate_role,
)

# ═══════════════════════════════════════════════
# LoginRequest Schema Tests
# ═══════════════════════════════════════════════


class TestLoginRequestSchema:
    def test_valid_email_login(self):
        req = LoginRequest(login="user@example.com", password="securePass1!")
        assert req.login == "user@example.com"
        assert req.password == "securePass1!"
        assert req.provider == "credentials"

    def test_valid_username_login(self):
        req = LoginRequest(login="testuser", password="securePass1!")
        assert req.login == "testuser"

    def test_empty_login_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(login="", password="x")

    def test_empty_password_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(login="user@example.com", password="")

    def test_invalid_email_double_at_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(login="user@@example.com", password="securePass1!")

    def test_provider_defaults_to_credentials(self):
        req = LoginRequest(login="user@example.com", password="securePass1!")
        assert req.provider == "credentials"

    def test_oidc_provider_accepted(self):
        req = LoginRequest(
            login="user@example.com", password="oidc-code", provider="oidc"
        )
        assert req.provider == "oidc"


# ═══════════════════════════════════════════════
# RegisterRequest Schema Tests
# ═══════════════════════════════════════════════


class TestRegisterRequestSchema:
    def test_valid_registration(self):
        req = RegisterRequest(
            email="newuser@example.com",
            password="securePass1!",
            full_name="New User",
        )
        assert req.email == "newuser@example.com"
        assert req.username is None

    def test_short_password_rejected(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", password="short")

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", password="securePass1!")

    def test_username_optional(self):
        req = RegisterRequest(
            email="a@b.com",
            password="securePass1!",
            username="cooluser",
        )
        assert req.username == "cooluser"


# ═══════════════════════════════════════════════
# Verify2FARequest Schema Tests
# ═══════════════════════════════════════════════


class TestVerify2FARequestSchema:
    def test_valid_2fa_request(self):
        req = Verify2FARequest(temp_token="eyJ...", code="123456")
        assert req.temp_token == "eyJ..."
        assert req.code == "123456"

    def test_short_code_rejected(self):
        with pytest.raises(ValidationError):
            Verify2FARequest(temp_token="eyJ...", code="12345")


# ═══════════════════════════════════════════════
# UpdateUserRequest Schema Tests
# ═══════════════════════════════════════════════


class TestUpdateUserRequestSchema:
    def test_valid_update(self):
        req = UpdateUserRequest(full_name="New Name")
        assert req.full_name == "New Name"
        assert req.password is None

    def test_short_password_rejected(self):
        with pytest.raises(ValidationError):
            UpdateUserRequest(password="short")

    def test_empty_update_allowed(self):
        req = UpdateUserRequest()
        assert req.full_name is None


# ═══════════════════════════════════════════════
# SessionResponse Schema Tests
# ═══════════════════════════════════════════════


class TestSessionResponseSchema:
    def test_serialization(self):
        from datetime import datetime, timezone

        resp = SessionResponse(
            access_token="eyJ...",
            session_id="sess_abc123",
            expires_at=datetime.now(UTC),
            user=UserSummary(
                id=1,
                email="a@b.com",
                username=None,
                full_name="A User",
                role="pro",
                avatar_url=None,
                totp_enabled=False,
            ),
        )
        data = resp.model_dump()
        assert data["access_token"] == "eyJ..."
        assert data["session_id"] == "sess_abc123"
        assert data["user"]["id"] == 1
        assert data["user"]["email"] == "a@b.com"

    def test_user_summary_attributes(self):
        user = UserSummary(
            id=42,
            email="test@example.com",
            username="tester",
            full_name="Test User",
            role="admin",
            avatar_url="https://example.com/avatar.png",
            totp_enabled=True,
        )
        assert user.role == "admin"
        assert user.totp_enabled is True


# ═══════════════════════════════════════════════
# CreateApiKeyRequest Schema Tests
# ═══════════════════════════════════════════════


class TestCreateApiKeyRequest:
    def test_valid_request(self):
        req = CreateApiKeyRequest(
            name="CI Key", scopes=["missions:read", "missions:write"]
        )
        assert req.name == "CI Key"
        assert req.scopes == ["missions:read", "missions:write"]

    def test_default_scopes(self):
        req = CreateApiKeyRequest(name="Default Key")
        assert req.scopes == ["missions:read"]

    def test_expires_in_days_validation(self):
        # Valid: 1–365
        CreateApiKeyRequest(name="Key", expires_in_days=30)
        CreateApiKeyRequest(name="Key", expires_in_days=365)

        # Invalid: 0 and 366
        with pytest.raises(ValidationError):
            CreateApiKeyRequest(name="Key", expires_in_days=0)
        with pytest.raises(ValidationError):
            CreateApiKeyRequest(name="Key", expires_in_days=366)


# ═══════════════════════════════════════════════
# API Key Generation Tests
# ═══════════════════════════════════════════════


class TestApiKeyGeneration:
    def test_generate_produces_valid_key(self):
        key, prefix, hash_val = ApiKey.generate_api_key()
        assert key.startswith("fm_")
        assert len(key) > 32  # fm_ + 40 hex chars
        assert len(prefix) == 8  # fm_ + 6 hex chars
        assert prefix.startswith("fm_")
        assert len(hash_val) == 64  # SHA-256 hex

    def test_keys_are_unique(self):
        keys = {ApiKey.generate_api_key()[0] for _ in range(100)}
        assert len(keys) == 100

    def test_key_hash_is_consistent(self):
        key, _, _ = ApiKey.generate_api_key()
        hash1 = ApiKey.hash_key(key)
        hash2 = ApiKey.hash_key(key)
        assert hash1 == hash2
        assert len(hash1) == 64


# ═══════════════════════════════════════════════
# Refresh Token Hashing Tests
# ═══════════════════════════════════════════════


class TestRefreshTokenHashing:
    def test_hash_is_sha256_hex(self):
        token = "test-token-abcdef123456"
        result = hash_refresh_token(token)
        assert len(result) == 64  # SHA-256 produces 64 hex chars
        assert result == AuthSession.make_refresh_token_hash(token)

    def test_same_input_same_hash(self):
        token = "my-refresh-token"
        assert hash_refresh_token(token) == hash_refresh_token(token)

    def test_different_inputs_different_hash(self):
        assert hash_refresh_token("token-a") != hash_refresh_token("token-b")


# ═══════════════════════════════════════════════
# Refresh Token Generation Tests
# ═══════════════════════════════════════════════


class TestRefreshTokenGeneration:
    def test_token_is_64_chars(self):
        token = AuthSession.generate_refresh_token()
        assert len(token) == 64  # 32 bytes → 64 hex chars

    def test_tokens_are_unique(self):
        tokens = {AuthSession.generate_refresh_token() for _ in range(100)}
        assert len(tokens) == 100


# ═══════════════════════════════════════════════
# Scope Validation Tests
# ═══════════════════════════════════════════════


class TestScopeValidation:
    def test_valid_scopes_pass(self):
        assert validate_api_key_scopes(["missions:read"]) is True
        assert validate_api_key_scopes(["missions:write"]) is True
        assert validate_api_key_scopes(["sessions:read"]) is True
        assert validate_api_key_scopes(["api_keys:write"]) is True

    def test_invalid_scope_rejected(self):
        assert validate_api_key_scopes(["superadmin:destroy"]) is False
        assert validate_api_key_scopes(["invalid"]) is False

    def test_empty_scopes_rejected(self):
        assert validate_api_key_scopes([]) is False

    def test_mixed_scopes(self):
        # One valid, one invalid
        assert validate_api_key_scopes(["missions:read", "invalid:scope"]) is False

    def test_all_valid_scopes(self):
        valid = [
            "missions:read",
            "missions:write",
            "sessions:read",
            "sessions:write",
            "api_keys:read",
            "api_keys:write",
            "webhooks:read",
            "webhooks:write",
            "workspaces:read",
            "workspaces:write",
            "agents:read",
            "agents:write",
        ]
        for scope in valid:
            assert (
                validate_api_key_scopes([scope]) is True
            ), f"Scope {scope} should be valid"


# ═══════════════════════════════════════════════
# Role Validation Tests
# ═══════════════════════════════════════════════


class TestRoleValidation:
    def test_valid_roles(self):
        for role in ["viewer", "member", "admin", "owner"]:
            assert validate_role(role) is True

    def test_invalid_role(self):
        assert validate_role("bogus") is False
        assert validate_role("superadmin") is False
        assert validate_role("") is False


# ═══════════════════════════════════════════════
# Invite Token Generation Tests
# ═══════════════════════════════════════════════


class TestInviteTokenGeneration:
    def test_token_is_64_chars(self):
        token = generate_invite_token()
        assert len(token) == 64
        # Should be all hex characters
        assert all(c in "0123456789abcdef" for c in token)

    def test_tokens_are_unique(self):
        tokens = {generate_invite_token() for _ in range(100)}
        assert len(tokens) == 100


# ═══════════════════════════════════════════════
# Webhook Secret Tests
# ═══════════════════════════════════════════════


class TestWebhookSecretGeneration:
    def test_secret_is_64_chars(self):
        secret = AuthWebhookSubscription.generate_secret()
        assert len(secret) == 64

    def test_secrets_are_unique(self):
        secrets = {AuthWebhookSubscription.generate_secret() for _ in range(100)}
        assert len(secrets) == 100
