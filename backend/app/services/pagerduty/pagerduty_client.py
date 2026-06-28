"""
PagerDuty REST API Client

Async client for PagerDuty's REST API v2.
Used by the user-facing PagerDuty integration — agents manage incidents,
services, schedules, and escalation policies on behalf of the USER.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).
Works with PagerDuty's standard OAuth2 flow (no quirks).

Token URL: https://identity.pagerduty.com/oauth/token
API Base: https://api.pagerduty.com
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PAGERDUTY_API_BASE = "https://api.pagerduty.com"


class PagerDutyAPIError(Exception):
    """PagerDuty API error."""

    pass


class PagerDutyClient:
    """Async REST client for PagerDuty REST API v2."""

    def __init__(self, auth_token: str, base_url: str = PAGERDUTY_API_BASE):
        """
        Args:
            auth_token: PagerDuty OAuth access token
            base_url: PagerDuty API base URL (default: https://api.pagerduty.com)
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.pagerduty+json;version=2",
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
                retry_after = resp.headers.get("retry-after", "?")
                raise PagerDutyAPIError(f"PagerDuty rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise PagerDutyAPIError(f"PagerDuty API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            if resp.status_code == 204:
                return {}
            return resp.json()

    # ── User ───────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """GET /users/me — Get authenticated user info (credential validation)."""
        return await self._request("GET", "/users/me")  # type: ignore[return-value]

    # ── Incidents ───────────────────────────────────────────────

    async def list_incidents(
        self,
        limit: int = 25,
        offset: int | None = None,
        statuses: list[str] | None = None,
        urgencies: list[str] | None = None,
        service_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """GET /incidents — List incidents with optional filters."""
        params: dict[str, Any] = {"limit": limit}
        if offset is not None:
            params["offset"] = offset
        if statuses:
            params["statuses[]"] = statuses
        if urgencies:
            params["urgencies[]"] = urgencies
        if service_ids:
            params["service_ids[]"] = service_ids
        return await self._request("GET", "/incidents", params=params)  # type: ignore[return-value]

    async def get_incident(self, incident_id: str) -> dict[str, Any]:
        """GET /incidents/{id} — Get incident details."""
        return await self._request("GET", f"/incidents/{incident_id}")  # type: ignore[return-value]

    async def create_incident(
        self,
        title: str,
        service_id: str,
        urgency: str = "high",
        body: str | None = None,
        incident_key: str | None = None,
    ) -> dict[str, Any]:
        """POST /incidents — Create a new incident."""
        payload: dict[str, Any] = {
            "incident": {
                "type": "incident",
                "title": title,
                "service": {"id": service_id, "type": "service_reference"},
                "urgency": urgency,
            }
        }
        if body:
            payload["incident"]["body"] = {
                "type": "incident_body",
                "details": body,
            }
        if incident_key:
            payload["incident"]["incident_key"] = incident_key
        return await self._request("POST", "/incidents", json=payload)  # type: ignore[return-value]

    async def update_incident(
        self,
        incident_id: str,
        status: str | None = None,
        priority: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """PUT /incidents/{id} — Update incident (acknowledge, resolve, add note)."""
        payload: dict[str, Any] = {"incident": {"type": "incident_reference"}}
        if status:
            payload["incident"]["status"] = status
        if priority:
            payload["incident"]["priority"] = priority
        if note:
            payload["incident"]["body"] = {
                "type": "incident_body",
                "details": note,
            }
        return await self._request("PUT", f"/incidents/{incident_id}", json=payload)  # type: ignore[return-value]

    # ── Services ────────────────────────────────────────────────

    async def list_services(
        self,
        limit: int = 25,
        offset: int | None = None,
    ) -> dict[str, Any]:
        """GET /services — List services (paginated with offset)."""
        params: dict[str, Any] = {"limit": limit}
        if offset is not None:
            params["offset"] = offset
        return await self._request("GET", "/services", params=params)  # type: ignore[return-value]

    async def get_service(self, service_id: str) -> dict[str, Any]:
        """GET /services/{id} — Get service details."""
        return await self._request("GET", f"/services/{service_id}")  # type: ignore[return-value]

    # ── Schedules ───────────────────────────────────────────────

    async def list_schedules(
        self,
        limit: int = 25,
        offset: int | None = None,
    ) -> dict[str, Any]:
        """GET /schedules — List on-call schedules."""
        params: dict[str, Any] = {"limit": limit}
        if offset is not None:
            params["offset"] = offset
        return await self._request("GET", "/schedules", params=params)  # type: ignore[return-value]

    async def get_schedule(self, schedule_id: str) -> dict[str, Any]:
        """GET /schedules/{id} — Get schedule details."""
        return await self._request("GET", f"/schedules/{schedule_id}")  # type: ignore[return-value]

    # ── Escalation Policies ─────────────────────────────────────

    async def list_escalation_policies(
        self,
        limit: int = 25,
        offset: int | None = None,
    ) -> dict[str, Any]:
        """GET /escalation_policies — List escalation policies."""
        params: dict[str, Any] = {"limit": limit}
        if offset is not None:
            params["offset"] = offset
        return await self._request("GET", "/escalation_policies", params=params)  # type: ignore[return-value]

    # ── Users ───────────────────────────────────────────────────

    async def list_users(
        self,
        limit: int = 25,
        offset: int | None = None,
    ) -> dict[str, Any]:
        """GET /users — List users."""
        params: dict[str, Any] = {"limit": limit}
        if offset is not None:
            params["offset"] = offset
        return await self._request("GET", "/users", params=params)  # type: ignore[return-value]

    async def get_user(self, user_id: str) -> dict[str, Any]:
        """GET /users/{id} — Get user details."""
        return await self._request("GET", f"/users/{user_id}")  # type: ignore[return-value]
