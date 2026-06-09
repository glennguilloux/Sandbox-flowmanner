import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps import get_current_user
from app.database import get_db

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-123")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")


@pytest.fixture(autouse=True)
def _override_db(test_client, mock_db_session):
    """Override get_db to use mock_db_session so auth tests can configure DB mocks.

    test_client uses mock_db (bare AsyncMock) by default, but auth routes call
    get_user_by_email / db.execute directly and need the structured mock_db_session.
    """

    async def _override():
        yield mock_db_session

    test_client.app.dependency_overrides[get_db] = _override
    return
    # test_client teardown clears all overrides


def test_register_success(test_client, mock_db_session):
    """POST /api/auth/register returns 201 with tokens."""
    # get_user_by_email and get_user_by_username query the DB — return None (no existing user)
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
    with (
        patch("app.api.v1.auth.create_access_token", return_value="acc-test-123"),
        patch(
            "app.api.v1.auth.create_refresh_token_value", return_value="ref-test-456"
        ),
        patch(
            "app.services.auth_service.create_user",
            new_callable=AsyncMock,
            return_value=MagicMock(id=1, role="user"),
        ),
        patch("app.api.v1.auth.store_refresh_token", new_callable=AsyncMock),
        patch("app.api.v1.auth.validate_password_strength", return_value=[]),
    ):
        response = test_client.post(
            "/api/auth/register",
            json={
                "email": "new@example.com",
                "password": "ValidPass123!",
                "username": "newuser",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data


def test_register_duplicate_email(test_client, mock_db_session):
    """POST /api/auth/register with existing email returns 409."""
    # get_user_by_email returns a user → conflict
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = MagicMock()
    with patch("app.api.v1.auth.validate_password_strength", return_value=[]):
        response = test_client.post(
            "/api/auth/register",
            json={
                "email": "existing@example.com",
                "password": "ValidPass123!",
                "username": "newuser",
            },
        )
        assert response.status_code == 409


def test_login_success(test_client, mock_db_session, sample_user):
    """POST /api/auth/login with valid credentials returns 200."""
    sample_user.totp_enabled = False
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = sample_user
    with (
        patch("app.api.v1.auth.verify_password", return_value=True),
        patch("app.api.v1.auth.create_access_token", return_value="acc-test-123"),
        patch(
            "app.api.v1.auth.create_refresh_token_value", return_value="ref-test-456"
        ),
        patch("app.api.v1.auth.store_refresh_token", new_callable=AsyncMock),
        patch("app.api.v1.auth.track_login", new_callable=AsyncMock),
        patch(
            "app.api.v1.auth.record_failed_login",
            return_value={
                "locked": False,
                "attempts_remaining": 5,
                "lockout_seconds": 0,
            },
        ),
        patch("app.api.v1.auth.reset_login_attempts"),
    ):
        response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "CorrectPass123!"},
        )
        assert response.status_code == 200
        assert response.json()["access_token"] == "acc-test-123"


def test_login_invalid_password(test_client, mock_db_session, sample_user):
    """POST /api/auth/login with wrong password returns 401."""
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = sample_user
    with (
        patch("app.api.v1.auth.verify_password", return_value=False),
        patch(
            "app.api.v1.auth.record_failed_login",
            return_value={
                "locked": False,
                "attempts_remaining": 4,
                "lockout_seconds": 0,
            },
        ),
    ):
        response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "WrongPass!"},
        )
        assert response.status_code == 401


def test_get_me_authenticated(test_client, sample_user):
    """GET /api/auth/me with valid auth returns 200."""
    test_client.app.dependency_overrides[get_current_user] = lambda: sample_user
    try:
        response = test_client.get(
            "/api/auth/me", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        assert response.json()["email"] == sample_user.email
    finally:
        test_client.app.dependency_overrides.pop(get_current_user, None)


def test_get_me_unauthenticated(test_client):
    """GET /api/auth/me without auth returns 401."""
    # Remove the get_current_user override so the real dependency runs
    test_client.app.dependency_overrides.pop(get_current_user, None)
    response = test_client.get("/api/auth/me")
    assert response.status_code == 401


def test_logout(test_client, sample_user):
    """POST /api/auth/logout returns 204."""
    test_client.app.dependency_overrides[get_current_user] = lambda: sample_user
    try:
        with patch("app.api.v1.auth.revoke_refresh_token", new_callable=AsyncMock):
            response = test_client.post(
                "/api/auth/logout",
                json={"refresh_token": "test-refresh"},
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status_code == 204
    finally:
        test_client.app.dependency_overrides.pop(get_current_user, None)
