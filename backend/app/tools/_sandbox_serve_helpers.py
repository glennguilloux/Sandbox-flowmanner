"""Shared helpers for sandboxd HTTP serving.

Two tools (``sandboxd_serve`` and ``sandboxd_file_write``) need to:

1. Check whether a port inside a sandbox is already serving HTTP.
2. Start a ``python3 -m http.server`` fallback if not.

Both also need to handle the same shell-quoting gotcha (``bash -c`` not
``bash -lc`` — login shells mangle ``%{http_code}`` in curl format
strings).  Centralising the logic here keeps the two consumers in sync
and makes the "fire-and-forget" vs. "wait-for-PID" contract explicit.

GOTCHA: ``fuser`` and ``ss`` are NOT available in the sandbox container,
and the template's built-in dev server is the container entrypoint —
**never kill anything on port 8080**.  Port 8081 is the safe port.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── Public constants ──────────────────────────────────────────────────────

# The sandbox workspace root inside the container.  The PUT /files API
# writes paths relative to this directory (e.g. path="index.html" puts
# the file at /home/sandbox/index.html).  Both ``sandboxd_serve`` and
# ``sandboxd_file_write`` serve from this directory.
DEFAULT_SANDBOX_WORKSPACE = "/home/sandbox"

# Default port for the python3 fallback server.  Port 8080 is used by
# the sandbox template's built-in dev server (also the container
# entrypoint) — never serve on 8080, and never kill anything on 8080.
DEFAULT_SERVE_PORT = 8081


# HTTP status codes that mean "the port is serving" for our purposes.
# We accept any 2xx or 3xx — a static file server may return 200, 301,
# 302 (directory index), or 304 (cached).
_SERVING_STATUS_CODES: frozenset[str] = frozenset(("200", "301", "302", "304"))


# ── Private command builders ──────────────────────────────────────────────


def _build_check_port_command(port: int) -> list[str]:
    """Build the ``bash -c`` argv that probes an HTTP port.

    Uses ``bash -c`` (NOT ``bash -lc``) because login shells treat
    ``%`` as a job-control specifier, which silently mangles the
    ``%{http_code}`` curl format string.
    """
    return [
        "bash",
        "-c",
        f"curl -sf -o /dev/null -w '%{{http_code}}' http://localhost:{port}/ 2>/dev/null || echo '000'",
    ]


def _build_http_server_script(port: int, serve_dir: str) -> str:
    """Return the python3 source code for a directory-serving HTTP server.

    Uses ``SimpleHTTPRequestHandler(directory=...)`` to avoid ``os.chdir``
    quoting issues, and ``SO_REUSEADDR`` so the server can rebind if the
    port is in ``TIME_WAIT``.
    """
    lines = [
        "import http.server, socketserver",
        "class H(http.server.SimpleHTTPRequestHandler):",
        "    def __init__(self, *a, **kw):",
        f"        super().__init__(*a, directory='{serve_dir}', **kw)",
        "socketserver.TCPServer.allow_reuse_address = True",
        f"s = socketserver.TCPServer(('0.0.0.0', {port}), H)",
        f"print('Serving on :{port} from {serve_dir}')",
        "s.serve_forever()",
    ]
    return "\n".join(lines) + "\n"


def _build_start_command(
    port: int,
    serve_dir: str,
    *,
    script_name: str,
    log_name: str,
    return_pid: bool,
) -> list[str]:
    """Build the full ``bash -c`` argv that starts the server in the background.

    The script is written to ``/tmp/<script_name>``, started with
    ``nohup`` so it survives the bash process exit, and logs to
    ``/tmp/<log_name>``.  When ``return_pid`` is ``True``, an additional
    ``echo $! > ...pid && cat ...pid`` pipeline captures the PID so the
    caller can return it.

    Note: ``script_name`` has no extension by default (e.g. ``"serve"``,
    not ``"serve.py"``) so the PID file lives at ``/tmp/serve.pid``,
    matching the pre-refactor filename.  This avoids breaking any
    external scripts that read ``/tmp/serve.pid``.
    """
    script = _build_http_server_script(port, serve_dir)
    # Escape for single-quoted shell string
    escaped = script.replace("'", "'\\''")

    cmd = f"echo '{escaped}' > /tmp/{script_name} && nohup python3 /tmp/{script_name} > /tmp/{log_name} 2>&1 & "
    if return_pid:
        cmd += f"echo $! > /tmp/{script_name}.pid && cat /tmp/{script_name}.pid"

    return ["bash", "-c", cmd]


# ── Public API ────────────────────────────────────────────────────────────


async def is_port_serving(
    client: Any,
    sandbox_id: str,
    port: int,
    *,
    timeout: float = 5.0,
) -> bool:
    """Return ``True`` if ``port`` is accepting HTTP connections inside the sandbox.

    Treats any 2xx/3xx response as "serving".  Connection refused,
    timeout, and any non-2xx/3xx response return ``False``.
    """
    result = await client.exec_command(
        sandbox_id, _build_check_port_command(port), timeout=timeout
    )
    output = result.get("stdout", "").strip().strip("'")
    return output in _SERVING_STATUS_CODES


async def start_static_http_server(
    client: Any,
    sandbox_id: str,
    port: int,
    serve_dir: str,
    *,
    script_name: str = "serve",
    log_name: str = "serve.log",
    return_pid: bool = True,
    timeout: float = 10.0,
) -> tuple[int, str | None]:
    """Start a python3 static HTTP server in the sandbox.

    Returns ``(pid, error)`` where ``error`` is ``None`` on success.
    When ``return_pid=False`` (fire-and-forget mode), ``pid`` is always
    ``0`` and ``error`` is ``None`` unless the start command itself
    failed.

    The server runs detached (``nohup``) so it survives the bash process
    exit.  No PID return means the caller doesn't need to track or kill
    the process — typical for auto-serve in ``sandboxd_file_write``,
    which only needs "a server is running on port 8081".

    Note: a non-empty ``stderr`` alone is not treated as an error.  The
    start command's exit code is the only signal of failure.  This
    matches typical Unix conventions and avoids false positives from
    backgrounded processes writing harmless warnings.
    """
    cmd = _build_start_command(
        port,
        serve_dir,
        script_name=script_name,
        log_name=log_name,
        return_pid=return_pid,
    )
    result = await client.exec_command(sandbox_id, cmd, timeout=timeout)

    # Non-fatal cases first: stderr with exit_code 0 = success.
    exit_code = result.get("exit_code", 1)
    if exit_code != 0:
        stderr = result.get("stderr", "").strip()
        error_msg = f"Start command exited with code {exit_code}"
        if stderr:
            error_msg += f": {stderr[:200]}"
        return 0, error_msg

    if not return_pid:
        return 0, None

    pid_str = result.get("stdout", "").strip().split("\n")[-1]
    try:
        return int(pid_str), None
    except (ValueError, TypeError):
        return 0, f"Could not parse PID from output: {pid_str!r}"


async def ensure_serving_on_port(
    client: Any,
    sandbox_id: str,
    port: int,
    serve_dir: str,
    *,
    script_name: str = "serve",
    log_name: str = "serve.log",
) -> None:
    """Start a server on ``port`` only if it isn't already serving.

    Fire-and-forget variant used by ``sandboxd_file_write`` — the LLM
    may forget to call ``sandboxd_serve``, so every successful file
    write silently ensures a server is running on 8081.

    Returns ``None`` on success.  Logs and swallows errors so the
    surrounding file-write response is never blocked by auto-serve
    failures (which are non-fatal: the LLM can still call
    ``sandboxd_serve`` explicitly if needed).
    """
    try:
        if await is_port_serving(client, sandbox_id, port):
            return  # Already serving — nothing to do
        await start_static_http_server(
            client,
            sandbox_id,
            port,
            serve_dir,
            script_name=script_name,
            log_name=log_name,
            return_pid=False,
        )
        logger.info(
            "_sandbox_serve_helpers: auto-serve started on port %s (sandbox=%s)",
            port,
            sandbox_id,
        )
    except Exception:
        logger.debug(
            "_sandbox_serve_helpers: auto-serve failed (non-fatal)",
            exc_info=True,
        )
