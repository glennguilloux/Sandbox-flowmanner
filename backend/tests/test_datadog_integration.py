"""Tests for Datadog integration wiring.

Verifies that the Datadog integration is properly wired through all layers:
OAuth provider, AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, and settings.
"""

import pytest


def test_datadog_in_v1_oauth_providers():
    """Datadog OAuth provider is registered."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("datadog")
    assert provider is not None
    assert provider.slug == "datadog"
    assert provider.name == "Datadog"
    assert provider.authorize_url == "https://app.datadoghq.com/oauth2/v1/authorize"
    assert provider.token_url == "https://app.datadoghq.com/oauth2/v1/token"
    assert provider.client_id_env == "DATADOG_OAUTH_CLIENT_ID"
    assert provider.client_secret_env == "DATADOG_OAUTH_CLIENT_SECRET"
    assert "monitors_read" in provider.scopes
    assert "incidents_write" in provider.scopes


def test_datadog_in_available_integrations():
    """Datadog is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    dd = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "datadog"), None)
    assert dd is not None
    assert dd.name == "Datadog"
    assert dd.auth_type == "oauth2"
    assert dd.category == "development"


def test_datadog_manifest_exists():
    """Datadog manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "datadog.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "datadog"
    assert manifest["name"] == "Datadog"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 12


def test_datadog_bridge_capabilities():
    """Datadog has all 12 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("datadog", [])
    assert len(caps) >= 12

    ids = {c["id"] for c in caps}
    expected = {
        "get_current_user",
        "list_monitors",
        "get_monitor",
        "list_incidents",
        "get_incident",
        "create_incident",
        "update_incident",
        "list_dashboards",
        "get_dashboard",
        "list_metrics",
        "query_metrics",
        "list_events",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_datadog_webhook_router_exists():
    """Datadog webhook router is importable."""
    from app.api.v1.datadog_webhook import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/datadog/webhook" in routes


def test_datadog_connector_importable():
    """DatadogConnector is importable and has 12 actions."""
    from app.services.connectors.datadog_connector import DatadogConnector

    assert DatadogConnector is not None
    assert len(DatadogConnector.ACTIONS) == 12


def test_datadog_settings_exist():
    """Datadog settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "DATADOG_OAUTH_CLIENT_ID")
    assert hasattr(settings, "DATADOG_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "DATADOG_WEBHOOK_SECRET")
