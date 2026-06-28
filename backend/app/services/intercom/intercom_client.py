"""
Intercom REST API Client

Async client for Intercom's REST API.
Used by the user-facing Intercom integration — agents interact with the USER's
Intercom workspace for conversations, contacts, and companies.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).

Token URL: https://api.intercom.io/auth/eagle/token
API Base: https://api.intercom.io
Quirk: All requests require `Intercom-Version` header (e.g., 2.8).
Note: Intercom tokens do NOT expire (no refresh_token).
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

INTERCOM_API_BASE = "https://api.intercom.io"
INTERCOM_API_VERSION = "2.8"


class IntercomAPIError(Exception):
    """Intercom API error."""

    pass


class IntercomClient:
    """Async REST client for Intercom API."""

    def __init__(self, auth_token: str, base_url: str = INTERCOM_API_BASE):
        """
        Args:
            auth_token: Intercom OAuth access token
            base_url: Intercom API base URL (default: https://api.intercom.io)
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Intercom-Version": INTERCOM_API_VERSION,
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
                raise IntercomAPIError(f"Intercom rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise IntercomAPIError(f"Intercom API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── Admin ───────────────────────────────────────────────────

    async def get_admin(self) -> dict[str, Any]:
        """GET /admins/me — Get authenticated admin info (credential validation)."""
        return await self._request("GET", "/admins/me")  # type: ignore[return-value]

    # ── Conversations ───────────────────────────────────────────

    async def list_conversations(
        self,
        starting_after: str | None = None,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """GET /conversations — List conversations (paginated with starting_after cursor)."""
        params: dict[str, Any] = {"per_page": per_page}
        if starting_after:
            params["starting_after"] = starting_after
        return await self._request("GET", "/conversations", params=params)  # type: ignore[return-value]

    async def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        """GET /conversations/{id} — Get conversation details."""
        return await self._request("GET", f"/conversations/{conversation_id}")  # type: ignore[return-value]

    async def reply_to_conversation(
        self,
        conversation_id: str,
        message_type: str = "comment",
        body: str = "",
        admin_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /conversations/{id}/reply — Reply to a conversation."""
        payload: dict[str, Any] = {
            "message_type": message_type,
            "body": body,
        }
        if admin_id:
            payload["admin_id"] = admin_id
        return await self._request("POST", f"/conversations/{conversation_id}/reply", json_body=payload)  # type: ignore[return-value]

    # ── Contacts ────────────────────────────────────────────────

    async def list_contacts(
        self,
        starting_after: str | None = None,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """GET /contacts — List contacts (paginated)."""
        params: dict[str, Any] = {"per_page": per_page}
        if starting_after:
            params["starting_after"] = starting_after
        return await self._request("GET", "/contacts", params=params)  # type: ignore[return-value]

    async def get_contact(self, contact_id: str) -> dict[str, Any]:
        """GET /contacts/{id} — Get contact details."""
        return await self._request("GET", f"/contacts/{contact_id}")  # type: ignore[return-value]

    async def search_contacts(self, query: str) -> dict[str, Any]:
        """POST /contacts/search — Search contacts by query."""
        return await self._request(
            "POST", "/contacts/search", json_body={"query": {"field": "name", "operator": "~", "value": query}}
        )  # type: ignore[return-value]

    # ── Companies ───────────────────────────────────────────────

    async def list_companies(
        self,
        starting_after: str | None = None,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """GET /companies — List companies (paginated)."""
        params: dict[str, Any] = {"per_page": per_page}
        if starting_after:
            params["starting_after"] = starting_after
        return await self._request("GET", "/companies", params=params)  # type: ignore[return-value]

    # ── Teams ───────────────────────────────────────────────────

    async def list_teams(self) -> dict[str, Any]:
        """GET /teams — List teams."""
        return await self._request("GET", "/teams")  # type: ignore[return-value]

    # ── Tags ────────────────────────────────────────────────────

    async def list_tags(self) -> dict[str, Any]:
        """GET /tags — List tags."""
        return await self._request("GET", "/tags")  # type: ignore[return-value]
