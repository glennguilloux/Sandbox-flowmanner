"""
Unit tests for LinearConnector.

Tests the 7 Linear actions (issues, comments, teams) by mocking
the underlying LinearClient GraphQL calls, plus credential validation and stats.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.connectors.base import (
    AuthType,
    ConnectorConfig,
    ConnectorResponse,
)
from app.services.connectors.linear_connector import LinearConnector

# ── Helpers ────────────────────────────────────────────────────────────


def _make_config(auth_config: dict | None = None) -> ConnectorConfig:
    # Note: LinearConnector.__init__ only copies `settings.LINEAR_API_KEY` into
    # auth_config['key_value'] when auth_config['api_key'] is unset. Set both
    # keys so the test is hermetic in CI (where settings.LINEAR_API_KEY is not
    # exported) — the connector's _validate_credentials reads `key_value` (or
    # falls back to settings.LINEAR_API_KEY).
    base_auth = {"api_key": "lin_api_test123", "key_value": "lin_api_test123"}
    if auth_config:
        base_auth.update(auth_config)
    return ConnectorConfig(
        name="test-linear",
        connector_type="linear",
        auth_type=AuthType.API_KEY,
        auth_config=base_auth,
    )


def _make_mock_linear_client():
    """Create a mock LinearClient with standard method returns."""
    client = AsyncMock()
    client.get_teams.return_value = [{"id": "team1", "name": "Engineering", "key": "ENG"}]
    client.get_default_team_id.return_value = "team1"
    client.create_issue.return_value = {
        "id": "issue1",
        "title": "Test Issue",
        "identifier": "ENG-1",
        "url": "https://linear.app/issue/ENG-1",
        "state": {"id": "s1", "name": "Todo"},
        "team": {"id": "team1", "name": "Engineering"},
    }
    client.update_issue.return_value = {
        "id": "issue1",
        "title": "Updated Title",
        "identifier": "ENG-1",
        "url": "https://linear.app/issue/ENG-1",
        "state": {"id": "s2", "name": "In Progress"},
    }
    client.get_issue.return_value = {
        "id": "issue1",
        "title": "Existing Issue",
        "identifier": "ENG-1",
        "url": "https://linear.app/issue/ENG-1",
        "state": {"id": "s1", "name": "Todo"},
        "priority": 2,
        "assignee": {"id": "u1", "name": "Alice"},
    }
    client.get_issue_by_identifier.return_value = {
        "id": "issue1",
        "title": "Found Issue",
        "identifier": "ENG-1",
        "url": "https://linear.app/issue/ENG-1",
    }
    client.add_comment.return_value = {
        "id": "comment1",
        "body": "Looks good!",
        "createdAt": "2026-06-01T10:00:00Z",
    }
    client._execute = AsyncMock(
        return_value={
            "team": {
                "issues": {
                    "nodes": [
                        {"id": "i1", "title": "Bug fix", "identifier": "ENG-1"},
                        {"id": "i2", "title": "Feature", "identifier": "ENG-2"},
                    ]
                }
            }
        }
    )
    return client


# ── Constructor ───────────────────────────────────────────────────────


def test_constructor_defaults():
    """Verify default config values are set correctly."""
    config = _make_config()
    connector = LinearConnector(config)

    assert connector.connector_type == "linear"
    assert "create_issue" in connector.available_actions
    assert "add_comment" in connector.available_actions
    assert "list_teams" in connector.available_actions


def test_available_actions_count():
    connector = LinearConnector(_make_config())
    assert len(connector.available_actions) == 12


@pytest.mark.asyncio
async def test_unknown_action_returns_error():
    connector = LinearConnector(_make_config())
    result = await connector.execute_action("nonexistent_action", {})
    assert result.success is False
    assert result.status_code == 400


# ── Credential Validation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_credentials_success():
    """connect() succeeds when Linear teams are reachable."""
    mock_client = _make_mock_linear_client()

    with patch(
        "app.services.linear.client.LinearClient",
        return_value=mock_client,
    ):
        connector = LinearConnector(_make_config())
        ok = await connector.connect()

    assert ok is True
    assert connector._authenticated_team == "Engineering"


@pytest.mark.asyncio
async def test_validate_credentials_no_api_key():
    """connect() returns False when no API key is configured."""
    with patch("app.services.connectors.linear_connector.settings") as mock_settings:
        mock_settings.LINEAR_API_KEY = ""
        config = ConnectorConfig(
            name="test-linear",
            connector_type="linear",
            auth_type=AuthType.API_KEY,
            auth_config={},
        )
        connector = LinearConnector(config)
        ok = await connector.connect()

    assert ok is False


@pytest.mark.asyncio
async def test_validate_credentials_empty_teams():
    """connect() returns False when no teams are returned."""
    mock_client = AsyncMock()
    mock_client.get_teams.return_value = []

    with patch(
        "app.services.linear.client.LinearClient",
        return_value=mock_client,
    ):
        connector = LinearConnector(_make_config())
        ok = await connector.connect()

    assert ok is False


# ── Issues ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_issue():
    """Create a Linear issue."""
    mock_client = _make_mock_linear_client()

    with (
        patch(
            "app.services.linear.client.LinearClient",
            return_value=mock_client,
        ),
        patch("app.services.connectors.linear_connector.settings") as mock_settings,
    ):
        mock_settings.LINEAR_TEAM_ID = "team1"
        mock_settings.LINEAR_API_KEY = "test"

        connector = LinearConnector(_make_config())
        connector._linear_client = mock_client
        result = await connector.execute_action(
            "create_issue",
            {"title": "Test Issue", "description": "A new bug", "priority": 2},
        )

    assert result.success is True
    assert result.data["identifier"] == "ENG-1"
    mock_client.create_issue.assert_called_once()


@pytest.mark.asyncio
async def test_create_issue_missing_title():
    """Create issue with missing title returns 400."""
    connector = LinearConnector(_make_config())
    connector._linear_client = _make_mock_linear_client()

    result = await connector.execute_action("create_issue", {})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_create_issue_missing_team_id():
    """Create issue without team_id returns 400 when LINEAR_TEAM_ID is unset."""
    with patch("app.services.connectors.linear_connector.settings") as mock_settings:
        mock_settings.LINEAR_TEAM_ID = ""

        connector = LinearConnector(_make_config())
        connector._linear_client = _make_mock_linear_client()
        result = await connector.execute_action("create_issue", {"title": "No Team"})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_update_issue():
    """Update a Linear issue."""
    mock_client = _make_mock_linear_client()

    connector = LinearConnector(_make_config())
    connector._linear_client = mock_client
    result = await connector.execute_action(
        "update_issue",
        {"issue_id": "issue1", "title": "Updated Title", "state_id": "s2"},
    )

    assert result.success is True
    assert result.data["title"] == "Updated Title"
    mock_client.update_issue.assert_called_once()


@pytest.mark.asyncio
async def test_update_issue_missing_id():
    """Update issue missing issue_id returns 400."""
    connector = LinearConnector(_make_config())
    connector._linear_client = _make_mock_linear_client()

    result = await connector.execute_action("update_issue", {"title": "New Title"})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_get_issue_by_id():
    """Get a Linear issue by UUID ID."""
    mock_client = _make_mock_linear_client()

    connector = LinearConnector(_make_config())
    connector._linear_client = mock_client
    result = await connector.execute_action("get_issue", {"issue_id": "issue1"})

    assert result.success is True
    assert result.data["title"] == "Existing Issue"
    mock_client.get_issue.assert_called_once_with("issue1")


@pytest.mark.asyncio
async def test_get_issue_by_identifier():
    """Get a Linear issue by TEAM-123 identifier."""
    mock_client = _make_mock_linear_client()

    connector = LinearConnector(_make_config())
    connector._linear_client = mock_client
    result = await connector.execute_action("get_issue", {"identifier": "ENG-1"})

    assert result.success is True
    assert result.data["identifier"] == "ENG-1"
    mock_client.get_issue_by_identifier.assert_called_once_with("ENG-1")


@pytest.mark.asyncio
async def test_get_issue_not_found():
    """Get issue returns 404 when not found."""
    mock_client = _make_mock_linear_client()
    mock_client.get_issue.return_value = None

    connector = LinearConnector(_make_config())
    connector._linear_client = mock_client
    result = await connector.execute_action("get_issue", {"issue_id": "nonexistent"})

    assert result.success is False
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_get_issue_missing_params():
    """Get issue missing both issue_id and identifier returns 400."""
    connector = LinearConnector(_make_config())
    connector._linear_client = _make_mock_linear_client()

    result = await connector.execute_action("get_issue", {})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_list_issues():
    """List issues for a team."""
    mock_client = _make_mock_linear_client()

    with patch("app.services.connectors.linear_connector.settings") as mock_settings:
        mock_settings.LINEAR_TEAM_ID = "team1"

        connector = LinearConnector(_make_config())
        connector._linear_client = mock_client
        result = await connector.execute_action("list_issues", {})

    assert result.success is True
    assert len(result.data["issues"]) == 2


@pytest.mark.asyncio
async def test_list_issues_missing_team_id():
    """List issues missing team_id returns 400."""
    with patch("app.services.connectors.linear_connector.settings") as mock_settings:
        mock_settings.LINEAR_TEAM_ID = ""

        connector = LinearConnector(_make_config())
        connector._linear_client = _make_mock_linear_client()
        result = await connector.execute_action("list_issues", {})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_search_issues_by_identifier():
    """Search issues by exact identifier match."""
    mock_client = _make_mock_linear_client()

    connector = LinearConnector(_make_config())
    connector._linear_client = mock_client
    result = await connector.execute_action("search_issues", {"q": "ENG-1"})

    assert result.success is True
    assert result.data["issues"][0]["identifier"] == "ENG-1"


@pytest.mark.asyncio
async def test_search_issues_no_results():
    """Search with no matches returns empty results."""
    mock_client = _make_mock_linear_client()
    mock_client.get_issue_by_identifier.return_value = None

    connector = LinearConnector(_make_config())
    connector._linear_client = mock_client
    result = await connector.execute_action("search_issues", {"q": "NONEXIST-999"})

    assert result.success is True
    assert len(result.data["issues"]) == 0


@pytest.mark.asyncio
async def test_search_issues_missing_query():
    """Search issues missing query returns 400."""
    connector = LinearConnector(_make_config())
    connector._linear_client = _make_mock_linear_client()

    result = await connector.execute_action("search_issues", {})

    assert result.success is False
    assert result.status_code == 400


# ── Comments ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_comment():
    """Add a comment to a Linear issue."""
    mock_client = _make_mock_linear_client()

    connector = LinearConnector(_make_config())
    connector._linear_client = mock_client
    result = await connector.execute_action(
        "add_comment",
        {"issue_id": "issue1", "body": "Looks good!"},
    )

    assert result.success is True
    assert result.data["id"] == "comment1"
    mock_client.add_comment.assert_called_once_with("issue1", "Looks good!")


@pytest.mark.asyncio
async def test_add_comment_missing_params():
    """Add comment missing required params returns 400."""
    connector = LinearConnector(_make_config())
    connector._linear_client = _make_mock_linear_client()

    result = await connector.execute_action("add_comment", {})

    assert result.success is False
    assert result.status_code == 400


# ── Teams ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_teams():
    """List all Linear teams."""
    mock_client = _make_mock_linear_client()

    connector = LinearConnector(_make_config())
    connector._linear_client = mock_client
    result = await connector.execute_action("list_teams", {})

    assert result.success is True
    assert len(result.data["teams"]) == 1
    assert result.data["teams"][0]["name"] == "Engineering"


# ── get_stats ─────────────────────────────────────────────────────────


def test_get_stats():
    """get_stats returns connector info with authenticated team."""
    connector = LinearConnector(_make_config())
    stats = connector.get_stats()

    assert stats["name"] == "test-linear"
    assert stats["type"] == "linear"
    assert "authenticated_team" in stats
