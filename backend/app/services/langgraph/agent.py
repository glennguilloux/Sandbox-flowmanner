#!/usr/bin/env python3
"""
LangGraph Agent

Main agent implementation that orchestrates:
- State management
- Natural language to tool conversion
- Human approval workflow
- Tool execution
- Persistence
"""

import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .approval_workflow import get_approval_workflow
from .llm_config import get_llm
from .persistence import get_persistence
from .state import (
    AgentState,
    add_message_to_state,
    create_initial_state,
    create_tool_execution,
    state_to_dict,
    update_tool_execution,
)
from .tool_converter import get_tool_converter
from .tool_handlers.comfyui_handler import ComfyUIHandler
from .tool_handlers.integration_handler import (
    ExecuteIntegrationHandler,
    ListIntegrationsHandler,
)
from .tool_handlers.n8n_handler import N8nToolHandler
from .tool_handlers.registry import get_tool_handler_registry

logger = logging.getLogger(__name__)


class LangGraphAgent:
    """
    Main LangGraph agent for workflow automation.

    This agent:
    - Processes natural language requests
    - Converts them to tool calls
    - Manages human approval workflow
    - Executes tools
    - Maintains conversation state
    - Persists sessions and configurations
    """

    def __init__(self, llm, redis_client=None, auto_approve_safe=True, **config):
        self.llm = llm
        self.tool_converter = get_tool_converter(llm)
        self.approval_workflow = get_approval_workflow(
            tool_converter=self.tool_converter,
            auto_approve_safe=auto_approve_safe,
            redis_client=redis_client,
        )
        self.persistence = get_persistence(redis_client)

        # Store configuration for tool handlers
        self.tool_handler_config = config

        # Initialize tool handler registry
        self.tool_registry = get_tool_handler_registry()
        self._register_default_handlers(config)

        # Tool execution handlers (legacy compatibility)
        self.tool_handlers: dict[str, Callable] = {}
        self._initialize_default_handlers()

        # Build the graph
        self.graph = self._build_graph()

        # Checkpointer for state persistence
        self.checkpointer = MemorySaver()

        logger.info("LangGraph agent initialized with tool handlers")

    def _register_default_handlers(self, config: dict[str, Any]):
        """Register default tool handlers with configuration"""

        # Register n8n handler
        n8n_base_url = config.get("n8n_base_url")
        if n8n_base_url:
            self.tool_registry.register_handler("execute_n8n_workflow", N8nToolHandler)
            logger.info('Registered n8n handler with URL: %s', n8n_base_url)

        # Register ComfyUI handler
        comfyui_base_url = config.get("comfyui_base_url")
        if comfyui_base_url:
            self.tool_registry.register_handler(
                "execute_comfyui_workflow", ComfyUIHandler
            )
            logger.info('Registered ComfyUI handler with URL: %s', comfyui_base_url)

        # Register integration handlers (always available — no config needed)
        self.tool_registry.register_handler(
            "list_integrations", ListIntegrationsHandler
        )
        self.tool_registry.register_handler(
            "execute_integration", ExecuteIntegrationHandler
        )
        logger.info("Registered integration tool handlers")

    def _initialize_default_handlers(self):
        """Initialize default tool execution handlers"""
        # These handlers will be connected to actual workflow services
        self.register_tool_handler("execute_n8n_workflow", self._handle_n8n_workflow)
        self.register_tool_handler(
            "execute_comfyui_workflow", self._handle_comfyui_workflow
        )
        self.register_tool_handler(
            "execute_3dglenn_workflow", self._handle_3dglenn_workflow
        )
        self.register_tool_handler("search_workflows", self._handle_search_workflows)
        self.register_tool_handler(
            "get_workflow_details", self._handle_get_workflow_details
        )
        self.register_tool_handler(
            "list_saved_configs", self._handle_list_saved_configs
        )
        self.register_tool_handler("load_saved_config", self._handle_load_saved_config)
        self.register_tool_handler("save_tool_config", self._handle_save_tool_config)

    def register_tool_handler(
        self,
        tool_id: str,
        handler: Callable[[AgentState, dict[str, Any]], dict[str, Any]],
    ):
        """
        Register a tool execution handler.

        Args:
            tool_id: Tool identifier
            handler: Handler function
        """
        self.tool_handlers[tool_id] = handler
        logger.debug('Registered handler for tool: %s', tool_id)

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine"""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("process_input", self._process_input_node)
        workflow.add_node("convert_to_tools", self._convert_to_tools_node)
        workflow.add_node("check_approval", self._check_approval_node)
        workflow.add_node("execute_tools", self._execute_tools_node)
        workflow.add_node("generate_response", self._generate_response_node)

        # Add edges
        workflow.set_entry_point("process_input")
        workflow.add_edge("process_input", "convert_to_tools")
        workflow.add_conditional_edges(
            "convert_to_tools",
            self._should_request_approval,
            {
                "approval": "check_approval",
                "execute": "execute_tools",
                "response": "generate_response",
            },
        )
        workflow.add_conditional_edges(
            "check_approval",
            self._check_approval_result,
            {
                "approved": "execute_tools",
                "rejected": "generate_response",
                "pending": END,
            },
        )
        workflow.add_edge("execute_tools", "generate_response")
        workflow.add_edge("generate_response", END)

        return workflow.compile()

    async def process_message(
        self,
        message: str,
        session_id: str | None = None,
        user_id: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Process a user message through the agent.

        Args:
            message: User message
            session_id: Optional session ID (will create new if not provided)
            user_id: Optional user ID
            context: Optional context information

        Returns:
            Dictionary with response and state
        """
        # Create or load session
        if not session_id:
            session_id = f"session_{uuid.uuid4().hex[:16]}"

        # Load or create state
        state = self.persistence.load_state(session_id)
        if not state:
            state = create_initial_state(
                session_id=session_id,
                user_id=user_id,
                auto_approve_safe_tools=self.approval_workflow.auto_approve_safe,
                require_approval_for_all=False,
            )

        # Update state with new message
        state["current_message"] = message
        state["user_id"] = user_id
        if context:
            state["context"].update(context)

        # Add user message to history
        state = add_message_to_state(state, "user", message)

        # Run the graph
        try:
            result = await self.graph.ainvoke(
                state,
                config={"configurable": {"thread_id": session_id}},
            )
            state = result
        except Exception as e:
            logger.error('Error running graph: %s', e)
            state = add_message_to_state(
                state,
                "assistant",
                f"I encountered an error: {e!s}",
            )

        # Save state
        self.persistence.save_state(state)

        # Return response
        last_message = state["messages"][-1] if state["messages"] else None

        return {
            "success": True,
            "session_id": session_id,
            "response": last_message["content"] if last_message else "",
            "state": state_to_dict(state),
            "awaiting_approval": state["awaiting_approval"],
            "approval_request": state["current_approval_request"],
        }

    async def handle_approval(
        self,
        session_id: str,
        action: str,  # "approve", "reject", "cancel"
        user_id: int,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Handle user approval/rejection action.

        Args:
            session_id: Session ID
            action: Approval action
            user_id: User ID
            reason: Optional reason for rejection

        Returns:
            Dictionary with result
        """
        # Load state
        state = self.persistence.load_state(session_id)
        if not state:
            return {
                "success": False,
                "error": "Session not found",
            }

        # Get current approval request
        approval_request = state["current_approval_request"]
        if not approval_request:
            return {
                "success": False,
                "error": "No pending approval request",
            }

        # Use the approval_id from the approval request
        request_id = approval_request.get("approval_id")
        if not request_id:
            return {
                "success": False,
                "error": "Invalid approval request format",
            }

        # Handle action
        if action == "approve":
            result = self.approval_workflow.approve(request_id, user_id)
        elif action == "reject":
            result = self.approval_workflow.reject(request_id, user_id, reason)
        elif action == "cancel":
            result = self.approval_workflow.cancel(request_id, user_id)
        else:
            return {
                "success": False,
                "error": f"Invalid action: {action}",
            }

        if not result["success"]:
            return result

        # Update state
        state["awaiting_approval"] = False
        state["current_approval_request"] = None

        # If approved, execute the tool
        if action == "approve":
            tool_execution = result["tool_execution"]
            execution_result = self._execute_tool(state, tool_execution)

            # Add tool result message
            state = add_message_to_state(
                state,
                "tool",
                f"Executed {tool_execution['tool_name']}",
                tool_outputs=[execution_result],
            )

        # Save state
        self.persistence.save_state(state)

        return {
            "success": True,
            "action": action,
            "result": result,
            "state": state_to_dict(state),
        }

    # Graph nodes

    async def _process_input_node(self, state: AgentState) -> AgentState:
        """Process user input"""
        logger.debug('Processing input for session %s', state['session_id'])
        return state

    async def _convert_to_tools_node(self, state: AgentState) -> AgentState:
        """Convert natural language to tool calls with configuration reuse"""
        message = state["current_message"]
        history = state["messages"]
        context = state["context"]
        user_id = state.get("user_id")

        # Convert to tools with reuse support
        if user_id:
            # Use enhanced converter with reuse support
            result = await self.tool_converter.convert_with_reuse(
                message=message,
                user_id=user_id,
                conversation_history=history,
                context=context,
            )
        else:
            # Fallback to basic conversion for anonymous users
            result = await self.tool_converter.convert_to_tools(
                message=message,
                conversation_history=history,
                context=context,
            )

        # Store conversion result in context
        state["context"]["tool_conversion"] = result

        # Create tool executions
        for tool_call in result["tools"]:
            tool_def = self.tool_converter.get_tool(tool_call["tool_id"])
            if tool_def:
                tool_execution = create_tool_execution(
                    tool_name=tool_call["tool_name"],
                    tool_id=tool_call["tool_id"],
                    parameters=tool_call["parameters"],
                    requires_approval=tool_call["requires_approval"],
                )
                state["pending_tools"] = state["pending_tools"] + [tool_execution]

        return state

    def _should_request_approval(self, state: AgentState) -> str:
        """Determine if approval is needed"""
        pending_tools = state["pending_tools"]

        if not pending_tools:
            return "response"

        # Check if any tool requires approval
        for tool in pending_tools:
            if tool["requires_approval"]:
                return "approval"

        return "execute"

    async def _check_approval_node(self, state: AgentState) -> AgentState:
        """Create approval request and mark state as awaiting approval"""
        if state["pending_tools"]:
            # Mark as awaiting approval
            state["awaiting_approval"] = True

            # Create approval request for the first pending tool using the approval workflow
            tool = state["pending_tools"][0]
            result = self.approval_workflow.create_approval_request(
                state=state,
                tool_name=tool["tool_name"],
                tool_id=tool["tool_id"],
                parameters=tool["parameters"],
            )

            if result["success"]:
                # The approval workflow has created the request
                # Update state with the approval request
                state["current_approval_request"] = result["approval_request"]
                logger.info('Approval workflow created request for tool %s', tool['tool_name'])
            else:
                logger.warning('Failed to create approval request: %s', result.get('error'))

        return state

    def _check_approval_result(self, state: AgentState) -> str:
        """Check approval result"""
        if state["awaiting_approval"]:
            return "pending"

        # Check if tools were approved or rejected
        for tool in state["pending_tools"]:
            if tool["status"] == "rejected":
                return "rejected"

        return "approved"

    async def _execute_tools_node(self, state: AgentState) -> AgentState:
        """Execute approved tools"""
        for tool in state["pending_tools"]:
            if tool["status"] in ["pending", "approved"]:
                # Execute tool
                result = await self._execute_tool(state, tool)

                # Update tool execution
                if result["success"]:
                    tool = update_tool_execution(
                        tool,
                        status="completed",
                        result=result,
                    )
                else:
                    tool = update_tool_execution(
                        tool,
                        status="failed",
                        error=result.get("error", "Execution failed"),
                    )

                # Add to history
                state["tool_history"] = state["tool_history"] + [tool]

                # Record usage
                if state["user_id"]:
                    self.persistence.record_tool_usage(
                        user_id=state["user_id"],
                        tool_id=tool["tool_id"],
                        tool_name=tool["tool_name"],
                        parameters=tool["parameters"],
                    )

        # Clear pending tools
        state["pending_tools"] = []

        return state

    async def _generate_response_node(self, state: AgentState) -> AgentState:
        """Generate response to user"""
        conversion_result = state["context"].get("tool_conversion", {})

        # Build response
        if conversion_result.get("missing_info"):
            response = f"I need more information: {', '.join(conversion_result['missing_info'])}"
        elif state["tool_history"]:
            # Summarize tool executions
            completed = [t for t in state["tool_history"] if t["status"] == "completed"]
            failed = [t for t in state["tool_history"] if t["status"] == "failed"]

            parts = []
            if completed:
                parts.append(f"Successfully executed {len(completed)} tool(s)")
            if failed:
                parts.append(f"Failed to execute {len(failed)} tool(s)")

            response = ". ".join(parts)
        else:
            response = conversion_result.get("reasoning", "I understand your request.")

        # Add assistant message
        state = add_message_to_state(state, "assistant", response)

        return state

    def _execute_tool(
        self,
        state: AgentState,
        tool: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single tool using async tool handlers"""
        tool_id = tool["tool_id"]
        parameters = tool["parameters"]

        # Build execution context
        context = {
            "user_context": {
                "user_id": state.get("user_id"),
                "username": state.get("username"),
                "email": state.get("email"),
                "is_admin": state.get("is_admin", False),
            }
        }

        # Build tool call
        tool_call = {"tool_id": tool_id, "parameters": parameters, "context": context}

        # Execute using async handler
        import asyncio

        result = asyncio.run(self.execute_tool_call(tool_call))
        return result

    async def execute_tool_call(
        self, tool_call: dict[str, Any], user_context: dict[str, Any] = None
    ) -> dict[str, Any]:
        """
        Execute tool call using registered handlers with permission checking

        Args:
            tool_call: Tool call dictionary with tool_id and parameters
            user_context: User context for permission checking

        Returns:
            Execution result
        """
        tool_id = tool_call.get("tool_id")
        parameters = tool_call.get("parameters", {})
        context = tool_call.get("context", {})

        if not tool_id:
            return {"success": False, "error": "No tool_id specified"}

        # Get handler from registry with configuration
        handler_config = {}
        if tool_id == "execute_n8n_workflow":
            handler_config = {
                "n8n_base_url": self.tool_handler_config.get("n8n_base_url"),
                "api_key": self.tool_handler_config.get("n8n_api_key"),
            }
        elif tool_id == "execute_comfyui_workflow":
            handler_config = {
                "comfyui_base_url": self.tool_handler_config.get("comfyui_base_url"),
                "client_id": self.tool_handler_config.get(
                    "comfyui_client_id", "workflow-agent"
                ),
            }

        handler = self.tool_registry.get_handler(tool_id, **handler_config)
        if not handler:
            return {
                "success": False,
                "error": f"No handler registered for tool: {tool_id}",
            }

        # Check user permissions if user_context provided
        if user_context:
            from .auth import UserContext

            # Check if user_context is a dict or UserContext instance
            if isinstance(user_context, dict):
                # Create UserContext from dict
                auth_user_context = UserContext(
                    user_id=user_context.get("user_id", 0),
                    username=user_context.get("username", ""),
                    email=user_context.get("email", ""),
                    is_admin=user_context.get("is_admin", False),
                    permissions=user_context.get("permissions", {}),
                )
            else:
                auth_user_context = user_context

            # Check tool access permission
            if not auth_user_context.can_access_tool(tool_id):
                return {
                    "success": False,
                    "error": f"User does not have permission to access tool: {tool_id}",
                    "tool_id": tool_id,
                    "user_id": auth_user_context.user_id,
                }

            # Add user context to execution context
            if context is None:
                context = {}
            context["user_context"] = auth_user_context.to_dict()

        # Execute tool
        result = await handler.safe_execute(parameters, context)
        return result

    # Default tool handlers

    def _handle_n8n_workflow(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle n8n workflow execution"""
        from app.services.langchain.tools.n8n_agent_tool_prod import (
            execute_n8n_workflow,
        )

        workflow_id = parameters.get("workflow_id")
        if not workflow_id:
            return {"success": False, "error": "workflow_id is required"}

        try:
            result = execute_n8n_workflow(
                workflow_id=workflow_id, parameters=parameters.get("parameters", {})
            )
            return {"success": True, "result": json.loads(result)}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON response: {e}"}
        except Exception as e:
            logger.error('Error executing n8n workflow: %s', e)
            return {"success": False, "error": str(e)}

    def _handle_comfyui_workflow(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle ComfyUI workflow execution"""
        from app.services.langchain.tools.comfyui_agent_tool_prod import (
            generate_hero_background,
        )

        prompt = parameters.get("prompt")
        if not prompt:
            return {"success": False, "error": "prompt is required"}

        try:
            result = generate_hero_background(
                prompt=prompt, style=parameters.get("style", "modern")
            )
            return {"success": True, "result": json.loads(result)}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON response: {e}"}
        except Exception as e:
            logger.error('Error executing ComfyUI workflow: %s', e)
            return {"success": False, "error": str(e)}

    def _handle_3dglenn_workflow(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle 3Dglenn workflow execution"""
        from app.services.langchain.tools.comfyui_agent_tool_prod import (
            generate_3d_model,
        )

        description = parameters.get("description")
        if not description:
            return {"success": False, "error": "description is required"}

        try:
            result = generate_3d_model(
                description=description, style=parameters.get("style", "modern")
            )
            return {"success": True, "result": json.loads(result)}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON response: {e}"}
        except Exception as e:
            logger.error('Error executing 3Dglenn workflow: %s', e)
            return {"success": False, "error": str(e)}

    def _handle_search_workflows(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle workflow search"""
        from app.services.langchain.tools.n8n_agent_tool_prod import list_n8n_workflows

        search_query = parameters.get("search_query")

        try:
            result = list_n8n_workflows(search_query=search_query)
            return {"success": True, "result": json.loads(result)}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON response: {e}"}
        except Exception as e:
            logger.error('Error searching workflows: %s', e)
            return {"success": False, "error": str(e)}

    def _handle_get_workflow_details(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle getting workflow details"""
        from app.services.langchain.tools.n8n_agent_tool_prod import get_workflow_info

        workflow_id = parameters.get("workflow_id")
        if not workflow_id:
            return {"success": False, "error": "workflow_id is required"}

        try:
            result = get_workflow_info(workflow_id=workflow_id)
            return {"success": True, "result": json.loads(result)}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON response: {e}"}
        except Exception as e:
            logger.error('Error getting workflow details: %s', e)
            return {"success": False, "error": str(e)}

    def _handle_list_saved_configs(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle listing saved configurations"""
        if not state["user_id"]:
            return {
                "success": False,
                "error": "User ID required",
            }

        configs = self.persistence.list_user_configurations(
            user_id=state["user_id"],
            tool_id=parameters.get("tool_id"),
        )

        return {
            "success": True,
            "message": f"Found {len(configs)} saved configurations",
            "configurations": configs,
        }

    def _handle_load_saved_config(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle loading saved configuration"""
        config = self.persistence.get_tool_configuration(parameters["config_id"])

        if not config:
            return {
                "success": False,
                "error": "Configuration not found",
            }

        return {
            "success": True,
            "message": "Configuration loaded",
            "configuration": config,
        }

    def _handle_save_tool_config(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle saving tool configuration"""
        if not state["user_id"]:
            return {
                "success": False,
                "error": "User ID required",
            }

        config_id = self.persistence.save_tool_configuration(
            user_id=state["user_id"],
            tool_id=parameters["tool_id"],
            tool_name=parameters.get("tool_name", ""),
            name=parameters["name"],
            description=parameters.get("description", ""),
            parameters=parameters["parameters"],
        )

        if not config_id:
            return {
                "success": False,
                "error": "Failed to save configuration",
            }

        return {
            "success": True,
            "message": "Configuration saved",
            "config_id": config_id,
        }

    async def close(self):
        """Close agent and all handlers"""
        if hasattr(self, "tool_registry"):
            await self.tool_registry.close_all()


# Global agent instance
_agent = None


def get_agent(
    llm=None,
    redis_client=None,
    auto_approve_safe: bool = True,
    require_approval_for_all: bool = False,
    **config,
) -> LangGraphAgent:
    """
    Get singleton agent instance.

    Args:
        llm: Optional LLM instance. If None, will be auto-initialized.
        redis_client: Optional Redis client
        auto_approve_safe: Whether to auto-approve safe tools
        require_approval_for_all: Whether to require approval for all tools
        **config: Additional configuration for tool handlers

    Returns:
        LangGraphAgent instance
    """
    global _agent
    if _agent is None:
        # Auto-initialize LLM if not provided
        if llm is None:
            try:
                llm = get_llm()
                if llm is None:
                    raise ValueError(
                        "No LLM available. Please configure an LLM or pass one to get_agent."
                    )
                logger.info("Auto-initialized LLM for LangGraph agent")
            except Exception as e:
                logger.error('Failed to auto-initialize LLM: %s', e)
                raise ValueError(f"Failed to initialize LLM: {e}")

        _agent = LangGraphAgent(
            llm=llm,
            redis_client=redis_client,
            auto_approve_safe=auto_approve_safe,
            require_approval_for_all=require_approval_for_all,
            **config,
        )
    return _agent
