"""
Tool Executor - Executes any tool with auth, rate-limiting, logging

Provides unified execution interface for all tools with:
- Authentication/authorization checks
- Rate limiting
- Timeout handling
- Logging and metrics
- Error handling and retries
"""

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .tool_registry import Tool, get_tool_registry

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of a tool execution"""

    tool_id: str
    success: bool
    result: Any = None
    error: str | None = None
    execution_time_ms: float = 0
    tokens_used: int = 0
    cost_usd: float = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RateLimitInfo:
    """Rate limit tracking for a tool"""

    requests: list[float] = field(default_factory=list)
    window_seconds: int = 60
    max_requests: int = 60


class ToolExecutor:
    """
    Executes tools with comprehensive management.

    Features:
    - Authentication/authorization
    - Rate limiting per tool and per user
    - Timeout handling
    - Retry logic
    - Logging and metrics
    - Cost tracking
    """

    def __init__(self, registry=None):
        self.registry = registry or get_tool_registry()
        self._rate_limits: dict[str, RateLimitInfo] = defaultdict(RateLimitInfo)
        self._user_rate_limits: dict[str, dict[str, RateLimitInfo]] = defaultdict(lambda: defaultdict(RateLimitInfo))
        self._execution_history: list[ExecutionResult] = []
        self._auth_checker: Callable | None = None
        self._pre_hooks: list[Callable] = []
        self._post_hooks: list[Callable] = []

    def set_auth_checker(self, checker: Callable[[str, str, dict], Awaitable[bool]]) -> None:
        """Set a function to check authorization for tool execution"""
        self._auth_checker = checker

    def add_pre_hook(self, hook: Callable[[str, dict], Awaitable[None]]) -> None:
        """Add a pre-execution hook"""
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: Callable[[ExecutionResult], Awaitable[None]]) -> None:
        """Add a post-execution hook"""
        self._post_hooks.append(hook)

    async def execute(
        self,
        tool_id: str,
        params: dict[str, Any],
        user_id: str | None = None,
        session_id: str | None = None,
        timeout_override: int | None = None,
        retry_count: int = 0,
    ) -> ExecutionResult:
        """
        Execute a tool with full management.

        Args:
            tool_id: The tool to execute
            params: Parameters for the tool
            user_id: User making the request
            session_id: Session context
            timeout_override: Override default timeout
            retry_count: Number of retries on failure

        Returns:
            ExecutionResult with success status and data
        """
        start_time = time.time()

        # Get the tool
        tool = self.registry.get(tool_id)
        if not tool:
            return ExecutionResult(tool_id=tool_id, success=False, error=f"Tool not found: {tool_id}")

        # Check authorization
        if tool.requires_auth and self._auth_checker:
            try:
                authorized = await self._auth_checker(tool_id, user_id, params)
                if not authorized:
                    return ExecutionResult(tool_id=tool_id, success=False, error="Unauthorized")
            except Exception as e:
                logger.error("Auth check failed: %s", e)
                return ExecutionResult(tool_id=tool_id, success=False, error=f"Auth check failed: {e}")

        # Check rate limits
        if not self._check_rate_limit(tool_id, user_id, tool.rate_limit):
            return ExecutionResult(tool_id=tool_id, success=False, error="Rate limit exceeded")

        # Run pre-hooks
        for hook in self._pre_hooks:
            try:
                await hook(tool_id, params)
            except Exception as e:
                logger.warning("Pre-hook failed: %s", e)

        # Execute with timeout
        timeout = timeout_override or tool.timeout_seconds
        result = None
        error = None

        try:
            if tool.handler:
                result = await asyncio.wait_for(tool.handler(params), timeout=timeout)
            else:
                error = "Tool has no handler"
        except TimeoutError:
            error = f"Tool execution timed out after {timeout}s"
        except Exception as e:
            error = str(e)
            logger.error("Tool %s execution error: %s", tool_id, e)

            # Retry logic
            if retry_count > 0:
                logger.info("Retrying %s (%s retries left)", tool_id, retry_count)
                await asyncio.sleep(1)  # Brief delay before retry
                return await self.execute(
                    tool_id=tool_id,
                    params=params,
                    user_id=user_id,
                    session_id=session_id,
                    timeout_override=timeout_override,
                    retry_count=retry_count - 1,
                )

        execution_time = (time.time() - start_time) * 1000

        # Calculate cost
        cost = self._calculate_cost(tool, result, execution_time)

        # Create result
        exec_result = ExecutionResult(
            tool_id=tool_id,
            success=error is None,
            result=result,
            error=error,
            execution_time_ms=execution_time,
            cost_usd=cost,
            metadata={
                "user_id": user_id,
                "session_id": session_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "timeout_seconds": timeout,
            },
        )

        # Record for rate limiting
        self._record_request(tool_id, user_id)

        # Store in history
        self._execution_history.append(exec_result)
        if len(self._execution_history) > 1000:
            self._execution_history = self._execution_history[-500:]

        # Run post-hooks
        for hook in self._post_hooks:
            try:
                await hook(exec_result)
            except Exception as e:
                logger.warning("Post-hook failed: %s", e)

        return exec_result

    async def execute_batch(self, executions: list[dict[str, Any]], parallel: bool = True) -> list[ExecutionResult]:
        """
        Execute multiple tools in batch.

        Args:
            executions: List of {"tool_id": str, "params": dict, ...}
            parallel: Execute in parallel or sequentially

        Returns:
            List of ExecutionResults
        """
        if parallel:
            tasks = [
                self.execute(
                    tool_id=e["tool_id"],
                    params=e.get("params", {}),
                    user_id=e.get("user_id"),
                    session_id=e.get("session_id"),
                )
                for e in executions
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)  # type: ignore[return-value]
        else:
            results = []
            for e in executions:
                result = await self.execute(
                    tool_id=e["tool_id"],
                    params=e.get("params", {}),
                    user_id=e.get("user_id"),
                    session_id=e.get("session_id"),
                )
                results.append(result)
            return results

    def _check_rate_limit(self, tool_id: str, user_id: str | None, rate_limit: int | None) -> bool:
        """Check if request is within rate limits"""
        if not rate_limit:
            return True

        now = time.time()

        # Check tool-level rate limit
        tool_info = self._rate_limits[tool_id]
        tool_info.requests = [t for t in tool_info.requests if now - t < tool_info.window_seconds]

        if len(tool_info.requests) >= rate_limit:
            return False

        # Check user-level rate limit if user specified
        if user_id:
            user_info = self._user_rate_limits[user_id][tool_id]
            user_info.requests = [t for t in user_info.requests if now - t < user_info.window_seconds]

            if len(user_info.requests) >= rate_limit:
                return False

        return True

    def _record_request(self, tool_id: str, user_id: str | None) -> None:
        """Record a request for rate limiting"""
        now = time.time()
        self._rate_limits[tool_id].requests.append(now)

        if user_id:
            self._user_rate_limits[user_id][tool_id].requests.append(now)

    def _calculate_cost(self, tool: Tool, result: Any, execution_time_ms: float) -> float:
        """Calculate execution cost"""
        base_cost = tool.cost_estimate.get("usd", 0)

        # Add time-based cost for long-running operations
        if execution_time_ms > 10000:  # > 10 seconds
            base_cost += 0.001 * (execution_time_ms / 1000)

        return base_cost

    def get_execution_history(
        self, tool_id: str | None = None, user_id: str | None = None, limit: int = 100
    ) -> list[ExecutionResult]:
        """Get execution history, optionally filtered"""
        history = self._execution_history

        if tool_id:
            history = [h for h in history if h.tool_id == tool_id]

        if user_id:
            history = [h for h in history if h.metadata.get("user_id") == user_id]

        return history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get execution statistics"""
        if not self._execution_history:
            return {"total_executions": 0}

        total = len(self._execution_history)
        successful = sum(1 for h in self._execution_history if h.success)
        total_time = sum(h.execution_time_ms for h in self._execution_history)
        total_cost = sum(h.cost_usd for h in self._execution_history)

        return {
            "total_executions": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": successful / total if total > 0 else 0,
            "avg_execution_time_ms": total_time / total if total > 0 else 0,
            "total_cost_usd": total_cost,
            "tools_used": list({h.tool_id for h in self._execution_history}),
        }


# Global executor instance
_tool_executor: ToolExecutor | None = None


def get_tool_executor() -> ToolExecutor:
    """Get or create the global tool executor"""
    global _tool_executor
    if _tool_executor is None:
        _tool_executor = ToolExecutor()
    return _tool_executor
