"""
E-commerce & Business Tools — Salesforce Lead Creator.

salesforce_lead_creator → Automatically ingest parsed emails into
    Salesforce leads via the Salesforce REST API.
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

SALESFORCE_INSTANCE_URL = os.getenv("SALESFORCE_INSTANCE_URL", "").rstrip("/")
SALESFORCE_ACCESS_TOKEN = os.getenv("SALESFORCE_ACCESS_TOKEN", "")
SALESFORCE_API_VERSION = os.getenv("SALESFORCE_API_VERSION", "58.0")
SALESFORCE_TIMEOUT = int(os.getenv("SALESFORCE_TIMEOUT", "30"))


# ── Input ─────────────────────────────────────────────────────────────

SALESFORCE_ACTIONS = (
    "create_lead",
    "update_lead",
    "get_lead",
    "search_leads",
    "convert_lead",
    "soql_query",
)


class SalesforceLeadCreatorInput(ToolInput):
    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(SALESFORCE_ACTIONS)}",
    )
    lead_id: str | None = Field(
        None,
        description="Salesforce Lead ID (18-char, for get_lead, update_lead, convert_lead)",
    )
    lead_data: dict[str, Any] | None = Field(
        None,
        description=(
            "Lead fields. For create_lead: {'FirstName': '...', 'LastName': '...', "
            "'Company': '...', 'Email': '...', 'Phone': '...', 'Title': '...', "
            "'Description': '...', 'LeadSource': '...', 'Status': '...'}. "
            "For update_lead: any subset of fields to patch."
        ),
    )
    search_term: str | None = Field(
        None,
        description="Search term for SOSL search (for search_leads)",
    )
    soql_query: str | None = Field(
        None,
        description="SOQL query string (for soql_query action, e.g. 'SELECT Id, Name, Email FROM Lead LIMIT 10')",
    )
    converted_status: str | None = Field(
        "Qualified",
        description="Lead status to set on conversion (for convert_lead)",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class SalesforceLeadCreatorTool(BaseTool):
    """Automatically ingest parsed emails into Salesforce leads."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="salesforce_lead_creator",
            name="Salesforce Lead Creator",
            description=(
                "Automatically ingest parsed emails into Salesforce leads. "
                "Create, update, search, and convert leads via the Salesforce "
                "REST API. Also supports raw SOQL queries."
            ),
            category="e-commerce-business",
            input_schema=SalesforceLeadCreatorInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["salesforce", "crm", "leads", "email", "sales"],
            requires_auth=True,
            timeout_seconds=SALESFORCE_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SalesforceLeadCreatorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.action not in SALESFORCE_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(SALESFORCE_ACTIONS)}",
            )

        if not SALESFORCE_INSTANCE_URL or not SALESFORCE_ACCESS_TOKEN:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    "Salesforce not configured. Set SALESFORCE_INSTANCE_URL and SALESFORCE_ACCESS_TOKEN."
                ),
            )

        if is_placeholder(SALESFORCE_INSTANCE_URL) or is_placeholder(
            SALESFORCE_ACCESS_TOKEN
        ):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    "Salesforce credentials contain a placeholder. "
                    "Replace placeholder in .env with real SALESFORCE_INSTANCE_URL "
                    "and SALESFORCE_ACCESS_TOKEN values."
                ),
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("Salesforce API error: %s", e)
            detail = self._extract_sf_error(e)
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Salesforce API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.exception("salesforce_lead_creator failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(
        self, validated: SalesforceLeadCreatorInput
    ) -> dict[str, Any]:
        """Route to the appropriate Salesforce API handler."""
        headers = {
            "Authorization": f"Bearer {SALESFORCE_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            timeout=SALESFORCE_TIMEOUT,
            headers=headers,
        ) as client:
            base = f"{SALESFORCE_INSTANCE_URL}/services/data/v{SALESFORCE_API_VERSION}"

            if validated.action == "create_lead":
                return await self._create_lead(client, base, validated.lead_data)
            elif validated.action == "update_lead":
                return await self._update_lead(
                    client, base, validated.lead_id, validated.lead_data
                )
            elif validated.action == "get_lead":
                return await self._get_lead(client, base, validated.lead_id)
            elif validated.action == "search_leads":
                return await self._search_leads(client, base, validated.search_term)
            elif validated.action == "convert_lead":
                return await self._convert_lead(
                    client, base, validated.lead_id, validated.converted_status
                )
            elif validated.action == "soql_query":
                return await self._soql_query(client, base, validated.soql_query)
            else:
                return {"error": f"Unhandled action: {validated.action}"}

    # ── Lead CRUD ────────────────────────────────────────────────

    async def _create_lead(
        self,
        client: httpx.AsyncClient,
        base: str,
        lead_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not lead_data:
            return {"error": "lead_data is required for create_lead"}
        resp = await client.post(f"{base}/sobjects/Lead", json=lead_data)
        if resp.status_code == 201:
            data = resp.json()
            return {
                "action": "create_lead",
                "success": True,
                "id": data.get("id"),
                "errors": data.get("errors", []),
            }
        resp.raise_for_status()

    async def _update_lead(
        self,
        client: httpx.AsyncClient,
        base: str,
        lead_id: str | None,
        lead_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not lead_id:
            return {"error": "lead_id is required for update_lead"}
        if not lead_data:
            return {"error": "lead_data is required for update_lead"}
        resp = await client.patch(f"{base}/sobjects/Lead/{lead_id}", json=lead_data)
        if resp.status_code == 204:
            return {
                "action": "update_lead",
                "success": True,
                "id": lead_id,
            }
        resp.raise_for_status()

    async def _get_lead(
        self,
        client: httpx.AsyncClient,
        base: str,
        lead_id: str | None,
    ) -> dict[str, Any]:
        if not lead_id:
            return {"error": "lead_id is required for get_lead"}
        resp = await client.get(
            f"{base}/sobjects/Lead/{lead_id}",
            params={
                "fields": "Id,FirstName,LastName,Company,Email,Phone,Title,LeadSource,Status,Description,CreatedDate"
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "action": "get_lead",
            "lead": {k: v for k, v in data.items() if k != "attributes"},
        }

    # ── Search ───────────────────────────────────────────────────

    async def _search_leads(
        self,
        client: httpx.AsyncClient,
        base: str,
        search_term: str | None,
    ) -> dict[str, Any]:
        if not search_term:
            return {"error": "search_term is required for search_leads"}
        # SOSL: Salesforce Object Search Language
        sosl = (
            f"FIND {{{self._escape_sosl(search_term)}}} "
            "IN ALL FIELDS RETURNING Lead("
            "Id, FirstName, LastName, Company, Email, Status LIMIT 25)"
        )
        resp = await client.get(f"{base}/search", params={"q": sosl})
        resp.raise_for_status()
        data = resp.json()
        records = data.get("searchRecords", [])
        return {
            "action": "search_leads",
            "query": search_term,
            "count": len(records),
            "leads": [
                {
                    "id": r.get("Id"),
                    "first_name": r.get("FirstName"),
                    "last_name": r.get("LastName"),
                    "company": r.get("Company"),
                    "email": r.get("Email"),
                    "status": r.get("Status"),
                }
                for r in records
            ],
        }

    # ── Convert ──────────────────────────────────────────────────

    async def _convert_lead(
        self,
        client: httpx.AsyncClient,
        base: str,
        lead_id: str | None,
        converted_status: str | None,
    ) -> dict[str, Any]:
        if not lead_id:
            return {"error": "lead_id is required for convert_lead"}
        payload: dict[str, Any] = {
            "leadId": lead_id,
            "convertedStatus": converted_status or "Qualified",
            "doNotCreateOpportunity": False,
        }
        resp = await client.post(f"{base}/sobjects/Lead", json=payload)
        # Convert returns 200 on success with the new IDs
        if resp.status_code == 200:
            data = resp.json()
            return {
                "action": "convert_lead",
                "success": True,
                "lead_id": data.get("leadId", lead_id),
                "account_id": data.get("accountId"),
                "contact_id": data.get("contactId"),
                "opportunity_id": data.get("opportunityId"),
            }
        resp.raise_for_status()

    # ── SOQL ─────────────────────────────────────────────────────

    async def _soql_query(
        self,
        client: httpx.AsyncClient,
        base: str,
        query: str | None,
    ) -> dict[str, Any]:
        if not query:
            return {"error": "soql_query is required for soql_query action"}
        resp = await client.get(f"{base}/query", params={"q": query})
        resp.raise_for_status()
        data = resp.json()
        records = data.get("records", [])
        return {
            "action": "soql_query",
            "query": query,
            "total_size": data.get("totalSize", 0),
            "done": data.get("done", True),
            "count": len(records),
            "records": [
                {k: v for k, v in r.items() if k != "attributes"} for r in records
            ],
        }

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _escape_sosl(term: str) -> str:
        """Escape special SOSL characters."""
        for ch in "\\{}[]()^~*?:\"'&|!+-<>@":
            term = term.replace(ch, f"\\{ch}")
        return term

    @staticmethod
    def _extract_sf_error(e: httpx.HTTPStatusError) -> str:
        """Extract a human-readable error from a Salesforce API response."""
        try:
            body = e.response.json()
            if isinstance(body, list) and body:
                return body[0].get("message", str(body))
            if isinstance(body, dict):
                return body.get("error_description") or str(list(body.values())[:2])
            return str(body)[:500]
        except Exception:
            return e.response.text[:500]


# ── Register ──────────────────────────────────────────────────────────

register_tool(SalesforceLeadCreatorTool())
