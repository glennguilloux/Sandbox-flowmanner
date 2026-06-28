"""
Stripe Connector

Provides integration with Stripe for billing/payments via the BaseConnector framework.
Wraps the StripeClient REST client to expose standard connector actions.
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
    from app.services.stripe.stripe_client import StripeClient

logger = logging.getLogger(__name__)


class StripeConnector(BaseConnector):
    """Stripe billing/payments connector."""

    CONNECTOR_TYPE = "stripe"

    STRIPE_RATE_LIMIT = RateLimitConfig(
        requests_per_second=10.0,
        requests_per_minute=600,
        requests_per_hour=36000,
        burst_size=20,
    )

    ACTIONS = [
        "get_account",
        "list_charges",
        "get_charge",
        "list_customers",
        "get_customer",
        "list_invoices",
        "get_invoice",
        "list_subscriptions",
        "get_subscription",
        "list_products",
        "list_prices",
        "get_balance",
        "create_payment_link",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.stripe.com"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.STRIPE_RATE_LIMIT
        super().__init__(config)
        self._client: StripeClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.stripe.stripe_client import StripeClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            if not token:
                logger.debug("No Stripe token available — skipping credential validation")
                return True
            self._client = StripeClient(auth_token=token)
            account = await self._client.get_account()
            return bool(account.get("id"))
        except Exception as e:
            logger.warning("Stripe credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_account": self._get_account,
            "list_charges": self._list_charges,
            "get_charge": self._get_charge,
            "list_customers": self._list_customers,
            "get_customer": self._get_customer,
            "list_invoices": self._list_invoices,
            "get_invoice": self._get_invoice,
            "list_subscriptions": self._list_subscriptions,
            "get_subscription": self._get_subscription,
            "list_products": self._list_products,
            "list_prices": self._list_prices,
            "get_balance": self._get_balance,
            "create_payment_link": self._create_payment_link,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Stripe action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_account(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        account = await self._client.get_account()
        return ConnectorResponse(success=True, data=account, status_code=200)

    async def _list_charges(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        charges = await self._client.list_charges(
            limit=params.get("limit", 20),
            starting_after=params.get("starting_after"),
            created=params.get("created"),
        )
        return ConnectorResponse(success=True, data=charges, status_code=200)

    async def _get_charge(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        charge_id = params.get("charge_id")
        if not charge_id:
            return ConnectorResponse(success=False, error="Missing: charge_id", status_code=400)
        charge = await self._client.get_charge(charge_id)
        return ConnectorResponse(success=True, data=charge, status_code=200)

    async def _list_customers(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        customers = await self._client.list_customers(
            limit=params.get("limit", 20),
            starting_after=params.get("starting_after"),
        )
        return ConnectorResponse(success=True, data=customers, status_code=200)

    async def _get_customer(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        customer_id = params.get("customer_id")
        if not customer_id:
            return ConnectorResponse(success=False, error="Missing: customer_id", status_code=400)
        customer = await self._client.get_customer(customer_id)
        return ConnectorResponse(success=True, data=customer, status_code=200)

    async def _list_invoices(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        invoices = await self._client.list_invoices(
            limit=params.get("limit", 20),
            starting_after=params.get("starting_after"),
        )
        return ConnectorResponse(success=True, data=invoices, status_code=200)

    async def _get_invoice(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        invoice_id = params.get("invoice_id")
        if not invoice_id:
            return ConnectorResponse(success=False, error="Missing: invoice_id", status_code=400)
        invoice = await self._client.get_invoice(invoice_id)
        return ConnectorResponse(success=True, data=invoice, status_code=200)

    async def _list_subscriptions(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        subscriptions = await self._client.list_subscriptions(
            limit=params.get("limit", 20),
            starting_after=params.get("starting_after"),
            status=params.get("status"),
        )
        return ConnectorResponse(success=True, data=subscriptions, status_code=200)

    async def _get_subscription(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        subscription_id = params.get("subscription_id")
        if not subscription_id:
            return ConnectorResponse(success=False, error="Missing: subscription_id", status_code=400)
        subscription = await self._client.get_subscription(subscription_id)
        return ConnectorResponse(success=True, data=subscription, status_code=200)

    async def _list_products(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        products = await self._client.list_products(
            limit=params.get("limit", 20),
            starting_after=params.get("starting_after"),
        )
        return ConnectorResponse(success=True, data=products, status_code=200)

    async def _list_prices(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        prices = await self._client.list_prices(
            product=params.get("product"),
            limit=params.get("limit", 20),
            starting_after=params.get("starting_after"),
        )
        return ConnectorResponse(success=True, data=prices, status_code=200)

    async def _get_balance(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        balance = await self._client.get_balance()
        return ConnectorResponse(success=True, data=balance, status_code=200)

    async def _create_payment_link(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "StripeClient not initialized — call connect() first"
        line_items = params.get("line_items")
        if not line_items:
            return ConnectorResponse(success=False, error="Missing: line_items", status_code=400)
        link = await self._client.create_payment_link(line_items=line_items)
        return ConnectorResponse(success=True, data=link, status_code=201)
