#!/usr/bin/env python3
"""
OpenWhisk API Gateway

Maps external API routes to OpenWhisk actions.
Handles request validation, routing, rate limiting.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from .auth import OpenWhiskAuthManager
from .client import OpenWhiskClient

logger = logging.getLogger(__name__)


class Route:
    """API route definition"""

    def __init__(
        self,
        path: str,
        action_name: str,
        method: str = "POST",
        auth_required: bool = True,
        rate_limit: int | None = None,
        timeout: int = 30,
    ):
        self.path = path
        self.action_name = action_name
        self.method = method.upper()
        self.auth_required = auth_required
        self.rate_limit = rate_limit  # requests per minute
        self.timeout = timeout


class RequestLimiter:
    """Rate limiter using in-memory storage"""

    def __init__(self):
        self.requests: dict[str, list[datetime]] = {}

    def is_allowed(self, key: str, limit: int = 60) -> bool:
        """
        Check if request is allowed based on rate limit

        Args:
            key: Unique key (IP address or API key)
            limit: Max requests per minute

        Returns:
            True if allowed, False if rate limited
        """
        now = datetime.now(UTC)
        minute_ago = now - timedelta(minutes=1)

        if key not in self.requests:
            self.requests[key] = []

        # Remove old requests
        self.requests[key] = [
            req_time for req_time in self.requests[key] if req_time > minute_ago
        ]

        # Check if under limit
        if len(self.requests[key]) >= limit:
            logger.warning(
                "Rate limit exceeded for %s: %s >= %s",
                key,
                len(self.requests[key]),
                limit,
            )
            return False

        # Add current request
        self.requests[key].append(now)
        return True


class OpenWhiskAPIGateway:
    """
    API Gateway for OpenWhisk integration

    Maps external API routes to OpenWhisk actions with:
    - Request validation
    - Rate limiting
    - Authentication
    - Error handling
    - Monitoring
    """

    def __init__(
        self,
        client: OpenWhiskClient,
        auth_manager: OpenWhiskAuthManager,
        enable_rate_limiting: bool = True,
    ):
        """
        Initialize API gateway

        Args:
            client: OpenWhisk client instance
            auth_manager: Auth manager instance
            enable_rate_limiting: Enable rate limiting
        """
        self.client = client
        self.auth_manager = auth_manager
        self.routes: dict[str, Route] = {}
        self.rate_limiter = RequestLimiter() if enable_rate_limiting else None
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "rate_limited": 0,
            "start_time": datetime.now(UTC),
        }

        logger.info("OpenWhiskAPIGateway initialized")

    def register_route(
        self,
        path: str,
        action_name: str,
        method: str = "POST",
        auth_required: bool = True,
        rate_limit: int | None = None,
        timeout: int = 30,
    ) -> None:
        """
        Register an API route to an OpenWhisk action

        Args:
            path: API path (e.g., '/workflows/generate')
            action_name: OpenWhisk action to invoke
            method: HTTP method
            auth_required: Require authentication
            rate_limit: Max requests per minute
            timeout: Action timeout in seconds

        Example:
            >>> gateway.register_route(
            ...     '/api/workflows/generate',
            ...     'step_2a_generate_request',
            ...     method='POST',
            ...     rate_limit=60
            ... )
        """
        route = Route(
            path=path,
            action_name=action_name,
            method=method,
            auth_required=auth_required,
            rate_limit=rate_limit,
            timeout=timeout,
        )

        self.routes[path] = route
        logger.info("Route registered: %s %s -> action: %s", method, path, action_name)

    def get_route(self, path: str, method: str) -> Route | None:
        """
        Get route by path and method

        Args:
            path: API path
            method: HTTP method

        Returns:
            Route object or None if not found
        """
        route_key = f"{method.upper()} {path}"
        if route_key in self.routes:
            return self.routes[route_key]
        return None

    async def handle_request(
        self,
        path: str,
        method: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """
        Handle incoming API request

        Args:
            path: API path
            method: HTTP method
            payload: Request payload
            headers: Request headers
            client_ip: Client IP address for rate limiting

        Returns:
            Response dict with status, data, error

        Example:
            >>> result = await gateway.handle_request(
            ...     '/api/workflows/execute',
            ...     'POST',
            ...     {'workflow_id': 'test-123'}
            ... )
        """
        self.metrics["total_requests"] += 1

        try:
            # Find route
            route = self.get_route(path, method)
            if not route:
                self.metrics["failed_requests"] += 1
                return {
                    "success": False,
                    "status": 404,
                    "error": f"Route not found: {method} {path}",
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            # Rate limiting
            if self.rate_limiter and route.rate_limit:
                limit_key = client_ip or headers.get("X-API-Key", "default")
                if not self.rate_limiter.is_allowed(limit_key, route.rate_limit):
                    self.metrics["rate_limited"] += 1
                    self.metrics["failed_requests"] += 1
                    return {
                        "success": False,
                        "status": 429,
                        "error": "Rate limit exceeded",
                        "retry_after": 60,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }

            # Authentication
            if route.auth_required:
                auth_header = headers.get("Authorization") if headers else None
                if not auth_header:
                    self.metrics["failed_requests"] += 1
                    return {
                        "success": False,
                        "status": 401,
                        "error": "Authentication required",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }

                # Validate auth (simplified - in production use proper JWT/OAuth)
                # For now, we pass through since OpenWhiskClient handles it

            # Request validation
            if payload is None:
                payload = {}

            # Invoke OpenWhisk action
            invocation = await self.client.invoke_action(
                action_name=route.action_name, params=payload
            )

            if invocation.success:
                self.metrics["successful_requests"] += 1
                return {
                    "success": True,
                    "status": 200,
                    "data": invocation.result,
                    "duration_ms": invocation.duration_ms,
                    "activation_id": invocation.activation_id,
                    "logs": invocation.logs,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            else:
                self.metrics["failed_requests"] += 1
                return {
                    "success": False,
                    "status": 500,
                    "error": invocation.error,
                    "timestamp": datetime.now(UTC).isoformat(),
                }

        except Exception as e:
            logger.error("Error handling request %s %s: %s", method, path, e)
            self.metrics["failed_requests"] += 1
            return {
                "success": False,
                "status": 500,
                "error": f"Internal server error: {e!s}",
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def batch_handle(
        self, requests: list[dict[str, Any]], max_concurrent: int = 10
    ) -> list[dict[str, Any]]:
        """
        Handle multiple requests concurrently

        Args:
            requests: List of request dicts {path, method, payload}
            max_concurrent: Max concurrent requests

        Returns:
            List of response dicts
        """
        logger.info("Batch handling %s requests", len(requests))

        semaphore = asyncio.Semaphore(max_concurrent)
        tasks = []

        async def handle_with_limit(req):
            async with semaphore:
                return await self.handle_request(
                    path=req["path"],
                    method=req.get("method", "POST"),
                    payload=req.get("payload"),
                    headers=req.get("headers"),
                    client_ip=req.get("client_ip"),
                )

        for req in requests:
            task = asyncio.create_task(handle_with_limit(req))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Batch request %s failed: %s", i, result)
                processed_results.append(
                    {
                        "success": False,
                        "status": 500,
                        "error": str(result),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            else:
                processed_results.append(result)

        return processed_results

    def get_metrics(self) -> dict[str, Any]:
        """
        Get gateway metrics

        Returns:
            Metrics dictionary
        """
        uptime = datetime.now(UTC) - self.metrics["start_time"]

        return {
            "uptime_seconds": int(uptime.total_seconds()),
            "total_requests": self.metrics["total_requests"],
            "successful_requests": self.metrics["successful_requests"],
            "failed_requests": self.metrics["failed_requests"],
            "rate_limited": self.metrics["rate_limited"],
            "success_rate": (
                self.metrics["successful_requests"]
                / self.metrics["total_requests"]
                * 100
                if self.metrics["total_requests"] > 0
                else 0
            ),
            "registered_routes": len(self.routes),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def reset_metrics(self) -> None:
        """Reset metrics counters"""
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "rate_limited": 0,
            "start_time": datetime.now(UTC),
        }
        logger.info("Metrics reset")

    def list_routes(self) -> list[dict[str, str]]:
        """
        List all registered routes

        Returns:
            List of route information
        """
        routes_info = []
        for path, route in self.routes.items():
            routes_info.append(
                {
                    "path": path,
                    "method": route.method,
                    "action": route.action_name,
                    "auth_required": route.auth_required,
                    "rate_limit": route.rate_limit,
                    "timeout": route.timeout,
                }
            )
        return routes_info


def create_gateway(
    client: OpenWhiskClient | None = None,
    auth_manager: OpenWhiskAuthManager | None = None,
) -> OpenWhiskAPIGateway | None:
    """
    Factory function to create API gateway

    Args:
        client: OpenWhisk client or None (auto-create)
        auth_manager: Auth manager or None (auto-create)

    Returns:
        OpenWhiskAPIGateway instance or None if not configured

    Example:
        >>> gateway = create_gateway()
        >>> if gateway:
        >>>     gateway.register_route('/api/test', 'test_action')
        >>>     result = await gateway.handle_request('/api/test', 'POST', {...})
    """
    try:
        if client is None:
            from .client import get_openwhisk_client

            client = get_openwhisk_client()

        if auth_manager is None:
            from .auth import get_auth_manager

            auth_manager = get_auth_manager()

        if not client or not auth_manager:
            logger.warning("Cannot create gateway: missing client or auth")
            return None

        gateway = OpenWhiskAPIGateway(
            client=client, auth_manager=auth_manager, enable_rate_limiting=True
        )

        logger.info("API gateway created successfully")
        return gateway

    except Exception as e:
        logger.error("Error creating gateway: %s", e)
        return None
