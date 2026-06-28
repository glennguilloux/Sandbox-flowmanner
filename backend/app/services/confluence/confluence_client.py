"""
Confluence Cloud REST API Client

Async client for Confluence Cloud API v2 via the Atlassian REST API gateway.
Used by the user-facing Confluence integration — agents manage the USER's
Confluence spaces and pages.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).
All requests go through: https://api.atlassian.com/ex/confluence/{cloudId}/wiki/api/v2/...

The cloudId is obtained during the OAuth callback site discovery step and
stored in IntegrationConnection.account_id (same as Jira).
"""

import logging
from typing import Any

import httpx

from app.services.jira.jira_client import text_to_adf

logger = logging.getLogger(__name__)

ATLASSIAN_API_BASE = "https://api.atlassian.com"


class ConfluenceAPIError(Exception):
    """Confluence API error."""

    pass


class ConfluenceClient:
    """Async REST client for Confluence Cloud API v2."""

    def __init__(self, cloud_id: str, auth_token: str):
        """
        Args:
            cloud_id: Atlassian cloud ID (from site discovery during OAuth callback)
            auth_token: Atlassian OAuth access token
        """
        self.cloud_id = cloud_id
        self.auth_token = auth_token
        self._base_url = f"{ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2"
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=self._headers, **kwargs)
            if resp.status_code == 429:
                raise ConfluenceAPIError(
                    f"Confluence rate limited: {method} {path} — retry after {resp.headers.get('retry-after', '?')}s"
                )
            if resp.status_code >= 400:
                raise ConfluenceAPIError(f"Confluence API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            if resp.status_code == 204:
                return {}
            return resp.json()

    # ── User ───────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """GET /wiki/api/v2/users/current — Get authenticated user info."""
        return await self._request("GET", "/users/current")  # type: ignore[return-value]

    # ── Spaces ─────────────────────────────────────────────────

    async def list_spaces(self, limit: int = 25) -> list[dict[str, Any]]:
        """GET /wiki/api/v2/spaces — List Confluence spaces."""
        data = await self._request("GET", "/spaces", params={"limit": limit})
        if isinstance(data, dict):
            return data.get("results", [])
        return []  # type: ignore[return-value]

    async def get_space(self, space_id: str) -> dict[str, Any]:
        """GET /wiki/api/v2/spaces/{id} — Get space details."""
        return await self._request("GET", f"/spaces/{space_id}")  # type: ignore[return-value]

    # ── Pages ──────────────────────────────────────────────────

    async def get_page(self, page_id: str) -> dict[str, Any]:
        """GET /wiki/api/v2/pages/{id} — Get page details (with body)."""
        return await self._request("GET", f"/pages/{page_id}", params={"body-format": "atlas_doc_format"})  # type: ignore[return-value]

    async def create_page(
        self,
        space_id: str,
        title: str,
        body: str,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /wiki/api/v2/pages — Create a new page.

        Body is automatically converted to ADF format.
        """
        payload: dict[str, Any] = {
            "spaceId": space_id,
            "title": title,
            "body": {
                "representation": "atlas_doc_format",
                "value": text_to_adf(body) if isinstance(body, str) else body,
            },
            "status": "current",
        }
        if parent_id:
            payload["parentId"] = parent_id
        return await self._request("POST", "/pages", json=payload)  # type: ignore[return-value]

    async def update_page(
        self,
        page_id: str,
        title: str,
        body: str,
        version_number: int,
    ) -> dict[str, Any]:
        """PUT /wiki/api/v2/pages/{id} — Update page content.

        Requires the current version.number (fetched via get_page first).
        """
        payload: dict[str, Any] = {
            "id": page_id,
            "title": title,
            "body": {
                "representation": "atlas_doc_format",
                "value": text_to_adf(body) if isinstance(body, str) else body,
            },
            "version": {
                "number": version_number,
            },
            "status": "current",
        }
        return await self._request("PUT", f"/pages/{page_id}", json=payload)  # type: ignore[return-value]

    # ── Search ─────────────────────────────────────────────────

    async def search_content(self, cql: str, limit: int = 25) -> dict[str, Any]:
        """GET /wiki/api/v2/search — Search content with CQL."""
        return await self._request("GET", "/search", params={"cql": cql, "limit": limit})  # type: ignore[return-value]

    # ── Page Children ──────────────────────────────────────────

    async def list_page_children(self, page_id: str, limit: int = 25) -> list[dict[str, Any]]:
        """GET /wiki/api/v2/pages/{id}/children — List sub-pages."""
        data = await self._request("GET", f"/pages/{page_id}/children", params={"limit": limit})
        if isinstance(data, dict):
            return data.get("results", [])
        return []  # type: ignore[return-value]

    # ── Comments ───────────────────────────────────────────────

    async def add_comment(self, page_id: str, body: str) -> dict[str, Any]:
        """POST /wiki/api/v2/pages/{id}/footer-comments — Add a comment.

        Body is automatically converted to ADF format.
        """
        payload: dict[str, Any] = {
            "body": {
                "representation": "atlas_doc_format",
                "value": text_to_adf(body) if isinstance(body, str) else body,
            },
        }
        return await self._request("POST", f"/pages/{page_id}/footer-comments", json=payload)  # type: ignore[return-value]

    # ── Attachments ────────────────────────────────────────────

    async def list_attachments(self, page_id: str, limit: int = 25) -> list[dict[str, Any]]:
        """GET /wiki/api/v2/pages/{id}/attachments — List page attachments."""
        data = await self._request("GET", f"/pages/{page_id}/attachments", params={"limit": limit})
        if isinstance(data, dict):
            return data.get("results", [])
        return []  # type: ignore[return-value]

    # ── Labels ─────────────────────────────────────────────────

    async def list_labels(self, page_id: str) -> list[dict[str, Any]]:
        """GET /wiki/api/v2/pages/{id}/labels — List labels on a page."""
        data = await self._request("GET", f"/pages/{page_id}/labels")
        if isinstance(data, dict):
            return data.get("results", [])
        return []  # type: ignore[return-value]

    async def add_labels(self, page_id: str, labels: list[str]) -> dict[str, Any]:
        """POST /wiki/api/v2/pages/{id}/labels — Add labels to a page."""
        payload = [{"name": label} for label in labels]
        return await self._request("POST", f"/pages/{page_id}/labels", json=payload)  # type: ignore[return-value]
