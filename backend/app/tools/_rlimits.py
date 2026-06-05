"""
Shared resource-limit utility for code execution tools.

Provides make_preexec_fn() which creates a preexec_fn closure that sets
RLIMIT_AS (memory), RLIMIT_NPROC (fork-bomb prevention), and RLIMIT_CPU
(CPU time) via resource.setrlimit(). Runs in the child process after fork,
before exec.

Also provides analyze_exit_code() which inspects a subprocess return code
and stderr to detect resource-limit kills (OOM, CPU timeout, segfault, etc.)
so callers can surface why a process was terminated.

Usage:
    from app.tools._rlimits import make_preexec_fn, analyze_exit_code

    proc = subprocess.run(
        ["python3", script_path],
        preexec_fn=make_preexec_fn(memory_mb=256, max_procs=0, cpu_seconds=30),
        ...
    )
    flags = analyze_exit_code(proc.returncode, proc.stderr or "")

RLIMIT_CPU measures CPU time (not wall-clock), so a sleeping process won't
trigger it. Use subprocess.run(timeout=...) for wall-clock enforcement in
addition to this CPU rlimit.

Rlimits are inherited by child processes, so a shell pipeline (a | b | c)
shares the cumulative CPU budget across all three.

prctl(PR_SET_PDEATHSIG, SIGKILL) ensures that if the parent process dies
unexpectedly (e.g., OOM kill, crash, SIGKILL), the child is immediately
terminated rather than becoming an orphan.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import resource
import signal
from typing import Any

# ── Module-level libc handle for prctl ────────────────────────────

_PR_SET_PDEATHSIG = 1  # prctl op: set signal sent to child when parent dies

# Cached at import time; prctl is only available on Linux.
# The try/except inside _set_limits handles the case where it's unavailable.
try:
    _LIBC = ctypes.CDLL("libc.so.6", use_errno=True)
except (OSError, AttributeError):
    _LIBC = None

DEFAULT_MEMORY_MB = int(os.getenv("SANDBOX_DEFAULT_MEMORY_MB", "256"))
DEFAULT_MAX_PROCS = int(os.getenv("SANDBOX_DEFAULT_MAX_PROCS", "0"))
DEFAULT_CPU_SECONDS = 30


def make_preexec_fn(
    memory_mb: int = DEFAULT_MEMORY_MB,
    max_procs: int = DEFAULT_MAX_PROCS,
    cpu_seconds: int = DEFAULT_CPU_SECONDS,
):
    """Create a preexec_fn that sets rlimits to prevent resource exhaustion.

    Args:
        memory_mb: Virtual memory limit in MB. 0 disables the limit.
        max_procs: Max child processes. 0 blocks all forks. -1 disables.
        cpu_seconds: CPU time limit in seconds. 0 disables the limit.

    Returns:
        A callable suitable for subprocess.run(preexec_fn=...).
    """
    # Convert to rlimit-compatible values
    mem_bytes = memory_mb * 1024 * 1024 if memory_mb > 0 else resource.RLIM_INFINITY
    soft_nproc = max_procs if max_procs >= 0 else resource.RLIM_INFINITY
    hard_nproc = max_procs if max_procs >= 0 else resource.RLIM_INFINITY
    soft_cpu = cpu_seconds if cpu_seconds > 0 else resource.RLIM_INFINITY

    def _set_limits():
        # Parent-death signal — kill this child if the parent dies
        with contextlib.suppress(AttributeError, OSError):
            _LIBC.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL)

        # Memory (address space)
        with contextlib.suppress(ValueError, OSError, AttributeError):
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

        # Process count (fork-bomb prevention)
        with contextlib.suppress(ValueError, OSError, AttributeError):
            resource.setrlimit(resource.RLIMIT_NPROC, (soft_nproc, hard_nproc))

        # CPU time
        with contextlib.suppress(ValueError, OSError, AttributeError):
            resource.setrlimit(resource.RLIMIT_CPU, (soft_cpu, soft_cpu))

    return _set_limits


# ── Exit code analysis ───────────────────────────────────────────

# Common Linux signal numbers
_SIGNAL_NAMES: dict[int, str] = {
    1: "SIGHUP",
    2: "SIGINT",
    6: "SIGABRT",
    9: "SIGKILL",
    11: "SIGSEGV",
    15: "SIGTERM",
    24: "SIGXCPU",
    25: "SIGXFSZ",
    31: "SIGSYS",
}

# Patterns in stderr that suggest the OOM killer
_OOM_STDERR_PATTERNS = [
    "out of memory",
    "killed",
    "memoryerror",
    "cannot allocate memory",
    "allocation failed",
    "nomem",
    "memory limit exceeded",
    "malloc",
]


def analyze_exit_code(returncode: int, stderr: str = "") -> dict[str, Any]:
    """Inspect a subprocess exit code to detect resource-limit kills.

    On POSIX, when a process is killed by a signal, ``subprocess.run().returncode``
    is negative: ``returncode = -signum``.

    Args:
        returncode: The raw return code from ``subprocess.CompletedProcess.returncode``.
        stderr: The stderr output from the process, scanned for OOM hints.

    Returns:
        A dict of detection flags intended to be merged into the tool result:
        ``killed_by_oom``, ``killed_by_cpu``, ``killed_by_signal``,
        ``signal_name``, ``exit_code``, ``exited_cleanly``.
    """
    flags: dict[str, Any] = {
        "exited_cleanly": returncode == 0,
        "exit_code": returncode,
        "killed_by_signal": False,
        "killed_by_oom": False,
        "killed_by_cpu": False,
        "signal_name": None,
        "signal_number": None,
    }

    if returncode >= 0:
        return flags

    # Negative returncode means killed by signal
    signum = -returncode
    flags["killed_by_signal"] = True
    flags["signal_number"] = signum
    flags["signal_name"] = _SIGNAL_NAMES.get(signum, f"SIG({signum})")

    # SIGXCPU (24) — CPU time limit exceeded
    if signum == 24:
        flags["killed_by_cpu"] = True

    # SIGKILL (9) — potentially OOM; check stderr for hints
    elif signum == 9 or signum in (6, 11):
        stderr_lower = stderr.lower()
        for pattern in _OOM_STDERR_PATTERNS:
            if pattern in stderr_lower:
                flags["killed_by_oom"] = True
                break

    return flags
