"""High-level convenience wrapper for the Flowmanner API.

Provides a clean, Pythonic interface over the auto-generated low-level client.

Usage:
    from flowmanner_api_client import FlowmannerClient

    with FlowmannerClient("https://flowmanner.com", api_key="sk-...") as fm:
        mission = fm.create_mission("My Mission")
        fm.execute_mission(str(mission.id))
        status = fm.get_mission_status(str(mission.id))
        print(status)
"""

from __future__ import annotations

import os
import time
from typing import Any
from uuid import UUID

from .client import AuthenticatedClient
from .models.mission_create import MissionCreate
from .models.mission_execute_request import MissionExecuteRequest


class FlowmannerError(Exception):
    """Raised when an API call fails or returns an unexpected response."""


class FlowmannerClient:
    """High-level client for the Flowmanner API.

    Args:
        base_url: The base URL of the Flowmanner API (e.g. "https://flowmanner.com").
        api_key: API key for authentication. Falls back to FLOWMANNER_API_KEY env var.

    Example::

        with FlowmannerClient("https://flowmanner.com") as fm:
            mission = fm.create_mission("Summarize docs")
            print(mission.id, mission.status)
    """

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        api_key = api_key or os.environ.get("FLOWMANNER_API_KEY", "")
        if not api_key:
            raise FlowmannerError("No API key provided. Pass api_key or set FLOWMANNER_API_KEY env var.")
        self._client = AuthenticatedClient(
            base_url=base_url.rstrip("/"),
            token=api_key,
            raise_on_unexpected_status=True,
        )

    # ── Context manager support ────────────────────────────────────

    def __enter__(self) -> FlowmannerClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self._client.__exit__(*args)

    async def __aenter__(self) -> FlowmannerClient:
        self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.__aexit__(*args)

    # ── Missions ───────────────────────────────────────────────────

    def create_mission(
        self,
        title: str,
        description: str = "",
        mission_type: str | None = None,
        priority: str | None = None,
    ) -> Any:
        """Create a new mission.

        Args:
            title: Mission title.
            description: Optional description.
            mission_type: Optional mission type (e.g. "automation").
            priority: Optional priority (e.g. "high", "medium", "low").

        Returns:
            MissionResponse with .id, .status, .title, etc.
        """
        from .api.missions import create_item_api_missions_post

        body = MissionCreate(
            title=title,
            description=description,
            mission_type=mission_type,
            priority=priority,
        )
        result = create_item_api_missions_post.sync(client=self._client, body=body)
        if result is None:
            raise FlowmannerError("Failed to create mission: empty response")
        return result

    def get_mission(self, mission_id: str) -> Any:
        """Get a mission by ID.

        Args:
            mission_id: UUID of the mission.

        Returns:
            MissionResponse with full mission details.
        """
        from .api.missions import get_item_api_missions_mission_id_get

        result = get_item_api_missions_mission_id_get.sync(mission_id=UUID(mission_id), client=self._client)
        if result is None:
            raise FlowmannerError(f"Mission {mission_id} not found")
        return result

    def list_missions(self, page: int = 1, per_page: int = 20) -> Any:
        """List missions with pagination.

        Args:
            page: Page number (default 1).
            per_page: Items per page (default 20).

        Returns:
            List of mission objects.
        """
        from .api.missions import list_items_api_missions_get

        result = list_items_api_missions_get.sync(client=self._client, page=page, per_page=per_page)
        return result

    def delete_mission(self, mission_id: str) -> None:
        """Delete a mission by ID.

        Args:
            mission_id: UUID of the mission.
        """
        from .api.missions import delete_item_api_missions_mission_id_delete

        delete_item_api_missions_mission_id_delete.sync(mission_id=UUID(mission_id), client=self._client)

    # ── Swarm debate (the most differentiated call) ───────────────

    def debate(
        self,
        topic: str,
        agent_a_id: str,
        agent_a_name: str,
        agent_b_id: str,
        agent_b_name: str,
        max_rounds: int = 2,
    ) -> dict[str, Any]:
        """Start a multi-agent debate with an LLM judge.

        This is Flowmanner's most distinctive call: two agents argue a topic,
        an LLM judge scores each side, and a consensus synthesis is produced.

        Args:
            topic: The debate topic (1-5000 chars).
            agent_a_id: Personality id of the first agent (from
                ``GET /api/agent-personalities``, format ``<domain>/<slug>``).
            agent_a_name: Display name for the first agent.
            agent_b_id: Personality id of the second agent.
            agent_b_name: Display name for the second agent.
            max_rounds: Number of debate rounds (1-5, default 2).

        Returns:
            Dict with debate_id, judge_verdict, judge_score_a/b,
            consensus_reached, consensus_synthesis, status.

        Example::

            with FlowmannerClient("https://flowmanner.com") as fm:
                result = fm.debate(
                    topic="GraphQL or REST for our public API?",
                    agent_a_id="software_it/code-review-assistant",
                    agent_a_name="Code Review Assistant",
                    agent_b_id="legal/contract-reviewer",
                    agent_b_name="Contract Reviewer",
                )
                print(result["consensus_synthesis"])
        """
        import httpx

        resp = httpx.post(
            f"{self._client.base_url}/api/swarm/protocol/debate",
            headers={"Authorization": f"Bearer {self._client.token}"},
            json={
                "topic": topic,
                "agent_a_id": agent_a_id,
                "agent_a_name": agent_a_name,
                "agent_b_id": agent_b_id,
                "agent_b_name": agent_b_name,
                "max_rounds": max_rounds,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def list_agent_personalities(self) -> list[dict[str, Any]]:
        """List available agent personalities for use in debates.

        Returns:
            List of dicts with ``id`` (``<domain>/<slug>``), ``name``,
            ``domain``, ``description``, ``color``.
        """
        import httpx

        resp = httpx.get(
            f"{self._client.base_url}/api/agent-personalities",
            headers={"Authorization": f"Bearer {self._client.token}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Execution ──────────────────────────────────────────────────

    def execute_mission(self, mission_id: str, input: str | None = None) -> Any:
        """Execute a mission synchronously.

        Args:
            mission_id: UUID of the mission.
            input: Optional input text for the mission.

        Returns:
            MissionExecutionStatus with .status, .total_tasks, etc.
        """
        from .api.missions import execute_mission_api_missions_mission_id_execute_post

        body: MissionExecuteRequest | None = None
        if input is not None:
            body = MissionExecuteRequest(input=input)

        result = execute_mission_api_missions_mission_id_execute_post.sync(
            mission_id=UUID(mission_id), client=self._client, body=body
        )
        if result is None:
            raise FlowmannerError(f"Failed to execute mission {mission_id}")
        return result

    def execute_mission_async(self, mission_id: str, input: str | None = None) -> Any:
        """Execute a mission asynchronously (non-blocking).

        Args:
            mission_id: UUID of the mission.
            input: Optional input text for the mission.

        Returns:
            MissionExecutionStatus.
        """
        from .api.missions import (
            execute_mission_async_api_missions_mission_id_execute_async_post,
        )

        body: MissionExecuteRequest | None = None
        if input is not None:
            body = MissionExecuteRequest(input=input)

        result = execute_mission_async_api_missions_mission_id_execute_async_post.sync(
            mission_id=UUID(mission_id), client=self._client, body=body
        )
        if result is None:
            raise FlowmannerError(f"Failed to execute mission {mission_id} asynchronously")
        return result

    def get_mission_status(self, mission_id: str) -> str:
        """Get the current status of a mission.

        Args:
            mission_id: UUID of the mission.

        Returns:
            Status string (e.g. "pending", "running", "completed", "failed").
        """
        from .api.missions import (
            get_mission_status_api_missions_mission_id_status_get,
        )

        result = get_mission_status_api_missions_mission_id_status_get.sync(
            mission_id=UUID(mission_id), client=self._client
        )
        if result is None:
            raise FlowmannerError(f"Could not get status for mission {mission_id}")
        return result.status if hasattr(result, "status") else str(result)

    def wait_for_mission(
        self,
        mission_id: str,
        poll_interval: float = 5.0,
        timeout: float = 600.0,
    ) -> Any:
        """Poll a mission until it reaches a terminal state.

        Args:
            mission_id: UUID of the mission.
            poll_interval: Seconds between polls (default 5).
            timeout: Max seconds to wait (default 600).

        Returns:
            MissionExecutionStatus when terminal state reached.

        Raises:
            FlowmannerError: On timeout or failure.
        """
        start = time.monotonic()
        terminal = {"completed", "failed", "aborted", "cancelled"}

        while True:
            status = self.get_mission_status(mission_id)
            if status in terminal:
                if status == "failed":
                    raise FlowmannerError(f"Mission {mission_id} failed")
                if status in ("aborted", "cancelled"):
                    raise FlowmannerError(f"Mission {mission_id} was {status}")
                return status

            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                raise FlowmannerError(
                    f"Timeout waiting for mission {mission_id} (status={status}, elapsed={elapsed:.0f}s)"
                )
            time.sleep(poll_interval)

    # ── Tasks ──────────────────────────────────────────────────────

    def list_tasks(self, mission_id: str) -> Any:
        """List tasks for a mission.

        Args:
            mission_id: UUID of the mission.

        Returns:
            List of task objects.
        """
        from .api.missions import (
            list_tasks_api_missions_mission_id_tasks_get,
        )

        result = list_tasks_api_missions_mission_id_tasks_get.sync(mission_id=UUID(mission_id), client=self._client)
        return result

    # ── Analytics ──────────────────────────────────────────────────

    def get_usage_summary(self, period: str = "30d") -> Any:
        """Get usage summary for a time period.

        Args:
            period: Time period string (e.g. "7d", "30d", "90d").

        Returns:
            UsageSummaryResponse with .total_tokens, .total_cost, .breakdown.
        """
        from .api.usage import get_usage_summary_api_v1_usage_summary_get

        result = get_usage_summary_api_v1_usage_summary_get.sync(client=self._client, period=period)
        if result is None:
            raise FlowmannerError("Failed to get usage summary")
        return result

    def get_cost_analytics(self, period: str = "month") -> Any:
        """Get cost analytics broken down by model/agent.

        Args:
            period: "week", "month", or "all".

        Returns:
            Response with .total_cost, .by_agent, .by_model.
        """
        from .api.usage import get_usage_summary_api_v1_usage_summary_get

        result = get_usage_summary_api_v1_usage_summary_get.sync(client=self._client, period=period)
        if result is None:
            raise FlowmannerError("Failed to get cost analytics")
        return result

    # ── System ─────────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """Check API connectivity.

        Returns:
            Health response dict.
        """
        import httpx

        resp = httpx.get(
            f"{self._client.base_url}/api/health",
            headers={"Authorization": f"Bearer {self._client.token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
