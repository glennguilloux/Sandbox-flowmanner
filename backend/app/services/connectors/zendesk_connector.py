"""
Zendesk Connector

Provides integration with Zendesk API v2 for:
- Current user (get_me)
- Tickets (list, get, create, update, search)
- Users (list, get)
- Organizations (list)
- Groups (list)
- Ticket comments (add)
- Ticket metrics (list)
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
    from app.services.zendesk.zendesk_client import ZendeskClient

logger = logging.getLogger(__name__)


class ZendeskConnector(BaseConnector):
    """Zendesk customer support connector."""

    CONNECTOR_TYPE = "zendesk"

    ZENDESK_RATE_LIMIT = RateLimitConfig(
        requests_per_second=3.0,
        requests_per_minute=200,
        requests_per_hour=12000,
        burst_size=10,
    )

    ACTIONS = [
        "get_me",
        "list_tickets",
        "get_ticket",
        "create_ticket",
        "update_ticket",
        "list_users",
        "get_user",
        "search_tickets",
        "list_organizations",
        "list_groups",
        "add_ticket_comment",
        "list_ticket_metrics",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://zendesk.com"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.ZENDESK_RATE_LIMIT
        super().__init__(config)
        self._client: ZendeskClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.config import settings
            from app.services.zendesk.zendesk_client import ZendeskClient

            subdomain = self.config.auth_config.get("subdomain", "")
            access_token = self.config.auth_config.get("access_token", "")
            if not subdomain or not access_token:
                logger.debug("Zendesk credentials not configured — skipping validation")
                return True
            self._client = ZendeskClient(subdomain=subdomain, access_token=access_token)
            me = await self._client.get_me()
            return bool(me.get("id"))
        except Exception as e:
            logger.warning("Zendesk credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_me": self._get_me,
            "list_tickets": self._list_tickets,
            "get_ticket": self._get_ticket,
            "create_ticket": self._create_ticket,
            "update_ticket": self._update_ticket,
            "list_users": self._list_users,
            "get_user": self._get_user,
            "search_tickets": self._search_tickets,
            "list_organizations": self._list_organizations,
            "list_groups": self._list_groups,
            "add_ticket_comment": self._add_ticket_comment,
            "list_ticket_metrics": self._list_ticket_metrics,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Zendesk action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_me(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        result = await self._client.get_me()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_tickets(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        result = await self._client.list_tickets(page=params.get("page", 1), per_page=params.get("per_page", 25))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_ticket(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        ticket_id = params.get("ticket_id")
        if not ticket_id:
            return ConnectorResponse(success=False, error="Missing: ticket_id", status_code=400)
        result = await self._client.get_ticket(ticket_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _create_ticket(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        subject = params.get("subject")
        if not subject:
            return ConnectorResponse(success=False, error="Missing: subject", status_code=400)
        result = await self._client.create_ticket(params)
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _update_ticket(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        ticket_id = params.get("ticket_id")
        if not ticket_id:
            return ConnectorResponse(success=False, error="Missing: ticket_id", status_code=400)
        result = await self._client.update_ticket(ticket_id, {k: v for k, v in params.items() if k != "ticket_id"})
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_users(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        result = await self._client.list_users(page=params.get("page", 1), per_page=params.get("per_page", 25))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_user(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        user_id = params.get("user_id")
        if not user_id:
            return ConnectorResponse(success=False, error="Missing: user_id", status_code=400)
        result = await self._client.get_user(user_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _search_tickets(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        query = params.get("query")
        if not query:
            return ConnectorResponse(success=False, error="Missing: query", status_code=400)
        result = await self._client.search_tickets(query, per_page=params.get("per_page", 25))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_organizations(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        result = await self._client.list_organizations(page=params.get("page", 1), per_page=params.get("per_page", 25))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_groups(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        result = await self._client.list_groups(page=params.get("page", 1), per_page=params.get("per_page", 25))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _add_ticket_comment(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        ticket_id = params.get("ticket_id")
        comment_body = params.get("comment_body")
        if not ticket_id or not comment_body:
            return ConnectorResponse(success=False, error="Missing: ticket_id and comment_body", status_code=400)
        result = await self._client.add_ticket_comment(ticket_id, comment_body, public=params.get("public", True))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_ticket_metrics(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ZendeskClient not initialized — call connect() first"
        result = await self._client.list_ticket_metrics(page=params.get("page", 1), per_page=params.get("per_page", 25))
        return ConnectorResponse(success=True, data=result, status_code=200)
