"""
Phase 4.3: Runtime SDK
Python SDK for programmatic runtime control
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RuntimeStatus(Enum):
    INITIALIZING = "initializing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    MAINTENANCE = "maintenance"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class ExecutionResult:
    execution_id: str
    status: str
    result: Any | None = None
    error: str | None = None
    duration_ms: float = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueueStats:
    total_queued: int
    total_running: int
    total_completed: int
    total_failed: int
    avg_wait_time_ms: float
    avg_execution_time_ms: float


class RuntimeSDK:
    """Python SDK for runtime control"""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, headers=self._get_headers()
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make HTTP request"""
        if not self._client:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._get_headers(),
            )

        response = await self._client.request(method, endpoint, **kwargs)
        response.raise_for_status()
        return response.json()

    # ====================
    # Health & Status
    # ====================

    async def get_health(self) -> dict[str, Any]:
        """Get runtime health status"""
        return await self._request("GET", "/api/runtime/health")

    async def get_status(self) -> dict[str, Any]:
        """Get detailed runtime status"""
        return await self._request("GET", "/api/runtime/status")

    async def get_metrics(self) -> dict[str, Any]:
        """Get current runtime metrics"""
        return await self._request("GET", "/api/runtime/metrics")

    # ====================
    # Queue Management
    # ====================

    async def get_queue_stats(self) -> QueueStats:
        """Get queue statistics"""
        data = await self._request("GET", "/api/runtime/queue/stats")
        return QueueStats(**data)

    async def get_queue_items(
        self, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get items in the execution queue"""
        params = {"limit": limit}
        if status:
            params["status"] = int(status)
        return await self._request("GET", "/api/runtime/queue/items", params=params)

    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a queued or running execution"""
        result = await self._request(
            "POST", f"/api/runtime/queue/{execution_id}/cancel"
        )
        return result.get("cancelled", False)

    async def prioritize_execution(self, execution_id: str, priority: int) -> bool:
        """Change execution priority"""
        result = await self._request(
            "POST",
            f"/api/runtime/queue/{execution_id}/priority",
            json={"priority": priority},
        )
        return result.get("updated", False)

    # ====================
    # Execution Control
    # ====================

    async def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        priority: str = "normal",
        timeout: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute a tool synchronously"""
        payload = {
            "tool": tool_name,
            "params": params,
            "priority": priority,
            "metadata": metadata or {},
        }
        if timeout:
            payload["timeout"] = timeout  # type: ignore[assignment]

        data = await self._request("POST", "/api/runtime/execute", json=payload)

        return ExecutionResult(
            execution_id=data.get("execution_id", ""),
            status=data.get("status", "unknown"),
            result=data.get("result"),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0),
            metadata=data.get("metadata", {}),
        )

    async def execute_async(
        self,
        tool_name: str,
        params: dict[str, Any],
        priority: str = "normal",
        callback_url: str | None = None,
    ) -> str:
        """Execute a tool asynchronously, returns execution ID"""
        payload = {
            "tool": tool_name,
            "params": params,
            "priority": priority,
            "async": True,
        }
        if callback_url:
            payload["callback_url"] = callback_url

        data = await self._request("POST", "/api/runtime/execute", json=payload)
        return data.get("execution_id", "")

    async def get_execution(self, execution_id: str) -> ExecutionResult:
        """Get execution result by ID"""
        data = await self._request("GET", f"/api/runtime/executions/{execution_id}")
        return ExecutionResult(
            execution_id=data.get("execution_id", ""),
            status=data.get("status", "unknown"),
            result=data.get("result"),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0),
            metadata=data.get("metadata", {}),
        )

    # ====================
    # Scaling Control
    # ====================

    async def get_scaling_status(self) -> dict[str, Any]:
        """Get auto-scaling status"""
        return await self._request("GET", "/api/runtime/scaling/status")

    async def scale_up(self, count: int = 1) -> dict[str, Any]:
        """Manually scale up workers"""
        return await self._request(
            "POST", "/api/runtime/scaling/scale-up", json={"count": count}
        )

    async def scale_down(self, count: int = 1) -> dict[str, Any]:
        """Manually scale down workers"""
        return await self._request(
            "POST", "/api/runtime/scaling/scale-down", json={"count": count}
        )

    async def set_scaling_policy(
        self,
        min_workers: int,
        max_workers: int,
        target_cpu: float = 70.0,
        target_memory: float = 80.0,
    ) -> dict[str, Any]:
        """Set auto-scaling policy"""
        return await self._request(
            "PUT",
            "/api/runtime/scaling/policy",
            json={
                "min_workers": min_workers,
                "max_workers": max_workers,
                "target_cpu": target_cpu,
                "target_memory": target_memory,
            },
        )

    # ====================
    # Predictive Features
    # ====================

    async def get_predictions(self) -> dict[str, Any]:
        """Get resource predictions"""
        return await self._request("GET", "/api/runtime/predictions")

    async def get_anomalies(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get detected anomalies"""
        return await self._request(
            "GET", "/api/runtime/anomalies", params={"hours": hours}
        )

    async def get_scaling_recommendations(self) -> dict[str, Any]:
        """Get scaling recommendations"""
        return await self._request("GET", "/api/runtime/scaling/recommendations")

    # ====================
    # Self-Healing
    # ====================

    async def get_system_health(self) -> dict[str, Any]:
        """Get system health status"""
        return await self._request("GET", "/api/runtime/health/system")

    async def get_recovery_history(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get recovery attempt history"""
        return await self._request(
            "GET", "/api/runtime/recovery/history", params={"hours": hours}
        )

    async def trigger_recovery(
        self, error_id: str, strategy: str | None = None
    ) -> dict[str, Any]:
        """Manually trigger recovery"""
        payload = {"error_id": error_id}
        if strategy:
            payload["strategy"] = strategy
        return await self._request(
            "POST", "/api/runtime/recovery/trigger", json=payload
        )

    # ====================
    # Configuration
    # ====================

    async def get_config(self) -> dict[str, Any]:
        """Get runtime configuration"""
        return await self._request("GET", "/api/runtime/config")

    async def update_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Update runtime configuration"""
        return await self._request("PUT", "/api/runtime/config", json=config)

    async def reset_config(self) -> dict[str, Any]:
        """Reset configuration to defaults"""
        return await self._request("POST", "/api/runtime/config/reset")


# Sync wrapper for non-async code
class RuntimeSDKSync:
    """Synchronous wrapper for RuntimeSDK"""

    def __init__(
        self, base_url: str = "http://localhost:8000", api_key: str | None = None
    ):
        self._async_sdk = RuntimeSDK(base_url, api_key)

    def _run(self, coro):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

    def get_health(self) -> dict[str, Any]:
        return self._run(self._async_sdk.get_health())

    def get_status(self) -> dict[str, Any]:
        return self._run(self._async_sdk.get_status())

    def execute(self, tool_name: str, params: dict[str, Any]) -> ExecutionResult:
        return self._run(self._async_sdk.execute(tool_name, params))

    def get_queue_stats(self) -> QueueStats:
        return self._run(self._async_sdk.get_queue_stats())

    def get_predictions(self) -> dict[str, Any]:
        return self._run(self._async_sdk.get_predictions())

    def get_system_health(self) -> dict[str, Any]:
        return self._run(self._async_sdk.get_system_health())
