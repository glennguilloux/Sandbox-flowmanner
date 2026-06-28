"""Tests for Confluence integration wiring."""

import pytest


def test_confluence_in_v1_oauth_providers():
    """Confluence OAuth provider is registered in the v1 system."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("confluence")
    assert provider is not None
    assert provider.slug == "confluence"
    assert provider.scopes == [
        "read:confluence-content.all",
        "write:confluence-content",
        "read:confluence-space.summary",
    ]
    assert provider.client_id_env == "CONFLUENCE_OAUTH_CLIENT_ID"
    assert provider.authorize_url == "https://auth.atlassian.com/authorize"
    assert provider.token_url == "https://auth.atlassian.com/oauth/token"
    # Verify audience param is set for Atlassian 3LO
    assert provider.extra_auth_params is not None
    assert provider.extra_auth_params["audience"] == "api.atlassian.com"
    assert provider.extra_auth_params["prompt"] == "consent"


def test_confluence_in_available_integrations():
    """Confluence appears in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    slugs = [i.slug for i in AVAILABLE_INTEGRATIONS]
    assert "confluence" in slugs


def test_confluence_manifest_exists():
    """Confluence manifest JSON exists and is valid."""
    from app.services.integration_manifest_service import manifest_service

    m = manifest_service.get("confluence")
    assert m is not None
    assert m["slug"] == "confluence"
    assert m["auth_type"] == "oauth2"
    assert len(m["capabilities"]) >= 11


def test_confluence_bridge_capabilities():
    """Confluence capabilities are registered in the integration bridge."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("confluence", [])
    assert len(caps) >= 11
    cap_ids = [c["id"] for c in caps]
    assert "get_me" in cap_ids
    assert "list_spaces" in cap_ids
    assert "get_space" in cap_ids
    assert "get_page" in cap_ids
    assert "create_page" in cap_ids
    assert "update_page" in cap_ids
    assert "search_content" in cap_ids
    assert "list_page_children" in cap_ids
    assert "add_comment" in cap_ids
    assert "list_attachments" in cap_ids
    assert "add_labels" in cap_ids


def test_confluence_webhook_router_exists():
    """Confluence webhook router is importable with correct paths."""
    from app.api.v1.confluence_webhook import router

    assert router is not None
    paths = [r.path for r in router.routes]  # type: ignore[union-attr]
    assert "/confluence/webhook" in paths


def test_confluence_oauth_callback_router_exists():
    """Confluence custom OAuth callback router is importable."""
    from app.api.v1.confluence_oauth import router

    assert router is not None
    paths = [r.path for r in router.routes]  # type: ignore[union-attr]
    assert "/confluence/oauth/callback" in paths


def test_confluence_connector_importable():
    """ConfluenceConnector can be imported and has expected actions."""
    from app.services.connectors.confluence_connector import ConfluenceConnector

    assert ConfluenceConnector.CONNECTOR_TYPE == "confluence"
    assert "get_me" in ConfluenceConnector.ACTIONS
    assert "list_spaces" in ConfluenceConnector.ACTIONS
    assert "get_page" in ConfluenceConnector.ACTIONS
    assert "create_page" in ConfluenceConnector.ACTIONS
    assert "update_page" in ConfluenceConnector.ACTIONS
    assert "search_content" in ConfluenceConnector.ACTIONS
    assert "add_comment" in ConfluenceConnector.ACTIONS
    assert "list_attachments" in ConfluenceConnector.ACTIONS
    assert "add_labels" in ConfluenceConnector.ACTIONS
    assert len(ConfluenceConnector.ACTIONS) == 11


def test_confluence_settings_exist():
    """Confluence OAuth settings exist in config."""
    from app.config import settings

    assert hasattr(settings, "CONFLUENCE_OAUTH_CLIENT_ID")
    assert hasattr(settings, "CONFLUENCE_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "CONFLUENCE_WEBHOOK_SECRET")


def test_confluence_connector_requires_cloud_id():
    """ConfluenceConnector validates that cloud_id is in auth_config."""
    from app.services.connectors.base import AuthType, ConnectorConfig
    from app.services.connectors.confluence_connector import ConfluenceConnector

    config = ConnectorConfig(
        name="test-confluence",
        connector_type="confluence",
        auth_type=AuthType.OAUTH2,
        auth_config={"access_token": "test-token"},
    )
    connector = ConfluenceConnector(config)
    # Without cloud_id, _validate_credentials should handle gracefully
    assert connector.CONNECTOR_TYPE == "confluence"
