"""sandboxd_serve — start a dev server inside the sandbox.

Starts a ``python3 -m http.server`` on port 8081 (port 8080 is
used by the sandbox template's built-in dev server).  Serves files
from the sandbox workspace root (``/home/sandbox/``).  Polls until the server is accepting
connections, then returns the preview URL.

This tool eliminates the need for the LLM to manually craft
``sandboxd_exec`` calls with ``nohup`` + ``cd`` + ``--directory`` flags.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import Field

from app.integrations.sandboxd_client import rewrite_sandboxd_url
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# The sandbox workspace root inside the container.  The PUT /files API
# writes paths relative to this directory (e.g. path="index.html" puts
# the file at /home/sandbox/index.html).
_WORKSPACE_DIR = "/home/sandbox"

# Number of poll attempts × interval after starting the fallback server.
_SERVE_POLL_ATTEMPTS = 20  # 20 × 0.5 s = 10 s max
_SERVE_POLL_INTERVAL = 0.5  # seconds


class SandboxdServeInput(ToolInput):
    sandbox_id: str | None = Field(
        default=None,
        description="Sandbox ID. If omitted, uses the current context sandbox.",
    )
    port: int = Field(
        default=8081,
        ge=1,
        le=65535,
        description=(
            "Port to serve on (default 8081). Port 8080 is used by the sandbox template's built-in dev server."
        ),
    )
    directory: str | None = Field(
        default=None,
        description=(
            "Directory to serve from inside the container. Defaults to /home/sandbox/ (the sandbox workspace root)."
        ),
    )


class SandboxdServeTool(BaseTool):
    """Ensure a dev server is running inside the sandbox and return the preview URL."""

    def __init__(self) -> None:
        metadata = ToolMetadata(
            tool_id="sandboxd_serve",
            name="Sandboxd Serve",
            description=(
                "Start a static file server inside the sandbox on port 8081 "
                "(port 8080 is used by the sandbox template). The server serves "
                "files from /home/sandbox/ so files written with sandboxd_file_write "
                "are accessible at the preview URL. Returns the preview URL directly. "
                "Typical workflow: (1) sandboxd_preview to create sandbox, "
                "(2) sandboxd_file_write to write files, "
                "(3) sandboxd_serve to get the preview URL. That's it — 3 tool calls."
            ),
            category="code-execution-and-development",
            input_schema=SandboxdServeInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "sandbox_id": {"type": "string"},
                    "port": {"type": "integer"},
                    "preview_url": {"type": "string"},
                    "server_pid": {"type": "integer"},
                    "status": {"type": "string"},
                },
            },
            tags=["sandbox", "serve", "preview", "server"],
            requires_auth=False,
            timeout_seconds=45,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        try:
            validated = SandboxdServeInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            sandbox_id = validated.sandbox_id or self._resolve_sandbox_id()
            if not sandbox_id:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=(
                        "No sandbox available. Call sandboxd_preview first to create one, or pass `sandbox_id`."
                    ),
                )

            client = self._get_client()
            port = validated.port

            # ── Step 1: Check if port is already serving ──────────────
            ready = await self._check_port(client, sandbox_id, port)

            if not ready:
                # ── Step 2: Start a fallback server ───────────────────
                serve_dir = validated.directory or _WORKSPACE_DIR
                server_pid, start_error = await self._start_fallback_server(
                    client, sandbox_id, port, serve_dir
                )

                if start_error:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=(
                            f"Failed to start server in sandbox {sandbox_id}: {start_error}"
                        ),
                    )

                # Poll until the server is accepting connections (up to 10s)
                for _attempt in range(_SERVE_POLL_ATTEMPTS):
                    await asyncio.sleep(_SERVE_POLL_INTERVAL)
                    ready = await self._check_port(client, sandbox_id, port)
                    if ready:
                        break
            else:
                server_pid = 0  # Already running — we don't know the PID

            if not ready:
                logger.warning(
                    "sandboxd_serve: server not accepting connections after 10s polling (sandbox=%s, port=%s).",
                    sandbox_id,
                    port,
                )
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=(
                        f"Server on port {port} is not accepting connections in sandbox "
                        f"{sandbox_id}. The server may have crashed or failed to start. "
                        f"Check that the files are valid and try again."
                    ),
                )

            raw_preview_url = f"http://s-{sandbox_id}-{port}.preview.localhost"
            preview_url = rewrite_sandboxd_url(raw_preview_url)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "sandbox_id": sandbox_id,
                    "port": port,
                    "preview_url": preview_url,
                    "server_pid": server_pid,
                    "status": "ready",
                },
            )
        except Exception as e:
            logger.exception("sandboxd_serve failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    async def _check_port(client, sandbox_id: str, port: int) -> bool:
        """Return True if the port is accepting HTTP connections."""
        # NOTE: ``bash -c`` (not ``bash -lc``) — login shells treat ``%``
        # as a job-control specifier, which silently mangles the
        # ``%{http_code}`` curl format string.
        check_cmd = [
            "bash",
            "-c",
            f"curl -sf -o /dev/null -w '%{{http_code}}' http://localhost:{port}/ 2>/dev/null || echo '000'",
        ]
        result = await client.exec_command(sandbox_id, check_cmd, timeout=5.0)
        output = result.get("stdout", "").strip().strip("'")
        return output in ("200", "301", "302", "304")

    @staticmethod
    async def _start_fallback_server(
        client, sandbox_id: str, port: int, serve_dir: str
    ) -> tuple[int, str | None]:
        """Start a python3 http.server as a fallback.

        Returns ``(pid, error)`` where ``error`` is ``None`` on success
        and a human-readable message if the start command failed.
        """
        # Write a serve script to /tmp/serve.py to avoid quoting issues.
        # Uses SO_REUSEADDR so it can bind even if the port is in TIME_WAIT.
        # Uses SimpleHTTPRequestHandler(directory=...) instead of os.chdir
        # to avoid path quoting issues.
        lines = [
            "import http.server, socketserver",
            "class H(http.server.SimpleHTTPRequestHandler):",
            "    def __init__(self, *a, **kw):",
            f"        super().__init__(*a, directory='{serve_dir}', **kw)",
            "socketserver.TCPServer.allow_reuse_address = True",
            f"s = socketserver.TCPServer(('0.0.0.0', {port}), H)",
            f"print('Serving on :{port} from {serve_dir}')",
            "s.serve_forever()",
        ]
        script_content = "\n".join(lines) + "\n"

        # Escape for single-quoted shell string
        escaped = script_content.replace("'", "'\\''")

        start_cmd = [
            "bash",
            "-c",
            f"echo '{escaped}' > /tmp/serve.py && nohup python3 /tmp/serve.py > /tmp/serve.log 2>&1 & echo $! > /tmp/serve.pid && cat /tmp/serve.pid",
        ]

        result = await client.exec_command(sandbox_id, start_cmd, timeout=10.0)

        # Check exit code — the echo+nohup pipeline should exit 0.
        exit_code = result.get("exit_code", 1)
        if exit_code != 0:
            stderr = result.get("stderr", "").strip()
            error_msg = f"Start command exited with code {exit_code}"
            if stderr:
                error_msg += f": {stderr[:200]}"
            return 0, error_msg

        pid_str = result.get("stdout", "").strip().split("\n")[-1]
        try:
            pid = int(pid_str)
        except (ValueError, TypeError):
            return 0, f"Could not parse PID from output: {pid_str!r}"
        return pid, None

    @staticmethod
    def _resolve_sandbox_id() -> str | None:
        """Resolve sandbox_id from the current tool context (ContextVar)."""
        try:
            from app.tools._sandbox_context import get_current_sandbox_id

            return get_current_sandbox_id()
        except ImportError:
            return None

    @staticmethod
    def _get_client():
        from app.integrations.sandboxd_client import get_sandboxd_client

        return get_sandboxd_client()


register_tool(SandboxdServeTool())
