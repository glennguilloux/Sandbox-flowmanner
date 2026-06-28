"""
Vercel REST API Client

Async client for Vercel's REST API.
Used by the user-facing Vercel integration — agents monitor and manage the USER's Vercel deployments.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).
Works with Vercel's standard OAuth2 flow.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

VERCEL_API_BASE = "https://api.vercel.com"


class VercelAPIError(Exception):
    """Vercel API error."""

    pass


class VercelClient:
    """Async REST client for Vercel API."""

    def __init__(self, auth_token: str, base_url: str = VERCEL_API_BASE):
        """
        Args:
            auth_token: Vercel OAuth access token (user provides this via OAuth)
            base_url: Vercel API base URL (default: https://api.vercel.com)
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
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=self._headers, **kwargs)
            if resp.status_code >= 400:
                raise VercelAPIError(f"Vercel API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── User ───────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """GET /v2/user — Get authenticated user info."""
        return await self._request("GET", "/v2/user")  # type: ignore[return-value]

    # ── Projects ───────────────────────────────────────────────

    async def list_projects(
        self,
        limit: int = 20,
        until: int | None = None,
    ) -> dict[str, Any]:
        """GET /v9/projects — List projects.

        Vercel uses `until` (timestamp) cursor for pagination.
        """
        params: dict[str, Any] = {"limit": limit}
        if until is not None:
            params["until"] = until
        return await self._request("GET", "/v9/projects", params=params)  # type: ignore[return-value]

    async def get_project(self, project_id_or_name: str) -> dict[str, Any]:
        """GET /v9/projects/{id} — Get project details."""
        return await self._request("GET", f"/v9/projects/{project_id_or_name}")  # type: ignore[return-value]

    # ── Deployments ────────────────────────────────────────────

    async def list_deployments(
        self,
        project_id: str | None = None,
        limit: int = 20,
        until: int | None = None,
    ) -> dict[str, Any]:
        """GET /v6/deployments — List deployments, optionally filtered by project."""
        params: dict[str, Any] = {"limit": limit}
        if project_id:
            params["projectId"] = project_id
        if until is not None:
            params["until"] = until
        return await self._request("GET", "/v6/deployments", params=params)  # type: ignore[return-value]

    async def get_deployment(self, deployment_id: str) -> dict[str, Any]:
        """GET /v13/deployments/{id} — Get deployment details."""
        return await self._request("GET", f"/v13/deployments/{deployment_id}")  # type: ignore[return-value]

    async def cancel_deployment(self, deployment_id: str) -> dict[str, Any]:
        """POST /v13/deployments/{id}/cancel — Cancel a running deployment."""
        return await self._request("POST", f"/v13/deployments/{deployment_id}/cancel")  # type: ignore[return-value]

    async def redeploy(
        self,
        deployment_id: str,
        target: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """POST /v13/deployments — Trigger a redeployment."""
        body: dict[str, Any] = {"deploymentId": deployment_id}
        if target:
            body["target"] = target
        if name:
            body["name"] = name
        return await self._request("POST", "/v13/deployments", json=body)  # type: ignore[return-value]

    async def get_deployment_events(self, deployment_id: str) -> list[Any]:
        """GET /v2/deployments/{id}/events — Get build events for a deployment."""
        data = await self._request("GET", f"/v2/deployments/{deployment_id}/events")
        return data if isinstance(data, list) else []  # type: ignore[return-value]

    # ── Domains ────────────────────────────────────────────────

    async def list_domains(self, project_id: str) -> dict[str, Any]:
        """GET /v9/projects/{id}/domains — List domains for a project."""
        return await self._request("GET", f"/v9/projects/{project_id}/domains")  # type: ignore[return-value]
