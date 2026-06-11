"""
Sentry MCP Instrumentation

Wraps MCP server with Sentry monitoring for per-tool
performance tracking and error capture.
"""

import logging
import time
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# Optional Sentry SDK support
try:
    import sentry_sdk
    from sentry_sdk.tracing import Span

    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False
    sentry_sdk = None


def instrument_mcp_server(server: Any) -> Any:
    """
    Wrap MCP server with Sentry monitoring.

    Args:
        server: MCPServerGateway instance to instrument

    Returns:
        Instrumented server instance
    """
    if not SENTRY_AVAILABLE:
        logger.warning("Sentry SDK not available, skipping MCP instrumentation")
        return server

    # Store original methods
    original_handle_tool_call = getattr(server, "handle_tool_call", None)
    original_handle_request = getattr(server, "handle_request", None)

    if original_handle_tool_call:

        @wraps(original_handle_tool_call)
        async def wrapped_handle_tool_call(tool_name: str, arguments: dict[str, Any], *args, **kwargs):
            """Wrapped tool call handler with Sentry instrumentation."""
            with sentry_sdk.start_transaction(name=f"mcp.tool.{tool_name}", op="mcp.tool_call") as transaction:
                # Set tool context
                sentry_sdk.set_context(
                    "mcp_tool",
                    {
                        "tool_name": tool_name,
                        "arguments": _scrub_sensitive_data(arguments),
                    },
                )

                # Add breadcrumb
                sentry_sdk.add_breadcrumb(
                    message=f"MCP tool call: {tool_name}",
                    category="mcp",
                    level="info",
                    data={"arguments": _scrub_sensitive_data(arguments)},
                )

                start_time = time.time()
                try:
                    result = await original_handle_tool_call(tool_name, arguments, *args, **kwargs)

                    # Record success metrics
                    duration = time.time() - start_time
                    transaction.set_status("ok")
                    transaction.set_data("duration_ms", duration * 1000)

                    return result

                except Exception as e:
                    # Record error
                    duration = time.time() - start_time
                    transaction.set_status("internal_error")
                    transaction.set_data("duration_ms", duration * 1000)
                    transaction.set_data("error", str(e))

                    # Capture exception with context
                    sentry_sdk.capture_exception(e)
                    raise

        server.handle_tool_call = wrapped_handle_tool_call

    if original_handle_request:

        @wraps(original_handle_request)
        async def wrapped_handle_request(request: dict[str, Any], *args, **kwargs):
            """Wrapped request handler with Sentry instrumentation."""
            method = request.get("method", "unknown")

            with sentry_sdk.start_span(op="mcp.request", description=f"MCP request: {method}") as span:
                span.set_data("method", method)
                span.set_data("request_id", request.get("id"))

                try:
                    result = await original_handle_request(request, *args, **kwargs)
                    span.set_status("ok")
                    return result
                except Exception as e:
                    span.set_status("internal_error")
                    sentry_sdk.capture_exception(e)
                    raise

        server.handle_request = wrapped_handle_request

    logger.info("✅ MCP server instrumented with Sentry monitoring")
    return server


def _scrub_sensitive_data(data: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive data from arguments before logging."""
    if not isinstance(data, dict):
        return data

    sensitive_keys = {
        "password",
        "secret",
        "token",
        "api_key",
        "authorization",
        "credential",
        "private_key",
        "access_token",
    }

    scrubbed: dict[str, Any] = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            scrubbed[key] = "[Filtered]"
        elif isinstance(value, dict):
            scrubbed[key] = _scrub_sensitive_data(value)
        else:
            scrubbed[key] = value

    return scrubbed


class MCPPerformanceTracker:
    """
    Track MCP tool performance metrics.
    """

    def __init__(self):
        self._tool_metrics: dict[str, dict[str, Any]] = {}

    def record_tool_call(
        self,
        tool_name: str,
        duration_ms: float,
        success: bool,
        error: str | None = None,
    ):
        """Record a tool call metric."""
        if tool_name not in self._tool_metrics:
            self._tool_metrics[tool_name] = {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "total_duration_ms": 0,
                "errors": [],
            }

        metrics = self._tool_metrics[tool_name]
        metrics["total_calls"] += 1
        metrics["total_duration_ms"] += duration_ms

        if success:
            metrics["successful_calls"] += 1
        else:
            metrics["failed_calls"] += 1
            if error:
                metrics["errors"].append(error)

        # Send to Sentry as custom metric
        if SENTRY_AVAILABLE:
            sentry_sdk.set_context(
                f"mcp_tool_{tool_name}",
                {
                    "total_calls": metrics["total_calls"],
                    "success_rate": metrics["successful_calls"] / metrics["total_calls"],
                    "avg_duration_ms": metrics["total_duration_ms"] / metrics["total_calls"],
                },
            )

    def get_tool_metrics(self, tool_name: str | None = None) -> dict[str, Any]:
        """Get metrics for a specific tool or all tools."""
        if tool_name:
            return self._tool_metrics.get(tool_name, {})
        return self._tool_metrics

    def get_slow_tools(self, threshold_ms: float = 1000) -> dict[str, Any]:
        """Get tools with average duration above threshold."""
        slow_tools = {}
        for tool_name, metrics in self._tool_metrics.items():
            avg_duration = metrics["total_duration_ms"] / metrics["total_calls"]
            if avg_duration > threshold_ms:
                slow_tools[tool_name] = {
                    "avg_duration_ms": avg_duration,
                    "total_calls": metrics["total_calls"],
                }
        return slow_tools

    def get_error_prone_tools(self, threshold_rate: float = 0.1) -> dict[str, Any]:
        """Get tools with error rate above threshold."""
        error_prone = {}
        for tool_name, metrics in self._tool_metrics.items():
            if metrics["total_calls"] > 0:
                error_rate = metrics["failed_calls"] / metrics["total_calls"]
                if error_rate > threshold_rate:
                    error_prone[tool_name] = {
                        "error_rate": error_rate,
                        "failed_calls": metrics["failed_calls"],
                        "total_calls": metrics["total_calls"],
                    }
        return error_prone


# Singleton instance
_mcp_performance_tracker: MCPPerformanceTracker | None = None


def get_mcp_performance_tracker() -> MCPPerformanceTracker:
    """Get or create the MCP performance tracker singleton."""
    global _mcp_performance_tracker
    if _mcp_performance_tracker is None:
        _mcp_performance_tracker = MCPPerformanceTracker()
    return _mcp_performance_tracker
