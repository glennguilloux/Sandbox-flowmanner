"""Tests for the GitHub integration adapter (all 4 actions with mocked httpx)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.adapters.github import (
    GitHubAdapter,
    _github_error_code,
    _parse_github_response,
)


@pytest.fixture
def adapter():
    return GitHubAdapter()


@pytest.fixture
def connection():
    """Mock UserOAuthConnection that returns a fake access token."""
    conn = MagicMock()
    conn.provider = "github"
    conn.get_access_token.return_value = "ghp_test-token"
    conn.get_refresh_token.return_value = None
    return conn


# ── Response parser tests ─────────────────────────────────────────────────────


class TestGitHubResponseParser:
    def test_success_201(self):
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {
            "number": 42,
            "html_url": "https://github.com/owner/repo/issues/42",
        }
        result = _parse_github_response(resp)
        assert result["success"] is True
        assert result["response"]["number"] == 42

    def test_success_200(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"total_count": 5, "items": []}
        result = _parse_github_response(resp)
        assert result["success"] is True

    def test_404_not_found(self):
        resp = MagicMock()
        resp.status_code = 404
        resp.json.return_value = {"message": "Not Found"}
        result = _parse_github_response(resp)
        assert result["success"] is False
        assert result["error_code"] == "not_found"

    def test_401_token_expired(self):
        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {"message": "Bad credentials"}
        result = _parse_github_response(resp)
        assert result["success"] is False
        assert result["error"] == "token_expired"

    def test_422_validation_failed(self):
        resp = MagicMock()
        resp.status_code = 422
        resp.json.return_value = {"message": "Validation Failed", "errors": []}
        result = _parse_github_response(resp)
        assert result["success"] is False
        assert result["error_code"] == "validation_failed"

    def test_non_json_response(self):
        resp = MagicMock()
        resp.status_code = 502
        resp.json.side_effect = ValueError("not json")
        result = _parse_github_response(resp)
        assert result["success"] is False
        assert "non-JSON" in result["error"]


class TestGitHubErrorCodes:
    def test_known_errors(self):
        assert _github_error_code(404, "Not Found") == "not_found"
        assert _github_error_code(401, "Bad credentials") == "bad_credentials"
        assert _github_error_code(422, "Validation Failed") == "validation_failed"

    def test_unknown_error(self):
        assert _github_error_code(403, "Something else") == "http_403"


# ── GitHubAdapter basic tests ─────────────────────────────────────────────────


class TestGitHubAdapter:
    @pytest.mark.asyncio
    async def test_provider_mismatch(self, adapter, connection):
        connection.provider = "slack"
        result = await adapter.execute("create_issue", {}, connection)
        assert result["success"] is False
        assert "Provider mismatch" in result["error"]

    @pytest.mark.asyncio
    async def test_no_access_token(self, adapter, connection):
        connection.get_access_token.return_value = ""
        result = await adapter.execute("create_issue", {}, connection)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_unknown_action(self, adapter, connection):
        result = await adapter.execute("unknown_action", {}, connection)
        assert result["success"] is False
        assert "Unknown GitHub action" in result["error"]


# ── Action: create_issue ──────────────────────────────────────────────────────


class TestCreateIssue:
    @pytest.mark.asyncio
    async def test_success(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "number": 42,
            "title": "Bug found",
            "html_url": "https://github.com/user/repo/issues/42",
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "create_issue",
                {"owner": "user", "repo": "my-repo", "title": "Bug found"},
                connection,
            )

        assert result["success"] is True
        assert result["response"]["number"] == 42
        assert (
            result["response"]["html_url"] == "https://github.com/user/repo/issues/42"
        )

    @pytest.mark.asyncio
    async def test_missing_owner(self, adapter, connection):
        result = await adapter.execute(
            "create_issue", {"repo": "r", "title": "t"}, connection
        )
        assert result["success"] is False
        assert "owner" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_repo(self, adapter, connection):
        result = await adapter.execute(
            "create_issue", {"owner": "o", "title": "t"}, connection
        )
        assert result["success"] is False
        assert "repo" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_title(self, adapter, connection):
        result = await adapter.execute(
            "create_issue", {"owner": "o", "repo": "r"}, connection
        )
        assert result["success"] is False
        assert "title" in result["error"]

    @pytest.mark.asyncio
    async def test_with_labels_and_body(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"number": 1}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await adapter.execute(
                "create_issue",
                {
                    "owner": "user",
                    "repo": "repo",
                    "title": "Bug",
                    "body": "Description",
                    "labels": ["bug", "high-priority"],
                },
                connection,
            )

        call_args = mock_post.call_args
        body = call_args[1]["json"]
        assert body["body"] == "Description"
        assert body["labels"] == ["bug", "high-priority"]

    @pytest.mark.asyncio
    async def test_api_error_handled(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"message": "Not Found"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "create_issue",
                {"owner": "user", "repo": "nonexistent", "title": "Bug"},
                connection,
            )

        assert result["success"] is False
        assert result["error_code"] == "not_found"


# ── Action: create_pr ─────────────────────────────────────────────────────────


class TestCreatePR:
    @pytest.mark.asyncio
    async def test_success(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "number": 5,
            "title": "Add feature",
            "html_url": "https://github.com/user/repo/pull/5",
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "create_pr",
                {
                    "owner": "user",
                    "repo": "repo",
                    "title": "Add feature",
                    "head": "feature-branch",
                    "base": "main",
                },
                connection,
            )

        assert result["success"] is True
        assert result["response"]["number"] == 5

    @pytest.mark.asyncio
    async def test_missing_head(self, adapter, connection):
        result = await adapter.execute(
            "create_pr",
            {"owner": "o", "repo": "r", "title": "t", "base": "main"},
            connection,
        )
        assert result["success"] is False
        assert "head" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_base(self, adapter, connection):
        result = await adapter.execute(
            "create_pr",
            {"owner": "o", "repo": "r", "title": "t", "head": "feature"},
            connection,
        )
        assert result["success"] is False
        assert "base" in result["error"]

    @pytest.mark.asyncio
    async def test_with_body(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"number": 1}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await adapter.execute(
                "create_pr",
                {
                    "owner": "user",
                    "repo": "repo",
                    "title": "PR",
                    "head": "feature",
                    "base": "main",
                    "body": "Description of changes",
                },
                connection,
            )

        body = mock_post.call_args[1]["json"]
        assert body["body"] == "Description of changes"

    @pytest.mark.asyncio
    async def test_merge_conflict_error(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.json.return_value = {"message": "Merge conflict"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "create_pr",
                {
                    "owner": "user",
                    "repo": "repo",
                    "title": "PR",
                    "head": "conflicting",
                    "base": "main",
                },
                connection,
            )

        assert result["success"] is False
        assert result["error_code"] == "merge_conflict"


# ── Action: search_repos ──────────────────────────────────────────────────────


class TestSearchRepos:
    @pytest.mark.asyncio
    async def test_success(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "total_count": 2,
            "items": [
                {"full_name": "user/repo1", "stargazers_count": 10},
                {"full_name": "user/repo2", "stargazers_count": 5},
            ],
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            result = await adapter.execute(
                "search_repos",
                {"query": "machine learning"},
                connection,
            )

        assert result["success"] is True
        assert result["response"]["total_count"] == 2

    @pytest.mark.asyncio
    async def test_missing_query(self, adapter, connection):
        result = await adapter.execute("search_repos", {}, connection)
        assert result["success"] is False
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_with_sort(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total_count": 0, "items": []}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            await adapter.execute(
                "search_repos",
                {"query": "test", "sort": "stars"},
                connection,
            )

        assert mock_get.call_args[1]["params"]["sort"] == "stars"

    @pytest.mark.asyncio
    async def test_invalid_sort_ignored(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total_count": 0, "items": []}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            await adapter.execute(
                "search_repos",
                {"query": "test", "sort": "invalid"},
                connection,
            )

        assert "sort" not in mock_get.call_args[1]["params"]

    @pytest.mark.asyncio
    async def test_limit_capped_at_100(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total_count": 0, "items": []}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            await adapter.execute(
                "search_repos",
                {"query": "test", "limit": 500},
                connection,
            )

        assert mock_get.call_args[1]["params"]["per_page"] == 100


# ── Action: get_file_contents ─────────────────────────────────────────────────


class TestGetFileContents:
    @pytest.mark.asyncio
    async def test_success(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "name": "README.md",
            "path": "README.md",
            "content": "SGVsbG8gV29ybGQ=",  # base64 "Hello World"
            "encoding": "base64",
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            result = await adapter.execute(
                "get_file_contents",
                {"owner": "user", "repo": "repo", "path": "README.md"},
                connection,
            )

        assert result["success"] is True
        assert result["response"]["name"] == "README.md"
        assert result["response"]["encoding"] == "base64"

    @pytest.mark.asyncio
    async def test_missing_path(self, adapter, connection):
        result = await adapter.execute(
            "get_file_contents", {"owner": "o", "repo": "r"}, connection
        )
        assert result["success"] is False
        assert "path" in result["error"]

    @pytest.mark.asyncio
    async def test_with_ref(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"name": "file.txt", "content": "YQ=="}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            await adapter.execute(
                "get_file_contents",
                {"owner": "user", "repo": "repo", "path": "file.txt", "ref": "v1.0"},
                connection,
            )

        assert mock_get.call_args[1]["params"]["ref"] == "v1.0"

    @pytest.mark.asyncio
    async def test_file_not_found(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"message": "Not Found"}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            result = await adapter.execute(
                "get_file_contents",
                {"owner": "user", "repo": "repo", "path": "missing.txt"},
                connection,
            )

        assert result["success"] is False
        assert result["error_code"] == "not_found"
