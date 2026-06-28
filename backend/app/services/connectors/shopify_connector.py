"""
Shopify Connector

Provides integration with Shopify Admin API for:
- Shop info (get_shop)
- Products (list, get, create)
- Orders (list, get, update)
- Customers (list, get)
- Inventory (list levels)
- Webhooks (create)
- Transactions (list)
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
    from app.services.shopify.shopify_client import ShopifyClient

logger = logging.getLogger(__name__)


class ShopifyConnector(BaseConnector):
    """Shopify e-commerce platform connector."""

    CONNECTOR_TYPE = "shopify"

    SHOPIFY_RATE_LIMIT = RateLimitConfig(
        requests_per_second=2.0,
        requests_per_minute=40,
        requests_per_hour=2400,
        burst_size=10,
    )

    ACTIONS = [
        "get_shop",
        "list_products",
        "get_product",
        "create_product",
        "list_orders",
        "get_order",
        "update_order",
        "list_customers",
        "get_customer",
        "list_inventory_levels",
        "create_webhook",
        "list_transactions",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://shopify.com"
        config.auth_type = config.auth_type or AuthType.API_KEY
        config.rate_limit = config.rate_limit or self.SHOPIFY_RATE_LIMIT
        super().__init__(config)
        self._client: ShopifyClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.config import settings
            from app.services.shopify.shopify_client import ShopifyClient

            shop_domain = self.config.auth_config.get("shop_domain", "")
            access_token = self.config.auth_config.get("access_token", "") or settings.SHOPIFY_OAUTH_CLIENT_SECRET
            if not shop_domain or not access_token:
                logger.debug("Shopify credentials not configured — skipping validation")
                return True
            self._client = ShopifyClient(shop_domain=shop_domain, access_token=access_token)
            shop = await self._client.get_shop()
            return bool(shop.get("id"))
        except Exception as e:
            logger.warning("Shopify credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_shop": self._get_shop,
            "list_products": self._list_products,
            "get_product": self._get_product,
            "create_product": self._create_product,
            "list_orders": self._list_orders,
            "get_order": self._get_order,
            "update_order": self._update_order,
            "list_customers": self._list_customers,
            "get_customer": self._get_customer,
            "list_inventory_levels": self._list_inventory_levels,
            "create_webhook": self._create_webhook,
            "list_transactions": self._list_transactions,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Shopify action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_shop(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        result = await self._client.get_shop()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_products(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        result = await self._client.list_products(limit=params.get("limit", 50))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_product(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        product_id = params.get("product_id")
        if not product_id:
            return ConnectorResponse(success=False, error="Missing: product_id", status_code=400)
        result = await self._client.get_product(product_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _create_product(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        title = params.get("title")
        if not title:
            return ConnectorResponse(success=False, error="Missing: title", status_code=400)
        result = await self._client.create_product(params)
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _list_orders(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        result = await self._client.list_orders(limit=params.get("limit", 50), status=params.get("status", "any"))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_order(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        order_id = params.get("order_id")
        if not order_id:
            return ConnectorResponse(success=False, error="Missing: order_id", status_code=400)
        result = await self._client.get_order(order_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _update_order(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        order_id = params.get("order_id")
        if not order_id:
            return ConnectorResponse(success=False, error="Missing: order_id", status_code=400)
        result = await self._client.update_order(order_id, {k: v for k, v in params.items() if k != "order_id"})
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_customers(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        result = await self._client.list_customers(limit=params.get("limit", 50))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_customer(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        customer_id = params.get("customer_id")
        if not customer_id:
            return ConnectorResponse(success=False, error="Missing: customer_id", status_code=400)
        result = await self._client.get_customer(customer_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_inventory_levels(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        inventory_item_ids = params.get("inventory_item_ids", "")
        result = await self._client.list_inventory_levels(inventory_item_ids)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _create_webhook(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        topic = params.get("topic")
        address = params.get("address")
        if not topic or not address:
            return ConnectorResponse(success=False, error="Missing: topic and address", status_code=400)
        result = await self._client.create_webhook(topic, address, format_=params.get("format", "json"))
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _list_transactions(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "ShopifyClient not initialized — call connect() first"
        order_id = params.get("order_id")
        if not order_id:
            return ConnectorResponse(success=False, error="Missing: order_id", status_code=400)
        result = await self._client.list_transactions(order_id)
        return ConnectorResponse(success=True, data=result, status_code=200)
