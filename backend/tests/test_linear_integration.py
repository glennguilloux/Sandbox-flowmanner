"""Tests for Linear integration wiring."""

import pytest


def test_linear_in_v1_oauth_providers():
    """Linear OAuth provider is registered in the v1 system."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("linear")
    assert provider is not None
    assert provider.slug == "linear"
    assert provider.scopes == ["read", "write"]
    assert provider.client_id_env == "LINEAR_OAUTH_CLIENT_ID"


def test_linear_in_available_integrations():
    """Linear appears in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    slugs = [i.slug for i in AVAILABLE_INTEGRATIONS]
    assert "linear" in slugs


def test_linear_manifest_exists():
    """Linear manifest JSON exists and is valid."""
    from app.services.integration_manifest_service import manifest_service

    m = manifest_service.get("linear")
    assert m is not None
    assert m["slug"] == "linear"
    assert m["auth_type"] == "oauth2"
    assert len(m["capabilities"]) >= 7


def test_linear_bridge_capabilities():
    """Linear capabilities are registered in the integration bridge."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("linear", [])
    assert len(caps) >= 7
    cap_names = [c["name"] for c in caps]
    assert "Create Linear Issue" in cap_names


def test_linear_webhook_router_exists():
    """Linear webhook router is importable."""
    from app.api.v1.linear import router

    assert router is not None
    # Verify the webhook endpoint is registered
    paths = [r.path for r in router.routes]  # type: ignore[union-attr]
    assert "/linear/webhook" in paths


def test_linear_connector_importable():
    """Linear connector can be imported."""
    from app.services.connectors.linear_connector import LinearConnector

    assert LinearConnector.CONNECTOR_TYPE == "linear"
    assert "create_issue" in LinearConnector.ACTIONS


def test_linear_settings_exist():
    """Linear OAuth settings exist in config."""
    from app.config import settings

    # These should be empty strings by default (not raise)
    assert hasattr(settings, "LINEAR_OAUTH_CLIENT_ID")
    assert hasattr(settings, "LINEAR_OAUTH_CLIENT_SECRET")
