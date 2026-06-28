"""
Shopify Admin API Client

Async client for Shopify's Admin REST API.
Auth: X-Shopify-Access-Token header (no OAuth refresh — tokens don't expire).

API Base: https://{shop}.myshopify.com/admin/api/2024-01
Quirk: Shop-specific URLs — the shop domain must be captured during OAuth.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SHOPIFY_API_VERSION = "2024-01"


class ShopifyAPIError(Exception):
    """Shopify API error."""

    pass


class ShopifyClient:
    """Async REST client for Shopify Admin API."""

    def __init__(
        self,
        shop_domain: str,
        access_token: str,
    ):
        self.shop_domain = shop_domain
        self.access_token = access_token
        self.base_url = f"https://{shop_domain}/admin/api/{SHOPIFY_API_VERSION}"
        self._headers = {
            "X-Shopify-Access-Token": access_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an API request."""
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=self._headers, params=params, json=json)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After", "?")
                raise ShopifyAPIError(f"Shopify rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise ShopifyAPIError(f"Shopify API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── Shop ─────────────────────────────────────────────────────

    async def get_shop(self) -> dict[str, Any]:
        """GET /shop.json — Get shop info (credential validation)."""
        result = await self._request("GET", "/shop.json")
        return result.get("shop", result)  # type: ignore[return-value]

    # ── Products ─────────────────────────────────────────────────

    async def list_products(self, limit: int = 50) -> dict[str, Any]:
        """GET /products.json — List products."""
        return await self._request("GET", "/products.json", params={"limit": limit})  # type: ignore[return-value]

    async def get_product(self, product_id: int) -> dict[str, Any]:
        """GET /products/{id}.json — Get product details."""
        result = await self._request("GET", f"/products/{product_id}.json")
        return result.get("product", result)  # type: ignore[return-value]

    async def create_product(self, product_data: dict[str, Any]) -> dict[str, Any]:
        """POST /products.json — Create a product."""
        result = await self._request("POST", "/products.json", json={"product": product_data})
        return result.get("product", result)  # type: ignore[return-value]

    # ── Orders ───────────────────────────────────────────────────

    async def list_orders(self, limit: int = 50, status: str = "any") -> dict[str, Any]:
        """GET /orders.json — List orders."""
        return await self._request("GET", "/orders.json", params={"limit": limit, "status": status})  # type: ignore[return-value]

    async def get_order(self, order_id: int) -> dict[str, Any]:
        """GET /orders/{id}.json — Get order details."""
        result = await self._request("GET", f"/orders/{order_id}.json")
        return result.get("order", result)  # type: ignore[return-value]

    async def update_order(self, order_id: int, order_data: dict[str, Any]) -> dict[str, Any]:
        """PUT /orders/{id}.json — Update an order."""
        result = await self._request("PUT", f"/orders/{order_id}.json", json={"order": order_data})
        return result.get("order", result)  # type: ignore[return-value]

    # ── Customers ────────────────────────────────────────────────

    async def list_customers(self, limit: int = 50) -> dict[str, Any]:
        """GET /customers.json — List customers."""
        return await self._request("GET", "/customers.json", params={"limit": limit})  # type: ignore[return-value]

    async def get_customer(self, customer_id: int) -> dict[str, Any]:
        """GET /customers/{id}.json — Get customer details."""
        result = await self._request("GET", f"/customers/{customer_id}.json")
        return result.get("customer", result)  # type: ignore[return-value]

    # ── Inventory ────────────────────────────────────────────────

    async def list_inventory_levels(self, inventory_item_ids: str) -> dict[str, Any]:
        """GET /inventory_levels.json — List inventory levels."""
        return await self._request("GET", "/inventory_levels.json", params={"inventory_item_ids": inventory_item_ids})  # type: ignore[return-value]

    # ── Webhooks ─────────────────────────────────────────────────

    async def create_webhook(self, topic: str, address: str, format_: str = "json") -> dict[str, Any]:
        """POST /webhooks.json — Create a webhook."""
        result = await self._request(
            "POST", "/webhooks.json", json={"webhook": {"topic": topic, "address": address, "format": format_}}
        )
        return result.get("webhook", result)  # type: ignore[return-value]

    # ── Transactions ─────────────────────────────────────────────

    async def list_transactions(self, order_id: int) -> dict[str, Any]:
        """GET /orders/{id}/transactions.json — List payment transactions."""
        return await self._request("GET", f"/orders/{order_id}/transactions.json")  # type: ignore[return-value]
