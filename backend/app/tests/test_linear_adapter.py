"""Tests for the Linear adapter — all 4 GraphQL actions + response parser."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.adapters.linear import (
    LinearAdapter,
    _linear_error_code,
    _parse_linear_response,
    _unwrap_mutation,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _json_response(status=200, data=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = data or {}
    return resp


# ── Response parser ───────────────────────────────────────────────────────────


class TestParseLinearResponse:
    def test_success(self):
        resp = _json_response(200, {"data": {"issues": {"nodes": []}}})
        result = _parse_linear_response(resp)
        assert result["success"] is True
        assert result["response"]["issues"]["nodes"] == []

    def test_graphql_error(self):
        resp = _json_response(
            200,
            {
                "errors": [
                    {
                        "message": "Could not find team",
                        "extensions": {"code": "not_found"},
                    }
                ]
            },
        )
        result = _parse_linear_response(resp)
        assert result["success"] is False
        assert "Could not find team" in result["error"]
        assert result["error_code"] == "not_found"

    def test_auth_error(self):
        resp = _json_response(
            200, {"errors": [{"message": "Authentication required", "extensions": {}}]}
        )
        result = _parse_linear_response(resp)
        assert result["success"] is False
        assert result["error"] == "token_expired"

    def test_http_error(self):
        resp = _json_response(500, {"message": "Internal server error"})
        result = _parse_linear_response(resp)
        assert result["success"] is False
        assert "Internal server error" in result["error"]
        assert result["error_code"] == "http_500"

    def test_http_401(self):
        resp = _json_response(401, {"message": "Unauthorized"})
        result = _parse_linear_response(resp)
        assert result["success"] is False
        assert result["error"] == "token_expired"

    def test_non_json(self):
        resp = MagicMock()
        resp.status_code = 502
        resp.json.side_effect = ValueError("not json")
        result = _parse_linear_response(resp)
        assert result["success"] is False
        assert "non-JSON" in result["error"]


class TestUnwrapMutation:
    def test_success(self):
        result = {
            "success": True,
            "response": {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "i1",
                        "identifier": "TEAM-1",
                        "url": "https://linear.app/issue/TEAM-1",
                    },
                }
            },
        }
        unwrapped = _unwrap_mutation(result, "issueCreate")
        assert unwrapped["success"] is True
        assert unwrapped["response"]["identifier"] == "TEAM-1"

    def test_mutation_failed(self):
        result = {
            "success": True,
            "response": {"issueCreate": {"success": False}},
        }
        unwrapped = _unwrap_mutation(result, "issueCreate")
        assert unwrapped["success"] is False
        assert "mutation failed" in unwrapped["error"]

    def test_parent_failure_passthrough(self):
        result = {"success": False, "error": "Something broke"}
        unwrapped = _unwrap_mutation(result, "issueCreate")
        assert unwrapped["success"] is False
        assert unwrapped["error"] == "Something broke"


class TestLinearErrorCode:
    def test_known(self):
        assert _linear_error_code("not_found", "") == "not_found"
        assert _linear_error_code("notFound", "") == "not_found"
        assert _linear_error_code("validation_error", "") == "validation_error"
        assert _linear_error_code("ValidationError", "") == "validation_error"
        assert _linear_error_code("rate_limited", "") == "rate_limited"
        assert _linear_error_code("feature_not_available", "") == "feature_unavailable"

    def test_unknown_passthrough(self):
        assert _linear_error_code("custom_code", "") == "custom_code"


# ── Adapter instantiation ─────────────────────────────────────────────────────


class TestAdapterBasics:
    def test_provider(self):
        adapter = LinearAdapter()
        assert adapter.provider == "linear"

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        adapter = LinearAdapter()
        result = await adapter._execute_action("bogus", {}, "token")
        assert result["success"] is False
        assert "Unknown" in result["error"]


# ── create_issue ──────────────────────────────────────────────────────────────


class TestCreateIssue:
    @pytest.mark.asyncio
    async def test_success(self):
        adapter = LinearAdapter()
        resp = _json_response(
            200,
            {
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": "abc-123",
                            "identifier": "TEAM-42",
                            "title": "Fix login bug",
                            "url": "https://linear.app/issue/TEAM-42",
                            "priority": 2,
                            "state": {"id": "state-1", "name": "Todo"},
                        },
                    }
                }
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=resp)
            result = await adapter._create_issue(
                {"team_id": "team-1", "title": "Fix login bug", "priority": 2},
                "lin_api_key",
            )

        assert result["success"] is True
        assert result["response"]["identifier"] == "TEAM-42"
        assert result["response"]["id"] == "abc-123"

    @pytest.mark.asyncio
    async def test_missing_team_id(self):
        adapter = LinearAdapter()
        result = await adapter._create_issue({"title": "Bug"}, "key")
        assert result["success"] is False
        assert "team_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_title(self):
        adapter = LinearAdapter()
        result = await adapter._create_issue({"team_id": "t1"}, "key")
        assert result["success"] is False
        assert "title" in result["error"]

    @pytest.mark.asyncio
    async def test_with_description_and_assignee(self):
        adapter = LinearAdapter()
        resp = _json_response(
            200,
            {
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": "i2",
                            "identifier": "T-2",
                            "url": "https://linear.app/issue/T-2",
                        },
                    }
                }
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=resp)
            result = await adapter._create_issue(
                {
                    "team_id": "t1",
                    "title": "Feature",
                    "description": "A new feature",
                    "assignee_id": "user-1",
                },
                "key",
            )

        # Verify assigneeId was passed
        call_args = ctx.post.call_args[1]["json"]
        assert call_args["variables"]["assigneeId"] == "user-1"
        assert call_args["variables"]["description"] == "A new feature"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_none_values_stripped(self):
        adapter = LinearAdapter()
        resp = _json_response(
            200,
            {
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": "i3",
                            "identifier": "T-3",
                            "url": "https://linear.app/issue/T-3",
                        },
                    }
                }
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=resp)
            await adapter._create_issue(
                {
                    "team_id": "t1",
                    "title": "Task",
                    "priority": None,
                    "assignee_id": None,
                    "description": None,
                },
                "key",
            )

        call_args = ctx.post.call_args[1]["json"]
        # priority, assigneeId, description should not be in variables
        assert "priority" not in call_args["variables"]


# ── update_issue ──────────────────────────────────────────────────────────────


class TestUpdateIssue:
    @pytest.mark.asyncio
    async def test_success(self):
        adapter = LinearAdapter()
        resp = _json_response(
            200,
            {
                "data": {
                    "issueUpdate": {
                        "success": True,
                        "issue": {
                            "id": "abc-123",
                            "identifier": "TEAM-42",
                            "title": "Updated title",
                            "url": "https://linear.app/issue/TEAM-42",
                            "priority": 1,
                            "state": {"id": "done", "name": "Done"},
                        },
                    }
                }
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=resp)
            result = await adapter._update_issue(
                {"issue_id": "abc-123", "title": "Updated title", "status": "done"},
                "key",
            )

        assert result["success"] is True
        assert result["response"]["title"] == "Updated title"

    @pytest.mark.asyncio
    async def test_missing_issue_id(self):
        adapter = LinearAdapter()
        result = await adapter._update_issue({}, "key")
        assert result["success"] is False
        assert "issue_id" in result["error"]

    @pytest.mark.asyncio
    async def test_no_updatable_fields(self):
        adapter = LinearAdapter()
        result = await adapter._update_issue({"issue_id": "abc"}, "key")
        assert result["success"] is False
        assert "updatable field" in result["error"]

    @pytest.mark.asyncio
    async def test_update_priority(self):
        adapter = LinearAdapter()
        resp = _json_response(
            200,
            {
                "data": {
                    "issueUpdate": {
                        "success": True,
                        "issue": {
                            "id": "abc",
                            "identifier": "T-1",
                            "url": "https://linear.app/issue/T-1",
                            "priority": 1,
                        },
                    }
                }
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=resp)
            result = await adapter._update_issue(
                {"issue_id": "abc", "priority": 1},
                "key",
            )

        assert result["success"] is True
        call_args = ctx.post.call_args[1]["json"]
        assert call_args["variables"]["priority"] == 1


# ── search_issues ─────────────────────────────────────────────────────────────


class TestSearchIssues:
    @pytest.mark.asyncio
    async def test_success(self):
        adapter = LinearAdapter()
        resp = _json_response(
            200,
            {
                "data": {
                    "issueSearch": {
                        "nodes": [
                            {
                                "id": "i1",
                                "identifier": "TEAM-1",
                                "title": "Login fails",
                                "url": "https://linear.app/issue/TEAM-1",
                                "state": {"id": "s1", "name": "Todo"},
                                "team": {"id": "t1", "name": "Engineering"},
                            }
                        ]
                    }
                }
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=resp)
            result = await adapter._search_issues({"query": "login"}, "key")

        assert result["success"] is True
        assert result["response"]["issueSearch"]["nodes"][0]["identifier"] == "TEAM-1"

    @pytest.mark.asyncio
    async def test_missing_query(self):
        adapter = LinearAdapter()
        result = await adapter._search_issues({}, "key")
        assert result["success"] is False
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_limit_capped(self):
        adapter = LinearAdapter()
        resp = _json_response(200, {"data": {"issueSearch": {"nodes": []}}})

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=resp)
            await adapter._search_issues({"query": "bug", "limit": 99}, "key")

        call_args = ctx.post.call_args[1]["json"]
        assert call_args["variables"]["limit"] == 50  # capped


# ── list_projects ─────────────────────────────────────────────────────────────


class TestListProjects:
    @pytest.mark.asyncio
    async def test_success(self):
        adapter = LinearAdapter()
        resp = _json_response(
            200,
            {
                "data": {
                    "projects": {
                        "nodes": [
                            {
                                "id": "p1",
                                "name": "Q4 Platform",
                                "description": "Platform work",
                                "url": "https://linear.app/project/Q4-Platform",
                                "state": "started",
                                "progress": 0.45,
                                "team": {"id": "t1", "name": "Engineering"},
                            }
                        ]
                    }
                }
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=resp)
            result = await adapter._list_projects({}, "key")

        assert result["success"] is True
        assert result["response"]["projects"]["nodes"][0]["name"] == "Q4 Platform"

    @pytest.mark.asyncio
    async def test_with_team_id(self):
        adapter = LinearAdapter()
        resp = _json_response(200, {"data": {"projects": {"nodes": []}}})

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=resp)
            await adapter._list_projects({"team_id": "team-eng", "limit": 10}, "key")

        call_args = ctx.post.call_args[1]["json"]
        assert call_args["variables"]["teamId"] == "team-eng"
        assert call_args["variables"]["limit"] == 10

    @pytest.mark.asyncio
    async def test_limit_capped(self):
        adapter = LinearAdapter()
        resp = _json_response(200, {"data": {"projects": {"nodes": []}}})

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=resp)
            await adapter._list_projects({"limit": 99}, "key")

        call_args = ctx.post.call_args[1]["json"]
        assert call_args["variables"]["limit"] == 50


# ── Auth header test ──────────────────────────────────────────────────────────


class TestAuthHeader:
    @pytest.mark.asyncio
    async def test_linear_uses_plain_token_not_bearer(self):
        """Linear uses Authorization: <token> (no Bearer prefix)."""
        adapter = LinearAdapter()
        resp = _json_response(200, {"data": {"projects": {"nodes": []}}})

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=resp)
            await adapter._list_projects({}, "lin_api_abc123")

        call_headers = ctx.post.call_args[1]["headers"]
        assert call_headers["Authorization"] == "lin_api_abc123"
        assert "Bearer" not in call_headers["Authorization"]
