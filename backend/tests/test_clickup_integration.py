"""Tests for ClickUp integration wiring.

Verifies that the ClickUp integration is properly wired through all layers:
OAuth provider, AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, and settings.
"""

import pytest


def test_clickup_in_v1_oauth_providers():
    """ClickUp OAuth provider is registered."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("clickup")
    assert provider is not None
    assert provider.slug == "clickup"
    assert provider.name == "ClickUp"
    assert provider.authorize_url == "https://app.clickup.com/api"
    assert provider.token_url == "https://api.clickup.com/api/v2/oauth/token"
    assert provider.client_id_env == "CLICKUP_OAUTH_CLIENT_ID"
    assert provider.client_secret_env == "CLICKUP_OAUTH_CLIENT_SECRET"


def test_clickup_in_available_integrations():
    """ClickUp is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    clickup = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "clickup"), None)
    assert clickup is not None
    assert clickup.name == "ClickUp"
    assert clickup.auth_type == "oauth2"
    assert clickup.category == "productivity"


def test_clickup_manifest_exists():
    """ClickUp manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "clickup.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "clickup"
    assert manifest["name"] == "ClickUp"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 12


def test_clickup_bridge_capabilities():
    """ClickUp has all 12 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("clickup", [])
    assert len(caps) >= 12

    ids = {c["id"] for c in caps}
    expected = {
        "get_user",
        "list_workspaces",
        "list_spaces",
        "list_folders",
        "list_lists",
        "list_tasks",
        "get_task",
        "create_task",
        "update_task",
        "get_comments",
        "add_comment",
        "list_time_entries",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_clickup_webhook_router_exists():
    """ClickUp webhook router is importable."""
    from app.api.v1.integration_webhooks import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/{provider}/webhook" in routes


def test_clickup_connector_importable():
    """ClickUpConnector is importable and has 12 actions."""
    from app.services.connectors.clickup_connector import ClickUpConnector

    assert ClickUpConnector is not None
    assert len(ClickUpConnector.ACTIONS) == 12


def test_clickup_settings_exist():
    """ClickUp settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "CLICKUP_OAUTH_CLIENT_ID")
    assert hasattr(settings, "CLICKUP_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "CLICKUP_WEBHOOK_SECRET")
