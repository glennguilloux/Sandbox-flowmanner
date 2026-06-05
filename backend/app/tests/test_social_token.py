"""
Integration tests for POST /api/auth/social/token.

Covers GitHub and Google OAuth token exchange:
- Unsupported provider → 400
- Rate limited → 429
- Invalid access token → 401
- New GitHub user → 200 (creates user + OIDC link + workspace)
- Returning GitHub user → 200 (finds by OIDC account)
- Email-linked user → 200 (finds by email, links OIDC)
- New Google user → 200 (creates user via Google profile)
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main_fastapi import app

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-123")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-123")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_github_profile():
    """Return a fake GitHub profile dict that _fetch_social_profile would return."""
    return {
        "id": "123456",
        "login": "ghuser",
        "email": "ghuser@example.com",
        "name": "GitHub User",
        "avatar": "https://avatars.githubusercontent.com/u/123456",
        "display_name": "GitHub",
        "issuer_url": "https://github.com",
    }


def _mock_google_profile():
    """Return a fake Google profile dict that _fetch_social_profile would return."""
    return {
        "id": "789012",
        "login": "guser",
        "email": "guser@gmail.com",
        "name": "Google User",
        "avatar": "https://lh3.googleusercontent.com/photo",
        "display_name": "Google",
        "issuer_url": "https://accounts.google.com",
    }


def _make_db_result(*, scalar_one_or_none=None):
    """Create a MagicMock that behaves like a SQLAlchemy AsyncResult."""
    result = MagicMock()
    # scalar_one_or_none() is synchronous in SQLAlchemy
    result.scalar_one_or_none.return_value = scalar_one_or_none
    return result


def _make_mock_user(**kwargs):
    """Create a mock User with sensible defaults."""
    user = MagicMock()
    user.id = kwargs.get("id", 1)
    user.email = kwargs.get("email", "test@example.com")
    user.username = kwargs.get("username", "testuser")
    user.full_name = kwargs.get("full_name", "Test User")
    user.avatar_url = kwargs.get("avatar_url")
    user.role = kwargs.get("role", "user")
    user.tenant_id = kwargs.get("tenant_id", 1)
    user.is_active = True
    user.login_count = 0
    user.last_login_at = None
    return user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_session():
    """AsyncMock simulating an async SQLAlchemy session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def test_client(mock_db_session):
    """TestClient with DB override."""
    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 1. Unsupported provider
# ---------------------------------------------------------------------------

def test_social_token_unsupported_provider(test_client, mock_db_session):
    """POST /api/auth/social/token with unsupported provider returns 400."""
    with patch("app.api.v1.auth.check_rate_limit", return_value=(True, 5, 0)):
        response = test_client.post("/api/auth/social/token", json={
            "provider": "twitter",
            "access_token": "fake-token",
        })
    assert response.status_code == 400
    assert "Unsupported provider" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 2. Rate limited — too many requests from same IP
# ---------------------------------------------------------------------------

def test_social_token_rate_limited(test_client, mock_db_session):
    """POST /api/auth/social/token returns 429 when rate limit is exceeded."""
    rate_limit_mock = MagicMock(return_value=(False, 0, 42))

    with patch("app.api.v1.auth.check_rate_limit", rate_limit_mock):
        response = test_client.post("/api/auth/social/token", json={
            "provider": "github",
            "access_token": "gho_valid_token",
        })

    assert response.status_code == 429
    data = response.json()
    assert "Too many" in data["detail"]
    # Verify the rate limiter was consulted with the correct key pattern
    rate_limit_mock.assert_called_once()
    key_arg = rate_limit_mock.call_args[0][0]
    assert key_arg.startswith("social_token:")


# ---------------------------------------------------------------------------
# 3. Invalid GitHub token (API rejects it)
# ---------------------------------------------------------------------------

def test_social_token_github_invalid_token(test_client, mock_db_session):
    """POST /api/auth/social/token with invalid GitHub token returns 401."""
    async def raise_401(*args, **kwargs):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub access token",
        )

    with patch("app.api.v1.auth.check_rate_limit", return_value=(True, 5, 0)):
        with patch("app.api.v1.auth._fetch_social_profile", side_effect=raise_401):
            response = test_client.post("/api/auth/social/token", json={
                "provider": "github",
                "access_token": "invalid-github-token",
            })

    assert response.status_code == 401
    assert "Invalid GitHub access token" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 4. New GitHub user — first login
# ---------------------------------------------------------------------------

@patch("app.services.auth_service.create_user")
def test_social_token_github_new_user(
    mock_create_user_svc,
    test_client,
    mock_db_session,
):
    """First GitHub OAuth login: creates user, OIDC link, workspace, returns tokens."""
    profile = _mock_github_profile()

    with patch("app.api.v1.auth.check_rate_limit", return_value=(True, 5, 0)):
        with patch("app.api.v1.auth._fetch_social_profile", AsyncMock(return_value=profile)):
            with patch("app.api.v1.auth._ensure_oidc_provider", AsyncMock(return_value="github-uuid-1234")):

                # All DB queries return None (no existing user / OIDC link)
                mock_db_session.execute.return_value = _make_db_result(scalar_one_or_none=None)

                new_user = _make_mock_user(id=42, email=profile["email"], username=profile["login"])
                mock_create_user_svc.return_value = new_user

                with patch("app.api.v1.auth.create_access_token", return_value="acc-github-new-42"):
                    with patch("app.api.v1.auth._issue_refresh_token", AsyncMock(return_value="ref-github-new-42")):

                        response = test_client.post("/api/auth/social/token", json={
                            "provider": "github",
                            "access_token": "gho_valid_token",
                        })

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "acc-github-new-42"
    assert data["refresh_token"] == "ref-github-new-42"

    # Verify _link_oidc_account was called (via db.add being called)
    assert mock_db_session.add.called, "Expected OIDC account link to be created"

    # Verify user created with correct fields
    mock_create_user_svc.assert_called_once()
    call_kwargs = mock_create_user_svc.call_args.kwargs
    assert call_kwargs["email"] == profile["email"]
    assert call_kwargs["full_name"] == profile["name"]
    assert call_kwargs["username"] == profile["login"]

    # Verify avatar was set
    assert new_user.avatar_url == profile["avatar"]


