"""
Flowmanner Execution Router - Route Selection

Routes execution to the appropriate existing backend route based on:
- Project configuration
- Goal keyword analysis
- Resource requirements

This is a WRAPPER - it calls existing routes without modifying them.
"""

import datetime
import logging
import os
from typing import Any

import httpx
import jwt

logger = logging.getLogger(__name__)


class ExecutionRouter:
    """
    Routes execution to the appropriate existing route.

    Existing routes:
    - mission_routes.py (37KB) - Mission/task execution
    - ai_routes.py (51KB) - AI capabilities, chat, analysis
    - workflow_catalog.py (34KB) - Workflow templates, chains
    """

    def __init__(self):
        # Get backend URL from environment or default
        self.base_url = os.getenv("BACKEND_URL", "http://localhost:8000")
        self.timeout = float(os.getenv("EXECUTION_TIMEOUT", "300"))  # 5 minutes default

        # Keyword mappings for route selection
        self.mission_keywords = [
            "execute",
            "complete",
            "task",
            "mission",
            "step",
            "process",
            "accomplish",
            "achieve",
            "finish",
            "run task",
        ]
        self.workflow_keywords = [
            "workflow",
            "pipeline",
            "chain",
            "sequence",
            "automate",
            "orchestrate",
            "series of steps",
        ]
        self.ai_keywords = [
            "write",
            "generate",
            "create",
            "analyze",
            "summarize",
            "explain",
            "help",
            "chat",
            "answer",
            "research",
            "draft",
        ]

    def get_internal_token(self) -> str:
        """Generate JWT token for internal service authentication."""
        secret = os.environ.get("JWT_SECRET_KEY", "your-secret-key")
        token = jwt.encode(
            {
                "sub": "internal-service",
                "username": "flow-service",
                "is_admin": True,
                "type": "access",
                "exp": datetime.datetime.now(datetime.UTC)
                + datetime.timedelta(days=365),
            },
            secret,
            algorithm="HS256",
        )
        return token

    async def route_and_execute(
        self, project: dict[str, Any], goal: str, mode: str, resources: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Analyze goal and route to appropriate executor.

        Args:
            project: Project dict with id, slug, name, config
            goal: User's objective
            mode: Execution mode (autonomous/guided)
            resources: Resource config (rag, tools, swarm, memory)

        Returns:
            Dict with content, type, metadata
        """

        # Check for explicit route in project config
        explicit_route = project.get("config", {}).get("route")

        if explicit_route:
            logger.info(
                "Using explicit route: %s for project %s",
                explicit_route,
                project["slug"],
            )
            route = explicit_route
        else:
            # Analyze goal to determine route
            route = self.analyze_goal(goal)
            logger.info("Analyzed route: %s for goal: %s...", route, goal[:50])

        # Execute via selected route
        return await self.execute_route(route, project, goal, mode, resources)

    def analyze_goal(self, goal: str) -> str:
        """
        Analyze goal keywords to determine best route.

        Priority:
        1. Mission keywords → mission route
        2. Workflow keywords → workflow route
        3. Default → ai route (most flexible)
        """

        goal_lower = goal.lower()

        # Check mission keywords first (most specific)
        if any(kw in goal_lower for kw in self.mission_keywords):
            return "mission"

        # Check workflow keywords
        if any(kw in goal_lower for kw in self.workflow_keywords):
            return "workflow"

        # Default to AI routes (most flexible)
        return "ai"

    async def execute_route(
        self,
        route: str,
        project: dict[str, Any],
        goal: str,
        mode: str,
        resources: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute via the selected route.

        Each route has its own API contract:
        - mission: POST /api/missions/execute
        - workflow: POST /api/workflows/execute
        - ai: POST /api/chat/completions
        """

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if route == "mission":
                return await self._execute_mission(
                    client, project, goal, mode, resources
                )
            elif route == "workflow":
                return await self._execute_workflow(
                    client, project, goal, mode, resources
                )
            else:  # ai
                return await self._execute_ai(client, project, goal, mode, resources)

    async def _execute_mission(
        self,
        client: httpx.AsyncClient,
        project: dict[str, Any],
        goal: str,
        mode: str,
        resources: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute via mission_routes.py

        Calls: POST /api/missions/execute
        """
        try:
            response = await client.post(
                f"{self.base_url}/api/missions/execute",
                json={
                    "goal": goal,
                    "project_id": project["id"],
                    "mode": mode,
                    "config": project.get("config", {}).get("mission_config", {}),
                    "use_rag": resources.get("rag", True),
                    "use_tools": resources.get("tools", True),
                },
            )
            response.raise_for_status()
            data = response.json()

            return {
                "content": data.get("result", data.get("output", "")),
                "type": "markdown",
                "metadata": {
                    "route": "mission",
                    "mission_id": data.get("mission_id"),
                    "steps_completed": data.get("steps_completed", 0),
                },
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "Mission route error: %s - %s", e.response.status_code, e.response.text
            )
            raise Exception(f"Mission execution failed: {e.response.text}")
        except Exception as e:
            logger.error("Mission route exception: %s", e)
            raise

    async def _execute_workflow(
        self,
        client: httpx.AsyncClient,
        project: dict[str, Any],
        goal: str,
        mode: str,
        resources: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute via workflow_catalog.py

        Calls: POST /api/workflows/execute
        """
        try:
            response = await client.post(
                f"{self.base_url}/api/workflows/execute",
                json={
                    "goal": goal,
                    "project_id": project["id"],
                    "workflow_id": project.get("config", {}).get("workflow_id"),
                    "use_memory": resources.get("memory", True),
                },
            )
            response.raise_for_status()
            data = response.json()

            return {
                "content": data.get("result", data.get("output", "")),
                "type": "markdown",
                "metadata": {
                    "route": "workflow",
                    "workflow_id": data.get("workflow_id"),
                    "steps": data.get("steps", []),
                },
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "Workflow route error: %s - %s", e.response.status_code, e.response.text
            )
            raise Exception(f"Workflow execution failed: {e.response.text}")
        except Exception as e:
            logger.error("Workflow route exception: %s", e)
            raise

    async def _execute_ai(
        self,
        client: httpx.AsyncClient,
        project: dict[str, Any],
        goal: str,
        mode: str,
        resources: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute via ai_routes.py

        Calls: POST /api/chat/completions
        This is the default, most flexible route.
        """
        try:
            response = await client.post(
                f"{self.base_url}/api/providers/chat/completions",
                headers={"Authorization": f"Bearer {self.get_internal_token()}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": goal}],
                    "temperature": 0.7,
                    "max_tokens": 4000,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Extract content from chat response
            content = ""
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")
            elif "content" in data:
                content = data["content"]
            elif "response" in data:
                content = data["response"]

            return {
                "content": content,
                "type": "markdown",
                "metadata": {
                    "route": "ai",
                    "model": data.get("model", "unknown"),
                    "tokens_used": data.get("usage", {}).get("total_tokens", 0),
                    "finish_reason": (
                        data.get("choices", [{}])[0].get("finish_reason")
                        if "choices" in data
                        else None
                    ),
                },
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "AI route error: %s - %s", e.response.status_code, e.response.text
            )
            raise Exception(f"AI execution failed: {e.response.text}")
        except Exception as e:
            logger.error("AI route exception: %s", e)
            raise
