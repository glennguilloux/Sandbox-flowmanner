"""Tests for the Google Drive adapter — all 4 actions + response parser."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.adapters.google_drive import (
    _MAX_FILE_BYTES,
    GoogleDriveAdapter,
    _drive_error_code,
    _parse_drive_response,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_connection(access_token="ya29.test", refresh_token="1//refresh"):
    """Build a minimal UserOAuthConnection mock."""
    conn = MagicMock()
    conn.id = "conn-1"
    conn.provider = "google_drive"
    conn.get_access_token.return_value = access_token
    conn.get_refresh_token.return_value = refresh_token
    conn.app_id = "app-1"
    return conn


def _json_response(status=200, data=None):
    """Build a mock httpx.Response that returns JSON."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = data or {}
    return resp


# ── Response parser ───────────────────────────────────────────────────────────


class TestParseDriveResponse:
    def test_success(self):
        resp = _json_response(200, {"files": [], "kind": "drive#fileList"})
        result = _parse_drive_response(resp)
        assert result["success"] is True
        assert result["response"]["files"] == []

    def test_error_with_dict(self):
        resp = _json_response(
            403,
            {
                "error": {
                    "code": 403,
                    "message": "Insufficient Permission",
                    "errors": [{"reason": "insufficientFilePermissions"}],
                }
            },
        )
        result = _parse_drive_response(resp)
        assert result["success"] is False
        assert "Insufficient Permission" in result["error"]
        assert result["error_code"] == "permission_denied"

    def test_token_expired(self):
        resp = _json_response(
            401, {"error": {"code": 401, "message": "Invalid Credentials"}}
        )
        result = _parse_drive_response(resp)
        assert result["success"] is False
        assert result["error"] == "token_expired"

    def test_non_json_response(self):
        resp = MagicMock()
        resp.status_code = 502
        resp.json.side_effect = ValueError("not json")
        result = _parse_drive_response(resp)
        assert result["success"] is False
        assert "non-JSON" in result["error"]

    def test_rate_limit(self):
        resp = _json_response(
            429, {"error": {"code": 429, "message": "Rate limit exceeded"}}
        )
        result = _parse_drive_response(resp)
        assert result["success"] is False
        assert result["error_code"] == "rate_limited"

    def test_quota_exceeded(self):
        resp = _json_response(
            403,
            {
                "error": {
                    "code": 403,
                    "message": "The user's Drive storage quota has been exceeded",
                }
            },
        )
        result = _parse_drive_response(resp)
        assert result["success"] is False
        assert result["error_code"] == "quota_exceeded"


class TestDriveErrorCode:
    def test_known_codes(self):
        assert _drive_error_code("notFound", "") == "not_found"
        assert _drive_error_code("fileNotFound", "") == "file_not_found"
        assert (
            _drive_error_code("insufficientFilePermissions", "") == "permission_denied"
        )
        assert _drive_error_code("rateLimitExceeded", "") == "rate_limited"
        assert _drive_error_code("quotaExceeded", "") == "quota_exceeded"
        assert _drive_error_code("userRateLimitExceeded", "") == "rate_limited"
        assert _drive_error_code("dailyLimitExceeded", "") == "quota_exceeded"

    def test_unknown_code(self):
        assert _drive_error_code(500, "") == "http_500"

    def test_message_match(self):
        assert _drive_error_code(403, "file not found") == "file_not_found"


# ── Adapter instantiation ─────────────────────────────────────────────────────


class TestAdapterBasics:
    def test_provider(self):
        adapter = GoogleDriveAdapter()
        assert adapter.provider == "google_drive"

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        adapter = GoogleDriveAdapter()
        result = await adapter._execute_action("bogus", {}, "token")
        assert result["success"] is False
        assert "Unknown" in result["error"]


# ── list_files ────────────────────────────────────────────────────────────────


