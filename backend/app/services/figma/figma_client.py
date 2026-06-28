"""
Figma REST API Client

Async client for Figma's REST API.
Used by the user-facing Figma integration — agents read and interact with
the USER's Figma design files.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).
Works with Figma's standard OAuth2 flow.

Token URL: https://www.figma.com/api/oauth/token (verified against Figma docs 2026-06-28).
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FIGMA_API_BASE = "https://api.figma.com"


class FigmaAPIError(Exception):
    """Figma API error."""

    pass


class FigmaClient:
    """Async REST client for Figma API."""

    def __init__(self, auth_token: str, base_url: str = FIGMA_API_BASE):
        """
        Args:
            auth_token: Figma OAuth access token
            base_url: Figma API base URL (default: https://api.figma.com)
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self._headers = {
            "X-Figma-Token": auth_token,
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
                raise FigmaAPIError(f"Figma API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── User ───────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """GET /v1/me — Get authenticated user info."""
        return await self._request("GET", "/v1/me")  # type: ignore[return-value]

    # ── Files ──────────────────────────────────────────────────

    async def get_file(self, file_key: str) -> dict[str, Any]:
        """GET /v1/files/:key — Get full file data."""
        return await self._request("GET", f"/v1/files/{file_key}")  # type: ignore[return-value]

    async def get_file_nodes(self, file_key: str, node_ids: list[str]) -> dict[str, Any]:
        """GET /v1/files/:key/nodes?ids=... — Get specific nodes from a file."""
        return await self._request(
            "GET",
            f"/v1/files/{file_key}/nodes",
            params={"ids": ",".join(node_ids)},
        )  # type: ignore[return-value]

    # ── Comments ───────────────────────────────────────────────

    async def list_comments(self, file_key: str) -> list[dict[str, Any]]:
        """GET /v1/files/:key/comments — List all comments on a file."""
        data = await self._request("GET", f"/v1/files/{file_key}/comments")
        if isinstance(data, dict):
            return data.get("comments", [])
        return []  # type: ignore[return-value]

    async def post_comment(
        self,
        file_key: str,
        message: str,
        client_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /v1/files/:key/comments — Add a comment to a file."""
        body: dict[str, Any] = {"message": message}
        if client_meta:
            body["client_meta"] = client_meta
        return await self._request("POST", f"/v1/files/{file_key}/comments", json=body)  # type: ignore[return-value]

    # ── Versions ───────────────────────────────────────────────

    async def get_file_versions(self, file_key: str) -> list[dict[str, Any]]:
        """GET /v1/files/:key/versions — Get version history of a file."""
        data = await self._request("GET", f"/v1/files/{file_key}/versions")
        if isinstance(data, dict):
            return data.get("versions", [])
        return []  # type: ignore[return-value]

    # ── Team Projects ──────────────────────────────────────────

    async def list_team_projects(self, team_id: str) -> list[dict[str, Any]]:
        """GET /v1/teams/:team_id/projects — List projects for a team.

        Note: Not available for public OAuth apps.
        """
        data = await self._request("GET", f"/v1/teams/{team_id}/projects")
        if isinstance(data, dict):
            return data.get("projects", [])
        return []  # type: ignore[return-value]

    async def list_project_files(self, project_id: str) -> list[dict[str, Any]]:
        """GET /v1/projects/:project_id/files — List files in a project."""
        data = await self._request("GET", f"/v1/projects/{project_id}/files")
        if isinstance(data, dict):
            return data.get("files", [])
        return []  # type: ignore[return-value]
