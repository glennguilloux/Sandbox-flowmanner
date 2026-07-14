"""Hard wall-clock timeout wrapper for sandboxd-backed tools.

Problem this solves
-------------------
The sandboxd HTTP client has a per-request timeout (``httpx.Timeout(30,
connect=5)``), but a single tool call can issue *many* requests plus
in-tool polling loops (e.g. ``sandboxd_preview`` polls up to 15 s,
``sandboxd_serve`` up to 10 s). If sandboxd is slow, auth-rejected, or
partially wedged, the stacked calls can stretch a single tool invocation
well beyond the per-request budget — and if that happens inside the
agentic chat loop, the SSE stream stays open and the UI appears "stuck
at sandbox" for many minutes with no GPU activity (it is blocked on a
network round-trip, not computing).

``run_sandbox_tool`` puts a single, hard ceiling on a tool invocation's
total wall-clock time. On ``_timeout``/``CancelledError`` it returns a
clean ``ToolResult.error_result`` (with the real exception surfaced) so
the agent loop sees a definitive failure and does NOT keep retrying an
unhandled exception forever.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.tools.base import ToolResult

logger = logging.getLogger(__name__)

# Default ceiling for the sandbox tool *call* (not the code *exec* inside a
# container — that is bounded separately by sandboxd_exec's own timeout).
DEFAULT_SANDBOX_TOOL_HARD_CAP_S = 60.0


async def run_sandbox_tool(
    tool_id: str,
    coro: Any,
    *,
    hard_cap: float = DEFAULT_SANDBOX_TOOL_HARD_CAP_S,
) -> ToolResult:
    """Run a sandboxd tool coroutine under a hard wall-clock timeout.

    Args:
        tool_id: Tool id (for error attribution).
        coro: The coroutine that performs the actual sandbox work.
        hard_cap: Maximum wall-clock seconds for the whole invocation.

    Returns:
        The tool's own ``ToolResult`` on success, or a clean
        ``error_result`` if the call timed out / was cancelled.
    """
    try:
        return await asyncio.wait_for(coro, timeout=hard_cap)
    except (TimeoutError, asyncio.CancelledError) as exc:
        logger.warning(
            "sandbox tool %s exceeded hard cap of %.0fs — returning timeout error "
            "(this prevents a wedged sandboxd from freezing the chat turn)",
            tool_id,
            hard_cap,
        )
        kind = "timeout" if isinstance(exc, asyncio.TimeoutError) else "cancelled"
        return ToolResult.error_result(
            tool_id=tool_id,
            error=(
                f"Sandbox operation timed out after {int(hard_cap)}s "
                f"({kind}). The sandbox service may be slow or unavailable — "
                f"try again later or check sandboxd health."
            ),
        )
