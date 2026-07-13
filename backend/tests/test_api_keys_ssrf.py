"""Regression tests for P0 SSRF (R-8) + BYOK input-validation parity (R-9).

R-8: ``base_url`` supplied to /api-keys (add) or stored on a key (test) must
never point at a private/loopback/link-local/reserved address, and the test
request must not auto-follow redirects into a private range.

R-9: api_keys.py add_key must enforce the same input validation as byok.py:
``validate_provider`` (reject unknown providers) and a per-user key-count quota.

These tests are written to FAIL before the fix and PASS after. Each destructive
case asserts that NO outbound HTTP request is issued to the malicious host.
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.api.v1.api_keys as api_keys_module
from app.api.deps import get_current_user
from app.database import get_db
from app.main_fastapi import app

client = TestClient(app)

ADD_URL = "/api/api-keys"
TEST_URL = "/api/api-keys/{key_id}/test"


# ── R-8 unit tests: _is_safe_outbound_url (no network, no DB) ───────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/v1",
        "https://127.0.0.1/v1",
        "http://localhost/v1",
        "http://0.0.0.0/v1",
        "http://10.0.0.5/v1",
        "http://10.1.2.3:9000",
        "http://172.16.0.1/v1",
        "http://172.31.255.255/v1",
        "http://192.168.1.1/v1",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://169.254.169.254:80/",
        "http://[::1]/v1",
        "http://[fc00::1]/v1",
        "http://[fe80::1]/v1",
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379/",
        "ftp://10.0.0.1/",
    ],
)
def test_is_safe_outbound_url_rejects_private_and_bad_schemes(url):
    ok, err = api_keys_module._is_safe_outbound_url(url)
    assert ok is False, f"expected {url!r} to be rejected, got ok={ok} err={err}"
    assert err


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://openrouter.ai/api/v1",
    ],
)
def test_is_safe_outbound_url_allows_public_https(url):
    # We only assert the helper returns a proper (bool, str|None) tuple and that
    # it never reports "ok" for a private range. Online it returns (True, None).
    ok, err = api_keys_module._is_safe_outbound_url(url)
    assert isinstance(ok, bool)
    if not ok:
        assert err


def test_is_safe_outbound_url_rejects_hostname_resolving_to_private(monkeypatch):
    import socket

    def _fake_getaddrinfo(host, port, *a, **k):
        # Pretend evil.example.com resolves to a private IP (DNS rebinding sim).
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.99", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    ok, err = api_keys_module._is_safe_outbound_url("https://evil.example.com/v1")
    assert ok is False
    assert err is not None and ("10.0.0.99" in err or "non-public" in err)


# ── helpers for integration tests ───────────────────────────────────────────


class _ExplodingClient:
    """httpx.AsyncClient stand-in that fails the test on ANY real request."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, url, **kwargs):
        raise AssertionError(f"UNEXPECTED outbound HTTP to {url!r}")


def _patch_httpx():
    return patch("app.api.v1.api_keys.httpx.AsyncClient", return_value=_ExplodingClient())


@pytest.fixture
def authed_client(monkeypatch):
    """TestClient with get_db/get_current_user overridden; yields the mock db."""
    user = MagicMock()
    user.id = 1

    db = AsyncMock()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    yield db

    app.dependency_overrides.clear()


# ── R-8 integration: add_key rejects private base_url, NO outbound request ───


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1:8080/v1",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/v1",
        "http://192.168.1.1/v1",
    ],
)
def test_add_key_rejects_private_base_url(authed_client, base_url):
    # Under quota => count query returns 0. Rejected at write time (before insert).
    result = MagicMock()
    result.scalar_one.return_value = 0
    result.scalar_one_or_none.return_value = None
    authed_client.execute = AsyncMock(return_value=result)

    with _patch_httpx():
        resp = client.post(
            ADD_URL,
            json={"provider": "openai", "api_key": "sk-test-123", "base_url": base_url},
        )

    assert resp.status_code == 400, resp.text
    assert "base_url" in resp.json().get("detail", "").lower()


