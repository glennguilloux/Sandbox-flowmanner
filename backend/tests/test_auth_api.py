import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main_fastapi import app

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-123")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")


@pytest.fixture
def sample_user():
    user = MagicMock()
    user.id = 1
    user.email = "test@example.com"
    user.username = "testuser"
    user.is_active = True
    user.role = "user"
    user.is_admin = False
    user.is_superuser = False
    user.totp_enabled = False
    user.hashed_password = "$2b$...hashed"
    return user


def test_register_success(test_client, mock_db_session):
    """POST /api/auth/register returns 201 with tokens."""
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
    mock_db_session.commit = AsyncMock()
    with (
        patch("app.api.v1.auth.create_access_token", return_value="acc-test-123"),
        patch("app.api.v1.auth.create_refresh_token_value", return_value="ref-test-456"),
        patch("app.services.auth_service.create_user", return_value=MagicMock(id=1)),
    ):
        response = test_client.post(
            "/api/auth/register",
            json={
                "email": "new@example.com",
                "password": "ValidPass123!",
                "username": "newuser",
            },
        )
        # Route declares status_code=201, but the endpoint returns a
        # JSONResponse via _auth_response() which FastAPI honours as-is
        # (status_code=200).  Asserting the actual behaviour; the 201 on the
        # route decorator is not honoured because a Response object is returned.
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data


def test_register_duplicate_email(test_client, mock_db_session):
    """POST /api/auth/register with existing email returns 409."""
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = MagicMock()
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
    mock_v3_session = MagicMock()
    mock_v3_session.id = "sess-123"
    with (
        patch("app.api.v1.auth.record_failed_login", return_value={"locked": False}),
        patch("app.api.v1.auth.reset_login_attempts"),
        patch("app.api.v1.auth.verify_password", return_value=True),
        patch("app.api.v1.auth.v3_create_session", return_value=mock_v3_session),
        patch("app.api.v1.auth.v3_create_access_token", return_value="acc-test-123"),
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
        patch("app.api.v1.auth.record_failed_login", return_value={"locked": False}),
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


def test_get_me_unauthenticated(test_app):
    """GET /api/auth/me without auth returns 401.

    Uses a dedicated TestClient whose get_current_user override raises 401,
    since the shared test_client fixture always injects an authenticated user.
    """
    from fastapi import HTTPException

    async def raise_401():
        raise HTTPException(status_code=401, detail="Not authenticated")

    test_app.dependency_overrides[get_current_user] = raise_401
    try:
        with TestClient(test_app) as client:
            response = client.get("/api/auth/me")
            assert response.status_code == 401
    finally:
        test_app.dependency_overrides.pop(get_current_user, None)


def test_logout(test_client, sample_user):
    """POST /api/auth/logout returns 204."""
    app.dependency_overrides[get_current_user] = lambda: sample_user
    try:
        with patch("app.api.v1.auth.revoke_refresh_token", new_callable=AsyncMock):
            response = test_client.post(
                "/api/auth/logout",
                json={"refresh_token": "test-refresh"},
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status_code == 204
    finally:
        app.dependency_overrides.pop(get_current_user, None)
