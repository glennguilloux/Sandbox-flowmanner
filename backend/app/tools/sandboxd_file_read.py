"""sandboxd_file_read — read files from the sandbox workspace.

Maps to ``GET /v1/sandboxes/{id}/files/content?path=<rel>``.
File reads return raw text, max 2 MiB.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

logger = logging.getLogger(__name__)

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool


class SandboxdFileReadInput(ToolInput):
    sandbox_id: str | None = Field(
        default=None,
        description="Sandbox ID. If omitted, uses the current context sandbox.",
    )
    path: str = Field(
        ...,
        min_length=1,
        description="Relative file path inside the sandbox workspace",
    )


class SandboxdFileReadTool(BaseTool):
    """Read a file from the sandbox workspace."""

    def __init__(self) -> None:
        metadata = ToolMetadata(
            visibility="default_on",
            tool_id="sandboxd_file_read",
            name="Sandboxd File Read",
            description=(
                "Read a file from the sandbox workspace. "
                "Path is relative to /home/sandbox/workspace/app/ inside the container. "
                "Max file size: 2 MiB."
            ),
            category="code-execution-and-development",
            input_schema=SandboxdFileReadInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {"content": {"type": "string"}},
            },
            tags=["sandbox", "file", "read"],
            requires_auth=False,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        try:
            validated = SandboxdFileReadInput(**input_data)
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
            # Use native GET /files/content API (up to 2 MiB)
            content = await client.read_file(sandbox_id, validated.path)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={"content": content, "path": validated.path},
            )
        except Exception as e:
            logger.exception("sandboxd_file_read failed")
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


register_tool(SandboxdFileReadTool())
