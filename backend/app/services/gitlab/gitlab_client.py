"""
GitLab REST API v4 Client

Async client for GitLab's REST API.
Used by the user-facing GitLab integration — agents interact with the USER's
GitLab instance for projects, merge requests, issues, and pipelines.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).

Token URL: https://gitlab.com/oauth/token (or self-hosted)
API Base: https://gitlab.com/api/v4 (or self-hosted)
Quirk: Supports self-hosted instances — base_url is configurable per connection.
Note: GitLab tokens expire in 2 hours. Refresh tokens are supported.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITLAB_API_BASE = "https://gitlab.com/api/v4"


class GitLabAPIError(Exception):
    """GitLab API error."""

    pass


class GitLabClient:
    """Async REST client for GitLab API v4."""

    def __init__(self, auth_token: str, base_url: str = GITLAB_API_BASE):
        """
        Args:
            auth_token: GitLab OAuth access token
            base_url: GitLab API base URL (default: https://gitlab.com/api/v4).
                      For self-hosted instances, pass e.g. https://gitlab.example.com/api/v4
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
                raise GitLabAPIError(f"GitLab rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise GitLabAPIError(f"GitLab API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── User ────────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """GET /user — Get authenticated user info (credential validation)."""
        return await self._request("GET", "/user")  # type: ignore[return-value]

    # ── Projects ────────────────────────────────────────────────

    async def list_projects(
        self,
        membership: bool = True,
        page: int = 1,
        per_page: int = 20,
    ) -> list[Any]:
        """GET /projects — List projects (filtered by membership by default)."""
        params: dict[str, Any] = {
            "membership": str(membership).lower(),
            "page": page,
            "per_page": per_page,
            "order_by": "last_activity_at",
            "sort": "desc",
        }
        return await self._request("GET", "/projects", params=params)  # type: ignore[return-value]

    async def get_project(self, project_id: str | int) -> dict[str, Any]:
        """GET /projects/:id — Get project details."""
        return await self._request("GET", f"/projects/{project_id}")  # type: ignore[return-value]

    # ── Merge Requests ──────────────────────────────────────────

    async def list_merge_requests(
        self,
        project_id: str | int,
        state: str = "opened",
        page: int = 1,
        per_page: int = 20,
    ) -> list[Any]:
        """GET /projects/:id/merge_requests — List merge requests."""
        params: dict[str, Any] = {
            "state": state,
            "page": page,
            "per_page": per_page,
        }
        return await self._request("GET", f"/projects/{project_id}/merge_requests", params=params)  # type: ignore[return-value]

    async def get_merge_request(self, project_id: str | int, mr_iid: int) -> dict[str, Any]:
        """GET /projects/:id/merge_requests/:mr_iid — Get MR details."""
        return await self._request("GET", f"/projects/{project_id}/merge_requests/{mr_iid}")  # type: ignore[return-value]

    async def create_merge_request(
        self,
        project_id: str | int,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """POST /projects/:id/merge_requests — Create a merge request."""
        body: dict[str, Any] = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
        }
        if description:
            body["description"] = description
        return await self._request("POST", f"/projects/{project_id}/merge_requests", json_body=body)  # type: ignore[return-value]

    async def merge_merge_request(self, project_id: str | int, mr_iid: int) -> dict[str, Any]:
        """PUT /projects/:id/merge_requests/:mr_iid/merge — Merge an MR."""
        return await self._request("PUT", f"/projects/{project_id}/merge_requests/{mr_iid}/merge")  # type: ignore[return-value]

    async def approve_merge_request(self, project_id: str | int, mr_iid: int) -> dict[str, Any]:
        """POST /projects/:id/merge_requests/:mr_iid/approve — Approve an MR."""
        return await self._request("POST", f"/projects/{project_id}/merge_requests/{mr_iid}/approve")  # type: ignore[return-value]

    # ── Issues ──────────────────────────────────────────────────

    async def list_issues(
        self,
        project_id: str | int,
        state: str = "opened",
        page: int = 1,
        per_page: int = 20,
    ) -> list[Any]:
        """GET /projects/:id/issues — List issues."""
        params: dict[str, Any] = {
            "state": state,
            "page": page,
            "per_page": per_page,
        }
        return await self._request("GET", f"/projects/{project_id}/issues", params=params)  # type: ignore[return-value]

    async def get_issue(self, project_id: str | int, issue_iid: int) -> dict[str, Any]:
        """GET /projects/:id/issues/:issue_iid — Get issue details."""
        return await self._request("GET", f"/projects/{project_id}/issues/{issue_iid}")  # type: ignore[return-value]

    async def create_issue(
        self,
        project_id: str | int,
        title: str,
        description: str | None = None,
        assignee_ids: list[int] | None = None,
        labels: str | None = None,
    ) -> dict[str, Any]:
        """POST /projects/:id/issues — Create an issue."""
        body: dict[str, Any] = {"title": title}
        if description:
            body["description"] = description
        if assignee_ids:
            body["assignee_ids"] = assignee_ids
        if labels:
            body["labels"] = labels
        return await self._request("POST", f"/projects/{project_id}/issues", json_body=body)  # type: ignore[return-value]

    async def add_issue_note(
        self,
        project_id: str | int,
        issue_iid: int,
        body: str,
    ) -> dict[str, Any]:
        """POST /projects/:id/issues/:issue_iid/notes — Add a comment to an issue."""
        return await self._request(
            "POST",
            f"/projects/{project_id}/issues/{issue_iid}/notes",
            json_body={"body": body},
        )  # type: ignore[return-value]

    # ── Pipelines ───────────────────────────────────────────────

    async def list_pipelines(
        self,
        project_id: str | int,
        status: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> list[Any]:
        """GET /projects/:id/pipelines — List pipelines."""
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if status:
            params["status"] = status
        return await self._request("GET", f"/projects/{project_id}/pipelines", params=params)  # type: ignore[return-value]

    async def get_pipeline(self, project_id: str | int, pipeline_id: int) -> dict[str, Any]:
        """GET /projects/:id/pipelines/:pipeline_id — Get pipeline details."""
        return await self._request("GET", f"/projects/{project_id}/pipelines/{pipeline_id}")  # type: ignore[return-value]

    async def retry_pipeline(self, project_id: str | int, pipeline_id: int) -> dict[str, Any]:
        """POST /projects/:id/pipelines/:pipeline_id/retry — Retry a failed pipeline."""
        return await self._request("POST", f"/projects/{project_id}/pipelines/{pipeline_id}/retry")  # type: ignore[return-value]

    async def cancel_pipeline(self, project_id: str | int, pipeline_id: int) -> dict[str, Any]:
        """POST /projects/:id/pipelines/:pipeline_id/cancel — Cancel a running pipeline."""
        return await self._request("POST", f"/projects/{project_id}/pipelines/{pipeline_id}/cancel")  # type: ignore[return-value]

    # ── Deployments ─────────────────────────────────────────────

    async def list_deployments(
        self,
        project_id: str | int,
        page: int = 1,
        per_page: int = 20,
    ) -> list[Any]:
        """GET /projects/:id/deployments — List deployments."""
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        return await self._request("GET", f"/projects/{project_id}/deployments", params=params)  # type: ignore[return-value]

    # ── Releases ────────────────────────────────────────────────

    async def list_releases(
        self,
        project_id: str | int,
        page: int = 1,
        per_page: int = 20,
    ) -> list[Any]:
        """GET /projects/:id/releases — List releases."""
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        return await self._request("GET", f"/projects/{project_id}/releases", params=params)  # type: ignore[return-value]

    async def create_release(
        self,
        project_id: str | int,
        tag_name: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """POST /projects/:id/releases — Create a release."""
        body: dict[str, Any] = {"tag_name": tag_name}
        if name:
            body["name"] = name
        if description:
            body["description"] = description
        return await self._request("POST", f"/projects/{project_id}/releases", json_body=body)  # type: ignore[return-value]
