"""
E-commerce & Business Tools — HubSpot CRM Link.

hubspot_crm_link → Create, update, and track leads in HubSpot CRM
    via the HubSpot CRM API v3.
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

HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
HUBSPOT_TIMEOUT = int(os.getenv("HUBSPOT_TIMEOUT", "30"))


# ── Input ─────────────────────────────────────────────────────────────

HUBSPOT_ACTIONS = (
    "create_contact",
    "update_contact",
    "search_contacts",
    "get_contact",
    "list_contacts",
    "create_deal",
    "update_deal",
    "list_deals",
    "get_deal",
    "create_company",
    "search_companies",
)


class HubspotCrmLinkInput(ToolInput):
    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(HUBSPOT_ACTIONS)}",
    )
    object_id: str | None = Field(
        None,
        description="HubSpot record ID (for get_contact, update_contact, get_deal, update_deal)",
    )
    properties: dict[str, Any] | None = Field(
        None,
        description=(
            "Properties dict. For contacts: {'email': '...', 'firstname': '...', "
            "'lastname': '...', 'phone': '...', 'company': '...'}. "
            "For deals: {'dealname': '...', 'amount': '...', 'pipeline': '...', "
            "'dealstage': '...'}. For companies: {'name': '...', 'domain': '...'}."
        ),
    )
    search_query: str | None = Field(
        None,
        description="Search query string (for search_contacts, search_companies)",
    )
    search_property: str | None = Field(
        "email",
        description="Property to search by (for search_contacts, default: email)",
    )
    limit: int = Field(
        10,
        ge=1,
        le=100,
        description="Max records to return (for list_contacts, list_deals)",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class HubspotCrmLinkTool(BaseTool):
    """Create, update, and track leads in HubSpot CRM."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="hubspot_crm_link",
            name="HubSpot CRM Link",
            description=(
                "Create, update, and track leads in HubSpot CRM. Supports "
                "contacts, deals, and companies via the HubSpot CRM API v3."
            ),
            category="e-commerce-business",
            input_schema=HubspotCrmLinkInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["hubspot", "crm", "leads", "contacts", "deals", "sales"],
            requires_auth=True,
            timeout_seconds=HUBSPOT_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = HubspotCrmLinkInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if validated.action not in HUBSPOT_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(HUBSPOT_ACTIONS)}",
            )

        if not HUBSPOT_ACCESS_TOKEN:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="HubSpot not configured. Set HUBSPOT_ACCESS_TOKEN.",
            )

        if is_placeholder(HUBSPOT_ACCESS_TOKEN):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    "HUBSPOT_ACCESS_TOKEN is a placeholder. "
                    "Replace placeholder in .env with a real HubSpot access token "
                    "(private app token or OAuth token from https://app.hubspot.com)."
                ),
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("HubSpot API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"HubSpot API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.exception("hubspot_crm_link failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(self, validated: HubspotCrmLinkInput) -> dict[str, Any]:
        """Route to the appropriate HubSpot API handler."""
        headers = {
            "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            timeout=HUBSPOT_TIMEOUT,
            headers=headers,
            base_url="https://api.hubapi.com",
        ) as client:
            if validated.action.startswith("create_contact"):
                return await self._create_record(client, "contacts", validated.properties)
            elif validated.action == "update_contact":
                return await self._update_record(client, "contacts", validated.object_id, validated.properties)
            elif validated.action == "get_contact":
                return await self._get_record(client, "contacts", validated.object_id)
            elif validated.action == "list_contacts":
                return await self._list_records(client, "contacts", validated.limit)
            elif validated.action == "search_contacts":
                return await self._search_records(
                    client,
                    "contacts",
                    validated.search_query,
                    validated.search_property or "email",
                )
            elif validated.action == "create_deal":
                return await self._create_record(client, "deals", validated.properties)
            elif validated.action == "update_deal":
                return await self._update_record(client, "deals", validated.object_id, validated.properties)
            elif validated.action == "get_deal":
                return await self._get_record(client, "deals", validated.object_id)
            elif validated.action == "list_deals":
                return await self._list_records(client, "deals", validated.limit)
            elif validated.action == "create_company":
                return await self._create_record(client, "companies", validated.properties)
            elif validated.action == "search_companies":
                return await self._search_records(
                    client,
                    "companies",
                    validated.search_query,
                    "domain",
                )
            else:
                return {"error": f"Unhandled action: {validated.action}"}

    # ── CRUD helpers ─────────────────────────────────────────────

    async def _create_record(
        self,
        client: httpx.AsyncClient,
        object_type: str,
        properties: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not properties:
            return {"error": "properties are required for create"}
        resp = await client.post(
            f"/crm/v3/objects/{object_type}",
            json={"properties": properties},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "action": f"create_{object_type.rstrip('s')}",
            "id": data.get("id"),
            "properties": data.get("properties", {}),
            "created_at": data.get("createdAt"),
        }

    async def _update_record(
        self,
        client: httpx.AsyncClient,
        object_type: str,
        object_id: str | None,
        properties: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not object_id:
            return {"error": "object_id is required for update"}
        if not properties:
            return {"error": "properties are required for update"}
        resp = await client.patch(
            f"/crm/v3/objects/{object_type}/{object_id}",
            json={"properties": properties},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "action": f"update_{object_type.rstrip('s')}",
            "id": data.get("id"),
            "properties": data.get("properties", {}),
            "updated_at": data.get("updatedAt"),
        }

    async def _get_record(
        self,
        client: httpx.AsyncClient,
        object_type: str,
        object_id: str | None,
    ) -> dict[str, Any]:
        if not object_id:
            return {"error": "object_id is required for get"}
        resp = await client.get(
            f"/crm/v3/objects/{object_type}/{object_id}",
            params={"properties": "email,firstname,lastname,phone,company,dealname,amount,dealstage,hs_pipeline"},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "action": f"get_{object_type.rstrip('s')}",
            "id": data.get("id"),
            "properties": data.get("properties", {}),
        }

    async def _list_records(
        self,
        client: httpx.AsyncClient,
        object_type: str,
        limit: int,
    ) -> dict[str, Any]:
        resp = await client.get(
            f"/crm/v3/objects/{object_type}",
            params={"limit": limit, "archived": "false"},
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return {
            "action": f"list_{object_type}",
            "count": len(results),
            "records": [{"id": r["id"], "properties": r.get("properties", {})} for r in results],
        }

    async def _search_records(
        self,
        client: httpx.AsyncClient,
        object_type: str,
        query: str | None,
        property_name: str,
    ) -> dict[str, Any]:
        if not query:
            return {"error": "search_query is required for search"}
        resp = await client.post(
            f"/crm/v3/objects/{object_type}/search",
            json={
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": property_name,
                                "operator": "EQ",
                                "value": query,
                            }
                        ],
                    }
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return {
            "action": f"search_{object_type}",
            "property": property_name,
            "query": query,
            "count": len(results),
            "records": [{"id": r["id"], "properties": r.get("properties", {})} for r in results],
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(HubspotCrmLinkTool())
