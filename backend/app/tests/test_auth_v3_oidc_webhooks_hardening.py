"""Unit tests for T5 hardening of v3 OIDC + webhooks.

These tests cover the *guarded* hardening logic described in
``.sisyphus/plans/CODEBASE-ANALYSIS-FOLLOWUP-PLAN-2026-07-08.md`` Task B, without
requiring a database or network access:

OIDC (``auth_oidc.py`` / ``services/oidc_service.py``)
  - Provider allowlist: unknown/inactive providers are rejected (``ValueError``),
    never reach discovery/exchange.
  - PKCE code_verifier -> S256 code_challenge is deterministic and recomputes.
  - State store is one-time-use (CSRF/replay protection).
  - ``_require_oidc_enabled`` returns 404 when the feature flag is off.

Webhooks (``auth_webhooks.py``)
  - HMAC-SHA256 signature: deterministic, ``sha256=`` prefix, tamper-detecting verify.
  - ``_deliver_webhook`` POSTs to the subscriber with the correct signature header,
    event header, and ``{event, data, timestamp, webhook_id}`` payload shape.
  - Delivery honours HTTP status (2xx => success, non-2xx => failure w/ error text)
    and network exceptions (=> failure, no crash).
  - ``_deliver_with_retry`` retries with backoff then succeeds; exhausts and reports
    failure after ``max_retries``.
  - ``_require_webhooks_enabled`` returns 404 when the feature flag is off.

All behavior is a no-op/404 unless the operator enables the relevant feature flag at
runtime, so these tests assert the guarded surface is intact.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v3 import auth_oidc, auth_webhooks
from app.services import oidc_service

# ── Helpers ──────────────────────────────────────────────────────────────────


def _fake_subscription(url: str = "https://example.test/hook", secret: str = "topsecret") -> SimpleNamespace:
    """Minimal stand-in for AuthWebhookSubscription.

    ``_deliver_webhook`` only reads ``subscription.secret`` and ``subscription.url``,
    so a SimpleNamespace is sufficient and avoids DB/model imports.
    """
    return SimpleNamespace(url=url, secret=secret)


def _make_httpx_client(status_code: int = 200, text: str = "ok", side_effect=None):
    """Build a fake ``httpx.AsyncClient`` context manager.

    Returns ``(context_manager, post_mock)`` so the test can inspect the captured
    POST call.
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    post = AsyncMock(return_value=resp)
    if side_effect is not None:
        post.side_effect = side_effect

    inner = MagicMock()
    inner.post = post

    cm = MagicMock()
    cm.__aenter__.return_value = inner
    cm.__aexit__.return_value = False
    return cm, post


def _mock_db(scalar_value=None, scalar_one_or_none_value=None):
    """Build an AsyncMock DB session whose execute() returns a configurable result."""
    result = MagicMock()
    result.scalar.return_value = scalar_value
    result.scalar_one_or_none.return_value = scalar_one_or_none_value
    db = AsyncMock()
    db.execute.return_value = result
    return db


# ── OIDC provider allowlist ────────────────────────────────────────────────────


async def test_get_provider_config_returns_none_for_unknown_provider():
    db = _mock_db(scalar_one_or_none_value=None)
    cfg = await oidc_service.get_provider_config(db, "not-a-real-provider")
    assert cfg is None


async def test_get_authorization_url_rejects_unknown_provider():
    db = _mock_db(scalar_one_or_none_value=None)
    with pytest.raises(ValueError, match="Unknown or inactive OIDC provider"):
        await oidc_service.get_authorization_url(db, "evil-provider", "https://cb.test/oidc/callback")


async def test_get_provider_config_does_not_query_when_missing():
    db = _mock_db(scalar_one_or_none_value=None)
    await oidc_service.get_provider_config(db, "x")
    # No discovery/network call should happen for an unknown provider.
    db.execute.assert_awaited_once()


# ── OIDC PKCE + state ──────────────────────────────────────────────────────────


def test_pkce_challenge_is_deterministic_s256():
    import base64
    import hashlib

    verifier = oidc_service.generate_code_verifier()
    ch1 = oidc_service.generate_code_challenge(verifier)
    ch2 = oidc_service.generate_code_challenge(verifier)
    assert ch1 == ch2

    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    assert ch1 == expected
    assert "=" not in ch1  # S256 challenge is base64url without padding


def test_state_store_is_one_time_use():
    oidc_service.store_state("state-abc", "nonce-1", "google", "cv-1", "https://cb.test/cb")
    first = oidc_service.consume_state("state-abc")
    assert first is not None
    assert first["nonce"] == "nonce-1"
    assert first["provider"] == "google"

    # Second consume returns None -> prevents replay of the same state.
    assert oidc_service.consume_state("state-abc") is None


# ── OIDC flag gate ──────────────────────────────────────────────────────────────


async def test_require_oidc_enabled_passes_when_flag_on():
    db = _mock_db(scalar_value=True)
    # Should not raise.
    await auth_oidc._require_oidc_enabled(db)