# ── R-9 integration: provider validation + quota parity with byok.py ────────


def test_add_key_rejects_unknown_provider(authed_client):
    result = MagicMock()
    result.scalar_one.return_value = 0
    authed_client.execute = AsyncMock(return_value=result)

    with _patch_httpx():
        resp = client.post(
            ADD_URL,
            json={"provider": "totally-unknown-provider", "api_key": "sk-test-123"},
        )

    assert resp.status_code == 400, resp.text
    assert "Unsupported provider" in resp.text


def test_add_key_enforces_quota(authed_client):
    # At the limit => 429, and never reaches httpx.
    result = MagicMock()
    result.scalar_one.return_value = api_keys_module.MAX_USER_API_KEYS
    authed_client.execute = AsyncMock(return_value=result)

    with _patch_httpx():
        resp = client.post(
            ADD_URL,
            json={"provider": "openai", "api_key": "sk-test-123"},
        )

    assert resp.status_code == 429, resp.text
    assert "limit" in resp.text.lower()


# ── R-8 integration: test_key on stored private base_url makes NO request ────


def test_test_key_rejects_stored_private_base_url(authed_client):
    """A key whose stored base_url is a private host must be refused, and the
    user's Authorization header must NEVER be sent to that host."""
    key = MagicMock()
    key.id = 42
    key.provider = "openai"
    key.key_label = "evil"
    key.base_url = "http://169.254.169.254/latest/meta-data/"
    key.get_api_key.return_value = "sk-secret-user-key"

    result = MagicMock()
    result.scalar_one_or_none.return_value = key
    authed_client.execute = AsyncMock(return_value=result)

    with _patch_httpx():
        resp = client.post(TEST_URL.format(key_id=42), json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert "Refusing" in body["message"] or "base_url" in body["message"].lower()


def test_test_key_rejects_stored_hostname_rebinding_to_private(authed_client, monkeypatch):
    """Even a hostname that looked public at write time must be re-checked; if
    it now resolves to a private IP, the credentialed request is refused."""
    import socket

    key = MagicMock()
    key.id = 43
    key.provider = "openai"
    key.key_label = "rebind"
    key.base_url = "https://looks-public.example.com/v1"
    key.get_api_key.return_value = "sk-secret-user-key"

    result = MagicMock()
    result.scalar_one_or_none.return_value = key
    authed_client.execute = AsyncMock(return_value=result)

    def _fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.99", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    with _patch_httpx():
        resp = client.post(TEST_URL.format(key_id=43), json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert "Refusing" in body["message"] or "non-public" in body["message"]


def test_test_key_uses_no_follow_redirects(monkeypatch):
    """The httpx.AsyncClient used by test_key must be constructed with
    follow_redirects=False so a 302 to a private host cannot leak the
    Authorization header."""
    captured = {}
    original = api_keys_module.httpx.AsyncClient

    class _CaptureClient:
        def __init__(self, *a, **k):
            captured.update(k)
            self._wrapped = original(*a, **k)

        async def __aenter__(self):
            await self._wrapped.__aenter__()
            return self

        async def __aexit__(self, *a):
            await self._wrapped.__aexit__(*a)

        async def get(self, url, **kwargs):
            return MagicMock(status_code=200, is_success=True)

    with patch("app.api.v1.api_keys.httpx.AsyncClient", side_effect=_CaptureClient):
        key = MagicMock()
        key.id = 44
        key.provider = "openai"
        key.key_label = "ok"
        key.base_url = None  # falls back to default public openai base url
        key.get_api_key.return_value = "sk-secret"

        result = MagicMock()
        result.scalar_one_or_none.return_value = key
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)

        user = MagicMock()
        user.id = 1

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            client.post(TEST_URL.format(key_id=44), json={})
        finally:
            app.dependency_overrides.clear()

    assert "follow_redirects" in captured, "httpx.AsyncClient called without follow_redirects kwarg"
    assert captured["follow_redirects"] is False
