import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.api.deps import get_current_user
from app.main_fastapi import app

os.environ.setdefault("OPENAI_API_KEY", "***")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")


@pytest.fixture
def sample_user():
    user = MagicMock()
    user.id = 1
    user.email = "test@example.com"
    user.username = "testuser"
    user.full_name = None
    user.hashed_password = "hashed_placeholder"
    user.is_active = True
    user.role = "user"
    user.is_admin = False
    user.is_superuser = False
    user.avatar_url = None
    user.created_at = datetime.now()
    user.login_count = 0
    user.last_login_at = None
    user.onboarding_step = "welcome"
    user.onboarding_completed = False
    user.onboarding_completed_at = None
    user.onboarding_data = "{}"
    user.totp_enabled = False
    return user


def test_register_success(test_client, mock_db_session):
    """POST /api/auth/register returns 201 with tokens."""
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
    with (
        patch("app.api.v1.auth.check_rate_limit", return_value=(True, 5, 0)),
        patch("app.api.v1.auth.create_access_token", return_value="acc-test-123"),
        patch("app.api.v1.auth.create_refresh_token_value", return_value="ref-test-456"),
        patch(
            "app.services.auth_service.create_user",
            return_value=MagicMock(id=1, role="user"),
        ),
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
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = MagicMock()
    with patch("app.api.v1.auth.check_rate_limit", return_value=(True, 5, 0)):
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
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = sample_user
    with (
        patch("app.api.v1.auth.check_rate_limit", return_value=(True, 5, 0)),
        patch(
            "app.api.v1.auth.record_failed_login",
            return_value={
                "locked": False,
                "attempts_remaining": 5,
                "lockout_seconds": 0,
                "progressive_delay_ms": 0,
            },
        ),
        patch("app.api.v1.auth.reset_login_attempts", return_value=None),
        patch("app.api.v1.auth.verify_password", return_value=True),
        patch("app.api.v1.auth.create_access_token", return_value="acc-test-123"),
        patch("app.api.v1.auth.create_refresh_token_value", return_value="ref-test-456"),
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
        patch("app.api.v1.auth.check_rate_limit", return_value=(True, 5, 0)),
        patch(
            "app.api.v1.auth.record_failed_login",
            return_value={
                "locked": False,
                "attempts_remaining": 5,
                "lockout_seconds": 0,
                "progressive_delay_ms": 0,
            },
        ),
        patch("app.api.v1.auth.verify_password", return_value=False),
    ):
        response = test_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "WrongPass!"},
        )
        assert response.status_code == 401


def test_get_me_authenticated(test_client, sample_user):
    """GET /api/auth/me with valid auth returns 200."""
    app.dependency_overrides[get_current_user] = lambda: sample_user
    try:
        response = test_client.get("/api/auth/me", headers={"Authorization": "Bearer test-token"})
        assert response.status_code == 200
        assert response.json()["email"] == sample_user.email
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_get_me_unauthenticated(test_client):
    """GET /api/auth/me without auth returns 401."""
    response = test_client.get("/api/auth/me")
    assert response.status_code == 401


def test_logout(test_client, sample_user):
    """POST /api/auth/logout returns 204."""
    app.dependency_overrides[get_current_user] = lambda: sample_user
    try:
        with patch("app.api.v1.auth.revoke_refresh_token", return_value=None):
            response = test_client.post(
                "/api/auth/logout",
                json={"refresh_token": "test-refresh"},
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status_code == 204
    finally:
        app.dependency_overrides.pop(get_current_user, None)
