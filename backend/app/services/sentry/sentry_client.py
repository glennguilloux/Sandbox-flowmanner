"""
Sentry REST API Client

Async client for Sentry's REST API (v0).
Used by the user-facing Sentry integration — agents triage the USER's Sentry errors.

Auth: per-user API token (stored in IntegrationConnection, decrypted at call time).
Works with both sentry.io and self-hosted Sentry instances.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SentryAPIError(Exception):
    """Sentry API error."""

    pass


class SentryClient:
    """Async REST client for Sentry API."""

    def __init__(self, base_url: str = "https://sentry.io", auth_token: str = ""):
        """
        Args:
            base_url: Sentry instance URL (https://sentry.io or self-hosted URL)
            auth_token: Sentry auth token (user provides this)
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        url = f"{self.base_url}/api/0{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=self._headers, **kwargs)
            if resp.status_code >= 400:
                raise SentryAPIError(f"Sentry API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── Organizations ──────────────────────────────────────────

    async def list_organizations(self) -> list[dict[str, Any]]:
        """GET /api/0/organizations/"""
        return await self._request("GET", "/organizations/")  # type: ignore[return-value]

    # ── Projects ───────────────────────────────────────────────

    async def list_projects(self, org_slug: str) -> list[dict[str, Any]]:
        """GET /api/0/organizations/{org}/projects/"""
        return await self._request("GET", f"/organizations/{org_slug}/projects/")  # type: ignore[return-value]

    # ── Issues ─────────────────────────────────────────────────

    async def list_issues(
        self,
        org_slug: str,
        project_slug: str | None = None,
        query: str = "",
        sort: str = "date",
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """GET /api/0/organizations/{org}/issues/"""
        params: dict[str, Any] = {"sort": sort, "per_page": limit}
        if project_slug:
            params["project"] = project_slug
        if query:
            params["query"] = query
        data = await self._request("GET", f"/organizations/{org_slug}/issues/", params=params)
        return data if isinstance(data, list) else []

    async def get_issue(self, issue_id: str) -> dict[str, Any]:
        """GET /api/0/issues/{issue_id}/"""
        return await self._request("GET", f"/issues/{issue_id}/")  # type: ignore[return-value]

    async def get_latest_event(self, issue_id: str) -> dict[str, Any]:
        """GET /api/0/issues/{issue_id}/events/latest/"""
        return await self._request("GET", f"/issues/{issue_id}/events/latest/")  # type: ignore[return-value]

    async def get_event(self, issue_id: str, event_id: str) -> dict[str, Any]:
        """GET /api/0/issues/{issue_id}/events/{event_id}/"""
        return await self._request("GET", f"/issues/{issue_id}/events/{event_id}/")  # type: ignore[return-value]

    async def resolve_issue(self, issue_id: str) -> dict[str, Any]:
        """PUT /api/0/issues/{issue_id}/ with status 'resolved'."""
        return await self._request(
            "PUT",
            f"/issues/{issue_id}/",
            json={"status": "resolved"},
        )  # type: ignore[return-value]

    async def ignore_issue(self, issue_id: str) -> dict[str, Any]:
        """PUT /api/0/issues/{issue_id}/ with status 'ignored'."""
        return await self._request(
            "PUT",
            f"/issues/{issue_id}/",
            json={"status": "ignored"},
        )  # type: ignore[return-value]

    # ── Releases ───────────────────────────────────────────────

    async def list_releases(
        self,
        org_slug: str,
        project_slug: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /api/0/organizations/{org}/releases/"""
        params: dict[str, Any] = {}
        if project_slug:
            params["project"] = project_slug
        data = await self._request("GET", f"/organizations/{org_slug}/releases/", params=params)
        return data if isinstance(data, list) else []

    async def get_release(self, org_slug: str, version: str) -> dict[str, Any]:
        """GET /api/0/organizations/{org}/releases/{version}/"""
        return await self._request("GET", f"/organizations/{org_slug}/releases/{version}/")  # type: ignore[return-value]
