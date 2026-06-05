"""
GitHub Connector

Provides integration with GitHub API for:
- Managing issues (create, list, get, update, close)
- Managing pull requests (create, list, get, merge)
- Repository operations (list, get info)
- Code search
- User info
"""

import logging
from typing import Any

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)


class GitHubConnector(BaseConnector):
    """
    GitHub API connector for repository, issue, and PR operations.

    Supports:
    - Issue management (create, list, get, update, close)
    - Pull request management (create, list, get, merge)
    - Repository info and listing
    - Code search
    - User profile
    """

    CONNECTOR_TYPE = "github"

    # GitHub API rate limits: 5000/hr for authenticated users
    GITHUB_RATE_LIMIT = RateLimitConfig(
        requests_per_second=2.0,
        requests_per_minute=80,
        requests_per_hour=4500,
        burst_size=10,
    )

    ACTIONS = [
        "create_issue",
        "list_issues",
        "get_issue",
        "update_issue",
        "close_issue",
        "create_pr",
        "list_prs",
        "get_pr",
        "merge_pr",
        "get_repo",
        "list_repos",
        "list_user_repos",
        "search_code",
        "search_repos",
        "get_user",
        "get_file_contents",
        "create_comment",
        "list_comments",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.github.com"
        config.auth_type = config.auth_type or AuthType.BEARER_TOKEN
        config.rate_limit = config.rate_limit or self.GITHUB_RATE_LIMIT
        config.headers = {
            **config.headers,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        super().__init__(config)
        self._authenticated_user: str | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        """Validate GitHub token by calling /user."""
        response = await self._execute_request("GET", "user")

        if response.success and response.data:
            self._authenticated_user = response.data.get("login")
            return True

        return False

    async def execute_action(
        self,
        action: str,
        params: dict[str, Any],
    ) -> ConnectorResponse:
        """Execute a GitHub action."""

        action_handlers = {
            "create_issue": self._create_issue,
            "list_issues": self._list_issues,
            "get_issue": self._get_issue,
            "update_issue": self._update_issue,
            "close_issue": self._close_issue,
            "create_pr": self._create_pr,
            "list_prs": self._list_prs,
            "get_pr": self._get_pr,
            "merge_pr": self._merge_pr,
            "get_repo": self._get_repo,
            "list_repos": self._list_repos,
            "list_user_repos": self._list_user_repos,
            "search_code": self._search_code,
            "search_repos": self._search_repos,
            "get_user": self._get_user,
            "get_file_contents": self._get_file_contents,
            "create_comment": self._create_comment,
            "list_comments": self._list_comments,
        }

        handler = action_handlers.get(action)
        if not handler:
            return ConnectorResponse(
                success=False,
                error=f"Unknown action: {action}",
                status_code=400,
            )

        return await handler(params)

    # ── Issue Actions ───────────────────────────────────────────────

    async def _create_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")
        title = params.get("title")

        if not all([owner, repo, title]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner, repo, and title",
                status_code=400,
            )

        payload: dict[str, Any] = {"title": title}
        if params.get("body"):
            payload["body"] = params["body"]
        if params.get("labels"):
            payload["labels"] = params["labels"]
        if params.get("assignees"):
            payload["assignees"] = params["assignees"]
        if params.get("milestone"):
            payload["milestone"] = params["milestone"]

        return await self._execute_with_retry(
            "POST",
            f"repos/{owner}/{repo}/issues",
            json_data=payload,
        )

    async def _list_issues(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")

        if not all([owner, repo]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner and repo",
                status_code=400,
            )

        query_params: dict[str, Any] = {"state": params.get("state", "open")}
        if params.get("labels"):
            query_params["labels"] = params["labels"]
        if params.get("assignee"):
            query_params["assignee"] = params["assignee"]
        if params.get("per_page"):
            query_params["per_page"] = params["per_page"]
        if params.get("page"):
            query_params["page"] = params["page"]

        return await self._execute_with_retry(
            "GET",
            f"repos/{owner}/{repo}/issues",
            params=query_params,
        )

    async def _get_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")
        issue_number = params.get("issue_number")

        if not all([owner, repo, issue_number]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner, repo, and issue_number",
                status_code=400,
            )

        return await self._execute_with_retry(
            "GET",
            f"repos/{owner}/{repo}/issues/{issue_number}",
        )

    async def _update_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")
        issue_number = params.get("issue_number")

        if not all([owner, repo, issue_number]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner, repo, and issue_number",
                status_code=400,
            )

        payload: dict[str, Any] = {}
        if params.get("title"):
            payload["title"] = params["title"]
        if params.get("body"):
            payload["body"] = params["body"]
        if params.get("state"):
            payload["state"] = params["state"]
        if params.get("labels") is not None:
            payload["labels"] = params["labels"]
        if params.get("assignees") is not None:
            payload["assignees"] = params["assignees"]

        return await self._execute_with_retry(
            "PATCH",
            f"repos/{owner}/{repo}/issues/{issue_number}",
            json_data=payload,
        )

    async def _close_issue(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")
        issue_number = params.get("issue_number")

        if not all([owner, repo, issue_number]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner, repo, and issue_number",
                status_code=400,
            )

        return await self._execute_with_retry(
            "PATCH",
            f"repos/{owner}/{repo}/issues/{issue_number}",
            json_data={"state": "closed"},
        )

    # ── Pull Request Actions ────────────────────────────────────────

    async def _create_pr(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")
        title = params.get("title")
        head = params.get("head")
        base = params.get("base")

        if not all([owner, repo, title, head, base]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner, repo, title, head, and base",
                status_code=400,
            )

        payload: dict[str, Any] = {
            "title": title,
            "head": head,
            "base": base,
        }
        if params.get("body"):
            payload["body"] = params["body"]
        if params.get("draft"):
            payload["draft"] = params["draft"]

        return await self._execute_with_retry(
            "POST",
            f"repos/{owner}/{repo}/pulls",
            json_data=payload,
        )

    async def _list_prs(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")

        if not all([owner, repo]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner and repo",
                status_code=400,
            )

        query_params: dict[str, Any] = {"state": params.get("state", "open")}
        if params.get("head"):
            query_params["head"] = params["head"]
        if params.get("base"):
            query_params["base"] = params["base"]
        if params.get("per_page"):
            query_params["per_page"] = params["per_page"]

        return await self._execute_with_retry(
            "GET",
            f"repos/{owner}/{repo}/pulls",
            params=query_params,
        )

    async def _get_pr(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")
        pr_number = params.get("pr_number")

        if not all([owner, repo, pr_number]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner, repo, and pr_number",
                status_code=400,
            )

        return await self._execute_with_retry(
            "GET",
            f"repos/{owner}/{repo}/pulls/{pr_number}",
        )

    async def _merge_pr(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")
        pr_number = params.get("pr_number")

        if not all([owner, repo, pr_number]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner, repo, and pr_number",
                status_code=400,
            )

        payload: dict[str, Any] = {}
        if params.get("commit_title"):
            payload["commit_title"] = params["commit_title"]
        if params.get("merge_method"):
            payload["merge_method"] = params["merge_method"]

        return await self._execute_with_retry(
            "PUT",
            f"repos/{owner}/{repo}/pulls/{pr_number}/merge",
            json_data=payload,
        )

    # ── Repository Actions ──────────────────────────────────────────

    async def _get_repo(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")

        if not all([owner, repo]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner and repo",
                status_code=400,
            )

        return await self._execute_with_retry(
            "GET",
            f"repos/{owner}/{repo}",
        )

    async def _list_repos(self, params: dict[str, Any]) -> ConnectorResponse:
        """List repositories for the authenticated user."""
        query_params: dict[str, Any] = {
            "sort": params.get("sort", "updated"),
            "per_page": params.get("per_page", 30),
        }
        if params.get("type"):
            query_params["type"] = params["type"]
        if params.get("page"):
            query_params["page"] = params["page"]

        return await self._execute_with_retry(
            "GET",
            "user/repos",
            params=query_params,
        )

    async def _list_user_repos(self, params: dict[str, Any]) -> ConnectorResponse:
        """List repositories for a specific user."""
        username = params.get("username")

        if not username:
            return ConnectorResponse(
                success=False,
                error="Missing required param: username",
                status_code=400,
            )

        query_params: dict[str, Any] = {
            "sort": params.get("sort", "updated"),
            "per_page": params.get("per_page", 30),
        }

        return await self._execute_with_retry(
            "GET",
            f"users/{username}/repos",
            params=query_params,
        )

    # ── Search Actions ──────────────────────────────────────────────

    async def _search_code(self, params: dict[str, Any]) -> ConnectorResponse:
        q = params.get("q") or params.get("query")

        if not q:
            return ConnectorResponse(
                success=False,
                error="Missing required param: q (search query)",
                status_code=400,
            )

        query_params: dict[str, Any] = {"q": q}
        if params.get("per_page"):
            query_params["per_page"] = params["per_page"]
        if params.get("page"):
            query_params["page"] = params["page"]

        return await self._execute_with_retry(
            "GET",
            "search/code",
            params=query_params,
        )

    async def _search_repos(self, params: dict[str, Any]) -> ConnectorResponse:
        q = params.get("q") or params.get("query")

        if not q:
            return ConnectorResponse(
                success=False,
                error="Missing required param: q (search query)",
                status_code=400,
            )

        query_params: dict[str, Any] = {"q": q}
        if params.get("sort"):
            query_params["sort"] = params["sort"]
        if params.get("order"):
            query_params["order"] = params["order"]
        if params.get("per_page"):
            query_params["per_page"] = params["per_page"]

        return await self._execute_with_retry(
            "GET",
            "search/repositories",
            params=query_params,
        )

    # ── User Actions ────────────────────────────────────────────────

    async def _get_user(self, params: dict[str, Any]) -> ConnectorResponse:
        username = params.get("username")

        endpoint = f"users/{username}" if username else "user"
        return await self._execute_with_retry("GET", endpoint)

    # ── Content Actions ─────────────────────────────────────────────

    async def _get_file_contents(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")
        path = params.get("path")

        if not all([owner, repo, path]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner, repo, and path",
                status_code=400,
            )

        query_params: dict[str, Any] = {}
        if params.get("ref"):
            query_params["ref"] = params["ref"]

        return await self._execute_with_retry(
            "GET",
            f"repos/{owner}/{repo}/contents/{path}",
            params=query_params,
        )

    # ── Comment Actions ─────────────────────────────────────────────

    async def _create_comment(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")
        issue_number = params.get("issue_number")
        body = params.get("body")

        if not all([owner, repo, issue_number, body]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner, repo, issue_number, and body",
                status_code=400,
            )

        return await self._execute_with_retry(
            "POST",
            f"repos/{owner}/{repo}/issues/{issue_number}/comments",
            json_data={"body": body},
        )

    async def _list_comments(self, params: dict[str, Any]) -> ConnectorResponse:
        owner = params.get("owner")
        repo = params.get("repo")
        issue_number = params.get("issue_number")

        if not all([owner, repo, issue_number]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: owner, repo, and issue_number",
                status_code=400,
            )

        return await self._execute_with_retry(
            "GET",
            f"repos/{owner}/{repo}/issues/{issue_number}/comments",
        )

    def get_stats(self) -> dict[str, Any]:
        """Get connector statistics including GitHub-specific info."""
        stats = super().get_stats()
        stats.update({"authenticated_user": self._authenticated_user})
        return stats
