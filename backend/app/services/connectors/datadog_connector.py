"""
Datadog Connector

Provides integration with Datadog for monitoring and observability via the BaseConnector framework.
Wraps the DatadogClient REST client to expose standard connector actions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

if TYPE_CHECKING:
    from app.services.datadog.datadog_client import DatadogClient

logger = logging.getLogger(__name__)


class DatadogConnector(BaseConnector):
    """Datadog monitoring/observability connector."""

    CONNECTOR_TYPE = "datadog"

    DATADOG_RATE_LIMIT = RateLimitConfig(
        requests_per_second=10.0,
        requests_per_minute=600,
        requests_per_hour=36000,
        burst_size=20,
    )

    ACTIONS = [
        "get_current_user",
        "list_monitors",
        "get_monitor",
        "list_incidents",
        "get_incident",
        "create_incident",
        "update_incident",
        "list_dashboards",
        "get_dashboard",
        "list_metrics",
        "query_metrics",
        "list_events",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.datadoghq.com"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.DATADOG_RATE_LIMIT
        super().__init__(config)
        self._client: DatadogClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.datadog.datadog_client import DatadogClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            if not token:
                logger.debug("No Datadog token available — skipping credential validation")
                return True
            self._client = DatadogClient(auth_token=token)
            user = await self._client.get_current_user()
            return bool(user.get("data", {}).get("id"))
        except Exception as e:
            logger.warning("Datadog credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_current_user": self._get_current_user,
            "list_monitors": self._list_monitors,
            "get_monitor": self._get_monitor,
            "list_incidents": self._list_incidents,
            "get_incident": self._get_incident,
            "create_incident": self._create_incident,
            "update_incident": self._update_incident,
            "list_dashboards": self._list_dashboards,
            "get_dashboard": self._get_dashboard,
            "list_metrics": self._list_metrics,
            "query_metrics": self._query_metrics,
            "list_events": self._list_events,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Datadog action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_current_user(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        user = await self._client.get_current_user()
        return ConnectorResponse(success=True, data=user, status_code=200)

    async def _list_monitors(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        monitors = await self._client.list_monitors(
            monitor_tags=params.get("monitor_tags"),
            page=params.get("page"),
            page_size=params.get("page_size"),
        )
        return ConnectorResponse(success=True, data={"monitors": monitors}, status_code=200)

    async def _get_monitor(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        monitor_id = params.get("monitor_id")
        if not monitor_id:
            return ConnectorResponse(success=False, error="Missing: monitor_id", status_code=400)
        monitor = await self._client.get_monitor(int(monitor_id))
        return ConnectorResponse(success=True, data=monitor, status_code=200)

    async def _list_incidents(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        incidents = await self._client.list_incidents(
            page_size=params.get("page_size"),
            page_offset=params.get("page_offset"),
        )
        return ConnectorResponse(success=True, data=incidents, status_code=200)

    async def _get_incident(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        incident_id = params.get("incident_id")
        if not incident_id:
            return ConnectorResponse(success=False, error="Missing: incident_id", status_code=400)
        incident = await self._client.get_incident(incident_id)
        return ConnectorResponse(success=True, data=incident, status_code=200)

    async def _create_incident(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        title = params.get("title")
        if not title:
            return ConnectorResponse(success=False, error="Missing: title", status_code=400)
        incident = await self._client.create_incident(
            title=title,
            severity=params.get("severity", "unknown"),
            customer_impacted=params.get("customer_impacted", False),
        )
        return ConnectorResponse(success=True, data=incident, status_code=201)

    async def _update_incident(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        incident_id = params.get("incident_id")
        if not incident_id:
            return ConnectorResponse(success=False, error="Missing: incident_id", status_code=400)
        result = await self._client.update_incident(
            incident_id=incident_id,
            title=params.get("title"),
            severity=params.get("severity"),
            state=params.get("state"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_dashboards(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        dashboards = await self._client.list_dashboards()
        return ConnectorResponse(success=True, data={"dashboards": dashboards}, status_code=200)

    async def _get_dashboard(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        dashboard_id = params.get("dashboard_id")
        if not dashboard_id:
            return ConnectorResponse(success=False, error="Missing: dashboard_id", status_code=400)
        dashboard = await self._client.get_dashboard(dashboard_id)
        return ConnectorResponse(success=True, data=dashboard, status_code=200)

    async def _list_metrics(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        metrics = await self._client.list_metrics(from_time=params.get("from_time"))
        return ConnectorResponse(success=True, data={"metrics": metrics}, status_code=200)

    async def _query_metrics(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        query = params.get("query")
        from_time = params.get("from_time")
        to_time = params.get("to_time")
        if not query or from_time is None or to_time is None:
            return ConnectorResponse(success=False, error="Missing: query, from_time, to_time", status_code=400)
        result = await self._client.query_metrics(query=query, from_time=int(from_time), to_time=int(to_time))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_events(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "DatadogClient not initialized — call connect() first"
        start = params.get("start")
        end = params.get("end")
        if start is None or end is None:
            return ConnectorResponse(success=False, error="Missing: start, end (unix timestamps)", status_code=400)
        events = await self._client.list_events(
            start=int(start),
            end=int(end),
            tags=params.get("tags"),
            sources=params.get("sources"),
            priority=params.get("priority"),
        )
        return ConnectorResponse(success=True, data=events, status_code=200)
