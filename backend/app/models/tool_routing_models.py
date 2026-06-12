"""Tool Routing Models — Q2-Q3 Chunk 3.

Pydantic models for the sparse tool router:
- ToolScore: Per-tool score breakdown with weighted components
- ToolRouteResult: The full routing decision (candidate set + metadata)
- ToolRouteDecidedEvent: Audit event payload for substrate event log
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ToolScore(BaseModel):
    """Score breakdown for a single tool against a task."""

    tool_id: str = Field(..., description="Tool identifier")
    score: float = Field(..., ge=0.0, le=1.0, description="Final weighted score")
    components: dict[str, float] = Field(
        default_factory=dict,
        description="Score components: text_similarity, category_match, memory_hint, permission_ok",
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Human-readable reasons for the score",
    )


class ToolRouteResult(BaseModel):
    """Result of a tool routing decision."""

    tools: list[dict] = Field(
        default_factory=list,
        description="Selected ToolDefinition dicts (to_dict() output)",
    )
    mode: Literal["sparse", "fallback-full-registry"] = Field(
        ...,
        description="'sparse' when confidence is above threshold, 'fallback-full-registry' otherwise",
    )
    top_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Highest score among all candidates considered",
    )
    reasons: dict[str, str] = Field(
        default_factory=dict,
        description="Per-tool_id reason string for why it was included",
    )
    candidates_considered: int = Field(
        ...,
        ge=0,
        description="Total number of tools scored",
    )
    candidates_returned: int = Field(
        ...,
        ge=0,
        description="Number of tools in the final candidate set",
    )
    task_text_hash: str = Field(
        ...,
        description="SHA-256 hex digest of normalized task text (for audit privacy)",
    )
    scores: list[ToolScore] = Field(
        default_factory=list,
        description="Per-tool score details (for debugging/admin)",
    )


class ToolRouteDecidedEvent(BaseModel):
    """Audit event payload emitted to the substrate event log.

    Note: task_text is NEVER included — only the SHA-256 hash.
    """

    mode: Literal["sparse", "fallback-full-registry"]
    top_score: float
    candidates_considered: int
    candidates_returned: int
    selected_tool_ids: list[str]
    task_text_hash: str
    workspace_id: str
    user_id: int
    mission_id: str | None = None
