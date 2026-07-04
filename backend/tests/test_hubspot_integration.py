"""Tests for HubSpot integration wiring.

Verifies that the HubSpot integration is properly wired through all layers:
OAuth provider, AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, and settings.
"""

import pytest


def test_hubspot_in_v1_oauth_providers():
    """HubSpot OAuth provider is registered."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("hubspot")
    assert provider is not None
    assert provider.slug == "hubspot"
    assert provider.name == "HubSpot"
    assert provider.authorize_url == "https://app.hubspot.com/oauth/authorize"
    assert provider.token_url == "https://api.hubapi.com/oauth/v1/token"
    assert provider.client_id_env == "HUBSPOT_OAUTH_CLIENT_ID"
    assert provider.client_secret_env == "HUBSPOT_OAUTH_CLIENT_SECRET"
    assert "crm.objects.contacts.read" in provider.scopes


def test_hubspot_in_available_integrations():
    """HubSpot is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    hubspot = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "hubspot"), None)
    assert hubspot is not None
    assert hubspot.name == "HubSpot"
    assert hubspot.auth_type == "oauth2"
    assert hubspot.category == "productivity"


def test_hubspot_manifest_exists():
    """HubSpot manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "hubspot.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "hubspot"
    assert manifest["name"] == "HubSpot"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 12


def test_hubspot_bridge_capabilities():
    """HubSpot has all 12 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("hubspot", [])
    assert len(caps) >= 12

    ids = {c["id"] for c in caps}
    expected = {
        "get_owner",
        "list_contacts",
        "get_contact",
        "create_contact",
        "update_contact",
        "list_companies",
        "get_company",
        "list_deals",
        "get_deal",
        "create_deal",
        "search_contacts",
        "list_tickets",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_hubspot_webhook_router_exists():
    """HubSpot webhook router is importable."""
    from app.api.v1.integration_webhooks import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/{provider}/webhook" in routes


def test_hubspot_connector_importable():
    """HubSpotConnector is importable and has 12 actions."""
    from app.services.connectors.hubspot_connector import HubSpotConnector

    assert HubSpotConnector is not None
    assert len(HubSpotConnector.ACTIONS) == 12


def test_hubspot_settings_exist():
    """HubSpot settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "HUBSPOT_OAUTH_CLIENT_ID")
    assert hasattr(settings, "HUBSPOT_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "HUBSPOT_WEBHOOK_SECRET")
