"""GitHub integration adapter — 4 actions using the GitHub REST API v3."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.integrations.adapters.base import BaseIntegrationAdapter

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_ACCEPT = "application/vnd.github.v3+json"


class GitHubAdapter(BaseIntegrationAdapter):
    """Adapter for GitHub actions using stored OAuth / personal access tokens.

    Actions:
        - ``create_issue``: Create a new issue in a repository.
        - ``create_pr``: Create a new pull request.
        - ``search_repos``: Search public/private repositories.
        - ``get_file_contents``: Retrieve file contents from a repo.
    """

    provider = "github"

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
            case "create_pr":
                return await self._create_pr(params, access_token)
            case "search_repos":
                return await self._search_repos(params, access_token)
            case "get_file_contents":
                return await self._get_file_contents(params, access_token)
            case _:
                return {
                    "success": False,
                    "error": f"Unknown GitHub action: {action}",
                }

    # ── Headers helper ─────────────────────────────────────────────────────

    @staticmethod
    def _headers(access_token: str, extra: dict | None = None) -> dict:
        h = {
            "Authorization": f"Bearer {access_token}",
            "Accept": GITHUB_ACCEPT,
        }
        if extra:
            h.update(extra)
        return h

    # ── Action: create_issue ───────────────────────────────────────────────

    async def _create_issue(self, params: dict[str, Any], access_token: str) -> dict[str, Any]:
        """Create an issue in a GitHub repository.

        Required params: ``owner``, ``repo``, ``title``
        Optional params: ``body``, ``labels`` (list of strings)
        """
        owner = params.get("owner")
        repo = params.get("repo")
        title = params.get("title")

        if not owner:
            return {"success": False, "error": "Missing required param: owner"}
        if not repo:
            return {"success": False, "error": "Missing required param: repo"}
        if not title:
            return {"success": False, "error": "Missing required param: title"}

        body: dict = {"title": title}
        if params.get("body"):
            body["body"] = params["body"]
        if params.get("labels") and isinstance(params["labels"], list):
            body["labels"] = params["labels"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
                json=body,
                headers=self._headers(access_token),
            )
            return _parse_github_response(resp)

    # ── Action: create_pr ──────────────────────────────────────────────────

    async def _create_pr(self, params: dict[str, Any], access_token: str) -> dict[str, Any]:
        """Create a pull request.

        Required params: ``owner``, ``repo``, ``title``, ``head``, ``base``
        Optional params: ``body``
        """
        owner = params.get("owner")
        repo = params.get("repo")
        title = params.get("title")
        head = params.get("head")
        base = params.get("base")

        if not owner:
            return {"success": False, "error": "Missing required param: owner"}
        if not repo:
            return {"success": False, "error": "Missing required param: repo"}
        if not title:
            return {"success": False, "error": "Missing required param: title"}
        if not head:
            return {"success": False, "error": "Missing required param: head"}
        if not base:
            return {"success": False, "error": "Missing required param: base"}

        body: dict = {
            "title": title,
            "head": head,
            "base": base,
        }
        if params.get("body"):
            body["body"] = params["body"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
                json=body,
                headers=self._headers(access_token),
            )
            return _parse_github_response(resp)

    # ── Action: search_repos ───────────────────────────────────────────────

    async def _search_repos(self, params: dict[str, Any], access_token: str) -> dict[str, Any]:
        """Search repositories on GitHub.

        Required params: ``query``
        Optional params: ``sort`` (stars, forks, updated), ``limit`` (default 30, max 100)
        """
        query = params.get("query")
        if not query:
            return {"success": False, "error": "Missing required param: query"}

        sort = params.get("sort")  # stars, forks, updated
        limit = min(int(params.get("limit", 30)), 100)

        query_params: dict = {"q": query, "per_page": limit}
        if sort and sort in ("stars", "forks", "updated"):
            query_params["sort"] = sort

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/search/repositories",
                params=query_params,
                headers=self._headers(access_token),
            )
            return _parse_github_response(resp)

    # ── Action: get_file_contents ──────────────────────────────────────────

    async def _get_file_contents(self, params: dict[str, Any], access_token: str) -> dict[str, Any]:
        """Retrieve file contents from a GitHub repository.

        Required params: ``owner``, ``repo``, ``path``
        Optional params: ``ref`` (branch/tag/commit SHA)
        """
        owner = params.get("owner")
        repo = params.get("repo")
        path = params.get("path")

        if not owner:
            return {"success": False, "error": "Missing required param: owner"}
        if not repo:
            return {"success": False, "error": "Missing required param: repo"}
        if not path:
            return {"success": False, "error": "Missing required param: path"}

        query_params: dict = {}
        if params.get("ref"):
            query_params["ref"] = params["ref"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}",
                params=query_params,
                headers=self._headers(access_token),
            )
            return _parse_github_response(resp)


# ── Response parser ───────────────────────────────────────────────────────────


def _parse_github_response(resp: httpx.Response) -> dict[str, Any]:
    """Parse a GitHub API response and return a structured result."""
    try:
        data = resp.json()
    except Exception:
        return {
            "success": False,
            "error": f"GitHub returned non-JSON response (HTTP {resp.status_code})",
        }

    if resp.status_code < 400:
        return {
            "success": True,
            "response": data,
        }

    # GitHub error — extract a clear error message
    error_msg = data.get("message", f"GitHub API error (HTTP {resp.status_code})")
    error_code = _github_error_code(resp.status_code, error_msg)

    # Detect auth errors for token refresh
    if resp.status_code == 401:
        return {"success": False, "error": "token_expired", "error_detail": error_msg}

    return {
        "success": False,
        "error": error_msg,
        "error_code": error_code,
    }


def _github_error_code(status: int, message: str) -> str:
    """Distill a stable error code from GitHub's response."""
    # Known GitHub error messages
    known = {
        "Not Found": "not_found",
        "Bad credentials": "bad_credentials",
        "Validation Failed": "validation_failed",
        "Resource not accessible by integration": "forbidden",
        "Repository access blocked": "blocked",
        "Merge conflict": "merge_conflict",
    }
    for key, code in known.items():
        if key.lower() in message.lower():
            return code
    return f"http_{status}"
