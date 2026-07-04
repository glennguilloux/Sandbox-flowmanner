"""Tests for Intercom integration wiring.

Verifies that the Intercom integration is properly wired through all layers:
OAuth provider, AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, and settings.
"""

import pytest


def test_intercom_in_v1_oauth_providers():
    """Intercom OAuth provider is registered."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("intercom")
    assert provider is not None
    assert provider.slug == "intercom"
    assert provider.name == "Intercom"
    assert provider.authorize_url == "https://app.intercom.com/oauth"
    assert provider.token_url == "https://api.intercom.io/auth/eagle/token"
    assert provider.client_id_env == "INTERCOM_OAUTH_CLIENT_ID"
    assert provider.client_secret_env == "INTERCOM_OAUTH_CLIENT_SECRET"


def test_intercom_in_available_integrations():
    """Intercom is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    intercom = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "intercom"), None)
    assert intercom is not None
    assert intercom.name == "Intercom"
    assert intercom.auth_type == "oauth2"
    assert intercom.category == "communication"


def test_intercom_manifest_exists():
    """Intercom manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "intercom.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "intercom"
    assert manifest["name"] == "Intercom"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 10


def test_intercom_bridge_capabilities():
    """Intercom has all 10 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("intercom", [])
    assert len(caps) >= 10

    ids = {c["id"] for c in caps}
    expected = {
        "get_admin",
        "list_conversations",
        "get_conversation",
        "reply_to_conversation",
        "list_contacts",
        "get_contact",
        "list_companies",
        "list_teams",
        "list_tags",
        "search_contacts",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_intercom_webhook_router_exists():
    """Intercom webhook router is importable."""
    from app.api.v1.integration_webhooks import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/{provider}/webhook" in routes


def test_intercom_connector_importable():
    """IntercomConnector is importable and has 10 actions."""
    from app.services.connectors.intercom_connector import IntercomConnector

    assert IntercomConnector is not None
    assert len(IntercomConnector.ACTIONS) == 10


def test_intercom_settings_exist():
    """Intercom settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "INTERCOM_OAUTH_CLIENT_ID")
    assert hasattr(settings, "INTERCOM_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "INTERCOM_WEBHOOK_SECRET")