# ---------------------------------------------------------------------------
# 5. Returning GitHub user — OIDC account link exists
# ---------------------------------------------------------------------------

def test_social_token_github_returning_user(test_client, mock_db_session):
    """Returning GitHub OAuth: finds existing OIDC account → returns tokens."""
    profile = _mock_github_profile()
    existing_user = _make_mock_user(id=42, email=profile["email"])

    mock_oidc_account = MagicMock()
    mock_oidc_account.user_id = 42

    with patch("app.api.v1.auth.check_rate_limit", return_value=(True, 5, 0)):
        with patch("app.api.v1.auth._fetch_social_profile", AsyncMock(return_value=profile)):
            with patch("app.api.v1.auth._ensure_oidc_provider", AsyncMock(return_value="github-uuid-1234")):

                # Query 1: OIDC account → found
                # Query 2: User by id → found
                call_count = [0]

                async def execute_side_effect(*args, **kwargs):
                    call_count[0] += 1
                    if call_count[0] == 1:
                        return _make_db_result(scalar_one_or_none=mock_oidc_account)
                    else:
                        return _make_db_result(scalar_one_or_none=existing_user)

                mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)

                with patch("app.api.v1.auth.create_access_token", return_value="acc-returning-42"):
                    with patch("app.api.v1.auth._issue_refresh_token", AsyncMock(return_value="ref-returning-42")):

                        response = test_client.post("/api/auth/social/token", json={
                            "provider": "github",
                            "access_token": "gho_valid_token",
                        })

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "acc-returning-42"
    assert data["refresh_token"] == "ref-returning-42"


# ---------------------------------------------------------------------------
# 6. Email-linked user — existing account by email, link OIDC
# ---------------------------------------------------------------------------

def test_social_token_github_email_link(test_client, mock_db_session):
    """Existing user by email (no OIDC link): links OIDC account → returns tokens."""
    profile = _mock_github_profile()
    existing_user = _make_mock_user(id=99, email=profile["email"], avatar_url=None)

    with patch("app.api.v1.auth.check_rate_limit", return_value=(True, 5, 0)):
        with patch("app.api.v1.auth._fetch_social_profile", AsyncMock(return_value=profile)):
            with patch("app.api.v1.auth._ensure_oidc_provider", AsyncMock(return_value="github-uuid-1234")):

                # Query 1: OIDC account lookup → None (no link yet)
                # Query 2: User by email → found
                call_count = [0]

                async def execute_side_effect(*args, **kwargs):
                    call_count[0] += 1
                    if call_count[0] == 1:
                        return _make_db_result(scalar_one_or_none=None)
                    elif call_count[0] == 2:
                        return _make_db_result(scalar_one_or_none=existing_user)
                    else:
                        return _make_db_result(scalar_one_or_none=None)

                mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)

                with patch("app.api.v1.auth.create_access_token", return_value="acc-email-link-99"):
                    with patch("app.api.v1.auth._issue_refresh_token", AsyncMock(return_value="ref-email-link-99")):

                        response = test_client.post("/api/auth/social/token", json={
                            "provider": "github",
                            "access_token": "gho_valid_token",
                        })

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "acc-email-link-99"
    assert data["refresh_token"] == "ref-email-link-99"

    # Verify OIDC link was created (db.add called for UserOIDCAccount)
    assert mock_db_session.add.called, "Expected OIDC account to be linked"

    # Avatar should be set (was None before, now has GitHub avatar)
    assert existing_user.avatar_url == profile["avatar"]


# ---------------------------------------------------------------------------
# 7. New Google user — first login
# ---------------------------------------------------------------------------

@patch("app.services.auth_service.create_user")
def test_social_token_google_new_user(
    mock_create_user_svc,
    test_client,
    mock_db_session,
):
    """First Google OAuth login: creates user via Google profile → returns tokens."""
    profile = _mock_google_profile()

    with patch("app.api.v1.auth.check_rate_limit", return_value=(True, 5, 0)):
        with patch("app.api.v1.auth._fetch_social_profile", AsyncMock(return_value=profile)):
            with patch("app.api.v1.auth._ensure_oidc_provider", AsyncMock(return_value="google-uuid-5678")):

                mock_db_session.execute.return_value = _make_db_result(scalar_one_or_none=None)

                new_user = _make_mock_user(id=55, email=profile["email"], username=profile["login"])
                mock_create_user_svc.return_value = new_user

                with patch("app.api.v1.auth.create_access_token", return_value="acc-google-new-55"):
                    with patch("app.api.v1.auth._issue_refresh_token", AsyncMock(return_value="ref-google-new-55")):

                        response = test_client.post("/api/auth/social/token", json={
                            "provider": "google",
                            "access_token": "ya29.valid_google_token",
                        })

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "acc-google-new-55"
    assert data["refresh_token"] == "ref-google-new-55"

    mock_create_user_svc.assert_called_once()
    call_kwargs = mock_create_user_svc.call_args.kwargs
    assert call_kwargs["email"] == profile["email"]  # "guser@gmail.com"
    assert call_kwargs["full_name"] == profile["name"]  # "Google User"
    assert mock_db_session.add.called
    assert new_user.avatar_url == profile["avatar"]
