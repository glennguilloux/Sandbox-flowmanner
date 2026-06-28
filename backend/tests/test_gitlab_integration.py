"""Tests for GitLab integration wiring.

Verifies that the GitLab integration is properly wired through all layers:
OAuth provider, AVAILABLE_INTEGRATIONS, manifest, bridge capabilities,
webhook router, connector, and settings.
"""

import pytest


def test_gitlab_in_v1_oauth_providers():
    """GitLab OAuth provider is registered."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("gitlab")
    assert provider is not None
    assert provider.slug == "gitlab"
    assert provider.name == "GitLab"
    assert provider.authorize_url == "https://gitlab.com/oauth/authorize"
    assert provider.token_url == "https://gitlab.com/oauth/token"
    assert provider.client_id_env == "GITLAB_OAUTH_CLIENT_ID"
    assert provider.client_secret_env == "GITLAB_OAUTH_CLIENT_SECRET"
    assert "api" in provider.scopes


def test_gitlab_in_available_integrations():
    """GitLab is in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    gitlab = next((i for i in AVAILABLE_INTEGRATIONS if i.slug == "gitlab"), None)
    assert gitlab is not None
    assert gitlab.name == "GitLab"
    assert gitlab.auth_type == "oauth2"
    assert gitlab.category == "development"


def test_gitlab_manifest_exists():
    """GitLab manifest file exists and is valid."""
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[1] / "integrations" / "manifests" / "gitlab.json"
    assert manifest_path.exists(), f"Manifest not found: {manifest_path}"

    import json

    manifest = json.loads(manifest_path.read_text())
    assert manifest["slug"] == "gitlab"
    assert manifest["name"] == "GitLab"
    assert manifest["auth_type"] == "oauth2"
    assert len(manifest["capabilities"]) >= 14


def test_gitlab_bridge_capabilities():
    """GitLab has all 14 bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("gitlab", [])
    assert len(caps) >= 14

    ids = {c["id"] for c in caps}
    expected = {
        "get_me",
        "list_projects",
        "get_project",
        "list_merge_requests",
        "get_merge_request",
        "create_merge_request",
        "merge_merge_request",
        "approve_merge_request",
        "list_issues",
        "get_issue",
        "create_issue",
        "add_issue_note",
        "list_pipelines",
        "retry_pipeline",
    }
    assert expected.issubset(ids), f"Missing capabilities: {expected - ids}"


def test_gitlab_webhook_router_exists():
    """GitLab webhook router is importable."""
    from app.api.v1.gitlab_webhook import router

    assert router is not None
    routes = [r.path for r in router.routes]
    assert "/gitlab/webhook" in routes


def test_gitlab_connector_importable():
    """GitLabConnector is importable and has 14 actions."""
    from app.services.connectors.gitlab_connector import GitLabConnector

    assert GitLabConnector is not None
    assert len(GitLabConnector.ACTIONS) == 14


def test_gitlab_settings_exist():
    """GitLab settings are defined in config."""
    from app.config import settings

    assert hasattr(settings, "GITLAB_OAUTH_CLIENT_ID")
    assert hasattr(settings, "GITLAB_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "GITLAB_WEBHOOK_SECRET")
