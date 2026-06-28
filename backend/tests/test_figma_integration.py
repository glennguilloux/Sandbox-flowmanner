"""Tests for Figma integration wiring."""

import pytest


def test_figma_in_v1_oauth_providers():
    """Figma OAuth provider is registered in the v1 system."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("figma")
    assert provider is not None
    assert provider.slug == "figma"
    assert provider.scopes == [
        "file_content:read",
        "file_comments:read",
        "file_comments:write",
        "file_versions:read",
    ]
    assert provider.client_id_env == "FIGMA_OAUTH_CLIENT_ID"
    assert provider.authorize_url == "https://www.figma.com/oauth"
    assert provider.token_url == "https://www.figma.com/api/oauth/token"


def test_figma_in_available_integrations():
    """Figma appears in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    slugs = [i.slug for i in AVAILABLE_INTEGRATIONS]
    assert "figma" in slugs


def test_figma_manifest_exists():
    """Figma manifest JSON exists and is valid."""
    from app.services.integration_manifest_service import manifest_service

    m = manifest_service.get("figma")
    assert m is not None
    assert m["slug"] == "figma"
    assert m["auth_type"] == "oauth2"
    assert len(m["capabilities"]) >= 8


def test_figma_bridge_capabilities():
    """Figma capabilities are registered in the integration bridge."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("figma", [])
    assert len(caps) >= 8
    cap_ids = [c["id"] for c in caps]
    assert "get_me" in cap_ids
    assert "get_file" in cap_ids
    assert "get_file_nodes" in cap_ids
    assert "list_comments" in cap_ids
    assert "post_comment" in cap_ids
    assert "get_file_versions" in cap_ids
    assert "list_team_projects" in cap_ids
    assert "list_project_files" in cap_ids


def test_figma_webhook_router_exists():
    """Figma webhook router is importable with correct paths."""
    from app.api.v1.figma_webhook import router

    assert router is not None
    paths = [r.path for r in router.routes]  # type: ignore[union-attr]
    assert "/figma/webhook" in paths


def test_figma_connector_importable():
    """FigmaConnector can be imported and has expected actions."""
    from app.services.connectors.figma_connector import FigmaConnector

    assert FigmaConnector.CONNECTOR_TYPE == "figma"
    assert "get_me" in FigmaConnector.ACTIONS
    assert "get_file" in FigmaConnector.ACTIONS
    assert "get_file_nodes" in FigmaConnector.ACTIONS
    assert "list_comments" in FigmaConnector.ACTIONS
    assert "post_comment" in FigmaConnector.ACTIONS
    assert "get_file_versions" in FigmaConnector.ACTIONS
    assert "list_team_projects" in FigmaConnector.ACTIONS
    assert "list_project_files" in FigmaConnector.ACTIONS
    assert len(FigmaConnector.ACTIONS) == 8


def test_figma_settings_exist():
    """Figma OAuth settings exist in config."""
    from app.config import settings

    assert hasattr(settings, "FIGMA_OAUTH_CLIENT_ID")
    assert hasattr(settings, "FIGMA_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "FIGMA_WEBHOOK_SECRET")
