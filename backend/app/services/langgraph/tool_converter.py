#!/usr/bin/env python3
"""
Natural Language to Tool Converter

Converts natural language requests into structured tool calls using LLM.
Handles:
- Intent classification
- Tool selection
- Parameter extraction
- Tool chaining
- Multiple LLM model support
"""

import json
import logging
import os
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.core.llm_config import LLMManager, get_llm_manager

logger = logging.getLogger(__name__)


class ToolDefinition:
    """Represents a tool that can be called by the agent"""

    def __init__(
        self,
        tool_id: str,
        name: str,
        description: str,
        parameters_schema: dict[str, Any],
        category: str = "general",
        is_safe: bool = False,
        requires_approval: bool = False,
    ):
        self.tool_id = tool_id
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema
        self.category = category
        self.is_safe = is_safe
        self.requires_approval = requires_approval

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "parameters_schema": self.parameters_schema,
            "category": self.category,
            "is_safe": self.is_safe,
            "requires_approval": self.requires_approval,
        }

    def to_llm_format(self) -> str:
        """Format for LLM prompt"""
        schema_str = json.dumps(self.parameters_schema, indent=2)
        return f"""
Tool: {self.name} (ID: {self.tool_id})
Category: {self.category}
Description: {self.description}
Safe: {self.is_safe}
Requires Approval: {self.requires_approval}
Parameters Schema:
{schema_str}
"""


