"""
Unified Tools REST API — exposes the ToolRegistry via HTTP endpoints.

All tools (browser, topology, terminal, etc.) are discoverable and executable
through a single /api/tools/* interface. No changes to base.py needed.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user, get_current_user_optional
from app.models.user import User
from app.tools.base import get_tool_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolSummary(BaseModel):
    tool_id: str
    name: str
    description: str
    category: str
    tags: list[str]
    input_schema: dict
    requires_auth: bool


class ToolDetail(BaseModel):
    tool_id: str
    name: str
    description: str
    category: str
    tags: list[str]
    input_schema: dict
    output_schema: dict
    requires_auth: bool
    timeout_seconds: int
    rate_limit: int | None = None


class ToolExecutionResult(BaseModel):
    tool_id: str
    success: bool
    result: dict | None = None
    error: str | None = None
    execution_time_ms: float = 0.0
    tokens_used: int = 0
    cost_usd: float = 0.0


def _tool_to_summary(tool) -> ToolSummary:
    return ToolSummary(
        tool_id=tool.tool_id,
        name=tool.name,
        description=tool.description,
        category=tool.category,
        tags=tool.tags,
        input_schema=tool.metadata.input_schema,
        requires_auth=tool.metadata.requires_auth,
    )


def _tool_to_detail(tool) -> ToolDetail:
    return ToolDetail(
        tool_id=tool.tool_id,
        name=tool.name,
        description=tool.description,
        category=tool.category,
        tags=tool.tags,
        input_schema=tool.metadata.input_schema,
        output_schema=tool.metadata.output_schema,
        requires_auth=tool.metadata.requires_auth,
        timeout_seconds=tool.metadata.timeout_seconds,
        rate_limit=tool.metadata.rate_limit,
    )


class ToolStats(BaseModel):
    """Public tool statistics — no auth required."""

    total_tools: int
    categories: list[str]
    category_counts: dict[str, int]


@router.get("/stats", response_model=ToolStats)
async def get_tool_stats(
    current_user: User | None = Depends(get_current_user_optional),
):
    """Return tool count statistics. Public endpoint — no auth required."""
    registry = get_tool_registry()
    tools = registry.list_all()

    category_counts: dict[str, int] = {}
    for t in tools:
        cat = t.category or "uncategorized"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    return ToolStats(
        total_tools=len(tools),
        categories=sorted(category_counts.keys()),
        category_counts=category_counts,
    )


@router.get("/", response_model=list[ToolSummary])
async def list_tools(
    category: str | None = Query(None, description="Filter by category"),
    current_user: User = Depends(get_current_user),
):
    """List all registered tools, optionally filtered by category."""
    registry = get_tool_registry()
    tools = registry.list_all(category=category)
    return [_tool_to_summary(t) for t in tools]


@router.get("/categories", response_model=list[str])
async def list_categories(
    current_user: User = Depends(get_current_user),
):
    """Return all tool categories."""
    registry = get_tool_registry()
    return registry.list_categories()


@router.get("/search", response_model=list[ToolSummary])
async def search_tools(
    q: str = Query(..., min_length=1, description="Search query"),
    current_user: User = Depends(get_current_user),
):
    """Search tools by name, description, tags, or category."""
    registry = get_tool_registry()
    tools = registry.search(q)
    return [_tool_to_summary(t) for t in tools]


@router.get("/{tool_id}", response_model=ToolDetail)
async def get_tool(
    tool_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get full metadata for a specific tool."""
    registry = get_tool_registry()
    tool = registry.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_id}")
    return _tool_to_detail(tool)


@router.post("/{tool_id}/execute", response_model=ToolExecutionResult)
async def execute_tool(
    tool_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
):
    """
    Execute a tool by ID with JSON input body.

    The body is passed to the tool's execute() method along with
    a 'context' dict containing the user_id.
    """
    registry = get_tool_registry()
    tool = registry.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_id}")

    # Merge user context into input
    input_data = {**body, "context": {"user_id": str(current_user.id)}}

    try:
        result = await tool.execute(input_data)
        return ToolExecutionResult(
            tool_id=result.tool_id,
            success=result.success,
            result=result.result,
            error=result.error,
            execution_time_ms=result.execution_time_ms,
            tokens_used=result.tokens_used,
            cost_usd=result.cost_usd,
        )
    except Exception as e:
        logger.error(f"Tool {tool_id} execution error: {e}", exc_info=True)
        return ToolExecutionResult(
            tool_id=tool_id,
            success=False,
            error=str(e),
        )
