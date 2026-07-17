"""Tests for integration webhook → durable external_events bus wiring.

Verifies that ``handle_provider_webhook`` now routes inbound webhook events
to the durable ``EventBus.publish`` (SELF-AUDIT-MED-09) instead of only
log-and-ack.  Covers:

- The route calls ``EventBus.publish`` with the correct source / event_type /
  payload / delivery_id (idempotency key) before acknowledging.
- The route still returns the unchanged ``{"status": "ok", ...}`` contract.
- The ack is NOT sent when the bus write fails (at-least-once delivery:
  the provider must retry).
- Signature-verification failures still return 401 and do NOT publish.
- Unknown providers still 404 and do NOT publish.

DB is mocked (no live Postgres required) — only the wiring is under test.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import integration_webhooks
from app.config import settings
from app.main_fastapi import app

# ── Fake event bus ──────────────────────────────────────────────────────────


class FakeEventBus:
    """Records publish() calls; stores the last call args for assertions."""

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        self._raise = False

    async def publish(self, db, *, source, event_type, payload=None, raw_body=None, delivery_id=None, user_id=None):
        # Mirror production: return an object with an ``id`` so the route's
        # post-commit enqueue (enqueue_event_processing(str(event.id))) works.
        from types import SimpleNamespace
        from uuid import uuid4

        event = SimpleNamespace(id=uuid4())
        self.published.append(
            {
                "source": source,
                "event_type": event_type,
                "payload": payload,
                "raw_body": raw_body,
                "delivery_id": delivery_id,
                "user_id": user_id,
                "id": event.id,
            }
        )
        if self._raise:
            raise RuntimeError("bus write failed")
        return event


@pytest.fixture
def fake_bus(monkeypatch):
    """Install a FakeEventBus as the EventBus singleton and reset it after."""
    bus = FakeEventBus()
    monkeypatch.setattr(integration_webhooks, "get_event_bus", lambda: bus)

    # Ensure reset_event_bus is called so the real singleton is restored
    from app.services.event_bus import reset_event_bus

    reset_event_bus()
    yield bus
    reset_event_bus()
    return bus


@pytest.fixture
def fake_db(monkeypatch):
    """Override get_db to yield a MagicMock session (no real DB)."""
    fake_session = MagicMock()

    async def _override():
        yield fake_session

    app.dependency_overrides[integration_webhooks.get_db] = _override
    yield fake_session
    app.dependency_overrides.pop(integration_webhooks.get_db, None)


@pytest.fixture
def client():
    """A TestClient with auth disabled (webhook route needs no user)."""
    return TestClient(app)


# ── Tests ────────────────────────────────────────────────────────────────────


def test_github_webhook_routes_to_bus(client, fake_bus, fake_db):
    """A verified GitHub push webhook publishes to the durable bus before ack."""
    # Disable signature verification so the request passes (no secret configured)
    monkeypatch_secret(client, "GITHUB_WEBHOOK_SECRET", "")
    body = {"ref": "refs/heads/main", "repository": {"full_name": "acme/widgets"}}
    headers = {
        "x-github-event": "push",
        "x-github-delivery": "deliv-123",
        "content-type": "application/json",
    }
    resp = client.post("/api/github/webhook", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok", "provider": "github", "event_type": "push"}

    assert len(fake_bus.published) == 1
    call = fake_bus.published[0]
    assert call["source"] == "github"
    assert call["event_type"] == "push"
    assert call["delivery_id"] == "deliv-123"
    assert call["payload"] == body


def test_bus_failure_suppresses_ack(client, fake_bus, fake_db):
    """If the durable bus write fails, the webhook is NOT acknowledged.

    The route re-raises, so TestClient surfaces the server exception
    (no 200/JSON ack is returned).  The provider will retry — preserving
    at-least-once delivery.
    """
    fake_bus._raise = True
    monkeypatch_secret(client, "GITHUB_WEBHOOK_SECRET", "")
    body = {"ref": "refs/heads/main"}
    headers = {
        "x-github-event": "push",
        "x-github-delivery": "deliv-fail",
        "content-type": "application/json",
    }
    from starlette.testclient import TestClient as _TC

    # raise_server_exceptions=True surfaces the unhandled error instead of
    # returning a response — proves no ack was produced.
    tc = _TC(app, raise_server_exceptions=True)
    with pytest.raises(RuntimeError):
        tc.post("/api/github/webhook", json=body, headers=headers)
    assert len(fake_bus.published) == 1


def test_bad_signature_does_not_publish(client, fake_bus, fake_db):
    """A signature-verification failure returns 401 and never publishes."""
    monkeypatch_secret(client, "GITHUB_WEBHOOK_SECRET", "correct-secret")
    body = {"ref": "refs/heads/main"}
    headers = {
        "x-github-event": "push",
        "x-github-delivery": "deliv-bad",
        "x-hub-signature-256": "sha256=deadbeef",  # wrong sig
        "content-type": "application/json",
    }
    resp = client.post("/api/github/webhook", json=body, headers=headers)
    assert resp.status_code == 401
    assert len(fake_bus.published) == 0


def test_unknown_provider_does_not_publish(client, fake_bus, fake_db):
    """An unknown provider 404s and does not publish to the bus."""
    resp = client.post("/api/notarealprovider/webhook", json={})
    assert resp.status_code == 404
    assert len(fake_bus.published) == 0


def test_monday_challenge_short_circuits_bus(client, fake_bus, fake_db):
    """Monday challenge-response returns the challenge without publishing."""
    monkeypatch_secret(client, "MONDAY_WEBHOOK_SECRET", "")
    resp = client.post("/api/monday/webhook", json={"challenge": "abc123"})
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "abc123"}
    assert len(fake_bus.published) == 0


# ── Helpers ────────────────────────────────────────────────────────────────


def monkeypatch_secret(client, name: str, value: str) -> None:
    """Temporarily set a provider secret on settings (verification disabled if '')."""
    # settings is read via getattr in verify_webhook; patch the attribute.
    setattr(settings, name, value)
