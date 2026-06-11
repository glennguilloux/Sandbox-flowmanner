"""Unit tests for app.tools._sandbox_serve_helpers.

The helpers centralise the "check port + start python3 http.server" logic
that was previously duplicated between ``sandboxd_serve.py`` and
``sandboxd_file_write.py``.  These tests pin the contract:

- ``is_port_serving`` returns ``True`` only for 2xx/3xx HTTP responses
- ``start_static_http_server(return_pid=True)`` returns the PID
- ``start_static_http_server(return_pid=False)`` is fire-and-forget
- ``ensure_serving_on_port`` is idempotent (no-op if already serving)
- ``start_static_http_server`` reports start-command failures clearly
"""

import os
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

# These are pure unit tests with mocked sandboxd client — no integration marker needed.


class TestIsPortServing:
    """is_port_serving — probes an HTTP port inside the sandbox."""

    @pytest.mark.asyncio
    async def test_returns_true_for_200(self):
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "200", "stderr": "", "exit_code": 0}
        )

        result = await is_port_serving(mock_client, "sb-abc", 8081)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_301_redirect(self):
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "301", "stderr": "", "exit_code": 0}
        )

        result = await is_port_serving(mock_client, "sb-abc", 8081)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_302_redirect(self):
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "302", "stderr": "", "exit_code": 0}
        )

        result = await is_port_serving(mock_client, "sb-abc", 8081)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_304_not_modified(self):
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "304", "stderr": "", "exit_code": 0}
        )

        result = await is_port_serving(mock_client, "sb-abc", 8081)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_for_000_connection_failed(self):
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "000", "stderr": "", "exit_code": 0}
        )

        result = await is_port_serving(mock_client, "sb-abc", 8081)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_404_not_serving(self):
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "404", "stderr": "", "exit_code": 0}
        )

        result = await is_port_serving(mock_client, "sb-abc", 8081)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_500_internal_error(self):
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "500", "stderr": "", "exit_code": 0}
        )

        result = await is_port_serving(mock_client, "sb-abc", 8081)
        assert result is False

    @pytest.mark.asyncio
    async def test_handles_surrounding_whitespace_and_quotes(self):
        """Output may include leading/trailing whitespace and stray quotes
        from shell escaping.  The parser must normalise before checking."""
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": " '200'\n", "stderr": "", "exit_code": 0}
        )

        result = await is_port_serving(mock_client, "sb-abc", 8081)
        assert result is True

    @pytest.mark.asyncio
    async def test_handles_empty_stdout(self):
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "", "stderr": "", "exit_code": 0}
        )

        result = await is_port_serving(mock_client, "sb-abc", 8081)
        assert result is False

    @pytest.mark.asyncio
    async def test_uses_bash_c_not_bash_lc(self):
        """GOTCHA: bash -lc mangles %{http_code} due to job-control % parsing."""
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "200", "stderr": "", "exit_code": 0}
        )

        await is_port_serving(mock_client, "sb-abc", 8081)
        call_args = mock_client.exec_command.call_args
        cmd = call_args[0][1]  # second positional arg = cmd list
        assert cmd[0] == "bash"
        assert cmd[1] == "-c"  # NOT "-lc"
        assert "8081" in cmd[2]
        assert "%{http_code}" in cmd[2]

    @pytest.mark.asyncio
    async def test_passes_custom_timeout(self):
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "200", "stderr": "", "exit_code": 0}
        )

        await is_port_serving(mock_client, "sb-abc", 8081, timeout=12.5)
        call_kwargs = mock_client.exec_command.call_args.kwargs
        assert call_kwargs.get("timeout") == 12.5

    @pytest.mark.asyncio
    async def test_default_timeout_is_5s(self):
        from app.tools._sandbox_serve_helpers import is_port_serving

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "200", "stderr": "", "exit_code": 0}
        )

        await is_port_serving(mock_client, "sb-abc", 8081)
        call_kwargs = mock_client.exec_command.call_args.kwargs
        assert call_kwargs.get("timeout") == 5.0


