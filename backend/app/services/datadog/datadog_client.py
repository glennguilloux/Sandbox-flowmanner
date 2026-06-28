"""
Datadog REST API Client

Async client for Datadog's API (v1/v2).
Used by the user-facing Datadog integration — agents monitor dashboards,
incidents, metrics, and events on behalf of the USER.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).
Works with Datadog's standard OAuth2 flow (no quirks).

Token URL: https://app.datadoghq.com/oauth2/v1/token
API Base: https://api.datadoghq.com
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DATADOG_API_BASE = "https://api.datadoghq.com"


class DatadogAPIError(Exception):
    """Datadog API error."""

    pass


class DatadogClient:
    """Async REST client for Datadog API."""

    def __init__(self, auth_token: str, base_url: str = DATADOG_API_BASE):
        """
        Args:
            auth_token: Datadog OAuth access token
            base_url: Datadog API base URL (default: https://api.datadoghq.com)
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
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
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=self._headers, **kwargs)
            if resp.status_code == 429:
                retry_after = resp.headers.get("x-ratelimit-reset", "?")
                raise DatadogAPIError(f"Datadog rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise DatadogAPIError(f"Datadog API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            if resp.status_code == 204:
                return {}
            return resp.json()

    # ── User / Validate ─────────────────────────────────────────

    async def get_current_user(self) -> dict[str, Any]:
        """GET /api/v2/current_user — Get authenticated user (credential validation)."""
        return await self._request("GET", "/api/v2/current_user")  # type: ignore[return-value]

    # ── Monitors ────────────────────────────────────────────────

    async def list_monitors(
        self,
        monitor_tags: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[dict[str, Any]]:
        """GET /api/v1/monitor — List all monitors."""
        params: dict[str, Any] = {}
        if monitor_tags:
            params["monitor_tags"] = monitor_tags
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        data = await self._request("GET", "/api/v1/monitor", params=params)
        return data if isinstance(data, list) else []  # type: ignore[return-value]

    async def get_monitor(self, monitor_id: int) -> dict[str, Any]:
        """GET /api/v1/monitor/{id} — Get monitor details."""
        return await self._request("GET", f"/api/v1/monitor/{monitor_id}")  # type: ignore[return-value]

    # ── Incidents ───────────────────────────────────────────────

    async def list_incidents(
        self,
        page_size: int | None = None,
        page_offset: int | None = None,
    ) -> dict[str, Any]:
        """GET /api/v2/incidents — List incidents."""
        params: dict[str, Any] = {}
        if page_size is not None:
            params["page[size]"] = page_size
        if page_offset is not None:
            params["page[offset]"] = page_offset
        return await self._request("GET", "/api/v2/incidents", params=params)  # type: ignore[return-value]

    async def get_incident(self, incident_id: str) -> dict[str, Any]:
        """GET /api/v2/incidents/{id} — Get incident details."""
        return await self._request("GET", f"/api/v2/incidents/{incident_id}")  # type: ignore[return-value]

    async def create_incident(
        self,
        title: str,
        severity: str = "unknown",
        customer_impacted: bool = False,
    ) -> dict[str, Any]:
        """POST /api/v2/incidents — Create a new incident."""
        payload = {
            "data": {
                "type": "incidents",
                "attributes": {
                    "title": title,
                    "severity": severity,
                    "customer_impacted": customer_impacted,
                },
            }
        }
        return await self._request("POST", "/api/v2/incidents", json=payload)  # type: ignore[return-value]

    async def update_incident(
        self,
        incident_id: str,
        title: str | None = None,
        severity: str | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        """PATCH /api/v2/incidents/{id} — Update incident."""
        attrs: dict[str, Any] = {}
        if title is not None:
            attrs["title"] = title
        if severity is not None:
            attrs["severity"] = severity
        if state is not None:
            attrs["state"] = state
        payload = {
            "data": {
                "type": "incidents",
                "id": incident_id,
                "attributes": attrs,
            }
        }
        return await self._request("PATCH", f"/api/v2/incidents/{incident_id}", json=payload)  # type: ignore[return-value]

    # ── Dashboards ──────────────────────────────────────────────

    async def list_dashboards(self) -> list[dict[str, Any]]:
        """GET /api/v1/dashboard — List all dashboards."""
        data = await self._request("GET", "/api/v1/dashboard")
        if isinstance(data, dict):
            return data.get("dashboards", [])
        return []  # type: ignore[return-value]

    async def get_dashboard(self, dashboard_id: str) -> dict[str, Any]:
        """GET /api/v1/dashboard/{id} — Get dashboard details."""
        return await self._request("GET", f"/api/v1/dashboard/{dashboard_id}")  # type: ignore[return-value]

    # ── Metrics ─────────────────────────────────────────────────

    async def list_metrics(self, from_time: int | None = None) -> list[str]:
        """GET /api/v1/metrics — List available metric names."""
        params: dict[str, Any] = {}
        if from_time is not None:
            params["from"] = from_time
        data = await self._request("GET", "/api/v1/metrics", params=params)
        if isinstance(data, dict):
            return data.get("metrics", [])
        return []  # type: ignore[return-value]

    async def query_metrics(
        self,
        query: str,
        from_time: int,
        to_time: int,
    ) -> dict[str, Any]:
        """GET /api/v1/query — Query metrics over a time range."""
        params = {
            "query": query,
            "from": from_time,
            "to": to_time,
        }
        return await self._request("GET", "/api/v1/query", params=params)  # type: ignore[return-value]

    # ── Events ──────────────────────────────────────────────────

    async def list_events(
        self,
        start: int,
        end: int,
        tags: str | None = None,
        sources: str | None = None,
        priority: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/v1/events — List events in a time range."""
        params: dict[str, Any] = {"start": start, "end": end}
        if tags:
            params["tags"] = tags
        if sources:
            params["sources"] = sources
        if priority:
            params["priority"] = priority
        return await self._request("GET", "/api/v1/events", params=params)  # type: ignore[return-value]
