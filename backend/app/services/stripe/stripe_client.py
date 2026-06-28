"""
Stripe REST API Client

Async client for Stripe's REST API (v1).
Used by the user-facing Stripe integration — agents interact with the USER's
Stripe connected account for billing, payments, and revenue data.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).
Works with Stripe Connect OAuth2 flow.

Token URL: https://connect.stripe.com/oauth/token (verified against Stripe docs 2026-06-28).
API Base: https://api.stripe.com/v1
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

STRIPE_API_BASE = "https://api.stripe.com"


class StripeAPIError(Exception):
    """Stripe API error."""

    pass


class StripeClient:
    """Async REST client for Stripe API v1."""

    def __init__(self, auth_token: str, base_url: str = STRIPE_API_BASE):
        """
        Args:
            auth_token: Stripe OAuth access token (connected account)
            base_url: Stripe API base URL (default: https://api.stripe.com)
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make an API request. Uses form-encoded for POST/PUT, query params for GET."""
        url = f"{self.base_url}{path}"
        headers = dict(self._headers)

        # Stripe uses form-encoded bodies for POST/PUT, not JSON
        data = None
        if json_body and method in ("POST", "PUT", "PATCH"):
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = _flatten_params(json_body)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=headers, params=params, data=data)
            if resp.status_code == 429:
                retry_after = resp.headers.get("retry-after", "?")
                raise StripeAPIError(f"Stripe rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise StripeAPIError(f"Stripe API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── Account ─────────────────────────────────────────────────

    async def get_account(self) -> dict[str, Any]:
        """GET /v1/account — Get connected account info (credential validation)."""
        return await self._request("GET", "/v1/account")  # type: ignore[return-value]

    # ── Charges ─────────────────────────────────────────────────

    async def list_charges(
        self,
        limit: int = 20,
        starting_after: str | None = None,
        created: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET /v1/charges — List charges (paginated with starting_after cursor)."""
        params: dict[str, Any] = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        if created:
            for k, v in created.items():
                params[f"created[{k}]"] = v
        return await self._request("GET", "/v1/charges", params=params)  # type: ignore[return-value]

    async def get_charge(self, charge_id: str) -> dict[str, Any]:
        """GET /v1/charges/{id} — Get charge details."""
        return await self._request("GET", f"/v1/charges/{charge_id}")  # type: ignore[return-value]

    # ── Customers ───────────────────────────────────────────────

    async def list_customers(
        self,
        limit: int = 20,
        starting_after: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/customers — List customers (paginated)."""
        params: dict[str, Any] = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        return await self._request("GET", "/v1/customers", params=params)  # type: ignore[return-value]

    async def get_customer(self, customer_id: str) -> dict[str, Any]:
        """GET /v1/customers/{id} — Get customer details."""
        return await self._request("GET", f"/v1/customers/{customer_id}")  # type: ignore[return-value]

    # ── Invoices ────────────────────────────────────────────────

    async def list_invoices(
        self,
        limit: int = 20,
        starting_after: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/invoices — List invoices (paginated)."""
        params: dict[str, Any] = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        return await self._request("GET", "/v1/invoices", params=params)  # type: ignore[return-value]

    async def get_invoice(self, invoice_id: str) -> dict[str, Any]:
        """GET /v1/invoices/{id} — Get invoice details."""
        return await self._request("GET", f"/v1/invoices/{invoice_id}")  # type: ignore[return-value]

    # ── Subscriptions ───────────────────────────────────────────

    async def list_subscriptions(
        self,
        limit: int = 20,
        starting_after: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/subscriptions — List subscriptions (paginated)."""
        params: dict[str, Any] = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        if status:
            params["status"] = status
        return await self._request("GET", "/v1/subscriptions", params=params)  # type: ignore[return-value]

    async def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        """GET /v1/subscriptions/{id} — Get subscription details."""
        return await self._request("GET", f"/v1/subscriptions/{subscription_id}")  # type: ignore[return-value]

    # ── Products ────────────────────────────────────────────────

    async def list_products(
        self,
        limit: int = 20,
        starting_after: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/products — List products (paginated)."""
        params: dict[str, Any] = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        return await self._request("GET", "/v1/products", params=params)  # type: ignore[return-value]

    # ── Prices ──────────────────────────────────────────────────

    async def list_prices(
        self,
        product: str | None = None,
        limit: int = 20,
        starting_after: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/prices — List prices, optionally filtered by product."""
        params: dict[str, Any] = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        if product:
            params["product"] = product
        return await self._request("GET", "/v1/prices", params=params)  # type: ignore[return-value]

    # ── Balance ─────────────────────────────────────────────────

    async def get_balance(self) -> dict[str, Any]:
        """GET /v1/balance — Get current balance."""
        return await self._request("GET", "/v1/balance")  # type: ignore[return-value]

    # ── Payment Links ───────────────────────────────────────────

    async def create_payment_link(
        self,
        line_items: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """POST /v1/payment_links — Create a checkout payment link."""
        body: dict[str, Any] = {}
        for i, item in enumerate(line_items):
            body[f"line_items[{i}][price]"] = item["price"]
            body[f"line_items[{i}][quantity]"] = item.get("quantity", 1)
        body.update(kwargs)
        return await self._request("POST", "/v1/payment_links", json_body=body)  # type: ignore[return-value]

    async def list_payment_links(
        self,
        limit: int = 20,
        starting_after: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/payment_links — List payment links."""
        params: dict[str, Any] = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        return await self._request("GET", "/v1/payment_links", params=params)  # type: ignore[return-value]


def _flatten_params(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested dict into Stripe's form-encoded parameter format.

    Stripe uses bracket notation: {'metadata': {'key': 'val'}} → metadata[key]=val
    """
    result: dict[str, Any] = {}
    for k, v in obj.items():
        key = f"{prefix}[{k}]" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten_params(v, key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    result.update(_flatten_params(item, f"{key}[{i}]"))
                else:
                    result[f"{key}[{i}]"] = item
        elif isinstance(v, bool):
            result[key] = "true" if v else "false"
        else:
            result[key] = v
    return result
