"""
Asana REST API Client

Async client for Asana's REST API.
Used by the user-facing Asana integration — agents interact with the USER's
Asana workspace for projects, tasks, and sections.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).

Token URL: https://app.asana.com/-/oauth_token
API Base: https://app.asana.com/api/1.0
Quirk: Responses are sparse by default — must use `opt_fields` to request specific fields.
Note: Asana tokens expire in 1 hour. Refresh tokens are supported.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ASANA_API_BASE = "https://app.asana.com/api/1.0"

# Pre-defined opt_fields for list/get endpoints to avoid sparse responses
_TASK_FIELDS = "name,completed,due_on,assignee,assignee.name,notes,projects,projects.name,section,section.name,created_at,modified_at,permalink_url,tags,tags.name"
_PROJECT_FIELDS = "name,notes,color,archived,created_at,modified_at,permalink_url,public,team,team.name"
_WORKSPACE_FIELDS = "name,is_organization"
_SECTION_FIELDS = "name,project,project.name"


class AsanaAPIError(Exception):
    """Asana API error."""

    pass


class AsanaClient:
    """Async REST client for Asana API."""

    def __init__(self, auth_token: str, base_url: str = ASANA_API_BASE):
        """
        Args:
            auth_token: Asana OAuth access token
            base_url: Asana API base URL (default: https://app.asana.com/api/1.0)
        """
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
                raise AsanaAPIError(f"Asana rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise AsanaAPIError(f"Asana API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── User ────────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """GET /users/me — Get authenticated user info (credential validation)."""
        return await self._request("GET", "/users/me", params={"opt_fields": "name,email"})  # type: ignore[return-value]

    # ── Workspaces ──────────────────────────────────────────────

    async def list_workspaces(self) -> dict[str, Any]:
        """GET /workspaces — List user's workspaces."""
        return await self._request("GET", "/workspaces", params={"opt_fields": _WORKSPACE_FIELDS})  # type: ignore[return-value]

    # ── Projects ────────────────────────────────────────────────

    async def list_projects(
        self,
        workspace: str | None = None,
        offset: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """GET /projects — List projects, optionally filtered by workspace."""
        params: dict[str, Any] = {"opt_fields": _PROJECT_FIELDS, "limit": limit}
        if workspace:
            params["workspace"] = workspace
        if offset:
            params["offset"] = offset
        return await self._request("GET", "/projects", params=params)  # type: ignore[return-value]

    async def get_project(self, project_gid: str) -> dict[str, Any]:
        """GET /projects/{gid} — Get project details."""
        return await self._request("GET", f"/projects/{project_gid}", params={"opt_fields": _PROJECT_FIELDS})  # type: ignore[return-value]

    # ── Tasks ───────────────────────────────────────────────────

    async def list_tasks(
        self,
        project: str | None = None,
        assignee: str | None = None,
        workspace: str | None = None,
        completed_since: str | None = None,
        offset: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """GET /tasks — List tasks with optional filters."""
        params: dict[str, Any] = {"opt_fields": _TASK_FIELDS, "limit": limit}
        if project:
            params["project"] = project
        if assignee:
            params["assignee"] = assignee
        if workspace:
            params["workspace"] = workspace
        if completed_since:
            params["completed_since"] = completed_since
        if offset:
            params["offset"] = offset
        return await self._request("GET", "/tasks", params=params)  # type: ignore[return-value]

    async def get_task(self, task_gid: str) -> dict[str, Any]:
        """GET /tasks/{gid} — Get task details."""
        return await self._request("GET", f"/tasks/{task_gid}", params={"opt_fields": _TASK_FIELDS})  # type: ignore[return-value]

    async def create_task(
        self,
        name: str,
        projects: list[str] | None = None,
        notes: str | None = None,
        assignee: str | None = None,
        due_on: str | None = None,
    ) -> dict[str, Any]:
        """POST /tasks — Create a new task."""
        body: dict[str, Any] = {"name": name, "opt_fields": _TASK_FIELDS}
        if projects:
            body["projects"] = projects
        if notes:
            body["notes"] = notes
        if assignee:
            body["assignee"] = assignee
        if due_on:
            body["due_on"] = due_on
        return await self._request("POST", "/tasks", json_body={"data": body})  # type: ignore[return-value]

    async def update_task(
        self,
        task_gid: str,
        name: str | None = None,
        notes: str | None = None,
        assignee: str | None = None,
        due_on: str | None = None,
        completed: bool | None = None,
    ) -> dict[str, Any]:
        """PUT /tasks/{gid} — Update task fields."""
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if notes is not None:
            body["notes"] = notes
        if assignee is not None:
            body["assignee"] = assignee
        if due_on is not None:
            body["due_on"] = due_on
        if completed is not None:
            body["completed"] = completed
        return await self._request("PUT", f"/tasks/{task_gid}", json_body={"data": body})  # type: ignore[return-value]

    async def complete_task(self, task_gid: str) -> dict[str, Any]:
        """POST /tasks/{gid} — Mark task as completed."""
        return await self._request("POST", f"/tasks/{task_gid}", json_body={"data": {"completed": True}})  # type: ignore[return-value]

    # ── Sections ────────────────────────────────────────────────

    async def list_sections(
        self,
        project_gid: str,
        offset: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """GET /projects/{gid}/sections — List sections in a project."""
        params: dict[str, Any] = {"opt_fields": _SECTION_FIELDS, "limit": limit}
        if offset:
            params["offset"] = offset
        return await self._request("GET", f"/projects/{project_gid}/sections", params=params)  # type: ignore[return-value]
