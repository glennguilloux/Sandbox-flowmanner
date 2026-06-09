"""Linear integration adapter — 4 actions using the Linear GraphQL API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.integrations.adapters.base import BaseIntegrationAdapter

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"

# ── GraphQL query templates (variables are parameterised — no interpolation) ───

_CREATE_ISSUE_MUTATION = """
mutation($teamId: String!, $title: String!, $description: String, $priority: Int, $assigneeId: String) {
  issueCreate(input: {
    teamId: $teamId,
    title: $title,
    description: $description,
    priority: $priority,
    assigneeId: $assigneeId
  }) {
    success
    issue {
      id
      identifier
      title
      url
      priority
      state { id name }
    }
  }
}
"""

_UPDATE_ISSUE_MUTATION = """
mutation($issueId: String!, $title: String, $description: String, $stateId: String, $priority: Int) {
  issueUpdate(id: $issueId, input: {
    title: $title,
    description: $description,
    stateId: $stateId,
    priority: $priority
  }) {
    success
    issue {
      id
      identifier
      title
      url
      priority
      state { id name }
    }
  }
}
"""

_SEARCH_ISSUES_QUERY = """
query($query: String!, $limit: Int) {
  issueSearch(query: $query, first: $limit) {
    nodes {
      id
      identifier
      title
      url
      priority
      state { id name }
      team { id name }
    }
  }
}
"""

_LIST_PROJECTS_QUERY = """
query($limit: Int, $teamId: String) {
  projects(first: $limit, filter: {team: {id: {eq: $teamId}}}) {
    nodes {
      id
      name
      description
      url
      state
      progress
      team { id name }
    }
  }
}
"""


class LinearAdapter(BaseIntegrationAdapter):
    """Adapter for Linear actions using a stored API key / OAuth token.

    Linear uses a GraphQL API (there is no REST API).  All actions POST to
    ``https://api.linear.app/graphql`` with parameterised queries to avoid
    injection.

    Actions:
        - ``create_issue``: Create a new issue in a team.
        - ``update_issue``: Update an existing issue.
        - ``search_issues``: Search issues across teams.
        - ``list_projects``: List projects (optionally scoped to a team).
    """

    provider = "linear"

    # ── Action dispatch ────────────────────────────────────────────────────

    async def _execute_action(
        self,
        action: str,
        params: dict[str, Any],
        access_token: str,
    ) -> dict[str, Any]:
        match action:
            case "create_issue":
                return await self._create_issue(params, access_token)
            case "update_issue":
                return await self._update_issue(params, access_token)
            case "search_issues":
                return await self._search_issues(params, access_token)
            case "list_projects":
                return await self._list_projects(params, access_token)
            case _:
                return {
                    "success": False,
                    "error": f"Unknown Linear action: {action}",
                }

    # ── GraphQL helper ─────────────────────────────────────────────────────

    @staticmethod
    async def _graphql(
        query: str,
        variables: dict,
        access_token: str,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Execute a GraphQL query against the Linear API.

        Linear uses ``Authorization: <token>`` (no ``Bearer`` prefix).
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                LINEAR_API_URL,
                json={"query": query, "variables": variables},
                headers={
                    "Authorization": access_token,
                    "Content-Type": "application/json",
                },
            )
            return _parse_linear_response(resp)

    # ── Action: create_issue ───────────────────────────────────────────────

    async def _create_issue(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Create an issue in a Linear team.

        Required params: ``team_id``, ``title``
        Optional params: ``description``, ``priority`` (1-4), ``assignee_id``
        """
        team_id = params.get("team_id")
        title = params.get("title")

        if not team_id:
            return {"success": False, "error": "Missing required param: team_id"}
        if not title:
            return {"success": False, "error": "Missing required param: title"}

        variables: dict = {
            "teamId": team_id,
            "title": title,
            "description": params.get("description"),
            "priority": params.get("priority"),
            "assigneeId": params.get("assignee_id"),
        }
        # Strip None values so Linear uses its defaults
        variables = {k: v for k, v in variables.items() if v is not None}

        result = await self._graphql(_CREATE_ISSUE_MUTATION, variables, access_token)
        return _unwrap_mutation(result, "issueCreate")

    # ── Action: update_issue ───────────────────────────────────────────────

    async def _update_issue(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Update an existing Linear issue.

        Required params: ``issue_id``
        Optional params: ``title``, ``description``, ``status``
        (state ID), ``priority`` (1-4).
        """
        issue_id = params.get("issue_id")
        if not issue_id:
            return {"success": False, "error": "Missing required param: issue_id"}

        # At least one updatable field must be provided
        updatable = {"title", "description", "status", "priority"}
        provided = {k for k, v in params.items() if v is not None and k in updatable}
        if not provided:
            return {
                "success": False,
                "error": "At least one updatable field is required (title, description, status, priority)",
            }

        variables: dict = {
            "issueId": issue_id,
            "title": params.get("title"),
            "description": params.get("description"),
            "stateId": params.get("status"),
            "priority": params.get("priority"),
        }
        variables = {k: v for k, v in variables.items() if v is not None}

        result = await self._graphql(_UPDATE_ISSUE_MUTATION, variables, access_token)
        return _unwrap_mutation(result, "issueUpdate")

    # ── Action: search_issues ──────────────────────────────────────────────

    async def _search_issues(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Search for issues across Linear teams.

        Required params: ``query``
        Optional params: ``limit`` (default 20, max 50)
        """
        query = params.get("query")
        if not query:
            return {"success": False, "error": "Missing required param: query"}

        limit = min(int(params.get("limit", 20)), 50)

        return await self._graphql(
            _SEARCH_ISSUES_QUERY,
            {"query": query, "limit": limit},
            access_token,
        )

    # ── Action: list_projects ──────────────────────────────────────────────

    async def _list_projects(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """List Linear projects, optionally scoped to a team.

        Optional params: ``team_id``, ``limit`` (default 25, max 50)
        """
        limit = min(int(params.get("limit", 25)), 50)
        team_id = params.get("team_id")

        return await self._graphql(
            _LIST_PROJECTS_QUERY,
            {"limit": limit, "teamId": team_id},
            access_token,
        )


# ── Response helpers ──────────────────────────────────────────────────────────


def _parse_linear_response(resp: httpx.Response) -> dict[str, Any]:
    """Parse a Linear GraphQL response and return a structured result.

    Linear always returns HTTP 200 — errors appear inside the JSON
    ``errors`` array.
    """
    try:
        data = resp.json()
    except Exception:
        return {
            "success": False,
            "error": f"Linear returned non-JSON response (HTTP {resp.status_code})",
        }

    if resp.status_code >= 400:
        error_msg = data.get("message", f"Linear API error (HTTP {resp.status_code})")
        if resp.status_code == 401:
            return {
                "success": False,
                "error": "token_expired",
                "error_detail": error_msg,
            }
        return {
            "success": False,
            "error": error_msg,
            "error_code": f"http_{resp.status_code}",
        }

    # GraphQL-level errors
    graphql_errors = data.get("errors", [])
    if graphql_errors:
        first = graphql_errors[0]
        msg = first.get("message", "Unknown GraphQL error")
        extensions = first.get("extensions", {})
        code = extensions.get(
            "code", first.get("extensions", {}).get("type", "graphql_error")
        )

        # Detect auth / not-found errors
        err_str = str(first).lower()
        if (
            "authentication" in err_str
            or "unauthorized" in err_str
            or "auth" in err_str
        ):
            return {"success": False, "error": "token_expired", "error_detail": msg}

        return {
            "success": False,
            "error": msg,
            "error_code": _linear_error_code(code, msg),
        }

    return {
        "success": True,
        "response": data.get("data", data),
    }


def _unwrap_mutation(result: dict[str, Any], operation: str) -> dict[str, Any]:
    """Unwrap a Linear mutation response.

    Linear mutations return ``{ operation: { success: bool, issue: {...} } }``.
    This helper normalises that into the standard result shape.
    """
    if not result.get("success"):
        return result

    data = result.get("response", {})
    payload = data.get(operation, {}) if isinstance(data, dict) else {}

    if not payload.get("success"):
        return {
            "success": False,
            "error": f"Linear {operation} mutation failed",
            "response": data,
        }

    return {
        "success": True,
        "response": payload.get("issue") or payload,
    }


def _linear_error_code(code: str, message: str) -> str:
    """Distill a stable error code from Linear's GraphQL error response."""
    known: dict = {
        "not_found": "not_found",
        "notFound": "not_found",
        "validation_error": "validation_error",
        "ValidationError": "validation_error",
        "rate_limited": "rate_limited",
        "RATELIMITED": "rate_limited",
        "feature_not_available": "feature_unavailable",
    }

    code_lower = str(code).lower()
    msg_lower = message.lower()

    for key, value in sorted(known.items(), key=lambda x: len(x[0]), reverse=True):
        if key.lower() in code_lower or key.lower() in msg_lower:
            return value

    return code
