"""
Confluence Connector

Provides integration with Confluence Cloud for knowledge base management
via the BaseConnector framework. Wraps the ConfluenceClient REST client
to expose standard connector actions.
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
    from app.services.confluence.confluence_client import ConfluenceClient

logger = logging.getLogger(__name__)


class ConfluenceConnector(BaseConnector):
    """Confluence Cloud knowledge base connector."""

    CONNECTOR_TYPE = "confluence"

    CONFLUENCE_RATE_LIMIT = RateLimitConfig(
        requests_per_second=5.0,
        requests_per_minute=100,
        requests_per_hour=5000,
        burst_size=10,
    )

    ACTIONS = [
        "get_me",
        "list_spaces",
        "get_space",
        "get_page",
        "create_page",
        "update_page",
        "search_content",
        "list_page_children",
        "add_comment",
        "list_attachments",
        "add_labels",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.atlassian.com"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.CONFLUENCE_RATE_LIMIT
        super().__init__(config)
        self._client: ConfluenceClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.confluence.confluence_client import ConfluenceClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            cloud_id = self.config.auth_config.get("cloud_id", "")
            if not token or not cloud_id:
                logger.debug("No Confluence token or cloudId available — skipping credential validation")
                return True
            self._client = ConfluenceClient(cloud_id=cloud_id, auth_token=token)
            user = await self._client.get_me()
            return bool(user.get("accountId") or user.get("email"))
        except Exception as e:
            logger.warning("Confluence credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_me": self._get_me,
            "list_spaces": self._list_spaces,
            "get_space": self._get_space,
            "get_page": self._get_page,
            "create_page": self._create_page,
            "update_page": self._update_page,
            "search_content": self._search_content,
            "list_page_children": self._list_page_children,
            "add_comment": self._add_comment,
            "list_attachments": self._list_attachments,
            "add_labels": self._add_labels,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Confluence action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_me(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ConfluenceClient not initialized — call connect() first"
        user = await self._client.get_me()
        return ConnectorResponse(success=True, data=user, status_code=200)

    async def _list_spaces(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ConfluenceClient not initialized — call connect() first"
        spaces = await self._client.list_spaces(limit=params.get("limit", 25))
        return ConnectorResponse(success=True, data={"spaces": spaces}, status_code=200)

    async def _get_space(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ConfluenceClient not initialized — call connect() first"
        space_id = params.get("space_id")
        if not space_id:
            return ConnectorResponse(success=False, error="Missing: space_id", status_code=400)
        space = await self._client.get_space(space_id)
        return ConnectorResponse(success=True, data=space, status_code=200)

    async def _get_page(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ConfluenceClient not initialized — call connect() first"
        page_id = params.get("page_id")
        if not page_id:
            return ConnectorResponse(success=False, error="Missing: page_id", status_code=400)
        page = await self._client.get_page(page_id)
        return ConnectorResponse(success=True, data=page, status_code=200)

    async def _create_page(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ConfluenceClient not initialized — call connect() first"
        space_id = params.get("space_id")
        title = params.get("title")
        body = params.get("body")
        if not space_id or not title or not body:
            return ConnectorResponse(success=False, error="Missing: space_id, title, and body", status_code=400)
        page = await self._client.create_page(
            space_id=space_id,
            title=title,
            body=body,
            parent_id=params.get("parent_id"),
        )
        return ConnectorResponse(success=True, data=page, status_code=201)

    async def _update_page(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ConfluenceClient not initialized — call connect() first"
        page_id = params.get("page_id")
        title = params.get("title")
        body = params.get("body")
        if not page_id or not title or not body:
            return ConnectorResponse(success=False, error="Missing: page_id, title, and body", status_code=400)
        # Fetch current page to get version number
        current = await self._client.get_page(page_id)
        version_number = current.get("version", {}).get("number", 1)
        page = await self._client.update_page(
            page_id=page_id,
            title=title,
            body=body,
            version_number=version_number + 1,
        )
        return ConnectorResponse(success=True, data=page, status_code=200)

    async def _search_content(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ConfluenceClient not initialized — call connect() first"
        cql = params.get("cql")
        if not cql:
            return ConnectorResponse(success=False, error="Missing: cql", status_code=400)
        result = await self._client.search_content(
            cql=cql,
            limit=params.get("limit", 25),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_page_children(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ConfluenceClient not initialized — call connect() first"
        page_id = params.get("page_id")
        if not page_id:
            return ConnectorResponse(success=False, error="Missing: page_id", status_code=400)
        children = await self._client.list_page_children(page_id, limit=params.get("limit", 25))
        return ConnectorResponse(success=True, data={"children": children}, status_code=200)

    async def _add_comment(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ConfluenceClient not initialized — call connect() first"
        page_id = params.get("page_id")
        body = params.get("body")
        if not page_id or not body:
            return ConnectorResponse(success=False, error="Missing: page_id and body", status_code=400)
        comment = await self._client.add_comment(page_id, body)
        return ConnectorResponse(success=True, data=comment, status_code=201)

    async def _list_attachments(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ConfluenceClient not initialized — call connect() first"
        page_id = params.get("page_id")
        if not page_id:
            return ConnectorResponse(success=False, error="Missing: page_id", status_code=400)
        attachments = await self._client.list_attachments(page_id, limit=params.get("limit", 25))
        return ConnectorResponse(success=True, data={"attachments": attachments}, status_code=200)

    async def _add_labels(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ConfluenceClient not initialized — call connect() first"
        page_id = params.get("page_id")
        labels = params.get("labels")
        if not page_id or not labels:
            return ConnectorResponse(success=False, error="Missing: page_id and labels", status_code=400)
        result = await self._client.add_labels(page_id, labels)
        return ConnectorResponse(success=True, data=result, status_code=201)
