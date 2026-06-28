"""
Asana Connector

Provides integration with Asana API for:
- Projects (list, get)
- Tasks (list, get, create, update, complete)
- Sections (list)
- Workspaces (list)
- User info (get_me)
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
    from app.services.asana.asana_client import AsanaClient

logger = logging.getLogger(__name__)


class AsanaConnector(BaseConnector):
    """Asana project management connector."""

    CONNECTOR_TYPE = "asana"

    ASANA_RATE_LIMIT = RateLimitConfig(
        requests_per_second=1.5,  # ~100-150/min per user
        requests_per_minute=90,
        requests_per_hour=5000,
        burst_size=10,
    )

    ACTIONS = [
        "get_me",
        "list_workspaces",
        "list_projects",
        "get_project",
        "list_tasks",
        "get_task",
        "create_task",
        "update_task",
        "complete_task",
        "list_sections",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://app.asana.com/api/1.0"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.ASANA_RATE_LIMIT
        super().__init__(config)
        self._client: AsanaClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.asana.asana_client import AsanaClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            if not token:
                logger.debug("No Asana token available — skipping credential validation")
                return True
            self._client = AsanaClient(auth_token=token)
            me = await self._client.get_me()
            return bool(me.get("data", {}).get("gid"))
        except Exception as e:
            logger.warning("Asana credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_me": self._get_me,
            "list_workspaces": self._list_workspaces,
            "list_projects": self._list_projects,
            "get_project": self._get_project,
            "list_tasks": self._list_tasks,
            "get_task": self._get_task,
            "create_task": self._create_task,
            "update_task": self._update_task,
            "complete_task": self._complete_task,
            "list_sections": self._list_sections,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Asana action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_me(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AsanaClient not initialized — call connect() first"
        result = await self._client.get_me()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_workspaces(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AsanaClient not initialized — call connect() first"
        result = await self._client.list_workspaces()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_projects(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AsanaClient not initialized — call connect() first"
        result = await self._client.list_projects(
            workspace=params.get("workspace"),
            offset=params.get("offset"),
            limit=params.get("limit", 100),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_project(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AsanaClient not initialized — call connect() first"
        project_gid = params.get("project_gid") or params.get("project_id")
        if not project_gid:
            return ConnectorResponse(success=False, error="Missing: project_gid", status_code=400)
        result = await self._client.get_project(project_gid)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_tasks(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AsanaClient not initialized — call connect() first"
        result = await self._client.list_tasks(
            project=params.get("project"),
            assignee=params.get("assignee"),
            workspace=params.get("workspace"),
            completed_since=params.get("completed_since"),
            offset=params.get("offset"),
            limit=params.get("limit", 100),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_task(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AsanaClient not initialized — call connect() first"
        task_gid = params.get("task_gid") or params.get("task_id")
        if not task_gid:
            return ConnectorResponse(success=False, error="Missing: task_gid", status_code=400)
        result = await self._client.get_task(task_gid)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _create_task(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AsanaClient not initialized — call connect() first"
        name = params.get("name")
        if not name:
            return ConnectorResponse(success=False, error="Missing: name", status_code=400)
        result = await self._client.create_task(
            name=name,
            projects=params.get("projects"),
            notes=params.get("notes"),
            assignee=params.get("assignee"),
            due_on=params.get("due_on"),
        )
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _update_task(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AsanaClient not initialized — call connect() first"
        task_gid = params.get("task_gid") or params.get("task_id")
        if not task_gid:
            return ConnectorResponse(success=False, error="Missing: task_gid", status_code=400)
        result = await self._client.update_task(
            task_gid,
            name=params.get("name"),
            notes=params.get("notes"),
            assignee=params.get("assignee"),
            due_on=params.get("due_on"),
            completed=params.get("completed"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _complete_task(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AsanaClient not initialized — call connect() first"
        task_gid = params.get("task_gid") or params.get("task_id")
        if not task_gid:
            return ConnectorResponse(success=False, error="Missing: task_gid", status_code=400)
        result = await self._client.complete_task(task_gid)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_sections(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AsanaClient not initialized — call connect() first"
        project_gid = params.get("project_gid") or params.get("project_id")
        if not project_gid:
            return ConnectorResponse(success=False, error="Missing: project_gid", status_code=400)
        result = await self._client.list_sections(
            project_gid,
            offset=params.get("offset"),
            limit=params.get("limit", 100),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)
