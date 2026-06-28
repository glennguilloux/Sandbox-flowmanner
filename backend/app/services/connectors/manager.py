"""
Connector Manager

Manages connector instances, registration, configuration, and execution.
Provides a unified interface for all external API integrations.
"""

import asyncio
import logging
from typing import Any

from .base import (
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    ConnectorStatus,
)
from .discord_connector import DiscordConnector
from .email_connector import EmailConnector
from .github_connector import GitHubConnector
from .google_connector import GoogleConnector
from .jira_connector import JiraConnector
from .linear_connector import LinearConnector
from .notion_connector import NotionConnector
from .sentry_connector import SentryConnector
from .slack_connector import SlackConnector
from .vercel_connector import VercelConnector
from .webhook_connector import WebhookConnector

logger = logging.getLogger(__name__)


class ConnectorManager:
    """
    Central manager for all external API connectors.

    Features:
    - Register and configure connectors
    - Execute actions on connectors
    - Monitor connector health
    - Manage connector lifecycle
    """

    CONNECTOR_CLASSES = {
        "slack": SlackConnector,
        "discord": DiscordConnector,
        "email": EmailConnector,
        "webhook": WebhookConnector,
        "github": GitHubConnector,
        "google": GoogleConnector,
        "notion": NotionConnector,
        "jira": JiraConnector,
        "linear": LinearConnector,
        "sentry": SentryConnector,
        "vercel": VercelConnector,
    }

    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}
        self._configs: dict[str, ConnectorConfig] = {}
        self._lock = asyncio.Lock()

    @property
    def registered_connectors(self) -> list[str]:
        """List all registered connector IDs"""
        return list(self._connectors.keys())

    @property
    def available_connector_types(self) -> list[str]:
        """List all available connector types"""
        return list(self.CONNECTOR_CLASSES.keys())

    def get_connector_class(self, connector_type: str) -> type[BaseConnector] | None:
        """Get connector class by type"""
        return self.CONNECTOR_CLASSES.get(connector_type)

    async def register_connector(
        self,
        connector_id: str,
        connector_type: str,
        config: dict[str, Any],
        auto_connect: bool = True,
    ) -> bool:
        """
        Register a new connector.

        Args:
            connector_id: Unique identifier for this connector instance
            connector_type: Type of connector (slack, discord, email, webhook)
            config: Configuration dictionary
            auto_connect: Whether to automatically connect after registration

        Returns:
            True if registration successful
        """
        async with self._lock:
            if connector_id in self._connectors:
                logger.warning("Connector '%s' already registered", connector_id)
                return False

            connector_class = self.get_connector_class(connector_type)
            if not connector_class:
                logger.error("Unknown connector type: %s", connector_type)
                return False

            try:
                # Create connector config
                connector_config = ConnectorConfig(
                    connector_id=connector_id,
                    name=config.get("name", connector_id),
                    base_url=config.get("base_url"),
                    auth_type=config.get("auth_type"),
                    auth_config=config.get("auth_config", {}),
                    headers=config.get("headers"),
                    timeout=config.get("timeout", 30.0),
                    rate_limit=config.get("rate_limit"),
                    retry_config=config.get("retry_config"),
                    metadata=config.get("metadata", {}),
                )

                # Create connector instance
                connector = connector_class(connector_config)

                # Connect if auto_connect
                if auto_connect:
                    connected = await connector.connect()
                    if not connected:
                        logger.error("Failed to connect connector '%s'", connector_id)
                        return False

                self._connectors[connector_id] = connector
                self._configs[connector_id] = connector_config

                logger.info(
                    "Registered connector '%s' of type '%s'",
                    connector_id,
                    connector_type,
                )
                return True

            except Exception as e:
                logger.error("Failed to register connector '%s': %s", connector_id, e)
                return False

    async def unregister_connector(self, connector_id: str) -> bool:
        """
        Unregister and disconnect a connector.

        Args:
            connector_id: ID of connector to unregister

        Returns:
            True if unregistration successful
        """
        async with self._lock:
            if connector_id not in self._connectors:
                logger.warning("Connector '%s' not found", connector_id)
                return False

            try:
                connector = self._connectors[connector_id]
                await connector.disconnect()

                del self._connectors[connector_id]
                del self._configs[connector_id]

                logger.info("Unregistered connector '%s'", connector_id)
                return True

            except Exception as e:
                logger.error("Failed to unregister connector '%s': %s", connector_id, e)
                return False

    def get_connector(self, connector_id: str) -> BaseConnector | None:
        """Get a connector instance by ID"""
        return self._connectors.get(connector_id)

    def get_connector_info(self, connector_id: str) -> dict[str, Any] | None:
        """Get connector information"""
        connector = self._connectors.get(connector_id)
        if not connector:
            return None

        return {
            "id": connector_id,
            "type": connector.connector_type,
            "name": connector.config.name,
            "status": connector.status.value,
            "available_actions": connector.available_actions,
            "stats": connector.get_stats(),
        }

    def list_connectors(self, connector_type: str | None = None) -> list[dict[str, Any]]:
        """
        List all registered connectors.

        Args:
            connector_type: Filter by connector type (optional)

        Returns:
            List of connector info dictionaries
        """
        result = []
        for connector_id, connector in self._connectors.items():
            if connector_type and connector.connector_type != connector_type:
                continue

            result.append(
                {
                    "id": connector_id,
                    "type": connector.connector_type,
                    "name": connector.config.name,
                    "status": connector.status.value,
                    "available_actions": connector.available_actions,
                }
            )

        return result

    async def execute(self, connector_id: str, action: str, params: dict[str, Any]) -> ConnectorResponse:
        """
        Execute an action on a connector.

        Args:
            connector_id: ID of the connector
            action: Action to execute
            params: Action parameters

        Returns:
            ConnectorResponse with result
        """
        connector = self._connectors.get(connector_id)
        if not connector:
            return ConnectorResponse(
                success=False,
                error=f"Connector '{connector_id}' not found",
                status_code=404,
            )

        if connector.status != ConnectorStatus.ACTIVE:
            return ConnectorResponse(
                success=False,
                error=f"Connector '{connector_id}' is not active (status: {connector.status.value})",
                status_code=503,
            )

        return await connector.execute_action(action, params)

    async def execute_batch(self, operations: list[dict[str, Any]]) -> list[ConnectorResponse]:
        """
        Execute multiple operations in parallel.

        Args:
            operations: List of {connector_id, action, params} dicts

        Returns:
            List of ConnectorResponse objects
        """
        tasks = []
        for op in operations:
            task = self.execute(op.get("connector_id"), op.get("action"), op.get("params", {}))
            tasks.append(task)

        return await asyncio.gather(*tasks, return_exceptions=False)

    async def health_check(self, connector_id: str | None = None) -> dict[str, Any]:
        """
        Check health of connectors.

        Args:
            connector_id: Specific connector to check (optional, checks all if not provided)

        Returns:
            Health check results
        """
        if connector_id:
            connector = self._connectors.get(connector_id)
            if not connector:
                return {"error": f"Connector '{connector_id}' not found"}

            is_healthy = await connector.health_check()
            return {
                connector_id: {
                    "healthy": is_healthy,
                    "status": connector.status.value,
                    "last_error": connector.last_error,  # type: ignore[attr-defined]
                }
            }

        results = {}
        for cid, connector in self._connectors.items():
            is_healthy = await connector.health_check()
            results[cid] = {
                "healthy": is_healthy,
                "status": connector.status.value,
                "last_error": connector.last_error,  # type: ignore[attr-defined]
            }

        return results

    async def reconnect(self, connector_id: str) -> bool:
        """
        Reconnect a connector.

        Args:
            connector_id: ID of connector to reconnect

        Returns:
            True if reconnection successful
        """
        connector = self._connectors.get(connector_id)
        if not connector:
            logger.warning("Connector '%s' not found", connector_id)
            return False

        try:
            await connector.disconnect()
            return await connector.connect()
        except Exception as e:
            logger.error("Failed to reconnect connector '%s': %s", connector_id, e)
            return False

    async def reconnect_all(self) -> dict[str, bool]:
        """
        Reconnect all connectors.

        Returns:
            Dictionary of connector_id -> success
        """
        results = {}
        for connector_id in self._connectors:
            results[connector_id] = await self.reconnect(connector_id)
        return results

    async def disconnect_all(self) -> None:
        """Disconnect all connectors"""
        for connector in self._connectors.values():
            try:
                await connector.disconnect()
            except Exception as e:
                logger.error("Error disconnecting connector: %s", e)

    def get_stats(self) -> dict[str, Any]:
        """Get overall statistics"""
        connector_stats = {}
        for connector_id, connector in self._connectors.items():
            connector_stats[connector_id] = connector.get_stats()

        return {
            "total_connectors": len(self._connectors),
            "connectors_by_type": self._count_by_type(),
            "connectors_by_status": self._count_by_status(),
            "connector_stats": connector_stats,
        }

    def _count_by_type(self) -> dict[str, int]:
        """Count connectors by type"""
        counts: dict[str, int] = {}
        for connector in self._connectors.values():
            ctype = connector.connector_type
            counts[ctype] = counts.get(ctype, 0) + 1
        return counts

    def _count_by_status(self) -> dict[str, int]:
        """Count connectors by status"""
        counts: dict[str, int] = {}
        for connector in self._connectors.values():
            status = connector.status.value
            counts[status] = counts.get(status, 0) + 1
        return counts


# Singleton instance
_manager_instance: ConnectorManager | None = None


def get_connector_manager() -> ConnectorManager:
    """Get the singleton connector manager instance"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ConnectorManager()
    return _manager_instance
