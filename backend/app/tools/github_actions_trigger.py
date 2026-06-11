"""
GitHub Actions Trigger — Agent-callable tool for CI/CD workflow management.

github_actions_trigger → trigger, list, and monitor GitHub Actions workflow runs.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", os.getenv("GITHUB_ACCESS_TOKEN", ""))
GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = int(os.getenv("GITHUB_HTTP_TIMEOUT", "30"))


ACTIONS: tuple[str, ...] = (
    "trigger_workflow",
    "list_workflows",
    "get_run_status",
    "list_runs",
    "cancel_run",
    "rerun_failed_jobs",
    "get_run_logs",
)


# ── Input ───────────────────────────────────────────────────────────


class GithubActionsTriggerInput(ToolInput):
    action: str = Field(
        ...,
        description=(
            "GitHub Actions operation: 'trigger_workflow', 'list_workflows', "
            "'get_run_status', 'list_runs', 'cancel_run', 'rerun_failed_jobs', 'get_run_logs'"
        ),
    )
    owner: str = Field(
        ...,
        description="GitHub repository owner (username or org).",
    )
    repo: str = Field(
        ...,
        description="GitHub repository name.",
    )
    workflow_id: str | None = Field(
        None,
        description="Workflow file name (e.g., 'ci.yml') or workflow ID for trigger_workflow / list runs.",
    )
    ref: str | None = Field(
        "main",
        description="Branch or tag ref to trigger workflow on (default: main).",
    )
    inputs: dict[str, str] | None = Field(
        None,
        description="Workflow input parameters (key-value pairs) for trigger_workflow.",
    )
    run_id: str | None = Field(
        None,
        description="Run ID for get_run_status, cancel_run, rerun_failed_jobs, or get_run_logs.",
    )
    max_runs: int | None = Field(
        10,
        description="Maximum number of runs to return for list_runs.",
    )
    status_filter: str | None = Field(
        None,
        description="Filter runs by status for list_runs (e.g., 'completed', 'in_progress', 'failure').",
    )


# ── Tool ────────────────────────────────────────────────────────────


class GithubActionsTriggerTool(BaseTool):
    """Trigger and monitor GitHub Actions workflows via the REST API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="github_actions_trigger",
            name="GitHub Actions Trigger",
            description=(
                "Trigger and monitor GitHub Actions workflows. Supports triggering "
                "workflow dispatches, listing workflows and runs, checking run status, "
                "canceling runs, and viewing logs. Requires GITHUB_TOKEN env var."
            ),
            category="developer-tools",
            input_schema=GithubActionsTriggerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "result": {"type": "object"},
                },
            },
            tags=["github", "ci-cd", "workflow", "devops", "developer"],
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = GithubActionsTriggerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(self.tool_id, f"Invalid input: {e}")

        if not GITHUB_TOKEN:
            return ToolResult.error_result(
                self.tool_id,
                "GITHUB_TOKEN env var not set. Set your GitHub personal access token "
                "with 'workflow' and 'repo' scopes.",
            )

        if validated.action not in ACTIONS:
            return ToolResult.error_result(
                self.tool_id,
                f"Unknown action '{validated.action}'. Use one of: {', '.join(ACTIONS)}",
            )

        result = await self._execute_action(validated)
        return ToolResult.success_result(self.tool_id, result)

    # ── helpers ────────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _workflow_url(self, owner: str, repo: str, workflow_id: str | None = None) -> str:
        base = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/actions"
        if workflow_id:
            return f"{base}/workflows/{workflow_id}"
        return f"{base}/workflows"

    def _runs_url(self, owner: str, repo: str, run_id: str | None = None) -> str:
        base = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/actions/runs"
        if run_id:
            return f"{base}/{run_id}"
        return base

    def _summarize_run(self, run: dict[str, Any]) -> dict[str, Any]:
        """Extract key fields from a workflow run object."""
        return {
            "id": run.get("id"),
            "name": run.get("name"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "html_url": run.get("html_url"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "head_branch": run.get("head_branch"),
            "head_sha": (run.get("head_sha", "") or "")[:8],
            "event": run.get("event"),
            "run_attempt": run.get("run_attempt"),
        }

    def _summarize_workflow(self, wf: dict[str, Any]) -> dict[str, Any]:
        """Extract key fields from a workflow object."""
        return {
            "id": wf.get("id"),
            "name": wf.get("name"),
            "path": wf.get("path"),
            "state": wf.get("state"),
            "html_url": wf.get("html_url"),
            "created_at": wf.get("created_at"),
            "updated_at": wf.get("updated_at"),
        }

    # ── actions ────────────────────────────────────────────────────

    async def _execute_action(self, v: GithubActionsTriggerInput) -> dict[str, Any]:
        action = v.action
        if action == "trigger_workflow":
            return await self._trigger_workflow(v)
        elif action == "list_workflows":
            return await self._list_workflows(v)
        elif action == "get_run_status":
            return await self._get_run_status(v)
        elif action == "list_runs":
            return await self._list_runs(v)
        elif action == "cancel_run":
            return await self._cancel_run(v)
        elif action == "rerun_failed_jobs":
            return await self._rerun_failed_jobs(v)
        elif action == "get_run_logs":
            return await self._get_run_logs(v)
        return {"error": f"Action '{action}' not implemented"}

    async def _trigger_workflow(self, v: GithubActionsTriggerInput) -> dict[str, Any]:
        if not v.workflow_id:
            return {
                "action": "trigger_workflow",
                "error": "workflow_id is required (file name or ID)",
            }

        url = f"{self._workflow_url(v.owner, v.repo, v.workflow_id)}/dispatches"
        payload: dict[str, Any] = {"ref": v.ref or "main"}
        if v.inputs:
            payload["inputs"] = v.inputs

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=self._auth_headers())

        if resp.status_code == 204:
            return {
                "action": "trigger_workflow",
                "workflow_id": v.workflow_id,
                "ref": v.ref,
                "triggered": True,
                "note": "Workflow dispatch triggered. Use list_runs to monitor.",
            }

        if resp.status_code == 404:
            return {
                "action": "trigger_workflow",
                "error": f"Workflow '{v.workflow_id}' not found. Does it have a workflow_dispatch trigger?",
                "status_code": 404,
            }

        return {
            "action": "trigger_workflow",
            "error": f"GitHub API error {resp.status_code}: {resp.text[:500]}",
        }

    async def _list_workflows(self, v: GithubActionsTriggerInput) -> dict[str, Any]:
        url = self._workflow_url(v.owner, v.repo)

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=self._auth_headers())

        if resp.status_code >= 400:
            return {
                "action": "list_workflows",
                "error": f"GitHub API error {resp.status_code}: {resp.text[:500]}",
            }

        data = resp.json()
        workflows = data.get("workflows", []) if isinstance(data, dict) else data

        return {
            "action": "list_workflows",
            "owner": v.owner,
            "repo": v.repo,
            "workflows": [self._summarize_workflow(w) for w in workflows],
            "total_count": len(workflows),
        }

    async def _get_run_status(self, v: GithubActionsTriggerInput) -> dict[str, Any]:
        if not v.run_id:
            return {"action": "get_run_status", "error": "run_id is required"}

        url = self._runs_url(v.owner, v.repo, v.run_id)

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=self._auth_headers())

        if resp.status_code >= 400:
            return {
                "action": "get_run_status",
                "error": f"GitHub API error {resp.status_code}: {resp.text[:500]}",
            }

        return {
            "action": "get_run_status",
            "run": self._summarize_run(resp.json()),
        }

    async def _list_runs(self, v: GithubActionsTriggerInput) -> dict[str, Any]:
        url = self._runs_url(v.owner, v.repo)
        params: dict[str, Any] = {"per_page": min(v.max_runs or 10, 100)}
        if v.workflow_id:
            params["workflow_id"] = v.workflow_id
        if v.status_filter:
            params["status"] = v.status_filter
        if v.ref:
            params["branch"] = v.ref

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=self._auth_headers())

        if resp.status_code >= 400:
            return {
                "action": "list_runs",
                "error": f"GitHub API error {resp.status_code}: {resp.text[:500]}",
            }

        data = resp.json()
        runs = data.get("workflow_runs", []) if isinstance(data, dict) else data

        return {
            "action": "list_runs",
            "owner": v.owner,
            "repo": v.repo,
            "filters": {
                "workflow_id": v.workflow_id,
                "status": v.status_filter,
                "branch": v.ref,
            },
            "runs": [self._summarize_run(r) for r in runs],
            "total_count": len(runs),
        }

    async def _cancel_run(self, v: GithubActionsTriggerInput) -> dict[str, Any]:
        if not v.run_id:
            return {"action": "cancel_run", "error": "run_id is required"}

        url = f"{self._runs_url(v.owner, v.repo, v.run_id)}/cancel"

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, headers=self._auth_headers())

        if resp.status_code == 202:
            return {
                "action": "cancel_run",
                "run_id": v.run_id,
                "cancelled": True,
            }

        return {
            "action": "cancel_run",
            "error": f"GitHub API error {resp.status_code}: {resp.text[:500]}",
        }

    async def _rerun_failed_jobs(self, v: GithubActionsTriggerInput) -> dict[str, Any]:
        if not v.run_id:
            return {"action": "rerun_failed_jobs", "error": "run_id is required"}

        url = f"{self._runs_url(v.owner, v.repo, v.run_id)}/rerun-failed-jobs"

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, headers=self._auth_headers())

        if resp.status_code == 201:
            return {
                "action": "rerun_failed_jobs",
                "run_id": v.run_id,
                "rerun_triggered": True,
            }

        return {
            "action": "rerun_failed_jobs",
            "error": f"GitHub API error {resp.status_code}: {resp.text[:500]}",
        }

    async def _get_run_logs(self, v: GithubActionsTriggerInput) -> dict[str, Any]:
        if not v.run_id:
            return {"action": "get_run_logs", "error": "run_id is required"}

        url = f"{self._runs_url(v.owner, v.repo, v.run_id)}/logs"

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=False) as client:
            resp = await client.get(url, headers=self._auth_headers())
            if resp.status_code in (302, 307):
                # Logs are available as a zip download URL
                return {
                    "action": "get_run_logs",
                    "run_id": v.run_id,
                    "log_download_url": resp.headers.get("Location", ""),
                    "note": "Logs are available at the download URL. The URL expires after 1 minute.",
                }
            elif resp.status_code == 200:
                return {
                    "action": "get_run_logs",
                    "run_id": v.run_id,
                    "logs_raw": resp.text[:50000],  # truncate large logs
                    "truncated": len(resp.text) > 50000,
                }

        return {
            "action": "get_run_logs",
            "error": f"GitHub API error {resp.status_code}: {resp.text[:500]}",
        }


# ── Register ────────────────────────────────────────────────────────

register_tool(GithubActionsTriggerTool())
