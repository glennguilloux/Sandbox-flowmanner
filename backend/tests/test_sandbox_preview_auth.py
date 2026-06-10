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

from app.api.v1.sandbox_preview import (
    _auth_cache,
    _authenticate_preview_request,
    _is_jwt,
)


@pytest.fixture(autouse=True)
def _clear_auth_cache():
    """Clear the forward-auth cache between tests to prevent leakage."""
    _auth_cache.clear()
    yield
    _auth_cache.clear()


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


# ── Cache behavior ────────────────────────────────────────────────────


def test_token_hash_deterministic():
    """Same token always produces the same hash."""
    from app.api.v1.sandbox_preview import _token_hash

    assert _token_hash("abc123") == _token_hash("abc123")
    assert _token_hash("abc123") != _token_hash("def456")


def test_token_hash_no_raw_token_stored():
    """Hash does not contain the raw token string."""
    from app.api.v1.sandbox_preview import _token_hash

    h = _token_hash(FAKE_JWT)
    assert FAKE_JWT not in h
    assert len(h) == 16


def test_cache_set_and_get():
    """_cache_set stores a result, _cache_get retrieves it."""
    from app.api.v1.sandbox_preview import _cache_get, _cache_set

    _cache_set("my-token", "42")
    assert _cache_get("my-token") == "42"


def test_cache_miss_returns_none():
    """_cache_get returns None for unknown tokens."""
    from app.api.v1.sandbox_preview import _cache_get

    assert _cache_get("nonexistent") is None


def test_cache_expiry():
    """Expired entries return None."""
    import time as time_mod

    from app.api.v1.sandbox_preview import (
        _AUTH_CACHE_TTL,
        _auth_cache,
        _cache_get,
        _cache_set,
        _token_hash,
    )

    _cache_set("expiring-token", "99")
    # Manually expire the entry by setting expires_at to the past
    key = _token_hash("expiring-token")
    user_id, _ = _auth_cache[key]
    _auth_cache[key] = (user_id, time_mod.monotonic() - 1)

    assert _cache_get("expiring-token") is None
    # Entry should be evicted from dict
    assert key not in _auth_cache


def test_cache_eviction_on_full():
    """Cache evicts entries when max size is reached."""
    from app.api.v1.sandbox_preview import _AUTH_CACHE_MAX_SIZE, _auth_cache, _cache_set

    # Fill cache to max
    for i in range(_AUTH_CACHE_MAX_SIZE):
        _cache_set(f"token-{i}", str(i))
    assert len(_auth_cache) == _AUTH_CACHE_MAX_SIZE

    # Adding one more should evict an entry (not crash)
    _cache_set("overflow-token", "overflow")
    assert len(_auth_cache) <= _AUTH_CACHE_MAX_SIZE


@pytest.mark.anyio
async def test_cached_result_skips_db():
    """Second call with same token uses cache, not DB."""
    req = _make_request(bearer=FAKE_JWT)
    mock_db = AsyncMock()
    mock_user = MagicMock(is_active=True, id=42)

    # First call — populates cache
    with (
        patch(_PATCH_DECODE, return_value="42"),
        patch(_PATCH_GET_DB, return_value=_fake_db_session(mock_db)),
        patch(
            _PATCH_GET_USER, new_callable=AsyncMock, return_value=mock_user
        ) as mock_get_user,
    ):
        result1 = await _authenticate_preview_request(req)
        assert result1 == "42"
        assert mock_get_user.call_count == 1

    # Second call — should hit cache, NOT call get_user_by_id again
    with (
        patch(_PATCH_DECODE, return_value="42"),
        patch(_PATCH_GET_DB, return_value=_fake_db_session(mock_db)),
        patch(
            _PATCH_GET_USER, new_callable=AsyncMock, return_value=mock_user
        ) as mock_get_user,
    ):
        result2 = await _authenticate_preview_request(req)
        assert result2 == "42"
        assert mock_get_user.call_count == 0  # cache hit, no DB call
