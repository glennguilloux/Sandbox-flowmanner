"""
HubSpot CRM API v3 Client

Async client for HubSpot's CRM API.
Used by the user-facing HubSpot integration — agents interact with the USER's
HubSpot account for contacts, companies, deals, tickets, and search.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).

Token URL: https://api.hubapi.com/oauth/v1/token
API Base: https://api.hubapi.com
Quirk: Refresh tokens may rotate on each refresh. Tokens expire in 30 minutes.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubSpotAPIError(Exception):
    """HubSpot API error."""

    pass


class HubSpotClient:
    """Async REST client for HubSpot CRM API v3."""

    def __init__(self, auth_token: str, base_url: str = HUBSPOT_API_BASE):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make an API request."""
        url = f"{self.base_url}{path}"
        headers = dict(self._headers)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=headers, params=params, json=json_body)
            if resp.status_code == 429:
                retry_after = resp.headers.get("retry-after", "?")
                raise HubSpotAPIError(f"HubSpot rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise HubSpotAPIError(f"HubSpot API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── Owners (credential validation) ──────────────────────────

    async def get_owner(self) -> dict[str, Any]:
        """GET /crm/v3/owners — Get owners (first page, used for credential validation)."""
        return await self._request("GET", "/crm/v3/owners", params={"limit": 1})  # type: ignore[return-value]

    # ── Contacts ────────────────────────────────────────────────

    async def list_contacts(
        self,
        limit: int = 100,
        after: str | None = None,
        properties: str | None = None,
    ) -> dict[str, Any]:
        """GET /crm/v3/objects/contacts — List contacts with pagination."""
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        if properties:
            params["properties"] = properties
        return await self._request("GET", "/crm/v3/objects/contacts", params=params)  # type: ignore[return-value]

    async def get_contact(self, contact_id: str) -> dict[str, Any]:
        """GET /crm/v3/objects/contacts/{id} — Get contact details."""
        return await self._request("GET", f"/crm/v3/objects/contacts/{contact_id}")  # type: ignore[return-value]

    async def create_contact(self, properties: dict[str, Any]) -> dict[str, Any]:
        """POST /crm/v3/objects/contacts — Create a contact."""
        return await self._request(
            "POST",
            "/crm/v3/objects/contacts",
            json_body={"properties": properties},
        )  # type: ignore[return-value]

    async def update_contact(self, contact_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        """PATCH /crm/v3/objects/contacts/{id} — Update a contact."""
        return await self._request(
            "PATCH",
            f"/crm/v3/objects/contacts/{contact_id}",
            json_body={"properties": properties},
        )  # type: ignore[return-value]

    # ── Companies ───────────────────────────────────────────────

    async def list_companies(
        self,
        limit: int = 100,
        after: str | None = None,
    ) -> dict[str, Any]:
        """GET /crm/v3/objects/companies — List companies."""
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        return await self._request("GET", "/crm/v3/objects/companies", params=params)  # type: ignore[return-value]

    async def get_company(self, company_id: str) -> dict[str, Any]:
        """GET /crm/v3/objects/companies/{id} — Get company details."""
        return await self._request("GET", f"/crm/v3/objects/companies/{company_id}")  # type: ignore[return-value]

    # ── Deals ───────────────────────────────────────────────────

    async def list_deals(
        self,
        limit: int = 100,
        after: str | None = None,
    ) -> dict[str, Any]:
        """GET /crm/v3/objects/deals — List deals."""
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        return await self._request("GET", "/crm/v3/objects/deals", params=params)  # type: ignore[return-value]

    async def get_deal(self, deal_id: str) -> dict[str, Any]:
        """GET /crm/v3/objects/deals/{id} — Get deal details."""
        return await self._request("GET", f"/crm/v3/objects/deals/{deal_id}")  # type: ignore[return-value]

    async def create_deal(self, properties: dict[str, Any]) -> dict[str, Any]:
        """POST /crm/v3/objects/deals — Create a deal."""
        return await self._request(
            "POST",
            "/crm/v3/objects/deals",
            json_body={"properties": properties},
        )  # type: ignore[return-value]

    # ── Search ──────────────────────────────────────────────────

    async def search_contacts(
        self,
        query: str,
        limit: int = 100,
        properties: list[str] | None = None,
    ) -> dict[str, Any]:
        """POST /crm/v3/objects/contacts/search — Search contacts."""
        body: dict[str, Any] = {
            "query": query,
            "limit": limit,
        }
        if properties:
            body["properties"] = properties
        return await self._request(
            "POST",
            "/crm/v3/objects/contacts/search",
            json_body=body,
        )  # type: ignore[return-value]

    # ── Tickets ─────────────────────────────────────────────────

    async def list_tickets(
        self,
        limit: int = 100,
        after: str | None = None,
    ) -> dict[str, Any]:
        """GET /crm/v3/objects/tickets — List support tickets."""
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        return await self._request("GET", "/crm/v3/objects/tickets", params=params)  # type: ignore[return-value]
