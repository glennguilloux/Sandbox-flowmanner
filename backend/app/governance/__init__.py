"""
Governance Layer - Red Zone

The governance layer orchestrates workflow execution using LangGraph,
manages workflow configurations, and coordinates between the
Yellow Zone (integration) and Blue Zone (workers).
"""

from .controlflow import ControlFlowAgent, get_agent

get_controlflow_agent = get_agent
# Backward compatibility alias
get_controlflow_agent = get_agent
from .tool_handlers import (
    ToolHandlerRegistry,
    WorkerConfig,
    WorkerHandler,
    get_tool_handler_registry,
)
from .workflow_config import SessionState, WorkflowConfig, WorkflowConfigManager

__all__ = [
    # ControlFlow
    "ControlFlowAgent",
    "SessionState",
    "ToolHandlerRegistry",
    "WorkerConfig",
    # Tool Handlers
    "WorkerHandler",
    "WorkflowConfig",
    # Workflow Config
    "WorkflowConfigManager",
    "get_agent",
    "get_tool_handler_registry",
]
