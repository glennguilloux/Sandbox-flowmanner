#!/usr/bin/env python3
"""
Health Check Service

Monitors health of OpenWhisk integration, actions, and infrastructure.
Provides health endpoints and metrics collection.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from ..openwhisk.api_gateway import OpenWhiskAPIGateway
from ..openwhisk.client import OpenWhiskClient, get_openwhisk_client
from ..openwhisk.integration_controller import (
    OpenWhiskIntegrationController,
    create_integration_controller,
)

logger = logging.getLogger(__name__)


class HealthCheck:
    """
    Health check service for OpenWhisk integration

    Monitors:
    - OpenWhisk connectivity
    - Action health
    - API gateway status
    - Resource usage
    """

    def __init__(
        self,
        client: OpenWhiskClient | None = None,
        gateway: OpenWhiskAPIGateway | None = None,
        controller: OpenWhiskIntegrationController | None = None,
    ):
        """
        Initialize health check service

        Args:
            client: OpenWhisk client instance
            gateway: API gateway instance
            controller: Integration controller instance
        """
        self.client = client or get_openwhisk_client()
        self.gateway = gateway
        self.controller = controller or create_integration_controller(
            client=self.client
        )

        # Cache health status
        self.health_status = {
            "last_check": None,
            "openwhisk_healthy": False,
            "gateway_healthy": False,
            "actions_healthy": 0,
            "total_actions": 0,
        }

        logger.info("HealthCheck service initialized")

    async def check_openwhisk(self) -> dict[str, Any]:
        """
        Check OpenWhisk platform connectivity

        Returns:
            Health status dict
        """
        logger.info("Checking OpenWhisk connectivity")

        try:
            health = await self.client.health_check()

            self.health_status["openwhisk_healthy"] = health["status"] == "healthy"
            self.health_status["last_check"] = datetime.now(UTC)

            return health

        except Exception as e:
            logger.error(f"OpenWhisk health check failed: {e}")
            self.health_status["openwhisk_healthy"] = False
            self.health_status["last_check"] = datetime.now(UTC)

            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def check_gateway(self) -> dict[str, Any]:
        """
        Check API gateway status

        Returns:
            Gateway health status dict
        """
        logger.info("Checking API gateway status")

        try:
            if not self.gateway:
                return {
                    "status": "unknown",
                    "error": "Gateway not initialized",
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            # Get gateway metrics
            metrics = self.gateway.get_metrics()

            uptime = metrics.get("uptime_seconds", 0)
            total_requests = metrics.get("total_requests", 0)

            success_rate = (
                metrics.get("successful_requests", 0) / total_requests * 100
                if total_requests > 0
                else 0
            )

            # Gateway is healthy if:
            # - Has been running for at least 30 seconds
            # - Has processed some requests
            # - Success rate is > 80%
            is_healthy = uptime >= 30 and total_requests > 0 and success_rate >= 80

            self.health_status["gateway_healthy"] = is_healthy

            return {
                "status": "healthy" if is_healthy else "degraded",
                "uptime_seconds": uptime,
                "total_requests": total_requests,
                "successful_requests": metrics.get("successful_requests", 0),
                "failed_requests": metrics.get("failed_requests", 0),
                "success_rate": success_rate,
                "rate_limited": metrics.get("rate_limited", 0),
                "registered_routes": metrics.get("registered_routes", 0),
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error(f"Gateway health check failed: {e}")
            self.health_status["gateway_healthy"] = False

            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def check_actions(self) -> dict[str, Any]:
        """
        Check health of deployed actions

        Returns:
            Actions health summary dict
        """
        logger.info("Checking deployed actions health")

        try:
            if not self.controller:
                return {
                    "status": "unknown",
                    "error": "Controller not initialized",
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            # Get health of all actions
            health = await self.controller.health_check_all_actions()

            self.health_status["actions_healthy"] = health.get("healthy_actions", 0)
            self.health_status["total_actions"] = health.get("total_actions", 0)

            return health

        except Exception as e:
            logger.error(f"Actions health check failed: {e}")

            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def comprehensive_health_check(self) -> dict[str, Any]:
        """
        Perform comprehensive health check

        Returns:
            Overall health status with component breakdown

        Example:
            >>> health = await check.comprehensive_health_check()
            >>> if health['overall_status'] == 'healthy':
            >>>     print("All systems operational")
        """
        logger.info("Performing comprehensive health check")

        start_time = datetime.now(UTC)

        # Run all checks concurrently
        openwhisk_health, gateway_health, actions_health = await asyncio.gather(
            self.check_openwhisk(),
            self.check_gateway(),
            self.check_actions(),
            return_exceptions=True,
        )

        # Handle any failures
        if isinstance(openwhisk_health, Exception):
            logger.error(f"OpenWhisk check error: {openwhisk_health}")
            openwhisk_health = {"status": "error", "error": str(openwhisk_health)}

        if isinstance(gateway_health, Exception):
            logger.error(f"Gateway check error: {gateway_health}")
            gateway_health = {"status": "error", "error": str(gateway_health)}

        if isinstance(actions_health, Exception):
            logger.error(f"Actions check error: {actions_health}")
            actions_health = {"status": "error", "error": str(actions_health)}

        # Determine overall status
        all_healthy = (
            openwhisk_health.get("status") in ("healthy", "ok")
            and gateway_health.get("status") in ("healthy", "ok")
            and actions_health.get("health_percentage", 0) >= 80
        )

        overall_status = "healthy" if all_healthy else "degraded"

        duration = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        return {
            "overall_status": overall_status,
            "openwhisk": openwhisk_health,
            "gateway": gateway_health,
            "actions": actions_health,
            "duration_ms": duration,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_cached_health(self, max_age_seconds: int = 60) -> dict[str, Any] | None:
        """
        Get cached health status if recent

        Args:
            max_age_seconds: Maximum age of cache in seconds

        Returns:
            Cached health dict or None if expired
        """
        if not self.health_status["last_check"]:
            return None

        age = (datetime.now(UTC) - self.health_status["last_check"]).total_seconds()

        if age > max_age_seconds:
            logger.info(f"Health cache expired ({age}s old)")
            return None

        return {
            "openwhisk_healthy": self.health_status["openwhisk_healthy"],
            "gateway_healthy": self.health_status["gateway_healthy"],
            "actions_healthy": self.health_status["actions_healthy"],
            "total_actions": self.health_status["total_actions"],
            "cached_at": self.health_status["last_check"].isoformat(),
            "age_seconds": age,
        }

    def reset_cache(self):
        """Reset health status cache"""
        self.health_status = {
            "last_check": None,
            "openwhisk_healthy": False,
            "gateway_healthy": False,
            "actions_healthy": 0,
            "total_actions": 0,
        }
        logger.info("Health cache reset")


async def create_health_check(
    client: OpenWhiskClient | None = None,
    gateway: OpenWhiskAPIGateway | None = None,
    controller: OpenWhiskIntegrationController | None = None,
) -> HealthCheck | None:
    """
    Factory function to create health check service

    Args:
        client: OpenWhisk client or None (auto-create)
        gateway: API gateway or None (auto-create)
        controller: Integration controller or None (auto-create)

    Returns:
        HealthCheck instance or None if not configured

    Example:
        >>> health = await create_health_check()
        >>> if health:
        >>>     status = await health.comprehensive_health_check()
        >>>     print(status['overall_status'])
    """
    try:
        health = HealthCheck(client=client, gateway=gateway, controller=controller)

        logger.info("Health check service created successfully")
        return health

    except Exception as e:
        logger.error(f"Error creating health check service: {e}")
        return None
