"""
ClickUp Connector

Provides integration with ClickUp API for:
- User info (get_user)
- Workspaces (list_workspaces)
- Spaces (list_spaces)
- Folders (list_folders)
- Lists (list_lists)
- Tasks (list, get, create, update)
- Comments (get, add)
- Time entries (list)
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
    from app.services.clickup.clickup_client import ClickUpClient

logger = logging.getLogger(__name__)


class ClickUpConnector(BaseConnector):
    """ClickUp project management connector."""

    CONNECTOR_TYPE = "clickup"

    CLICKUP_RATE_LIMIT = RateLimitConfig(
        requests_per_second=1.6,  # ~100/min per token
        requests_per_minute=90,
        requests_per_hour=5000,
        burst_size=10,
    )

    ACTIONS = [
        "get_user",
        "list_workspaces",
        "list_spaces",
        "list_folders",
        "list_lists",
        "list_tasks",
        "get_task",
        "create_task",
        "update_task",
        "get_comments",
        "add_comment",
        "list_time_entries",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.clickup.com/api/v2"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.CLICKUP_RATE_LIMIT
        super().__init__(config)
        self._client: ClickUpClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.clickup.clickup_client import ClickUpClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            if not token:
                logger.debug("No ClickUp token available — skipping credential validation")
                return True
            self._client = ClickUpClient(auth_token=token)
            user = await self._client.get_user()
            return bool(user.get("user", {}).get("id"))
        except Exception as e:
            logger.warning("ClickUp credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_user": self._get_user,
            "list_workspaces": self._list_workspaces,
            "list_spaces": self._list_spaces,
            "list_folders": self._list_folders,
            "list_lists": self._list_lists,
            "list_tasks": self._list_tasks,
            "get_task": self._get_task,
            "create_task": self._create_task,
            "update_task": self._update_task,
            "get_comments": self._get_comments,
            "add_comment": self._add_comment,
            "list_time_entries": self._list_time_entries,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("ClickUp action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_user(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        result = await self._client.get_user()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_workspaces(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        result = await self._client.list_workspaces()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_spaces(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        team_id = params.get("team_id")
        if not team_id:
            return ConnectorResponse(success=False, error="Missing: team_id", status_code=400)
        result = await self._client.list_spaces(team_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_folders(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        space_id = params.get("space_id")
        if not space_id:
            return ConnectorResponse(success=False, error="Missing: space_id", status_code=400)
        result = await self._client.list_folders(space_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_lists(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        folder_id = params.get("folder_id")
        if not folder_id:
            return ConnectorResponse(success=False, error="Missing: folder_id", status_code=400)
        result = await self._client.list_lists(folder_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_tasks(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        list_id = params.get("list_id")
        if not list_id:
            return ConnectorResponse(success=False, error="Missing: list_id", status_code=400)
        result = await self._client.list_tasks(
            list_id,
            page=params.get("page", 0),
            order_by=params.get("order_by", "created"),
            reverse=params.get("reverse", False),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_task(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        task_id = params.get("task_id")
        if not task_id:
            return ConnectorResponse(success=False, error="Missing: task_id", status_code=400)
        result = await self._client.get_task(task_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _create_task(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        list_id = params.get("list_id")
        name = params.get("name")
        if not list_id or not name:
            return ConnectorResponse(success=False, error="Missing: list_id and name", status_code=400)
        result = await self._client.create_task(
            list_id,
            name=name,
            description=params.get("description"),
            assignees=params.get("assignees"),
            priority=params.get("priority"),
            due_date=params.get("due_date"),
            status=params.get("status"),
        )
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _update_task(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        task_id = params.get("task_id")
        if not task_id:
            return ConnectorResponse(success=False, error="Missing: task_id", status_code=400)
        result = await self._client.update_task(
            task_id,
            name=params.get("name"),
            description=params.get("description"),
            status=params.get("status"),
            priority=params.get("priority"),
            due_date=params.get("due_date"),
            assignees=params.get("assignees"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_comments(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        task_id = params.get("task_id")
        if not task_id:
            return ConnectorResponse(success=False, error="Missing: task_id", status_code=400)
        result = await self._client.get_comments(task_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _add_comment(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        task_id = params.get("task_id")
        comment_text = params.get("comment_text")
        if not task_id or not comment_text:
            return ConnectorResponse(success=False, error="Missing: task_id and comment_text", status_code=400)
        result = await self._client.add_comment(task_id, comment_text)
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _list_time_entries(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ClickUpClient not initialized — call connect() first"
        team_id = params.get("team_id")
        if not team_id:
            return ConnectorResponse(success=False, error="Missing: team_id", status_code=400)
        result = await self._client.list_time_entries(team_id)
        return ConnectorResponse(success=True, data=result, status_code=200)
