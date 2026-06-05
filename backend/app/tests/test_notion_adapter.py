"""Tests for the Notion integration adapter (all 3 actions with mocked httpx)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.adapters.notion import (
    NotionAdapter,
    _notion_error_code,
    _parse_notion_response,
)


@pytest.fixture
def adapter():
    return NotionAdapter()


@pytest.fixture
def connection():
    conn = MagicMock()
    conn.provider = "notion"
    conn.get_access_token.return_value = "secret_notion_token"
    conn.get_refresh_token.return_value = None
    return conn


# ── Response parser tests ─────────────────────────────────────────────────────


class TestNotionResponseParser:
    def test_success(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "id": "abc-123",
            "object": "page",
            "url": "https://notion.so/page-123",
        }
        result = _parse_notion_response(resp)
        assert result["success"] is True
        assert result["response"]["id"] == "abc-123"

    def test_validation_error(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {
            "message": "body failed validation",
            "code": "validation_error",
        }
        result = _parse_notion_response(resp)
        assert result["success"] is False
        assert result["error_code"] == "validation_error"

    def test_object_not_found(self):
        resp = MagicMock()
        resp.status_code = 404
        resp.json.return_value = {
            "message": "Could not find database",
            "code": "object_not_found",
        }
        result = _parse_notion_response(resp)
        assert result["success"] is False
        assert result["error_code"] == "object_not_found"

    def test_token_expired(self):
        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {"message": "Unauthorized", "code": "unauthorized"}
        result = _parse_notion_response(resp)
        assert result["success"] is False
        assert result["error"] == "token_expired"

    def test_non_json(self):
        resp = MagicMock()
        resp.status_code = 502
        resp.json.side_effect = ValueError("bad json")
        result = _parse_notion_response(resp)
        assert result["success"] is False
        assert "non-JSON" in result["error"]


class TestNotionErrorCodes:
    def test_known(self):
        assert _notion_error_code("validation_error") == "validation_error"
        assert _notion_error_code("object not found") == "object_not_found"
        assert _notion_error_code("rate limited") == "rate_limited"

    def test_unknown(self):
        assert _notion_error_code("something weird") == "unknown_error"


# ── Basic adapter tests ───────────────────────────────────────────────────────


class TestNotionAdapter:
    @pytest.mark.asyncio
    async def test_provider_mismatch(self, adapter, connection):
        connection.provider = "slack"
        result = await adapter.execute("create_page", {}, connection)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_unknown_action(self, adapter, connection):
        result = await adapter.execute("unknown", {}, connection)
        assert result["success"] is False
        assert "Unknown Notion action" in result["error"]


# ── Action: create_page ───────────────────────────────────────────────────────


class TestCreatePage:
    @pytest.mark.asyncio
    async def test_success(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "page-1",
            "url": "https://notion.so/page-1",
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "create_page",
                {
                    "parent_page_id": "abc",
                    "properties": {
                        "title": {"title": [{"text": {"content": "New Page"}}]}
                    },
                },
                connection,
            )

        assert result["success"] is True
        assert result["response"]["id"] == "page-1"

    @pytest.mark.asyncio
    async def test_missing_parent_page_id(self, adapter, connection):
        result = await adapter.execute(
            "create_page", {"properties": {"title": {}}}, connection
        )
        assert result["success"] is False
        assert "parent_page_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_properties(self, adapter, connection):
        result = await adapter.execute(
            "create_page", {"parent_page_id": "abc"}, connection
        )
        assert result["success"] is False
        assert "properties" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_properties_rejected(self, adapter, connection):
        result = await adapter.execute(
            "create_page",
            {"parent_page_id": "abc", "properties": None},
            connection,
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_with_children(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "page-1"}

        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": "Hello"}}]},
            }
        ]

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await adapter.execute(
                "create_page",
                {
                    "parent_page_id": "abc",
                    "properties": {"title": {"title": [{"text": {"content": "P"}}]}},
                    "children": children,
                },
                connection,
            )

        body = mock_post.call_args[1]["json"]
        assert body["children"] == children

    @pytest.mark.asyncio
    async def test_empty_children_not_sent(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "page-1"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await adapter.execute(
                "create_page",
                {
                    "parent_page_id": "abc",
                    "properties": {"title": {"title": [{"text": {"content": "P"}}]}},
                    "children": [],
                },
                connection,
            )

        body = mock_post.call_args[1]["json"]
        assert "children" not in body


# ── Action: query_database ────────────────────────────────────────────────────


class TestQueryDatabase:
    @pytest.mark.asyncio
    async def test_success(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [{"id": "row-1", "properties": {}}],
            "has_more": False,
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "query_database", {"database_id": "db-123"}, connection
            )

        assert result["success"] is True
        assert len(result["response"]["results"]) == 1

    @pytest.mark.asyncio
    async def test_missing_database_id(self, adapter, connection):
        result = await adapter.execute("query_database", {}, connection)
        assert result["success"] is False
        assert "database_id" in result["error"]

    @pytest.mark.asyncio
    async def test_with_filter(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}

        filter_obj = {"property": "Status", "select": {"equals": "Done"}}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await adapter.execute(
                "query_database",
                {"database_id": "db-123", "filter": filter_obj},
                connection,
            )

        assert mock_post.call_args[1]["json"]["filter"] == filter_obj

    @pytest.mark.asyncio
    async def test_with_sorts(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}

        sorts = [{"property": "Created", "direction": "descending"}]

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await adapter.execute(
                "query_database",
                {"database_id": "db-123", "sorts": sorts},
                connection,
            )

        assert mock_post.call_args[1]["json"]["sorts"] == sorts

    @pytest.mark.asyncio
    async def test_limit(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await adapter.execute(
                "query_database",
                {"database_id": "db-123", "limit": 50},
                connection,
            )

        assert mock_post.call_args[1]["json"]["page_size"] == 50


# ── Action: append_block ──────────────────────────────────────────────────────


class TestAppendBlock:
    @pytest.mark.asyncio
    async def test_success(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [{"id": "block-1", "type": "paragraph"}],
        }

        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch:
            mock_patch.return_value = mock_resp
            result = await adapter.execute(
                "append_block",
                {
                    "block_id": "abc-123",
                    "children": [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {"rich_text": []},
                        }
                    ],
                },
                connection,
            )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_missing_block_id(self, adapter, connection):
        result = await adapter.execute(
            "append_block",
            {"children": [{"object": "block"}]},
            connection,
        )
        assert result["success"] is False
        assert "block_id" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_children_rejected(self, adapter, connection):
        result = await adapter.execute(
            "append_block", {"block_id": "abc", "children": []}, connection
        )
        assert result["success"] is False
        assert "children" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_children(self, adapter, connection):
        result = await adapter.execute("append_block", {"block_id": "abc"}, connection)
        assert result["success"] is False
        assert "children" in result["error"]
