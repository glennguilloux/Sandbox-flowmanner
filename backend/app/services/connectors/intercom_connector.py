"""
Intercom Connector

Provides integration with Intercom API for:
- Customer conversations (list, get, reply)
- Contacts (list, get, search)
- Companies, teams, and tags
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
    from app.services.intercom.intercom_client import IntercomClient

logger = logging.getLogger(__name__)


class IntercomConnector(BaseConnector):
    """Intercom customer messaging connector."""

    CONNECTOR_TYPE = "intercom"

    INTERCOM_RATE_LIMIT = RateLimitConfig(
        requests_per_second=50.0,  # 10,000/min per app
        requests_per_minute=500,
        requests_per_hour=10000,
        burst_size=50,
    )

    ACTIONS = [
        "get_admin",
        "list_conversations",
        "get_conversation",
        "reply_to_conversation",
        "list_contacts",
        "get_contact",
        "list_companies",
        "list_teams",
        "list_tags",
        "search_contacts",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.intercom.io"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.INTERCOM_RATE_LIMIT
        super().__init__(config)
        self._client: IntercomClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.intercom.intercom_client import IntercomClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            if not token:
                logger.debug("No Intercom token available — skipping credential validation")
                return True
            self._client = IntercomClient(auth_token=token)
            admin = await self._client.get_admin()
            return bool(admin.get("id"))
        except Exception as e:
            logger.warning("Intercom credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_admin": self._get_admin,
            "list_conversations": self._list_conversations,
            "get_conversation": self._get_conversation,
            "reply_to_conversation": self._reply_to_conversation,
            "list_contacts": self._list_contacts,
            "get_contact": self._get_contact,
            "list_companies": self._list_companies,
            "list_teams": self._list_teams,
            "list_tags": self._list_tags,
            "search_contacts": self._search_contacts,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Intercom action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_admin(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "IntercomClient not initialized — call connect() first"
        admin = await self._client.get_admin()
        return ConnectorResponse(success=True, data=admin, status_code=200)

    async def _list_conversations(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "IntercomClient not initialized — call connect() first"
        conversations = await self._client.list_conversations(
            starting_after=params.get("starting_after"),
            per_page=params.get("per_page", 20),
        )
        return ConnectorResponse(success=True, data=conversations, status_code=200)

    async def _get_conversation(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "IntercomClient not initialized — call connect() first"
        conversation_id = params.get("conversation_id")
        if not conversation_id:
            return ConnectorResponse(success=False, error="Missing: conversation_id", status_code=400)
        conversation = await self._client.get_conversation(conversation_id)
        return ConnectorResponse(success=True, data=conversation, status_code=200)

    async def _reply_to_conversation(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "IntercomClient not initialized — call connect() first"
        conversation_id = params.get("conversation_id")
        body = params.get("body")
        if not conversation_id or not body:
            return ConnectorResponse(success=False, error="Missing: conversation_id and body", status_code=400)
        result = await self._client.reply_to_conversation(
            conversation_id=conversation_id,
            message_type=params.get("message_type", "comment"),
            body=body,
            admin_id=params.get("admin_id"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_contacts(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "IntercomClient not initialized — call connect() first"
        contacts = await self._client.list_contacts(
            starting_after=params.get("starting_after"),
            per_page=params.get("per_page", 20),
        )
        return ConnectorResponse(success=True, data=contacts, status_code=200)

    async def _get_contact(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "IntercomClient not initialized — call connect() first"
        contact_id = params.get("contact_id")
        if not contact_id:
            return ConnectorResponse(success=False, error="Missing: contact_id", status_code=400)
        contact = await self._client.get_contact(contact_id)
        return ConnectorResponse(success=True, data=contact, status_code=200)

    async def _list_companies(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "IntercomClient not initialized — call connect() first"
        companies = await self._client.list_companies(
            starting_after=params.get("starting_after"),
            per_page=params.get("per_page", 20),
        )
        return ConnectorResponse(success=True, data=companies, status_code=200)

    async def _list_teams(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "IntercomClient not initialized — call connect() first"
        teams = await self._client.list_teams()
        return ConnectorResponse(success=True, data=teams, status_code=200)

    async def _list_tags(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "IntercomClient not initialized — call connect() first"
        tags = await self._client.list_tags()
        return ConnectorResponse(success=True, data=tags, status_code=200)

    async def _search_contacts(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "IntercomClient not initialized — call connect() first"
        query = params.get("query") or params.get("q")
        if not query:
            return ConnectorResponse(success=False, error="Missing: query", status_code=400)
        results = await self._client.search_contacts(query)
        return ConnectorResponse(success=True, data=results, status_code=200)
