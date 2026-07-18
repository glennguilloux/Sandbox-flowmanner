"""
ComfyUI Tool Handler
Executes ComfyUI workflows via API
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import aiohttp

from .base_handler import BaseToolHandler


class ComfyUIHandler(BaseToolHandler):
    """
    Handler for executing ComfyUI workflows

    Supports:
    - Workflow execution
    - Image generation
    - Prompt execution
    - Result retrieval
    """

    def __init__(self, comfyui_base_url: str, client_id: str = None):
        super().__init__("execute_comfyui_workflow", "Execute ComfyUI Workflow")
        self.comfyui_base_url = comfyui_base_url.rstrip("/")
        self.client_id = client_id
        self.session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=300)  # 5 minutes for image generation
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate ComfyUI workflow parameters"""
        required_fields = ["workflow_id"]

        for field in required_fields:
            if field not in parameters:
                return False, f"Missing required field: {field}"

        if not isinstance(parameters["workflow_id"], str):
            return False, "workflow_id must be string"

        return True, None

    async def execute(self, parameters: dict[str, Any], context: dict[str, Any] = None) -> dict[str, Any]:
        """Execute ComfyUI workflow with user isolation"""
        workflow_id = parameters["workflow_id"]
        prompt = parameters.get("prompt", {})

        # Extract user context for isolation
        user_context = (context or {}).get("user_context", {})
        user_id = user_context.get("user_id")

        # Build execution URL
        url = f"{self.comfyui_base_url}/prompt"

        # Prepare payload with user context
        payload = {
            "prompt": prompt,
            "client_id": self.client_id,
            "workflow_id": workflow_id,
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
            # User-specific workflow ID
            user_workflow_id = f"user_{user_id}_{workflow_id}"
            payload["user_workflow_id"] = user_workflow_id

            # Add user-specific output directory
            payload["output_directory"] = f"/comfyui/output/users/{user_id}"

            # Modify prompt to include user context
            if isinstance(prompt, dict):
                prompt["user_context"] = {
                    "user_id": user_id,
                    "username": user_context.get("username"),
                    "is_admin": user_context.get("is_admin", False),
                }

        # Execute workflow
        session = await self._get_session()

        try:
            # Start execution
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    prompt_id = result.get("prompt_id")

                    if not prompt_id:
                        raise Exception("No prompt_id returned from ComfyUI")

                    # Poll for completion
                    execution_result = await self._wait_for_completion(prompt_id)
                    return execution_result

                else:
                    error_text = await response.text()
                    raise Exception(f"ComfyUI API error: {response.status} - {error_text}")

        except Exception as e:
            self.logger.error(f"Failed to execute ComfyUI workflow {workflow_id}: {e}")
            raise

    async def _wait_for_completion(self, prompt_id: str, max_attempts: int = 60) -> dict[str, Any]:
        """Wait for ComfyUI execution to complete"""
        url = f"{self.comfyui_base_url}/history/{prompt_id}"
        session = await self._get_session()

        for attempt in range(max_attempts):
            await asyncio.sleep(2)  # Poll every 2 seconds

            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        history = await response.json()

                        if prompt_id in history:
                            # Execution complete
                            result = history[prompt_id]
                            return {
                                "prompt_id": prompt_id,
                                "status": "completed",
                                "outputs": result.get("outputs", {}),
                                "execution_time": result.get("execution_time"),
                            }

                    elif response.status != 404:
                        # 404 means still executing
                        error_text = await response.text()
                        raise Exception(f"ComfyUI history error: {response.status} - {error_text}")

            except Exception as e:
                self.logger.warning(f"Polling attempt {attempt + 1} failed: {e}")

        raise Exception(f"ComfyUI execution timeout after {max_attempts * 2} seconds")

    def get_tool_schema(self) -> dict[str, Any]:
        """Get ComfyUI workflow tool schema"""
        return {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "description": "Execute ComfyUI workflows for image generation",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "ComfyUI workflow ID",
                    },
                    "prompt": {
                        "type": "object",
                        "description": "ComfyUI prompt object",
                        "additionalProperties": True,
                    },
                    "style": {
                        "type": "string",
                        "description": "Style preset (e.g., 'dark', 'light')",
                    },
                    "resolution": {
                        "type": "string",
                        "description": "Output resolution (e.g., '1920x1080')",
                    },
                },
                "required": ["workflow_id"],
            },
            "requires_approval": True,
            "category": "image_generation",
        }

    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
