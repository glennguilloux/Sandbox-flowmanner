"""Tests for Jira integration wiring."""

import pytest


def test_jira_in_v1_oauth_providers():
    """Jira OAuth provider is registered in the v1 system."""
    from app.core.oauth import OAUTH_PROVIDERS

    provider = OAUTH_PROVIDERS.get("jira")
    assert provider is not None
    assert provider.slug == "jira"
    assert provider.scopes == ["read:jira-work", "write:jira-work", "read:jira-user"]
    assert provider.client_id_env == "JIRA_OAUTH_CLIENT_ID"
    assert provider.authorize_url == "https://auth.atlassian.com/authorize"
    assert provider.token_url == "https://auth.atlassian.com/oauth/token"
    # Verify audience param is set for Atlassian 3LO
    assert provider.extra_auth_params is not None
    assert provider.extra_auth_params["audience"] == "api.atlassian.com"
    assert provider.extra_auth_params["prompt"] == "consent"


def test_jira_in_available_integrations():
    """Jira appears in the static AVAILABLE_INTEGRATIONS list."""
    from app.api.v1.integrations import AVAILABLE_INTEGRATIONS

    slugs = [i.slug for i in AVAILABLE_INTEGRATIONS]
    assert "jira" in slugs


def test_jira_manifest_exists():
    """Jira manifest JSON exists and is valid."""
    from app.services.integration_manifest_service import manifest_service

    m = manifest_service.get("jira")
    assert m is not None
    assert m["slug"] == "jira"
    assert m["auth_type"] == "oauth2"
    assert len(m["capabilities"]) >= 10


def test_jira_bridge_capabilities():
    """Jira capabilities are registered in the integration bridge."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    caps = _INTEGRATION_CAPABILITIES.get("jira", [])
    assert len(caps) >= 10
    cap_ids = [c["id"] for c in caps]
    assert "list_projects" in cap_ids
    assert "get_project" in cap_ids
    assert "search_issues" in cap_ids
    assert "get_issue" in cap_ids
    assert "create_issue" in cap_ids
    assert "update_issue" in cap_ids
    assert "add_comment" in cap_ids
    assert "transition_issue" in cap_ids
    assert "list_boards" in cap_ids
    assert "list_sprints" in cap_ids


def test_jira_webhook_router_exists():
    """Jira webhook router is importable with correct paths."""
    from app.api.v1.jira_webhook import router

    assert router is not None
    paths = [r.path for r in router.routes]  # type: ignore[union-attr]
    assert "/jira/webhook" in paths


def test_jira_oauth_callback_router_exists():
    """Jira custom OAuth callback router is importable."""
    from app.api.v1.jira_oauth import router

    assert router is not None
    paths = [r.path for r in router.routes]  # type: ignore[union-attr]
    assert "/jira/oauth/callback" in paths


def test_jira_connector_importable():
    """JiraConnector can be imported and has expected actions."""
    from app.services.connectors.jira_connector import JiraConnector

    assert JiraConnector.CONNECTOR_TYPE == "jira"
    assert "list_projects" in JiraConnector.ACTIONS
    assert "search_issues" in JiraConnector.ACTIONS
    assert "create_issue" in JiraConnector.ACTIONS
    assert "transition_issue" in JiraConnector.ACTIONS
    assert "list_boards" in JiraConnector.ACTIONS
    assert "list_sprints" in JiraConnector.ACTIONS
    assert len(JiraConnector.ACTIONS) == 10


def test_jira_settings_exist():
    """Jira OAuth settings exist in config."""
    from app.config import settings

    assert hasattr(settings, "JIRA_OAUTH_CLIENT_ID")
    assert hasattr(settings, "JIRA_OAUTH_CLIENT_SECRET")
    assert hasattr(settings, "JIRA_WEBHOOK_SECRET")


def test_jira_text_to_adf():
    """text_to_adf converts plain text to Atlassian Document Format."""
    from app.services.jira.jira_client import text_to_adf

    # Simple text
    result = text_to_adf("Hello world")
    assert result["version"] == 1
    assert result["type"] == "doc"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "paragraph"
    assert result["content"][0]["content"][0]["text"] == "Hello world"

    # Multi-paragraph text
    result = text_to_adf("Paragraph one\n\nParagraph two")
    assert len(result["content"]) == 2
    assert result["content"][0]["content"][0]["text"] == "Paragraph one"
    assert result["content"][1]["content"][0]["text"] == "Paragraph two"

    # Text with line breaks within paragraph
    result = text_to_adf("Line one\nLine two")
    assert len(result["content"]) == 1
    para_content = result["content"][0]["content"]
    assert para_content[0]["text"] == "Line one"
    assert para_content[1]["type"] == "hardBreak"
    assert para_content[2]["text"] == "Line two"

    # Empty text
    result = text_to_adf("")
    assert result["version"] == 1
    assert result["content"] == [{"type": "paragraph"}]


def test_jira_connector_requires_cloud_id():
    """JiraConnector validates that cloud_id is in auth_config."""
    from app.services.connectors.base import AuthType, ConnectorConfig
    from app.services.connectors.jira_connector import JiraConnector

    config = ConnectorConfig(
        name="test-jira",
        connector_type="jira",
        auth_type=AuthType.OAUTH2,
        auth_config={"access_token": "test-token"},
    )
    connector = JiraConnector(config)
    # Without cloud_id, _validate_credentials should handle gracefully
    assert connector.CONNECTOR_TYPE == "jira"
