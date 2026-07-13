#!/usr/bin/env python3
"""
LangGraph Agent (Governance Layer - ControlFlow)

Main agent implementation that orchestrates:
- State management
- Natural language to tool conversion
- Human approval workflow
- Tool execution via WorkerHandler (Celery workers)
- Persistence

Migrated from services/langgraph/agent.py to governance/controlflow/
"""

import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .state import (
    AgentState,
    add_message_to_state,
    create_initial_state,
    create_tool_execution,
    dict_to_state,
    state_to_dict,
    update_tool_execution,
)

logger = logging.getLogger(__name__)


class ControlFlowAgent:
    """
    Main LangGraph agent for workflow automation in governance layer.

    This agent:
    - Processes natural language requests
    - Converts them to tool calls
    - Manages human approval workflow
    - Executes tools via WorkerHandler (Celery workers)
    - Maintains conversation state
    - Persists sessions and configurations
    """

    def __init__(self, llm, redis_client=None, auto_approve_safe=True, **config):
        self.llm = llm

        # Import dependencies
        from ..tool_handlers import WorkerHandler
        from ..workflow_config import WorkflowConfigManager

        # Initialize WorkerHandler for Celery worker tasks
        self.worker_handler = WorkerHandler()

        # Initialize config manager
        self.config_manager = WorkflowConfigManager(redis_client=redis_client)

        # Tool execution handlers
        self.tool_handlers: dict[str, Callable] = {}
        self._initialize_default_handlers()

        # Checkpointer for state persistence (created before graph build)
        self.checkpointer = MemorySaver()

        # Build the graph (pass checkpointer to compile)
        self.graph = self._build_graph()

        logger.info("ControlFlow agent initialized with WorkerHandler")

    def _initialize_default_handlers(self):
        """Initialize default tool execution handlers"""
        # Register worker task handlers
        self.register_tool_handler("execute_worker_task", self._handle_worker_task)
        self.register_tool_handler("execute_chain", self._handle_chain)
        self.register_tool_handler("get_task_status", self._handle_get_task_status)
        self.register_tool_handler("cancel_task", self._handle_cancel_task)

        # Register workflow config handlers
        self.register_tool_handler("get_workflow_config", self._handle_get_workflow_config)
        self.register_tool_handler("save_workflow_config", self._handle_save_workflow_config)
        self.register_tool_handler("list_workflow_configs", self._handle_list_workflow_configs)

        # Register legacy handlers for backward compatibility
        self.register_tool_handler("execute_n8n_workflow", self._handle_n8n_workflow)
        self.register_tool_handler("execute_comfyui_workflow", self._handle_comfyui_workflow)

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
        logger.debug("Registered handler for tool: %s", tool_id)

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
        workflow.add_edge(START, "process_input")
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

        return workflow.compile(checkpointer=self.checkpointer)

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
        state = self._load_state(session_id)
        if not state:
            state = create_initial_state(
                session_id=session_id,
                user_id=user_id,
                auto_approve_safe_tools=True,
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
            logger.error("Error running graph: %s", e)
            state = add_message_to_state(
                state,
                "assistant",
                f"I encountered an error: {e!s}",
            )

        # Save state
        self._save_state(state)

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

    def _load_state(self, session_id: str) -> AgentState | None:
        """Load state from config manager"""
        try:
            data = self.config_manager.get_session_state(session_id)
            if data:
                return dict_to_state(data)
        except Exception as e:
            logger.error("Failed to load state: %s", e)
        return None

    def _save_state(self, state: AgentState):
        """Save state to config manager"""
        try:
            self.config_manager.save_session_state(state["session_id"], state_to_dict(state))
        except Exception as e:
            logger.error("Failed to save state: %s", e)

    # Graph nodes

    async def _process_input_node(self, state: AgentState) -> AgentState:
        """Process user input"""
        logger.debug("Processing input for session %s", state["session_id"])
        return state

    async def _convert_to_tools_node(self, state: AgentState) -> AgentState:
        """Convert natural language to tool calls"""
        message = state["current_message"]
        context = state["context"]

        # Simple tool conversion for worker tasks
        result = self._simple_tool_conversion(message, context)

        # Create tool executions
        for tool_call in result["tools"]:
            tool_execution = create_tool_execution(
                tool_name=tool_call["tool_name"],
                tool_id=tool_call["tool_id"],
                parameters=tool_call["parameters"],
                requires_approval=tool_call["requires_approval"],
            )
            state["pending_tools"] = state["pending_tools"] + [tool_execution]

        return state

    def _simple_tool_conversion(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        """Simple tool conversion based on keywords"""
        message_lower = message.lower()
        tools = []

        # Detect worker task execution
        if "execute" in message_lower and ("step" in message_lower or "task" in message_lower):
            step_name = None
            for step in [
                "step_2a_generate_request",
                "step_2b_process_response",
                "data_fetch",
                "data_transform",
            ]:
                if step in message_lower:
                    step_name = step
                    break

            if step_name:
                tools.append(
                    {
                        "tool_id": "execute_worker_task",
                        "tool_name": "Execute Worker Task",
                        "parameters": {"action": step_name},
                        "requires_approval": True,
                    }
                )

        # Detect workflow config operations
        elif "save config" in message_lower or "save workflow" in message_lower:
            tools.append(
                {
                    "tool_id": "save_workflow_config",
                    "tool_name": "Save Workflow Config",
                    "parameters": {},
                    "requires_approval": True,
                }
            )

        elif "get config" in message_lower or "load config" in message_lower:
            tools.append(
                {
                    "tool_id": "get_workflow_config",
                    "tool_name": "Get Workflow Config",
                    "parameters": {},
                    "requires_approval": False,
                }
            )

        elif "list config" in message_lower or "list workflows" in message_lower:
            tools.append(
                {
                    "tool_id": "list_workflow_configs",
                    "tool_name": "List Workflow Configs",
                    "parameters": {},
                    "requires_approval": False,
                }
            )

        return {
            "tools": tools,
            "missing_info": [],
            "reasoning": f"Converted message to {len(tools)} tool(s)",
        }

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

            # Create approval request for first pending tool
            tool = state["pending_tools"][0]
            approval_id = f"approval_{uuid.uuid4().hex[:16]}"

            state["current_approval_request"] = {  # type: ignore[typeddict-item]
                "approval_id": approval_id,
                "tool_execution": tool,
                "created_at": datetime.now(UTC).isoformat(),
            }

            logger.info(
                "Created approval request %s for tool %s",
                approval_id,
                tool["tool_name"],
            )

        return state

    def _check_approval_result(self, state: AgentState) -> str:
        """Check approval result.

        Returns "pending" while awaiting a human decision. The decision is
        recorded by the explicit approval callback (``resolve_approval``), which
        flips the tool status and clears ``awaiting_approval``. Until that
        callback runs, we MUST stay in "pending" — we never infer resolution
        here, because doing so would mask a missing human-in-the-loop decision.
        """
        if state["awaiting_approval"]:
            return "pending"

        # Check if tools were approved or rejected
        for tool in state["pending_tools"]:
            if tool["status"] == "rejected":
                return "rejected"

        return "approved"

    async def resolve_approval(
        self,
        session_id: str,
        decision: str,
        approved_by: int | None = None,
        tool_index: int | None = None,
    ) -> dict[str, Any]:
        """Record a human approval decision and resume the flow.

        .. warning::
            STATUS — UN-WIRED SCAFFOLDING.

            This is the *correct* approval-callback implementation (it explicitly
            flips tool status, clears ``awaiting_approval``/``current_approval_request``,
            and resumes the graph from the same checkpointer thread). However, as of
            2026-07-13 NO production caller reaches it:

            - ``app/api/v1/governance.py`` exposes an endpoint that calls this method,
              but that route has no live client (the real human-in-the-loop path is the
              HITL inbox, which does not yet invoke ``resolve_approval``).
            - The graph dead-ends at ``_check_approval_result`` returning "pending"
              (routing to END), so without an external decision recorded here the flow
              stalls. Until the HITL inbox is wired to call this method, approvals are
              effectively unresolvable in production.

            Do NOT treat a green import/test of this method as proof the approval path
            works end-to-end.

        This is the ACTUAL approval callback path — the missing link that the
        earlier defensive re-derivation was masking. The graph dead-ends at
        ``_check_approval_result`` returning "pending" (which routes to END),
        so the only way to progress is an external decision recorded here:

          1. Load the session state.
          2. Flip the relevant tool(s) to "approved"/"rejected" via
             ``update_tool_execution`` (records approved_at / approved_by).
          3. Clear ``awaiting_approval`` + ``current_approval_request`` — this is
             the explicit flag reset the old code inferred defensively.
          4. Re-invoke the graph with the SAME checkpointer thread_id so it
             continues past the pending->END dead-end (executes approved tools
             or generates a rejection response).

        Args:
            session_id: The agent session/thread id.
            decision: "approved" or "rejected".
            approved_by: User id of the human decision-maker (for audit).
            tool_index: Optional index into pending_tools. If omitted, all
                approval-required tools are set to the same decision.
        """
        if decision not in ("approved", "rejected"):
            raise ValueError(f"decision must be 'approved' or 'rejected', got {decision!r}")

        state = self._load_state(session_id)
        if not state:
            raise ValueError(f"No agent session found for session_id={session_id}")
        if not state["awaiting_approval"]:
            raise ValueError(f"Session {session_id} is not currently awaiting approval")

        targets = [state["pending_tools"][tool_index]] if tool_index is not None else state["pending_tools"]
        for tool in targets:
            if tool["requires_approval"]:
                tool = update_tool_execution(tool, status=decision, approved_by=approved_by)

        # Explicit flag reset — this is the real callback, not inference.
        state["awaiting_approval"] = False
        state["current_approval_request"] = None
        self._save_state(state)

        # Resume the graph from the same checkpointer thread so it continues
        # past the pending->END dead-end.
        try:
            result = await self.graph.ainvoke(
                state,
                config={"configurable": {"thread_id": session_id}},
            )
            state = result
        except Exception as e:
            logger.error("Error resuming graph after approval: %s", e)
            state = add_message_to_state(state, "assistant", f"I encountered an error resuming: {e!s}")

        self._save_state(state)
        return {
            "success": True,
            "session_id": session_id,
            "decision": decision,
            "awaiting_approval": state["awaiting_approval"],
            "approval_request": state["current_approval_request"],
            "state": state_to_dict(state),
        }

    async def _execute_tools_node(self, state: AgentState) -> AgentState:
        """Execute approved tools"""
        for tool in state["pending_tools"]:
            # Only execute tools with a definitive go-ahead.
            # - "approved" tools run.
            # - "pending" tools that do NOT require approval run (happy path).
            # - "pending" tools that REQUIRE approval must wait (not executed).
            # - "rejected" tools must never run.
            should_execute = tool["status"] == "approved" or (
                tool["status"] == "pending" and not tool["requires_approval"]
            )
            if not should_execute:
                continue

            # Execute tool
            result = self._execute_tool(state, tool)  # type: ignore[arg-type]

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

        # Clear pending tools
        state["pending_tools"] = []

        return state

    async def _generate_response_node(self, state: AgentState) -> AgentState:
        """Generate response to user"""
        # Build response
        if state["tool_history"]:
            # Summarize tool executions
            completed = [t for t in state["tool_history"] if t["status"] == "completed"]
            failed = [t for t in state["tool_history"] if t["status"] == "failed"]

            parts = []
            if completed:
                parts.append(f"Successfully executed {len(completed)} task(s)")
            if failed:
                parts.append(f"Failed to execute {len(failed)} task(s)")

            response = ". ".join(parts) if parts else "I processed your request."
        else:
            response = "I understand your request, but no tools were executed."

        # Add assistant message
        state = add_message_to_state(state, "assistant", response)

        return state

    def _execute_tool(
        self,
        state: AgentState,
        tool: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single tool"""
        tool_id = tool["tool_id"]
        parameters = tool["parameters"]

        # Get handler
        handler = self.tool_handlers.get(tool_id)
        if not handler:
            return {
                "success": False,
                "error": f"No handler registered for tool: {tool_id}",
            }

        # Execute handler
        try:
            result = handler(state, parameters)  # type: ignore[misc]
            return result
        except Exception as e:
            logger.error("Tool execution failed: %s", e)
            return {"success": False, "error": str(e)}

    # Default tool handlers

    def _handle_worker_task(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle worker task execution via WorkerHandler"""
        action = parameters.get("action")
        params = parameters.get("params", {})

        if not action:
            return {"success": False, "error": "action is required"}

        try:
            result = self.worker_handler.execute(action=action, params=params)
            return result
        except Exception as e:
            logger.error("Worker task execution failed: %s", e)
            return {"success": False, "error": str(e)}

    def _handle_chain(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle chain execution via WorkerHandler"""
        actions = parameters.get("actions", [])
        params_list = parameters.get("params_list", [])

        if not actions:
            return {"success": False, "error": "actions is required"}

        try:
            result = self.worker_handler.execute_chain(actions=actions, params_list=params_list)
            return result
        except Exception as e:
            logger.error("Chain execution failed: %s", e)
            return {"success": False, "error": str(e)}

    def _handle_get_task_status(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle getting task status"""
        task_id = parameters.get("task_id")

        if not task_id:
            return {"success": False, "error": "task_id is required"}

        try:
            result = self.worker_handler.get_task_status(task_id)
            return result
        except Exception as e:
            logger.error("Get task status failed: %s", e)
            return {"success": False, "error": str(e)}

    def _handle_cancel_task(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle cancelling a task"""
        task_id = parameters.get("task_id")

        if not task_id:
            return {"success": False, "error": "task_id is required"}

        try:
            result = self.worker_handler.cancel_task(task_id)
            return {"success": result}
        except Exception as e:
            logger.error("Cancel task failed: %s", e)
            return {"success": False, "error": str(e)}

    def _handle_get_workflow_config(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle getting workflow config"""
        config_id = parameters.get("config_id")
        workflow_id = parameters.get("workflow_id")

        try:
            if config_id:
                result = self.config_manager.get_config(config_id)
            elif workflow_id:
                result = self.config_manager.get_workflow_config(workflow_id)
            else:
                return {
                    "success": False,
                    "error": "config_id or workflow_id is required",
                }
            return result
        except Exception as e:
            logger.error("Get workflow config failed: %s", e)
            return {"success": False, "error": str(e)}

    def _handle_save_workflow_config(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle saving workflow config"""
        workflow_id = parameters.get("workflow_id")
        config_data = parameters.get("config_data", {})
        name = parameters.get("name")

        if not workflow_id:
            return {"success": False, "error": "workflow_id is required"}

        try:
            result = self.config_manager.save_config(workflow_id=workflow_id, config_data=config_data, name=name)
            return result
        except Exception as e:
            logger.error("Save workflow config failed: %s", e)
            return {"success": False, "error": str(e)}

    def _handle_list_workflow_configs(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle listing workflow configs"""
        workflow_id = parameters.get("workflow_id")

        try:
            result = self.config_manager.list_configs(workflow_id=workflow_id)
            return result
        except Exception as e:
            logger.error("List workflow configs failed: %s", e)
            return {"success": False, "error": str(e)}

    def _handle_n8n_workflow(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle n8n workflow execution (legacy)"""
        from app.services.langchain.tools.n8n_agent_tool_prod import (
            execute_n8n_workflow,
        )

        workflow_id = parameters.get("workflow_id")
        if not workflow_id:
            return {"success": False, "error": "workflow_id is required"}

        try:
            result = execute_n8n_workflow(workflow_id=workflow_id, parameters=parameters.get("parameters", {}))
            return {"success": True, "result": json.loads(result)}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON response: {e}"}
        except Exception as e:
            logger.error("Error executing n8n workflow: %s", e)
            return {"success": False, "error": str(e)}

    def _handle_comfyui_workflow(
        self,
        state: AgentState,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle ComfyUI workflow execution (legacy)"""
        from app.services.langchain.tools.comfyui_agent_tool_prod import (
            generate_hero_background,
        )

        prompt = parameters.get("prompt")
        if not prompt:
            return {"success": False, "error": "prompt is required"}

        try:
            result = generate_hero_background(prompt=prompt, style=parameters.get("style", "modern"))
            return {"success": True, "result": json.loads(result)}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON response: {e}"}
        except Exception as e:
            logger.error("Error executing ComfyUI workflow: %s", e)
            return {"success": False, "error": str(e)}

    async def close(self):
        """Close agent and handlers"""
        logger.info("ControlFlow agent closed")


# Global agent instance
_agent = None


def get_agent(
    llm=None,
    redis_client=None,
    auto_approve_safe: bool = True,
    require_approval_for_all: bool = False,
    **config,
) -> ControlFlowAgent:
    """
    Get singleton agent instance.

    Args:
        llm: Optional LLM instance
        redis_client: Optional Redis client
        auto_approve_safe: Whether to auto-approve safe tools
        require_approval_for_all: Whether to require approval for all tools
        **config: Additional configuration for tool handlers

    Returns:
        ControlFlowAgent instance
    """
    global _agent
    if _agent is None:
        _agent = ControlFlowAgent(
            llm=llm,
            redis_client=redis_client,
            auto_approve_safe=auto_approve_safe,
            require_approval_for_all=require_approval_for_all,
            **config,
        )
    return _agent
