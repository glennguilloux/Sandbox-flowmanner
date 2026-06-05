"""
LangChain Tool: n8n Workflow Agent - Production Ready
Execute and manage n8n workflows through natural language

Production Features:
- Connection pooling with requests.Session
- Retry logic with exponential backoff
- Structured logging
- Environment variable validation
- Custom exceptions
"""

import json
import logging
import os
import time
from typing import Any

import requests
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================


class N8NConfig:
    """Configuration for n8n client"""

    BASE_URL = os.getenv("N8N_URL", "http://n8n:5678")
    API_KEY = os.getenv("N8N_API_KEY", "")
    TIMEOUT = int(os.getenv("N8N_TIMEOUT", "30"))
    MAX_RETRIES = int(os.getenv("N8N_MAX_RETRIES", "3"))

    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []

        if not cls.BASE_URL:
            errors.append("N8N_URL is not set")

        if not cls.API_KEY:
            logger.warning("N8N_API_KEY not set - some operations may fail")

        if errors:
            logger.error(f"N8N configuration errors: {errors}")
            raise ValueError(f"Invalid configuration: {', '.join(errors)}")

        logger.info(f"N8N config validated - URL: {cls.BASE_URL}")


try:
    N8NConfig.validate()
except ValueError as e:
    logger.warning(f"N8N configuration issue: {e}")

# ==================== CUSTOM EXCEPTIONS ====================


class N8NError(Exception):
    """Base exception for n8n operations"""

    pass


class N8NConnectionError(N8NError):
    """Connection to n8n failed"""

    pass


class N8NWorkflowError(N8NError):
    """Workflow execution failed"""

    pass


# ==================== VALIDATION MODELS ====================


class N8NWorkflowRequest(BaseModel):
    """Request model for n8n workflow operations"""

    action: str = Field(
        ..., description="Action to perform: list, execute, create, status"
    )
    workflow_id: str | None = Field(None, description="Workflow ID for execute/status")
    parameters: dict[str, Any] | None = Field(
        None, description="Parameters for workflow execution"
    )
    workflow_type: str | None = Field(None, description="Type of workflow to create")
    search_query: str | None = Field(
        None, description="Search query for listing workflows"
    )


# ==================== HTTP CLIENT ====================


class HTTPClient:
    """HTTP client with connection pooling and retry logic"""

    def __init__(
        self, base_url: str, api_key: str, timeout: int = 30, max_retries: int = 3
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.headers = {
            "X-N8N-API-KEY": api_key,
            "Content-Type": "application/json",
        }

        self.session = requests.Session()

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS"],
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy, pool_connections=5, pool_maxsize=5
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        logger.info(f"HTTP client initialized for n8n")

    def get(self, endpoint: str, params: dict | None = None) -> requests.Response:
        """GET request with retry logic"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.get(
                url, headers=self.headers, params=params, timeout=self.timeout
            )
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            raise N8NConnectionError(f"Request to {url} timed out")
        except requests.exceptions.ConnectionError:
            raise N8NConnectionError(f"Cannot connect to {url}")
        except Exception as e:
            raise N8NError(f"GET request failed: {e}")

    def post(self, endpoint: str, json_data: dict | None = None) -> requests.Response:
        """POST request with retry logic"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.post(
                url, headers=self.headers, json=json_data, timeout=self.timeout
            )
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            raise N8NConnectionError(f"Request to {url} timed out")
        except requests.exceptions.ConnectionError:
            raise N8NConnectionError(f"Cannot connect to {url}")
        except Exception as e:
            raise N8NError(f"POST request failed: {e}")

    def close(self):
        """Close session"""
        if self.session:
            self.session.close()


# ==================== N8N CLIENT ====================


