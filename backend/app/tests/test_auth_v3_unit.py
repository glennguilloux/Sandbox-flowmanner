from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.auth_v3 import (
    CreateApiKeyRequest,
    LoginRequest,
    RegisterRequest,
)
from app.services.auth_v3_service import (
    _to_utc_aware,
    _to_utc_naive,
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

        assert decode_access_token("not-a-real-token") is None


# ═══════════════════════════════════════════════
# _to_utc_aware — regression for the v1→v3 refresh 500
# ═══════════════════════════════════════════════
#
# Background: 2026-06-15, every POST /api/v3/auth/sessions/refresh returned
# 500 with "can't compare offset-naive and offset-aware datetimes". Root
# cause: the v1 ``refresh_tokens`` table stores ``expires_at`` as naive UTC
# (``timestamp without time zone``), and the v3 migration code compared it
# directly to ``datetime.now(UTC)`` without reattaching tzinfo. These tests
# pin the helper that bridges the two representations. The endpoint-level
# behaviour is covered in test_auth_v3_integration.py.


class TestToUtcAware:
    def test_none_passes_through(self):
        assert _to_utc_aware(None) is None

    def test_naive_gets_utc_attached(self):
        naive = datetime(2026, 6, 15, 12, 0, 0)  # no tzinfo
        assert naive.tzinfo is None
        result = _to_utc_aware(naive)
        assert result is not None
        assert result.tzinfo is UTC
        assert result == naive.replace(tzinfo=UTC)

    def test_aware_passes_through_unchanged(self):
        aware = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        result = _to_utc_aware(aware)
        assert result is aware  # identity preserved, no rewrap

    def test_naive_in_past_compares_against_aware_now_without_raising(self):
        """Reproduces the original 500: comparing naive past < aware now()."""
        naive_past = datetime(2026, 6, 14, 0, 0, 0)  # naive, expired
        aware_now = datetime.now(UTC)
        # The original bug: naive_past < aware_now raises TypeError.
        with pytest.raises(TypeError):
            naive_past < aware_now  # noqa: B015  (raises inside pytest.raises)
        # After normalization: comparison works and reports "expired".
        normalized = _to_utc_aware(naive_past)
        assert normalized is not None
        assert normalized < aware_now  # no exception

    def test_naive_in_future_does_not_trigger_expiry(self):
        naive_future = datetime.now() + timedelta(days=7)  # naive
        normalized = _to_utc_aware(naive_future)
        assert normalized is not None
        assert normalized > datetime.now(UTC)  # not expired


class TestToUtcNaive:
    """Mirror of TestToUtcAware for the write-side: v1 columns are
    ``timestamp without time zone`` and asyncpg rejects aware datetimes
    on insert. The migration code in ``_try_migrate_v1_token`` must
    strip tzinfo before writing to ``refresh_tokens.last_used_at``."""

    def test_none_passes_through(self):
        assert _to_utc_naive(None) is None

    def test_aware_gets_tzinfo_stripped(self):
        aware = datetime.now(UTC)
        assert aware.tzinfo is not None
        result = _to_utc_naive(aware)
        assert result is not None
        assert result.tzinfo is None
        assert result == aware.replace(tzinfo=None)

    def test_naive_passes_through_unchanged(self):
        naive = datetime(2026, 6, 15, 12, 0, 0)
        result = _to_utc_naive(naive)
        assert result is naive  # identity preserved, no rewrap


# ═══════════════════════════════════════════════
# R2 — fail-closed v3 auth
# ═══════════════════════════════════════════════
# get_current_session must DENY (401) when token decode or the session lookup
# raises an unexpected exception — never fall through to an unhandled 500.
# These are DB-free: the db stub's execute() raises on purpose.


class _StubState:
    trace_id = None


class _StubRequest:
    """Minimal Request stand-in for get_current_session."""

    def __init__(self, *, cookie: object | None = None, bearer: str | None = None):
        self.cookies = {"fm_refresh_token": cookie} if cookie else {}
        headers = {}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        self.headers = headers
        self.state = _StubState()


class _RaisingDB:
    """AsyncSession stub whose execute() always raises."""

    async def execute(self, *args, **kwargs):
        raise RuntimeError("simulated session-store failure")


class TestGetCurrentSessionFailClosed:
    @pytest.mark.asyncio
    async def test_decode_exception_raises_401_not_500(self):
        from fastapi import HTTPException

        from app.api.deps import get_current_session

        # A truthy, non-str token makes jwt.decode raise TypeError — which is
        # OUTSIDE the (ExpiredSignatureError, InvalidTokenError) pair caught by
        # decode_access_token, so it would have escaped to a 500 before R2.
        req = _StubRequest(cookie=123, bearer=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_session(req, _RaisingDB())
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_session_lookup_exception_raises_401(self):
        from fastapi import HTTPException

        from app.config import settings
        from app.services.auth_v3_service import create_access_token

        settings.JWT_SECRET_KEY = "test-secret-key-for-unit-tests-32chars!!"
        token = create_access_token(user_id=1, session_id="sess_x")

        from app.api.deps import get_current_session

        req = _StubRequest(bearer=token)
        # db.execute raises AFTER a valid decode (during session lookup)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_session(req, _RaisingDB())
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_flag_false_still_denies_401(self):
        from fastapi import HTTPException

        from app.api.deps import get_current_session
        from app.config import settings

        settings.FLOWMANNER_CIRCUIT_BREAKER_FAIL_CLOSED = False
        try:
            req = _StubRequest(cookie=123, bearer=None)
            with pytest.raises(HTTPException) as exc_info:
                await get_current_session(req, _RaisingDB())
            assert exc_info.value.status_code == 401
        finally:
            settings.FLOWMANNER_CIRCUIT_BREAKER_FAIL_CLOSED = True
