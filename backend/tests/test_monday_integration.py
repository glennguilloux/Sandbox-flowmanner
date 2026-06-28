"""Tests for Monday.com integration wiring.

Verifies that the Monday.com integration is properly wired through all layers:
AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, OAuth provider, and settings.
"""

import pytest


def test_monday_in_v1_oauth_providers():
    """Monday is in the OAuth providers dict."""
    from app.core.oauth import OAUTH_PROVIDERS

    monday = OAUTH_PROVIDERS.get("monday")
    assert monday is not None
    assert monday.slug == "monday"
    assert monday.name == "Monday.com"
    assert "monday.com" in monday.authorize_url


def test_monday_in_available_integrations():
    """Monday is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    monday = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "monday"), None)
    assert monday is not None
    assert monday.name == "Monday.com"
    assert monday.auth_type == "oauth2"
    assert monday.category == "productivity"


def test_monday_manifest_exists():
    """Monday manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "monday.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "monday"
    assert manifest["name"] == "Monday.com"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 10


def test_monday_bridge_capabilities():
    """Monday has all 10 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("monday", [])
    assert len(caps) >= 10

    ids = {c["id"] for c in caps}
    expected = {
        "get_me",
        "list_boards",
        "get_board",
        "list_items",
        "get_item",
        "create_item",
        "update_item",
        "create_update",
        "list_users",
        "list_workspaces",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_monday_webhook_router_exists():
    """Monday webhook router is importable."""
    from app.api.v1.monday_webhook import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/monday/webhook" in routes


def test_monday_connector_importable():
    """MondayConnector is importable and has 10 actions."""
    from app.services.connectors.monday_connector import MondayConnector

    assert MondayConnector is not None
    assert len(MondayConnector.ACTIONS) == 10


def test_monday_settings_exist():
    """Monday settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "MONDAY_OAUTH_CLIENT_ID")
    assert hasattr(settings, "MONDAY_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "MONDAY_WEBHOOK_SECRET")
