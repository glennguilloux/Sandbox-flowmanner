"""sandboxd_serve — start a dev server inside the sandbox.

Starts an HTTP server in the background on the given port (default 3000)
that serves files from the sandbox workspace directory.  Polls until the
server is accepting connections, then returns the preview URL.

This tool eliminates the need for the LLM to manually craft
``sandboxd_exec`` calls with ``nohup`` + ``cd`` + ``--directory`` flags —
the exact commands that caused the "empty preview" bug when the LLM
served from the wrong directory.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import Field

from app.integrations.sandboxd_client import rewrite_sandboxd_url
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# The sandbox workspace inside the container.  This is where
# sandboxd_file_write puts files and where the template's dev server
# (Vite, npm run dev, etc.) should serve from.
_WORKSPACE_DIR = "/home/sandbox/workspace/app"


class SandboxdServeInput(ToolInput):
    sandbox_id: str | None = Field(
        default=None,
        description="Sandbox ID. If omitted, uses the current context sandbox.",
    )
    port: int = Field(
        default=3000,
        ge=1,
        le=65535,
        description="Port to serve on (default 3000).",
    )
    directory: str | None = Field(
        default=None,
        description=(
            "Directory to serve from inside the container. "
            "Defaults to /home/sandbox/workspace/app (the sandbox workspace)."
        ),
    )


class SandboxdServeTool(BaseTool):
    """Start a dev server inside the sandbox and return the preview URL."""

    def __init__(self) -> None:
        metadata = ToolMetadata(
            tool_id="sandboxd_serve",
            name="Sandboxd Serve",
            description=(
                "Start a static file server inside the sandbox on the given port "
                "(default 3000). The server serves files from the sandbox workspace "
                "(/home/sandbox/workspace/app) so HTML files written with "
                "sandboxd_file_write are accessible. Polls until the server is "
                "accepting connections, then returns the preview URL. "
                "Typical workflow: (1) sandboxd_preview to create sandbox, "
                "(2) sandboxd_file_write to create files, "
                "(3) sandboxd_serve to start the server and get the preview URL. "
                "That's it — 3 tool calls total."
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
            serve_dir = validated.directory or _WORKSPACE_DIR

            # Start the server in the background using nohup + python3 http.server.
            # We use python3 because it's guaranteed to exist in the sandbox image.
            # The command:
            #   0. Kill any existing process on the port (e.g. template dev server)
            #   1. cd into the serve directory
            #   2. Start python3 -m http.server in the background with nohup
            #   3. Write the PID to /tmp/serve.pid so we can report it
            #   4. Redirect output to /tmp/serve.log for debugging
            start_cmd = [
                "bash",
                "-lc",
                (
                    f"fuser -k {port}/tcp 2>/dev/null; "
                    f"cd {serve_dir} && "
                    f"nohup python3 -m http.server {port} "
                    f"> /tmp/serve.log 2>&1 & "
                    f"echo $! > /tmp/serve.pid && "
                    f"cat /tmp/serve.pid"
                ),
            ]

            result = await client.exec_command(sandbox_id, start_cmd, timeout=10.0)
            exit_code = result.get("exit_code", 1)
            if exit_code != 0:
                stderr = result.get("stderr", "")
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Failed to start server (exit_code={exit_code}): {stderr}",
                )

            # Extract PID from stdout
            pid_str = result.get("stdout", "").strip().split("\n")[-1]
            try:
                server_pid = int(pid_str)
            except (ValueError, TypeError):
                server_pid = 0

            # Poll until the server is accepting connections (up to 10s)
            ready = False
            for _attempt in range(20):  # 20 × 500ms = 10s max
                await asyncio.sleep(0.5)
                check_cmd = [
                    "bash",
                    "-lc",
                    f"curl -sf -o /dev/null -w '%{{http_code}}' http://localhost:{port}/ 2>/dev/null || echo '000'",
                ]
                check_result = await client.exec_command(
                    sandbox_id, check_cmd, timeout=5.0
                )
                check_output = check_result.get("stdout", "").strip().strip("'")
                if check_output in ("200", "301", "302", "304"):
                    ready = True
                    break

            # Build the preview URL
            # The URL format is: https://s-<sandbox_id>-<port>.preview.flowmanner.com
            raw_preview_url = f"http://s-{sandbox_id}-{port}.preview.localhost"
            preview_url = rewrite_sandboxd_url(raw_preview_url)

            status = "ready" if ready else "started"

            if not ready:
                logger.warning(
                    "sandboxd_serve: server started (pid=%s) but not accepting "
                    "connections after 10s polling. Check /tmp/serve.log inside sandbox.",
                    server_pid,
                )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "sandbox_id": sandbox_id,
                    "port": port,
                    "preview_url": preview_url,
                    "server_pid": server_pid,
                    "status": status,
                },
            )
        except Exception as e:
            logger.exception("sandboxd_serve failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── Helpers ────────────────────────────────────────────────────────

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
