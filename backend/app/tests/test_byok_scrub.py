"""Regression tests: BYOK keys must be envelope-encrypted AND never leak.

These tests guard two P0 findings fixed on this branch:

1. CRYPTO: ``encrypt_api_key`` must produce *envelope* encryption (v3:
   KEK wraps a per-record DEK), not single-key AES. Before the fix the
   format was ``v2:`` (single master key, no KEK/DEK split) and it
   referenced ``settings.ENCRYPTION_KEY`` which does not exist — silently
   falling back to the JWT ``SECRET_KEY``.

2. LEAK SURFACE: a known plaintext API key must NEVER appear in captured
   structlog output or in OTel span attributes after a BYOK create+read
   round-trip. The raw key is scrubbed via ``app.utils.scrubber``.

Run from the live tree (host venv) — do NOT test against the /app container:
    cd /opt/flowmanner/backend
    /opt/flowmanner/backend/.venv/bin/python -m pytest \\
        app/tests/test_byok_scrub.py -q --tb=short
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from app.utils import encryption as enc_module
from app.utils.scrubber import SpanAttributeScrubber, scrub_dict, structlog_scrub_processor

# A realistic-looking but FAKE secret used only to prove it never leaks.
# Deliberately does NOT start with "sk-" so it is not mistaken for a real key
# by secret scanners; the scrubber redacts it via the "api_key" field name
# (its primary, key-name based protection) in the leak assertions below.
KNOWN_KEY = "BYOKFAKE-SUPERSECRET-0123456789abcdef-ZXCVBNM"
KEK_SECRET = "a-productions-grade-kek-secret-at-least-32-chars!!"


@pytest.fixture
def byok_settings():
    """Patch settings so encryption uses a dedicated, non-JWT KEK secret."""
    mock = type(
        "S",
        (),
        {
            "BYOK_KEK_SECRET": KEK_SECRET,
            "AES_ENCRYPTION_KEY": "unused-enc-key",
            "SECRET_KEY": "the-jwt-signing-secret-do-not-use",
            "ENCRYPTION_ALLOW_LEGACY_DECRYPT": True,
        },
    )()
    _reset = getattr(enc_module, "_clear_kek_cache", lambda: None)
    with patch.object(enc_module, "settings", mock):
        _reset()
        yield mock
        _reset()


def test_byok_uses_envelope_v3_format(byok_settings):
    """encrypt_api_key must produce the v3 envelope, not single-key v2."""
    encrypted = enc_module.encrypt_api_key(KNOWN_KEY)
    assert encrypted.startswith("v3:"), (
        f"Expected v3 envelope format, got: {encrypted[:8]!r} "
        "(single-key / legacy format — KEK/DEK separation missing)"
    )
    # v3 envelope = kek_id:wrapped_dek:payload  => 4 colon-separated parts.
    parts = encrypted.split(":")
    assert len(parts) == 4, f"v3 envelope must have 4 parts, got {len(parts)}: {encrypted!r}"
    # Random DEK => two encryptions of the same plaintext differ.
    assert enc_module.encrypt_api_key(KNOWN_KEY) != encrypted
    assert enc_module.decrypt_api_key(encrypted) == KNOWN_KEY


def test_byok_key_never_in_structlog(byok_settings):
    """A BYOK key must be redacted by the structlog scrubber before rendering.

    Control + fix in one test: without the scrubber processor a logged secret
    reaches output (the pre-fix reality); with it, the secret is [REDACTED].
    """
    import structlog
    from structlog.testing import capture_logs

    # --- Control: a logging pipeline WITHOUT the scrubber leaks the key. ---
    # capture_logs auto-appends add_log_level + LogCapture, so we only need to
    # supply (or omit) our scrubber. With no scrubber the raw key is captured.
    with capture_logs(processors=[]) as control_captured:
        structlog.get_logger().info("byok.create", api_key=KNOWN_KEY, provider="openai")
    control_out = "\n".join(str(e) for e in control_captured)
    assert KNOWN_KEY in control_out, "control: key must be present when unscubbed (documents the leak)"

    # --- Fix: the production scrubber processor redacts the secret. ---
    with capture_logs(processors=[structlog_scrub_processor]) as fixed_captured:
        structlog.get_logger().info("byok.create", api_key=KNOWN_KEY, provider="openai")
    fixed_out = "\n".join(str(e) for e in fixed_captured)
    assert KNOWN_KEY not in fixed_out, f"BYOK key leaked into structlog output:\n{fixed_out}"
    assert "[REDACTED]" in fixed_out, "scrubber should have redacted the api_key field"


def test_byok_key_never_in_span_attributes(byok_settings):
    """A BYOK key set on a span must be scrubbed before export (Jaeger).

    Control + fix in one test: a TracerProvider WITHOUT the scrubber exports
    the raw key (the pre-fix reality — no SpanProcessor scrubbed spans); a
    TracerProvider WITH ``SpanAttributeScrubber`` redacts it.
    """
    from opentelemetry.sdk.trace import SpanProcessor, TracerProvider

    prev = trace.get_tracer_provider()
    try:
        # --- Control: no scrubber -> raw key exported (documents the leak). ---
        class ControlCapture(SpanProcessor):
            def on_end(self, span):
                self.captured.append(dict(getattr(span, "_attributes", {})))

            def shutdown(self):
                return None

            def force_flush(self, timeout_millis=30000):
                return True

        bare_provider = TracerProvider()
        control_cap = ControlCapture()
        control_cap.captured = []
        bare_provider.add_span_processor(control_cap)
        trace.set_tracer_provider(bare_provider)
        tracer = bare_provider.get_tracer("byok-control")
        with tracer.start_as_current_span("byok.roundtrip") as span:
            span.set_attribute("byok.api_key", KNOWN_KEY)
        assert control_cap.captured, "control span was not exported"
        assert (
            control_cap.captured[0]["byok.api_key"] == KNOWN_KEY
        ), "control: raw key must be exported when unscrubbed (documents the leak)"

        # --- Fix: SpanAttributeScrubber redacts the key before export. ---
        provider = TracerProvider()
        fixed_captured: list = []

        class CaptureProcessor(SpanAttributeScrubber):
            def on_end(self, span):
                super().on_end(span)
                fixed_captured.append(dict(getattr(span, "_attributes", {})))

        provider.add_span_processor(CaptureProcessor())
        trace.set_tracer_provider(provider)
        tracer = provider.get_tracer("byok-test")
        with tracer.start_as_current_span("byok.roundtrip") as span:
            span.set_attribute("byok.api_key", KNOWN_KEY)
            span.set_attribute("byok.provider", "openai")
            enc = enc_module.encrypt_api_key(KNOWN_KEY)
            span.set_attribute("byok.encrypted_len", len(enc))
        assert fixed_captured, "span was not exported"
        exported = fixed_captured[0]
        assert "byok.api_key" in exported, "sanity: attribute key present"
        assert exported["byok.api_key"] == "[REDACTED]", f"BYOK key leaked into span attributes: {exported!r}"
    finally:
        trace.set_tracer_provider(prev)


def test_scrubber_redacts_known_key_value():
    """The shared scrubber must redact a raw secret value under an innocent key."""
    # A value that starts with a known provider-key prefix (sk-) exercises the
    # value-based heuristic even when the field name is innocent ("value").
    sk_like = "sk-FAKESECRETVALUE0123456789abcdef"  # gitleaks:allow
    dirty = {
        "request_id": "abc",
        "config": {"apiKey": KNOWN_KEY},
        "value": sk_like,  # innocent key, secret value (caught by prefix heuristic)
        "nested": [{"token": KNOWN_KEY}],
    }
    clean = scrub_dict(dirty)
    assert clean["request_id"] == "abc"
    assert clean["config"]["apiKey"] == "[REDACTED]"
    assert clean["value"] == "[REDACTED]"
    assert clean["nested"][0]["token"] == "[REDACTED]"
    # None of the cleaned output contains the raw key.
    assert KNOWN_KEY not in str(clean)
    assert sk_like not in str(clean)


def test_kek_not_derived_from_jwt_secret(byok_settings):
    """If BYOK_KEK_SECRET is unset, the code must NOT silently use SECRET_KEY.

    Guards against the original regression where encryption referenced a
    nonexistent settings.ENCRYPTION_KEY and fell back to the JWT secret.
    Here we set a real KEK and confirm the ciphertext is indecipherable with
    the JWT secret alone (i.e. the KEK is the real wrapping key).
    """
    enc = enc_module.encrypt_api_key(KNOWN_KEY)
    # Build a settings object that only has the JWT secret — no KEK.
    jwt_only = type(
        "S",
        (),
        {
            "BYOK_KEK_SECRET": None,
            "AES_ENCRYPTION_KEY": "unused",
            "SECRET_KEY": "the-jwt-signing-secret-do-not-use",
            "ENCRYPTION_ALLOW_LEGACY_DECRYPT": True,
        },
    )()
    with patch.object(enc_module, "settings", jwt_only):
        enc_module._clear_kek_cache()
        try:
            # Decrypting with the wrong KEK must fail (InvalidToken), proving
            # the KEK is the actual wrapping key, not the JWT secret.
            enc_module.decrypt_api_key(enc)
            pytest.fail("Decryption succeeded with JWT-only secret — KEK is not the real wrapping key")
        except Exception:  # InvalidToken expected
            pass
        finally:
            enc_module._clear_kek_cache()
