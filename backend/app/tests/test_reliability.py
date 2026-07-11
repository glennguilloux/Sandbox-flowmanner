"""Tests for /api/reliability auth enforcement (P0 security punchlist).

Verifies that the read report requires a valid JWT and the chaos toggle
requires an admin role. Self-contained: uses inline dependency overrides
rather than the test_client fixture (which lives in backend/tests/, not an
ancestor of app/tests/), mirroring the override pattern in
app/tests/test_auth_api.py (test_get_me_authenticated).
"""

import os
from unittest.mock import AsyncMock, MagicMock

# 32+ char secrets required by app.config production-secret guard.
os.environ.update(
    OPENAI_API_KEY="***",
    JWT_SECRET_KEY="test-jwt-secret-key-1234567890ab",
    SECRET_KEY="test-secret-key-1234567890abcdefghij",
    AES_ENCRYPTION_KEY="test-aes-key-16-char-abcdefghijk",
    SENTRY_WEBHOOK_SECRET="test-webhook-secret-16char",
    LANGFUSE_PUBLIC_KEY="x",
    LANGFUSE_SECRET_KEY="x",
    APP_ENV="test",
    LANGFUSE_ENABLED="false",
)

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.database import get_db
from app.main_fastapi import app


@pytest.fixture
def admin_user():
    return MagicMock(
        id=1,
        email="admin@example.com",
        username="admin",
        role="admin",
        is_admin=True,
        is_active=True,
    )


@pytest.fixture
def regular_user():
    return MagicMock(
        id=2,
        email="user@example.com",
        username="user",
        role="user",
        is_admin=False,
        is_active=True,
    )


@pytest.fixture
def mock_db():
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.fixture
def reliability_client(mock_db):
    """TestClient with get_db overridden; get_current_user is set per-test."""

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _override_user(user):
    async def override_get_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user


def test_get_reliability_unauthenticated(reliability_client):
    """GET /api/reliability without a token must be rejected (401)."""
    response = reliability_client.get("/api/reliability")
    assert response.status_code == 401


def test_get_reliability_authenticated(reliability_client, admin_user):
    """GET /api/reliability with a valid token must return 200."""
    _override_user(admin_user)
    response = reliability_client.get("/api/reliability")
    assert response.status_code == 200


def test_post_chaos_unauthenticated(reliability_client):
    """POST /api/reliability/chaos without a token must be rejected (401)."""
    response = reliability_client.post(
        "/api/reliability/chaos", json={"enabled": True}
    )
    assert response.status_code == 401


def test_post_chaos_as_admin(reliability_client, admin_user):
    """POST /api/reliability/chaos with an admin token must return 200."""
    _override_user(admin_user)
    response = reliability_client.post(
        "/api/reliability/chaos", json={"enabled": True}
    )
    assert response.status_code == 200


def test_post_chaos_as_non_admin_forbidden(reliability_client, regular_user):
    """POST /api/reliability/chaos with a non-admin token must be forbidden (403)."""
    _override_user(regular_user)
    response = reliability_client.post(
        "/api/reliability/chaos", json={"enabled": True}
    )
    assert response.status_code == 403
