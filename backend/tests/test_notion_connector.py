"""
Unit tests for NotionConnector.

Tests the 8 Notion actions (Search, Databases, Pages, Blocks) using
mocked aiohttp responses, plus credential validation and stats.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import ClientResponse

from app.services.connectors.base import (
    AuthType,
    ConnectorConfig,
    ConnectorResponse,
)
from app.services.connectors.notion_connector import NotionConnector

# ── Helpers ────────────────────────────────────────────────────────────


def _make_mock_response(status: int, body: dict | str, headers: dict | None = None):
    """Create a mock aiohttp ClientResponse."""
    resp = MagicMock(spec=ClientResponse)
    resp.status = status
    resp.headers = headers or {}
    resp.ok = 200 <= status < 300

    async def _json():
        if isinstance(body, dict | list):
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
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def request(self, method: str, url: str, **kwargs):
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
        name="test-notion",
        connector_type="notion",
        auth_type=AuthType.OAUTH2,
        auth_config=auth_config or {"access_token": "secret_ntn.test"},
    )


# ── Constructor ───────────────────────────────────────────────────────


def test_constructor_defaults():
    """Verify default config values are set correctly."""
    config = _make_config()
    connector = NotionConnector(config)

    assert connector.connector_type == "notion"
    assert "search" in connector.available_actions
    assert "query_database" in connector.available_actions
    assert "create_page" in connector.available_actions


def test_available_actions_count():
    connector = NotionConnector(_make_config())
    assert len(connector.available_actions) == 12


@pytest.mark.asyncio
async def test_unknown_action_returns_error():
    connector = NotionConnector(_make_config())
    result = await connector.execute_action("nonexistent_action", {})
    assert result.success is False
    assert result.status_code == 400


# ── Credential Validation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_credentials_success():
    """_validate_credentials succeeds with a valid token."""
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(
                200,
                {"object": "user", "id": "u1", "name": "Test Bot", "type": "bot"},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        ok = await connector.connect()

    assert ok is True
    assert "Test Bot" in connector._authenticated_user


@pytest.mark.asyncio
async def test_validate_credentials_no_token():
    """_validate_credentials returns False with no access_token."""
    config = ConnectorConfig(
        name="test-notion",
        connector_type="notion",
        auth_type=AuthType.OAUTH2,
        auth_config={},
    )
    connector = NotionConnector(config)

    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(401, {"message": "Invalid token"}),
        }
    )
    with patch("aiohttp.ClientSession", return_value=fake):
        ok = await connector.connect()

    assert ok is False


# ── Search ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search():
    """Search pages and databases by title."""
    results = {
        "results": [
            {"id": "p1", "object": "page", "url": "https://notion.so/p1"},
            {"id": "d1", "object": "database", "url": "https://notion.so/d1"},
        ],
        "has_more": False,
    }
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
            "POST:https://api.notion.com/v1/search": _make_mock_response(200, results),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("search", {"q": "meeting notes"})

    assert result.success is True
    assert len(result.data["results"]) == 2


@pytest.mark.asyncio
async def test_search_missing_query():
    """Search with missing query returns 400."""
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("search", {})

    assert result.success is False
    assert result.status_code == 400


# ── Databases ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_databases():
    """List databases shared with the integration."""
    databases = {
        "results": [
            {"id": "db1", "title": [{"text": {"content": "Tasks"}}]},
            {"id": "db2", "title": [{"text": {"content": "Projects"}}]},
        ],
        "has_more": False,
    }
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
            "GET:https://api.notion.com/v1/databases": _make_mock_response(200, databases),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("list_databases", {})

    assert result.success is True
    assert len(result.data["results"]) == 2


@pytest.mark.asyncio
async def test_query_database():
    """Query rows from a Notion database."""
    rows = {
        "results": [
            {
                "id": "r1",
                "properties": {"Name": {"title": [{"text": {"content": "Buy milk"}}]}},
            },
            {
                "id": "r2",
                "properties": {"Name": {"title": [{"text": {"content": "Write docs"}}]}},
            },
        ],
        "has_more": False,
    }
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
            "POST:https://api.notion.com/v1/databases/db1/query": _make_mock_response(200, rows),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("query_database", {"database_id": "db1"})

    assert result.success is True
    assert len(result.data["results"]) == 2


@pytest.mark.asyncio
async def test_query_database_missing_id():
    """Query database missing database_id returns 400."""
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("query_database", {})

    assert result.success is False
    assert result.status_code == 400


# ── Pages ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_page():
    """Get a page by ID."""
    page = {
        "id": "page1",
        "object": "page",
        "properties": {"title": {"title": [{"text": {"content": "Meeting Notes"}}]}},
        "url": "https://notion.so/page1",
    }
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
            "GET:https://api.notion.com/v1/pages/page1": _make_mock_response(200, page),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_page", {"page_id": "page1"})

    assert result.success is True
    assert result.data["id"] == "page1"


@pytest.mark.asyncio
async def test_get_page_missing_id():
    """Get page missing page_id returns 400."""
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_page", {})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_create_page():
    """Create a new page in a database."""
    created = {
        "id": "page-new",
        "object": "page",
        "url": "https://notion.so/page-new",
    }
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
            "POST:https://api.notion.com/v1/pages": _make_mock_response(200, created),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "create_page",
            {
                "parent": {"database_id": "db1"},
                "properties": {"Name": {"title": [{"text": {"content": "New Task"}}]}},
            },
        )

    assert result.success is True
    assert result.data["id"] == "page-new"


@pytest.mark.asyncio
async def test_create_page_missing_parent():
    """Create page missing parent param returns 400."""
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("create_page", {"properties": {"Name": {}}})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_update_page():
    """Update page properties."""
    updated = {"id": "page1", "object": "page", "archived": False}
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
            "PATCH:https://api.notion.com/v1/pages/page1": _make_mock_response(200, updated),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "update_page",
            {
                "page_id": "page1",
                "properties": {"Status": {"select": {"name": "Done"}}},
            },
        )

    assert result.success is True


@pytest.mark.asyncio
async def test_update_page_missing_id():
    """Update page missing page_id returns 400."""
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("update_page", {})

    assert result.success is False
    assert result.status_code == 400


# ── Blocks ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_block_children():
    """Get the children blocks of a page."""
    children = {
        "results": [
            {
                "id": "b1",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": "Hello"}}]},
            },
            {
                "id": "b2",
                "type": "heading_1",
                "heading_1": {"rich_text": [{"text": {"content": "Title"}}]},
            },
        ],
        "has_more": False,
    }
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
            "GET:https://api.notion.com/v1/blocks/page1/children": _make_mock_response(200, children),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_block_children", {"block_id": "page1"})

    assert result.success is True
    assert len(result.data["results"]) == 2
    assert result.data["results"][0]["type"] == "paragraph"


@pytest.mark.asyncio
async def test_get_block_children_missing_id():
    """Get block children missing block_id returns 400."""
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_block_children", {})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_append_block_children():
    """Append content blocks to a page."""
    appended = {
        "results": [
            {
                "id": "b3",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": "New block"}}]},
            }
        ]
    }
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
            "PATCH:https://api.notion.com/v1/blocks/page1/children": _make_mock_response(200, appended),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "append_block_children",
            {
                "block_id": "page1",
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"text": {"content": "New block"}}]},
                    }
                ],
            },
        )

    assert result.success is True
    assert len(result.data["results"]) == 1


@pytest.mark.asyncio
async def test_append_block_children_missing_params():
    """Append blocks missing required params returns 400."""
    fake = _FakeSession(
        {
            "GET:https://api.notion.com/v1/users/me": _make_mock_response(200, {"name": "Bot", "type": "bot"}),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = NotionConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("append_block_children", {})

    assert result.success is False
    assert result.status_code == 400


# ── get_stats ─────────────────────────────────────────────────────────


def test_get_stats():
    """get_stats returns connector info with authenticated user."""
    connector = NotionConnector(_make_config())
    stats = connector.get_stats()

    assert stats["name"] == "test-notion"
    assert stats["type"] == "notion"
    assert "authenticated_user" in stats
