"""Tests for _authenticate_preview_request — the forward-auth cookie path.

Covers the UUID-vs-JWT cookie auth bug fix (Option A):
- Bearer header path (JWT decode, unchanged)
- ?token= query param path (JWT decode, unchanged)
- refresh_token cookie path (UUID → DB lookup, FIXED)
- fm_refresh_token legacy cookie path (UUID → DB lookup, FIXED)
- Priority order: Bearer → ?token= → cookies
- Edge cases: expired, revoked, malformed, unknown UUID
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request

from app.api.v1.sandbox_preview import _authenticate_preview_request, _is_jwt

# ── Helpers ────────────────────────────────────────────────────────────

# Patch targets — functions are imported *locally* inside
# _authenticate_preview_request, so we must patch at source.
_PATCH_DECODE = "app.api.deps.decode_access_token"
_PATCH_GET_DB = "app.database.get_db_session"
_PATCH_GET_RT = "app.services.auth_service.get_refresh_token"
_PATCH_GET_USER = "app.services.auth_service.get_user_by_id"


def _make_request(
    *,
    bearer: str | None = None,
    query_token: str | None = None,
    refresh_cookie: str | None = None,
    fm_refresh_cookie: str | None = None,
) -> Request:
    """Build a minimal Starlette Request for forward-auth testing."""
    scope: dict = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/sandbox/forward-auth",
        "query_string": b"",
        "headers": [],
    }
    if bearer:
        scope["headers"].append((b"authorization", f"Bearer {bearer}".encode()))
    if query_token:
        scope["query_string"] = f"token={query_token}".encode()
    # Starlette stores cookies as a raw header
    cookie_parts = []
    if refresh_cookie:
        cookie_parts.append(f"refresh_token={refresh_cookie}")
    if fm_refresh_cookie:
        cookie_parts.append(f"fm_refresh_token={fm_refresh_cookie}")
    if cookie_parts:
        scope["headers"].append((b"cookie", "; ".join(cookie_parts).encode()))
    return Request(scope)


def _fake_db_session(mock_db: AsyncMock):
    """Return an async generator that yields mock_db (matches get_db_session signature)."""

    async def _gen():
        yield mock_db

    return _gen()


# Fake JWT: >50 chars, contains dots
FAKE_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"

# Fake UUID: 36-char hex with hyphens
FAKE_UUID = "550e8400-e29b-41d4-a716-446655440000"


# ── _is_jwt helper ─────────────────────────────────────────────────────


def test_is_jwt_with_valid_jwt():
    assert _is_jwt(FAKE_JWT) is True


def test_is_jwt_with_uuid():
    assert _is_jwt(FAKE_UUID) is False


def test_is_jwt_with_short_string():
    assert _is_jwt("abc123") is False


# ── Bearer header path (unchanged) ────────────────────────────────────


@pytest.mark.anyio
async def test_bearer_header_returns_user_id():
    """Bearer header with valid JWT returns user_id."""
    req = _make_request(bearer=FAKE_JWT)
    mock_db = AsyncMock()
    mock_user = MagicMock(is_active=True, id=42)

    with (
        patch(_PATCH_DECODE, return_value="42"),
        patch(_PATCH_GET_DB, return_value=_fake_db_session(mock_db)),
        patch(_PATCH_GET_USER, new_callable=AsyncMock, return_value=mock_user),
    ):
        result = await _authenticate_preview_request(req)

    assert result == "42"


@pytest.mark.anyio
async def test_bearer_header_invalid_jwt_returns_none():
    """Bearer header with invalid JWT returns None."""
    req = _make_request(bearer=FAKE_JWT)

    with patch(_PATCH_DECODE, return_value=None):
        result = await _authenticate_preview_request(req)

    assert result is None


# ── ?token= query param path (unchanged) ──────────────────────────────


@pytest.mark.anyio
async def test_query_token_returns_user_id():
    """?token= with valid JWT returns user_id."""
    req = _make_request(query_token=FAKE_JWT)
    mock_db = AsyncMock()
    mock_user = MagicMock(is_active=True, id=99)

    with (
        patch(_PATCH_DECODE, return_value="99"),
        patch(_PATCH_GET_DB, return_value=_fake_db_session(mock_db)),
        patch(_PATCH_GET_USER, new_callable=AsyncMock, return_value=mock_user),
    ):
        result = await _authenticate_preview_request(req)

    assert result == "99"


# ── Cookie path — UUID refresh token (THE FIX) ───────────────────────


@pytest.mark.anyio
async def test_refresh_cookie_valid_uuid_returns_user_id():
    """Valid UUID refresh token cookie resolves via DB lookup → user_id."""
    req = _make_request(refresh_cookie=FAKE_UUID)
    mock_db = AsyncMock()

    mock_record = MagicMock()
    mock_record.user_id = 7
    mock_record.is_revoked = False
    mock_record.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30)

    mock_user = MagicMock(is_active=True, id=7)

    with (
        patch(_PATCH_GET_DB, return_value=_fake_db_session(mock_db)),
        patch(_PATCH_GET_RT, new_callable=AsyncMock, return_value=mock_record),
        patch(_PATCH_GET_USER, new_callable=AsyncMock, return_value=mock_user),
    ):
        result = await _authenticate_preview_request(req)

    assert result == "7"


@pytest.mark.anyio
async def test_refresh_cookie_expired_returns_none():
    """Expired UUID refresh token returns None."""
    req = _make_request(refresh_cookie=FAKE_UUID)
    mock_db = AsyncMock()

    mock_record = MagicMock()
    mock_record.user_id = 7
    mock_record.is_revoked = False
    mock_record.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)

    with (
        patch(_PATCH_GET_DB, return_value=_fake_db_session(mock_db)),
        patch(_PATCH_GET_RT, new_callable=AsyncMock, return_value=mock_record),
    ):
        result = await _authenticate_preview_request(req)

    assert result is None


@pytest.mark.anyio
async def test_refresh_cookie_revoked_returns_none():
    """Revoked UUID refresh token returns None (get_refresh_token filters revoked)."""
    req = _make_request(refresh_cookie=FAKE_UUID)
    mock_db = AsyncMock()

    with (
        patch(_PATCH_GET_DB, return_value=_fake_db_session(mock_db)),
        patch(_PATCH_GET_RT, new_callable=AsyncMock, return_value=None),
    ):
        result = await _authenticate_preview_request(req)

    assert result is None


@pytest.mark.anyio
async def test_refresh_cookie_unknown_uuid_returns_none():
    """Unknown UUID (not in DB) returns None."""
    req = _make_request(refresh_cookie=FAKE_UUID)
    mock_db = AsyncMock()

    with (
        patch(_PATCH_GET_DB, return_value=_fake_db_session(mock_db)),
        patch(_PATCH_GET_RT, new_callable=AsyncMock, return_value=None),
    ):
        result = await _authenticate_preview_request(req)

    assert result is None


# ── Legacy fm_refresh_token cookie ────────────────────────────────────


@pytest.mark.anyio
async def test_fm_refresh_legacy_cookie_works():
    """Legacy fm_refresh_token cookie also resolves via DB lookup."""
    req = _make_request(fm_refresh_cookie=FAKE_UUID)
    mock_db = AsyncMock()

    mock_record = MagicMock()
    mock_record.user_id = 55
    mock_record.is_revoked = False
    mock_record.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30)

    mock_user = MagicMock(is_active=True, id=55)

    with (
        patch(_PATCH_GET_DB, return_value=_fake_db_session(mock_db)),
        patch(_PATCH_GET_RT, new_callable=AsyncMock, return_value=mock_record),
        patch(_PATCH_GET_USER, new_callable=AsyncMock, return_value=mock_user),
    ):
        result = await _authenticate_preview_request(req)

    assert result == "55"


# ── Priority ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_bearer_wins_over_cookie():
    """Bearer header takes priority over cookie when both present."""
    req = _make_request(bearer=FAKE_JWT, refresh_cookie=FAKE_UUID)
    mock_db = AsyncMock()
    mock_user = MagicMock(is_active=True, id=10)

    with (
        patch(_PATCH_DECODE, return_value="10"),
        patch(_PATCH_GET_DB, return_value=_fake_db_session(mock_db)),
        patch(_PATCH_GET_USER, new_callable=AsyncMock, return_value=mock_user),
    ):
        result = await _authenticate_preview_request(req)

    assert result == "10"


# ── Edge cases ────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_no_token_returns_none():
    """Request with no auth returns None."""
    req = _make_request()
    result = await _authenticate_preview_request(req)
    assert result is None


@pytest.mark.anyio
async def test_malformed_cookie_returns_none():
    """Garbage cookie value returns None without crashing."""
    req = _make_request(refresh_cookie="not-a-uuid-not-a-jwt")
    mock_db = AsyncMock()

    with (
        patch(_PATCH_GET_DB, return_value=_fake_db_session(mock_db)),
        patch(_PATCH_GET_RT, new_callable=AsyncMock, return_value=None),
    ):
        result = await _authenticate_preview_request(req)

    assert result is None
