"""Regression tests for the shared SSRF URL guard (R-ssrf-guard).

Covers ``app.tools._file_utils.validate_url_ssrf`` and its use in
``smart_web_scraper``. The guard must refuse loopback, RFC1918 private ranges,
link-local, reserved, multicast and unspecified addresses, and non-http(s)
schemes — without weakening behaviour already present in sibling tools.

These tests issue NO real outbound HTTP request to internal hosts. The scraper
fetch is mocked; we only assert the guard short-circuits before the fetch.
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from unittest.mock import AsyncMock, patch

import pytest

from app.tools._file_utils import validate_url_ssrf
from app.tools.smart_web_scraper import SmartWebScraperTool

# URLs that MUST be refused (guard returns a reason string, not None).
_BLOCKED = [
    "http://127.0.0.1/",
    "http://127.0.0.1:8080/admin",
    "https://localhost/secret",
    "http://0.0.0.0/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://172.16.0.1/",
    "http://172.31.255.255/",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "ftp://10.0.0.1/file",
    "file:///etc/passwd",
    "gopher://127.0.0.1:11211/",
    "data:text/html,<script>alert(1)</script>",
]

# URLs that MUST be allowed (guard returns None).
_ALLOWED = [
    "https://example.com/",
    "http://example.com/article/123",
    "https://news.bbc.co.uk/sport",
]


@pytest.mark.parametrize("url", _BLOCKED)
def test_validate_url_ssrf_blocks_internal(url):
    assert validate_url_ssrf(url) is not None, f"expected {url!r} to be blocked"


@pytest.mark.parametrize("url", _ALLOWED)
def test_validate_url_ssrf_allows_public(url):
    assert validate_url_ssrf(url) is None, f"expected {url!r} to be allowed"


@pytest.mark.parametrize(
    "url",
    [
        "http://[::1]/",  # IPv6 loopback
        "https://[::ffff:127.0.0.1]/",  # IPv4-mapped loopback
    ],
)
def test_validate_url_ssrf_blocks_ipv6_loopback(url):
    assert validate_url_ssrf(url) is not None, f"expected {url!r} to be blocked"


async def test_smart_web_scraper_blocks_internal_before_fetch():
    """The scraper must refuse an internal URL and never perform the HTTP fetch."""
    tool = SmartWebScraperTool()
    with patch("app.tools.smart_web_scraper.httpx.AsyncClient") as client_cls:
        result = await tool.execute({"url": "http://127.0.0.1/"})
        client_cls.assert_not_called()
    assert result.success is False
    assert "SSRF" in result.error
