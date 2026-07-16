"""Regression test — v1 error-envelope status codes (research-brief P0).

Defends against the "200-success-false" anti-pattern: v1 endpoints used to
return HTTP 200 with a ``{"success": false, "error": ...}`` body on failure,
which breaks standard HTTP clients, monitoring, and automatic retries.

The fix (2026-07-16) keeps the response *body* backward-compatible (the
``success`` / ``error`` fields clients rely on are unchanged) but sets a proper
non-2xx HTTP status on the failure path:

- browser automation failure  -> 502 Bad Gateway  (upstream browser subsystem)
- tool execution failure      -> 500 Internal Server Error
- code sandbox failure        -> 500 Internal Server Error
- plugin execution failure    -> 500 Internal Server Error

Self-contained: uses inline dependency overrides rather than the ``test_client``
fixture (which lives in ``backend/tests/``, not an ancestor of ``app/tests/``),
mirroring the override pattern in ``app/tests/test_reliability.py``.
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
from app.main_fastapi import app


@pytest.fixture
def mock_user():
    return MagicMock(
        id="1",
        email="user@example.com",
        username="user",
        role="user",
        is_admin=False,
        is_active=True,
    )


@pytest.fixture
def client(mock_user):
    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_browser_navigate_failure_returns_non_2xx(client, monkeypatch):
    """A failing /api/browser/navigate must NOT return 200 + success:false.

    This is the core regression assertion for the research-brief P0 item:
    a browser-subsystem failure returns 502 (a non-2xx status) while the body
    still carries the backward-compatible success/error fields.
    """
    failing_service = MagicMock()
    failing_service.navigate = AsyncMock(return_value={"success": False, "error": "browser crashed"})
    monkeypatch.setattr(
        "app.services.browser_service.get_browser_service",
        lambda: failing_service,
    )

    resp = client.post("/api/browser/navigate", json={"url": "https://example.com"})

    # The whole point: it is NOT a 2xx success.
    assert resp.status_code >= 400, f"expected non-2xx on failure, got {resp.status_code}: {resp.text}"
    # And specifically the upstream-dependency status for browser failures.
    assert resp.status_code == 502, f"expected 502 Bad Gateway, got {resp.status_code}"

    # Body content is preserved for backward compatibility.
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "browser crashed"


def test_browser_navigate_success_still_200(client, monkeypatch):
    """The happy path is untouched — success still returns 200 + success:true."""
    ok_service = MagicMock()
    ok_service.navigate = AsyncMock(
        return_value={
            "success": True,
            "url": "https://example.com",
            "title": "Example",
            "status": 200,
        }
    )
    monkeypatch.setattr(
        "app.services.browser_service.get_browser_service",
        lambda: ok_service,
    )

    resp = client.post("/api/browser/navigate", json={"url": "https://example.com"})

    assert resp.status_code == 200, f"expected 200 on success, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["success"] is True
    assert body["url"] == "https://example.com"