class N8NClient:
    """Production-ready n8n client"""

    def __init__(self):
        self.config = N8NConfig
        self.http_client = HTTPClient(
            base_url=self.config.BASE_URL,
            api_key=self.config.API_KEY,
            timeout=self.config.TIMEOUT,
            max_retries=self.config.MAX_RETRIES,
        )
        logger.info(f"N8NClient initialized for {self.config.BASE_URL}")

    def list_workflows(self, search_query: str | None = None) -> list[dict]:
        """List all workflows with optional search"""
        logger.info(f"Listing workflows - search: {search_query}")

        try:
            response = self.http_client.get("/api/v1/workflows")
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

            logger.info(f"Found {len(workflows)} workflows")
            return workflows

        except N8NConnectionError as e:
            logger.error(f"Connection error listing workflows: {e}")
            raise
        except Exception as e:
            logger.error(f"Error listing workflows: {e}")
            raise N8NError(f"Failed to list workflows: {e}")

    def execute_workflow(
        self, workflow_id: str, parameters: dict | None = None
    ) -> dict:
        """Execute a workflow with polling"""
        logger.info(f"Executing workflow {workflow_id} with params: {parameters}")

        try:
            # Get workflow details
            details_response = self.http_client.get(f"/api/v1/workflows/{workflow_id}")
            details = details_response.json()
            logger.debug(f"Workflow details: {details.get('name')}")

            # Execute
            payload = {"workflowId": workflow_id, "parameters": parameters or {}}
            response = self.http_client.post(
                f"/api/v1/workflows/{workflow_id}/execute", json_data=payload
            )
            result = response.json()
            execution_id = result.get("executionId")

            if not execution_id:
                return result

            # Poll for completion
            return self._wait_for_completion(workflow_id, execution_id)

        except N8NConnectionError as e:
            logger.error(f"Connection error executing workflow {workflow_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error executing workflow {workflow_id}: {e}")
            raise N8NError(f"Failed to execute workflow {workflow_id}: {e}")

    def _wait_for_completion(
        self, workflow_id: str, execution_id: str, timeout: int = 60
    ) -> dict:
        """Wait for workflow execution to complete"""
        start_time = time.time()
        logger.info(
            f"Polling for completion - workflow: {workflow_id}, execution: {execution_id}"
        )

        while time.time() - start_time < timeout:
            try:
                response = self.http_client.get(
                    f"/api/v1/workflows/{workflow_id}/executions/{execution_id}"
                )
                execution = response.json()
                status = execution.get("status")

                if status == "success":
                    logger.info(
                        f"Workflow completed successfully - execution: {execution_id}"
                    )
                    return {
                        "success": True,
                        "execution_id": execution_id,
                        "status": "completed",
                        "data": execution.get("data", {}),
                    }
                elif status in ["error", "failed"]:
                    logger.error(f"Workflow failed - execution: {execution_id}")
                    return {
                        "success": False,
                        "execution_id": execution_id,
                        "status": "failed",
                        "error": execution.get("error", "Unknown error"),
                    }

                time.sleep(2)

            except Exception:
                time.sleep(2)

        logger.warning(f"Workflow execution timed out - execution: {execution_id}")
        return {
            "success": False,
            "execution_id": execution_id,
            "status": "timeout",
            "error": f"Execution did not complete within {timeout} seconds",
        }

    def create_workflow(self, workflow_type: str, config: dict | None = None) -> dict:
        """Create a new workflow from template"""
        logger.info(f"Creating workflow - type: {workflow_type}")

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

        template = templates[workflow_type]
        logger.info(f"Workflow template selected: {template['name']}")

        return {
            "success": True,
            "message": f"Workflow template '{workflow_type}' ready",
            "workflow": template,
            "next_steps": "Use execute action to run this workflow",
        }

    def get_workflow_status(self, workflow_id: str) -> dict:
        """Get workflow status and recent executions"""
        logger.info(f"Getting status for workflow {workflow_id}")

        try:
            # Get workflow details
            response = self.http_client.get(f"/api/v1/workflows/{workflow_id}")
            workflow = response.json()

            # Get recent executions
            exec_response = self.http_client.get(
                f"/api/v1/workflows/{workflow_id}/executions"
            )
            executions = exec_response.json().get("data", [])

            return {
                "workflow": workflow,
                "recent_executions": executions[:5],
                "status": "active" if workflow.get("active") else "inactive",
            }

        except N8NConnectionError as e:
            logger.error(f"Connection error getting status for {workflow_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting status for {workflow_id}: {e}")
            raise N8NError(f"Failed to get workflow status: {e}")

    def close(self):
        """Close HTTP client"""
        self.http_client.close()


# ==================== LANGCHAIN TOOL ====================


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
        logger.error(f"n8n_workflow_manager failed: {e}")
        return json.dumps({"success": False, "error": str(e)}, indent=2)
    finally:
        client.close()


# ==================== CONVENIENCE FUNCTIONS ====================


def execute_n8n_workflow(workflow_id: str, parameters: dict = None) -> str:
    """Execute an n8n workflow by ID"""
    return n8n_workflow_manager.invoke(
        {"action": "execute", "workflow_id": workflow_id, "parameters": parameters}
    )


def list_n8n_workflows(search_query: str = None) -> str:
    """List available n8n workflows"""
    return n8n_workflow_manager.invoke({"action": "list", "search_query": search_query})


def create_n8n_workflow(workflow_type: str, config: dict = None) -> str:
    """Create a new n8n workflow from template"""
    return n8n_workflow_manager.invoke(
        {"action": "create", "workflow_type": workflow_type, "parameters": config}
    )


def get_workflow_info(workflow_id: str) -> str:
    """Get detailed information about a workflow"""
    return n8n_workflow_manager.invoke({"action": "status", "workflow_id": workflow_id})
