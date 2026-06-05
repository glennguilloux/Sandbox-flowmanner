"""
Notion Connector

Provides integration with Notion API for:
- Search across pages and databases
- Database operations (get, query)
- Page operations (get, create, update)
- Block operations (get children, append children)
"""

import logging
from typing import Any

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)


class NotionConnector(BaseConnector):
    """
    Notion API connector for page, database, and block operations.

    Supports:
    - Search: find pages and databases by title
    - Databases: get schema, query rows
    - Pages: create, read, update page properties and content
    - Blocks: read and append block children
    """

    CONNECTOR_TYPE = "notion"

    # Notion API rate limits: 3 req/sec for most endpoints
    NOTION_RATE_LIMIT = RateLimitConfig(
        requests_per_second=3.0,
        requests_per_minute=180,
        requests_per_hour=10000,
        burst_size=10,
    )

    BASE_URL = "https://api.notion.com/v1"

    ACTIONS = [
        "search",
        "list_databases",
        "query_database",
        "get_page",
        "create_page",
        "update_page",
        "get_block_children",
        "append_block_children",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or self.BASE_URL
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.NOTION_RATE_LIMIT
        config.headers = {
            **config.headers,
            "Accept": "application/json",
            "Notion-Version": "2022-06-28",
        }

        super().__init__(config)
        self._authenticated_user: str | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        """Validate Notion token by calling /users/me."""
        response = await self._execute_request("GET", "users/me")

        if response.success and response.data:
            bot_info = response.data
            name = bot_info.get("name") or "Notion Bot"
            bot_type = bot_info.get("type", "unknown")
            self._authenticated_user = f"{name} ({bot_type})"
            return True

        return False

    async def execute_action(
        self,
        action: str,
        params: dict[str, Any],
    ) -> ConnectorResponse:
        """Execute a Notion connector action."""

        action_handlers = {
            "search": self._search,
            "list_databases": self._list_databases,
            "query_database": self._query_database,
            "get_page": self._get_page,
            "create_page": self._create_page,
            "update_page": self._update_page,
            "get_block_children": self._get_block_children,
            "append_block_children": self._append_block_children,
        }

        handler = action_handlers.get(action)
        if not handler:
            return ConnectorResponse(
                success=False,
                error=f"Unknown action: {action}",
                status_code=400,
            )

        return await handler(params)

    # ═══════════════════════════════════════════════════════════════
    #  Search
    # ═══════════════════════════════════════════════════════════════

    async def _search(self, params: dict[str, Any]) -> ConnectorResponse:
        """Search pages and databases by title."""
        q = params.get("q") or params.get("query")
        if not q:
            return ConnectorResponse(
                success=False,
                error="Missing required param: q (search query)",
                status_code=400,
            )

        payload: dict[str, Any] = {
            "query": q,
            "page_size": params.get("page_size", 20),
        }
        if params.get("filter"):
            payload["filter"] = params["filter"]
        if params.get("sort"):
            payload["sort"] = params["sort"]

        return await self._execute_with_retry(
            "POST",
            "search",
            json_data=payload,
        )

    # ═══════════════════════════════════════════════════════════════
    #  Databases
    # ═══════════════════════════════════════════════════════════════

    async def _list_databases(self, params: dict[str, Any]) -> ConnectorResponse:
        """List databases shared with the integration."""
        query_params: dict[str, Any] = {
            "page_size": params.get("page_size", 20),
        }
        if params.get("start_cursor"):
            query_params["start_cursor"] = params["start_cursor"]

        return await self._execute_with_retry(
            "GET",
            "databases",
            params=query_params,
        )

    async def _query_database(self, params: dict[str, Any]) -> ConnectorResponse:
        """Query rows from a Notion database."""
        database_id = params.get("database_id")
        if not database_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: database_id",
                status_code=400,
            )

        payload: dict[str, Any] = {
            "page_size": params.get("page_size", 20),
        }
        if params.get("filter"):
            payload["filter"] = params["filter"]
        if params.get("sorts"):
            payload["sorts"] = params["sorts"]
        if params.get("start_cursor"):
            payload["start_cursor"] = params["start_cursor"]

        return await self._execute_with_retry(
            "POST",
            f"databases/{database_id}/query",
            json_data=payload,
        )

    # ═══════════════════════════════════════════════════════════════
    #  Pages
    # ═══════════════════════════════════════════════════════════════

    async def _get_page(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get a page by ID."""
        page_id = params.get("page_id")
        if not page_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: page_id",
                status_code=400,
            )

        return await self._execute_with_retry(
            "GET",
            f"pages/{page_id}",
        )

    async def _create_page(self, params: dict[str, Any]) -> ConnectorResponse:
        """Create a new page (in a database or as a child of another page)."""
        parent = params.get("parent")
        properties = params.get("properties")

        if not parent:
            return ConnectorResponse(
                success=False,
                error="Missing required param: parent (e.g. {'database_id': '...'} or {'page_id': '...'})",
                status_code=400,
            )
        if not properties:
            return ConnectorResponse(
                success=False,
                error="Missing required param: properties (page property values)",
                status_code=400,
            )

        payload: dict[str, Any] = {
            "parent": parent,
            "properties": properties,
        }
        if params.get("children"):
            payload["children"] = params["children"]
        if params.get("icon"):
            payload["icon"] = params["icon"]
        if params.get("cover"):
            payload["cover"] = params["cover"]

        return await self._execute_with_retry(
            "POST",
            "pages",
            json_data=payload,
        )

    async def _update_page(self, params: dict[str, Any]) -> ConnectorResponse:
        """Update page properties."""
        page_id = params.get("page_id")
        if not page_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: page_id",
                status_code=400,
            )

        payload: dict[str, Any] = {}
        if params.get("properties"):
            payload["properties"] = params["properties"]
        if params.get("archived") is not None:
            payload["archived"] = params["archived"]
        if params.get("icon"):
            payload["icon"] = params["icon"]
        if params.get("cover"):
            payload["cover"] = params["cover"]

        if not payload:
            return ConnectorResponse(
                success=False,
                error="No update fields provided",
                status_code=400,
            )

        return await self._execute_with_retry(
            "PATCH",
            f"pages/{page_id}",
            json_data=payload,
        )

    # ═══════════════════════════════════════════════════════════════
    #  Blocks
    # ═══════════════════════════════════════════════════════════════

    async def _get_block_children(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get the children (content blocks) of a page or block."""
        block_id = params.get("block_id")
        if not block_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: block_id",
                status_code=400,
            )

        query_params: dict[str, Any] = {
            "page_size": params.get("page_size", 20),
        }
        if params.get("start_cursor"):
            query_params["start_cursor"] = params["start_cursor"]

        return await self._execute_with_retry(
            "GET",
            f"blocks/{block_id}/children",
            params=query_params,
        )

    async def _append_block_children(self, params: dict[str, Any]) -> ConnectorResponse:
        """Append content blocks to a page or block."""
        block_id = params.get("block_id")
        children = params.get("children")

        if not block_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: block_id",
                status_code=400,
            )
        if not children:
            return ConnectorResponse(
                success=False,
                error="Missing required param: children (list of block objects)",
                status_code=400,
            )

        return await self._execute_with_retry(
            "PATCH",
            f"blocks/{block_id}/children",
            json_data={"children": children},
        )

    def get_stats(self) -> dict[str, Any]:
        """Get connector statistics including Notion-specific info."""
        stats = super().get_stats()
        stats.update({"authenticated_user": self._authenticated_user})
        return stats
