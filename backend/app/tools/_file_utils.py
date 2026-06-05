"""
Shared file-handling utilities for FlowManner tool suite.

Provides base64 decoding, URL fetching, and input resolution helpers
used by all file-handling and data-processing tools.
"""

from __future__ import annotations

import base64
import logging

import httpx

logger = logging.getLogger(__name__)


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
        raise ValueError(
            f"Invalid base64 data (first 50 chars: {data[:50]!r}): {e}"
        ) from e


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
    """
    if data:
        return decode_data(data)
    if url:
        return await fetch_bytes(url, timeout=fetch_timeout)
    raise ValueError(f"Either 'data' (base64) or 'url' must be provided for {label}")