class TestStartStaticHttpServer:
    """start_static_http_server — starts python3 -m http.server in the sandbox."""

    @pytest.mark.asyncio
    async def test_returns_pid_when_requested(self):
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "12345", "stderr": "", "exit_code": 0}
        )

        pid, error = await start_static_http_server(
            mock_client, "sb-abc", 8081, "/home/sandbox"
        )

        assert error is None
        assert pid == 12345

    @pytest.mark.asyncio
    async def test_fire_and_forget_skips_pid_return(self):
        """return_pid=False must NOT trigger the PID-write pipeline."""
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "should-be-ignored", "stderr": "", "exit_code": 0}
        )

        pid, error = await start_static_http_server(
            mock_client,
            "sb-abc",
            8081,
            "/home/sandbox",
            script_name="auto.py",
            log_name="auto.log",
            return_pid=False,
        )

        assert error is None
        assert pid == 0
        # Command sent should NOT include the PID-write + cat pipeline
        call_args = mock_client.exec_command.call_args
        cmd = call_args[0][1]
        cmd_str = cmd[2]
        assert "echo $!" not in cmd_str
        assert ".pid" not in cmd_str
        # The script name and log name are still embedded
        assert "/tmp/auto.py" in cmd_str
        assert "/tmp/auto.log" in cmd_str

    @pytest.mark.asyncio
    async def test_stderr_with_zero_exit_code_is_success(self):
        """Pinned behaviour: stderr alone is NOT an error.  Only exit_code matters.

        This guards against a future change that flips to "any stderr = error"
        and breaks the (common) case where backgrounded processes write harmless
        warnings to stderr after the parent pipeline has returned.
        """
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={
                "stdout": "444",
                "stderr": "nohup: ignoring input",  # harmless warning
                "exit_code": 0,
            }
        )

        pid, error = await start_static_http_server(
            mock_client, "sb-abc", 8081, "/home/sandbox"
        )

        assert error is None
        assert pid == 444

    @pytest.mark.asyncio
    async def test_stderr_with_nonzero_exit_includes_stderr_in_error(self):
        """When exit_code != 0, stderr should appear in the error message
        (truncated to 200 chars) so users can diagnose start failures."""
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={
                "stdout": "",
                "stderr": "python3: can't open file '/tmp/serve': [Errno 2] No such file or directory",
                "exit_code": 2,
            }
        )

        pid, error = await start_static_http_server(
            mock_client, "sb-abc", 8081, "/home/sandbox"
        )

        assert pid == 0
        assert error is not None
        assert "2" in error
        assert "No such file" in error

    @pytest.mark.asyncio
    async def test_stderr_truncation_at_200_chars(self):
        """Long stderr messages are truncated to 200 chars to avoid log spam."""
        from app.tools._sandbox_serve_helpers import start_static_http_server

        long_stderr = "x" * 500
        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "", "stderr": long_stderr, "exit_code": 1}
        )

        _, error = await start_static_http_server(
            mock_client, "sb-abc", 8081, "/home/sandbox"
        )

        assert error is not None
        # Only the first 200 'x's should appear
        assert "x" * 200 in error
        assert "x" * 201 not in error

    @pytest.mark.asyncio
    async def test_default_script_name_is_serve_not_serve_py(self):
        """Pinned behaviour: default script_name is 'serve' (no .py) so the
        PID file lives at /tmp/serve.pid — matching the pre-refactor filename.

        This guards against a future change to script_name='serve.py' default
        which would silently rename /tmp/serve.pid → /tmp/serve.py.pid and
        break any external scripts that read the old path.
        """
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "555", "stderr": "", "exit_code": 0}
        )

        await start_static_http_server(mock_client, "sb-abc", 8081, "/home/sandbox")

        call_args = mock_client.exec_command.call_args
        cmd_str = call_args[0][1][2]
        # Parse the script write path: '> /tmp/<name> && nohup ...'
        match = re.search(r"> /tmp/(\S+) &&", cmd_str)
        assert match is not None, f"Could not parse script path from: {cmd_str}"
        assert match.group(1) == "serve"
        # PID file is at /tmp/serve.pid, NOT /tmp/serve.py.pid
        assert "/tmp/serve.pid" in cmd_str
        assert "/tmp/serve.py" not in cmd_str

    @pytest.mark.asyncio
    async def test_custom_timeout_passed_to_exec(self):
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "666", "stderr": "", "exit_code": 0}
        )

        await start_static_http_server(
            mock_client, "sb-abc", 8081, "/home/sandbox", timeout=12.5
        )

        call_kwargs = mock_client.exec_command.call_args.kwargs
        assert call_kwargs.get("timeout") == 12.5

    @pytest.mark.asyncio
    async def test_default_timeout_is_10s(self):
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "777", "stderr": "", "exit_code": 0}
        )

        await start_static_http_server(mock_client, "sb-abc", 8081, "/home/sandbox")

        call_kwargs = mock_client.exec_command.call_args.kwargs
        assert call_kwargs.get("timeout") == 10.0

    @pytest.mark.asyncio
    async def test_returns_error_on_nonzero_exit(self):
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "", "stderr": "Permission denied", "exit_code": 126}
        )

        pid, error = await start_static_http_server(
            mock_client, "sb-abc", 8081, "/home/sandbox"
        )

        assert pid == 0
        assert error is not None
        assert "126" in error
        assert "Permission denied" in error

    @pytest.mark.asyncio
    async def test_returns_error_on_unparseable_pid(self):
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "not-a-pid", "stderr": "", "exit_code": 0}
        )

        pid, error = await start_static_http_server(
            mock_client, "sb-abc", 8081, "/home/sandbox"
        )

        assert pid == 0
        assert error is not None
        assert "Could not parse PID" in error
        assert "not-a-pid" in error

    @pytest.mark.asyncio
    async def test_fire_and_forget_reports_nonzero_exit(self):
        """Fire-and-forget mode should still surface start-command failures."""
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "", "stderr": "crash", "exit_code": 1}
        )

        pid, error = await start_static_http_server(
            mock_client, "sb-abc", 8081, "/home/sandbox", return_pid=False
        )

        assert pid == 0
        assert error is not None
        assert "1" in error
        assert "crash" in error

    @pytest.mark.asyncio
    async def test_takes_last_line_of_stdout_as_pid(self):
        """The cat /tmp/serve.py.pid prints the PID; if the pipeline
        also echoes the start message, we want the LAST line."""
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "some noise\n54321", "stderr": "", "exit_code": 0}
        )

        pid, error = await start_static_http_server(
            mock_client, "sb-abc", 8081, "/home/sandbox"
        )

        assert error is None
        assert pid == 54321

    @pytest.mark.asyncio
    async def test_script_uses_simple_http_request_handler_with_directory(self):
        """The generated python script must use ``directory=`` kwarg
        so we never need ``os.chdir`` (which would have quoting issues)."""
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "111", "stderr": "", "exit_code": 0}
        )

        await start_static_http_server(
            mock_client, "sb-abc", 9000, "/home/sandbox/subdir"
        )

        call_args = mock_client.exec_command.call_args
        cmd_str = call_args[0][1][2]
        # Embedded python script contains the directory
        assert "/home/sandbox/subdir" in cmd_str
        assert "SimpleHTTPRequestHandler" in cmd_str
        assert "directory=" in cmd_str
        assert "allow_reuse_address" in cmd_str
        assert "9000" in cmd_str

    @pytest.mark.asyncio
    async def test_custom_script_name(self):
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "222", "stderr": "", "exit_code": 0}
        )

        await start_static_http_server(
            mock_client,
            "sb-abc",
            8081,
            "/home/sandbox",
            script_name="custom.py",
            log_name="custom.log",
        )

        call_args = mock_client.exec_command.call_args
        cmd_str = call_args[0][1][2]
        assert "/tmp/custom.py" in cmd_str
        assert "/tmp/custom.log" in cmd_str
        # PID file is named after the script
        assert "/tmp/custom.py.pid" in cmd_str

    @pytest.mark.asyncio
    async def test_quotes_in_directory_are_escaped(self):
        """A path with single quotes must be escaped for the shell."""
        from app.tools._sandbox_serve_helpers import start_static_http_server

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "333", "stderr": "", "exit_code": 0}
        )

        await start_static_http_server(
            mock_client, "sb-abc", 8081, "/home/sandbox/o'malley"
        )

        call_args = mock_client.exec_command.call_args
        cmd_str = call_args[0][1][2]
        # Single quotes escaped as '\\''
        assert "o'\\''malley" in cmd_str


