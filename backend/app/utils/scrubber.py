"""Centralized sensitive-data scrubbing for logs and OTel spans.

BYOK API keys must never appear in plaintext in structlog output or in OTel
span attributes (Jaeger). Every key/secret that reaches a log line or a span
attribute is scrubbed by the helpers here.

This module is the single source of truth for the scrubber. The Sentry/MCP
path's existing ``_scrub_sensitive_data`` (in
``app/services/mcp/sentry_mcp_instrumentation.py``) is a sibling that covers a
different sink; keep both in sync if the sensitive-key set changes.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Substrings (case-insensitive) that mark a key/value as sensitive. A key whose
# name contains any of these is redacted. This is intentionally broad to catch
# provider-specific variants (openai_api_key, anthropicKey, x-api-key, token,
# secret, password, credential, private_key, bearer, ...).
SENSITIVE_KEY_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "api-key",
        "authorization",
        "credential",
        "private_key",
        "access_token",
        "refresh_token",
        "bearer",
        "x-api-key",
        "sk-",
    }
)

REDACTED = "[REDACTED]"

# Providers whose keys share the ``sk-`` prefix — a value beginning with a
# known key prefix is itself treated as sensitive even when the key name is
# innocent (e.g. an untyped ``value=`` field).
_KEY_VALUE_PREFIXES: tuple[str, ...] = ("sk-", "sk_", "pk-", "pk_", "AIza", "xox", "eyJ")


def is_sensitive_key(key: str) -> bool:
    """Return True if ``key`` (case-insensitive) looks like a secret field."""
    k = key.lower()
    return any(sub in k for sub in SENSITIVE_KEY_SUBSTRINGS)


def looks_like_secret_value(value: str) -> bool:
    """Heuristic: does ``value`` look like a raw secret even with an innocent key?"""
    if not isinstance(value, str) or len(value) < 8:
        return False
    return value.startswith(_KEY_VALUE_PREFIXES)


def scrub_value(key: str, value: Any) -> Any:
    """Return ``[REDACTED]`` if key/value is sensitive, else the value."""
    if is_sensitive_key(key):
        return REDACTED
    if isinstance(value, str) and looks_like_secret_value(value):
        return REDACTED
    return value


def scrub_dict(data: dict[str, Any] | None) -> Any:
    """Recursively redact sensitive keys/values in a dict (returns a new dict).

    Mirrors the contract of the Sentry/MCP ``_scrub_sensitive_data`` so the two
    scrubbers stay behavior-compatible.
    """
    if not isinstance(data, dict):
        return data
    scrubbed: dict[str, Any] = {}
    for key, value in data.items():
        if is_sensitive_key(key):
            scrubbed[key] = REDACTED
        elif isinstance(value, dict):
            scrubbed[key] = scrub_dict(value)
        elif isinstance(value, list):
            scrubbed[key] = [scrub_dict(item) if isinstance(item, dict) else item for item in value]
        elif isinstance(value, str) and looks_like_secret_value(value):
            scrubbed[key] = REDACTED
        else:
            scrubbed[key] = value
    return scrubbed


# ---------------------------------------------------------------------------
# Sinks
# ---------------------------------------------------------------------------
from opentelemetry.sdk.trace import SpanProcessor


def scrub_span_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Scrub a dict of OTel span attributes before they are exported.

    OTel span attribute values may be scalars or lists of scalars; this
    redacts any attribute whose key or string value looks sensitive.
    """
    if not isinstance(attributes, dict):
        return attributes
    out: dict[str, Any] = {}
    for key, value in attributes.items():
        if is_sensitive_key(key):
            out[key] = REDACTED
            continue
        if isinstance(value, str) and looks_like_secret_value(value):
            out[key] = REDACTED
        elif isinstance(value, list) and value and isinstance(value[0], str):
            out[key] = [REDACTED if looks_like_secret_value(v) else v for v in value]
        else:
            out[key] = value
    return out


class SpanAttributeScrubber(SpanProcessor):
    """OTel ``SpanProcessor`` that redacts sensitive span attributes on export.

    Register via ``provider.add_span_processor(SpanAttributeScrubber())`` in
    ``app/core/telemetry.py`` so every exported span (Jaeger) is scrubbed.
    """

    def on_end(self, span) -> None:
        attrs = getattr(span, "_attributes", None)
        if not attrs:
            return
        scrubbed = scrub_span_attributes(dict(attrs))
        # Replace in place so exporters (Jaeger) receive the redacted values.
        attrs.clear()
        attrs.update(scrubbed)

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


# ---------------------------------------------------------------------------
# structlog processor
# ---------------------------------------------------------------------------
def structlog_scrub_processor(_logger, _method, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor that redacts sensitive key/value pairs in event data.

    Registered in ``structlog.configure(processors=[...])``. It walks the
    event dict (which may contain nested dicts/lists) and redacts anything a
    key name or value hints is secret, so a BYOK key can never be emitted via
    ``logger.info/debug/...``.
    """
    if not isinstance(event_dict, dict):
        return event_dict
    return scrub_dict(event_dict)
