"""
PagerDuty Connector

Provides integration with PagerDuty for incident management via the BaseConnector framework.
Wraps the PagerDutyClient REST client to expose standard connector actions.
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
    from app.services.pagerduty.pagerduty_client import PagerDutyClient

logger = logging.getLogger(__name__)


class PagerDutyConnector(BaseConnector):
    """PagerDuty incident management connector."""

    CONNECTOR_TYPE = "pagerduty"

    PAGERDUTY_RATE_LIMIT = RateLimitConfig(
        requests_per_second=16.0,
        requests_per_minute=960,
        requests_per_hour=57600,
        burst_size=30,
    )

    ACTIONS = [
        "get_me",
        "list_incidents",
        "get_incident",
        "create_incident",
        "update_incident",
        "list_services",
        "get_service",
        "list_schedules",
        "get_schedule",
        "list_escalation_policies",
        "list_users",
        "get_user",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.pagerduty.com"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.PAGERDUTY_RATE_LIMIT
        super().__init__(config)
        self._client: PagerDutyClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.pagerduty.pagerduty_client import PagerDutyClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            if not token:
                logger.debug("No PagerDuty token available — skipping credential validation")
                return True
            self._client = PagerDutyClient(auth_token=token)
            me = await self._client.get_me()
            return bool(me.get("user", {}).get("id"))
        except Exception as e:
            logger.warning("PagerDuty credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_me": self._get_me,
            "list_incidents": self._list_incidents,
            "get_incident": self._get_incident,
            "create_incident": self._create_incident,
            "update_incident": self._update_incident,
            "list_services": self._list_services,
            "get_service": self._get_service,
            "list_schedules": self._list_schedules,
            "get_schedule": self._get_schedule,
            "list_escalation_policies": self._list_escalation_policies,
            "list_users": self._list_users,
            "get_user": self._get_user,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("PagerDuty action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_me(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        me = await self._client.get_me()
        return ConnectorResponse(success=True, data=me, status_code=200)

    async def _list_incidents(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        incidents = await self._client.list_incidents(
            limit=params.get("limit", 25),
            offset=params.get("offset"),
            statuses=params.get("statuses"),
            urgencies=params.get("urgencies"),
            service_ids=params.get("service_ids"),
        )
        return ConnectorResponse(success=True, data=incidents, status_code=200)

    async def _get_incident(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        incident_id = params.get("incident_id")
        if not incident_id:
            return ConnectorResponse(success=False, error="Missing: incident_id", status_code=400)
        incident = await self._client.get_incident(incident_id)
        return ConnectorResponse(success=True, data=incident, status_code=200)

    async def _create_incident(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        title = params.get("title")
        service_id = params.get("service_id")
        if not title or not service_id:
            return ConnectorResponse(success=False, error="Missing: title and service_id", status_code=400)
        incident = await self._client.create_incident(
            title=title,
            service_id=service_id,
            urgency=params.get("urgency", "high"),
            body=params.get("body"),
            incident_key=params.get("incident_key"),
        )
        return ConnectorResponse(success=True, data=incident, status_code=201)

    async def _update_incident(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        incident_id = params.get("incident_id")
        if not incident_id:
            return ConnectorResponse(success=False, error="Missing: incident_id", status_code=400)
        result = await self._client.update_incident(
            incident_id=incident_id,
            status=params.get("status"),
            priority=params.get("priority"),
            note=params.get("note"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_services(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        services = await self._client.list_services(
            limit=params.get("limit", 25),
            offset=params.get("offset"),
        )
        return ConnectorResponse(success=True, data=services, status_code=200)

    async def _get_service(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        service_id = params.get("service_id")
        if not service_id:
            return ConnectorResponse(success=False, error="Missing: service_id", status_code=400)
        service = await self._client.get_service(service_id)
        return ConnectorResponse(success=True, data=service, status_code=200)

    async def _list_schedules(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        schedules = await self._client.list_schedules(
            limit=params.get("limit", 25),
            offset=params.get("offset"),
        )
        return ConnectorResponse(success=True, data=schedules, status_code=200)

    async def _get_schedule(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        schedule_id = params.get("schedule_id")
        if not schedule_id:
            return ConnectorResponse(success=False, error="Missing: schedule_id", status_code=400)
        schedule = await self._client.get_schedule(schedule_id)
        return ConnectorResponse(success=True, data=schedule, status_code=200)

    async def _list_escalation_policies(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        policies = await self._client.list_escalation_policies(
            limit=params.get("limit", 25),
            offset=params.get("offset"),
        )
        return ConnectorResponse(success=True, data=policies, status_code=200)

    async def _list_users(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        users = await self._client.list_users(
            limit=params.get("limit", 25),
            offset=params.get("offset"),
        )
        return ConnectorResponse(success=True, data=users, status_code=200)

    async def _get_user(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "PagerDutyClient not initialized — call connect() first"
        user_id = params.get("user_id")
        if not user_id:
            return ConnectorResponse(success=False, error="Missing: user_id", status_code=400)
        user = await self._client.get_user(user_id)
        return ConnectorResponse(success=True, data=user, status_code=200)
