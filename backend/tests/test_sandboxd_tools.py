"""Unit tests for sandboxd agent tools — sandboxd_exec, sandboxd_file_*, sandboxd_preview."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

# These are pure unit tests with mocked sandboxd client — no integration marker needed.


class TestSandboxdExecTool:
    """sandboxd_exec — execute code in isolated Docker container."""

    def test_tool_metadata(self):
        from app.tools.sandboxd_exec import SandboxdExecTool

        tool = SandboxdExecTool()
        assert tool.tool_id == "sandboxd_exec"
        assert "sandbox" in tool.tags
        assert tool.category == "code-execution-and-development"

    @pytest.mark.asyncio
    async def test_execute_python_code(self):
        from app.tools.sandboxd_exec import SandboxdExecTool

        tool = SandboxdExecTool()

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={
                "stdout": "hello world\n",
                "stderr": "",
                "exit_code": 0,
            }
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"),
        ):
            result = await tool.execute(
                {"code": "print('hello world')", "language": "python"}
            )

        assert result.success is True
        assert "hello world" in result.result["stdout"]

    @pytest.mark.asyncio
    async def test_execute_returns_nonzero_on_error(self):
        from app.tools.sandboxd_exec import SandboxdExecTool

        tool = SandboxdExecTool()

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={
                "stdout": "",
                "stderr": "SyntaxError: invalid syntax",
                "exit_code": 1,
            }
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"),
        ):
            result = await tool.execute({"code": "def broken(", "language": "python"})

        assert result.success is True  # Tool succeeded (code failed)
        assert result.result["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_execute_invalid_input_returns_error(self):
        from app.tools.sandboxd_exec import SandboxdExecTool

        tool = SandboxdExecTool()
        result = await tool.execute({})  # Missing both 'code' and 'command'

        assert result.success is False
        assert "command" in result.error.lower() or "code" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_unsupported_language(self):
        from app.tools.sandboxd_exec import SandboxdExecTool

        tool = SandboxdExecTool()
        result = await tool.execute({"code": "fn main() {}", "language": "rust"})

        assert result.success is False
        assert "Unsupported language" in result.error

    @pytest.mark.asyncio
    async def test_execute_no_sandbox_available(self):
        from app.tools.sandboxd_exec import SandboxdExecTool

        tool = SandboxdExecTool()

        with patch.object(tool, "_resolve_sandbox_id", return_value=None):
            result = await tool.execute({"code": "print('hi')", "language": "python"})

        assert result.success is False
        assert "No sandbox available" in result.error


class TestSandboxdFileReadTool:
    """sandboxd_file_read — read files from sandbox workspace."""

    def test_tool_metadata(self):
        from app.tools.sandboxd_file_read import SandboxdFileReadTool

        tool = SandboxdFileReadTool()
        assert tool.tool_id == "sandboxd_file_read"
        assert "sandbox" in tool.tags

    @pytest.mark.asyncio
    async def test_read_file_returns_content(self):
        from app.tools.sandboxd_file_read import SandboxdFileReadTool

        tool = SandboxdFileReadTool()

        mock_client = MagicMock()
        mock_client.read_file = AsyncMock(return_value="const x = 42;")

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"),
        ):
            result = await tool.execute({"path": "src/index.js"})

        assert result.success is True
        assert result.result["content"] == "const x = 42;"
        mock_client.read_file.assert_awaited_once_with("sb-abc", "src/index.js")

    @pytest.mark.asyncio
    async def test_read_file_no_sandbox(self):
        from app.tools.sandboxd_file_read import SandboxdFileReadTool

        tool = SandboxdFileReadTool()

        with patch.object(tool, "_resolve_sandbox_id", return_value=None):
            result = await tool.execute({"path": "src/index.js"})

        assert result.success is False
        assert "No sandbox available" in result.error


class TestSandboxdFileWriteTool:
    """sandboxd_file_write — write files to sandbox workspace."""

    def test_tool_metadata(self):
        from app.tools.sandboxd_file_write import SandboxdFileWriteTool

        tool = SandboxdFileWriteTool()
        assert tool.tool_id == "sandboxd_file_write"
        assert "sandbox" in tool.tags

    @pytest.mark.asyncio
    async def test_write_file_success(self):
        from app.tools.sandboxd_file_write import SandboxdFileWriteTool

        tool = SandboxdFileWriteTool()

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
            }
        )
        mock_client.write_file = AsyncMock(return_value={"written": True})

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"),
        ):
            result = await tool.execute(
                {"path": "src/app.py", "content": "print('hi')"}
            )

        assert result.success is True
        mock_client.write_file.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_file_no_sandbox(self):
        from app.tools.sandboxd_file_write import SandboxdFileWriteTool

        tool = SandboxdFileWriteTool()

        with patch.object(tool, "_resolve_sandbox_id", return_value=None):
            result = await tool.execute(
                {"path": "src/app.py", "content": "print('hi')"}
            )

        assert result.success is False


class TestSandboxdPreviewTool:
    """sandboxd_preview — get or create sandbox, return live preview URL."""

    def test_tool_metadata(self):
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        tool = SandboxdPreviewTool()
        assert tool.tool_id == "sandboxd_preview"
        assert "sandbox" in tool.tags
        assert tool.metadata.timeout_seconds == 30

    @pytest.mark.asyncio
    async def test_returns_preview_url_with_explicit_sandbox_id(self):
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        tool = SandboxdPreviewTool()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(
            return_value={
                "preview": {
                    "url": "http://s-abc-3000.preview.localhost",
                    "status": "ready",
                }
            }
        )

        with patch.object(tool, "_get_client", return_value=mock_client):
            result = await tool.execute({"sandbox_id": "sb-abc"})

        assert result.success is True
        assert result.result["sandbox_id"] == "sb-abc"
        assert "preview" in result.result
        assert result.result["preview"]["status"] == "ready"
        mock_client.get.assert_awaited()

    @pytest.mark.asyncio
    async def test_returns_preview_url_from_context(self):
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        tool = SandboxdPreviewTool()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(
            return_value={
                "preview": {
                    "url": "http://s-ctx-3000.preview.localhost",
                    "status": "ready",
                }
            }
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value="sb-from-context"),
        ):
            result = await tool.execute({})

        assert result.success is True
        assert result.result["sandbox_id"] == "sb-from-context"

    @pytest.mark.asyncio
    async def test_auto_creates_sandbox_when_none_exists(self):
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        tool = SandboxdPreviewTool()

        mock_client = MagicMock()
        mock_client.create = AsyncMock(
            return_value={"id": "sb-auto-123", "status": "creating"}
        )
        mock_client.get = AsyncMock(
            return_value={
                "status": "running",
                "preview": {
                    "url": "http://s-auto-123-3000.preview.localhost",
                    "status": "ready",
                },
            }
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value=None),
            patch.object(tool, "_set_sandbox_id") as mock_set,
        ):
            result = await tool.execute({})

        assert result.success is True
        assert result.result["sandbox_id"] == "sb-auto-123"
        mock_client.create.assert_awaited_once()
        mock_set.assert_called_once_with("sb-auto-123")

    @pytest.mark.asyncio
    async def test_auto_create_failure_returns_error(self):
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        tool = SandboxdPreviewTool()

        mock_client = MagicMock()

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value=None),
            patch.object(tool, "_auto_create_sandbox", return_value=None),
        ):
            result = await tool.execute({})

        assert result.success is False
        assert "Failed to auto-create" in result.error

    # ── rewrite_sandboxd_url tests ──────────────────────────────────

    def test_rewrite_url_empty(self):
        from app.integrations.sandboxd_client import rewrite_sandboxd_url

        assert rewrite_sandboxd_url("") == ""

    def test_rewrite_url_localhost_to_flowmanner(self):
        from app.integrations.sandboxd_client import rewrite_sandboxd_url

        with patch("app.integrations.sandboxd_client.settings") as mock_settings:
            mock_settings.SANDBOXD_PREVIEW_DOMAIN = "preview.flowmanner.com"
            result = rewrite_sandboxd_url("http://s-abc-3000.preview.localhost")
        assert result == "https://s-abc-3000.preview.flowmanner.com"

    def test_rewrite_url_upgrades_http_to_https(self):
        from app.integrations.sandboxd_client import rewrite_sandboxd_url

        with patch("app.integrations.sandboxd_client.settings") as mock_settings:
            mock_settings.SANDBOXD_PREVIEW_DOMAIN = "preview.flowmanner.com"
            result = rewrite_sandboxd_url("http://s-abc-3000.preview.flowmanner.com")
        assert result == "https://s-abc-3000.preview.flowmanner.com"

    def test_rewrite_url_already_https_noop(self):
        from app.integrations.sandboxd_client import rewrite_sandboxd_url

        with patch("app.integrations.sandboxd_client.settings") as mock_settings:
            mock_settings.SANDBOXD_PREVIEW_DOMAIN = "preview.flowmanner.com"
            result = rewrite_sandboxd_url("https://s-abc-3000.preview.flowmanner.com")
        assert result == "https://s-abc-3000.preview.flowmanner.com"

    def test_rewrite_url_no_domain_config(self):
        from app.integrations.sandboxd_client import rewrite_sandboxd_url

        with patch("app.integrations.sandboxd_client.settings") as mock_settings:
            mock_settings.SANDBOXD_PREVIEW_DOMAIN = ""
            result = rewrite_sandboxd_url("http://s-abc-3000.preview.localhost")
        # No domain configured → no rewrite, no https upgrade
        assert result == "http://s-abc-3000.preview.localhost"

    def test_rewrite_url_unrelated_url_noop(self):
        from app.integrations.sandboxd_client import rewrite_sandboxd_url

        with patch("app.integrations.sandboxd_client.settings") as mock_settings:
            mock_settings.SANDBOXD_PREVIEW_DOMAIN = "preview.flowmanner.com"
            result = rewrite_sandboxd_url("https://example.com/page")
        assert result == "https://example.com/page"

    # ── Readiness polling tests ───────────────────────────────────────

    @pytest.mark.asyncio
    async def test_polls_until_ready(self):
        """Polls preview status from 'starting' to 'ready' before returning."""
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        tool = SandboxdPreviewTool()

        starting_info = {
            "status": "running",
            "preview": {"url": None, "status": "starting"},
        }
        ready_info = {
            "status": "running",
            "preview": {
                "url": "http://s-poll-3000.preview.localhost",
                "status": "ready",
            },
        }

        mock_client = MagicMock()
        mock_client.get = AsyncMock(
            side_effect=[starting_info, starting_info, ready_info]
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result = await tool.execute({"sandbox_id": "sb-poll"})

        assert result.success is True
        assert result.result["preview_status"] == "ready"
        assert "preview.flowmanner.com" in result.result["preview_url"]
        # Polled 2 extra times (3 total get calls, 2 sleeps between them)
        assert mock_client.get.await_count == 3
        assert mock_sleep.await_count == 2
        mock_sleep.assert_awaited_with(0.5)

    @pytest.mark.asyncio
    async def test_polls_until_error(self):
        """Stops polling when preview status becomes 'error'."""
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        tool = SandboxdPreviewTool()

        starting_info = {
            "status": "running",
            "preview": {"url": None, "status": "starting"},
        }
        error_info = {
            "status": "running",
            "preview": {"url": None, "status": "error"},
        }

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[starting_info, error_info])

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result = await tool.execute({"sandbox_id": "sb-err"})

        assert result.success is True
        assert result.result["preview_status"] == "error"
        assert mock_client.get.await_count == 2
        assert mock_sleep.await_count == 1

    @pytest.mark.asyncio
    async def test_polling_survives_transient_get_errors(self):
        """Continues polling when client.get raises transient exceptions
        inside the polling loop (after the first successful call)."""
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        tool = SandboxdPreviewTool()

        starting_info = {
            "status": "running",
            "preview": {"url": None, "status": "starting"},
        }
        ready_info = {
            "status": "running",
            "preview": {
                "url": "http://s-t-3000.preview.localhost",
                "status": "ready",
            },
        }

        mock_client = MagicMock()
        # First call succeeds (starts polling), second raises (transient),
        # third succeeds (polling completes).
        mock_client.get = AsyncMock(
            side_effect=[starting_info, ConnectionError("transient"), ready_info]
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await tool.execute({"sandbox_id": "sb-transient"})

        assert result.success is True
        assert result.result["preview_status"] == "ready"
        assert mock_client.get.await_count == 3

    @pytest.mark.asyncio
    async def test_skips_polling_when_already_ready(self):
        """No polling when preview status is already 'ready'."""
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        tool = SandboxdPreviewTool()

        ready_info = {
            "status": "running",
            "preview": {
                "url": "http://s-already-3000.preview.localhost",
                "status": "ready",
            },
        }

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=ready_info)

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result = await tool.execute({"sandbox_id": "sb-already"})

        assert result.success is True
        assert result.result["preview_status"] == "ready"
        assert mock_client.get.await_count == 1
        mock_sleep.assert_not_awaited()

    # ── _auto_create_sandbox tests ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_auto_create_sandbox_success(self):
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        mock_client = MagicMock()
        mock_client.create = AsyncMock(return_value={"id": "sb-new-456"})

        with patch("app.config.settings") as mock_settings:
            mock_settings.SANDBOXD_DEFAULT_TEMPLATE = "react-standard"
            result = await SandboxdPreviewTool._auto_create_sandbox(mock_client)

        assert result == "sb-new-456"
        mock_client.create.assert_awaited_once()
        call_kwargs = mock_client.create.call_args
        assert call_kwargs.kwargs["user_id"] == "chat-standalone"
        assert call_kwargs.kwargs["template"] == "react-standard"
        assert call_kwargs.kwargs["project_id"].startswith("chat-")

    @pytest.mark.asyncio
    async def test_auto_create_sandbox_returns_none_on_failure(self):
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        mock_client = MagicMock()
        mock_client.create = AsyncMock(side_effect=ConnectionError("sandboxd down"))

        result = await SandboxdPreviewTool._auto_create_sandbox(mock_client)
        assert result is None

    # ── schema test ───────────────────────────────────────────────────

    def test_input_schema_has_sandbox_id_field(self):
        from app.tools.sandboxd_preview import SandboxdPreviewInput

        schema = SandboxdPreviewInput.schema_extra()
        props = schema.get("properties", {})
        assert "sandbox_id" in props
        # sandbox_id is optional (str | None) — Pydantic uses anyOf for unions
        assert (
            props["sandbox_id"].get("anyOf") is not None
            or props["sandbox_id"].get("type") is not None
        )


class TestSandboxdFileListTool:
    """sandboxd_file_list — list files in sandbox workspace."""

    def test_tool_metadata(self):
        from app.tools.sandboxd_file_list import SandboxdFileListTool

        tool = SandboxdFileListTool()
        assert tool.tool_id == "sandboxd_file_list"
        assert "sandbox" in tool.tags

    @pytest.mark.asyncio
    async def test_list_files_returns_tree(self):
        from app.tools.sandboxd_file_list import SandboxdFileListTool

        tool = SandboxdFileListTool()

        mock_client = MagicMock()
        mock_client.list_files = AsyncMock(
            return_value=[
                {"path": "src/index.js", "type": "file"},
                {"path": "src/utils.js", "type": "file"},
            ]
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"),
        ):
            result = await tool.execute({"path": "src", "recursive": True})

        assert result.success is True
        assert len(result.result["files"]) == 2
        mock_client.list_files.assert_awaited_once_with(
            "sb-abc", path="src", recursive=True
        )

    @pytest.mark.asyncio
    async def test_list_files_no_sandbox(self):
        from app.tools.sandboxd_file_list import SandboxdFileListTool

        tool = SandboxdFileListTool()

        with patch.object(tool, "_resolve_sandbox_id", return_value=None):
            result = await tool.execute({})

        assert result.success is False


class TestSandboxdServeTool:
    """sandboxd_serve — start dev server inside sandbox and return preview URL."""

    def test_tool_metadata(self):
        from app.tools.sandboxd_serve import SandboxdServeTool

        tool = SandboxdServeTool()
        assert tool.tool_id == "sandboxd_serve"
        assert "sandbox" in tool.tags
        assert "serve" in tool.tags
        assert tool.category == "code-execution-and-development"
        assert tool.metadata.timeout_seconds == 45

    @pytest.mark.asyncio
    async def test_returns_url_when_port_already_serving(self):
        """Port 3000 already serving (template server) — returns URL immediately."""
        from app.tools.sandboxd_serve import SandboxdServeTool

        tool = SandboxdServeTool()

        mock_client = MagicMock()
        # _check_port returns 200 — port is already serving
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "200", "stderr": "", "exit_code": 0}
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"),
        ):
            result = await tool.execute({})

        assert result.success is True
        assert result.result["sandbox_id"] == "sb-abc"
        assert result.result["port"] == 3000
        assert result.result["server_pid"] == 0  # Unknown — didn't start it
        assert result.result["status"] == "ready"
        assert "preview.flowmanner.com" in result.result["preview_url"]
        assert "sb-abc-3000" in result.result["preview_url"]
        # Only one exec call — the check, no fallback start
        assert mock_client.exec_command.await_count == 1

    @pytest.mark.asyncio
    async def test_starts_fallback_when_port_not_serving(self):
        """Port not serving — starts fallback server and polls until ready."""
        from app.tools.sandboxd_serve import SandboxdServeTool

        tool = SandboxdServeTool()

        mock_client = MagicMock()
        # _check_port: first call returns 000 (not serving), second returns 200 (ready)
        # _start_fallback_server: returns PID
        mock_client.exec_command = AsyncMock(
            side_effect=[
                # First check_port call — not serving
                {"stdout": "000", "stderr": "", "exit_code": 0},
                # start_fallback_server call — PID returned
                {"stdout": "12345", "stderr": "", "exit_code": 0},
                # Polling check_port — now serving
                {"stdout": "200", "stderr": "", "exit_code": 0},
            ]
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await tool.execute({})

        assert result.success is True
        assert result.result["server_pid"] == 12345
        assert result.result["status"] == "ready"
        assert "sb-abc-3000" in result.result["preview_url"]

    @pytest.mark.asyncio
    async def test_serve_with_custom_port(self):
        from app.tools.sandboxd_serve import SandboxdServeTool

        tool = SandboxdServeTool()

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            side_effect=[
                # check_port on custom port — already serving
                {"stdout": "200", "stderr": "", "exit_code": 0},
            ]
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"),
        ):
            result = await tool.execute({"port": 5173})

        assert result.success is True
        assert result.result["port"] == 5173
        assert "sb-abc-5173" in result.result["preview_url"]

    @pytest.mark.asyncio
    async def test_serve_with_explicit_sandbox_id(self):
        from app.tools.sandboxd_serve import SandboxdServeTool

        tool = SandboxdServeTool()

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "200", "stderr": "", "exit_code": 0}
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await tool.execute({"sandbox_id": "sb-explicit"})

        assert result.success is True
        assert result.result["sandbox_id"] == "sb-explicit"

    @pytest.mark.asyncio
    async def test_serve_no_sandbox_returns_error(self):
        from app.tools.sandboxd_serve import SandboxdServeTool

        tool = SandboxdServeTool()

        with patch.object(tool, "_resolve_sandbox_id", return_value=None):
            result = await tool.execute({})

        assert result.success is False
        assert "No sandbox available" in result.error

    @pytest.mark.asyncio
    async def test_serve_reports_started_when_poll_fails(self):
        """Fallback started but port never comes up — status='started'."""
        from app.tools.sandboxd_serve import SandboxdServeTool

        tool = SandboxdServeTool()

        mock_client = MagicMock()
        # First check: not serving → start fallback
        # Then 20 poll attempts: all return 000
        exec_results = [
            # check_port — not serving
            {"stdout": "000", "stderr": "", "exit_code": 0},
            # start_fallback_server — PID
            {"stdout": "999", "stderr": "", "exit_code": 0},
        ]
        for _ in range(20):
            exec_results.append(
                {"stdout": "000", "stderr": "", "exit_code": 0}
            )
        mock_client.exec_command = AsyncMock(side_effect=exec_results)

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await tool.execute({})

        assert result.success is True
        assert result.result["server_pid"] == 999
        assert result.result["status"] == "started"  # not "ready"
        assert "preview_url" in result.result

    @pytest.mark.asyncio
    async def test_serve_uses_context_sandbox_id(self):
        from app.tools.sandboxd_serve import SandboxdServeTool

        tool = SandboxdServeTool()

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "200", "stderr": "", "exit_code": 0}
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(
                tool, "_resolve_sandbox_id", return_value="sb-from-ctx"
            ),
        ):
            result = await tool.execute({})

        assert result.success is True
        assert result.result["sandbox_id"] == "sb-from-ctx"

    @pytest.mark.asyncio
    async def test_serve_with_custom_directory(self):
        """Custom directory is passed to fallback server start command."""
        from app.tools.sandboxd_serve import SandboxdServeTool

        tool = SandboxdServeTool()

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            side_effect=[
                # check_port — not serving (need fallback)
                {"stdout": "000", "stderr": "", "exit_code": 0},
                # start_fallback_server — PID
                {"stdout": "777", "stderr": "", "exit_code": 0},
                # poll check_port — ready
                {"stdout": "200", "stderr": "", "exit_code": 0},
            ]
        )

        with (
            patch.object(tool, "_get_client", return_value=mock_client),
            patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await tool.execute({"directory": "/home/sandbox/app"})

        assert result.success is True
        # Verify the start command used the custom directory
        start_call = mock_client.exec_command.call_args_list[1]
        cmd_str = start_call[0][1][2]  # the bash -lc arg
        assert "/home/sandbox/app" in cmd_str
