"""sandboxd_preview — get or create a sandbox and return its live preview URL.

Returns the preview URL from ``GET /v1/sandboxes/{id}`` (the
``sandbox.preview.url`` field).  If no sandbox exists in the current
context, automatically creates one so that standalone chat sessions
(not just missions) can build and preview HTML pages.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from pydantic import Field

from app.integrations.sandboxd_client import rewrite_sandboxd_url
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class SandboxdPreviewInput(ToolInput):
    """Optional sandbox_id — if omitted, creates a new sandbox automatically."""

    sandbox_id: str | None = Field(
        default=None,
        description=(
            "Sandbox ID to preview. If omitted, creates a new sandbox automatically and returns its preview URL."
        ),
    )


class SandboxdPreviewTool(BaseTool):
    """Get or create a sandbox and return its live preview URL."""

    def __init__(self) -> None:
        metadata = ToolMetadata(
            tool_id="sandboxd_preview",
            name="Sandboxd Preview",
            description=(
                "Get the live preview URL for a sandbox. If no sandbox_id is "
                "provided, creates a new sandbox automatically. "
                "The preview URL is publicly accessible at "
                "https://s-<sandbox_id>-<port>.preview.flowmanner.com. "
                "Always call this after writing HTML files and starting a dev "
                "server to share the live preview with the user. "
                "Typical workflow: (1) call this without arguments to create a "
                "sandbox, (2) use sandboxd_file_write to create your files, "
                "(3) use sandboxd_exec to start a dev server on port 3000, "
                "(4) call this again with the sandbox_id to get the preview URL."
            ),
            category="code-execution-and-development",
            input_schema=SandboxdPreviewInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "sandbox_id": {"type": "string"},
                    "status": {"type": "string"},
                    "preview_url": {"type": "string"},
                },
            },
            tags=["sandbox", "preview", "url"],
            requires_auth=False,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        try:
            validated = SandboxdPreviewInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            client = self._get_client()

            # Resolve sandbox_id: explicit arg > context > auto-create
            raw_id = validated.sandbox_id
            # Some LLMs (DeepSeek) pass the literal string "NEW" instead of
            # omitting the field.  Treat it as empty so auto-create fires.
            if raw_id and raw_id.strip().upper() in ("NEW", "NONE", "NULL"):
                raw_id = None
            sandbox_id = raw_id or self._resolve_sandbox_id()

            if not sandbox_id:
                # Auto-create a sandbox for standalone chat sessions
                sandbox_id = await self._auto_create_sandbox(client)
                if not sandbox_id:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=(
                            "Failed to auto-create a sandbox. sandboxd may be unavailable — check service health."
                        ),
                    )
                # Store in context so subsequent tool calls reuse it
                self._set_sandbox_id(sandbox_id)
                logger.info("sandboxd_preview: auto-created sandbox %s", sandbox_id)

            # Poll for preview readiness (up to 15s)
            info = await client.get(sandbox_id)
            preview = info.get("preview", {})
            preview_status = preview.get("status", "")

            if preview_status not in ("ready", ""):
                for _attempt in range(30):  # 30 × 500ms = 15s max
                    await asyncio.sleep(0.5)
                    try:
                        info = await client.get(sandbox_id)
                        preview = info.get("preview", {})
                        preview_status = preview.get("status", "")
                        if preview_status in ("ready", "error", ""):
                            break
                    except Exception:
                        logger.debug(
                            "sandboxd_preview: poll attempt failed (sandbox may be starting)",
                            exc_info=True,
                        )

            preview_url = rewrite_sandboxd_url(preview.get("url", ""))

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "sandbox_id": sandbox_id,
                    "status": info.get("status"),
                    "preview_url": preview_url,
                    "preview_status": preview_status,
                    "preview": preview,
                },
            )
        except Exception as e:
            logger.exception("sandboxd_preview failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_sandbox_id() -> str | None:
        """Resolve sandbox_id from the current tool context."""
        try:
            from app.tools._sandbox_context import get_current_sandbox_id

            return get_current_sandbox_id()
        except ImportError:
            return None

    @staticmethod
    def _set_sandbox_id(sandbox_id: str | None) -> None:
        """Store sandbox_id in context for subsequent tool calls."""
        try:
            from app.tools._sandbox_context import set_current_sandbox_id

            set_current_sandbox_id(sandbox_id)
        except ImportError:
            pass

    @staticmethod
    def _get_client():
        from app.integrations.sandboxd_client import get_sandboxd_client

        return get_sandboxd_client()

    @staticmethod
    async def _auto_create_sandbox(client) -> str | None:
        """Create a new sandbox for standalone chat usage.

        Returns the sandbox_id or None on failure.
        """
        from app.config import settings

        try:
            project_id = f"chat-{uuid4().hex[:12]}"
            result = await client.create(
                project_id=project_id,
                user_id="chat-standalone",
                template=settings.SANDBOXD_DEFAULT_TEMPLATE,
            )
            return result.get("id")
        except Exception:
            logger.exception("sandboxd_preview: auto-create failed")
            return None


register_tool(SandboxdPreviewTool())
