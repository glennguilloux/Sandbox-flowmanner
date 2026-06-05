"""
LangChain Tool: n8n Workflow Agent
Execute and manage n8n workflows through natural language
"""

import json
import os
import time
from typing import Any

import requests
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class N8NWorkflowRequest(BaseModel):
    """Request model for n8n workflow operations"""

    action: str = Field(
        ..., description="Action to perform: list, execute, create, status"
    )
    workflow_id: str | None = Field(
        None, description="Workflow ID for execute/status"
    )
    parameters: dict[str, Any] | None = Field(
        None, description="Parameters for workflow execution"
    )
    workflow_type: str | None = Field(None, description="Type of workflow to create")
    search_query: str | None = Field(
        None, description="Search query for listing workflows"
    )


class N8NWorkflowResponse(BaseModel):
    """Response model for n8n operations"""

    success: bool
    message: str
    data: dict[str, Any] | None = None
    execution_id: str | None = None
    workflow_id: str | None = None


class N8NClient:
    """Client for n8n API"""

    def __init__(self):
        self.base_url = os.getenv("N8N_URL", "http://n8n:5678")
        self.api_key = os.getenv("N8N_API_KEY", "")
        self.headers = {
            "X-N8N-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

    def list_workflows(self, search_query: str = None) -> list[dict]:
        """List all workflows"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/workflows", headers=self.headers, timeout=10
            )
            response.raise_for_status()
            workflows = response.json().get("data", [])

            if search_query:
                search_lower = search_query.lower()
                workflows = [
                    w
                    for w in workflows
                    if search_lower in w.get("name", "").lower()
                    or search_lower in w.get("tags", [])
                    or search_lower in w.get("description", "").lower()
                ]

            return workflows
        except Exception as e:
            raise Exception(f"Failed to list workflows: {e!s}")

    def execute_workflow(self, workflow_id: str, parameters: dict = None) -> dict:
        """Execute a workflow"""
        try:
            # Get workflow details first
            details = requests.get(
                f"{self.base_url}/api/v1/workflows/{workflow_id}",
                headers=self.headers,
                timeout=10,
            ).json()

            # Execute
            payload = {"workflowId": workflow_id, "parameters": parameters or {}}

            response = requests.post(
                f"{self.base_url}/api/v1/workflows/{workflow_id}/execute",
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            execution_id = result.get("executionId")

            # Poll for completion
            if execution_id:
                return self._wait_for_completion(workflow_id, execution_id)

            return result

        except Exception as e:
            raise Exception(f"Failed to execute workflow {workflow_id}: {e!s}")

    def _wait_for_completion(
        self, workflow_id: str, execution_id: str, timeout: int = 60
    ) -> dict:
        """Wait for workflow execution to complete"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.base_url}/api/v1/workflows/{workflow_id}/executions/{execution_id}",
                    headers=self.headers,
                    timeout=5,
                )
                response.raise_for_status()
                execution = response.json()

                status = execution.get("status")

                if status == "success":
                    return {
                        "success": True,
                        "execution_id": execution_id,
                        "status": "completed",
                        "data": execution.get("data", {}),
                    }
                elif status in ["error", "failed"]:
                    return {
                        "success": False,
                        "execution_id": execution_id,
                        "status": "failed",
                        "error": execution.get("error", "Unknown error"),
                    }

                time.sleep(2)  # Wait before polling again

            except Exception:
                time.sleep(2)

        return {
            "success": False,
            "execution_id": execution_id,
            "status": "timeout",
            "error": f"Execution did not complete within {timeout} seconds",
        }

    def create_workflow(self, workflow_type: str, config: dict = None) -> dict:
        """Create a new workflow"""
        try:
            # Predefined workflow templates
            templates = {
                "ai-image-generator": {
                    "name": "AI Image Generator",
                    "nodes": [
                        {"type": "webhook", "name": "AI Image Trigger"},
                        {"type": "comfyui", "name": "Generate Image"},
                        {"type": "notification", "name": "Send Result"},
                    ],
                    "trigger": "webhook: ai-image-generator",
                },
                "daily-digest": {
                    "name": "Daily Digest",
                    "nodes": [
                        {"type": "schedule", "name": "Daily 8AM"},
                        {"type": "database", "name": "Get Stats"},
                        {"type": "email", "name": "Send Report"},
                    ],
                    "schedule": "0 8 * * *",
                },
                "auto-archive": {
                    "name": "Auto Archive",
                    "nodes": [
                        {"type": "schedule", "name": "Daily 2AM"},
                        {"type": "storage", "name": "S3 Upload"},
                        {"type": "database", "name": "Update Records"},
                    ],
                    "schedule": "0 2 * * *",
                },
            }

            if workflow_type not in templates:
                raise ValueError(f"Unknown workflow type: {workflow_type}")

            # In a real implementation, this would create the workflow via API
            # For now, return the template
            template = templates[workflow_type]

            return {
                "success": True,
                "message": f"Workflow template '{workflow_type}' ready",
                "workflow": template,
                "next_steps": "Use execute action to run this workflow",
            }

        except Exception as e:
            raise Exception(f"Failed to create workflow: {e!s}")

    def get_workflow_status(self, workflow_id: str) -> dict:
        """Get workflow status and recent executions"""
        try:
            # Get workflow details
            response = requests.get(
                f"{self.base_url}/api/v1/workflows/{workflow_id}",
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            workflow = response.json()

            # Get recent executions
            exec_response = requests.get(
                f"{self.base_url}/api/v1/workflows/{workflow_id}/executions",
                headers=self.headers,
                timeout=10,
            )
            executions = exec_response.json().get("data", [])

            return {
                "workflow": workflow,
                "recent_executions": executions[:5],  # Last 5
                "status": "active" if workflow.get("active") else "inactive",
            }

        except Exception as e:
            raise Exception(f"Failed to get workflow status: {e!s}")


@tool
def n8n_workflow_manager(
    action: str,
    workflow_id: str = None,
    parameters: dict = None,
    workflow_type: str = None,
    search_query: str = None,
) -> str:
    """
    Manage and execute n8n workflows through natural language commands.

    Actions:
    - list: List all workflows (optionally filter by search_query)
    - execute: Execute a workflow by ID with parameters
    - create: Create a new workflow from template
    - status: Get workflow status and recent executions

    Examples:
    - List workflows: n8n_workflow_manager("list")
    - Search workflows: n8n_workflow_manager("list", search_query="daily digest")
    - Execute workflow: n8n_workflow_manager("execute", "123", {"param": "value"})
    - Create workflow: n8n_workflow_manager("create", workflow_type="ai-image-generator")
    - Check status: n8n_workflow_manager("status", "123")

    Returns: JSON string with results
    """
    client = N8NClient()

    try:
        if action == "list":
            workflows = client.list_workflows(search_query)
            return json.dumps(
                {
                    "success": True,
                    "count": len(workflows),
                    "workflows": [
                        {
                            "id": w.get("id"),
                            "name": w.get("name"),
                            "description": w.get("description"),
                            "tags": w.get("tags", []),
                            "active": w.get("active"),
                        }
                        for w in workflows
                    ],
                },
                indent=2,
            )

        elif action == "execute":
            if not workflow_id:
                return json.dumps(
                    {"success": False, "error": "workflow_id required for execute"}
                )

            result = client.execute_workflow(workflow_id, parameters)
            return json.dumps(result, indent=2)

        elif action == "create":
            if not workflow_type:
                return json.dumps(
                    {"success": False, "error": "workflow_type required for create"}
                )

            result = client.create_workflow(workflow_type, parameters)
            return json.dumps(result, indent=2)

        elif action == "status":
            if not workflow_id:
                return json.dumps(
                    {"success": False, "error": "workflow_id required for status"}
                )

            result = client.get_workflow_status(workflow_id)
            return json.dumps(result, indent=2)

        else:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Unknown action: {action}. Use list, execute, create, or status",
                }
            )

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


