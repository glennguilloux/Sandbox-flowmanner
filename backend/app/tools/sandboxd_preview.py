"""sandboxd_preview — create or get a sandbox environment.

Returns sandbox metadata (id, status, preview_status).  If no sandbox
exists in the current context, automatically creates one so that
standalone chat sessions (not just missions) can build and preview
HTML pages.

IMPORTANT: This tool does NOT return the app preview URL.  The
sandbox runtime URL on port 3000 is NOT your app — it only serves an
empty directory listing.  Call ``sandboxd_serve`` after writing files
to get the actual app preview URL (served on port 8081).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from pydantic import Field

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
            visibility="default_on",
            tool_id="sandboxd_preview",
            name="Sandboxd Preview",
            description=(
                "Create a new sandbox or get status for an existing one. "
                "If no sandbox_id is provided, creates a new sandbox automatically. "
                "Returns sandbox metadata (id, status, preview_status) — "
                "does NOT return the app preview URL. "
                "WARNING: The sandbox runtime URL (port 3000) is NOT your app. "
                "NEVER show the sandboxd_preview URL to the user. "
                "Typical workflow: (1) call this without arguments to create a "
                "sandbox, (2) use sandboxd_file_write to create your files, "
                "(3) use sandboxd_serve to start a dev server on port 8081 "
                "and get the preview URL — sandboxd_serve is the ONLY source of the app preview URL."
            ),
            category="code-execution-and-development",
            input_schema=SandboxdPreviewInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "sandbox_id": {"type": "string"},
                    "status": {"type": "string"},
                    "preview_status": {"type": "string"},
                },
            },
            tags=["sandbox", "preview", "url"],
            requires_auth=False,
            requires_sandbox=False,
            rate_limit_key=None,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        try:
            validated = SandboxdPreviewInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        # Hard wall-clock cap: a wedged sandboxd must never freeze the chat
        # turn. The wrapper converts a timeout into a clean error_result so the
        # agent loop does not retry an unhandled exception forever.
        from app.tools._sandbox_timeout import run_sandbox_tool

        return await run_sandbox_tool(self.tool_id, self._run(validated))

    async def _run(self, validated: SandboxdPreviewInput) -> ToolResult:
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
                    error=("Failed to auto-create a sandbox. sandboxd may be unavailable — check service health."),
                )
            # Store in context so subsequent tool calls reuse it
            self._set_sandbox_id(sandbox_id)
            logger.info("sandboxd_preview: auto-created sandbox %s", sandbox_id)

        # Fast-fail: check if container is dead before polling.
        # The v1 API reports status: "running" even when the Docker
        # container has exited.  The internal API exposes live_state
        # which reflects the actual Docker container status.
        info = await client.get(sandbox_id)
        preview = info.get("preview", {})
        preview_status = preview.get("status", "")

        if preview_status not in ("ready", ""):
            try:
                internal = await client.get_internal(sandbox_id)
                live_state = internal.get("live_state", {})
                container_status = live_state.get("State", {}).get("Status", "")
                if container_status == "exited":
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=(
                            f"Sandbox container exited unexpectedly (sandbox={sandbox_id}). "
                            "The sandbox template may be invalid or missing an entrypoint. "
                            "Create a new sandbox or check sandboxd templates."
                        ),
                    )
            except Exception:
                logger.debug(
                    "sandboxd_preview: internal API check failed, falling through to polling",
                    exc_info=True,
                )

            # Poll for preview readiness (up to 15s)
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

        # NOTE: Deliberately do NOT return the sandbox runtime preview_url.
        # The runtime URL (port 3000) shows an empty directory listing —
        # it is NOT the user's app.  sandboxd_serve is the ONLY tool that
        # returns the correct app preview URL (port 8081).

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "sandbox_id": sandbox_id,
                "status": info.get("status"),
                "preview_status": preview_status,
            },
        )

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
