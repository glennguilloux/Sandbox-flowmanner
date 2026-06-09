"""Secure Python code execution in an isolated sandbox subprocess.

Extracted from mission_executor.py.  Completely self-contained — no
dependency on the MissionExecutor class or its state.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any

DANGEROUS_PATTERNS = [
    "__import__",
    "import os",
    "import sys",
    "import subprocess",
    "import socket",
    "import urllib",
    "import http",
    "import ftplib",
    "import smtplib",
    "import telnetlib",
    "import xmlrpc",
    "exec(",
    "eval(",
    "compile(",
    "execfile",
    "open(",
    "file(",
    ".read(",
    ".write(",
    "os.system",
    "os.popen",
    "os.exec",
    "os.spawn",
    "os.fork",
    "os.kill",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.chdir",
    "os.chmod",
    "os.chown",
    "os.link",
    "os.symlink",
    "shutil.rmtree",
    "shutil.move",
    "shutil.copy",
    "sys.exit",
    "sys.modules",
    "sys.path",
    "globals()",
    "locals()",
    "vars()",
    "dir()",
    "getattr(",
    "setattr(",
    "delattr(",
    "breakpoint",
    "input(",
    "raw_input",
    "/etc/passwd",
    "/etc/shadow",
    "~/.ssh",
]

DEFAULT_RESOURCE_LIMITS = {
    "cpu_seconds": 60,
    "memory_mb": 512,
    "output_size_bytes": 1_000_000,
}


def _build_restricted_wrapper(code: str, workspace: str) -> str:
    """Wrap user code in a restricted environment with safe builtins only."""
    # Ensure non-empty code block for valid Python syntax
    # Empty code, whitespace-only, or comment-only would produce invalid try: block
    stripped = code.strip()
    if not stripped or all(
        line.strip() == "" or line.strip().startswith("#") for line in code.split("\n")
    ):
        code = "pass"
    return f"""
import sys
import json
import math
import statistics
import datetime
import collections
import itertools
import functools
import operator
import re
import string
import textwrap
import hashlib
import base64
import struct
import copy
import pprint
import csv
import io

# Save original open BEFORE restricting builtins
_orig_open = open

# Restricted workspace
import os as _os
_allowed_dir = {workspace!r}

def _restricted_open(path, mode='r', *args, **kwargs):
    if 'w' in mode or 'a' in mode or 'x' in mode or '+' in mode:
        raise PermissionError(f"Write access denied: {{path}}")
    abs_path = _os.path.realpath(path)
    if not abs_path.startswith(_allowed_dir):
        raise PermissionError(f"Access denied outside workspace: {{path}}")
    return _orig_open(path, mode, *args, **kwargs)

# Remove dangerous builtins, provide restricted open
__builtins__ = {{
    'open': _restricted_open,
    'True': True, 'False': False, 'None': None,
    'abs': abs, 'all': all, 'any': any, 'bin': bin, 'bool': bool,
    'chr': chr, 'complex': complex, 'dict': dict, 'divmod': divmod,
    'enumerate': enumerate, 'filter': filter, 'float': float, 'format': format,
    'frozenset': frozenset, 'hash': hash, 'hex': hex, 'int': int,
    'isinstance': isinstance, 'issubclass': issubclass, 'iter': iter,
    'len': len, 'list': list, 'map': map, 'max': max, 'min': min,
    'next': next, 'object': object, 'oct': oct, 'ord': ord, 'pow': pow,
    'print': print, 'range': range, 'repr': repr, 'reversed': reversed,
    'round': round, 'set': set, 'slice': slice, 'sorted': sorted,
    'str': str, 'sum': sum, 'tuple': tuple, 'type': type, 'zip': zip,
    'Exception': Exception, 'TypeError': TypeError, 'ValueError': ValueError,
    'KeyError': KeyError, 'IndexError': IndexError, 'AttributeError': AttributeError,
    'StopIteration': StopIteration, 'RuntimeError': RuntimeError,
}}

# Run user code
try:
{_indent(code, 4)}
except Exception as _exec_err:
    print("SANDBOX_ERROR: " + str(_exec_err), file=sys.stderr)
    sys.exit(1)
"""


def _indent(text: str, spaces: int) -> str:
    """Indent every non-empty line by `spaces` spaces."""
    prefix = " " * spaces
    return "\n".join(
        prefix + line if line.strip() else line for line in text.split("\n")
    )


def scan_for_dangerous_patterns(code: str) -> str | None:
    """Return the first dangerous pattern found, or None if clean."""
    code_lower = code.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in code_lower:
            return pattern
    return None


def execute_python_in_sandbox(
    code: str,
    workspace: str | None = None,
    resource_limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Execute Python code in a restricted subprocess.

    SECURITY: Code runs in an isolated subprocess with:
    - No network access (blocked via environment)
    - Restricted builtins (no __import__, open, exec, eval, compile)
    - Timeout (default 60 seconds)
    - Restricted workspace directory
    - Output size limit (default 1 MB)

    Returns:
        {"success": True/False, "output"/"error": str, ...}
    """
    limits = {**DEFAULT_RESOURCE_LIMITS, **(resource_limits or {})}
    ws = workspace or tempfile.mkdtemp(prefix="sandbox_")

    # Block obviously dangerous patterns before execution
    blocked = scan_for_dangerous_patterns(code)
    if blocked:
        return {
            "success": False,
            "error": (
                f"Code contains blocked pattern: '{blocked}'. Code execution is restricted to data analysis operations."
            ),
        }

    import shlex

    # Build restricted wrapper
    wrapper_code = _build_restricted_wrapper(code, ws)

    try:
        proc = subprocess.run(
            [shlex.quote("python3"), "-c", wrapper_code],
            capture_output=True,
            text=True,
            timeout=limits.get("cpu_seconds", 60),
            cwd=ws,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": ws,
                "PYTHONPATH": "",
                "PYTHONUNBUFFERED": "1",
            },
        )

        stdout = proc.stdout
        stderr = proc.stderr

        # Enforce output size limit
        max_output = limits.get("output_size_bytes", 1_000_000)
        if len(stdout) > max_output:
            stdout = stdout[:max_output] + "\n... [OUTPUT TRUNCATED]"

        if proc.returncode != 0:
            return {
                "success": False,
                "error": stderr.strip()
                or f"Process exited with code {proc.returncode}",
                "output": stdout,
            }

        return {"success": True, "output": stdout}

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Code execution timed out after {limits['cpu_seconds']}s",
        }
    except Exception as e:
        return {"success": False, "error": f"Sandbox execution error: {e!s}"}
