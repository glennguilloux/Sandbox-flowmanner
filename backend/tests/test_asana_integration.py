"""Tests for Asana integration wiring.

Verifies that the Asana integration is properly wired through all layers:
OAuth provider, AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, and settings.
"""

import pytest


def test_asana_in_v1_oauth_providers():
    """Asana OAuth provider is registered."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("asana")
    assert provider is not None
    assert provider.slug == "asana"
    assert provider.name == "Asana"
    assert provider.authorize_url == "https://app.asana.com/-/oauth_authorize"
    assert provider.token_url == "https://app.asana.com/-/oauth_token"
    assert provider.client_id_env == "ASANA_OAUTH_CLIENT_ID"
    assert provider.client_secret_env == "ASANA_OAUTH_CLIENT_SECRET"


def test_asana_in_available_integrations():
    """Asana is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    asana = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "asana"), None)
    assert asana is not None
    assert asana.name == "Asana"
    assert asana.auth_type == "oauth2"
    assert asana.category == "productivity"


def test_asana_manifest_exists():
    """Asana manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "asana.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "asana"
    assert manifest["name"] == "Asana"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 10


def test_asana_bridge_capabilities():
    """Asana has all 10 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("asana", [])
    assert len(caps) >= 10

    ids = {c["id"] for c in caps}
    expected = {
        "get_me",
        "list_workspaces",
        "list_projects",
        "get_project",
        "list_tasks",
        "get_task",
        "create_task",
        "update_task",
        "complete_task",
        "list_sections",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_asana_webhook_router_exists():
    """Asana webhook router is importable."""
    from app.api.v1.asana_webhook import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/asana/webhook" in routes


def test_asana_connector_importable():
    """AsanaConnector is importable and has 10 actions."""
    from app.services.connectors.asana_connector import AsanaConnector

    assert AsanaConnector is not None
    assert len(AsanaConnector.ACTIONS) == 10


def test_asana_settings_exist():
    """Asana settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "ASANA_OAUTH_CLIENT_ID")
    assert hasattr(settings, "ASANA_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "ASANA_WEBHOOK_SECRET")
