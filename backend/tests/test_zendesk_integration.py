"""Tests for Zendesk integration wiring.

Verifies that the Zendesk integration is properly wired through all layers:
AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, OAuth provider, and settings.
"""

import pytest


def test_zendesk_in_v1_oauth_providers():
    """Zendesk is in the OAuth providers dict."""
    from app.core.oauth import OAUTH_PROVIDERS

    zendesk = OAUTH_PROVIDERS.get("zendesk")
    assert zendesk is not None
    assert zendesk.slug == "zendesk"
    assert zendesk.name == "Zendesk"
    assert "zendesk.com" in zendesk.authorize_url


def test_zendesk_in_available_integrations():
    """Zendesk is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    zendesk = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "zendesk"), None)
    assert zendesk is not None
    assert zendesk.name == "Zendesk"
    assert zendesk.auth_type == "oauth2"
    assert zendesk.category == "support"


def test_zendesk_manifest_exists():
    """Zendesk manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "zendesk.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "zendesk"
    assert manifest["name"] == "Zendesk"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 12


def test_zendesk_bridge_capabilities():
    """Zendesk has all 12 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("zendesk", [])
    assert len(caps) >= 12

    ids = {c["id"] for c in caps}
    expected = {
        "get_me",
        "list_tickets",
        "get_ticket",
        "create_ticket",
        "update_ticket",
        "list_users",
        "get_user",
        "search_tickets",
        "list_organizations",
        "list_groups",
        "add_ticket_comment",
        "list_ticket_metrics",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_zendesk_webhook_router_exists():
    """Zendesk webhook router is importable."""
    from app.api.v1.integration_webhooks import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/{provider}/webhook" in routes


def test_zendesk_connector_importable():
    """ZendeskConnector is importable and has 12 actions."""
    from app.services.connectors.zendesk_connector import ZendeskConnector

    assert ZendeskConnector is not None
    assert len(ZendeskConnector.ACTIONS) == 12


def test_zendesk_settings_exist():
    """Zendesk settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "ZENDESK_OAUTH_CLIENT_ID")
    assert hasattr(settings, "ZENDESK_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "ZENDESK_WEBHOOK_SECRET")
