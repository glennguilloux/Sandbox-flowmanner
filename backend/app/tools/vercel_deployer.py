"""
Vercel Deployer — Agent-callable tool for Vercel deployment management.

vercel_deployer → trigger deployments, check build status, and manage Vercel projects via REST API.
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

VERCEL_TOKEN = os.getenv("VERCEL_TOKEN", os.getenv("VERCEL_API_TOKEN", ""))
VERCEL_TEAM_ID = os.getenv("VERCEL_TEAM_ID", "")
VERCEL_API_BASE = "https://api.vercel.com"
DEFAULT_TIMEOUT = int(os.getenv("VERCEL_HTTP_TIMEOUT", "30"))


VERCEL_ACTIONS: tuple[str, ...] = (
    "trigger_deployment",
    "get_deployment_status",
    "list_deployments",
    "cancel_deployment",
    "get_project_info",
    "list_projects",
    "get_deployment_events",
)


# ── Input ───────────────────────────────────────────────────────────

class VercelDeployerInput(ToolInput):
    action: str = Field(
        ...,
        description=(
            "Vercel operation: 'trigger_deployment', 'get_deployment_status', "
            "'list_deployments', 'cancel_deployment', 'get_project_info', "
            "'list_projects', 'get_deployment_events'"
        ),
    )
    project_id: str | None = Field(
        None,
        description="Vercel project ID or name. Required for trigger_deployment, get_project_info, and list_deployments.",
    )
    deployment_id: str | None = Field(
        None,
        description="Deployment ID for get_deployment_status, cancel_deployment, or get_deployment_events.",
    )
    target: str | None = Field(
        "production",
        description="Deployment target: 'production', 'preview', or 'development' (default: production).",
    )
    git_source: dict[str, str] | None = Field(
        None,
        description="Git source for trigger_deployment: {'ref': 'main', 'repo_id': '...'}.",
    )
    max_results: int | None = Field(
        10,
        description="Maximum number of deployments/projects to return (default: 10, max: 100).",
    )
    state_filter: str | None = Field(
        None,
        description="Filter by deployment state: 'BUILDING', 'READY', 'ERROR', 'CANCELED'.",
    )
    env_vars: dict[str, str] | None = Field(
        None,
        description="Environment variables to set for trigger_deployment.",
    )


# ── Tool ────────────────────────────────────────────────────────────

class VercelDeployerTool(BaseTool):
    """Trigger and manage Vercel deployments via the REST API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="vercel_deployer",
            name="Vercel Deployer",
            description=(
                "Trigger Vercel deployments, check build/deployment status, list projects "
                "and deployments, cancel builds, and view deployment events. "
                "Requires VERCEL_TOKEN env var (get yours at vercel.com/account/tokens)."
            ),
            category="developer-tools",
            input_schema=VercelDeployerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "result": {"type": "object"},
                },
            },
            tags=["vercel", "deploy", "ci-cd", "hosting", "developer"],
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = VercelDeployerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(self.tool_id, f"Invalid input: {e}")

        if not VERCEL_TOKEN:
            return ToolResult.error_result(
                self.tool_id,
                "VERCEL_TOKEN env var not set. Get a token at https://vercel.com/account/tokens "
                "and set it as VERCEL_TOKEN.",
            )

        if validated.action not in VERCEL_ACTIONS:
            return ToolResult.error_result(
                self.tool_id,
                f"Unknown action '{validated.action}'. Use one of: {', '.join(VERCEL_ACTIONS)}",
            )

        result = await self._execute_action(validated)
        return ToolResult.success_result(self.tool_id, result)

    # ── helpers ────────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {VERCEL_TOKEN}",
            "Content-Type": "application/json",
        }

    def _team_params(self) -> dict[str, str]:
        """Include team_id query param if configured."""
        params: dict[str, str] = {}
        if VERCEL_TEAM_ID:
            params["teamId"] = VERCEL_TEAM_ID
        return params

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> httpx.Response:
        url = f"{VERCEL_API_BASE}{path}"
        all_params = {**self._team_params(), **(params or {})}

        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(
                method, url, json=json_data, params=all_params, headers=self._auth_headers()
            )

    def _summarize_deployment(self, dep: dict[str, Any]) -> dict[str, Any]:
        """Extract key fields from a deployment object."""
        return {
            "uid": dep.get("uid"),
            "name": dep.get("name"),
            "url": dep.get("url") or f"https://{dep.get('url', '')}",
            "state": dep.get("state"),
            "target": dep.get("target"),
            "ready_state": dep.get("readyState"),
            "created_at": dep.get("created"),
            "ready_at": dep.get("ready"),
            "inspector_url": dep.get("inspectorUrl"),
        }

    def _summarize_project(self, proj: dict[str, Any]) -> dict[str, Any]:
        """Extract key fields from a project object."""
        return {
            "id": proj.get("id"),
            "name": proj.get("name"),
            "framework": proj.get("framework"),
            "latest_deployments": [
                {
                    "url": d.get("url"),
                    "target": d.get("target"),
                    "state": d.get("state"),
                }
                for d in (proj.get("latestDeployments") or [])[:3]
            ],
            "updated_at": proj.get("updatedAt"),
        }

    # ── actions ────────────────────────────────────────────────────

    async def _execute_action(self, v: VercelDeployerInput) -> dict[str, Any]:
        action = v.action
        if action == "trigger_deployment":
            return await self._trigger_deployment(v)
        elif action == "get_deployment_status":
            return await self._get_deployment_status(v)
        elif action == "list_deployments":
            return await self._list_deployments(v)
        elif action == "cancel_deployment":
            return await self._cancel_deployment(v)
        elif action == "get_project_info":
            return await self._get_project_info(v)
        elif action == "list_projects":
            return await self._list_projects(v)
        elif action == "get_deployment_events":
            return await self._get_deployment_events(v)
        return {"error": f"Action '{action}' not implemented"}

    async def _trigger_deployment(self, v: VercelDeployerInput) -> dict[str, Any]:
        if not v.project_id:
            return {"action": "trigger_deployment", "error": "project_id is required"}

        payload: dict[str, Any] = {
            "name": v.project_id,
            "target": v.target or "production",
        }

        if v.git_source:
            payload["gitSource"] = {
                "ref": v.git_source.get("ref", "main"),
                "repoId": v.git_source.get("repo_id", ""),
                "type": "github",
            }
            # If git source provided, set the project for git-based deployment
            payload["projectSettings"] = {"framework": None}

        if v.env_vars:
            payload["env"] = {
                k: {"value": val, "type": "plain"}
                for k, val in (v.env_vars or {}).items()
            }

        resp = await self._request(
            "POST",
            "/v13/deployments",
            json_data=payload,
        )

        if resp.status_code >= 400:
            error_body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            return {
                "action": "trigger_deployment",
                "error": f"Vercel API error {resp.status_code}: {error_body.get('error', {}).get('message', resp.text[:500])}",
            }

        data = resp.json()
        return {
            "action": "trigger_deployment",
            "deployment": self._summarize_deployment(data),
            "project_id": v.project_id,
            "target": v.target,
        }

    async def _get_deployment_status(self, v: VercelDeployerInput) -> dict[str, Any]:
        if not v.deployment_id:
            return {"action": "get_deployment_status", "error": "deployment_id is required"}

        resp = await self._request("GET", f"/v13/deployments/{v.deployment_id}")

        if resp.status_code >= 400:
            return {
                "action": "get_deployment_status",
                "error": f"Vercel API error {resp.status_code}: {resp.text[:500]}",
            }

        return {
            "action": "get_deployment_status",
            "deployment": self._summarize_deployment(resp.json()),
        }

    async def _list_deployments(self, v: VercelDeployerInput) -> dict[str, Any]:
        if not v.project_id:
            return {"action": "list_deployments", "error": "project_id is required"}

        params: dict[str, Any] = {
            "limit": min(v.max_results or 10, 100),
        }
        if v.state_filter:
            params["state"] = v.state_filter
        if v.target:
            params["target"] = v.target

        resp = await self._request(
            "GET",
            f"/v6/deployments",
            params={"projectId": v.project_id, **params},
        )

        if resp.status_code >= 400:
            return {
                "action": "list_deployments",
                "error": f"Vercel API error {resp.status_code}: {resp.text[:500]}",
            }

        data = resp.json()
        deployments = data.get("deployments", []) if isinstance(data, dict) else []

        return {
            "action": "list_deployments",
            "project_id": v.project_id,
            "filters": {"state": v.state_filter, "target": v.target},
            "deployments": [self._summarize_deployment(d) for d in deployments],
            "count": len(deployments),
            "pagination": data.get("pagination") if isinstance(data, dict) else None,
        }

    async def _cancel_deployment(self, v: VercelDeployerInput) -> dict[str, Any]:
        if not v.deployment_id:
            return {"action": "cancel_deployment", "error": "deployment_id is required"}

        resp = await self._request(
            "PATCH",
            f"/v12/deployments/{v.deployment_id}/cancel",
        )

        if resp.status_code >= 400:
            return {
                "action": "cancel_deployment",
                "error": f"Vercel API error {resp.status_code}: {resp.text[:500]}",
            }

        return {
            "action": "cancel_deployment",
            "deployment_id": v.deployment_id,
            "cancelled": True,
            "deployment": self._summarize_deployment(resp.json()),
        }

    async def _get_project_info(self, v: VercelDeployerInput) -> dict[str, Any]:
        if not v.project_id:
            return {"action": "get_project_info", "error": "project_id is required"}

        resp = await self._request("GET", f"/v9/projects/{v.project_id}")

        if resp.status_code >= 400:
            return {
                "action": "get_project_info",
                "error": f"Vercel API error {resp.status_code}: {resp.text[:500]}",
            }

        return {
            "action": "get_project_info",
            "project": self._summarize_project(resp.json()),
        }

    async def _list_projects(self, v: VercelDeployerInput) -> dict[str, Any]:
        params: dict[str, Any] = {
            "limit": min(v.max_results or 10, 100),
        }

        resp = await self._request("GET", "/v9/projects", params=params)

        if resp.status_code >= 400:
            return {
                "action": "list_projects",
                "error": f"Vercel API error {resp.status_code}: {resp.text[:500]}",
            }

        data = resp.json()
        projects = data.get("projects", []) if isinstance(data, dict) else []

        return {
            "action": "list_projects",
            "projects": [self._summarize_project(p) for p in projects],
            "count": len(projects),
            "pagination": data.get("pagination") if isinstance(data, dict) else None,
        }

    async def _get_deployment_events(self, v: VercelDeployerInput) -> dict[str, Any]:
        if not v.deployment_id:
            return {"action": "get_deployment_events", "error": "deployment_id is required"}

        resp = await self._request(
            "GET",
            f"/v2/deployments/{v.deployment_id}/events",
        )

        if resp.status_code >= 400:
            return {
                "action": "get_deployment_events",
                "error": f"Vercel API error {resp.status_code}: {resp.text[:500]}",
            }

        events = resp.json() if isinstance(resp.json(), list) else resp.json().get("events", [])
        # Summarize to most recent + key event types
        summarized: list[dict[str, Any]] = []
        for e in events[:50]:
            summarized.append({
                "type": e.get("type"),
                "created": e.get("created"),
                "text": (e.get("payload", {}).get("text", "") or "")[:200],
                "info": e.get("payload", {}).get("info", {}) if e.get("payload") else None,
            })

        return {
            "action": "get_deployment_events",
            "deployment_id": v.deployment_id,
            "events": summarized,
            "event_count": len(summarized),
        }


# ── Register ────────────────────────────────────────────────────────

register_tool(VercelDeployerTool())
