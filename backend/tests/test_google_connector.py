"""
Unit tests for GoogleConnector.

Tests the 15 actions (Drive, Gmail, Calendar) using mocked aiohttp responses,
plus credential validation and stats.
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
from app.services.connectors.google_connector import GoogleConnector


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
            resp = _make_mock_response(404, {"error": {"message": "Not Found"}})

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
        name="test-google",
        connector_type="google",
        auth_type=AuthType.OAUTH2,
        auth_config=auth_config or {"access_token": "ya29.test-token"},
    )


# ── Constructor ───────────────────────────────────────────────────────


def test_constructor_defaults():
    """Verify default config values are set correctly."""
    config = _make_config()
    connector = GoogleConnector(config)

    assert connector.connector_type == "google"
    assert "drive_list_files" in connector.available_actions
    assert "gmail_send" in connector.available_actions
    assert "calendar_create_event" in connector.available_actions


def test_available_actions_count():
    connector = GoogleConnector(_make_config())
    assert len(connector.available_actions) == 15


@pytest.mark.asyncio
async def test_unknown_action_returns_error():
    connector = GoogleConnector(_make_config())
    result = await connector.execute_action("nonexistent_action", {})
    assert result.success is False
    assert result.status_code == 400


# ── Credential Validation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_credentials_success():
    """_validate_credentials succeeds with a valid token."""
    # The GoogleConnector._validate_credentials uses httpx directly
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "email": "test@gmail.com",
            "expires_in": 3599,
            "scope": "https://www.googleapis.com/auth/gmail.send",
        }

        async def _get(url, **kwargs):
            return mock_resp

        mock_client.get = _get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        config = ConnectorConfig(
            name="test-google",
            connector_type="google",
            auth_type=AuthType.OAUTH2,
            auth_config={"access_token": "ya29.valid"},
        )
        connector = GoogleConnector(config)

        # Patch aiohttp.ClientSession to prevent BaseConnector.connect from failing
        fake_session = _FakeSession(
            {"default": _make_mock_response(200, {"status": "ok"})}
        )
        with patch("aiohttp.ClientSession", return_value=fake_session):
            ok = await connector.connect()

    assert ok is True
    assert connector._authenticated_email == "test@gmail.com"


@pytest.mark.asyncio
async def test_validate_credentials_no_token():
    """_validate_credentials returns False with no access_token."""
    config = ConnectorConfig(
        name="test-google",
        connector_type="google",
        auth_type=AuthType.OAUTH2,
        auth_config={},
    )
    connector = GoogleConnector(config)

    fake_session = _FakeSession({"default": _make_mock_response(200, {"status": "ok"})})
    with patch("aiohttp.ClientSession", return_value=fake_session):
        ok = await connector.connect()

    assert ok is False


@pytest.mark.asyncio
async def test_validate_credentials_invalid_token():
    """_validate_credentials returns False with an invalid token."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 400

        async def _get(url, **kwargs):
            return mock_resp

        mock_client.get = _get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        config = ConnectorConfig(
            name="test-google",
            connector_type="google",
            auth_type=AuthType.OAUTH2,
            auth_config={"access_token": "ya29.invalid"},
        )
        connector = GoogleConnector(config)

        fake_session = _FakeSession(
            {"default": _make_mock_response(200, {"status": "ok"})}
        )
        with patch("aiohttp.ClientSession", return_value=fake_session):
            ok = await connector.connect()

    assert ok is False


