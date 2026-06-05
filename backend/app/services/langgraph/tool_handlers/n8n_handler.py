"""
N8n Workflow Tool Handler
Executes n8n workflows via webhook or API
"""

from datetime import UTC, datetime
from typing import Any

import aiohttp

from .base_handler import BaseToolHandler


class N8nToolHandler(BaseToolHandler):
    """
    Handler for executing n8n workflows

    Supports:
    - Webhook triggers
    - API execution
    - Parameter passing
    - Result retrieval
    """

    def __init__(self, n8n_base_url: str, api_key: str = None):
        super().__init__("execute_n8n_workflow", "Execute n8n Workflow")
        self.n8n_base_url = n8n_base_url.rstrip("/")
        self.api_key = api_key
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=60)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def validate_parameters(
        self, parameters: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Validate n8n workflow parameters"""
        required_fields = ["workflow_id"]

        for field in required_fields:
            if field not in parameters:
                return False, f"Missing required field: {field}"

        if not isinstance(parameters["workflow_id"], (str, int)):
            return False, "workflow_id must be string or integer"

        return True, None

    async def execute(
        self, parameters: dict[str, Any], context: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Execute n8n workflow with user isolation"""
        workflow_id = parameters["workflow_id"]

        # Extract user context for isolation
        user_context = (context or {}).get("user_context", {})
        user_id = user_context.get("user_id")

        # Build execution URL with user isolation
        if self.api_key:
            # Use webhook URL with API key and user context
            url = f"{self.n8n_base_url}/webhook/{workflow_id}?api_key={self.api_key}"
        else:
            # Use generic webhook
            url = f"{self.n8n_base_url}/webhook/{workflow_id}"

        # Prepare payload with user context
        payload = {
            "workflow_id": workflow_id,
            "parameters": {k: v for k, v in parameters.items() if k != "workflow_id"},
            "context": context or {},
            # Add user isolation metadata
            "metadata": {
                "user_id": user_id,
                "executed_by": user_context.get("username", "unknown"),
                "is_admin": user_context.get("is_admin", False),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }

        # If user_id is present, add user-specific workflow parameters
        if user_id:
            # User-specific workflow ID (e.g., user_123_workflow_name)
            user_workflow_id = f"user_{user_id}_{workflow_id}"
            payload["user_workflow_id"] = user_workflow_id

            # Add user-specific configuration path
            payload["user_config_path"] = (
                f"/n8n/users/{user_id}/workflows/{workflow_id}"
            )

        # Execute workflow
        session = await self._get_session()

        try:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "workflow_id": workflow_id,
                        "execution_id": result.get("execution_id"),
                        "status": result.get("status", "completed"),
                        "output": result.get("data", {}),
                        "execution_time": result.get("execution_time"),
                    }
                else:
                    error_text = await response.text()
                    raise Exception(f"n8n API error: {response.status} - {error_text}")

        except Exception as e:
            self.logger.error(f"Failed to execute n8n workflow {workflow_id}: {e}")
            raise

    def get_tool_schema(self) -> dict[str, Any]:
        """Get n8n workflow tool schema"""
        return {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "description": "Execute n8n workflows with parameters",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": ["string", "integer"],
                        "description": "n8n workflow ID or name",
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Workflow-specific parameters",
                        "additionalProperties": True,
                    },
                },
                "required": ["workflow_id"],
            },
            "requires_approval": True,
            "category": "workflow",
        }

    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
