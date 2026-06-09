"""Tests for notification endpoints (Phase 3: DB-backed + web push)."""

import os
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main_fastapi import app

pytestmark = pytest.mark.integration

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-123")

# Notification router: prefix="/notifications", mounted at /api/users/me in api_v1
# Full path: /api/users/me/notifications/...
PREFIX = "/api/users/me/notifications"


def make_user():
    user = MagicMock()
    user.id = 1
    user.email = "notify@example.com"
    user.username = "notifyuser"
    user.is_active = True
    user.role = "user"
    return user


def make_mock_notification(
    nid=1,
    uid=1,
    title="Test",
    message="Test body",
    ntype="info",
    severity="info",
    is_read=False,
):
    n = MagicMock(spec=[])
    n.id = nid
    n.user_id = uid
    n.title = title
    n.message = message
    n.notification_type = ntype
    n.severity = severity
    n.is_read = is_read
    n.read_at = None
    n.entity_type = None
    n.entity_id = None
    n.meta = None
    now = datetime.now(UTC)
    n.created_at = now.isoformat()
    n.updated_at = now.isoformat()
    return n


def _real_mock_db_session(mock_db_session, notifications=None, scalar_value=None):
    """Configure mock_db_session.execute to return appropriate mocks."""
    mock_result = AsyncMock()
    # Use MagicMock for scalars/scalar/all so calling them doesn't return coroutines
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = notifications or []
    mock_result.scalars = MagicMock(return_value=scalars_mock)
    mock_result.scalar = MagicMock(return_value=scalar_value or 0)
    mock_result.scalar_one_or_none = MagicMock(
        return_value=notifications[0] if notifications else None
    )
    mock_db_session.execute.return_value = mock_result
    return mock_db_session


# ── Notification List & CRUD Tests ──────────────────────────────────────────


def test_list_notifications_success(test_client, mock_db_session):
    """GET /notifications/ returns paginated list."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        _real_mock_db_session(
            mock_db_session, notifications=[make_mock_notification()], scalar_value=1
        )
        response = test_client.get(f"{PREFIX}/")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_notifications_unread_only(test_client, mock_db_session):
    """GET /notifications/?unread_only=true filters read."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        _real_mock_db_session(mock_db_session, notifications=[], scalar_value=0)
        response = test_client.get(f"{PREFIX}/?unread_only=true")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_unread_count(test_client, mock_db_session):
    """GET /notifications/unread-count returns count."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        _real_mock_db_session(mock_db_session, scalar_value=3)
        response = test_client.get(f"{PREFIX}/unread-count")
        assert response.status_code == 200
        data = response.json()
        assert data["unread_count"] == 3
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_mark_read_success(test_client, mock_db_session):
    """POST /notifications/{id}/read marks as read."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        notif = make_mock_notification()
        _real_mock_db_session(mock_db_session, notifications=[notif])
        response = test_client.post(f"{PREFIX}/1/read")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_mark_read_not_found(test_client, mock_db_session):
    """POST /notifications/{id}/read returns 404 for unknown."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        _real_mock_db_session(mock_db_session, notifications=[])
        response = test_client.post(f"{PREFIX}/999/read")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_mark_all_read(test_client, mock_db_session):
    """POST /notifications/read-all marks all as read."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        _real_mock_db_session(
            mock_db_session, notifications=[make_mock_notification(is_read=True)]
        )
        response = test_client.post(f"{PREFIX}/read-all")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_delete_notification(test_client, mock_db_session):
    """DELETE /notifications/{id} returns 204."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        notif = make_mock_notification()
        _real_mock_db_session(mock_db_session, notifications=[notif])
        response = test_client.delete(f"{PREFIX}/1")
        assert response.status_code == 204
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_delete_notification_not_found(test_client, mock_db_session):
    """DELETE /notifications/{id} returns 404 for unknown."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        _real_mock_db_session(mock_db_session, notifications=[])
        response = test_client.delete(f"{PREFIX}/999")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ── Push Subscription Tests ────────────────────────────────────────────────


def test_push_subscribe_success(test_client, mock_db_session):
    """POST /notifications/push/subscribe stores subscription."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        # Simulate fresh subscription (no existing one found)
        mock_db_session.execute.return_value = AsyncMock(
            scalar_one_or_none=MagicMock(return_value=None)
        )
        payload = {
            "endpoint": "https://example.com/push/abc123",
            "keys": {
                "p256dh": "BP1qHww3Y...",
                "auth": "auth123...",
            },
        }
        response = test_client.post(
            f"{PREFIX}/push/subscribe",
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "subscribed"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_push_subscribe_missing_endpoint(test_client, mock_db_session):
    """POST /notifications/push/subscribe returns 400 without endpoint."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = test_client.post(
            f"{PREFIX}/push/subscribe",
            json={},
        )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_push_unsubscribe(test_client, mock_db_session):
    """POST /notifications/push/unsubscribe deactivates subscription."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        # Configure mock to return no existing subscription
        _real_mock_db_session(mock_db_session, notifications=[])
        payload = {"endpoint": "https://example.com/push/abc123"}
        response = test_client.post(
            f"{PREFIX}/push/unsubscribe",
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "unsubscribed"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_vapid_public_key(test_client):
    """GET /notifications/push/vapid-public-key returns a key string."""
    response = test_client.get(f"{PREFIX}/push/vapid-public-key")
    assert response.status_code == 200
    data = response.json()
    assert "public_key" in data
    assert isinstance(data["public_key"], str)
    assert len(data["public_key"]) > 0


# ── Auth Required Tests ─────────────────────────────────────────────────────


def test_notifications_require_auth(test_client):
    """All notification endpoints return 401 without auth."""
    endpoints = [
        ("GET", f"{PREFIX}/"),
        ("GET", f"{PREFIX}/unread-count"),
        ("POST", f"{PREFIX}/1/read"),
        ("POST", f"{PREFIX}/read-all"),
        ("DELETE", f"{PREFIX}/1"),
        ("POST", f"{PREFIX}/push/subscribe"),
        ("POST", f"{PREFIX}/push/unsubscribe"),
    ]
    for method, path in endpoints:
        response = test_client.request(method, path)
        assert (
            response.status_code == 401
        ), f"Expected 401 for {method} {path}, got {response.status_code}"


# ── Settings Tests ──────────────────────────────────────────────────────────


def test_get_notification_settings(test_client, mock_db_session):
    """GET /notifications/settings returns settings with defaults."""
    mock_user = make_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        # Return None for no settings (triggers defaults)
        mock_db_session.execute.return_value = AsyncMock(
            scalar_one_or_none=MagicMock(return_value=None)
        )
        response = test_client.get(f"{PREFIX}/settings")
        assert response.status_code == 200
        data = response.json()
        assert "email_enabled" in data
        assert "push_enabled" in data
        assert "in_app_enabled" in data
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ── SSE Stream Tests ────────────────────────────────────────────────────────


def test_notification_stream_requires_token(test_client):
    """GET /notifications/stream returns 401 without token."""
    response = test_client.get(f"{PREFIX}/stream")
    assert response.status_code == 401
    assert "Token required" in response.json()["detail"]


def test_notification_stream_invalid_token(test_client):
    """GET /notifications/stream returns 401 with bad token."""
    response = test_client.get(f"{PREFIX}/stream?token=bad-token")
    assert response.status_code == 401
