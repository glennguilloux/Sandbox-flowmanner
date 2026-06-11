"""sandboxd_file_write — write files to the sandbox workspace.

Maps to ``PUT /v1/sandboxes/{id}/files?path=<rel>`` with raw body.
Max 25 MiB. Atomic (tmp + rename). Rejects symlinks and ``..``.

After a successful write, best-effort auto-starts a python3 http.server
on port 8081 from /home/sandbox/ so files are immediately accessible.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import Field

from app.tools._sandbox_serve_helpers import (
    DEFAULT_SANDBOX_WORKSPACE,
    DEFAULT_SERVE_PORT,
    ensure_serving_on_port,
)
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class SandboxdFileWriteInput(ToolInput):
    sandbox_id: str | None = Field(
        default=None,
        description="Sandbox ID. If omitted, uses the current context sandbox.",
    )
    path: str = Field(
        ...,
        min_length=1,
        description="Relative file path inside the sandbox workspace (e.g. 'index.html' or 'css/style.css')",
    )
    content: str = Field(
        ...,
        description="File content to write (text, UTF-8)",
    )


class SandboxdFileWriteTool(BaseTool):
    """Write a file to the sandbox workspace."""

    def __init__(self) -> None:
        metadata = ToolMetadata(
            tool_id="sandboxd_file_write",
            name="Sandboxd File Write",
            description=(
                "Write a file to the sandbox workspace. Use this to create "
                "index.html, style.css, app.js, or any project file. "
                "Path is relative to /home/sandbox/ inside the container (the sandbox workspace root). "
                "Subdirectories are created automatically. Atomic write (tmp + rename). Max 25 MiB. "
                "For HTML previews: write all files first, then call sandboxd_serve "
                "to start a dev server and get the preview URL."
            ),
            category="code-execution-and-development",
            input_schema=SandboxdFileWriteInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {"written": {"type": "boolean"}},
            },
            tags=["sandbox", "file", "write"],
            requires_auth=False,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        try:
            validated = SandboxdFileWriteInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        try:
            sandbox_id = validated.sandbox_id or self._resolve_sandbox_id()
            if not sandbox_id:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error="No sandbox available. Call sandboxd_preview first to create one, or pass `sandbox_id`.",
                )

            if ".." in validated.path or validated.path.startswith("/"):
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error="Path must be relative and must not contain '..'",
                )

            client = self._get_client()

            # Ensure parent directory exists (sandboxd native API writes to
            # the exact path; we need dirs to exist first).
            parent = "/".join(validated.path.split("/")[:-1])
            if parent:
                mkdir_result = await client.exec_command(
                    sandbox_id,
                    ["mkdir", "-p", f"/home/sandbox/{parent}"],
                )
                if mkdir_result.get("exit_code", 1) != 0:
                    logger.warning(
                        "sandboxd_file_write: mkdir -p failed for %s: %s",
                        parent,
                        mkdir_result.get("stderr", ""),
                    )

            # Use native PUT /files API (atomic, up to 25 MiB)
            await client.write_file(
                sandbox_id,
                validated.path,
                validated.content,
            )

            # ── Best-effort auto-serve on port 8081 ───────────────────
            # The LLM may forget to call sandboxd_serve.  Auto-start a
            # server on port 8081 (port 8080 is reserved defensively — the default
            # python-img template does not use it, but some legacy templates like
            # react-standard may) so files
            # are immediately accessible after the first write.
            # Fire-and-forget — must not block the file write response.
            try:
                asyncio.create_task(
                    ensure_serving_on_port(
                        client,
                        sandbox_id,
                        DEFAULT_SERVE_PORT,
                        DEFAULT_SANDBOX_WORKSPACE,
                    )
                )
            except Exception:
                logger.debug(
                    "sandboxd_file_write: auto-serve skipped (non-fatal)",
                    exc_info=True,
                )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={"written": True, "path": validated.path},
            )
        except Exception as e:
            logger.exception("sandboxd_file_write failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    @staticmethod
    def _resolve_sandbox_id() -> str | None:
        try:
            from app.tools._sandbox_context import get_current_sandbox_id

            return get_current_sandbox_id()
        except ImportError:
            return None

    @staticmethod
    def _get_client():
        from app.integrations.sandboxd_client import get_sandboxd_client

        return get_sandboxd_client()


register_tool(SandboxdFileWriteTool())
