"""
Universal Tool Layer

Unifies every capability (RAG search, workflow execution, agent invocation,
external API calls, ComfyUI generation, n8n workflows) into a single
tool-calling interface that any agent can use.

Components:
- ToolRegistry: In-memory registry for all tools
- ToolExecutor: Execution engine with auth, rate-limiting, retries
- UnifiedToolBridge: Bridge between DB-backed tools and in-memory registry
- UnifiedChainExecutor: Real execution for tool chains
"""

from .chain_executor import (
    ChainExecutionError,
    UnifiedChainExecutor,
    get_chain_executor,
)
from .tool_adapter import ToolAdapter
from .tool_executor import ExecutionResult, ToolExecutor, get_tool_executor
from .tool_registry import Tool, ToolRegistry, get_tool_registry
from .unified_bridge import (
    ToolHandlerBuilder,
    UnifiedToolBridge,
    get_unified_bridge,
)

__all__ = [
    "ChainExecutionError",
    "ExecutionResult",
    "Tool",
    "ToolAdapter",
    "ToolExecutor",
    "ToolHandlerBuilder",
    # Core classes
    "ToolRegistry",
    # Chain execution
    "UnifiedChainExecutor",
    # Bridge components
    "UnifiedToolBridge",
    "get_chain_executor",
    "get_tool_executor",
    # Factory functions
    "get_tool_registry",
    "get_unified_bridge",
]
