#!/usr/bin/env python3
"""
ControlFlow State Management
"""

import operator
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict


class ToolExecution(TypedDict):
    tool_name: str
    tool_id: str
    parameters: dict[str, Any]
    status: str
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    approved_at: str | None
    completed_at: str | None
    requires_approval: bool
    approved_by: int | None


class ConversationMessage(TypedDict):
    role: str
    content: str
    timestamp: str
    tool_calls: list[dict[str, Any]] | None
    tool_outputs: list[dict[str, Any]] | None


class AgentState(TypedDict):
    messages: Annotated[list[ConversationMessage], operator.add]
    current_message: str
    pending_tools: list[ToolExecution]
    tool_history: list[ToolExecution]
    awaiting_approval: bool
    current_approval_request: ToolExecution | None
    session_id: str
    user_id: int | None
    created_at: str
    updated_at: str
    auto_approve_safe_tools: bool
    require_approval_for_all: bool
    context: dict[str, Any]


def create_initial_state(
    session_id: str,
    user_id: int | None = None,
    auto_approve_safe_tools: bool = True,
    require_approval_for_all: bool = False,
) -> AgentState:
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
