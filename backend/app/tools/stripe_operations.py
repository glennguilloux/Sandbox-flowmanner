"""
E-commerce & Business Tools — Stripe Operations.

stripe_operations → Check payment statuses, invoices, and customer
    subscriptions via the Stripe REST API.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import (
    BaseTool,
    ToolInput,
    ToolMetadata,
    ToolResult,
    is_placeholder,
    register_tool,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_API_VERSION = os.getenv("STRIPE_API_VERSION", "2023-10-16")
STRIPE_TIMEOUT = int(os.getenv("STRIPE_TIMEOUT", "30"))


# ── Input ─────────────────────────────────────────────────────────────

STRIPE_ACTIONS = (
    "get_payment",
    "list_payments",
    "get_invoice",
    "list_invoices",
    "get_subscription",
    "list_subscriptions",
    "get_customer",
    "list_customers",
    "create_refund",
)


class StripeOperationsInput(ToolInput):
    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(STRIPE_ACTIONS)}",
    )
    resource_id: str | None = Field(
        None,
        description=(
            "Stripe resource ID (e.g. 'pi_xxx' for payment, 'in_xxx' for "
            "invoice, 'sub_xxx' for subscription, 'cus_xxx' for customer)"
        ),
    )
    params: dict[str, Any] | None = Field(
        None,
        description=(
            "Optional query/body params. For list_payments: "
            "{'limit': 10, 'customer': 'cus_xxx'}. "
            "For create_refund: {'charge': 'ch_xxx', 'amount': 500}."
        ),
    )


# ── Tool ──────────────────────────────────────────────────────────────


class StripeOperationsTool(BaseTool):
    """Check payment statuses, invoices, and customer subscriptions."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="stripe_operations",
            name="Stripe Operations",
            description=(
                "Check payment statuses, invoices, and customer subscriptions "
                "via the Stripe API. Supports payments, invoices, subscriptions, "
                "customers, and refunds."
            ),
            category="e-commerce-business",
            input_schema=StripeOperationsInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["stripe", "payments", "invoices", "subscriptions", "billing"],
            requires_auth=True,
            timeout_seconds=STRIPE_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = StripeOperationsInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.action not in STRIPE_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. "
                f"Use: {', '.join(STRIPE_ACTIONS)}",
            )

        if not STRIPE_SECRET_KEY:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Stripe not configured. Set STRIPE_SECRET_KEY.",
            )

        if is_placeholder(STRIPE_SECRET_KEY):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    "STRIPE_SECRET_KEY is a placeholder. "
                    "Replace placeholder in .env with a real Stripe secret key "
                    "(sk_live_... or sk_test_... from https://dashboard.stripe.com/apikeys)."
                ),
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("Stripe API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json().get("error", {}).get("message", ""))
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Stripe API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.exception("stripe_operations failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(self, validated: StripeOperationsInput) -> dict[str, Any]:
        """Route to the appropriate Stripe API endpoint."""
        headers = {
            "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
            "Stripe-Version": STRIPE_API_VERSION,
        }

        async with httpx.AsyncClient(
            timeout=STRIPE_TIMEOUT,
            headers=headers,
            base_url="https://api.stripe.com",
        ) as client:
            action = validated.action
            params = validated.params or {}

            if action.startswith("get_") or action.startswith("create_"):
                if not validated.resource_id and action.startswith("get_"):
                    return {"error": f"resource_id is required for {action}"}
                return await self._single_resource(
                    client, action, validated.resource_id or "", params
                )
            elif action.startswith("list_"):
                return await self._list_resources(client, action, params)
            else:
                return {"error": f"Unhandled action: {action}"}

    # ── _single_resource ─────────────────────────────────────────

    async def _single_resource(
        self,
        client: httpx.AsyncClient,
        action: str,
        resource_id: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch or act on a single Stripe resource."""
        # Map action → (endpoint_name, method)
        resource_map: dict[str, tuple[str, str]] = {
            "get_payment": ("payment_intents", "GET"),
            "get_invoice": ("invoices", "GET"),
            "get_subscription": ("subscriptions", "GET"),
            "get_customer": ("customers", "GET"),
            "create_refund": ("refunds", "POST"),
        }

        endpoint_name, method = resource_map.get(action, ("", "GET"))
        if not endpoint_name:
            return {"error": f"Unknown single-resource action: {action}"}

        if method == "GET":
            resp = await client.get(
                f"/v1/{endpoint_name}/{resource_id}",
                params={k: v for k, v in params.items() if v is not None},
            )
        else:
            resp = await client.post(
                f"/v1/{endpoint_name}",
                data=params if params else {},
            )

        resp.raise_for_status()
        data = resp.json()
        return self._sanitize_response(action, data)

    # ── _list_resources ──────────────────────────────────────────

    async def _list_resources(
        self,
        client: httpx.AsyncClient,
        action: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """List Stripe resources."""
        list_map = {
            "list_payments": "payment_intents",
            "list_invoices": "invoices",
            "list_subscriptions": "subscriptions",
            "list_customers": "customers",
        }

        endpoint_name = list_map.get(action, "")
        if not endpoint_name:
            return {"error": f"Unknown list action: {action}"}

        resp = await client.get(
            f"/v1/{endpoint_name}",
            params={k: v for k, v in params.items() if v is not None},
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", [])
        return {
            "action": action,
            "count": len(items),
            "has_more": data.get("has_more", False),
            "records": [self._summarize_item(action, item) for item in items],
        }

    # ── Response formatting ──────────────────────────────────────

    def _sanitize_response(self, action: str, data: dict[str, Any]) -> dict[str, Any]:
        """Extract key fields from a single Stripe resource response."""
        result: dict[str, Any] = {
            "action": action,
            "id": data.get("id"),
            "object": data.get("object"),
            "created": data.get("created"),
            "livemode": data.get("livemode"),
        }

        if action == "get_payment":
            result.update(
                {
                    "amount": data.get("amount"),
                    "currency": data.get("currency"),
                    "status": data.get("status"),
                    "description": data.get("description"),
                    "customer": data.get("customer"),
                }
            )
        elif action == "get_invoice":
            result.update(
                {
                    "amount_due": data.get("amount_due"),
                    "amount_paid": data.get("amount_paid"),
                    "currency": data.get("currency"),
                    "status": data.get("status"),
                    "customer": data.get("customer"),
                    "hosted_invoice_url": data.get("hosted_invoice_url"),
                }
            )
        elif action == "get_subscription":
            plan = data.get("plan", {}) or data.get("items", {}).get("data", [{}])[0]
            result.update(
                {
                    "status": data.get("status"),
                    "customer": data.get("customer"),
                    "current_period_end": data.get("current_period_end"),
                    "plan_name": plan.get("nickname") or plan.get("id", ""),
                    "plan_amount": plan.get("amount"),
                    "plan_currency": plan.get("currency"),
                    "cancel_at_period_end": data.get("cancel_at_period_end"),
                }
            )
        elif action == "get_customer":
            result.update(
                {
                    "email": data.get("email"),
                    "name": data.get("name"),
                    "balance": data.get("balance"),
                    "delinquent": data.get("delinquent"),
                }
            )
        elif action == "create_refund":
            result.update(
                {
                    "amount": data.get("amount"),
                    "currency": data.get("currency"),
                    "status": data.get("status"),
                    "charge": data.get("charge"),
                    "reason": data.get("reason"),
                }
            )

        return result

    def _summarize_item(self, action: str, item: dict[str, Any]) -> dict[str, Any]:
        """Create a summary per list item."""
        summary: dict[str, Any] = {
            "id": item.get("id"),
            "object": item.get("object"),
        }

        if action in ("list_payments",):
            summary.update(
                {
                    "amount": item.get("amount"),
                    "currency": item.get("currency"),
                    "status": item.get("status"),
                    "customer": item.get("customer"),
                }
            )
        elif action in ("list_invoices",):
            summary.update(
                {
                    "amount_due": item.get("amount_due"),
                    "status": item.get("status"),
                    "customer": item.get("customer"),
                }
            )
        elif action in ("list_subscriptions",):
            summary.update(
                {
                    "status": item.get("status"),
                    "customer": item.get("customer"),
                }
            )
        elif action in ("list_customers",):
            summary.update(
                {
                    "email": item.get("email"),
                    "name": item.get("name"),
                }
            )

        return summary


# ── Register ──────────────────────────────────────────────────────────

register_tool(StripeOperationsTool())
