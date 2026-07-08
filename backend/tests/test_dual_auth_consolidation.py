"""Tests for Item #10 — Dual-auth consolidation.

Verifies:
- backfill_session_from_v1() creates an AuthSession when none exists
- backfill_session_from_v1() returns existing active session (no duplicate)
- _create_access_token_dual_write() falls back to v1 on v3 failure
- _create_access_token_dual_write() returns v3 token on success
- JWT decode behavior (v1 vs v3 tokens)
- get_current_user() resolves v1 JWT with backfill
- get_current_user() resolves v3 JWT with active session
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as _jwt
import pytest

from app.config import settings
from app.services.auth_v3_service import (
    create_access_token as v3_create_access_token,
)
from app.services.auth_v3_service import (
    decode_access_token as v3_decode_access_token,
)

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


def _v1_access_token(user_id: int = 42) -> str:
    """Create a v1-style access token (no session_id)."""
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "type": "access",
        "role": "user",
    }
    return _jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


# ──────────────────────────────────────────────────────────────
# backfill_session_from_v1()
# ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backfill_creates_session_when_none_exists(mock_db_session):
    """backfill_session_from_v1 creates a new AuthSession when user has none."""
    from app.services.auth_v3_service import backfill_session_from_v1

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db_session.execute = AsyncMock(return_value=mock_result)
    mock_db_session.flush = AsyncMock()
    mock_db_session.refresh = AsyncMock()

    added_obj = {}
    mock_db_session.add = lambda obj: added_obj.__setitem__("session", obj)

    session = await backfill_session_from_v1(mock_db_session, 99901, ip_address="10.0.0.1")

    assert "session" in added_obj
    assert added_obj["session"].user_id == 99901
    assert added_obj["session"].is_active is True
    assert added_obj["session"].ip_address == "10.0.0.1"
    mock_db_session.flush.assert_called()


@pytest.mark.asyncio
async def test_backfill_returns_existing_session(mock_db_session):
    """backfill_session_from_v1 returns existing active session (no duplicate)."""
    from app.services.auth_v3_service import backfill_session_from_v1

    existing = MagicMock()
    existing.id = str(uuid.uuid4())
    existing.user_id = 99902
    existing.is_active = True

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = existing
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    session = await backfill_session_from_v1(mock_db_session, 99902)

    assert session.id == existing.id
    mock_db_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_creates_new_if_existing_is_revoked(mock_db_session):
    """backfill creates a new session if the existing one is revoked.

    The query filters by is_active=True, so a revoked session returns None
    from the query, and a new one is created.
    """
    from app.services.auth_v3_service import backfill_session_from_v1

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db_session.execute = AsyncMock(return_value=mock_result)
    mock_db_session.flush = AsyncMock()
    mock_db_session.refresh = AsyncMock()

    added_obj = {}
    mock_db_session.add = lambda obj: added_obj.__setitem__("session", obj)

    session = await backfill_session_from_v1(mock_db_session, 99903)

    assert "session" in added_obj
    assert added_obj["session"].is_active is True
    assert session is added_obj["session"]


# ──────────────────────────────────────────────────────────────
# JWT decode behavior
# ──────────────────────────────────────────────────────────────


def test_v3_decode_extracts_session_id():
    """v3 decode_access_token returns session_id in payload."""
    token = v3_create_access_token(user_id=42, session_id="abc-123", role="user")
    payload = v3_decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["session_id"] == "abc-123"


def test_v1_token_decoded_by_v3_has_no_session_id():
    """A v1-style token (no session_id) decoded by v3 decode still works."""
    token = _v1_access_token(user_id=42)
    payload = v3_decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == "42"
    assert "session_id" not in payload


# ──────────────────────────────────────────────────────────────
# Dual-write helper fallback
# ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dual_write_falls_back_on_v3_error(mock_db_session):
    """_create_access_token_dual_write returns v1 token if v3_create_session fails."""
    from app.api.v1.auth import _create_access_token_dual_write

    user = MagicMock()
    user.id = 42
    user.role = "user"
    request = MagicMock()
    request.headers = {"user-agent": "test-agent"}

    with patch("app.api.v1.auth.v3_create_session", new_callable=AsyncMock, side_effect=Exception("db error")):
        token = await _create_access_token_dual_write(mock_db_session, user, request, "127.0.0.1")

    payload = v3_decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert "session_id" not in payload


@pytest.mark.asyncio
async def test_dual_write_returns_v3_token_on_success(mock_db_session):
    """_create_access_token_dual_write returns v3 token with session_id."""
    from app.api.v1.auth import _create_access_token_dual_write

    user = MagicMock()
    user.id = 42
    user.role = "user"
    request = MagicMock()
    request.headers = {"user-agent": "test-agent"}

    mock_session = MagicMock()
    mock_session.id = str(uuid.uuid4())
    mock_session.is_active = True

    with patch(
        "app.api.v1.auth.v3_create_session",
        new_callable=AsyncMock,
        return_value=(mock_session, "fake_refresh"),
    ):
        token = await _create_access_token_dual_write(mock_db_session, user, request, "127.0.0.1")

    payload = v3_decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert "session_id" in payload
    assert payload["session_id"] == str(mock_session.id)


# ──────────────────────────────────────────────────────────────
# get_current_user unified resolution
# ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_current_user_v1_jwt_backfills(mock_db_session, mock_user):
    """get_current_user with a v1 JWT (no session_id) backfills and returns user."""
    from app.api.deps import get_current_user

    token = _v1_access_token(user_id=mock_user.id)

    with (
        patch("app.api.deps.get_user_by_id", new_callable=AsyncMock, return_value=mock_user),
        patch("app.api.deps.backfill_session_from_v1", new_callable=AsyncMock) as mock_backfill,
    ):
        user = await get_current_user(token=token, db=mock_db_session)

    assert user.id == mock_user.id
    mock_backfill.assert_called_once_with(mock_db_session, mock_user.id)


@pytest.mark.asyncio
async def test_get_current_user_v3_jwt_active_session_returns_user(mock_db_session, mock_user):
    """get_current_user with a valid v3 JWT and active session returns user."""
    from app.api.deps import get_current_user

    session_id = str(uuid.uuid4())
    token = v3_create_access_token(user_id=mock_user.id, session_id=session_id, role="user")

    mock_session = MagicMock()
    mock_session.id = session_id
    mock_session.is_active = True
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_session
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    with (
        patch("app.api.deps.get_user_by_id", new_callable=AsyncMock, return_value=mock_user),
        patch.object(mock_db_session, "execute", new_callable=AsyncMock, return_value=mock_result),
    ):
        user = await get_current_user(token=token, db=mock_db_session)

    assert user.id == mock_user.id


@pytest.mark.asyncio
async def test_get_current_user_expired_token_raises(mock_db_session):
    """get_current_user with an expired token raises 401."""
    from fastapi import HTTPException

    from app.api.deps import get_current_user

    expired_payload = {
        "sub": "42",
        "exp": datetime.now(UTC) - timedelta(hours=1),
        "type": "access",
        "role": "user",
    }
    token = _jwt.encode(expired_payload, settings.JWT_SECRET_KEY, algorithm="HS256")

    with pytest.raises(HTTPException, match=r"expired|Invalid"):
        await get_current_user(token=token, db=mock_db_session)


@pytest.mark.asyncio
async def test_get_current_user_invalid_token_raises(mock_db_session):
    """get_current_user with an invalid token raises 401."""
    from fastapi import HTTPException

    from app.api.deps import get_current_user

    with pytest.raises(HTTPException, match=r"Invalid|expired"):
        await get_current_user(token="not-a-valid-jwt", db=mock_db_session)
