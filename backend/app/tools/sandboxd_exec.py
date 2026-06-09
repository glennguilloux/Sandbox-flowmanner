"""sandboxd_exec — execute code in an isolated Docker container.

Uses the sandboxd internal exec endpoint (``POST /sandbox/{id}/exec``)
which is reachable because FlowManner and sandboxd run on the same host.

For quick one-shot snippets, agents should prefer ``python_sandbox`` or
``nodejs_sandbox``.  Use ``sandboxd_exec`` when you need multi-file
projects, dev servers, or persistent workspaces.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from pydantic import Field

logger = logging.getLogger(__name__)

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

# ── Language → command mapping ─────────────────────────────────────────

_LANG_CMDS: dict[str, list[str]] = {
    "python": ["python3", "-c"],
    "node": ["node", "-e"],
    "bash": ["bash", "-c"],
    "go": ["go", "run", "/dev/stdin"],
}


# ── Input ─────────────────────────────────────────────────────────────


class SandboxdExecInput(ToolInput):
    code: str = Field(..., description="Source code to execute")
    language: str = Field(
        default="python",
        description="Runtime: python | node | bash | go",
    )
    timeout_seconds: int = Field(
        default=60, ge=5, le=300, description="Execution timeout (5-300s)"
    )


# ── Tool ──────────────────────────────────────────────────────────────


class SandboxdExecTool(BaseTool):
    """Execute code in an isolated Docker container via sandboxd."""

    def __init__(self) -> None:
        metadata = ToolMetadata(
            tool_id="sandboxd_exec",
            name="Sandboxd Exec",
            description=(
                "Execute a shell command inside an isolated Docker sandbox. "
                "Use this for multi-file projects, frontend apps, or anything "
                "that needs a real filesystem and dev server. "
                "Commands run with bash -lc for proper shell environment. "
                "PREFER this over python_sandbox/nodejs_sandbox for: "
                "building HTML pages, React apps, Python web servers, or any "
                "multi-file project that should be previewed at a live URL. "
                "Typical workflow: (1) sandboxd_file_write to create files, "
                "(2) sandboxd_exec to start a dev server, "
                "(3) sandboxd_preview to get the live preview URL."
            ),
            category="code-execution-and-development",
            input_schema=SandboxdExecInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "exit_code": {"type": "integer"},
                },
            },
            tags=["sandbox", "code", "execution", "docker"],
            requires_auth=False,
            timeout_seconds=90,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        try:
            validated = SandboxdExecInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        lang = validated.language.lower()
        if lang not in _LANG_CMDS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unsupported language '{lang}'. Supported: {', '.join(_LANG_CMDS)}",
            )

        try:
            sandbox_id = self._resolve_sandbox_id()
            if not sandbox_id:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=(
                        "No sandbox available for this mission. "
                        "sandboxd may be unavailable — use python_sandbox "
                        "or nodejs_sandbox instead."
                    ),
                )

            client = self._get_client()

            # Build command array
            cmd_parts = _LANG_CMDS[lang]
            if lang == "go":
                # Go requires a file — use base64 to avoid shell-escaping issues
                b64 = base64.b64encode(validated.code.encode()).decode()
                cmd = [
                    "bash",
                    "-c",
                    f"echo {b64} | base64 -d > /tmp/main.go && go run /tmp/main.go",
                ]
            else:
                cmd = [*cmd_parts, validated.code]

            result = await client.exec_command(sandbox_id, cmd)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "exit_code": result.get("exit_code", 0),
                },
            )
        except Exception as e:
            logger.exception("sandboxd_exec failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_sandbox_id() -> str | None:
        """Resolve sandbox_id from the current tool context.

        In Phase 1, the mission executor passes sandbox_id into the
        tool context.  Returns None if no sandbox is available.
        """
        # This will be populated by the mission executor wiring (Phase 1.8).
        # For now, import lazily to avoid circular deps.
        try:
            from app.tools._sandbox_context import get_current_sandbox_id

            return get_current_sandbox_id()
        except ImportError:
            return None

    @staticmethod
    def _get_client():
        from app.integrations.sandboxd_client import get_sandboxd_client

        return get_sandboxd_client()


# ── Register ──────────────────────────────────────────────────────────

register_tool(SandboxdExecTool())
