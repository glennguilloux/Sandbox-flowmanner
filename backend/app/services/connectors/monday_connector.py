"""
Monday.com Connector

Provides integration with Monday.com GraphQL API for:
- User info (get_me)
- Boards (list, get)
- Items (list, get, create, update)
- Updates/comments (create)
- Users (list)
- Workspaces (list)
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
    from app.services.monday.monday_client import MondayClient

logger = logging.getLogger(__name__)


class MondayConnector(BaseConnector):
    """Monday.com work management connector."""

    CONNECTOR_TYPE = "monday"

    MONDAY_RATE_LIMIT = RateLimitConfig(
        requests_per_second=1.0,
        requests_per_minute=30,
        requests_per_hour=1800,
        burst_size=5,
    )

    ACTIONS = [
        "get_me",
        "list_boards",
        "get_board",
        "list_items",
        "get_item",
        "create_item",
        "update_item",
        "create_update",
        "list_users",
        "list_workspaces",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.monday.com/v2"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.MONDAY_RATE_LIMIT
        super().__init__(config)
        self._client: MondayClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.monday.monday_client import MondayClient

            access_token = self.config.auth_config.get("access_token", "")
            if not access_token:
                logger.debug("Monday credentials not configured — skipping validation")
                return True
            self._client = MondayClient(access_token=access_token)
            me = await self._client.get_me()
            return bool(me.get("id"))
        except Exception as e:
            logger.warning("Monday credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_me": self._get_me,
            "list_boards": self._list_boards,
            "get_board": self._get_board,
            "list_items": self._list_items,
            "get_item": self._get_item,
            "create_item": self._create_item,
            "update_item": self._update_item,
            "create_update": self._create_update,
            "list_users": self._list_users,
            "list_workspaces": self._list_workspaces,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Monday action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_me(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "MondayClient not initialized — call connect() first"
        result = await self._client.get_me()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_boards(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "MondayClient not initialized — call connect() first"
        result = await self._client.list_boards(limit=params.get("limit", 50))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_board(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "MondayClient not initialized — call connect() first"
        board_id = params.get("board_id")
        if not board_id:
            return ConnectorResponse(success=False, error="Missing: board_id", status_code=400)
        result = await self._client.get_board(board_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_items(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "MondayClient not initialized — call connect() first"
        board_id = params.get("board_id")
        if not board_id:
            return ConnectorResponse(success=False, error="Missing: board_id", status_code=400)
        result = await self._client.list_items(board_id, limit=params.get("limit", 50))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_item(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "MondayClient not initialized — call connect() first"
        item_id = params.get("item_id")
        if not item_id:
            return ConnectorResponse(success=False, error="Missing: item_id", status_code=400)
        result = await self._client.get_item(item_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _create_item(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "MondayClient not initialized — call connect() first"
        board_id = params.get("board_id")
        item_name = params.get("item_name")
        if not board_id or not item_name:
            return ConnectorResponse(success=False, error="Missing: board_id and item_name", status_code=400)
        result = await self._client.create_item(
            board_id,
            item_name,
            group_id=params.get("group_id"),
            column_values=params.get("column_values"),
        )
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _update_item(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "MondayClient not initialized — call connect() first"
        item_id = params.get("item_id")
        board_id = params.get("board_id")
        column_values = params.get("column_values")
        if not item_id or not board_id or not column_values:
            return ConnectorResponse(
                success=False, error="Missing: item_id, board_id, and column_values", status_code=400
            )
        result = await self._client.update_item(item_id, board_id, column_values)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _create_update(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "MondayClient not initialized — call connect() first"
        item_id = params.get("item_id")
        body = params.get("body")
        if not item_id or not body:
            return ConnectorResponse(success=False, error="Missing: item_id and body", status_code=400)
        result = await self._client.create_update(item_id, body)
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _list_users(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "MondayClient not initialized — call connect() first"
        result = await self._client.list_users(limit=params.get("limit", 50))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_workspaces(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "MondayClient not initialized — call connect() first"
        result = await self._client.list_workspaces()
        return ConnectorResponse(success=True, data=result, status_code=200)
