"""
Vercel Connector

Provides integration with Vercel for deployment monitoring via the BaseConnector framework.
Wraps the VercelClient REST client to expose standard connector actions.
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
    from app.services.vercel.vercel_client import VercelClient

logger = logging.getLogger(__name__)


class VercelConnector(BaseConnector):
    """Vercel deployment monitoring connector."""

    CONNECTOR_TYPE = "vercel"

    VERCEL_RATE_LIMIT = RateLimitConfig(
        requests_per_second=10.0,
        requests_per_minute=300,
        requests_per_hour=10000,
        burst_size=20,
    )

    ACTIONS = [
        "get_me",
        "list_projects",
        "get_project",
        "list_deployments",
        "get_deployment",
        "cancel_deployment",
        "redeploy",
        "get_deployment_logs",
        "list_domains",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.vercel.com"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.VERCEL_RATE_LIMIT
        super().__init__(config)
        self._client: VercelClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.vercel.vercel_client import VercelClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            if not token:
                logger.debug("No Vercel token available — skipping credential validation")
                return True
            self._client = VercelClient(auth_token=token)
            user = await self._client.get_me()
            return bool(user.get("user", {}).get("id"))
        except Exception as e:
            logger.warning("Vercel credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_me": self._get_me,
            "list_projects": self._list_projects,
            "get_project": self._get_project,
            "list_deployments": self._list_deployments,
            "get_deployment": self._get_deployment,
            "cancel_deployment": self._cancel_deployment,
            "redeploy": self._redeploy,
            "get_deployment_logs": self._get_deployment_logs,
            "list_domains": self._list_domains,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Vercel action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_me(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "VercelClient not initialized — call connect() first"
        user = await self._client.get_me()
        return ConnectorResponse(success=True, data=user, status_code=200)

    async def _list_projects(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "VercelClient not initialized — call connect() first"
        projects = await self._client.list_projects(
            limit=params.get("limit", 20),
            until=params.get("until"),
        )
        return ConnectorResponse(success=True, data=projects, status_code=200)

    async def _get_project(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "VercelClient not initialized — call connect() first"
        project_id = params.get("project_id")
        if not project_id:
            return ConnectorResponse(success=False, error="Missing: project_id", status_code=400)
        project = await self._client.get_project(project_id)
        return ConnectorResponse(success=True, data=project, status_code=200)

    async def _list_deployments(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "VercelClient not initialized — call connect() first"
        deployments = await self._client.list_deployments(
            project_id=params.get("project_id"),
            limit=params.get("limit", 20),
            until=params.get("until"),
        )
        return ConnectorResponse(success=True, data=deployments, status_code=200)

    async def _get_deployment(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "VercelClient not initialized — call connect() first"
        deployment_id = params.get("deployment_id")
        if not deployment_id:
            return ConnectorResponse(success=False, error="Missing: deployment_id", status_code=400)
        deployment = await self._client.get_deployment(deployment_id)
        return ConnectorResponse(success=True, data=deployment, status_code=200)

    async def _cancel_deployment(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "VercelClient not initialized — call connect() first"
        deployment_id = params.get("deployment_id")
        if not deployment_id:
            return ConnectorResponse(success=False, error="Missing: deployment_id", status_code=400)
        result = await self._client.cancel_deployment(deployment_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _redeploy(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "VercelClient not initialized — call connect() first"
        deployment_id = params.get("deployment_id")
        if not deployment_id:
            return ConnectorResponse(success=False, error="Missing: deployment_id", status_code=400)
        result = await self._client.redeploy(
            deployment_id=deployment_id,
            target=params.get("target"),
            name=params.get("name"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_deployment_logs(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "VercelClient not initialized — call connect() first"
        deployment_id = params.get("deployment_id")
        if not deployment_id:
            return ConnectorResponse(success=False, error="Missing: deployment_id", status_code=400)
        events = await self._client.get_deployment_events(deployment_id)
        return ConnectorResponse(success=True, data={"events": events}, status_code=200)

    async def _list_domains(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "VercelClient not initialized — call connect() first"
        project_id = params.get("project_id")
        if not project_id:
            return ConnectorResponse(success=False, error="Missing: project_id", status_code=400)
        domains = await self._client.list_domains(project_id)
        return ConnectorResponse(success=True, data=domains, status_code=200)
