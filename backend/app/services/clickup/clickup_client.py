"""
ClickUp REST API v2 Client

Async client for ClickUp's REST API.
Used by the user-facing ClickUp integration — agents interact with the USER's
ClickUp workspace for spaces, folders, lists, tasks, and comments.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).

Token URL: https://api.clickup.com/api/v2/oauth/token
API Base: https://api.clickup.com/api/v2
Quirk: Tokens do NOT expire — no refresh token needed.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CLICKUP_API_BASE = "https://api.clickup.com/api/v2"


class ClickUpAPIError(Exception):
    """ClickUp API error."""

    pass


class ClickUpClient:
    """Async REST client for ClickUp API v2."""

    def __init__(self, auth_token: str, base_url: str = CLICKUP_API_BASE):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self._headers = {
            "Authorization": auth_token,
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
                raise ClickUpAPIError(f"ClickUp rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise ClickUpAPIError(f"ClickUp API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── User ────────────────────────────────────────────────────

    async def get_user(self) -> dict[str, Any]:
        """GET /user — Get authenticated user info (credential validation)."""
        return await self._request("GET", "/user")  # type: ignore[return-value]

    # ── Workspaces (Teams) ─────────────────────────────────────

    async def list_workspaces(self) -> dict[str, Any]:
        """GET /team — List user's workspaces (teams)."""
        return await self._request("GET", "/team")  # type: ignore[return-value]

    # ── Spaces ──────────────────────────────────────────────────

    async def list_spaces(self, team_id: str) -> dict[str, Any]:
        """GET /team/{team_id}/space — List spaces in a workspace."""
        return await self._request("GET", f"/team/{team_id}/space")  # type: ignore[return-value]

    # ── Folders ─────────────────────────────────────────────────

    async def list_folders(self, space_id: str) -> dict[str, Any]:
        """GET /space/{space_id}/folder — List folders in a space."""
        return await self._request("GET", f"/space/{space_id}/folder")  # type: ignore[return-value]

    # ── Lists ───────────────────────────────────────────────────

    async def list_lists(self, folder_id: str) -> dict[str, Any]:
        """GET /folder/{folder_id}/list — Lists in a folder."""
        return await self._request("GET", f"/folder/{folder_id}/list")  # type: ignore[return-value]

    # ── Tasks ───────────────────────────────────────────────────

    async def list_tasks(
        self,
        list_id: str,
        page: int = 0,
        order_by: str = "created",
        reverse: bool = False,
    ) -> dict[str, Any]:
        """GET /list/{list_id}/task — Tasks in a list."""
        params: dict[str, Any] = {
            "page": page,
            "order_by": order_by,
            "reverse": str(reverse).lower(),
        }
        return await self._request("GET", f"/list/{list_id}/task", params=params)  # type: ignore[return-value]

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """GET /task/{task_id} — Task details."""
        return await self._request("GET", f"/task/{task_id}")  # type: ignore[return-value]

    async def create_task(
        self,
        list_id: str,
        name: str,
        description: str | None = None,
        assignees: list[int] | None = None,
        priority: int | None = None,
        due_date: int | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """POST /list/{list_id}/task — Create a task."""
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        if assignees is not None:
            body["assignees"] = assignees
        if priority is not None:
            body["priority"] = priority
        if due_date is not None:
            body["due_date"] = due_date
        if status is not None:
            body["status"] = status
        return await self._request("POST", f"/list/{list_id}/task", json_body=body)  # type: ignore[return-value]

    async def update_task(
        self,
        task_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        due_date: int | None = None,
        assignees: list[int] | None = None,
    ) -> dict[str, Any]:
        """PUT /task/{task_id} — Update a task."""
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if status is not None:
            body["status"] = status
        if priority is not None:
            body["priority"] = priority
        if due_date is not None:
            body["due_date"] = due_date
        if assignees is not None:
            body["assignees"] = assignees
        return await self._request("PUT", f"/task/{task_id}", json_body=body)  # type: ignore[return-value]

    # ── Comments ────────────────────────────────────────────────

    async def get_comments(self, task_id: str) -> dict[str, Any]:
        """GET /task/{task_id}/comment — Get comments on a task."""
        return await self._request("GET", f"/task/{task_id}/comment")  # type: ignore[return-value]

    async def add_comment(self, task_id: str, comment_text: str) -> dict[str, Any]:
        """POST /task/{task_id}/comment — Add a comment to a task."""
        return await self._request(
            "POST",
            f"/task/{task_id}/comment",
            json_body={"comment_text": comment_text},
        )  # type: ignore[return-value]

    # ── Time Tracking ───────────────────────────────────────────

    async def list_time_entries(self, team_id: str) -> dict[str, Any]:
        """GET /team/{team_id}/time_entries — List time entries for a workspace."""
        return await self._request("GET", f"/team/{team_id}/time_entries")  # type: ignore[return-value]
