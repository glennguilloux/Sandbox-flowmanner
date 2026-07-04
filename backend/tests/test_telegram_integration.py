"""Tests for Telegram integration wiring.

Verifies that the Telegram integration is properly wired through all layers:
AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, non-OAuth config, and settings.
"""

import pytest


def test_telegram_in_available_integrations():
    """Telegram is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    telegram = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "telegram"), None)
    assert telegram is not None
    assert telegram.name == "Telegram"
    assert telegram.auth_type == "api_key"
    assert telegram.category == "communication"


def test_telegram_manifest_exists():
    """Telegram manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "telegram.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "telegram"
    assert manifest["name"] == "Telegram"
    assert manifest["auth_type"] == "api_key"
    assert len(manifest["capabilities"]) >= 12


def test_telegram_bridge_capabilities():
    """Telegram has all 12 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("telegram", [])
    assert len(caps) >= 12

    ids = {c["id"] for c in caps}
    expected = {
        "get_me",
        "send_message",
        "send_photo",
        "send_document",
        "edit_message",
        "delete_message",
        "forward_message",
        "get_chat",
        "get_chat_member",
        "pin_message",
        "set_webhook",
        "get_updates",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_telegram_webhook_router_exists():
    """Telegram webhook router is importable."""
    from app.api.v1.integration_webhooks import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/{provider}/webhook" in routes


def test_telegram_connector_importable():
    """TelegramConnector is importable and has 12 actions."""
    from app.services.connectors.telegram_connector import TelegramConnector

    assert TelegramConnector is not None
    assert len(TelegramConnector.ACTIONS) == 12


def test_telegram_settings_exist():
    """Telegram settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "TELEGRAM_BOT_TOKEN")
    assert hasattr(settings, "TELEGRAM_WEBHOOK_SECRET")


def test_telegram_in_non_oauth_configs():
    """Telegram is registered as a non-OAuth integration."""
    from app.services.integration_bridge import _NON_OAUTH_CONFIGS

    telegram = _NON_OAUTH_CONFIGS.get("telegram")
    assert telegram is not None
    assert telegram["auth_type"] == "api_key"
