"""Code Execution & Development Tools — Python Sandbox.

python_sandbox → Execute Python scripts in an isolated subprocess with
    timeout, memory limits, output capture, and import denylist scanning.

⚠️ NOT A SECURITY BOUNDARY (audit B23, §4.3/§9/§12). This tool relies on an
   IMPORT-LEVEL DENYLIST plus regex/string pre-scans only. There is no
   namespace, seccomp, or network-namespace isolation. A determined payload
   can still bypass these checks (ctypes/importlib/__loader__/dunder tricks,
   or modules reachable without a literal `import`). The guard is defense-in-
   depth, not containment. Do not run untrusted or adversarial code assuming
   it is isolated. Real isolation (seccomp/netns) is tracked out of scope.
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


class SecurityError(Exception):
    """Raised when sandbox code violates a hard security gate (audit B23).

    Distinct from normal execution errors so callers cannot confuse a blocked
    bypass attempt with a runtime failure.
    """

# ── Configuration ─────────────────────────────────────────────────────

DEFAULT_TIMEOUT = int(os.getenv("PYTHON_SANDBOX_TIMEOUT", "30"))
MAX_TIMEOUT = int(os.getenv("PYTHON_SANDBOX_MAX_TIMEOUT", "60"))
MAX_OUTPUT_BYTES = int(os.getenv("PYTHON_SANDBOX_MAX_OUTPUT", "102400"))  # 100KB
MEMORY_LIMIT_MB = int(os.getenv("PYTHON_SANDBOX_MEMORY_MB", "256"))
MAX_CHILD_PROCS = int(os.getenv("PYTHON_SANDBOX_MAX_PROCS", "0"))  # 0 = block fork

# ── Dangerous import denylist ─────────────────────────────────────

# Modules blocked entirely — any import of these modules is rejected
_BLOCKED_MODULES: set[str] = {
    "subprocess",
    "shutil",
    "ctypes",
    "socket",
    "signal",
    "pty",
    "fcntl",
    "multiprocessing",
    "concurrent.futures",
    "requests",
    "urllib.request",
    "urllib2",
    "httplib",
    "http.client",
    "pickle",
    "marshal",
    "code",
    "codeop",
    "importlib",
    "imp",
    "gc",
    "sysconfig",
    "distutils",
    "setuptools",
    "pip",
    "ensurepip",
}

# Functions/patterns blocked even if the parent module is allowed
_BLOCKED_FUNCTIONS: list[str] = [
    # Direct code execution
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bcompile\s*\(",
    r"\b__import__\s*\(",
    r"\bglobals\s*\(\)",
    r"\blocals\s*\(\)",
    # Dangerous os methods (os module itself is allowed for os.path)
    r"\bos\.system\s*\(",
    r"\bos\.popen\s*\(",
    r"\bos\.spawn[lvpe]+\s*\(",
    r"\bos\.exec[lvpe]+\s*\(",
    r"\bos\.fork\s*\(",
    r"\bos\.kill\s*\(",
    # sys.exit
    r"\bsys\.exit\s*\(",
    # Dunder access for sandbox escape
    r"\bgetattr\s*\([^)]*,\s*['\"']__",
    r"\._\s*_class_\s*_",
    r"\._\s*_bases_\s*_",
    r"\._\s*_subclasses_\s*_\s*\(",
    r"\._\s*_globals_\s*_",
    r"\._\s*_code_\s*_",
]

# Allowlisted patterns — safe uses of blocked-sounding functions
_ALLOW_EXCEPTIONS: list[str] = [
    r"from\s+os\s+import\s+path",  # os.path is benign
    r"import\s+os\.path",  # import os.path
    r"os\.path\.",  # os.path.* usage
]


def _is_code_allowed(code: str) -> tuple[bool, str | None]:
    """Scan code for dangerous imports/patterns.

    Returns (allowed, reason) where reason explains the block if not allowed.
    """
    # 1. Check for blocked modules via import / from-import
    for mod in sorted(_BLOCKED_MODULES, key=len, reverse=True):
        # import mod
        if re.search(rf"^\s*import\s+{re.escape(mod)}\b", code, re.MULTILINE):
            for exception in _ALLOW_EXCEPTIONS:
                if re.search(exception, code):
                    break
            else:
                return (
                    False,
                    f"Blocked module: 'import {mod}' is not allowed in sandbox",
                )

        # from mod import ...
        if re.search(rf"^\s*from\s+{re.escape(mod)}\s+import", code, re.MULTILINE):
            for exception in _ALLOW_EXCEPTIONS:
                if re.search(exception, code):
                    break
            else:
                return (
                    False,
                    f"Blocked module: 'from {mod} import ...' is not allowed in sandbox",
                )

        # import os, sys — comma-separated
        if re.search(rf"^\s*import\s+.+\b{re.escape(mod)}\b", code, re.MULTILINE):
            for exception in _ALLOW_EXCEPTIONS:
                if re.search(exception, code):
                    break
            else:
                return False, f"Blocked module: '{mod}' is not allowed in sandbox"

    # 2. Check for blocked function calls
    for pattern in _BLOCKED_FUNCTIONS:
        match = re.search(pattern, code)
        if match:
            snippet = match.group(0)[:40]
            return False, f"Blocked pattern: '{snippet}...' is not allowed in sandbox"

    # 3. Check for dynamic import via __import__
    if re.search(r"__import__\s*\(", code):
        return False, "Blocked: __import__() is not allowed in sandbox"

    return True, None


# Bypass-token pre-scan — defense in depth on top of the denylist (audit B23).
# These tokens are how a payload escapes an import-only denylist without ever
# writing a literal `import <blocked>`. They are blocked outright; there is no
# allowlist exception because each is a direct escape primitive.
_SECURITY_PRESCAN_TOKENS: list[str] = [
    "ctypes",
    "importlib",
    "__import__",
    "compile(",
    "__loader__",
]

# sys.modules probing patterns that reach already-loaded escape modules
# (e.g. `sys.modules["subprocess"]`) without an import statement.
_SECURITY_PRESCAN_PATTERNS: list[str] = [
    r"sys\s*\.\s*modules",
]


def _security_prescan(code: str) -> None:
    """Refuse code that uses known denylist-bypass primitives.

    Raises SecurityError if the code contains tokens used to escape an
    import-level denylist (ctypes/importlib/__import__/compile(/__loader__)
    or probes sys.modules for already-loaded escape modules. This is
    additive defense-in-depth; it is NOT a substitute for real isolation.
    """
    for token in _SECURITY_PRESCAN_TOKENS:
        if token in code:
            raise SecurityError(
                f"Blocked by security pre-scan (audit B23): '{token}' is a "
                "known sandbox-bypass primitive and is not allowed"
            )

    for pattern in _SECURITY_PRESCAN_PATTERNS:
        if re.search(pattern, code):
            raise SecurityError(
                "Blocked by security pre-scan (audit B23): sys.modules probing "
                "is a known sandbox-bypass primitive and is not allowed"
            )


# ── Input ─────────────────────────────────────────────────────────────


class PythonSandboxInput(ToolInput):
    code: str = Field(
        ...,
        min_length=1,
        description="Python source code to execute",
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


class PythonSandboxTool(BaseTool):
    """Execute Python code in a resource-limited subprocess."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="python_sandbox",
            name="Python Sandbox",
            description=(
                "Execute Python scripts in an isolated container for math, "
                "data processing, and code execution tasks. Enforces timeout "
                "and memory limits."
            ),
            category="code-execution-and-development",
            input_schema=PythonSandboxInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["code", "python", "execution", "sandbox"],
            requires_auth=True,
            timeout_seconds=DEFAULT_TIMEOUT + 10,  # Tool timeout > code timeout
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        # ⚠️ SECURITY BOUNDARY — NOT A TRUST BOUNDARY (audit B23, §4.3/§9/§12).
        #
        # The sandbox guards code with an IMPORT-LEVEL DENYLIST + regex pre-scan
        # only. There is NO namespace, seccomp, or network-namespace isolation for
        # the executed code — a determined payload can still bypass the checks
        # (e.g. ctypes/importlib/__loader__/dunder tricks, or modules reachable
        # without a literal `import`). Treat this as defense-in-depth, NOT as a
        # security boundary. Do not execute untrusted, adversarial, or
        # third-party-supplied code with the assumption it is contained. Full
        # seccomp/netns isolation is tracked separately and is out of scope here.
        try:
            validated = PythonSandboxInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        try:
            # Scan for dangerous imports before running
            allowed, reason = _is_code_allowed(validated.code)
            if not allowed:
                return ToolResult.error_result(tool_id=self.tool_id, error=reason)

            # Defense-in-depth pre-scan on top of the denylist (audit B23).
            # Refuses code that probes for escape vectors via sys.modules or uses
            # known bypass tokens. Raises SecurityError so callers cannot confuse
            # it with a normal execution error.
            try:
                _security_prescan(validated.code)
            except SecurityError as sec_err:
                return ToolResult.error_result(tool_id=self.tool_id, error=str(sec_err))

            result = await self._run_python(
                validated.code,
                validated.timeout_seconds,
                validated.stdin,
            )
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("python_sandbox failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── run_python ───────────────────────────────────────────────

    async def _run_python(
        self,
        code: str,
        timeout_seconds: int,
        stdin_text: str | None,
    ) -> dict[str, Any]:
        """Execute Python code in a subprocess with resource limits."""
        # Write code to a temp file for cleaner execution
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="sandbox_",
            delete=False,
        ) as tmp:
            tmp_path = tmp.name
            tmp.write(code)
            tmp.flush()

        start_time = time.monotonic()

        try:
            cmd = self._build_command(tmp_path, timeout_seconds)

            proc = subprocess.run(
                cmd,
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

            # Truncate output if too large
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
            # Cleanup temp file
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

    def _build_command(self, script_path: str, timeout: int) -> list[str]:
        """Build the python3 command with resource limits."""
        return [
            "python3",
            "-I",  # Isolated mode — ignore PYTHON* env vars
            "-B",  # Don't write .pyc files
            script_path,
        ]

    def _sanitized_env(self) -> dict[str, str]:
        """Return a sanitized environment for subprocess execution."""
        return {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": "/tmp",
            "LANG": "C.UTF-8",
            "PYTHONPATH": "",
            "PYTHONHOME": "",
            "VIRTUAL_ENV": "",
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(PythonSandboxTool())