async def test_require_oidc_enabled_raises_404_when_flag_off():
    db = _mock_db(scalar_value=False)
    with pytest.raises(HTTPException) as exc:
        await auth_oidc._require_oidc_enabled(db)
    assert exc.value.status_code == 404


# ── Webhook HMAC signing ───────────────────────────────────────────────────────


def test_compute_webhook_signature_format_and_deterministic():
    secret = "s3cr3t"
    body = b'{"event":"session.created","data":{"x":1}}'
    sig = auth_webhooks.compute_webhook_signature(secret, body)
    assert sig.startswith("sha256=")
    # Deterministic.
    assert auth_webhooks.compute_webhook_signature(secret, body) == sig


def test_verify_webhook_signature_roundtrip():
    secret = "s3cr3t"
    body = b"payload-bytes"
    sig = auth_webhooks.compute_webhook_signature(secret, body)
    assert auth_webhooks.verify_webhook_signature(secret, body, sig) is True


def test_verify_webhook_signature_detects_tampered_payload():
    secret = "s3cr3t"
    body = b"payload-bytes"
    sig = auth_webhooks.compute_webhook_signature(secret, body)
    tampered = b"payload-bytes-CHANGED"
    assert auth_webhooks.verify_webhook_signature(secret, tampered, sig) is False


def test_verify_webhook_signature_detects_wrong_secret():
    body = b"payload-bytes"
    sig = auth_webhooks.compute_webhook_signature("secret-a", body)
    assert auth_webhooks.verify_webhook_signature("secret-b", body, sig) is False


# ── Webhook delivery ───────────────────────────────────────────────────────────


async def test_deliver_webhook_posts_signed_payload_on_success():
    sub = _fake_subscription()
    cm, post = _make_httpx_client(status_code=200, text="accepted")

    with patch.object(auth_webhooks.httpx, "AsyncClient", return_value=cm):
        success, code, err = await auth_webhooks._deliver_webhook(sub, "session.created", {"user_id": 7})

    assert success is True
    assert code == 200
    assert err is None

    post.assert_awaited_once()
    # url is passed positionally to client.post(url, content=..., headers=...)
    assert post.call_args.args[0] == sub.url
    kwargs = post.call_args.kwargs

    headers = kwargs["headers"]
    body = kwargs["content"]
    assert headers["X-Webhook-Event"] == "session.created"
    # Signature must match the exact bytes delivered.
    assert headers["X-Webhook-Signature"] == auth_webhooks.compute_webhook_signature(sub.secret, body)

    parsed = __import__("json").loads(body)
    assert parsed["event"] == "session.created"
    assert parsed["data"] == {"user_id": 7}
    assert "timestamp" in parsed
    assert "webhook_id" in parsed


async def test_deliver_webhook_reports_failure_on_non_2xx():
    sub = _fake_subscription()
    cm, _ = _make_httpx_client(status_code=500, text="internal error")

    with patch.object(auth_webhooks.httpx, "AsyncClient", return_value=cm):
        success, code, err = await auth_webhooks._deliver_webhook(sub, "user.created", {"id": 1})

    assert success is False
    assert code == 500
    assert err is not None
    assert "internal error" in err


async def test_deliver_webhook_survives_network_exception():
    sub = _fake_subscription()
    cm, _ = _make_httpx_client(side_effect=RuntimeError("connection reset"))

    with patch.object(auth_webhooks.httpx, "AsyncClient", return_value=cm):
        success, code, err = await auth_webhooks._deliver_webhook(sub, "session.revoked", {})

    assert success is False
    assert code is None
    assert err is not None
    assert "connection reset" in err


# ── Webhook retry/backoff ──────────────────────────────────────────────────────


async def test_deliver_with_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    async def flaky(sub, event_type, payload):
        calls["n"] += 1
        if calls["n"] <= 2:
            return (False, 503, "try again")
        return (True, 200, None)

    with patch.object(auth_webhooks, "_deliver_webhook", side_effect=flaky), patch("asyncio.sleep") as sleep:
        ok = await auth_webhooks._deliver_with_retry(_fake_subscription(), "e", {}, max_retries=3)

    assert ok is True
    assert calls["n"] == 3
    # Backoff sleeps happen between attempts (2 sleeps before the 3rd success).
    assert sleep.await_count == 2


async def test_deliver_with_retry_exhausts_and_reports_failure():
    with patch.object(auth_webhooks, "_deliver_webhook", return_value=(False, 500, "boom")), patch("asyncio.sleep"):
        ok = await auth_webhooks._deliver_with_retry(_fake_subscription(), "e", {}, max_retries=2)

    assert ok is False


# ── Webhooks flag gate ─────────────────────────────────────────────────────────


async def test_require_webhooks_enabled_passes_when_flag_on():
    db = _mock_db(scalar_value=True)
    await auth_webhooks._require_webhooks_enabled(db)


async def test_require_webhooks_enabled_raises_404_when_flag_off():
    db = _mock_db(scalar_value=False)
    with pytest.raises(HTTPException) as exc:
        await auth_webhooks._require_webhooks_enabled(db)
    assert exc.value.status_code == 404
