"""
API & SaaS Integration Tools — GitHub Manager.

github_manager → Manage repositories, fetch issues, and create pull requests.
"""

from __future__ import annotations

import logging
import os

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class GithubManagerInput(ToolInput):
    action: str = Field(
        ...,
        description="Action: 'list_repos', 'get_repo', 'list_issues', 'get_issue', "
                    "'create_issue', 'list_prs', 'create_pr', 'get_file', 'search_code'",
    )
    owner: str | None = Field(None, description="Repository owner (user or org)")
    repo: str | None = Field(None, description="Repository name")
    title: str | None = Field(None, description="Issue/PR title (for create actions)")
    body: str | None = Field(None, description="Issue/PR description body")
    labels: list[str] | None = Field(None, description="Labels for issue/PR")
    state: str = Field("open", description="Filter by state: 'open', 'closed', 'all'")
    branch: str | None = Field(None, description="Source branch (for PRs)")
    base_branch: str = Field("main", description="Target base branch")
    file_path: str | None = Field(None, description="File path for get_file action")
    query: str | None = Field(None, description="Search query for search_code")
    issue_number: int | None = Field(None, description="Issue/PR number")
    limit: int = Field(30, ge=1, le=100)
    token: str | None = Field(None, description="GitHub PAT (uses GITHUB_TOKEN env var if omitted)")


class GithubManagerTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="github_manager",
            name="GitHub Manager",
            description="Manage repositories, fetch issues, and create pull requests",
            category="api-integrations",
            input_schema=GithubManagerInput.schema_extra(),
            tags=["github", "git", "issues", "pull-requests", "integration"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = GithubManagerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        token = validated.token or os.getenv("GITHUB_TOKEN", "")
        if not token:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="No GitHub token. Set GITHUB_TOKEN env var or pass token.",
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "FlowmannerBot/1.0",
        }
        base_url = "https://api.github.com"
        action = validated.action.lower().strip()

        try:
            async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
                if action == "list_repos":
                    return await self._list_repos(client, base_url, validated)
                elif action == "get_repo":
                    return await self._get_repo(client, base_url, validated)
                elif action == "list_issues":
                    return await self._list_issues(client, base_url, validated)
                elif action == "get_issue":
                    return await self._get_issue(client, base_url, validated)
                elif action == "create_issue":
                    return await self._create_issue(client, base_url, validated)
                elif action == "list_prs":
                    return await self._list_prs(client, base_url, validated)
                elif action == "create_pr":
                    return await self._create_pr(client, base_url, validated)
                elif action == "get_file":
                    return await self._get_file(client, base_url, validated)
                elif action == "search_code":
                    return await self._search_code(client, base_url, validated)
                else:
                    return ToolResult.error_result(tool_id=self.tool_id, error=f"Unknown action: {action}")
        except Exception as e:
            logger.exception("github_manager failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _list_repos(self, client, base_url, v) -> ToolResult:
        r = await client.get(f"{base_url}/user/repos", params={"per_page": v.limit, "sort": "updated"})
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"GitHub API error: {r.status_code}")
        repos = [{"name": repo["name"], "full_name": repo["full_name"], "private": repo["private"],
                   "description": repo.get("description", ""), "url": repo["html_url"],
                   "language": repo.get("language"), "stars": repo.get("stargazers_count", 0)}
                  for repo in r.json()]
        return ToolResult.success_result(tool_id=self.tool_id, result={"action": "list_repos", "count": len(repos), "repos": repos})

    async def _get_repo(self, client, base_url, v) -> ToolResult:
        if not v.owner or not v.repo:
            return ToolResult.error_result(tool_id=self.tool_id, error="owner and repo required")
        r = await client.get(f"{base_url}/repos/{v.owner}/{v.repo}")
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"GitHub API error: {r.status_code} {r.text[:200]}")
        repo = r.json()
        return ToolResult.success_result(tool_id=self.tool_id, result={"action": "get_repo", "repo": {
            "name": repo["full_name"], "description": repo.get("description"), "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0), "open_issues": repo.get("open_issues_count", 0),
            "language": repo.get("language"), "topics": repo.get("topics", []), "url": repo["html_url"],
            "default_branch": repo.get("default_branch"),
        }})

    async def _list_issues(self, client, base_url, v) -> ToolResult:
        if not v.owner or not v.repo:
            return ToolResult.error_result(tool_id=self.tool_id, error="owner and repo required")
        r = await client.get(f"{base_url}/repos/{v.owner}/{v.repo}/issues",
                             params={"state": v.state, "per_page": v.limit})
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"GitHub API error: {r.status_code}")
        issues = [{"number": i["number"], "title": i["title"], "state": i["state"],
                    "labels": [l["name"] for l in i.get("labels", [])],
                    "url": i["html_url"], "created_at": i.get("created_at")}
                   for i in r.json()]
        return ToolResult.success_result(tool_id=self.tool_id, result={"action": "list_issues", "count": len(issues), "issues": issues})

    async def _get_issue(self, client, base_url, v) -> ToolResult:
        if not v.owner or not v.repo or not v.issue_number:
            return ToolResult.error_result(tool_id=self.tool_id, error="owner, repo, and issue_number required")
        r = await client.get(f"{base_url}/repos/{v.owner}/{v.repo}/issues/{v.issue_number}")
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"GitHub API error: {r.status_code}")
        i = r.json()
        return ToolResult.success_result(tool_id=self.tool_id, result={"action": "get_issue", "issue": {
            "number": i["number"], "title": i["title"], "body": i.get("body", ""), "state": i["state"],
            "labels": [l["name"] for l in i.get("labels", [])], "url": i["html_url"], "created_at": i.get("created_at"),
        }})

    async def _create_issue(self, client, base_url, v) -> ToolResult:
        if not v.owner or not v.repo or not v.title:
            return ToolResult.error_result(tool_id=self.tool_id, error="owner, repo, and title required")
        payload: dict = {"title": v.title}
        if v.body:
            payload["body"] = v.body
        if v.labels:
            payload["labels"] = v.labels
        r = await client.post(f"{base_url}/repos/{v.owner}/{v.repo}/issues", json=payload)
        if r.status_code not in (200, 201):
            return ToolResult.error_result(tool_id=self.tool_id, error=f"GitHub API error: {r.status_code} {r.text[:200]}")
        i = r.json()
        return ToolResult.success_result(tool_id=self.tool_id, result={"action": "create_issue", "issue": {
            "number": i["number"], "title": i["title"], "url": i["html_url"],
        }})

    async def _list_prs(self, client, base_url, v) -> ToolResult:
        if not v.owner or not v.repo:
            return ToolResult.error_result(tool_id=self.tool_id, error="owner and repo required")
        r = await client.get(f"{base_url}/repos/{v.owner}/{v.repo}/pulls",
                             params={"state": v.state, "per_page": v.limit})
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"GitHub API error: {r.status_code}")
        prs = [{"number": p["number"], "title": p["title"], "state": p["state"],
                 "url": p["html_url"], "head": p["head"]["ref"], "base": p["base"]["ref"],
                 "created_at": p.get("created_at")} for p in r.json()]
        return ToolResult.success_result(tool_id=self.tool_id, result={"action": "list_prs", "count": len(prs), "prs": prs})

    async def _create_pr(self, client, base_url, v) -> ToolResult:
        if not v.owner or not v.repo or not v.title or not v.branch:
            return ToolResult.error_result(tool_id=self.tool_id, error="owner, repo, title, and branch required")
        payload: dict = {"title": v.title, "head": v.branch, "base": v.base_branch}
        if v.body:
            payload["body"] = v.body
        r = await client.post(f"{base_url}/repos/{v.owner}/{v.repo}/pulls", json=payload)
        if r.status_code not in (200, 201):
            return ToolResult.error_result(tool_id=self.tool_id, error=f"GitHub API error: {r.status_code} {r.text[:200]}")
        p = r.json()
        return ToolResult.success_result(tool_id=self.tool_id, result={"action": "create_pr", "pr": {
            "number": p["number"], "title": p["title"], "url": p["html_url"],
        }})

    async def _get_file(self, client, base_url, v) -> ToolResult:
        if not v.owner or not v.repo or not v.file_path:
            return ToolResult.error_result(tool_id=self.tool_id, error="owner, repo, and file_path required")
        r = await client.get(f"{base_url}/repos/{v.owner}/{v.repo}/contents/{v.file_path}")
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"GitHub API error: {r.status_code}")
        f = r.json()
        import base64
        content = base64.b64decode(f.get("content", "")).decode("utf-8", errors="replace")
        return ToolResult.success_result(tool_id=self.tool_id, result={"action": "get_file", "path": v.file_path,
            "content": content, "size": f.get("size"), "url": f.get("html_url"),
        })

    async def _search_code(self, client, base_url, v) -> ToolResult:
        if not v.query:
            return ToolResult.error_result(tool_id=self.tool_id, error="query required")
        params = {"q": v.query, "per_page": min(v.limit, 30)}
        r = await client.get(f"{base_url}/search/code", params=params)
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"GitHub API error: {r.status_code}")
        data = r.json()
        items = [{"path": i["path"], "repo": i["repository"]["full_name"], "url": i["html_url"]}
                 for i in data.get("items", [])]
        return ToolResult.success_result(tool_id=self.tool_id, result={"action": "search_code",
            "query": v.query, "total_count": data.get("total_count", 0), "count": len(items), "results": items,
        })


register_tool(GithubManagerTool())
