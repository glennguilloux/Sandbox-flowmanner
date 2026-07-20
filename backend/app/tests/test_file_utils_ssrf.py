"""Regression tests for the SSRF guard on tool-layer outbound HTTP (B19).

These pin the contract that ``app.tools._file_utils.fetch_bytes`` — the shared
raw-HTTP primitive used by file/URL tool inputs — MUST reject loopback,
private, link-local, reserved, multicast and cloud-metadata destinations
before any connection is opened. Previously ``fetch_bytes`` opened
``httpx.AsyncClient`` with no guard, so a direct caller could be abused as an
internal-network oracle.

The same ``validate_url_ssrf`` guard is also exercised through the callers we
routed through it (expense_receipt_parser, meta_tag_generator, deep_web_crawler).
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from app.tools import _file_utils

# Addresses that must ALWAYS be rejected (default-deny SSRF surface).
UNSAFE_URLS = [
    "http://127.0.0.1/",
    "http://127.0.0.1:8080/v1",
    "http://localhost/",
    "http://0.0.0.0/",
    "http://[::1]/",
    "http://10.0.0.5/",  # RFC1918 private
    "http://192.168.1.1/",
    "http://172.16.5.5/",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "http://169.254.169.254/",  # link-local
    "file:///etc/passwd",  # non-http scheme
    "gopher://127.0.0.1:11211/",
    "ftp://127.0.0.1/",
    "data:text/plain,hello",
]


@pytest.mark.parametrize("url", UNSAFE_URLS)
def test_validate_url_ssrf_rejects_unsafe(url):
    """Every loopback/private/link-local/non-http URL is rejected."""
    assert _file_utils.validate_url_ssrf(url) is not None


def test_validate_url_ssrf_resolves_and_rejects_private_hostname():
    """A hostname that DNS-resolves to a private IP must be rejected.

    This defeats the DNS-rebinding / hostname-not-IP bypass: a public-looking
    host that points at 10.x must NOT slip through.
    """
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.9", 0))]):
        reason = _file_utils.validate_url_ssrf("http://innocent-looking.example.com/")
    assert reason is not None
    assert "non-public" in reason


def test_validate_url_ssrf_allows_global_hostname():
    """A hostname resolving to a public address is permitted."""
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
        assert _file_utils.validate_url_ssrf("https://example.com/") is None


@pytest.mark.asyncio
async def test_fetch_bytes_rejects_loopback():
    """fetch_bytes must refuse a loopback URL instead of connecting."""
    with pytest.raises(ValueError, match="unsafe URL"):
        await _file_utils.fetch_bytes("http://127.0.0.1:9/")


@pytest.mark.asyncio
async def test_fetch_bytes_rejects_metadata_endpoint():
    """The cloud-metadata endpoint must be blocked even over http."""
    with pytest.raises(ValueError, match="unsafe URL"):
        await _file_utils.fetch_bytes("http://169.254.169.254/latest/meta-data/")


@pytest.mark.asyncio
async def test_fetch_bytes_allows_global_url(monkeypatch):
    """A genuine public URL passes the guard and reaches the httpx call.

    We stub the network side so the test never touches the real internet, but
    the guard itself runs for real (DNS resolution of a public host).
    """
    captured = {}

    class _FakeResp:
        content = b"hello"

        def raise_for_status(self):
            return None

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            captured["url"] = url
            return _FakeResp()

    monkeypatch.setattr(_file_utils.httpx, "AsyncClient", _FakeClient)
    # Stub DNS so the guard resolves this host to a public address (no real net).
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 0))],
    )
    data = await _file_utils.fetch_bytes("https://public.example.com/file.bin")
    assert data == b"hello"
    assert captured["url"] == "https://public.example.com/file.bin"
