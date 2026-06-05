"""
FastAPI Dependencies for Unified Tool System

Provides dependency injection for the unified tool bridge,
connecting DB-backed tools with the in-memory registry.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.unified_tools import UnifiedToolBridge, get_unified_bridge


def get_tool_bridge(db: Session = Depends(get_db)) -> UnifiedToolBridge:
    """
    FastAPI dependency that provides a configured UnifiedToolBridge.

    Usage in router:
        @router.post("/execute")
        async def execute_tool(
            tool_id: str,
            bridge: UnifiedToolBridge = Depends(get_tool_bridge)
        ):
            result = await bridge.execute_tool(tool_id, params)
            return result
    """
    bridge = get_unified_bridge(db)
    return bridge


def get_tool_bridge_optional(
    db: Session | None = Depends(get_db),
) -> UnifiedToolBridge | None:
    """
    Optional dependency that returns None if no DB session available.
    Useful for endpoints that can work with in-memory tools only.
    """
    if db is None:
        return None
    return get_unified_bridge(db)


def get_tool_executor():
    """
    Dependency for getting the tool executor directly.
    Use when you only need execution without DB persistence.
    """
    from app.services.unified_tools import get_tool_executor

    return get_tool_executor()


def get_tool_registry():
    """
    Dependency for getting the tool registry directly.
    Use when you only need tool discovery without execution.
    """
    from app.services.unified_tools import get_tool_registry

    return get_tool_registry()
