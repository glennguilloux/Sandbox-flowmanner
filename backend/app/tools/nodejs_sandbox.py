"""
Code Execution & Development Tools — Node.js Sandbox.

nodejs_sandbox → Run JavaScript/TypeScript code in an isolated subprocess
    with timeout, output capture, and resource limits.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import subprocess
import tempfile
import time
from typing import Any

from pydantic import Field

from app.tools._rlimits import analyze_exit_code, make_preexec_fn
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

DEFAULT_TIMEOUT = int(os.getenv("NODEJS_SANDBOX_TIMEOUT", "30"))
MAX_TIMEOUT = int(os.getenv("NODEJS_SANDBOX_MAX_TIMEOUT", "60"))
MAX_OUTPUT_BYTES = int(os.getenv("NODEJS_SANDBOX_MAX_OUTPUT", "102400"))
MEMORY_LIMIT_MB = int(os.getenv("NODEJS_SANDBOX_MEMORY_MB", "256"))
MAX_CHILD_PROCS = int(os.getenv("NODEJS_SANDBOX_MAX_PROCS", "0"))  # 0 = block fork

# ── Dangerous require denylist ────────────────────────────────────

# Modules blocked entirely — any require/import of these is rejected
_BLOCKED_MODULES: set[str] = {
    "child_process",
    "cluster",
    "worker_threads",
    "vm",
    "repl",
    "dgram",
    "net",
    "tls",
    "dns",
    "http2",
    "inspector",
    "v8",
}

# Methods blocked even on otherwise-allowed modules
# (require() calls to blocked modules are checked dynamically in _is_code_allowed step 2)
_BLOCKED_METHODS: list[str] = [
    r"process\.exit\s*\(",
    r"process\.kill\s*\(",
    r"process\.abort\s*\(",
    r"process\.binding\s*\(",
    r"process\._rawDebug\s*\(",
    r"process\.dlopen\s*\(",
]

# Dangerous fs methods (filesystem writes/deletes)
_BLOCKED_FS_METHODS: list[str] = [
    r"fs\.writeFile(?:Sync)?\s*\(",
    r"fs\.appendFile(?:Sync)?\s*\(",
    r"fs\.unlink(?:Sync)?\s*\(",
    r"fs\.rmdir(?:Sync)?\s*\(",
    r"fs\.rm\s*\(",
    r"fs\.rename(?:Sync)?\s*\(",
    r"fs\.createWriteStream\s*\(",
    r"fs\.chmod(?:Sync)?\s*\(",
    r"fs\.chown(?:Sync)?\s*\(",
    r"fs\.symlink(?:Sync)?\s*\(",
    r"fs\.mkdtemp(?:Sync)?\s*\(",
    r"fs\.truncate(?:Sync)?\s*\(",
    r"fs\.copyFile(?:Sync)?\s*\(",
    r"fs\.link(?:Sync)?\s*\(",
]

# Dangerous eval/new Function patterns
_BLOCKED_CODE_EXEC: list[str] = [
    r"\beval\s*\(",
    r"\bnew\s+Function\s*\(",
    r"\bFunction\s*\(",
    r"\bsetTimeout\s*\(\s*['\"]",  # setTimeout(string)
    r"\bsetInterval\s*\(\s*['\"]",  # setInterval(string)
]

# import() and import declarations — flagged if importing blocked modules
_BLOCKED_IMPORT_PATTERNS: list[str] = (
    [rf"import\s*\(\s*['\"]{re.escape(mod)}" for mod in _BLOCKED_MODULES]
    + [rf"import\s+.*\bfrom\s+['\"]{re.escape(mod)}" for mod in _BLOCKED_MODULES]
    + [rf"import\s+['\"]{re.escape(mod)}" for mod in _BLOCKED_MODULES]
)


def _is_code_allowed(code: str) -> tuple[bool, str | None]:
    """Scan JavaScript/TypeScript code for dangerous imports/patterns.

    Returns (allowed, reason) where reason explains the block if not allowed.
    """
    # 1. Check blocked module imports (static and dynamic)
    for pattern in _BLOCKED_IMPORT_PATTERNS:
        match = re.search(pattern, code)
        if match:
            snippet = match.group(0)[:50]
            return False, f"Blocked module: '{snippet}' is not allowed in sandbox"

    # 2. Check require() calls to blocked modules
    for mod in _BLOCKED_MODULES:
        if re.search(rf"require\s*\(\s*['\"]{re.escape(mod)}['\"]", code):
            return (
                False,
                f"Blocked module: 'require('{mod}')' is not allowed in sandbox",
            )

    # 3. Check blocked methods
    for pattern in _BLOCKED_METHODS:
        match = re.search(pattern, code)
        if match:
            snippet = match.group(0)[:40]
            return False, f"Blocked method: '{snippet}...' is not allowed in sandbox"

    # 4. Check dangerous fs methods (only if they write/delete)
    for pattern in _BLOCKED_FS_METHODS:
        match = re.search(pattern, code)
        if match:
            snippet = match.group(0)[:40]
            return False, f"Blocked fs method: '{snippet}...' is not allowed in sandbox"

    # 5. Check eval / code execution injection
    for pattern in _BLOCKED_CODE_EXEC:
        match = re.search(pattern, code)
        if match:
            snippet = match.group(0)[:40]
            return False, f"Blocked code exec: '{snippet}...' is not allowed in sandbox"

    return True, None


# ── Input ─────────────────────────────────────────────────────────────


class NodeJsSandboxInput(ToolInput):
    code: str = Field(
        ...,
        min_length=1,
        description="JavaScript (or TypeScript) source code to execute",
    )
    language: str = Field(
        "javascript",
        description="Language: 'javascript' or 'typescript'",
    )
    timeout_seconds: int = Field(
        DEFAULT_TIMEOUT,
        ge=1,
        le=MAX_TIMEOUT,
        description=f"Execution timeout in seconds (max {MAX_TIMEOUT}s)",
    )
    stdin: str | None = Field(
        None,
        description="Optional text to pipe to stdin",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class NodeJsSandboxTool(BaseTool):
    """Execute JavaScript/TypeScript code in a resource-limited subprocess."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="nodejs_sandbox",
            name="Node.js Sandbox",
            description=(
                "Run JavaScript and TypeScript code securely isolated from "
                "the host. Supports async/await, console output, and stdin."
            ),
            category="code-execution-and-development",
            input_schema=NodeJsSandboxInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["code", "javascript", "nodejs", "execution", "sandbox"],
            requires_auth=True,
            timeout_seconds=DEFAULT_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = NodeJsSandboxInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        lang = validated.language.lower()
        if lang not in ("javascript", "typescript", "js", "ts"):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unsupported language: '{validated.language}'. Use 'javascript' or 'typescript'.",
            )

        is_typescript = lang in ("typescript", "ts")

        # Scan for dangerous imports/requires before running
        allowed, reason = _is_code_allowed(validated.code)
        if not allowed:
            return ToolResult.error_result(tool_id=self.tool_id, error=reason)

        try:
            result = await self._run_node(
                validated.code,
                is_typescript,
                validated.timeout_seconds,
                validated.stdin,
            )
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("nodejs_sandbox failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── run_node ─────────────────────────────────────────────────

    async def _run_node(
        self,
        code: str,
        is_typescript: bool,
        timeout_seconds: int,
        stdin_text: str | None,
    ) -> dict[str, Any]:
        """Execute JavaScript/TypeScript code in a subprocess."""

        # Wrap in async IIFE to support top-level await
        wrapped_code = (
            "(async () => {\n"
            + code
            + "\n})().catch(e => { console.error(e.message || e); process.exit(1); });"
        )

        # If TypeScript, convert with tsc or ts-node (best-effort)
        if is_typescript:
            # Strip type annotations using a simple heuristic: remove `: type` patterns
            # This is NOT a full TS compiler but handles common cases
            wrapped_code = self._strip_typescript_types(wrapped_code)

        suffix = ".ts" if is_typescript else ".js"
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            prefix="sandbox_",
            delete=False,
        ) as tmp:
            tmp_path = tmp.name
            tmp.write(wrapped_code)
            tmp.flush()

        start_time = time.monotonic()

        try:
            proc = subprocess.run(
                ["node", "--no-warnings", tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                input=stdin_text,
                env=self._sanitized_env(),
                preexec_fn=make_preexec_fn(
                    memory_mb=MEMORY_LIMIT_MB,
                    max_procs=MAX_CHILD_PROCS,
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
                "stderr": f"Execution timed out after {timeout_seconds}s",
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
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

    def _strip_typescript_types(self, code: str) -> str:
        """Rudimentary TypeScript type annotation stripping.

        Handles common patterns: `: Type`, `: Type | Other`, `: Array<T>`,
        `<T>(...)` generics. NOT a full compiler — best-effort for simple scripts.
        """
        import re

        # Remove type annotations after variable declarations
        # let x: string = "hi" → let x = "hi"
        code = re.sub(
            r"\b(let|const|var)\s+(\w+)\s*:\s*[^=;]+(\s*=)", r"\1 \2 \3", code
        )

        # Remove parameter type annotations
        # (name: string, age: number) → (name, age)
        code = re.sub(r"(\w+)\s*:\s*\w+(\s*[,)])", r"\1\2", code)

        # Remove return type annotations on functions
        # function foo(): string { → function foo() {
        code = re.sub(r"\)\s*:\s*\w+(\s*{)", r")\1", code)

        # Remove interface / type declarations (they're not executable)
        code = re.sub(r"\binterface\s+\w+\s*{[^}]*}", "", code)
        code = re.sub(r"\btype\s+\w+\s*=\s*[^;]+;", "", code)

        # Remove generic type parameters
        # <T>(...) → (...)
        code = re.sub(r"<\w+>", "", code)

        return code

    def _sanitized_env(self) -> dict[str, str]:
        """Return a sanitized environment for Node.js subprocess execution."""
        return {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": "/tmp",
            "LANG": "C.UTF-8",
            "NODE_PATH": "",
            "NPM_CONFIG_PREFIX": "/tmp",
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(NodeJsSandboxTool())
