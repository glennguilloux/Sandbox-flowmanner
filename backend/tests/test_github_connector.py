"""
Unit tests for GitHubConnector.

Tests the 18 actions (issues, PRs, repos, search, comments, user) using
mocked aiohttp HTTP responses since BaseConnector uses aiohttp internally.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientResponse

from app.services.connectors.base import (
    AuthType,
    ConnectorConfig,
    ConnectorResponse,
)
from app.services.connectors.github_connector import GitHubConnector

# ── Helpers ────────────────────────────────────────────────────────────


def _make_mock_response(status: int, body: dict | str, headers: dict | None = None):
    """Create a mock aiohttp ClientResponse."""
    resp = MagicMock(spec=ClientResponse)
    resp.status = status
    resp.headers = headers or {}
    resp.ok = 200 <= status < 300

    async def _json():
        if isinstance(body, (dict, list)):
            return body
        return json.loads(body)

    async def _text():
        return body if isinstance(body, str) else json.dumps(body)

    resp.json = _json
    resp.text = _text
    return resp


class _FakeSession:
    """Fake aiohttp.ClientSession that returns controlled responses."""

    def __init__(self, response_map: dict[str, MagicMock] | None = None):
        self._response_map = response_map or {}
        self._last_request = None
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def request(self, method: str, url: str, **kwargs):
        self._last_request = (method, url, kwargs)
        key = f"{method}:{url}"
        resp = self._response_map.get(key, self._response_map.get("default"))
        if resp is None:
            resp = _make_mock_response(404, {"message": "Not Found"})

        class _Ctx:
            async def __aenter__(self):
                return resp

            async def __aexit__(self, *args):
                pass

        return _Ctx()

    async def close(self):
        self.closed = True


def _make_config(auth_config: dict | None = None) -> ConnectorConfig:
    return ConnectorConfig(
        name="test-github",
        connector_type="github",
        auth_type=AuthType.BEARER_TOKEN,
        auth_config=auth_config or {"token": "ghp_test123"},
    )


# ── Constructor ───────────────────────────────────────────────────────


def test_constructor_defaults():
    """Verify default config values are set correctly."""
    config = _make_config()
    connector = GitHubConnector(config)

    assert connector.connector_type == "github"
    assert "create_issue" in connector.available_actions
    assert "merge_pr" in connector.available_actions
    assert "search_code" in connector.available_actions


def test_available_actions_count():
    connector = GitHubConnector(_make_config())
    assert len(connector.available_actions) == 18


@pytest.mark.asyncio
async def test_unknown_action_returns_error():
    connector = GitHubConnector(_make_config())
    result = await connector.execute_action("nonexistent_action", {})
    assert result.success is False
    assert result.status_code == 400
    assert "Unknown action" in (result.error or "")


# ── Issue Actions ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_issue_success():
    """Create an issue on a GitHub repo."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test-user"}),
            "POST:https://api.github.com/repos/owner/repo/issues": _make_mock_response(
                201,
                {"id": 1, "number": 42, "title": "Test Issue", "state": "open"},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action(
            "create_issue",
            {"owner": "owner", "repo": "repo", "title": "Test Issue"},
        )

    assert result.success is True
    assert result.data["number"] == 42
    assert result.data["title"] == "Test Issue"


@pytest.mark.asyncio
async def test_create_issue_missing_params():
    """Missing required params returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"login": "test"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("create_issue", {"owner": "o"})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_list_issues():
    """List issues for a repo."""
    issues = [{"number": 1, "title": "Bug"}, {"number": 2, "title": "Feature"}]
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/repos/owner/repo/issues": _make_mock_response(
                200, issues
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "list_issues", {"owner": "owner", "repo": "repo"}
        )

    assert result.success is True
    assert len(result.data) == 2
    assert result.data[0]["title"] == "Bug"


@pytest.mark.asyncio
async def test_get_issue():
    """Get a specific issue."""
    issue = {"number": 42, "title": "Specific Issue"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/repos/owner/repo/issues/42": _make_mock_response(
                200, issue
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "get_issue", {"owner": "owner", "repo": "repo", "issue_number": 42}
        )

    assert result.success is True
    assert result.data["number"] == 42


@pytest.mark.asyncio
async def test_update_issue():
    """Update an issue's title and body."""
    updated = {"number": 42, "title": "Updated", "body": "New body"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "PATCH:https://api.github.com/repos/owner/repo/issues/42": _make_mock_response(
                200, updated
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "update_issue",
            {
                "owner": "owner",
                "repo": "repo",
                "issue_number": 42,
                "title": "Updated",
                "body": "New body",
            },
        )

    assert result.success is True
    assert result.data["title"] == "Updated"


@pytest.mark.asyncio
async def test_close_issue():
    """Close an issue."""
    closed = {"number": 42, "state": "closed"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "PATCH:https://api.github.com/repos/owner/repo/issues/42": _make_mock_response(
                200, closed
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "close_issue", {"owner": "owner", "repo": "repo", "issue_number": 42}
        )

    assert result.success is True
    assert result.data["state"] == "closed"


# ── PR Actions ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_pr():
    """Create a pull request."""
    pr = {"number": 10, "title": "New PR", "state": "open"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "POST:https://api.github.com/repos/owner/repo/pulls": _make_mock_response(
                201, pr
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "create_pr",
            {
                "owner": "owner",
                "repo": "repo",
                "title": "New PR",
                "head": "feature",
                "base": "main",
            },
        )

    assert result.success is True
    assert result.data["number"] == 10


@pytest.mark.asyncio
async def test_list_prs():
    """List pull requests."""
    prs = [{"number": 1}, {"number": 2}]
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/repos/owner/repo/pulls": _make_mock_response(
                200, prs
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "list_prs", {"owner": "owner", "repo": "repo"}
        )

    assert result.success is True
    assert len(result.data) == 2


@pytest.mark.asyncio
async def test_get_pr():
    """Get a specific PR."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/repos/owner/repo/pulls/5": _make_mock_response(
                200, {"number": 5, "title": "PR #5"}
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "get_pr", {"owner": "owner", "repo": "repo", "pr_number": 5}
        )

    assert result.success is True
    assert result.data["number"] == 5


@pytest.mark.asyncio
async def test_merge_pr():
    """Merge a pull request."""
    merged = {"merged": True, "message": "Pull Request successfully merged"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "PUT:https://api.github.com/repos/owner/repo/pulls/5/merge": _make_mock_response(
                200, merged
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "merge_pr",
            {
                "owner": "owner",
                "repo": "repo",
                "pr_number": 5,
                "merge_method": "squash",
            },
        )

    assert result.success is True
    assert result.data["merged"] is True


# ── Repository Actions ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_repo():
    """Get repository details."""
    repo = {"name": "repo", "full_name": "owner/repo", "stars": 100}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/repos/owner/repo": _make_mock_response(
                200, repo
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "get_repo", {"owner": "owner", "repo": "repo"}
        )

    assert result.success is True
    assert result.data["full_name"] == "owner/repo"


@pytest.mark.asyncio
async def test_list_repos():
    """List authenticated user's repos."""
    repos = [{"name": "repo1"}, {"name": "repo2"}]
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/user/repos": _make_mock_response(200, repos),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("list_repos", {})

    assert result.success is True
    assert len(result.data) == 2


@pytest.mark.asyncio
async def test_list_user_repos():
    """List a specific user's repos."""
    repos = [{"name": "proj"}]
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/users/otheruser/repos": _make_mock_response(
                200, repos
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "list_user_repos", {"username": "otheruser"}
        )

    assert result.success is True
    assert result.data[0]["name"] == "proj"


# ── Search Actions ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_code():
    """Search code across GitHub."""
    results = {"total_count": 1, "items": [{"name": "main.py"}]}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/search/code": _make_mock_response(200, results),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "search_code", {"q": "import requests language:python"}
        )

    assert result.success is True
    assert result.data["total_count"] == 1


@pytest.mark.asyncio
async def test_search_code_missing_query():
    """Search code with missing query returns error."""
    fake = _FakeSession({"default": _make_mock_response(200, {"login": "test"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("search_code", {})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_search_repos():
    """Search repositories."""
    results = {"total_count": 5, "items": [{"full_name": "a/b"}]}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/search/repositories": _make_mock_response(
                200, results
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "search_repos", {"q": "machine learning"}
        )

    assert result.success is True
    assert result.data["total_count"] == 5


# ── User Actions ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_user_authenticated():
    """Get the authenticated user's profile."""
    user = {"login": "test-user", "name": "Test User"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/user": _make_mock_response(200, user),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_user", {})

    assert result.success is True
    assert connector._authenticated_user == "test-user"


@pytest.mark.asyncio
async def test_get_user_specific():
    """Get a specific user's profile."""
    user = {"login": "torvalds", "name": "Linus Torvalds"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/users/torvalds": _make_mock_response(200, user),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_user", {"username": "torvalds"})

    assert result.success is True
    assert result.data["login"] == "torvalds"


# ── File Content Actions ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_file_contents():
    """Get file contents from a repo."""
    import base64

    content = base64.b64encode(b"print('hello')").decode()
    file_data = {"name": "main.py", "content": content, "encoding": "base64"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/repos/owner/repo/contents/main.py": _make_mock_response(
                200, file_data
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "get_file_contents",
            {"owner": "owner", "repo": "repo", "path": "main.py"},
        )

    assert result.success is True
    assert result.data["name"] == "main.py"


# ── Comment Actions ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_comment():
    """Create a comment on an issue."""
    comment = {"id": 999, "body": "Nice work!"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "POST:https://api.github.com/repos/owner/repo/issues/42/comments": _make_mock_response(
                201, comment
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "create_comment",
            {
                "owner": "owner",
                "repo": "repo",
                "issue_number": 42,
                "body": "Nice work!",
            },
        )

    assert result.success is True
    assert result.data["body"] == "Nice work!"


@pytest.mark.asyncio
async def test_list_comments():
    """List comments on an issue."""
    comments = [{"id": 1, "body": "First!"}, {"id": 2, "body": "Second"}]
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"login": "test"}),
            "GET:https://api.github.com/repos/owner/repo/issues/42/comments": _make_mock_response(
                200, comments
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "list_comments",
            {"owner": "owner", "repo": "repo", "issue_number": 42},
        )

    assert result.success is True
    assert len(result.data) == 2


# ── Auth Failure ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_connect_with_invalid_token():
    """Connector connect() fails with 401."""
    fake = _FakeSession(
        {
            "GET:https://api.github.com/user": _make_mock_response(
                401, {"message": "Bad credentials"}
            )
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = GitHubConnector(_make_config())
        ok = await connector.connect()

    assert ok is False


# ── get_stats ─────────────────────────────────────────────────────────


def test_get_stats():
    """get_stats returns connector info."""
    connector = GitHubConnector(_make_config())
    stats = connector.get_stats()

    assert stats["name"] == "test-github"
    assert stats["type"] == "github"
    assert "authenticated_user" in stats
