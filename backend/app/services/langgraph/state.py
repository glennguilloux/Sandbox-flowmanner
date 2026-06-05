#!/usr/bin/env python3
"""
LangGraph Agent State Management

Defines the state schema for the LangGraph agent, including:
- Conversation history
- Tool execution state
- Human approval workflow
- Tool persistence
"""

import operator
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict


class ToolExecution(TypedDict):
    """Represents a tool execution request"""

    tool_name: str
    tool_id: str
    parameters: dict[str, Any]
    status: str  # 'pending', 'approved', 'rejected', 'executing', 'completed', 'failed'
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    approved_at: str | None
    completed_at: str | None
    requires_approval: bool
    approved_by: int | None  # User ID who approved


class ConversationMessage(TypedDict):
    """Represents a message in the conversation"""

    role: str  # 'user', 'assistant', 'system', 'tool'
    content: str
    timestamp: str
    tool_calls: list[dict[str, Any]] | None
    tool_outputs: list[dict[str, Any]] | None


class AgentState(TypedDict):
    """
    Main state for the LangGraph agent.

    This state is passed between nodes in the graph and contains:
    - Conversation history
    - Current user message
    - Tool execution state
    - Approval workflow state
    - Metadata
    """

    # Conversation
    messages: Annotated[list[ConversationMessage], operator.add]
    current_message: str

    # Tool execution
    pending_tools: list[ToolExecution]
    tool_history: list[ToolExecution]

    # Approval workflow
    awaiting_approval: bool
    current_approval_request: ToolExecution | None

    # Metadata
    session_id: str
    user_id: int | None
    created_at: str
    updated_at: str

    # Agent configuration
    auto_approve_safe_tools: bool
    require_approval_for_all: bool

    # Context
    context: dict[str, Any]


def create_initial_state(
    session_id: str,
    user_id: int | None = None,
    auto_approve_safe_tools: bool = True,
    require_approval_for_all: bool = False,
) -> AgentState:
    """
    Create an initial agent state.

    Args:
        session_id: Unique session identifier
        user_id: Optional user ID
        auto_approve_safe_tools: Whether to auto-approve safe tools
        require_approval_for_all: Whether to require approval for all tools

    Returns:
        Initial AgentState
    """
    now = datetime.now(UTC).isoformat()

    return AgentState(
        messages=[],
        current_message="",
        pending_tools=[],
        tool_history=[],
        awaiting_approval=False,
        current_approval_request=None,
        session_id=session_id,
        user_id=user_id,
        created_at=now,
        updated_at=now,
        auto_approve_safe_tools=auto_approve_safe_tools,
        require_approval_for_all=require_approval_for_all,
        context={},
    )


def add_message_to_state(
    state: AgentState,
    role: str,
    content: str,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_outputs: list[dict[str, Any]] | None = None,
) -> AgentState:
    """
    Add a message to the agent state.

    Args:
        state: Current agent state
        role: Message role ('user', 'assistant', 'system', 'tool')
        content: Message content
        tool_calls: Optional tool calls made
        tool_outputs: Optional tool outputs received

    Returns:
        Updated agent state
    """
    message: ConversationMessage = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(UTC).isoformat(),
        "tool_calls": tool_calls,
        "tool_outputs": tool_outputs,
    }

    state["messages"] = state["messages"] + [message]
    state["updated_at"] = datetime.now(UTC).isoformat()

    return state


def create_tool_execution(
    tool_name: str,
    tool_id: str,
    parameters: dict[str, Any],
    requires_approval: bool = False,
) -> ToolExecution:
    """
    Create a tool execution request.

    Args:
        tool_name: Name of the tool
        tool_id: Unique tool identifier
        parameters: Tool parameters
        requires_approval: Whether this tool requires approval

    Returns:
        ToolExecution object
    """
    return ToolExecution(
        tool_name=tool_name,
        tool_id=tool_id,
        parameters=parameters,
        status="pending",
        result=None,
        error=None,
        created_at=datetime.now(UTC).isoformat(),
        approved_at=None,
        completed_at=None,
        requires_approval=requires_approval,
        approved_by=None,
    )


def update_tool_execution(
    tool: ToolExecution,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    approved_by: int | None = None,
) -> ToolExecution:
    """
    Update a tool execution with new status.

    Args:
        tool: Tool execution to update
        status: New status
        result: Optional result
        error: Optional error message
        approved_by: Optional user ID who approved

    Returns:
        Updated ToolExecution
    """
    tool["status"] = status

    if result is not None:
        tool["result"] = result

    if error is not None:
        tool["error"] = error

    if status == "approved" and approved_by:
        tool["approved_at"] = datetime.now(UTC).isoformat()
        tool["approved_by"] = approved_by

    if status in ["completed", "failed"]:
        tool["completed_at"] = datetime.now(UTC).isoformat()

    return tool


def state_to_dict(state: AgentState) -> dict[str, Any]:
    """
    Convert agent state to dictionary for serialization.

    Args:
        state: Agent state

    Returns:
        Dictionary representation
    """
    return {
        "messages": state["messages"],
        "current_message": state["current_message"],
        "pending_tools": state["pending_tools"],
        "tool_history": state["tool_history"],
        "awaiting_approval": state["awaiting_approval"],
        "current_approval_request": state["current_approval_request"],
        "session_id": state["session_id"],
        "user_id": state["user_id"],
        "created_at": state["created_at"],
        "updated_at": state["updated_at"],
        "auto_approve_safe_tools": state["auto_approve_safe_tools"],
        "require_approval_for_all": state["require_approval_for_all"],
        "context": state["context"],
    }


def dict_to_state(data: dict[str, Any]) -> AgentState:
    """
    Convert dictionary to agent state.

    Args:
        data: Dictionary representation

    Returns:
        Agent state
    """
    return AgentState(
        messages=data.get("messages", []),
        current_message=data.get("current_message", ""),
        pending_tools=data.get("pending_tools", []),
        tool_history=data.get("tool_history", []),
        awaiting_approval=data.get("awaiting_approval", False),
        current_approval_request=data.get("current_approval_request"),
        session_id=data.get("session_id", ""),
        user_id=data.get("user_id"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        auto_approve_safe_tools=data.get("auto_approve_safe_tools", True),
        require_approval_for_all=data.get("require_approval_for_all", False),
        context=data.get("context", {}),
    )