# ── Drive Actions ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drive_list_files():
    """List files in Google Drive."""
    files = {
        "files": [
            {"id": "f1", "name": "doc.pdf", "mimeType": "application/pdf"},
            {
                "id": "f2",
                "name": "sheet.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
        ]
    }
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "GET:https://www.googleapis.com/drive/v3/files": _make_mock_response(
                200, files
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("drive_list_files", {})

    assert result.success is True
    assert result.data["total"] == 2
    assert result.data["files"][0]["name"] == "doc.pdf"


@pytest.mark.asyncio
async def test_drive_search_files():
    """Search files by name."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "GET:https://www.googleapis.com/drive/v3/files": _make_mock_response(
                200, {"files": [{"id": "f99", "name": "budget.xlsx"}]}
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "drive_search_files", {"query": "budget"}
        )

    assert result.success is True
    assert result.data["files"][0]["name"] == "budget.xlsx"


@pytest.mark.asyncio
async def test_drive_search_files_missing_query():
    """Search files with missing query returns 400."""
    fake = _FakeSession(
        {"default": _make_mock_response(200, {"email": "test@gmail.com"})}
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("drive_search_files", {})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_drive_get_file():
    """Get file metadata by ID."""
    file_meta = {"id": "f1", "name": "doc.pdf", "mimeType": "application/pdf"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "GET:https://www.googleapis.com/drive/v3/files/f1": _make_mock_response(
                200, file_meta
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("drive_get_file", {"file_id": "f1"})

    assert result.success is True
    assert result.data["name"] == "doc.pdf"


@pytest.mark.asyncio
async def test_drive_create_folder():
    """Create a folder in Drive."""
    folder = {
        "id": "folder-new",
        "name": "New Folder",
        "mimeType": "application/vnd.google-apps.folder",
    }
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "POST:https://www.googleapis.com/drive/v3/files": _make_mock_response(
                200, folder
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "drive_create_folder", {"name": "New Folder"}
        )

    assert result.success is True
    assert result.data["name"] == "New Folder"


@pytest.mark.asyncio
async def test_drive_upload_file():
    """Upload a file to Drive."""
    uploaded = {"id": "upload-1", "name": "test.txt", "mimeType": "text/plain"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "POST:https://www.googleapis.com/drive/v3/files": _make_mock_response(
                200, uploaded
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "drive_upload_file",
            {"name": "test.txt", "content": "Hello World", "mime_type": "text/plain"},
        )

    assert result.success is True
    assert result.data["name"] == "test.txt"


# ── Gmail Actions ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gmail_send():
    """Send an email via Gmail."""
    sent = {"id": "msg-123", "labelIds": ["SENT"], "threadId": "thread-456"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "POST:https://gmail.googleapis.com/gmail/v1/users/me/messages/send": _make_mock_response(
                200, sent
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "gmail_send",
            {"to": "friend@example.com", "subject": "Hi", "body": "Hello!"},
        )

    assert result.success is True
    assert "SENT" in result.data.get("labelIds", [])


@pytest.mark.asyncio
async def test_gmail_send_missing_params():
    """Send email missing required params returns 400."""
    fake = _FakeSession(
        {"default": _make_mock_response(200, {"email": "test@gmail.com"})}
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("gmail_send", {"to": "x@x.com"})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_gmail_list():
    """List Gmail inbox messages."""
    msg_list = {"messages": [{"id": "m1"}, {"id": "m2"}], "resultSizeEstimate": 2}
    msg_detail = {"id": "m1", "snippet": "Hello", "payload": {"headers": []}}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "GET:https://gmail.googleapis.com/gmail/v1/users/me/messages": _make_mock_response(
                200, msg_list
            ),
            "GET:https://gmail.googleapis.com/gmail/v1/users/me/messages/m1": _make_mock_response(
                200, msg_detail
            ),
            "GET:https://gmail.googleapis.com/gmail/v1/users/me/messages/m2": _make_mock_response(
                200, {"id": "m2", "snippet": "World"}
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("gmail_list", {"max_results": 5})

    assert result.success is True
    assert len(result.data["messages"]) == 2


@pytest.mark.asyncio
async def test_gmail_search():
    """Search emails in Gmail."""
    msg_list = {"messages": [{"id": "m3"}], "resultSizeEstimate": 1}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "GET:https://gmail.googleapis.com/gmail/v1/users/me/messages": _make_mock_response(
                200, msg_list
            ),
            "GET:https://gmail.googleapis.com/gmail/v1/users/me/messages/m3": _make_mock_response(
                200, {"id": "m3", "snippet": "Found it"}
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("gmail_search", {"q": "invoice"})

    assert result.success is True
    assert result.data["messages"][0]["snippet"] == "Found it"


@pytest.mark.asyncio
async def test_gmail_get():
    """Get a specific email by ID."""
    msg = {"id": "m99", "snippet": "Details", "labelIds": ["INBOX"]}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "GET:https://gmail.googleapis.com/gmail/v1/users/me/messages/m99": _make_mock_response(
                200, msg
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("gmail_get", {"message_id": "m99"})

    assert result.success is True
    assert result.data["id"] == "m99"


# ── Calendar Actions ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calendar_list_events():
    """List calendar events."""
    events = {
        "items": [
            {
                "id": "e1",
                "summary": "Meeting",
                "start": {"dateTime": "2026-06-01T10:00:00Z"},
            },
            {
                "id": "e2",
                "summary": "Lunch",
                "start": {"dateTime": "2026-06-01T12:00:00Z"},
            },
        ]
    }
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "GET:https://www.googleapis.com/calendar/v3/calendars/primary/events": _make_mock_response(
                200, events
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("calendar_list_events", {})

    assert result.success is True
    assert len(result.data["items"]) == 2


@pytest.mark.asyncio
async def test_calendar_get_event():
    """Get a specific calendar event."""
    event = {
        "id": "e42",
        "summary": "Important",
        "start": {"dateTime": "2026-06-01T09:00:00Z"},
    }
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "GET:https://www.googleapis.com/calendar/v3/calendars/primary/events/e42": _make_mock_response(
                200, event
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "calendar_get_event", {"event_id": "e42"}
        )

    assert result.success is True
    assert result.data["summary"] == "Important"


@pytest.mark.asyncio
async def test_calendar_create_event():
    """Create a calendar event."""
    created = {"id": "e-new", "summary": "New Event", "status": "confirmed"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "POST:https://www.googleapis.com/calendar/v3/calendars/primary/events": _make_mock_response(
                200, created
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "calendar_create_event",
            {
                "summary": "New Event",
                "start": {"dateTime": "2026-06-01T14:00:00Z", "timeZone": "UTC"},
                "end": {"dateTime": "2026-06-01T15:00:00Z", "timeZone": "UTC"},
            },
        )

    assert result.success is True
    assert result.data["status"] == "confirmed"


@pytest.mark.asyncio
async def test_calendar_create_event_missing_summary():
    """Create calendar event missing summary returns 400."""
    fake = _FakeSession(
        {"default": _make_mock_response(200, {"email": "test@gmail.com"})}
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("calendar_create_event", {})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_calendar_update_event():
    """Update a calendar event."""
    updated = {"id": "e42", "summary": "Updated Summary"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "PATCH:https://www.googleapis.com/calendar/v3/calendars/primary/events/e42": _make_mock_response(
                200, updated
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "calendar_update_event",
            {"event_id": "e42", "summary": "Updated Summary"},
        )

    assert result.success is True
    assert result.data["summary"] == "Updated Summary"


@pytest.mark.asyncio
async def test_calendar_delete_event():
    """Delete a calendar event."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"email": "test@gmail.com"}),
            "DELETE:https://www.googleapis.com/calendar/v3/calendars/primary/events/e42": _make_mock_response(
                200, {}
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "calendar_delete_event", {"event_id": "e42"}
        )

    assert result.success is True


# ── get_stats ─────────────────────────────────────────────────────────


def test_get_stats():
    """get_stats returns connector info with authenticated email."""
    connector = GoogleConnector(_make_config())
    stats = connector.get_stats()

    assert stats["name"] == "test-google"
    assert stats["type"] == "google"
    assert "authenticated_email" in stats


# ── Disconnect ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disconnect():
    """Disconnect closes the session."""
    fake = _FakeSession({"default": _make_mock_response(200, {"login": "test"})})

    with patch("aiohttp.ClientSession", return_value=fake), patch.object(
        GoogleConnector, "_validate_credentials", return_value=True
    ):
        connector = GoogleConnector(_make_config())
        await connector.connect()
        assert connector.is_connected is True

        await connector.disconnect()
        assert connector.is_connected is False
