"""Unit tests for Auth v3 webhook routes.

Tests HMAC-SHA256 signing, webhook CRUD, delivery with retry,
delivery logs, and the auth event emission helper.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.api.v3.auth_webhooks import (
    CreateWebhookBody,
    _deliver_webhook,
    _deliver_with_retry,
    compute_webhook_signature,
    emit_auth_webhook_event,
    verify_webhook_signature,
)
from app.models.auth_v3_models import AuthWebhookSubscription

# ── HMAC Signing ─────────────────────────────────────────────────────────────


class TestHMACSigning:
    """compute_webhook_signature / verify_webhook_signature."""

    def test_compute_signature_format(self):
        """Signature starts with 'sha256=' and is hex."""
        sig = compute_webhook_signature("my-secret", b'{"test": true}')
        assert sig.startswith("sha256=")
        hex_part = sig[7:]
        assert len(hex_part) == 64  # SHA-256 = 64 hex chars
        # Verify it's valid hex
        int(hex_part, 16)

    def test_compute_signature_deterministic(self):
        """Same inputs produce same signature."""
        sig1 = compute_webhook_signature("secret", b"payload")
        sig2 = compute_webhook_signature("secret", b"payload")
        assert sig1 == sig2

    def test_compute_signature_different_secrets(self):
        """Different secrets produce different signatures."""
        sig1 = compute_webhook_signature("secret1", b"payload")
        sig2 = compute_webhook_signature("secret2", b"payload")
        assert sig1 != sig2

    def test_compute_signature_different_payloads(self):
        """Different payloads produce different signatures."""
        sig1 = compute_webhook_signature("secret", b"payload1")
        sig2 = compute_webhook_signature("secret", b"payload2")
        assert sig1 != sig2

    def test_verify_signature_valid(self):
        """Valid signature verifies correctly."""
        secret = "test-secret-123"
        payload = b'{"event": "session.created"}'
        sig = compute_webhook_signature(secret, payload)
        assert verify_webhook_signature(secret, payload, sig) is True

    def test_verify_signature_invalid(self):
        """Tampered signature fails verification."""
        secret = "test-secret-123"
        payload = b'{"event": "session.created"}'
        assert verify_webhook_signature(secret, payload, "sha256=deadbeef") is False

    def test_verify_signature_wrong_secret(self):
        """Wrong secret fails verification."""
        payload = b"payload"
        sig = compute_webhook_signature("correct-secret", payload)
        assert verify_webhook_signature("wrong-secret", payload, sig) is False

    def test_signature_matches_manual_hmac(self):
        """Signature matches manual HMAC-SHA256 computation."""
        secret = "my-key"
        payload = b"hello world"
        sig = compute_webhook_signature(secret, payload)
        expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        assert sig == expected


# ── Pydantic Schemas ─────────────────────────────────────────────────────────


class TestWebhookSchemas:
    """CreateWebhookBody validation."""

    def test_valid_body(self):
        body = CreateWebhookBody(
            url="https://example.com/webhook",
            events=["session.created", "session.revoked"],
            workspace_id="ws-123",
        )
        assert body.url == "https://example.com/webhook"
        assert len(body.events) == 2

    def test_empty_events_rejected(self):
        with pytest.raises(ValidationError):
            CreateWebhookBody(
                url="https://example.com/webhook",
                events=[],
                workspace_id="ws-123",
            )

    def test_url_max_length(self):
        with pytest.raises(ValidationError):
            CreateWebhookBody(
                url="x" * 2001,
                events=["test"],
                workspace_id="ws-123",
            )


# ── Webhook Model ────────────────────────────────────────────────────────────


class TestWebhookModel:
    """AuthWebhookSubscription model helpers."""

    def test_generate_secret_length(self):
        secret = AuthWebhookSubscription.generate_secret()
        assert len(secret) == 64

    def test_generate_secret_unique(self):
        secrets = {AuthWebhookSubscription.generate_secret() for _ in range(50)}
        assert len(secrets) == 50


# ── Feature flag gating ─────────────────────────────────────────────────────


class TestWebhookFeatureFlag:
    """Feature flag gating returns 404 when disabled."""

    def test_flag_off_create_returns_404(self, v3_client, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = v3_client.post(
            "/api/v3/auth/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["session.created"],
                "workspace_id": "ws-123",
            },
        )
        assert resp.status_code == 404

    def test_flag_off_list_returns_404(self, v3_client, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = v3_client.get("/api/v3/auth/webhooks?workspace_id=ws-123")
        assert resp.status_code == 404

    def test_flag_off_delete_returns_404(self, v3_client, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = v3_client.delete("/api/v3/auth/webhooks/wh-123")
        assert resp.status_code == 404


# ── POST /auth/webhooks ──────────────────────────────────────────────────────


class TestCreateWebhook:
    """Create webhook subscription."""

    def test_create_returns_secret(self, v3_client, mock_db_session):
        """Secret is returned ONCE on creation."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True
        mock_db_session.execute = AsyncMock(return_value=flag_result)

        resp = v3_client.post(
            "/api/v3/auth/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["session.created"],
                "workspace_id": "ws-123",
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "secret" in data
        assert len(data["secret"]) == 64
        assert data["url"] == "https://example.com/hook"
        assert data["events"] == ["session.created"]
        assert data["is_active"] is True
        assert "id" in data

    def test_create_persists_webhook(self, v3_client, mock_db_session):
        """Webhook is added to the DB session."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True
        mock_db_session.execute = AsyncMock(return_value=flag_result)

        v3_client.post(
            "/api/v3/auth/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["session.created"],
                "workspace_id": "ws-123",
            },
        )
        mock_db_session.add.assert_called_once()
        added = mock_db_session.add.call_args[0][0]
        assert isinstance(added, AuthWebhookSubscription)
        assert added.url == "https://example.com/hook"
        assert added.workspace_id == "ws-123"


# ── GET /auth/webhooks ───────────────────────────────────────────────────────


class TestListWebhooks:
    """List webhook subscriptions."""

    def test_list_returns_webhooks(self, v3_client, mock_db_session):
        """Returns webhooks for the workspace."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        webhook = MagicMock()
        webhook.id = "wh-1"
        webhook.workspace_id = "ws-123"
        webhook.url = "https://example.com/hook"
        webhook.events = json.dumps(["session.created"])
        webhook.is_active = True
        webhook.created_at = datetime.now(UTC)
        webhook.last_delivery_at = None
        webhook.failure_count = 0

        webhook_result = MagicMock()
        webhook_result.scalars.return_value.all.return_value = [webhook]

        mock_db_session.execute = AsyncMock(side_effect=[flag_result, webhook_result])

        resp = v3_client.get("/api/v3/auth/webhooks?workspace_id=ws-123")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == "wh-1"
        assert data[0]["events"] == ["session.created"]

    def test_list_empty(self, v3_client, mock_db_session):
        """Returns empty list when no webhooks."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        webhook_result = MagicMock()
        webhook_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[flag_result, webhook_result])

        resp = v3_client.get("/api/v3/auth/webhooks?workspace_id=ws-123")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ── DELETE /auth/webhooks/{id} ───────────────────────────────────────────────


class TestDeleteWebhook:
    """Delete webhook subscription."""

    def test_delete_existing(self, v3_client, mock_db_session):
        """Deleting existing webhook returns 204."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        webhook = MagicMock()
        webhook.id = "wh-1"
        webhook_result = MagicMock()
        webhook_result.scalar_one_or_none.return_value = webhook

        mock_db_session.execute = AsyncMock(side_effect=[flag_result, webhook_result])

        resp = v3_client.delete("/api/v3/auth/webhooks/wh-1")
        assert resp.status_code == 204
        mock_db_session.delete.assert_called_once_with(webhook)

    def test_delete_nonexistent_returns_404(self, v3_client, mock_db_session):
        """Deleting nonexistent webhook returns 404."""
        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        webhook_result = MagicMock()
        webhook_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[flag_result, webhook_result])

        resp = v3_client.delete("/api/v3/auth/webhooks/nonexistent")
        assert resp.status_code == 404


