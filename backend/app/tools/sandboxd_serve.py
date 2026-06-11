"""sandboxd_serve — start a dev server inside the sandbox.

Starts a ``python3 -m http.server`` on port 8081 (port 8080 is
reserved defensively — the default python-img template does not use it,
but some legacy templates like react-standard may).  Serves files
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
from app.tools._sandbox_serve_helpers import (
    DEFAULT_SANDBOX_WORKSPACE,
    is_port_serving,
    start_static_http_server,
)
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

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
            "Port to serve on (default 8081). Port 8080 is reserved defensively — the default python-img template does not use it, but some legacy templates (e.g., react-standard) may."
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
                "(port 8080 is reserved defensively — the default python-img template does not use it, "
                "but some legacy templates like react-standard may). The server serves "
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
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        try:
            sandbox_id = validated.sandbox_id or self._resolve_sandbox_id()
            if not sandbox_id:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=("No sandbox available. Call sandboxd_preview first to create one, or pass `sandbox_id`."),
                )

            client = self._get_client()
            port = validated.port

            # ── Step 1: Check if port is already serving ──────────────
            ready = await is_port_serving(client, sandbox_id, port)

            if not ready:
                # ── Step 2: Start a fallback server ───────────────────
                serve_dir = validated.directory or DEFAULT_SANDBOX_WORKSPACE
                server_pid, start_error = await start_static_http_server(client, sandbox_id, port, serve_dir)

                if start_error:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=(f"Failed to start server in sandbox {sandbox_id}: {start_error}"),
                    )

                # Poll until the server is accepting connections (up to 10s)
                for _attempt in range(_SERVE_POLL_ATTEMPTS):
                    await asyncio.sleep(_SERVE_POLL_INTERVAL)
                    ready = await is_port_serving(client, sandbox_id, port)
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
