"""Tests for audit B18 — auth-error telemetry in ``get_current_user_optional``.

Behaviour contract (unchanged): the dependency returns ``None`` on *any* auth
failure (missing token, expired, forged, unresolvable user). This test asserts
that contract is preserved AND that an observability-only structured log records
the failure *category* (no_token / expired / invalid_signature / invalid_token /
user_resolution / other) so operators can distinguish failure modes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as _jwt
import pytest
from starlette.requests import Request

from app.api.deps import get_current_user_optional
from app.config import settings

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


def _make_request(authorization: str | None) -> Request:
    """Build a minimal Starlette Request carrying an Authorization header."""
    headers = {}
    if authorization is not None:
        headers["authorization"] = authorization
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/tool/stats",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


def _v3_access_token(user_id: int = 42, exp: datetime | None = None) -> str:
    payload = {
        "sub": str(user_id),
        "exp": exp or (datetime.now(UTC) + timedelta(hours=1)),
        "type": "access",
        "role": "user",
        "session_id": "sess_test",
    }
    return _jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def _v3_expired_token(user_id: int = 42) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) - timedelta(hours=1),
        "type": "access",
        "role": "user",
        "session_id": "sess_test",
    }
    return _jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def _forged_token() -> str:
    # Signed with a wrong key → invalid signature.
    payload = {
        "sub": "42",
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "type": "access",
    }
    return _jwt.encode(payload, "definitely-not-the-real-secret", algorithm="HS256")


def _find_telemetry(caplog) -> list:
    """Return the structured extra dicts emitted on 'optional_user_auth_failed'."""
    return [rec.__dict__ for rec in caplog.records if rec.getMessage() == "optional_user_auth_failed"]


# ──────────────────────────────────────────────────────────────
# Behaviour-preserving: MUST return None on every failure mode
# ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_returns_none_without_authorization_header(mock_db_session, caplog):
    """No Authorization header → None (unchanged behaviour)."""
    import logging

    caplog.set_level(logging.DEBUG, logger="app.api.deps")
    req = _make_request(None)
    result = await get_current_user_optional(req, db=mock_db_session)
    assert result is None

    telemetry = _find_telemetry(caplog)
    assert telemetry, "expected a telemetry record for the missing-token case"
    assert telemetry[0]["category"] == "missing_or_malformed_authorization_header"


@pytest.mark.asyncio
async def test_returns_none_with_non_bearer_header(mock_db_session, caplog):
    """Non-Bearer Authorization header → None (unchanged behaviour)."""
    import logging

    caplog.set_level(logging.DEBUG, logger="app.api.deps")
    req = _make_request("Basic abcdef")
    result = await get_current_user_optional(req, db=mock_db_session)
    assert result is None
    assert _find_telemetry(caplog)


@pytest.mark.asyncio
async def test_returns_none_on_forged_token(mock_db_session, caplog):
    """Forged/invalid-signature token → None, telemetry marks invalid_signature."""
    import logging

    caplog.set_level(logging.DEBUG, logger="app.api.deps")

    # The decode helpers swallow the JWTError and return None, so user resolution
    # never runs; we still expect None and a logged failure category.
    with (
        patch("app.api.deps.get_user_by_id", new=AsyncMock()),
        patch("app.api.deps.backfill_session_from_v1", new=AsyncMock()),
    ):
        req = _make_request(f"Bearer {_forged_token()}")
        result = await get_current_user_optional(req, db=mock_db_session)

    assert result is None
    telemetry = _find_telemetry(caplog)
    assert telemetry, "expected telemetry for a forged token"
    # Forged token → helpers return None → classified as invalid_token
    # (no exception surfaced; raw re-decode also fails to verify signature).
    assert telemetry[0]["category"] in (
        "token_malformed_or_wrong_type",
        "token_signature_invalid",
    )


@pytest.mark.asyncio
async def test_returns_none_on_valid_token_but_missing_user(mock_db_session, caplog):
    """Valid token but user not found → None, telemetry marks user_resolution."""
    import logging

    caplog.set_level(logging.DEBUG, logger="app.api.deps")

    token = _v3_access_token(424242)

    async def _no_user(db, uid):
        return None

    with patch("app.api.deps.get_user_by_id", new=AsyncMock(side_effect=_no_user)):
        req = _make_request(f"Bearer {token}")
        result = await get_current_user_optional(req, db=mock_db_session)

    assert result is None
    telemetry = _find_telemetry(caplog)
    assert telemetry, "expected telemetry for an unresolvable user"
    assert telemetry[0]["category"] == "token_valid_but_user_not_found_or_inactive"


@pytest.mark.asyncio
async def test_returns_user_on_valid_token(mock_db_session, caplog):
    """Valid token + resolvable active user → the user object (unchanged success)."""
    token = _v3_access_token(43)

    fake_user = MagicMock()
    fake_user.is_active = True

    async def _return_user(db, uid):
        return fake_user

    with (
        patch("app.api.deps.get_user_by_id", new=AsyncMock(side_effect=_return_user)),
        patch("app.api.deps.backfill_session_from_v1", new=AsyncMock()),
    ):
        req = _make_request(f"Bearer {token}")
        result = await get_current_user_optional(req, db=mock_db_session)

    assert result is fake_user


@pytest.mark.asyncio
async def test_expired_token_surfaces_expired_category(mock_db_session, caplog):
    """An expired token's decode raises ExpiredSignatureError → 'expired' category.

    get_current_user_optional must still return None; the telemetry path is
    what distinguishes expired from forged.
    """
    import logging

    caplog.set_level(logging.DEBUG, logger="app.api.deps")

    # Force the raw decode in _classify_optional_auth_failure to observe the expiry.
    token = _v3_expired_token(44)
    req = _make_request(f"Bearer {token}")
    result = await get_current_user_optional(req, db=mock_db_session)

    assert result is None
    telemetry = _find_telemetry(caplog)
    assert telemetry, "expected telemetry for an expired token"
    assert telemetry[0]["category"] == "token_expired"