# ── Webhook Delivery ─────────────────────────────────────────────────────────


class TestWebhookDelivery:
    """_deliver_webhook: HTTP delivery with HMAC signing."""

    @pytest.mark.asyncio
    async def test_deliver_success(self):
        """Successful delivery returns (True, 200, None)."""
        sub = MagicMock()
        sub.url = "https://example.com/hook"
        sub.secret = "test-secret"

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("app.api.v3.auth_webhooks.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
            mock_client.return_value.__aexit__.return_value = False

            success, status_code, error = await _deliver_webhook(sub, "session.created", {"user_id": 1})

        assert success is True
        assert status_code == 200
        assert error is None

    @pytest.mark.asyncio
    async def test_deliver_failure_returns_error(self):
        """Failed delivery returns (False, status_code, error)."""
        sub = MagicMock()
        sub.url = "https://example.com/hook"
        sub.secret = "test-secret"

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("app.api.v3.auth_webhooks.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
            mock_client.return_value.__aexit__.return_value = False

            success, status_code, error = await _deliver_webhook(sub, "session.created", {"user_id": 1})

        assert success is False
        assert status_code == 500
        assert error is not None

    @pytest.mark.asyncio
    async def test_deliver_network_error(self):
        """Network error returns (False, None, error_msg)."""
        sub = MagicMock()
        sub.url = "https://unreachable.example.com/hook"
        sub.secret = "test-secret"

        with patch("app.api.v3.auth_webhooks.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            mock_client.return_value.__aexit__.return_value = False

            success, status_code, error = await _deliver_webhook(sub, "session.created", {"user_id": 1})

        assert success is False
        assert status_code is None
        assert "Connection refused" in error

    @pytest.mark.asyncio
    async def test_deliver_signs_payload(self):
        """Delivery includes HMAC signature in headers."""
        sub = MagicMock()
        sub.url = "https://example.com/hook"
        sub.secret = "my-secret-key"

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        captured_kwargs = {}

        async def capture_post(url, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_resp

        with patch("app.api.v3.auth_webhooks.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=capture_post)
            mock_client.return_value.__aexit__.return_value = False

            await _deliver_webhook(sub, "session.created", {"user_id": 1})

        headers = captured_kwargs.get("headers", {})
        assert "X-Webhook-Signature" in headers
        assert headers["X-Webhook-Signature"].startswith("sha256=")
        assert headers["X-Webhook-Event"] == "session.created"
        assert headers["User-Agent"] == "Flowmanner-Webhook/1.0"


# ── Deliver with Retry ───────────────────────────────────────────────────────


class TestDeliverWithRetry:
    """_deliver_with_retry: exponential backoff retries."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self):
        """No retries when first attempt succeeds."""
        sub = MagicMock()
        sub.url = "https://example.com/hook"
        sub.secret = "test-secret"

        with patch(
            "app.api.v3.auth_webhooks._deliver_webhook",
            new_callable=AsyncMock,
        ) as mock_deliver:
            mock_deliver.return_value = (True, 200, None)

            result = await _deliver_with_retry(sub, "session.created", {})

        assert result is True
        assert mock_deliver.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        """Retries up to max_retries on failure."""
        sub = MagicMock()
        sub.url = "https://example.com/hook"
        sub.secret = "test-secret"

        call_count = 0

        async def fail_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return (False, 500, "Server error")
            return (True, 200, None)

        with (
            patch(
                "app.api.v3.auth_webhooks._deliver_webhook",
                new_callable=AsyncMock,
                side_effect=fail_then_succeed,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await _deliver_with_retry(sub, "session.created", {})

        assert result is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_returns_false_after_max_retries(self):
        """Returns False when all retries exhausted."""
        sub = MagicMock()
        sub.url = "https://example.com/hook"
        sub.secret = "test-secret"

        with (
            patch(
                "app.api.v3.auth_webhooks._deliver_webhook",
                new_callable=AsyncMock,
                return_value=(False, 500, "Server error"),
            ) as mock_deliver,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await _deliver_with_retry(sub, "session.created", {})

        assert result is False
        # max_retries=3 means 4 total attempts (initial + 3 retries)
        assert mock_deliver.call_count == 4


# ── Emit Auth Webhook Event ──────────────────────────────────────────────────


class TestEmitAuthWebhookEvent:
    """emit_auth_webhook_event: dispatches to matching subscriptions."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_subscriptions(self):
        """Returns 0 when no active subscriptions for workspace."""
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        count = await emit_auth_webhook_event(db, "ws-123", "session.created", {})
        assert count == 0

    @pytest.mark.asyncio
    async def test_delivers_to_matching_subscriptions(self):
        """Delivers event to subscriptions that match the event type."""
        db = AsyncMock()

        sub = MagicMock()
        sub.id = "wh-1"
        sub.url = "https://example.com/hook"
        sub.secret = "test-secret"
        sub.events = json.dumps(["session.created", "session.revoked"])
        sub.is_active = True
        sub.failure_count = 0
        sub.last_delivery_at = None

        result = MagicMock()
        result.scalars.return_value.all.return_value = [sub]
        db.execute = AsyncMock(return_value=result)

        with patch(
            "app.api.v3.auth_webhooks._deliver_with_retry",
            new_callable=AsyncMock,
            return_value=True,
        ):
            count = await emit_auth_webhook_event(db, "ws-123", "session.created", {"user_id": 1})

        assert count == 1
        assert sub.last_delivery_at is not None

    @pytest.mark.asyncio
    async def test_skips_non_matching_events(self):
        """Skips subscriptions that don't subscribe to the event type."""
        db = AsyncMock()

        sub = MagicMock()
        sub.id = "wh-1"
        sub.events = json.dumps(["session.revoked"])  # doesn't match
        sub.is_active = True

        result = MagicMock()
        result.scalars.return_value.all.return_value = [sub]
        db.execute = AsyncMock(return_value=result)

        count = await emit_auth_webhook_event(db, "ws-123", "session.created", {"user_id": 1})
        assert count == 0

    @pytest.mark.asyncio
    async def test_increments_failure_count_on_failure(self):
        """Increments failure_count when delivery fails."""
        db = AsyncMock()

        sub = MagicMock()
        sub.id = "wh-1"
        sub.url = "https://example.com/hook"
        sub.secret = "test-secret"
        sub.events = json.dumps(["session.created"])
        sub.is_active = True
        sub.failure_count = 0
        sub.last_delivery_at = None

        result = MagicMock()
        result.scalars.return_value.all.return_value = [sub]
        db.execute = AsyncMock(return_value=result)

        with patch(
            "app.api.v3.auth_webhooks._deliver_with_retry",
            new_callable=AsyncMock,
            return_value=False,
        ):
            count = await emit_auth_webhook_event(db, "ws-123", "session.created", {"user_id": 1})

        assert count == 1
        assert sub.failure_count == 1
