from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth_v3 import (
    CreateApiKeyRequest,
    LoginRequest,
    RegisterRequest,
)
from app.services.auth_v3_service import (
    create_access_token,
    decode_access_token,
    generate_invite_token,
    hash_refresh_token,
    validate_api_key_scopes,
    validate_role,
)


class TestLoginRequestSchema:
    def test_valid_email_login(self):
        req = LoginRequest(login="user@example.com", password="securePass1!")
        assert req.login == "user@example.com"
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

    def test_custom_provider(self):
        req = LoginRequest(login="a@b.com", password="pass", provider="oidc")
        assert req.provider == "oidc"


class TestRegisterRequestSchema:
    def test_valid_registration(self):
        req = RegisterRequest(email="new@example.com", password="StrongPass1!")
        assert req.email == "new@example.com"

    def test_short_password_rejected(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", password="short")

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", password="StrongPass1!")


class TestCreateApiKeyRequestSchema:
    def test_valid_request(self):
        req = CreateApiKeyRequest(name="CI Key", scopes=["missions:read"])
        assert req.name == "CI Key"
        assert req.scopes == ["missions:read"]

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            CreateApiKeyRequest(name="", scopes=["missions:read"])


class TestScopeValidation:
    def test_valid_scopes_pass(self):
        assert validate_api_key_scopes(["missions:read"]) is True

    def test_multiple_valid_scopes(self):
        assert validate_api_key_scopes(["missions:read", "missions:write"]) is True

    def test_invalid_scope_rejected(self):
        assert validate_api_key_scopes(["superadmin:destroy"]) is False

    def test_empty_scopes_rejected(self):
        assert validate_api_key_scopes([]) is False


class TestRoleValidation:
    def test_valid_roles(self):
        for role in ["viewer", "member", "admin", "owner"]:
            assert validate_role(role) is True

    def test_invalid_role(self):
        assert validate_role("bogus") is False


class TestTokenHashing:
    def test_hash_refresh_token(self):
        token = "abc123def456"
        hashed = hash_refresh_token(token)
        assert len(hashed) == 64
        assert hashed != token

    def test_same_token_same_hash(self):
        token = "consistent-token"
        assert hash_refresh_token(token) == hash_refresh_token(token)


class TestInviteTokenGeneration:
    def test_token_is_64_chars(self):
        token = generate_invite_token()
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

    def test_tokens_are_unique(self):
        tokens = {generate_invite_token() for _ in range(100)}
        assert len(tokens) == 100


class TestAccessTokenCreation:
    def test_create_and_decode(self):
        from app.config import settings
        settings.JWT_SECRET_KEY = "test-secret-key-for-unit-tests-32chars!!"

        token = create_access_token(
            user_id=42,
            session_id="sess_abc123",
            tenant_id=1,
            role="admin",
            scopes=["missions:read"],
        )
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "42"
        assert payload["session_id"] == "sess_abc123"
        assert payload["role"] == "admin"
        assert "missions:read" in payload["scopes"]

    def test_invalid_token_returns_none(self):
        from app.config import settings
        settings.JWT_SECRET_KEY = "test-secret-key-for-unit-tests-32chars!!"

        result = decode_access_token("invalid.token.here")
        assert result is None