class ToolConverter:
    """
    Converts natural language to tool calls using LLM.

    This class handles:
    - Analyzing user intent
    - Selecting appropriate tools
    - Extracting parameters from natural language
    - Handling multi-step workflows
    - Multiple LLM model support with fallback
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        llm_manager: LLMManager | None = None,
        default_model_id: str | None = None,
    ):
        """
        Initialize tool converter.

        Args:
            llm: Optional LLM instance (will use LLM manager if not provided)
            llm_manager: Optional LLM manager instance
            default_model_id: Optional default model ID
        """
        self.llm = llm
        self.llm_manager = llm_manager or get_llm_manager()
        self.default_model_id = default_model_id
        self.tools: dict[str, ToolDefinition] = {}
        self._initialize_default_tools()

    def _initialize_default_tools(self):
        """Initialize default tool definitions"""
        # Workflow execution tools
        self.register_tool(
            ToolDefinition(
                tool_id="execute_n8n_workflow",
                name="Execute n8n Workflow",
                description="Execute an n8n workflow by ID with optional parameters",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "The ID of the n8n workflow to execute",
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Optional parameters to pass to the workflow",
                        },
                    },
                    "required": ["workflow_id"],
                },
                category="workflow",
                is_safe=False,
                requires_approval=True,
            )
        )

        self.register_tool(
            ToolDefinition(
                tool_id="execute_comfyui_workflow",
                name="Execute ComfyUI Workflow",
                description="Execute a ComfyUI workflow for image generation",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "The ID of the ComfyUI workflow",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Text prompt for image generation",
                        },
                        "negative_prompt": {
                            "type": "string",
                            "description": "Negative prompt for image generation",
                        },
                        "width": {
                            "type": "integer",
                            "description": "Image width in pixels",
                        },
                        "height": {
                            "type": "integer",
                            "description": "Image height in pixels",
                        },
                    },
                    "required": ["workflow_id", "prompt"],
                },
                category="image",
                is_safe=False,
                requires_approval=True,
            )
        )

        self.register_tool(
            ToolDefinition(
                tool_id="execute_3dglenn_workflow",
                name="Execute 3Dglenn Workflow",
                description="Execute a 3Dglenn workflow for 3D model generation",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "The ID of the 3Dglenn workflow",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Text prompt for 3D model generation",
                        },
                        "model_type": {
                            "type": "string",
                            "description": "Type of 3D model to generate",
                        },
                    },
                    "required": ["workflow_id", "prompt"],
                },
                category="3d",
                is_safe=False,
                requires_approval=True,
            )
        )

        self.register_tool(
            ToolDefinition(
                tool_id="search_workflows",
                name="Search Workflows",
                description="Search for available workflows by name, category, or tags",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for workflows",
                        },
                        "category": {
                            "type": "string",
                            "description": "Filter by workflow category",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                        },
                    },
                    "required": ["query"],
                },
                category="search",
                is_safe=True,
                requires_approval=False,
            )
        )

        self.register_tool(
            ToolDefinition(
                tool_id="get_workflow_details",
                name="Get Workflow Details",
                description="Get detailed information about a specific workflow",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "The ID of the workflow",
                        },
                        "workflow_type": {
                            "type": "string",
                            "description": "Type of workflow (n8n, external, comfyui, 3dglenn)",
                        },
                    },
                    "required": ["workflow_id"],
                },
                category="search",
                is_safe=True,
                requires_approval=False,
            )
        )

        self.register_tool(
            ToolDefinition(
                tool_id="list_saved_configs",
                name="List Saved Configurations",
                description="List saved tool configurations for the current user",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "tool_id": {
                            "type": "string",
                            "description": "Optional filter by tool ID",
                        }
                    },
                },
                category="config",
                is_safe=True,
                requires_approval=False,
            )
        )

        self.register_tool(
            ToolDefinition(
                tool_id="load_saved_config",
                name="Load Saved Configuration",
                description="Load a saved tool configuration by ID",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "config_id": {
                            "type": "string",
                            "description": "The ID of the saved configuration",
                        }
                    },
                    "required": ["config_id"],
                },
                category="config",
                is_safe=True,
                requires_approval=False,
            )
        )

        self.register_tool(
            ToolDefinition(
                tool_id="save_tool_config",
                name="Save Tool Configuration",
                description="Save current tool parameters as a reusable configuration",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "tool_id": {
                            "type": "string",
                            "description": "The ID of the tool",
                        },
                        "name": {
                            "type": "string",
                            "description": "Name for the saved configuration",
                        },
                        "description": {
                            "type": "string",
                            "description": "Description of the configuration",
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Tool parameters to save",
                        },
                    },
                    "required": ["tool_id", "name", "parameters"],
                },
                category="config",
                is_safe=True,
                requires_approval=False,
            )
        )

        # ── Integration discovery & execution tools ─────────────
        self.register_tool(
            ToolDefinition(
                tool_id="list_integrations",
                name="List Integrations",
                description=(
                    "List all integrations the current user has connected (Slack, GitHub, "
                    "Google, Notion, Linear, Discord) along with available actions for each. "
                    "Use this before calling execute_integration to discover what is available."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {},
                },
                category="integration",
                is_safe=True,
                requires_approval=False,
            )
        )

        self.register_tool(
            ToolDefinition(
                tool_id="execute_integration",
                name="Execute Integration Action",
                description=(
                    "Call an action on a user's connected integration. "
                    "Use list_integrations first to see available slugs and actions."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Integration slug: slack, github, google, notion, linear, or discord",
                        },
                        "action": {
                            "type": "string",
                            "description": "Action to call (e.g., send_message, create_issue, gmail_send)",
                        },
                        "params": {
                            "type": "object",
                            "description": 'Parameters for the action (e.g., {"channel": "C123", "text": "hello"})',
                        },
                    },
                    "required": ["slug", "action"],
                },
                category="integration",
                is_safe=False,
                requires_approval=True,
            )
        )

    def register_tool(self, tool: ToolDefinition):
        """
        Register a new tool.

        Args:
            tool: ToolDefinition to register
        """
        self.tools[tool.tool_id] = tool
        logger.info("Registered tool: %s (%s)", tool.name, tool.tool_id)

    def get_tool(self, tool_id: str) -> ToolDefinition | None:
        """
        Get a tool by ID.

        Args:
            tool_id: Tool identifier

        Returns:
            ToolDefinition if found, None otherwise
        """
        return self.tools.get(tool_id)

    def list_tools(self, category: str | None = None) -> list[ToolDefinition]:
        """
        List all available tools.

        Args:
            category: Optional filter by category

        Returns:
            List of ToolDefinition
        """
        tools = list(self.tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    async def convert_to_tools(
        self,
        message: str,
        conversation_history: list[dict[str, Any]] = None,
        context: dict[str, Any] = None,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Convert natural language message to tool calls.

        Args:
            message: User message
            conversation_history: Optional conversation history
            context: Optional context information
            model_id: Optional model ID to use (uses default if not provided)

        Returns:
            Dictionary with:
            - intent: Classified intent
            - tools: List of tool calls to make
            - reasoning: Explanation of the decision
        """
        # Get LLM instance
        llm = self._get_llm(model_id)
        if not llm:
            return self._fallback_conversion(message)

        try:
            # Build prompt
            tools_description = self._build_tools_description()

            prompt = ChatPromptTemplate.from_messages(
                [
                    SystemMessage(content=self._get_system_prompt(tools_description)),
                    MessagesPlaceholder(variable_name="history"),
                    HumanMessage(content=message),
                ]
            )

            # Format messages
            messages = []
            if conversation_history:
                for msg in conversation_history:
                    if msg["role"] == "user":
                        messages.append(HumanMessage(content=msg["content"]))
                    elif msg["role"] == "assistant":
                        messages.append(AIMessage(content=msg["content"]))

            # Invoke LLM
            chain = prompt | llm | JsonOutputParser()
            result = await chain.ainvoke(
                {
                    "history": messages,
                }
            )

            # Parse result
            return self._parse_llm_result(result)

        except Exception as e:
            logger.error("Error converting to tools: %s", e)
            return self._fallback_conversion(message)

    def _get_system_prompt(self, tools_description: str) -> str:
        """Get system prompt for LLM"""
        return f"""You are an AI assistant that helps users execute workflows, tools, and connected integrations.

Your task is to analyze user requests and determine:
1. What the user wants to do (intent)
2. Which tools to call
3. What parameters to pass to each tool

Available Tools:
{tools_description}

## Proactive Integration Awareness

You have access to list_integrations and execute_integration tools that let
you discover and use the user's connected services (Slack, GitHub, Google,
Notion, Linear, Discord). Be proactive — don't wait for the user to explicitly
ask about integrations.

When to volunteer integration actions:
- User mentions sending/posting/sharing something → check if Slack or Discord
  is connected and offer to post it there
- User mentions creating a task, bug, or issue → check if GitHub or Linear
  is connected and offer to create an issue
- User mentions emailing someone → check if Google (Gmail) is connected
- User mentions documents, notes, or wikis → check if Notion is connected
- User asks "what can you do?" or "what's connected?" → call list_integrations
  first before answering

Always call list_integrations first to discover what's available, then propose
the relevant action. Frame it as a suggestion: "I see you have GitHub connected —
want me to create an issue for that?"

Guidelines:
- Always explain your reasoning before suggesting tools
- When integrations could help, call list_integrations proactively
- Only suggest tools that are relevant to the user's request
- Extract parameters from the user's message when possible
- If required parameters are missing, ask the user for clarification
- For safe tools, you can proceed without asking for approval
- For tools requiring approval, clearly indicate this to the user
- You can chain multiple tools together if needed

Response Format:
{{
    "intent": "brief description of user's intent",
    "reasoning": "explanation of why you chose these tools",
    "tools": [
        {{
            "tool_id": "tool identifier",
            "tool_name": "tool name",
            "parameters": {{}},
            "requires_approval": true/false
        }}
    ],
    "missing_info": ["list of missing required parameters if any"]
}}"""

    def _build_tools_description(self) -> str:
        """Build description of all tools for LLM"""
        descriptions = []
        for tool in self.tools.values():
            descriptions.append(tool.to_llm_format())
        return "\n".join(descriptions)

    def _parse_llm_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Parse LLM result"""
        tools = []
        for tool_call in result.get("tools", []):
            tool_def = self.get_tool(tool_call.get("tool_id"))
            if tool_def:
                tools.append(
                    {
                        "tool_id": tool_call["tool_id"],
                        "tool_name": tool_call["tool_name"],
                        "parameters": tool_call.get("parameters", {}),
                        "requires_approval": tool_call.get(
                            "requires_approval", tool_def.requires_approval
                        ),
                    }
                )

        return {
            "intent": result.get("intent", ""),
            "reasoning": result.get("reasoning", ""),
            "tools": tools,
            "missing_info": result.get("missing_info", []),
        }

    def _get_llm(self, model_id: str | None = None) -> BaseChatModel | None:
        """
        Get LLM instance for specified model.

        Args:
            model_id: Optional model ID

        Returns:
            LLM instance or None
        """
        # Use provided LLM if available
        if self.llm:
            return self.llm

        # Get from LLM manager
        return self.llm_manager.get_model(
            model_id=model_id or self.default_model_id,
            use_fallback=True,
        )

    def _extract_workflow_file_info(
        self, message: str
    ) -> tuple[str | None, dict[str, Any] | None]:
        """
        Extract workflow file reference from message and load it.

        Looks for patterns like:
        - "geometry_only.json"
        - "with geometry_only"
        - "using workflow geometry_only"

        Args:
            message: User message

        Returns:
            Tuple of (workflow_id, workflow_data) or (None, None) if not found
        """
        import json
        import re

        # Common workflow directory paths (mounted in container)
        workflow_dirs = [
            "/external-workflows",  # Mounted from /mnt/apps/data/glennguilloux/Workflows
            "/comfy-output",  # Mounted from /var/www/workflows/comfyui-3d/mnt/ComfyUI/output
            # Also check subdirectories
            "/external-workflows/OPUS Workflows",
            "/external-workflows/3Dglenn",
        ]

        # Try to find workflow file references
        # Match patterns like "geometry_only.json" or "workflow geometry_only"
        patterns = [
            r"(\w+)\.json",  # Matches "geometry_only.json"
            r"workflow\s+(\w+)",  # Matches "workflow geometry_only"
            r"(\w+)\s+workflow",  # Matches "geometry_only workflow"
        ]

        workflow_name = None

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                workflow_name = match.group(1)
                logger.info(
                    "[DEBUG] Pattern %s matched, captured: '%s'", pattern, workflow_name
                )
                # Remove .json extension if present
                if workflow_name.endswith(".json"):
                    workflow_name = workflow_name[:-5]
                    logger.info(
                        "[DEBUG] Removed .json extension, workflow_name: '%s'",
                        workflow_name,
                    )
                break

        if not workflow_name:
            return None, None

        # Try to load the workflow file
        for workflow_dir in workflow_dirs:
            for ext in ["", ".json"]:
                workflow_path = f"{workflow_dir}/{workflow_name}{ext}"
                try:
                    if os.path.exists(workflow_path):
                        with open(workflow_path, "r") as f:
                            workflow_data = json.load(f)
                            logger.info("Loaded workflow file: %s", workflow_path)
                            return workflow_name, workflow_data
                except Exception as e:
                    logger.warning("Failed to load workflow %s: %s", workflow_path, e)
                    continue

        # If file not found, still return the workflow name for potential remote loading
        logger.info("Workflow file not found locally, using name: %s", workflow_name)
        return workflow_name, None

    def _fallback_conversion(self, message: str) -> dict[str, Any]:
        """
        Fallback conversion when LLM is not available.
        Uses simple keyword matching.
        """
        message_lower = message.lower()
        tools = []

        # Simple keyword matching
        if "execute" in message_lower or "run" in message_lower:
            if "n8n" in message_lower:
                tools.append(
                    {
                        "tool_id": "execute_n8n_workflow",
                        "tool_name": "Execute n8n Workflow",
                        "parameters": {},
                        "requires_approval": True,
                    }
                )
            elif "comfyui" in message_lower or "image" in message_lower:
                # Try to extract workflow file reference
                logger.info(
                    "[DEBUG] ComfyUI detected in message, calling _extract_workflow_file_info"
                )
                workflow_name, workflow_data = self._extract_workflow_file_info(message)
                logger.info(
                    "[DEBUG] Extraction result - workflow_name: %s, workflow_data: %s",
                    workflow_name,
                    workflow_data is not None,
                )

                parameters: dict[str, Any] = {}
                if workflow_name:
                    parameters["workflow_id"] = workflow_name

                if workflow_data:
                    parameters["prompt"] = workflow_data

                logger.info("[DEBUG] Final parameters: %s", parameters)

                tools.append(
                    {
                        "tool_id": "execute_comfyui_workflow",
                        "tool_name": "Execute ComfyUI Workflow",
                        "parameters": parameters,
                        "requires_approval": True,
                    }
                )
            elif "3d" in message_lower or "glenn" in message_lower:
                tools.append(
                    {
                        "tool_id": "execute_3dglenn_workflow",
                        "tool_name": "Execute 3Dglenn Workflow",
                        "parameters": {},
                        "requires_approval": True,
                    }
                )

        elif "search" in message_lower or "find" in message_lower:
            tools.append(
                {
                    "tool_id": "search_workflows",
                    "tool_name": "Search Workflows",
                    "parameters": {"query": message},
                    "requires_approval": False,
                }
            )

        elif "save" in message_lower and "config" in message_lower:
            tools.append(
                {
                    "tool_id": "save_tool_config",
                    "tool_name": "Save Tool Configuration",
                    "parameters": {},
                    "requires_approval": False,
                }
            )

        return {
            "intent": "Analyze user request",
            "reasoning": "Using keyword-based matching (LLM not available)",
            "tools": tools,
            "missing_info": [],
        }

    def validate_parameters(
        self,
        tool_id: str,
        parameters: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """
        Validate tool parameters against schema.

        Args:
            tool_id: Tool identifier
            parameters: Parameters to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        tool = self.get_tool(tool_id)
        if not tool:
            return False, [f"Tool {tool_id} not found"]

        errors = []
        schema = tool.parameters_schema

        # Check required parameters
        required = schema.get("required", [])
        for param in required:
            if param not in parameters:
                errors.append(f"Missing required parameter: {param}")

        # Validate parameter types (basic validation)
        properties = schema.get("properties", {})
        for param_name, param_value in parameters.items():
            if param_name in properties:
                param_schema = properties[param_name]
                expected_type = param_schema.get("type")

                if expected_type == "string" and not isinstance(param_value, str):
                    errors.append(f"Parameter {param_name} should be a string")
                elif expected_type == "integer" and not isinstance(param_value, int):
                    errors.append(f"Parameter {param_name} should be an integer")
                elif expected_type == "number" and not isinstance(
                    param_value, (int, float)
                ):
                    errors.append(f"Parameter {param_name} should be a number")
                elif expected_type == "boolean" and not isinstance(param_value, bool):
                    errors.append(f"Parameter {param_name} should be a boolean")

        return len(errors) == 0, errors

    async def convert_with_reuse(
        self,
        message: str,
        user_id: int,
        conversation_history: list[dict] = None,
        context: dict[str, Any] = None,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Convert message to tool calls with configuration reuse support.

        This enhanced method:
        1. Checks if user mentions a saved configuration
        2. Loads the configuration if found
        3. Uses LLM to extract parameters from message
        4. Merges saved config with new parameters
        5. Returns complete tool call with merged parameters

        Args:
            message: User message
            user_id: User ID for configuration lookup
            conversation_history: Optional conversation history
            context: Optional context information
            model_id: Optional model ID to use

        Returns:
            Dictionary with:
            - intent: Classified intent
            - tools: List of tool calls with merged parameters
            - reasoning: Explanation of the decision
            - reused_config: Configuration ID if reused
            - parameter_overrides: Parameters that were overridden
        """
        # Step 1: Check for configuration references
        config_match = await self._detect_configuration_reference(
            message=message,
            user_id=user_id,
            model_id=model_id,
        )

        # Step 2: Convert message to tool calls
        conversion_result = await self.convert_to_tools(
            message=message,
            conversation_history=conversation_history,
            context=context,
            model_id=model_id,
        )

        # Step 3: Merge with saved configuration if found
        if config_match and conversion_result.get("tools"):
            merged_result = await self._merge_with_configuration(
                conversion_result=conversion_result,
                config_match=config_match,
                message=message,
                user_id=user_id,
                model_id=model_id,
            )
            return merged_result

        return {
            **conversion_result,
            "reused_config": None,
            "parameter_overrides": {},
        }

    async def _detect_configuration_reference(
        self,
        message: str,
        user_id: int,
        model_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Detect if user is referencing a saved configuration.

        Uses LLM to analyze the message and determine if the user
        is referring to a saved configuration by name, description,
        or context.

        Returns:
            Dictionary with matched configuration and confidence score
        """
        # Get user's saved configurations
        from .persistence import get_persistence

        persistence = get_persistence()
        saved_configs = persistence.list_user_configurations(user_id=user_id)

        if not saved_configs:
            return None

        # Build prompt for LLM to detect configuration references
        config_descriptions = []
        for config in saved_configs:
            config_descriptions.append(
                f"""
Configuration: {config["name"]}
Description: {config["description"]}
Tool: {config["tool_name"]}
Parameters: {json.dumps(config["parameters"], indent=2)}
"""
            )

        llm = self._get_llm(model_id)
        if not llm:
            # Fallback to keyword matching
            return self._fallback_config_matching(message, saved_configs)  # type: ignore[arg-type]

        joined_descriptions = "\\n".join(config_descriptions)
        prompt = f"""Analyze the user's message and determine if they are referencing
any of their saved tool configurations.

User Message: "{message}"

Saved Configurations:
{joined_descriptions}

Respond with JSON:
{{
    "config_id": "ID of matched config or null",
    "confidence": 0.0-1.0,
    "reasoning": "Why this config was matched",
    "parameter_overrides": {{}}  // Example: {{"scale": 1.5, "steps": 30}}
}}"""

        try:
            result = await llm.ainvoke(prompt)
            response = json.loads(result.content)

            if response.get("config_id") and response.get("confidence", 0) > 0.7:
                return response

            return None
        except Exception as e:
            logger.error("Error detecting config reference: %s", e)
            return self._fallback_config_matching(message, saved_configs)  # type: ignore[arg-type]

    def _fallback_config_matching(
        self,
        message: str,
        saved_configs: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        Fallback configuration matching using keyword search.

        Used when LLM is not available or fails.
        """
        message_lower = message.lower()

        best_match = None
        best_score = 0

        for config in saved_configs:
            score = 0

            # Check name match
            if config["name"].lower() in message_lower:
                score += 0.5  # type: ignore[assignment]

            # Check description match
            if config["description"]:
                desc_words = config["description"].lower().split()
                for word in desc_words:
                    if len(word) > 3 and word in message_lower:
                        score += 0.1  # type: ignore[assignment]

            # Check tool name match
            if config["tool_name"].lower() in message_lower:
                score += 0.3  # type: ignore[assignment]

            if score > best_score:
                best_score = score
                best_match = config

        if best_score > 0.5:
            return {
                "config_id": best_match["config_id"],
                "confidence": best_score,
                "reasoning": f"Keyword match for '{best_match['name']}'",
                "parameter_overrides": {},
            }

        return None

    async def _merge_with_configuration(
        self,
        conversion_result: dict[str, Any],
        config_match: dict[str, Any],
        message: str,
        user_id: int,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Merge saved configuration with new parameters from message.

        Strategy:
        1. Use saved config as base
        2. Override with parameters extracted from current message
        3. Validate merged parameters
        4. Return enhanced result
        """
        from .persistence import get_persistence

        persistence = get_persistence()
        saved_config = persistence.get_tool_configuration(config_match["config_id"])

        if not saved_config:
            return conversion_result

        # Get the tool calls from conversion
        tool_calls = conversion_result.get("tools", [])
        if not tool_calls:
            return conversion_result

        # Merge parameters
        base_tool = tool_calls[0]  # Assume first tool
        saved_params = saved_config["parameters"]
        override_params = config_match.get("parameter_overrides", {})

        # Merge strategy: saved config <-- message extraction <-- explicit overrides
        merged_params = {**saved_params}

        # Override with parameters from current message extraction
        if base_tool.get("parameters"):
            merged_params.update(base_tool["parameters"])

        # Override with explicit overrides from config matching
        merged_params.update(override_params)

        # Validate merged parameters
        is_valid, errors = self.validate_parameters(
            tool_id=saved_config["tool_id"],
            parameters=merged_params,
        )

        if not is_valid:
            logger.warning("Parameter validation failed: %s", errors)
            # Return original conversion with warning
            return {
                **conversion_result,
                "reused_config": None,
                "parameter_overrides": {},
                "warning": f"Configuration parameters invalid: {errors}",
            }

        # Increment usage count
        persistence.record_tool_usage(
            user_id=user_id,
            tool_id=saved_config["tool_id"],
            tool_name=saved_config["tool_name"],
            parameters=merged_params,
        )

        return {
            "intent": f"Reuse {saved_config['name']} configuration",
            "reasoning": f"Matched saved configuration '{saved_config['name']}' and merged with current parameters",
            "tools": [
                {
                    "tool_id": saved_config["tool_id"],
                    "tool_name": saved_config["tool_name"],
                    "parameters": merged_params,
                    "requires_approval": base_tool.get("requires_approval", True),
                }
            ],
            "reused_config": saved_config["config_id"],
            "parameter_overrides": override_params,
            "original_intent": conversion_result.get("intent"),
        }


# Global converter instance
_converter = None


def get_tool_converter(
    llm: BaseChatModel | None = None,
    llm_manager: LLMManager | None = None,
    default_model_id: str | None = None,
) -> ToolConverter:
    """
    Get singleton tool converter instance.

    Args:
        llm: Optional LLM instance
        llm_manager: Optional LLM manager instance
        default_model_id: Optional default model ID

    Returns:
        ToolConverter instance
    """
    global _converter
    if _converter is None:
        _converter = ToolConverter(
            llm=llm,
            llm_manager=llm_manager,
            default_model_id=default_model_id,
        )
    return _converter
