"""Tests for Twilio integration wiring.

Verifies that the Twilio integration is properly wired through all layers:
AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, non-OAuth config, and settings.
"""

import pytest


def test_twilio_in_available_integrations():
    """Twilio is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    twilio = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "twilio"), None)
    assert twilio is not None
    assert twilio.name == "Twilio"
    assert twilio.auth_type == "api_key"
    assert twilio.category == "communication"


def test_twilio_manifest_exists():
    """Twilio manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "twilio.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "twilio"
    assert manifest["name"] == "Twilio"
    assert manifest["auth_type"] == "api_key"
    assert len(manifest["capabilities"]) >= 10


def test_twilio_bridge_capabilities():
    """Twilio has all 10 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("twilio", [])
    assert len(caps) >= 10

    ids = {c["id"] for c in caps}
    expected = {
        "get_account",
        "list_messages",
        "send_message",
        "list_calls",
        "get_call",
        "make_call",
        "list_phone_numbers",
        "get_recording",
        "list_recordings",
        "get_usage",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_twilio_webhook_router_exists():
    """Twilio webhook router is importable."""
    from app.api.v1.twilio_webhook import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/twilio/webhook" in routes


def test_twilio_connector_importable():
    """TwilioConnector is importable and has 10 actions."""
    from app.services.connectors.twilio_connector import TwilioConnector

    assert TwilioConnector is not None
    assert len(TwilioConnector.ACTIONS) == 10


def test_twilio_settings_exist():
    """Twilio settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "TWILIO_ACCOUNT_SID")
    assert hasattr(settings, "TWILIO_API_KEY_SID")
    assert hasattr(settings, "TWILIO_API_KEY_SECRET")
    assert hasattr(settings, "TWILIO_WEBHOOK_SECRET")


def test_twilio_in_non_oauth_configs():
    """Twilio is registered as a non-OAuth integration."""
    from app.services.integration_bridge import _NON_OAUTH_CONFIGS

    twilio = _NON_OAUTH_CONFIGS.get("twilio")
    assert twilio is not None
    assert twilio["auth_type"] == "api_key"
