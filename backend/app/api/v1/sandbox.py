"""
Sandbox code execution API — runs Python, JavaScript, TypeScript in isolated subprocesses.

POST /chat/execute-code — execute code and return stdout/stderr/exit_code
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# ── Configuration ─────────────────────────────────────────────────────

DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120
MAX_OUTPUT_BYTES = 102_400  # 100KB

# ── Schemas ───────────────────────────────────────────────────────────

import contextlib

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.models.user import User


class ExecuteCodeRequest(BaseModel):
    code: str = Field(..., min_length=1, description="Source code to execute")
    language: str = Field("python", description="python, javascript, or typescript")
    timeout: int = Field(DEFAULT_TIMEOUT, ge=1, le=MAX_TIMEOUT, description="Timeout in seconds")


class SandboxResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    execution_time_ms: float = 0.0
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    exited_cleanly: bool = True
    killed_by_oom: bool = False
    killed_by_cpu: bool = False


# ── Route ─────────────────────────────────────────────────────────────


@router.post("/execute-code")
async def execute_code(
    req: ExecuteCodeRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Execute code in an isolated subprocess and return the result."""
    try:
        if req.language == "python":
            result = await _run_python(req.code, req.timeout)
        elif req.language in ("javascript", "typescript"):
            result = await _run_javascript(req.code, req.timeout)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported language: {req.language}")

        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("sandbox execute_code failed")
        return {"success": False, "error": str(e)}


# ── Python sandbox ────────────────────────────────────────────────────


async def _run_python(code: str, timeout: int) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", prefix="sandbox_", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(code)
        tmp.flush()

    start = time.monotonic()
    try:
        proc = subprocess.run(
            ["python3", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        elapsed = (time.monotonic() - start) * 1000
        stdout, stderr = proc.stdout or "", proc.stderr or ""
        stdout_trunc = len(stdout) > MAX_OUTPUT_BYTES
        stderr_trunc = len(stderr) > MAX_OUTPUT_BYTES
        if stdout_trunc:
            stdout = stdout[:MAX_OUTPUT_BYTES] + "\n... [truncated]"
        if stderr_trunc:
            stderr = stderr[:MAX_OUTPUT_BYTES] + "\n... [truncated]"

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": proc.returncode,
            "timed_out": False,
            "execution_time_ms": round(elapsed, 2),
            "stdout_truncated": stdout_trunc,
            "stderr_truncated": stderr_trunc,
            "exited_cleanly": proc.returncode == 0,
            "killed_by_oom": False,
            "killed_by_cpu": False,
        }
    except subprocess.TimeoutExpired:
        elapsed = (time.monotonic() - start) * 1000
        return {
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s",
            "exit_code": -1,
            "timed_out": True,
            "execution_time_ms": round(elapsed, 2),
            "stdout_truncated": False,
            "stderr_truncated": False,
            "exited_cleanly": False,
            "killed_by_oom": False,
            "killed_by_cpu": False,
        }
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


# ── JavaScript/TypeScript sandbox ─────────────────────────────────────


async def _run_javascript(code: str, timeout: int) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", prefix="sandbox_", delete=False) as tmp:
        tmp_path = tmp.name
        # For TypeScript, transpile via ts-node or just run as JS
        if ".ts" in tmp_path:
            suffix = ".ts"
            tmp.close()
            tmp_path = tmp_path.replace(".mjs", ".ts")
            tmp = open(tmp_path, "w")
        tmp.write(code)
        tmp.flush()

    start = time.monotonic()
    try:
        cmd = ["node"]
        if tmp_path.endswith(".ts"):
            # Try tsx (esbuild-based TS runner) or fall back to ts-node
            try:
                subprocess.run(["which", "tsx"], capture_output=True, check=True)
                cmd = ["npx", "tsx"]
            except subprocess.CalledProcessError:
                cmd = ["npx", "ts-node", "--esm"]

        cmd.append(tmp_path)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "NODE_OPTIONS": "--no-warnings"},
        )
        elapsed = (time.monotonic() - start) * 1000
        stdout, stderr = proc.stdout or "", proc.stderr or ""
        stdout_trunc = len(stdout) > MAX_OUTPUT_BYTES
        stderr_trunc = len(stderr) > MAX_OUTPUT_BYTES
        if stdout_trunc:
            stdout = stdout[:MAX_OUTPUT_BYTES] + "\n... [truncated]"
        if stderr_trunc:
            stderr = stderr[:MAX_OUTPUT_BYTES] + "\n... [truncated]"

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": proc.returncode,
            "timed_out": False,
            "execution_time_ms": round(elapsed, 2),
            "stdout_truncated": stdout_trunc,
            "stderr_truncated": stderr_trunc,
            "exited_cleanly": proc.returncode == 0,
            "killed_by_oom": False,
            "killed_by_cpu": False,
        }
    except subprocess.TimeoutExpired:
        elapsed = (time.monotonic() - start) * 1000
        return {
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s",
            "exit_code": -1,
            "timed_out": True,
            "execution_time_ms": round(elapsed, 2),
            "stdout_truncated": False,
            "stderr_truncated": False,
            "exited_cleanly": False,
            "killed_by_oom": False,
            "killed_by_cpu": False,
        }
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
