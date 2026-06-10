"""sandboxd_file_list — list files in the sandbox workspace.

Maps to ``GET /v1/sandboxes/{id}/files?path=&recursive=``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

logger = logging.getLogger(__name__)

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool


class SandboxdFileListInput(ToolInput):
    sandbox_id: str | None = Field(
        default=None,
        description="Sandbox ID. If omitted, uses the current context sandbox.",
    )
    path: str = Field(
        default="",
        description="Relative directory path (empty = workspace root)",
    )
    recursive: bool = Field(
        default=False,
        description="Whether to list files recursively",
    )


class SandboxdFileListTool(BaseTool):
    """List files in the sandbox workspace."""

    def __init__(self) -> None:
        metadata = ToolMetadata(
            tool_id="sandboxd_file_list",
            name="Sandboxd File List",
            description=(
                "List files and directories in the sandbox workspace. "
                "Path is relative to /home/sandbox/workspace/app/ inside the container."
            ),
            category="code-execution-and-development",
            input_schema=SandboxdFileListInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "object"},
                    }
                },
            },
            tags=["sandbox", "file", "list"],
            requires_auth=False,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        try:
            validated = SandboxdFileListInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            sandbox_id = validated.sandbox_id or self._resolve_sandbox_id()
            if not sandbox_id:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error="No sandbox available. Call sandboxd_preview first to create one, or pass `sandbox_id`.",
                )

            if ".." in validated.path:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error="Path must not contain '..'",
                )

            client = self._get_client()
            # Use native GET /files API
            files = await client.list_files(
                sandbox_id,
                path=validated.path,
                recursive=validated.recursive,
            )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={"files": files, "path": validated.path},
            )
        except Exception as e:
            logger.exception("sandboxd_file_list failed")
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


register_tool(SandboxdFileListTool())