# Convenience functions for common operations
def execute_n8n_workflow(workflow_id: str, parameters: dict = None) -> str:
    """
    Execute an n8n workflow by ID.

    Use this when user wants to "run", "execute", or "trigger" a workflow.

    Example:
    - "Execute workflow 123" -> execute_n8n_workflow("123")
    - "Run daily digest with email" -> execute_n8n_workflow("456", {"email": "user@example.com"})
    """
    return n8n_workflow_manager("execute", workflow_id, parameters)


def list_n8n_workflows(search_query: str = None) -> str:
    """
    List available n8n workflows.

    Use this when user wants to "see", "list", or "find" workflows.

    Example:
    - "Show me all workflows" -> list_n8n_workflows()
    - "Find workflows for automation" -> list_n8n_workflows("automation")
    """
    return n8n_workflow_manager("list", search_query=search_query)


def create_n8n_workflow(workflow_type: str, config: dict = None) -> str:
    """
    Create a new n8n workflow from template.

    Available types: ai-image-generator, daily-digest, auto-archive

    Example:
    - "Create an AI image generator workflow" -> create_n8n_workflow("ai-image-generator")
    """
    return n8n_workflow_manager(
        "create", workflow_type=workflow_type, parameters=config
    )


def get_workflow_info(workflow_id: str) -> str:
    """
    Get detailed information about a workflow.

    Example:
    - "What is workflow 123?" -> get_workflow_info("123")
    - "Show me details of daily digest" -> get_workflow_info("456")
    """
    return n8n_workflow_manager("status", workflow_id)
