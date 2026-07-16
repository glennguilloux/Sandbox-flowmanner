"""
Shared file-handling utilities for FlowManner tool suite.

Provides base64 decoding, URL fetching, and input resolution helpers
used by all file-handling and data-processing tools.
"""

from __future__ import annotations

import base64
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


def validate_url_ssrf(url: str) -> str | None:
    """Validate a URL for safe outbound fetching (SSRF protection).

    Returns ``None`` if the URL is safe to fetch, otherwise a human-readable
    reason string describing why it was rejected.

    The check mirrors the substrate webhook SSRF guard (``node_executor._is_safe_url``):
      * only ``http`` / ``https`` schemes are allowed;
      * non-http schemes (``file``, ``ftp``, ``data``, ``gopher``, …) are rejected;
      * the host is resolved via DNS and *every* resolved address must be public —
        loopback, private (RFC1918), link-local, reserved, multicast and unspecified
        addresses are all refused. This defeats both literal-IP and DNS-rebinding
        style SSRF, since the connection still goes to one of the checked addresses.

    Do NOT weaken this to string-prefix matching: hostnames like ``10.0.0.1``
    resolve, and ``127.0.0.1`` / ``0.0.0.0`` / ``::1`` are caught by the
    ``is_loopback`` / ``is_unspecified`` checks below.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:  # pragma: no cover - urlparse is very defensive
        return f"could not parse URL: {e}"

    if parsed.scheme.lower() not in ("http", "https"):
        return f"URL scheme '{parsed.scheme}://' is not allowed; only http/https may be fetched"

    host = (parsed.hostname or "").lower()
    if not host:
        return "URL has no valid hostname"

    candidates: list[str] = []
    # IPv4 literal (all digits/dots) or IPv6 literal (contains ':').
    if host.replace(".", "").isdigit() or ":" in host:
        candidates.append(host)
    else:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return f"cannot resolve host: {host}"
        except Exception as e:  # pragma: no cover - defensive
            return f"DNS lookup failed for {host}: {e}"
        candidates = [str(info[4][0]) for info in infos]

    for addr in candidates:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            # Unparsable resolved address — treat as unsafe.
            return f"host '{host}' resolved to an invalid address: {addr}"
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return f"host '{host}' resolves to a non-public address ({ip})"
    return None


def decode_data(data: str) -> bytes:
    """Decode a base64-encoded string to bytes.

    Strips data-URI prefixes (e.g. ``data:application/pdf;base64,...``)
    before decoding.
    """
    if "," in data and data.startswith("data:"):
        data = data.split(",", 1)[1]
    try:
        return base64.b64decode(data)
    except Exception as e:
        raise ValueError(f"Invalid base64 data (first 50 chars: {data[:50]!r}): {e}") from e


async def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    """Fetch raw bytes from a URL via HTTP GET."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def resolve_input(
    data: str | None,
    url: str | None,
    *,
    label: str = "file",
    fetch_timeout: int = 30,
) -> bytes:
    """Resolve tool input from either base64 *data* or a *url*.

    Raises ``ValueError`` if neither is provided.

    SSRF guard: when fetching a URL, resolve the host and refuse loopback,
    private, link-local, or cloud-metadata addresses so the tool layer cannot
    be used as an internal-network oracle.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    if data:
        return decode_data(data)
    if not url:
        raise ValueError(f"No {label} provided (need 'data' or 'url')")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "::", "169.254.169.254"):
        raise ValueError(f"Refusing to fetch loopback/link-local/metadata host: {host}")
    try:
        for info in socket.getaddrinfo(host, None):
            if ipaddress.ip_address(info[4][0]).is_private:
                raise ValueError(f"Refusing to fetch private/non-public host: {host}")
    except socket.gaierror:
        raise ValueError(f"Cannot resolve host: {host}")

    return await fetch_bytes(url, timeout=fetch_timeout)
