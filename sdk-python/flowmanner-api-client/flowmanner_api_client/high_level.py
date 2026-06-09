"""High-level convenience wrapper for the Flowmanner API.

Usage:
    from flowmanner_api_client import FlowmannerClient

    with FlowmannerClient(base_url="https://flowmanner.com", api_key="sk-...") as fm:
        mission = fm.create_mission(title="My Mission")
        fm.execute_mission(mission["id"])
        print(fm.get_mission_status(mission["id"]))
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from .client import AuthenticatedClient


class FlowmannerError(Exception):
    """Raised when an API call fails or returns an unexpected response."""


class FlowmannerClient:
    """High-level client for the Flowmanner API.

    Args:
        base_url: The base URL of the Flowmanner instance (e.g. "https://flowmanner.com").
        api_key: API key for authentication. Falls back to FLOWMANNER_API_KEY env var.
        timeout: Request timeout in seconds. Defaults to 30.
    """

    def __init__(
        self,
        base_url: str = "https://flowmanner.com",
        api_key: str | None = None,
        timeout: float = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key or os.environ.get("FLOWMANNER_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "API key required. Pass api_key= or set FLOWMANNER_API_KEY env var."
            )
        self._client = AuthenticatedClient(
            base_url=self.base_url,
            token=self._api_key,
        )
        self._client = self._client.with_timeout(httpx.Timeout(timeout))

    def __enter__(self) -> FlowmannerClient:
        self._client.__enter__()
        return self

    def __exit__(self, *args: Any) -> None:
        self._client.__exit__(*args)

    # ── Helpers ──────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> Any:
        resp = self._client.get_httpx_client().get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json: dict | None = None) -> Any:
        resp = self._client.get_httpx_client().post(path, json=json)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, json: dict | None = None) -> Any:
        resp = self._client.get_httpx_client().patch(path, json=json)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> None:
        resp = self._client.get_httpx_client().delete(path)
        resp.raise_for_status()

    # ── Missions ─────────────────────────────────────────────────────

    def create_mission(
        self,
        title: str,
        description: str = "",
        mission_type: str = "general",
        priority: str = "medium",
    ) -> dict:
        """Create a new mission."""
        return self._post(
            "/api/v1/missions",
            json={
                "title": title,
                "description": description,
                "mission_type": mission_type,
                "priority": priority,
            },
        )

    def get_mission(self, mission_id: str) -> dict:
        """Get a mission by ID."""
        return self._get(f"/api/v1/missions/{mission_id}")

    def list_missions(self, limit: int = 20, status: str | None = None) -> list[dict]:
        """List recent missions."""
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self._get("/api/v1/missions", params=params)

    def execute_mission(self, mission_id: str) -> dict:
        """Execute a mission synchronously."""
        return self._post(f"/api/v1/missions/{mission_id}/execute")

    def execute_mission_async(self, mission_id: str) -> dict:
        """Queue a mission for async execution."""
        return self._post(f"/api/v1/missions/{mission_id}/execute-async")

    def get_mission_status(self, mission_id: str) -> str:
        """Get mission status string."""
        mission = self.get_mission(mission_id)
        return mission.get("status", "unknown")

    def delete_mission(self, mission_id: str) -> None:
        """Delete a mission."""
        self._delete(f"/api/v1/missions/{mission_id}")

    # ── Mission Tasks ────────────────────────────────────────────────

    def list_tasks(self, mission_id: str) -> list[dict]:
        """List tasks for a mission."""
        return self._get(f"/api/v1/missions/{mission_id}/tasks")

    # ── Mission Logs ─────────────────────────────────────────────────

    def list_logs(self, mission_id: str) -> list[dict]:
        """List logs for a mission."""
        return self._get(f"/api/v1/missions/{mission_id}/logs")

    # ── Analytics ────────────────────────────────────────────────────

    def get_usage_summary(self, period: str = "30d") -> dict:
        """Get usage summary for the given period."""
        return self._get("/api/v1/usage/summary", params={"period": period})

    def get_cost_analytics(self, period: str = "month") -> dict:
        """Get cost analytics from v2 dashboard."""
        return self._get("/api/v2/dashboard/costs", params={"period": period})

    # ── Health ───────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """Check API health."""
        return self._get("/api/health")

    # ── Agents ───────────────────────────────────────────────────────

    def list_agents(self) -> list[dict]:
        """List available agents."""
        return self._get("/api/v1/agents")

    def get_agent(self, agent_id: str) -> dict:
        """Get an agent by ID."""
        return self._get(f"/api/v1/agents/{agent_id}")
