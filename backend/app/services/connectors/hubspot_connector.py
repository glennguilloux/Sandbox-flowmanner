"""
HubSpot Connector

Provides integration with HubSpot CRM API for:
- Owner info (get_owner)
- Contacts (list, get, create, update, search)
- Companies (list, get)
- Deals (list, get, create)
- Tickets (list)
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
    from app.services.hubspot.hubspot_client import HubSpotClient

logger = logging.getLogger(__name__)


class HubSpotConnector(BaseConnector):
    """HubSpot CRM platform connector."""

    CONNECTOR_TYPE = "hubspot"

    HUBSPOT_RATE_LIMIT = RateLimitConfig(
        requests_per_second=10.0,  # 100 per 10 seconds
        requests_per_minute=100,
        requests_per_hour=5000,
        burst_size=15,
    )

    ACTIONS = [
        "get_owner",
        "list_contacts",
        "get_contact",
        "create_contact",
        "update_contact",
        "list_companies",
        "get_company",
        "list_deals",
        "get_deal",
        "create_deal",
        "search_contacts",
        "list_tickets",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.hubapi.com"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.HUBSPOT_RATE_LIMIT
        super().__init__(config)
        self._client: HubSpotClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.hubspot.hubspot_client import HubSpotClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            if not token:
                logger.debug("No HubSpot token available — skipping credential validation")
                return True
            self._client = HubSpotClient(auth_token=token)
            result = await self._client.get_owner()
            return bool(result.get("results"))
        except Exception as e:
            logger.warning("HubSpot credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_owner": self._get_owner,
            "list_contacts": self._list_contacts,
            "get_contact": self._get_contact,
            "create_contact": self._create_contact,
            "update_contact": self._update_contact,
            "list_companies": self._list_companies,
            "get_company": self._get_company,
            "list_deals": self._list_deals,
            "get_deal": self._get_deal,
            "create_deal": self._create_deal,
            "search_contacts": self._search_contacts,
            "list_tickets": self._list_tickets,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("HubSpot action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_owner(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        result = await self._client.get_owner()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_contacts(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        result = await self._client.list_contacts(
            limit=params.get("limit", 100),
            after=params.get("after"),
            properties=params.get("properties"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_contact(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        contact_id = params.get("contact_id")
        if not contact_id:
            return ConnectorResponse(success=False, error="Missing: contact_id", status_code=400)
        result = await self._client.get_contact(contact_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _create_contact(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        properties = params.get("properties")
        if not properties:
            return ConnectorResponse(success=False, error="Missing: properties", status_code=400)
        result = await self._client.create_contact(properties)
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _update_contact(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        contact_id = params.get("contact_id")
        properties = params.get("properties")
        if not contact_id or not properties:
            return ConnectorResponse(success=False, error="Missing: contact_id and properties", status_code=400)
        result = await self._client.update_contact(contact_id, properties)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_companies(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        result = await self._client.list_companies(
            limit=params.get("limit", 100),
            after=params.get("after"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_company(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        company_id = params.get("company_id")
        if not company_id:
            return ConnectorResponse(success=False, error="Missing: company_id", status_code=400)
        result = await self._client.get_company(company_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_deals(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        result = await self._client.list_deals(
            limit=params.get("limit", 100),
            after=params.get("after"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_deal(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        deal_id = params.get("deal_id")
        if not deal_id:
            return ConnectorResponse(success=False, error="Missing: deal_id", status_code=400)
        result = await self._client.get_deal(deal_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _create_deal(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        properties = params.get("properties")
        if not properties:
            return ConnectorResponse(success=False, error="Missing: properties", status_code=400)
        result = await self._client.create_deal(properties)
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _search_contacts(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        query = params.get("query")
        if not query:
            return ConnectorResponse(success=False, error="Missing: query", status_code=400)
        result = await self._client.search_contacts(
            query,
            limit=params.get("limit", 100),
            properties=params.get("properties"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_tickets(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "HubSpotClient not initialized — call connect() first"
        result = await self._client.list_tickets(
            limit=params.get("limit", 100),
            after=params.get("after"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)
