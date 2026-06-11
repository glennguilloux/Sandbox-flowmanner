"""
Code Execution & Development Tools — Shell Cmd Executor.

shell_cmd_executor → Run system-level bash commands in a resource-limited
    subprocess with safety checks and output capture.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from typing import Any

from pydantic import Field

from app.tools._rlimits import analyze_exit_code, make_preexec_fn
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

DEFAULT_TIMEOUT = int(os.getenv("SHELL_CMD_TIMEOUT", "30"))
MAX_TIMEOUT = int(os.getenv("SHELL_CMD_MAX_TIMEOUT", "120"))
MAX_OUTPUT_BYTES = int(os.getenv("SHELL_CMD_MAX_OUTPUT", "102400"))
WORKING_DIR = os.getenv("SHELL_CMD_WORKDIR", "/tmp")
SHELL_MEMORY_MB = int(os.getenv("SHELL_CMD_MEMORY_MB", "512"))
SHELL_MAX_PROCS = int(os.getenv("SHELL_CMD_MAX_PROCS", "10"))  # shell commands may need subshells

# Commands/patterns that are always blocked for safety
_BLOCKED_PATTERNS: list[str] = [
    r"\brm\s+(-[rRf]+\s+)*[/~]",  # rm -rf / or ~
    r"\bsudo\b",  # sudo
    r"\bchmod\s+777\b",  # chmod 777
    r"\bchown\b",  # chown
    r"\bdd\s+if=",  # dd (disk destroyer)
    r"\bmkfs\.",  # mkfs (format)
    r"\bfdisk\b",  # fdisk
    r"\breboot\b",  # reboot
    r"\bshutdown\b",  # shutdown
    r">\s*/dev/[hs]d",  # redirect to disk device
    r"\bcurl.*\|\s*(ba)?sh\b",  # curl pipe sh
    r"\bwget.*\|\s*(ba)?sh\b",  # wget pipe sh
    r"\b:\(\)\s*\{\s*:\|:&\s*\}\s*;",  # fork bomb
    r"\bgit\s+push\s+--force\b",  # git push --force
    r"\bdocker\s+(rm|prune|system)",  # destructive docker
]


# ── Input ─────────────────────────────────────────────────────────────


class ShellCmdExecutorInput(ToolInput):
    command: str = Field(
        ...,
        min_length=1,
        description="Shell command to execute (bash syntax)",
    )
    timeout_seconds: int = Field(
        DEFAULT_TIMEOUT,
        ge=1,
        le=MAX_TIMEOUT,
        description=f"Execution timeout in seconds (max {MAX_TIMEOUT}s)",
    )
    working_dir: str = Field(
        WORKING_DIR,
        description="Working directory for command execution",
    )
    stdin: str | None = Field(
        None,
        description="Optional text to pipe to stdin",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class ShellCmdExecutorTool(BaseTool):
    """Run bash commands in a secure, resource-limited subprocess.

    Safety features:
    - Blocks dangerous commands (rm -rf, sudo, fork bombs, etc.)
    - Enforces timeout and output size limits
    - Runs in sanitized environment
    - Restricts working directory
    """

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="shell_cmd_executor",
            name="Shell Cmd Executor",
            description=(
                "Run system-level bash commands in an ephemeral secure "
                "environment. Blocks dangerous commands and enforces "
                "timeout and output limits."
            ),
            category="code-execution-and-development",
            input_schema=ShellCmdExecutorInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["code", "shell", "bash", "execution", "cli"],
            requires_auth=True,
            timeout_seconds=DEFAULT_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ShellCmdExecutorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        # Safety check: block dangerous commands
        blocked = self._check_safety(validated.command)
        if blocked:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Command blocked for safety: {blocked}",
            )

        # Validate working directory
        workdir = validated.working_dir
        if not os.path.isdir(workdir):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Working directory not found: {workdir}",
            )

        # Deny access to protected paths
        if not self._is_allowed_path(workdir):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Working directory not allowed: {workdir}",
            )

        try:
            result = await self._run_command(
                validated.command,
                validated.timeout_seconds,
                workdir,
                validated.stdin,
            )
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("shell_cmd_executor failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── safety ──────────────────────────────────────────────────

    def _check_safety(self, command: str) -> str | None:
        """Check if the command matches any blocked patterns. Returns reason or None."""
        cmd_lower = command.lower()

        for pattern in _BLOCKED_PATTERNS:
            if re.search(pattern, cmd_lower):
                return f"Command matches blocked pattern: {pattern}"
        return None

    def _is_allowed_path(self, path: str) -> bool:
        """Prevent access to system directories like /etc, /boot, /sys, /proc."""
        blocked_prefixes = ["/etc", "/boot", "/sys", "/proc", "/dev", "/root"]
        real_path = os.path.realpath(path)
        return all(not (real_path.startswith(prefix + "/") or real_path == prefix) for prefix in blocked_prefixes)

    # ── run_command ─────────────────────────────────────────────

    async def _run_command(
        self,
        command: str,
        timeout_seconds: int,
        workdir: str,
        stdin_text: str | None,
    ) -> dict[str, Any]:
        """Execute a shell command with timeout and output capture."""
        start_time = time.monotonic()

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                input=stdin_text,
                cwd=workdir,
                env=self._sanitized_env(),
                preexec_fn=make_preexec_fn(
                    memory_mb=SHELL_MEMORY_MB,
                    max_procs=SHELL_MAX_PROCS,
                    cpu_seconds=timeout_seconds,
                ),
            )

            elapsed_ms = (time.monotonic() - start_time) * 1000

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""

            stdout_truncated = len(stdout) > MAX_OUTPUT_BYTES
            stderr_truncated = len(stderr) > MAX_OUTPUT_BYTES
            if stdout_truncated:
                stdout = stdout[:MAX_OUTPUT_BYTES] + "\n... [output truncated]"
            if stderr_truncated:
                stderr = stderr[:MAX_OUTPUT_BYTES] + "\n... [output truncated]"

            exit_flags = analyze_exit_code(proc.returncode, stderr)
            return {
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": False,
                "execution_time_ms": round(elapsed_ms, 2),
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                **exit_flags,
            }
        except subprocess.TimeoutExpired:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout_seconds}s",
                "exit_code": -1,
                "timed_out": True,
                "execution_time_ms": round(elapsed_ms, 2),
                "stdout_truncated": False,
                "stderr_truncated": False,
                "exited_cleanly": False,
                "killed_by_signal": False,
                "killed_by_oom": False,
                "killed_by_cpu": False,
                "signal_name": None,
                "signal_number": None,
            }

    def _sanitized_env(self) -> dict[str, str]:
        """Return a sanitized environment with minimal env vars."""
        return {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": "/tmp",
            "USER": "sandbox",
            "LANG": "C.UTF-8",
            "SHELL": "/bin/bash",
            "TERM": "dumb",
            "PWD": WORKING_DIR,
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(ShellCmdExecutorTool())
