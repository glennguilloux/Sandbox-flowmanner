"""Tests for PagerDuty integration wiring.

Verifies that the PagerDuty integration is properly wired through all layers:
OAuth provider, AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, and settings.
"""

import pytest


def test_pagerduty_in_v1_oauth_providers():
    """PagerDuty OAuth provider is registered."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("pagerduty")
    assert provider is not None
    assert provider.slug == "pagerduty"
    assert provider.name == "PagerDuty"
    assert provider.authorize_url == "https://identity.pagerduty.com/oauth/authorize"
    assert provider.token_url == "https://identity.pagerduty.com/oauth/token"
    assert provider.client_id_env == "PAGERDUTY_OAUTH_CLIENT_ID"
    assert provider.client_secret_env == "PAGERDUTY_OAUTH_CLIENT_SECRET"
    assert "incidents.read" in provider.scopes
    assert "incidents.write" in provider.scopes


def test_pagerduty_in_available_integrations():
    """PagerDuty is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    pd = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "pagerduty"), None)
    assert pd is not None
    assert pd.name == "PagerDuty"
    assert pd.auth_type == "oauth2"
    assert pd.category == "development"


def test_pagerduty_manifest_exists():
    """PagerDuty manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "pagerduty.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "pagerduty"
    assert manifest["name"] == "PagerDuty"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 12


def test_pagerduty_bridge_capabilities():
    """PagerDuty has all 12 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("pagerduty", [])
    assert len(caps) >= 12

    ids = {c["id"] for c in caps}
    expected = {
        "get_me",
        "list_incidents",
        "get_incident",
        "create_incident",
        "update_incident",
        "list_services",
        "get_service",
        "list_schedules",
        "get_schedule",
        "list_escalation_policies",
        "list_users",
        "get_user",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_pagerduty_webhook_router_exists():
    """PagerDuty webhook router is importable."""
    from app.api.v1.integration_webhooks import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/{provider}/webhook" in routes


def test_pagerduty_connector_importable():
    """PagerDutyConnector is importable and has 12 actions."""
    from app.services.connectors.pagerduty_connector import PagerDutyConnector

    assert PagerDutyConnector is not None
    assert len(PagerDutyConnector.ACTIONS) == 12


def test_pagerduty_settings_exist():
    """PagerDuty settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "PAGERDUTY_OAUTH_CLIENT_ID")
    assert hasattr(settings, "PAGERDUTY_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "PAGERDUTY_WEBHOOK_SECRET")
