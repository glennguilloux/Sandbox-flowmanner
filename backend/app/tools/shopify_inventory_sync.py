"""
E-commerce & Business Tools — Shopify Inventory Sync.

shopify_inventory_sync → Check stock levels and update product descriptions
    in Shopify via the Admin REST API (2024-01).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, is_placeholder, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL", "").rstrip("/")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")
SHOPIFY_TIMEOUT = int(os.getenv("SHOPIFY_TIMEOUT", "30"))



# ── Input ─────────────────────────────────────────────────────────────

SHOPIFY_ACTIONS = (
    "list_products", "get_product", "update_product",
    "list_inventory_levels", "get_inventory_item", "update_inventory",
)


class ShopifyInventorySyncInput(ToolInput):
    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(SHOPIFY_ACTIONS)}",
    )
    product_id: int | None = Field(
        None,
        description="Shopify product ID (for get_product, update_product)",
    )
    inventory_item_id: int | None = Field(
        None,
        description="Shopify inventory item ID (for get_inventory_item, update_inventory)",
    )
    data: dict[str, Any] | None = Field(
        None,
        description="Update payload (e.g. {'product': {'title': 'New Title'}} for update_product)",
    )
    query_params: dict[str, str] | None = Field(
        None,
        description="Optional query params (e.g. {'limit': '50', 'status': 'active'})",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class ShopifyInventorySyncTool(BaseTool):
    """Check stock levels and update product descriptions in Shopify."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="shopify_inventory_sync",
            name="Shopify Inventory Sync",
            description=(
                "Check stock levels and update product descriptions in Shopify. "
                "Supports listing products, getting individual products, updating "
                "product details, and managing inventory levels."
            ),
            category="e-commerce-business",
            input_schema=ShopifyInventorySyncInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["shopify", "ecommerce", "inventory", "products", "store"],
            requires_auth=True,
            timeout_seconds=SHOPIFY_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ShopifyInventorySyncInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.action not in SHOPIFY_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. "
                f"Use: {', '.join(SHOPIFY_ACTIONS)}",
            )

        if not SHOPIFY_STORE_URL or not SHOPIFY_ACCESS_TOKEN:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    "Shopify not configured. Set SHOPIFY_STORE_URL and "
                    "SHOPIFY_ACCESS_TOKEN environment variables."
                ),
            )

        if is_placeholder(SHOPIFY_STORE_URL) or is_placeholder(SHOPIFY_ACCESS_TOKEN):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    "Shopify credentials contain a placeholder. "
                    "Replace placeholder in .env with real SHOPIFY_STORE_URL "
                    "and SHOPIFY_ACCESS_TOKEN values "
                    "(from https://admin.shopify.com → Settings → Apps)."
                ),
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("shopify_inventory_sync failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(
        self, validated: ShopifyInventorySyncInput
    ) -> dict[str, Any]:
        """Route to the appropriate API handler."""
        base = f"{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}"
        headers = {
            "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
            "Content-Type": "application/json",
        }
        params = validated.query_params or {}

        async with httpx.AsyncClient(
            timeout=SHOPIFY_TIMEOUT, headers=headers
        ) as client:
            if validated.action == "list_products":
                return await self._list_products(client, base, params)
            elif validated.action == "get_product":
                return await self._get_product(
                    client, base, validated.product_id
                )
            elif validated.action == "update_product":
                return await self._update_product(
                    client, base, validated.product_id, validated.data
                )
            elif validated.action == "list_inventory_levels":
                return await self._list_inventory_levels(client, base, params)
            elif validated.action == "get_inventory_item":
                return await self._get_inventory_item(
                    client, base, validated.inventory_item_id
                )
            elif validated.action == "update_inventory":
                return await self._update_inventory(
                    client, base, validated.inventory_item_id, validated.data
                )
            else:
                return {"error": f"Unhandled action: {validated.action}"}

    # ── Products ─────────────────────────────────────────────────

    async def _list_products(
        self, client: httpx.AsyncClient, base: str, params: dict
    ) -> dict[str, Any]:
        resp = await client.get(f"{base}/products.json", params=params)
        resp.raise_for_status()
        data = resp.json()
        products = data.get("products", [])
        return {
            "action": "list_products",
            "count": len(products),
            "products": [
                {
                    "id": p["id"],
                    "title": p.get("title"),
                    "vendor": p.get("vendor"),
                    "product_type": p.get("product_type"),
                    "status": p.get("status"),
                    "variants_count": len(p.get("variants", [])),
                }
                for p in products
            ],
        }

    async def _get_product(
        self, client: httpx.AsyncClient, base: str, product_id: int | None
    ) -> dict[str, Any]:
        if not product_id:
            return {"error": "product_id is required for get_product"}
        resp = await client.get(f"{base}/products/{product_id}.json")
        resp.raise_for_status()
        product = resp.json().get("product", {})
        return {
            "action": "get_product",
            "product": {
                "id": product["id"],
                "title": product.get("title"),
                "body_html": product.get("body_html", "")[:500],
                "vendor": product.get("vendor"),
                "product_type": product.get("product_type"),
                "status": product.get("status"),
                "tags": product.get("tags"),
                "variants": [
                    {
                        "id": v["id"],
                        "title": v.get("title"),
                        "sku": v.get("sku"),
                        "price": v.get("price"),
                        "inventory_quantity": v.get("inventory_quantity"),
                    }
                    for v in product.get("variants", [])
                ],
                "images_count": len(product.get("images", [])),
            },
        }

    async def _update_product(
        self,
        client: httpx.AsyncClient,
        base: str,
        product_id: int | None,
        data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not product_id:
            return {"error": "product_id is required for update_product"}
        if not data:
            return {"error": "data payload is required for update_product"}
        resp = await client.put(
            f"{base}/products/{product_id}.json", json=data
        )
        resp.raise_for_status()
        product = resp.json().get("product", {})
        return {
            "action": "update_product",
            "success": True,
            "product_id": product.get("id"),
            "title": product.get("title"),
        }

    # ── Inventory ────────────────────────────────────────────────

    async def _list_inventory_levels(
        self, client: httpx.AsyncClient, base: str, params: dict
    ) -> dict[str, Any]:
        resp = await client.get(
            f"{base}/inventory_levels.json", params=params
        )
        resp.raise_for_status()
        levels = resp.json().get("inventory_levels", [])
        return {
            "action": "list_inventory_levels",
            "count": len(levels),
            "inventory_levels": [
                {
                    "inventory_item_id": l["inventory_item_id"],
                    "location_id": l.get("location_id"),
                    "available": l.get("available"),
                }
                for l in levels
            ],
        }

    async def _get_inventory_item(
        self, client: httpx.AsyncClient, base: str, item_id: int | None
    ) -> dict[str, Any]:
        if not item_id:
            return {"error": "inventory_item_id is required"}
        resp = await client.get(f"{base}/inventory_items/{item_id}.json")
        resp.raise_for_status()
        item = resp.json().get("inventory_item", {})
        return {
            "action": "get_inventory_item",
            "inventory_item": {
                "id": item["id"],
                "sku": item.get("sku"),
                "tracked": item.get("tracked"),
                "cost": item.get("cost"),
                "country_code_of_origin": item.get("country_code_of_origin"),
            },
        }

    async def _update_inventory(
        self,
        client: httpx.AsyncClient,
        base: str,
        item_id: int | None,
        data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not item_id:
            return {"error": "inventory_item_id is required"}
        if not data:
            return {"error": "data payload is required for update_inventory"}
        resp = await client.put(
            f"{base}/inventory_items/{item_id}.json", json=data
        )
        resp.raise_for_status()
        return {
            "action": "update_inventory",
            "success": True,
            "inventory_item_id": item_id,
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(ShopifyInventorySyncTool())
