"""
Unified Tool Bridge - Connects DB-backed tools with in-memory registry

This module bridges System A (ToolRegistry/ToolExecutor) with System B (CustomTool DB):
- Loads CustomTool records from database into ToolRegistry
- Creates executable handlers for DB-backed tools
- Provides unified execution through ToolExecutor
- Syncs changes back to database (analytics, usage tracking)
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from .tool_executor import ExecutionResult, get_tool_executor
from .tool_registry import Tool, get_tool_registry

logger = logging.getLogger(__name__)


class ToolHandlerBuilder:
    """
    Builds executable handlers for DB-backed tools.

    Converts OpenAPI endpoint definitions into callable async handlers
    that can be registered with the ToolExecutor.
    """

    def __init__(self, base_url: str, auth_config: dict[str, Any]):
        self.base_url = base_url.rstrip("/")
        self.auth_config = auth_config or {}
        self.auth_type = self.auth_config.get("auth_type", "none")

    def build_handler(
        self, endpoint: dict[str, Any]
    ) -> Callable[[dict[str, Any]], Awaitable[Any]]:
        """
        Build an async handler for a specific endpoint.

        Args:
            endpoint: Endpoint definition with method, path, parameters, etc.

        Returns:
            Async callable that executes the endpoint
        """
        method = endpoint.get("method", "GET").upper()
        path = endpoint.get("path", "")
        parameters = endpoint.get("parameters", [])

        async def handler(params: dict[str, Any]) -> Any:
            # Build URL with path parameters
            url_path = path
            query_params = {}
            body = None
            headers = self._build_auth_headers()

            # Process parameters
            for param in parameters:
                param_name = param.get("name")
                param_in = param.get("in", "query")
                param_value = params.get(param_name)

                if param_value is None and param.get("required", False):
                    raise ValueError(f"Missing required parameter: {param_name}")

                if param_value is not None:
                    if param_in == "path":
                        url_path = url_path.replace(
                            f"{{{param_name}}}", str(param_value)
                        )
                    elif param_in == "query":
                        query_params[param_name] = param_value
                    elif param_in == "header":
                        headers[param_name] = param_value
                    elif param_in == "body":
                        body = param_value

            # Handle request body
            if "requestBody" in endpoint:
                body = params.get("request_body", params.get("body", body))

            # Build full URL
            url = f"{self.base_url}{url_path}"

            # Execute HTTP request
            async with httpx.AsyncClient(timeout=30.0) as client:
                request_kwargs = {
                    "params": query_params if query_params else None,
                    "headers": headers,
                }

                if body and method in ["POST", "PUT", "PATCH"]:
                    if isinstance(body, dict):
                        request_kwargs["json"] = body
                    else:
                        request_kwargs["data"] = body

                response = await getattr(client, method.lower())(url, **request_kwargs)

                # Try to parse JSON, fall back to text
                try:
                    return response.json()
                except Exception as e:
                    return {"status_code": response.status_code, "text": response.text}

        return handler

    def _build_auth_headers(self) -> dict[str, str]:
        """Build authentication headers based on auth type."""
        headers = {"Content-Type": "application/json"}

        if self.auth_type == "api_key":
            key_name = self.auth_config.get("api_key_name", "X-API-Key")
            key_value = self.auth_config.get("api_key_value", "")
            if key_name.lower() == "authorization":
                headers["Authorization"] = f"Bearer {key_value}"
            else:
                headers[key_name] = key_value

        elif self.auth_type == "basic":
            import base64

            username = self.auth_config.get("username", "")
            password = self.auth_config.get("password", "")
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"

        elif self.auth_type == "bearer":
            token = self.auth_config.get("token", "")
            headers["Authorization"] = f"Bearer {token}"

        return headers


class UnifiedToolBridge:
    """
    Bridge between CustomTool DB records and ToolRegistry.

    Features:
    - Load tools from database into registry
    - Sync usage analytics back to database
    - Provide unified execution interface
    - Handle tool lifecycle (create, update, delete)
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self.registry = get_tool_registry()
        self.executor = get_tool_executor()
        self._loaded_tools: dict[str, str] = {}  # tool_id -> db_id mapping

    def set_db_session(self, db_session):
        """Set the database session for persistence operations."""
        self.db = db_session

    async def load_tools_from_db(self) -> int:
        """
        Load all CustomTool records from database into ToolRegistry.

        Returns:
            Number of tools loaded
        """
        if not self.db:
            logger.warning("No database session set, cannot load tools")
            return 0

        try:
            # Import here to avoid circular imports
            from app.models import CustomTool

            tools = (
                self.db.query(CustomTool)
                .filter(CustomTool.is_public == True)  # Load public tools by default
                .all()
            )

            loaded_count = 0
            for db_tool in tools:
                if self._register_db_tool(db_tool):
                    loaded_count += 1

            logger.info('Loaded %s tools from database into registry', loaded_count)
            return loaded_count

        except Exception as e:
            logger.error('Failed to load tools from database: %s', e)
            return 0

    async def load_user_tools(self, user_id: int) -> int:
        """
        Load tools accessible to a specific user.

        Args:
            user_id: User ID to load tools for

        Returns:
            Number of tools loaded
        """
        if not self.db:
            return 0

        try:
            from app.models import CustomTool, ToolPermission

            # Get tools user created or has permissions for
            owned_tools = (
                self.db.query(CustomTool).filter(CustomTool.created_by == user_id).all()
            )

            # Get tools user has execute permission for
            permitted_tool_ids = (
                self.db.query(ToolPermission.tool_id)
                .filter(
                    ToolPermission.user_id == user_id,
                    ToolPermission.permissions.contains(["execute"]),
                )
                .all()
            )

            permitted_tools = []
            if permitted_tool_ids:
                permitted_tools = (
                    self.db.query(CustomTool)
                    .filter(CustomTool.id.in_([t[0] for t in permitted_tool_ids]))
                    .all()
                )

            # Combine and dedupe
            all_tools = {str(t.id): t for t in owned_tools + permitted_tools}

            loaded_count = 0
            for db_tool in all_tools.values():
                if self._register_db_tool(db_tool):
                    loaded_count += 1

            return loaded_count

        except Exception as e:
            logger.error('Failed to load user tools: %s', e)
            return 0

    def _register_db_tool(self, db_tool) -> bool:
        """
        Register a database tool in the ToolRegistry.

        Args:
            db_tool: CustomTool database record

        Returns:
            True if registered successfully
        """
        try:
            endpoints = db_tool.endpoints or []

            # Register each endpoint as a separate tool
            for endpoint in endpoints:
                tool_id = f"{db_tool.name.lower().replace(' ', '_')}_{endpoint.get('operation_id', endpoint.get('path', '').replace('/', '_'))}"

                # Build handler
                handler_builder = ToolHandlerBuilder(
                    base_url=db_tool.base_url or "",
                    auth_config=db_tool.auth_config or {},
                )
                handler = handler_builder.build_handler(endpoint)

                # Create Tool object
                tool = Tool(
                    tool_id=tool_id,
                    name=f"{db_tool.name}: {endpoint.get('summary', endpoint.get('path'))}",
                    description=endpoint.get("description", db_tool.description or ""),
                    category=db_tool.category or "custom",
                    input_schema=self._build_input_schema(endpoint),
                    output_schema=self._build_output_schema(endpoint),
                    handler=handler,
                    source_service="tool_builder",
                    requires_auth=db_tool.auth_type != "none",
                    tags=db_tool.tags or [],
                    metadata={
                        "db_tool_id": str(db_tool.id),
                        "endpoint": endpoint.get("path"),
                        "method": endpoint.get("method"),
                    },
                )

                self.registry.register(tool)
                self._loaded_tools[tool_id] = str(db_tool.id)

            return True

        except Exception as e:
            logger.error('Failed to register tool %s: %s', db_tool.name, e)
            return False

    def _build_input_schema(self, endpoint: dict[str, Any]) -> dict[str, Any]:
        """Build JSON schema for endpoint input."""
        properties = {}
        required = []

        for param in endpoint.get("parameters", []):
            param_name = param.get("name")
            properties[param_name] = {
                "type": self._map_openapi_type(
                    param.get("schema", {}).get("type", "string")
                ),
                "description": param.get("description", ""),
            }
            if param.get("required", False):
                required.append(param_name)

        # Add request body if present
        if "requestBody" in endpoint:
            properties["request_body"] = {
                "type": "object",
                "description": "Request body",
            }

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _build_output_schema(self, endpoint: dict[str, Any]) -> dict[str, Any]:
        """Build JSON schema for endpoint output."""
        responses = endpoint.get("responses", {})
        success_response = responses.get("200", responses.get("201", {}))

        if "content" in success_response:
            json_content = success_response["content"].get("application/json", {})
            return json_content.get("schema", {"type": "object"})

        return {"type": "object"}

    def _map_openapi_type(self, openapi_type: str) -> str:
        """Map OpenAPI type to JSON Schema type."""
        type_map = {
            "integer": "integer",
            "number": "number",
            "string": "string",
            "boolean": "boolean",
            "array": "array",
            "object": "object",
        }
        return type_map.get(openapi_type, "string")

    async def execute_tool(
        self,
        tool_id: str,
        params: dict[str, Any],
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> ExecutionResult:
        """
        Execute a tool and record analytics.

        Args:
            tool_id: Tool to execute
            params: Parameters for the tool
            user_id: User making the request
            session_id: Session context

        Returns:
            ExecutionResult from the executor
        """
        result = await self.executor.execute(
            tool_id=tool_id, params=params, user_id=user_id, session_id=session_id
        )

        # Record analytics to database if available
        if self.db and tool_id in self._loaded_tools:
            await self._record_analytics(tool_id, result, user_id)

        return result

    async def _record_analytics(
        self, tool_id: str, result: ExecutionResult, user_id: str | None
    ):
        """Record execution analytics to database."""
        try:
            from app.models import CustomTool, ToolAnalytics

            db_tool_id = self._loaded_tools.get(tool_id)
            if not db_tool_id:
                return

            analytics = ToolAnalytics(
                id=uuid.uuid4(),
                tool_id=uuid.UUID(db_tool_id),
                endpoint=result.metadata.get("endpoint", "unknown"),
                method=result.metadata.get("method", "GET"),
                execution_time_ms=int(result.execution_time_ms),
                response_status=200 if result.success else 500,
                success=result.success,
                error_type="execution_error" if result.error else None,
                error_message=result.error,
            )

            self.db.add(analytics)

            # Update tool usage count
            self.db.query(CustomTool).filter(
                CustomTool.id == uuid.UUID(db_tool_id)
            ).update(
                {
                    "usage_count": CustomTool.usage_count + 1,
                    "last_used_at": datetime.now(UTC),
                }
            )

            self.db.commit()

        except Exception as e:
            logger.error('Failed to record analytics: %s', e)
            self.db.rollback()

    def register_new_tool(self, db_tool) -> bool:
        """
        Register a newly created tool from database.

        Args:
            db_tool: CustomTool database record

        Returns:
            True if registered successfully
        """
        return self._register_db_tool(db_tool)

    def unregister_tool(self, tool_id: str) -> bool:
        """
        Remove a tool from the registry.

        Args:
            tool_id: Tool ID to remove

        Returns:
            True if unregistered successfully
        """
        if tool_id in self._loaded_tools:
            del self._loaded_tools[tool_id]
        return self.registry.unregister(tool_id)

    def get_tool_info(self, tool_id: str) -> dict[str, Any] | None:
        """
        Get combined info from registry and database.

        Args:
            tool_id: Tool ID to get info for

        Returns:
            Combined tool information
        """
        tool = self.registry.get(tool_id)
        if not tool:
            return None

        info = {
            "tool_id": tool.tool_id,
            "name": tool.name,
            "description": tool.description,
            "category": tool.category,
            "tags": tool.tags,
            "requires_auth": tool.requires_auth,
            "source": tool.source_service,
            "db_tool_id": self._loaded_tools.get(tool_id),
        }

        return info


# Global bridge instance
_unified_bridge: UnifiedToolBridge | None = None


def get_unified_bridge(db_session=None) -> UnifiedToolBridge:
    """Get or create the global unified tool bridge."""
    global _unified_bridge
    if _unified_bridge is None:
        _unified_bridge = UnifiedToolBridge(db_session)
    elif db_session:
        _unified_bridge.set_db_session(db_session)
    return _unified_bridge
