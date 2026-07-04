"""Tests for Vercel integration wiring."""

import pytest


def test_vercel_in_v1_oauth_providers():
    """Vercel OAuth provider is registered in the v1 system."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("vercel")
    assert provider is not None
    assert provider.slug == "vercel"
    assert provider.scopes == ["user", "projects", "deployments"]
    assert provider.client_id_env == "VERCEL_OAUTH_CLIENT_ID"
    assert provider.authorize_url == "https://vercel.com/oauth/authorize"
    assert provider.token_url == "https://vercel.com/oauth/token"


def test_vercel_in_available_integrations():
    """Vercel appears in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    slugs = [i.slug for i in AVAILABLE_INTEGRATIONS]
    assert "vercel" in slugs


def test_vercel_manifest_exists():
    """Vercel manifest JSON exists and is valid."""
    from app.services.integration_manifest_service import manifest_service

    m = manifest_service.get("vercel")
    assert m is not None
    assert m["slug"] == "vercel"
    assert m["auth_type"] == "oauth2"
    assert len(m["capabilities"]) >= 9


def test_vercel_bridge_capabilities():
    """Vercel capabilities are registered in the integration bridge."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("vercel", [])
    assert len(caps) >= 9
    cap_ids = [c["id"] for c in caps]
    assert "get_me" in cap_ids
    assert "list_projects" in cap_ids
    assert "list_deployments" in cap_ids
    assert "get_deployment" in cap_ids
    assert "cancel_deployment" in cap_ids
    assert "redeploy" in cap_ids
    assert "get_deployment_logs" in cap_ids
    assert "list_domains" in cap_ids


def test_vercel_webhook_router_exists():
    """Vercel webhook router is importable with correct paths."""
    from app.api.v1.integration_webhooks import router

    assert router is not None
    paths = [r.path for r in router.routes]  # type: ignore[union-attr]
    assert "/{provider}/webhook" in paths


def test_vercel_connector_importable():
    """VercelConnector can be imported and has expected actions."""
    from app.services.connectors.vercel_connector import VercelConnector

    assert VercelConnector.CONNECTOR_TYPE == "vercel"
    assert "get_me" in VercelConnector.ACTIONS
    assert "list_projects" in VercelConnector.ACTIONS
    assert "list_deployments" in VercelConnector.ACTIONS
    assert "cancel_deployment" in VercelConnector.ACTIONS
    assert "redeploy" in VercelConnector.ACTIONS
    assert len(VercelConnector.ACTIONS) == 9


def test_vercel_settings_exist():
    """Vercel OAuth settings exist in config."""
    from app.config import settings

    assert hasattr(settings, "VERCEL_OAUTH_CLIENT_ID")
    assert hasattr(settings, "VERCEL_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "VERCEL_WEBHOOK_SECRET")
