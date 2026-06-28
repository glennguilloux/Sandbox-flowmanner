"""
Zendesk API v2 Client

Async client for Zendesk REST API v2.
Auth: Authorization: Bearer header.

API Base: https://{subdomain}.zendesk.com/api/v2
Quirk: Subdomain-specific URLs — the subdomain must be captured during OAuth.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ZendeskAPIError(Exception):
    """Zendesk API error."""

    pass


class ZendeskClient:
    """Async REST client for Zendesk API v2."""

    def __init__(
        self,
        subdomain: str,
        access_token: str,
    ):
        self.subdomain = subdomain
        self.access_token = access_token
        self.base_url = f"https://{subdomain}.zendesk.com/api/v2"
        self._headers = {
            "Authorization": f"Bearer {access_token}",
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
                raise ZendeskAPIError(f"Zendesk rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise ZendeskAPIError(f"Zendesk API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── Me ───────────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """GET /users/me.json — Get current user (credential validation)."""
        result = await self._request("GET", "/users/me.json")
        return result.get("user", result)  # type: ignore[return-value]

    # ── Tickets ──────────────────────────────────────────────────

    async def list_tickets(self, page: int = 1, per_page: int = 25) -> dict[str, Any]:
        """GET /tickets.json — List tickets."""
        return await self._request("GET", "/tickets.json", params={"page": page, "per_page": per_page})  # type: ignore[return-value]

    async def get_ticket(self, ticket_id: int) -> dict[str, Any]:
        """GET /tickets/{id}.json — Get ticket details."""
        result = await self._request("GET", f"/tickets/{ticket_id}.json")
        return result.get("ticket", result)  # type: ignore[return-value]

    async def create_ticket(self, ticket_data: dict[str, Any]) -> dict[str, Any]:
        """POST /tickets.json — Create a ticket."""
        result = await self._request("POST", "/tickets.json", json={"ticket": ticket_data})
        return result.get("ticket", result)  # type: ignore[return-value]

    async def update_ticket(self, ticket_id: int, ticket_data: dict[str, Any]) -> dict[str, Any]:
        """PUT /tickets/{id}.json — Update a ticket."""
        result = await self._request("PUT", f"/tickets/{ticket_id}.json", json={"ticket": ticket_data})
        return result.get("ticket", result)  # type: ignore[return-value]

    # ── Users ────────────────────────────────────────────────────

    async def list_users(self, page: int = 1, per_page: int = 25) -> dict[str, Any]:
        """GET /users.json — List users."""
        return await self._request("GET", "/users.json", params={"page": page, "per_page": per_page})  # type: ignore[return-value]

    async def get_user(self, user_id: int) -> dict[str, Any]:
        """GET /users/{id}.json — Get user details."""
        result = await self._request("GET", f"/users/{user_id}.json")
        return result.get("user", result)  # type: ignore[return-value]

    # ── Search ───────────────────────────────────────────────────

    async def search_tickets(self, query: str, per_page: int = 25) -> dict[str, Any]:
        """GET /search.json — Search tickets with Zendesk query syntax."""
        return await self._request("GET", "/search.json", params={"query": query, "per_page": per_page})  # type: ignore[return-value]

    # ── Organizations ────────────────────────────────────────────

    async def list_organizations(self, page: int = 1, per_page: int = 25) -> dict[str, Any]:
        """GET /organizations.json — List organizations."""
        return await self._request("GET", "/organizations.json", params={"page": page, "per_page": per_page})  # type: ignore[return-value]

    # ── Groups ───────────────────────────────────────────────────

    async def list_groups(self, page: int = 1, per_page: int = 25) -> dict[str, Any]:
        """GET /groups.json — List agent groups."""
        return await self._request("GET", "/groups.json", params={"page": page, "per_page": per_page})  # type: ignore[return-value]

    # ── Ticket Comments ──────────────────────────────────────────

    async def add_ticket_comment(self, ticket_id: int, comment_body: str, public: bool = True) -> dict[str, Any]:
        """PUT /tickets/{id}.json — Add a comment to a ticket via update."""
        result = await self._request(
            "PUT", f"/tickets/{ticket_id}.json", json={"ticket": {"comment": {"body": comment_body, "public": public}}}
        )
        return result.get("ticket", result)  # type: ignore[return-value]

    # ── Ticket Metrics ───────────────────────────────────────────

    async def list_ticket_metrics(self, page: int = 1, per_page: int = 25) -> dict[str, Any]:
        """GET /ticket_metrics.json — List ticket metrics."""
        return await self._request("GET", "/ticket_metrics.json", params={"page": page, "per_page": per_page})  # type: ignore[return-value]
