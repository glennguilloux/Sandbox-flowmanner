"""Tests for Airtable integration wiring.

Verifies that the Airtable integration is properly wired through all layers:
OAuth provider, AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, and settings.
"""

import pytest


def test_airtable_in_v1_oauth_providers():
    """Airtable OAuth provider is registered."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("airtable")
    assert provider is not None
    assert provider.slug == "airtable"
    assert provider.name == "Airtable"
    assert provider.authorize_url == "https://airtable.com/oauth2/v1/authorize"
    assert provider.token_url == "https://airtable.com/oauth2/v1/token"
    assert provider.client_id_env == "AIRTABLE_OAUTH_CLIENT_ID"
    assert provider.client_secret_env == "AIRTABLE_OAUTH_CLIENT_SECRET"
    assert "data.records:read" in provider.scopes
    assert "data.records:write" in provider.scopes


def test_airtable_in_available_integrations():
    """Airtable is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    at = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "airtable"), None)
    assert at is not None
    assert at.name == "Airtable"
    assert at.auth_type == "oauth2"
    assert at.category == "productivity"


def test_airtable_manifest_exists():
    """Airtable manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "airtable.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "airtable"
    assert manifest["name"] == "Airtable"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 9


def test_airtable_bridge_capabilities():
    """Airtable has all 9 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("airtable", [])
    assert len(caps) >= 9

    ids = {c["id"] for c in caps}
    expected = {
        "list_bases",
        "get_base",
        "list_tables",
        "get_table",
        "list_records",
        "get_record",
        "create_record",
        "update_record",
        "delete_record",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_airtable_webhook_router_exists():
    """Airtable webhook router is importable."""
    from app.api.v1.airtable_webhook import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/airtable/webhook" in routes


def test_airtable_connector_importable():
    """AirtableConnector is importable and has 9 actions."""
    from app.services.connectors.airtable_connector import AirtableConnector

    assert AirtableConnector is not None
    assert len(AirtableConnector.ACTIONS) == 9


def test_airtable_settings_exist():
    """Airtable settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "AIRTABLE_OAUTH_CLIENT_ID")
    assert hasattr(settings, "AIRTABLE_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "AIRTABLE_WEBHOOK_SECRET")