class TestListFiles:
    @pytest.mark.asyncio
    async def test_success(self):
        adapter = GoogleDriveAdapter()
        mock_resp = _json_response(
            200,
            {
                "files": [
                    {
                        "id": "f1",
                        "name": "Doc 1",
                        "mimeType": "application/vnd.google-apps.document",
                    },
                ]
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_resp
            )
            result = await adapter._list_files({}, "token")

        assert result["success"] is True
        assert result["response"]["files"][0]["name"] == "Doc 1"

    @pytest.mark.asyncio
    async def test_with_query(self):
        adapter = GoogleDriveAdapter()
        mock_resp = _json_response(200, {"files": []})

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.get = AsyncMock(return_value=mock_resp)
            await adapter._list_files(
                {"query": "mimeType='application/pdf'", "page_size": 10}, "token"
            )

        call_args = ctx.get.call_args
        assert call_args[1]["params"]["q"] == "mimeType='application/pdf'"
        assert call_args[1]["params"]["pageSize"] == 10

    @pytest.mark.asyncio
    async def test_page_size_capped(self):
        adapter = GoogleDriveAdapter()
        mock_resp = _json_response(200, {"files": []})

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.get = AsyncMock(return_value=mock_resp)
            await adapter._list_files({"page_size": 999}, "token")

        call_args = ctx.get.call_args
        assert call_args[1]["params"]["pageSize"] == 100  # capped


# ── create_doc ────────────────────────────────────────────────────────────────


class TestCreateDoc:
    @pytest.mark.asyncio
    async def test_success(self):
        adapter = GoogleDriveAdapter()
        mock_resp = _json_response(
            200,
            {
                "id": "doc-1",
                "name": "New Doc",
                "mimeType": "application/vnd.google-apps.document",
                "webViewLink": "https://docs.google.com/document/d/doc-1/edit",
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=mock_resp)
            result = await adapter._create_doc({"title": "New Doc"}, "token")

        assert result["success"] is True
        assert result["response"]["id"] == "doc-1"

    @pytest.mark.asyncio
    async def test_missing_title(self):
        adapter = GoogleDriveAdapter()
        result = await adapter._create_doc({}, "token")
        assert result["success"] is False
        assert "title" in result["error"]

    @pytest.mark.asyncio
    async def test_with_folder_and_content(self):
        adapter = GoogleDriveAdapter()
        mock_resp = _json_response(200, {"id": "doc-2", "name": "In Folder"})

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.post = AsyncMock(return_value=mock_resp)
            result = await adapter._create_doc(
                {
                    "title": "In Folder",
                    "folder_id": "folder-1",
                    "content": "Hello world",
                },
                "token",
            )

        assert result["success"] is True
        # Verify multipart body includes metadata and content
        call_args = ctx.post.call_args
        body_str = call_args[1]["content"].decode("utf-8")
        assert "In Folder" in body_str
        assert "Hello world" in body_str
        assert "multipart" in call_args[1]["headers"]["Content-Type"]


# ── search_files ──────────────────────────────────────────────────────────────


class TestSearchFiles:
    @pytest.mark.asyncio
    async def test_success(self):
        adapter = GoogleDriveAdapter()
        mock_resp = _json_response(
            200,
            {
                "files": [
                    {"id": "f1", "name": "report.pdf", "mimeType": "application/pdf"}
                ]
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.get = AsyncMock(return_value=mock_resp)
            result = await adapter._search_files(
                {"query": "name contains 'report'"}, "token"
            )

        assert result["success"] is True
        assert len(result["response"]["files"]) == 1

    @pytest.mark.asyncio
    async def test_missing_query(self):
        adapter = GoogleDriveAdapter()
        result = await adapter._search_files({}, "token")
        assert result["success"] is False
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_page_size_capped(self):
        adapter = GoogleDriveAdapter()
        mock_resp = _json_response(200, {"files": []})

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.get = AsyncMock(return_value=mock_resp)
            await adapter._search_files({"query": "starred", "page_size": 999}, "token")

        call_args = ctx.get.call_args
        assert call_args[1]["params"]["pageSize"] == 100


# ── read_file ─────────────────────────────────────────────────────────────────


class TestReadFile:
    @pytest.mark.asyncio
    async def test_success_text(self):
        adapter = GoogleDriveAdapter()
        meta_resp = _json_response(
            200,
            {"id": "f1", "name": "notes.txt", "mimeType": "text/plain", "size": "100"},
        )
        content_resp = MagicMock()
        content_resp.status_code = 200
        content_resp.content = b"Hello, Drive!"

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.get = AsyncMock(side_effect=[meta_resp, content_resp])
            result = await adapter._read_file({"file_id": "f1"}, "token")

        assert result["success"] is True
        assert result["response"]["content"] == "Hello, Drive!"
        assert result["response"]["size"] == 13
        assert result["response"]["metadata"]["name"] == "notes.txt"

    @pytest.mark.asyncio
    async def test_file_too_large(self):
        adapter = GoogleDriveAdapter()
        meta_resp = _json_response(
            200, {"id": "big", "name": "huge.zip", "size": str(_MAX_FILE_BYTES + 1)}
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.get = AsyncMock(return_value=meta_resp)
            result = await adapter._read_file({"file_id": "big"}, "token")

        assert result["success"] is False
        assert "exceeds" in result["error"]

    @pytest.mark.asyncio
    async def test_binary_content(self):
        adapter = GoogleDriveAdapter()
        meta_resp = _json_response(
            200, {"id": "img", "name": "photo.png", "size": "512"}
        )
        content_resp = MagicMock()
        content_resp.status_code = 200
        content_resp.content = b"\x89PNG\r\n\x1a\n"  # Valid PNG header, non-UTF8

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.get = AsyncMock(side_effect=[meta_resp, content_resp])
            result = await adapter._read_file({"file_id": "img"}, "token")

        assert result["success"] is True
        assert result["response"]["metadata"]["encoding"] == "base64"
        # Content should be valid base64
        import base64

        decoded = base64.b64decode(result["response"]["content"])
        assert decoded == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.asyncio
    async def test_missing_file_id(self):
        adapter = GoogleDriveAdapter()
        result = await adapter._read_file({}, "token")
        assert result["success"] is False
        assert "file_id" in result["error"]

    @pytest.mark.asyncio
    async def test_metadata_error(self):
        adapter = GoogleDriveAdapter()
        meta_resp = _json_response(
            404, {"error": {"code": 404, "message": "File not found: f404"}}
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.get = AsyncMock(return_value=meta_resp)
            result = await adapter._read_file({"file_id": "f404"}, "token")

        assert result["success"] is False
        assert "File not found" in result["error"]

    @pytest.mark.asyncio
    async def test_download_error(self):
        adapter = GoogleDriveAdapter()
        meta_resp = _json_response(200, {"id": "f1", "name": "notes.txt", "size": "50"})
        content_resp = _json_response(
            500, {"error": {"code": 500, "message": "Internal error"}}
        )

        with patch("httpx.AsyncClient") as mock_client:
            ctx = mock_client.return_value.__aenter__.return_value
            ctx.get = AsyncMock(side_effect=[meta_resp, content_resp])
            result = await adapter._read_file({"file_id": "f1"}, "token")

        assert result["success"] is False
        assert "500" in result.get("error", "") or "Internal error" in result.get(
            "error", ""
        )


# ── Token refresh ─────────────────────────────────────────────────────────────


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_refresh_success(self):
        adapter = GoogleDriveAdapter()
        conn = _mock_connection(refresh_token="1//refresh")

        app = MagicMock()
        app.get_client_id.return_value = "cid"
        app.get_client_secret.return_value = "csec"

        token_resp = _json_response(
            200,
            {
                "access_token": "new-token",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.post = AsyncMock(return_value=token_resp)

            with patch("sqlalchemy.select"), patch(
                "app.database.AsyncSessionLocal"
            ) as mock_session_cls, patch(
                "app.integrations.oauth.encrypt_token", return_value="encrypted-new"
            ):
                mock_db = AsyncMock()
                mock_db.execute = AsyncMock()
                mock_result = MagicMock()
                mock_result.scalars.return_value.first.return_value = app
                mock_db.execute.return_value = mock_result
                mock_db.merge = AsyncMock(return_value=conn)
                mock_db.commit = AsyncMock()
                mock_session_cls.return_value.__aenter__.return_value = mock_db

                new_token = await adapter._refresh_token(conn)
                assert new_token == "new-token"

    @pytest.mark.asyncio
    async def test_no_refresh_token(self):
        adapter = GoogleDriveAdapter()
        conn = _mock_connection(refresh_token="")
        result = await adapter._refresh_token(conn)
        assert result is None

    @pytest.mark.asyncio
    async def test_token_request_fails(self):
        adapter = GoogleDriveAdapter()
        conn = _mock_connection()
        app = MagicMock()
        app.get_client_id.return_value = "cid"
        app.get_client_secret.return_value = "csec"

        error_resp = _json_response(400, {"error": "invalid_grant"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.post = AsyncMock(return_value=error_resp)

            with patch("sqlalchemy.select"), patch(
                "app.database.AsyncSessionLocal"
            ) as mock_session_cls:
                mock_db = AsyncMock()
                mock_result = MagicMock()
                mock_result.scalars.return_value.first.return_value = app
                mock_db.execute = AsyncMock(return_value=mock_result)
                mock_session_cls.return_value.__aenter__.return_value = mock_db

                new_token = await adapter._refresh_token(conn)
                assert new_token is None


# ── Max file size constant ────────────────────────────────────────────────────


def test_max_file_bytes():
    assert _MAX_FILE_BYTES == 10 * 1024 * 1024
    assert _MAX_FILE_BYTES == 10485760