class TestEnsureServingOnPort:
    """ensure_serving_on_port — fire-and-forget convenience wrapper."""

    @pytest.mark.asyncio
    async def test_starts_server_when_not_serving(self):
        from app.tools._sandbox_serve_helpers import ensure_serving_on_port

        mock_client = MagicMock()
        # First call: check_port returns 000 (not serving)
        # Second call: start command succeeds
        mock_client.exec_command = AsyncMock(
            side_effect=[
                {"stdout": "000", "stderr": "", "exit_code": 0},
                {"stdout": "", "stderr": "", "exit_code": 0},
            ]
        )

        # Must not raise, must not return anything
        result = await ensure_serving_on_port(
            mock_client, "sb-abc", 8081, "/home/sandbox"
        )
        assert result is None
        # Both calls were made
        assert mock_client.exec_command.await_count == 2

    @pytest.mark.asyncio
    async def test_is_idempotent_when_already_serving(self):
        """If port 8081 is already serving, do NOT start a second server."""
        from app.tools._sandbox_serve_helpers import ensure_serving_on_port

        mock_client = MagicMock()
        # Only one call: check_port returns 200 (already serving)
        mock_client.exec_command = AsyncMock(
            return_value={"stdout": "200", "stderr": "", "exit_code": 0}
        )

        result = await ensure_serving_on_port(
            mock_client, "sb-abc", 8081, "/home/sandbox"
        )

        assert result is None
        # Only the check happened, no start
        assert mock_client.exec_command.await_count == 1

    @pytest.mark.asyncio
    async def test_swallows_check_port_exceptions(self):
        """If the check itself fails, auto-serve should not raise — the
        surrounding file-write response must not be blocked."""
        from app.tools._sandbox_serve_helpers import ensure_serving_on_port

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            side_effect=ConnectionError("sandboxd down")
        )

        # Must not raise
        result = await ensure_serving_on_port(
            mock_client, "sb-abc", 8081, "/home/sandbox"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_swallows_start_command_exceptions(self):
        """If the start command itself raises, auto-serve must swallow it."""
        from app.tools._sandbox_serve_helpers import ensure_serving_on_port

        mock_client = MagicMock()
        # Check returns 000 (not serving), start raises
        mock_client.exec_command = AsyncMock(
            side_effect=[
                {"stdout": "000", "stderr": "", "exit_code": 0},
                ConnectionError("container died"),
            ]
        )

        # Must not raise
        result = await ensure_serving_on_port(
            mock_client, "sb-abc", 8081, "/home/sandbox"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_fire_and_forget_mode(self):
        """ensure_serving_on_port must NOT request a PID return."""
        from app.tools._sandbox_serve_helpers import ensure_serving_on_port

        mock_client = MagicMock()
        mock_client.exec_command = AsyncMock(
            side_effect=[
                {"stdout": "000", "stderr": "", "exit_code": 0},
                {"stdout": "99999", "stderr": "", "exit_code": 0},
            ]
        )

        await ensure_serving_on_port(mock_client, "sb-abc", 8081, "/home/sandbox")

        # The second call (the start command) must NOT include the PID pipeline
        start_cmd = mock_client.exec_command.call_args_list[1][0][1]
        cmd_str = start_cmd[2]
        assert "echo $!" not in cmd_str

    @pytest.mark.asyncio
    async def test_uses_default_serve_workspace_constant(self):
        """The helper exports DEFAULT_SANDBOX_WORKSPACE='/home/sandbox' so
        consumers don't have to redefine the workspace dir."""
        from app.tools._sandbox_serve_helpers import DEFAULT_SANDBOX_WORKSPACE

        assert DEFAULT_SANDBOX_WORKSPACE == "/home/sandbox"

    @pytest.mark.asyncio
    async def test_uses_default_serve_port_constant(self):
        """The helper exports DEFAULT_SERVE_PORT=8081 so consumers don't
        have to hardcode the port."""
        from app.tools._sandbox_serve_helpers import DEFAULT_SERVE_PORT

        assert DEFAULT_SERVE_PORT == 8081
