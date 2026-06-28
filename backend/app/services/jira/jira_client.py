"""
Jira Cloud REST API Client

Async client for Jira Cloud API v3 via the Atlassian REST API gateway.
Used by the user-facing Jira integration — agents manage the USER's Jira issues.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).
All requests go through: https://api.atlassian.com/ex/jira/{cloudId}/rest/api/3/...

The cloudId is obtained during the OAuth callback site discovery step and
stored in IntegrationConnection.account_id.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ATLASSIAN_API_BASE = "https://api.atlassian.com"


class JiraAPIError(Exception):
    """Jira API error."""

    pass


def text_to_adf(text: str) -> dict[str, Any]:
    """Convert plain text to Atlassian Document Format (ADF).

    Handles paragraph splitting on double newlines.
    Single newlines become hard breaks within paragraphs.
    """
    if not text:
        return {"version": 1, "type": "doc", "content": [{"type": "paragraph"}]}

    paragraphs = text.split("\n\n")
    content: list[dict[str, Any]] = []
    for para in paragraphs:
        if not para.strip():
            continue
        # Handle single newlines within a paragraph as hard breaks
        lines = para.split("\n")
        para_content: list[dict[str, Any]] = []
        for i, line in enumerate(lines):
            para_content.append({"type": "text", "text": line})
            if i < len(lines) - 1:
                para_content.append({"type": "hardBreak"})
        content.append({"type": "paragraph", "content": para_content})

    return {"version": 1, "type": "doc", "content": content or [{"type": "paragraph"}]}


class JiraClient:
    """Async REST client for Jira Cloud API v3."""

    def __init__(self, cloud_id: str, auth_token: str):
        """
        Args:
            cloud_id: Atlassian cloud ID (from site discovery during OAuth callback)
            auth_token: Atlassian OAuth access token
        """
        self.cloud_id = cloud_id
        self.auth_token = auth_token
        self._base_url = f"{ATLASSIAN_API_BASE}/ex/jira/{cloud_id}"
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
            if resp.status_code >= 400:
                raise JiraAPIError(f"Jira API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            # Some endpoints return 204 No Content
            if resp.status_code == 204:
                return {}
            return resp.json()

    # ── User ───────────────────────────────────────────────────

    async def get_myself(self) -> dict[str, Any]:
        """GET /rest/api/3/myself — Get authenticated user info."""
        return await self._request("GET", "/rest/api/3/myself")  # type: ignore[return-value]

    # ── Projects ───────────────────────────────────────────────

    async def list_projects(self) -> list[dict[str, Any]]:
        """GET /rest/api/3/project — List all projects."""
        data = await self._request("GET", "/rest/api/3/project")
        return data if isinstance(data, list) else []  # type: ignore[return-value]

    async def get_project(self, project_id_or_key: str) -> dict[str, Any]:
        """GET /rest/api/3/project/{projectIdOrKey} — Get project details."""
        return await self._request("GET", f"/rest/api/3/project/{project_id_or_key}")  # type: ignore[return-value]

    # ── Issues ─────────────────────────────────────────────────

    async def search_issues(
        self,
        jql: str,
        fields: list[str] | None = None,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """POST /rest/api/3/search — Search issues with JQL."""
        body: dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
        }
        if fields:
            body["fields"] = fields
        return await self._request("POST", "/rest/api/3/search", json=body)  # type: ignore[return-value]

    async def get_issue(self, issue_id_or_key: str) -> dict[str, Any]:
        """GET /rest/api/3/issue/{issueIdOrKey} — Get issue details."""
        return await self._request("GET", f"/rest/api/3/issue/{issue_id_or_key}")  # type: ignore[return-value]

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: str | None = None,
        priority: str | None = None,
        assignee_account_id: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """POST /rest/api/3/issue — Create a new issue.

        Description is automatically converted to ADF format.
        """
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
        if description:
            fields["description"] = text_to_adf(description)
        if priority:
            fields["priority"] = {"name": priority}
        if assignee_account_id:
            fields["assignee"] = {"id": assignee_account_id}
        if labels:
            fields["labels"] = labels

        return await self._request("POST", "/rest/api/3/issue", json={"fields": fields})  # type: ignore[return-value]

    async def update_issue(
        self,
        issue_id_or_key: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """PUT /rest/api/3/issue/{issueIdOrKey} — Update issue fields."""
        # If description is a plain string, convert to ADF
        if "description" in fields and isinstance(fields["description"], str):
            fields["description"] = text_to_adf(fields["description"])
        return await self._request(
            "PUT",
            f"/rest/api/3/issue/{issue_id_or_key}",
            json={"fields": fields},
        )  # type: ignore[return-value]

    async def add_comment(
        self,
        issue_id_or_key: str,
        body: str,
    ) -> dict[str, Any]:
        """POST /rest/api/3/issue/{issueIdOrKey}/comment — Add a comment.

        Body is automatically converted to ADF format.
        """
        return await self._request(
            "POST",
            f"/rest/api/3/issue/{issue_id_or_key}/comment",
            json={"body": text_to_adf(body)},
        )  # type: ignore[return-value]

    # ── Transitions ────────────────────────────────────────────

    async def list_transitions(self, issue_id_or_key: str) -> list[dict[str, Any]]:
        """GET /rest/api/3/issue/{issueIdOrKey}/transitions — List available transitions."""
        data = await self._request("GET", f"/rest/api/3/issue/{issue_id_or_key}/transitions")
        if isinstance(data, dict):
            return data.get("transitions", [])
        return []  # type: ignore[return-value]

    async def transition_issue(
        self,
        issue_id_or_key: str,
        transition_id: str,
    ) -> dict[str, Any]:
        """POST /rest/api/3/issue/{issueIdOrKey}/transitions — Transition issue status."""
        return await self._request(
            "POST",
            f"/rest/api/3/issue/{issue_id_or_key}/transitions",
            json={"transition": {"id": transition_id}},
        )  # type: ignore[return-value]

    # ── Boards & Sprints (Agile) ──────────────────────────────

    async def list_boards(self) -> list[dict[str, Any]]:
        """GET /agile/1.0/board — List Scrum/Kanban boards."""
        data = await self._request("GET", "/agile/1.0/board")
        if isinstance(data, dict):
            return data.get("values", [])
        return []  # type: ignore[return-value]

    async def list_sprints(self, board_id: int) -> list[dict[str, Any]]:
        """GET /agile/1.0/board/{boardId}/sprint — List sprints for a board."""
        data = await self._request("GET", f"/agile/1.0/board/{board_id}/sprint")
        if isinstance(data, dict):
            return data.get("values", [])
        return []  # type: ignore[return-value]
