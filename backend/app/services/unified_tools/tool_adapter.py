"""
Tool Adapter - Adapts existing services into standardized tool format

Wraps existing services (RAG, workflows, agents, etc.) as tools
with consistent schemas and interfaces.
"""

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .tool_registry import Tool, get_tool_registry

logger = logging.getLogger(__name__)


@dataclass
class ServiceInfo:
    """Information about a service to be adapted"""

    name: str
    module_path: str
    class_name: str | None = None
    methods: dict[str, dict[str, Any]] = field(default_factory=dict)


class ToolAdapter:
    """
    Adapts existing services into standardized tool format.

    Auto-wraps services like:
    - rag_pipeline.py -> rag_search, rag_ingest, rag_summarize
    - workflow_executor.py -> workflow_run, workflow_status
    - comfyui_gateway.py -> image_generate, model_3d_generate
    - agent services -> agent_execute, agent_analyze
    """

    # Mapping of service methods to tool definitions
    SERVICE_TOOL_MAPPING = {
        "rag_pipeline": {
            "search": {
                "tool_id": "rag_search",
                "name": "Search Knowledge Base",
                "description": "Search the RAG knowledge base for relevant documents",
                "category": "knowledge",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "collection": {
                            "type": "string",
                            "description": "Collection to search",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "results": {"type": "array", "items": {"type": "object"}},
                        "scores": {"type": "array", "items": {"type": "number"}},
                    },
                },
            },
            "ingest": {
                "tool_id": "rag_ingest",
                "name": "Ingest Documents",
                "description": "Ingest documents into the knowledge base",
                "category": "knowledge",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "documents": {"type": "array", "items": {"type": "object"}},
                        "collection": {"type": "string"},
                    },
                    "required": ["documents", "collection"],
                },
            },
        },
        "workflow_executor": {
            "run": {
                "tool_id": "workflow_run",
                "name": "Run Workflow",
                "description": "Execute a workflow by ID or name",
                "category": "workflow",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string"},
                        "inputs": {"type": "object"},
                    },
                    "required": ["workflow_id"],
                },
            },
            "status": {
                "tool_id": "workflow_status",
                "name": "Check Workflow Status",
                "description": "Get the status of a workflow execution",
                "category": "workflow",
                "input_schema": {
                    "type": "object",
                    "properties": {"execution_id": {"type": "string"}},
                    "required": ["execution_id"],
                },
            },
        },
        "comfyui_gateway": {
            "generate": {
                "tool_id": "image_generate",
                "name": "Generate Image",
                "description": "Generate an image using ComfyUI",
                "category": "generation",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "negative_prompt": {"type": "string"},
                        "width": {"type": "integer", "default": 512},
                        "height": {"type": "integer", "default": 512},
                    },
                    "required": ["prompt"],
                },
            }
        },
        "agent_service": {
            "execute": {
                "tool_id": "agent_execute",
                "name": "Execute Agent Task",
                "description": "Execute a task using an AI agent",
                "category": "agent",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "agent_id": {"type": "string"},
                        "context": {"type": "object"},
                    },
                    "required": ["task"],
                },
            },
            "analyze": {
                "tool_id": "agent_analyze",
                "name": "Analyze with Agent",
                "description": "Analyze content using an AI agent",
                "category": "agent",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "analysis_type": {"type": "string"},
                    },
                    "required": ["content"],
                },
            },
        },
        "memory_service": {
            "store": {
                "tool_id": "memory_store",
                "name": "Store Memory",
                "description": "Store information in agent memory",
                "category": "memory",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "agent_id": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["content"],
                },
            },
            "recall": {
                "tool_id": "memory_recall",
                "name": "Recall Memory",
                "description": "Recall information from agent memory",
                "category": "memory",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "agent_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        },
    }

    def __init__(self, registry=None):
        self.registry = registry or get_tool_registry()
        self._adapted_services: dict[str, list[str]] = {}

    def adapt_service(
        self, service_name: str, service_instance: Any, methods: list[str] | None = None
    ) -> list[Tool]:
        """
        Adapt a service instance into tools.

        Args:
            service_name: Name of the service (e.g., "rag_pipeline")
            service_instance: The actual service instance
            methods: Specific methods to adapt (None = all mapped)

        Returns:
            List of created Tool objects
        """
        tools = []

        # Get tool definitions for this service
        tool_defs = self.SERVICE_TOOL_MAPPING.get(service_name, {})

        if not tool_defs:
            logger.warning('No tool definitions found for service: %s', service_name)
            return tools

        # Filter methods if specified
        if methods:
            tool_defs = {k: v for k, v in tool_defs.items() if k in methods}

        for method_name, tool_def in tool_defs.items():
            # Get the method from the service
            method = getattr(service_instance, method_name, None)
            if method is None:
                logger.warning('Method %s not found on %s', method_name, service_name)
                continue

            # Create wrapper handler
            handler = self._create_handler(method, service_name, method_name)

            # Create the tool
            tool = Tool(
                tool_id=tool_def["tool_id"],
                name=tool_def["name"],
                description=tool_def["description"],
                category=tool_def["category"],
                input_schema=tool_def.get("input_schema", {}),
                output_schema=tool_def.get("output_schema", {}),
                handler=handler,
                source_service=service_name,
                requires_auth=tool_def.get("requires_auth", True),
                cost_estimate=tool_def.get("cost_estimate", {}),
                tags=tool_def.get("tags", []),
            )

            # Register the tool
            self.registry.register(tool)
            tools.append(tool)

            # Track adapted services
            if service_name not in self._adapted_services:
                self._adapted_services[service_name] = []
            self._adapted_services[service_name].append(tool.tool_id)

        logger.info('Adapted %s tools from %s', len(tools), service_name)
        return tools

    def _create_handler(
        self, method: Callable, service_name: str, method_name: str
    ) -> Callable[[dict[str, Any]], Awaitable[Any]]:
        """Create an async handler wrapper for a service method"""

        async def handler(params: dict[str, Any]) -> Any:
            try:
                # Check if method is async
                if inspect.iscoroutinefunction(method):
                    result = await method(**params)
                else:
                    result = method(**params)
                return result
            except Exception as e:
                logger.error('Error in %s.%s: %s', service_name, method_name, e)
                raise

        return handler

    def adapt_function(
        self,
        func: Callable,
        tool_id: str,
        name: str,
        description: str,
        category: str,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        **kwargs,
    ) -> Tool:
        """
        Adapt a single function into a tool.

        Args:
            func: The function to adapt
            tool_id: Unique tool identifier
            name: Human-readable name
            description: Tool description
            category: Tool category
            input_schema: JSON schema for inputs
            output_schema: JSON schema for outputs

        Returns:
            The created Tool object
        """
        # Infer schema from function signature if not provided
        if not input_schema:
            input_schema = self._infer_schema_from_function(func)

        # Create handler
        handler = self._create_handler(func, "custom", tool_id)

        tool = Tool(
            tool_id=tool_id,
            name=name,
            description=description,
            category=category,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            handler=handler,
            source_service="custom",
            **kwargs,
        )

        self.registry.register(tool)
        return tool

    def _infer_schema_from_function(self, func: Callable) -> dict[str, Any]:
        """Infer input schema from function signature"""
        sig = inspect.signature(func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ["self", "cls"]:
                continue

            prop = {"type": "string"}  # Default type

            # Try to infer type from annotation
            if param.annotation != inspect.Parameter.empty:
                type_map = {
                    str: "string",
                    int: "integer",
                    float: "number",
                    bool: "boolean",
                    list: "array",
                    dict: "object",
                }
                prop["type"] = type_map.get(param.annotation, "string")

            properties[param_name] = prop

            # Check if required (no default value)
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {"type": "object", "properties": properties, "required": required}

    def list_adapted_services(self) -> dict[str, list[str]]:
        """List all adapted services and their tools"""
        return self._adapted_services.copy()

    def register_service_mapping(
        self, service_name: str, method_tools: dict[str, dict[str, Any]]
    ) -> None:
        """Register custom service-to-tool mappings"""
        self.SERVICE_TOOL_MAPPING[service_name] = method_tools
        logger.info('Registered custom mapping for %s', service_name)
