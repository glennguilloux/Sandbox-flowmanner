"""Unit tests for sandboxd_client — HTTP client for sandboxd v1 API."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestSandboxdClientCreate:
    """POST /v1/sandboxes — create sandbox."""

    @pytest.mark.asyncio
    async def test_create_sandbox_success(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "id": "sb-abc123",
            "status": "starting",
            "preview": {
                "url": "http://s-abc123-3000.preview.localhost",
                "status": "starting",
            },
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.create("proj-1", "user-1")

        assert result["id"] == "sb-abc123"
        assert result["status"] == "starting"

    @pytest.mark.asyncio
    async def test_create_sandbox_idempotent(self):
        """Calling create twice with same project_id returns existing sandbox."""
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200  # 200 on idempotent, 201 on new
        mock_resp.json.return_value = {"id": "sb-existing", "status": "running"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.create("proj-1", "user-1")

        assert result["id"] == "sb-existing"

    @pytest.mark.asyncio
    async def test_create_sandbox_server_error_raises(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=MagicMock(status_code=500)
            )
            with pytest.raises(httpx.HTTPStatusError):
                await client.create("proj-1", "user-1")


class TestSandboxdClientGet:
    """GET /v1/sandboxes/{id} — sandbox status."""

    @pytest.mark.asyncio
    async def test_get_sandbox_returns_status_and_preview(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "sb-abc123",
            "status": "running",
            "preview": {
                "url": "http://s-abc123-3000.preview.localhost",
                "status": "running",
            },
            "active_task": None,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.get("sb-abc123")

        assert result["status"] == "running"
        assert "preview" in result

    @pytest.mark.asyncio
    async def test_get_nonexistent_sandbox_raises(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=MagicMock(status_code=404)
            )
            with pytest.raises(httpx.HTTPStatusError):
                await client.get("sb-nonexistent")


class TestSandboxdClientStop:
    """POST /v1/sandboxes/{id}/stop — stop container."""

    @pytest.mark.asyncio
    async def test_stop_sandbox_success(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "sb-abc123", "status": "stopped"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.stop("sb-abc123")

        assert result["status"] == "stopped"


class TestSandboxdClientDelete:
    """DELETE /v1/sandboxes/{id} — full destroy."""

    @pytest.mark.asyncio
    async def test_delete_sandbox_returns_204(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.delete", new_callable=AsyncMock, return_value=mock_resp):
            await client.delete("sb-abc123")  # Should not raise


class TestSandboxdClientFiles:
    """File I/O operations."""

    @pytest.mark.asyncio
    async def test_read_file_returns_text(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "console.log('hello');"
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.read_file("sb-abc123", "src/index.js")

        assert result == "console.log('hello');"

    @pytest.mark.asyncio
    async def test_write_file_sends_raw_body(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"written": True}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.put", new_callable=AsyncMock, return_value=mock_resp) as mock_put:
            result = await client.write_file("sb-abc123", "src/app.py", b"print('hi')")

        assert result["written"] is True
        # Verify raw bytes sent, not base64 or JSON
        assert mock_put.call_args.kwargs.get("content") == b"print('hi')"

    @pytest.mark.asyncio
    async def test_list_files_with_recursive(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"path": "src/index.js", "type": "file"},
            {"path": "src/utils.js", "type": "file"},
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.list_files("sb-abc123", "src", recursive=True)

        assert len(result) == 2


class TestSandboxdClientTasks:
    """Task submission and events."""

    @pytest.mark.asyncio
    async def test_submit_task_returns_202(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "id": "task-xyz",
            "status": "running",
            "events_url": "/v1/sandboxes/sb-abc123/tasks/task-xyz/events",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.submit_task("sb-abc123", "Build a todo app")

        assert result["id"] == "task-xyz"
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_cancel_task_success(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "task-xyz", "status": "cancelled"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.cancel_task("sb-abc123", "task-xyz")

        assert result["status"] == "cancelled"


class TestSandboxdClientSnapshots:
    """Snapshot operations."""

    @pytest.mark.asyncio
    async def test_create_snapshot(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "snap-1", "sandbox_id": "sb-abc123"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.create_snapshot("sb-abc123", "before-deploy")

        assert result["id"] == "snap-1"

    @pytest.mark.asyncio
    async def test_list_snapshots(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"id": "snap-1"}, {"id": "snap-2"}]
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.list_snapshots()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_delete_snapshot(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.delete", new_callable=AsyncMock, return_value=mock_resp):
            await client.delete_snapshot("snap-1")  # Should not raise


class TestSandboxdClientHealth:
    """Health check."""

    @pytest.mark.asyncio
    async def test_health_check_returns_ok(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.health_check()

        assert result["status"] == "ok"
