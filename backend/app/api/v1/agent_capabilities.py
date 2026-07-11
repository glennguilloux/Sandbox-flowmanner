"""
Agent Capabilities API — capability-aware agent discovery and matching.

Extends the existing agent registry with semantic search, task-type filtering,
and confidence-scored matching for multi-agent orchestration.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.agent_registry_service import AgentRegistryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-capabilities", tags=["agent-capabilities"])


# ── Request / Response schemas ──────────────────────────────────────────


class RegisterCapabilityRequest(BaseModel):
    agent_id: str
    name: str
    description: str = ""
    task_types: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    confidence_score: float = Field(0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] | None = None


class MatchRequest(BaseModel):
    task_description: str = Field(..., min_length=1, max_length=5000)
    task_type: str | None = None
    required_tools: list[str] = Field(default_factory=list)


class DiscoverRequest(BaseModel):
    task_description: str = Field(..., min_length=1, max_length=5000)
    task_type: str | None = None
    limit: int = Field(5, ge=1, le=20)


# ── Endpoints ───────────────────────────────────────────────────────────


@router.post("/register")
async def register_capability(
    body: RegisterCapabilityRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Register or update an agent's capability profile with embedding."""
    registry = AgentRegistryService()
    cap = await registry.register(
        db=db,
        agent_id=body.agent_id,
        name=body.name,
        description=body.description,
        task_types=body.task_types,
        tools=body.tools,
        confidence_score=body.confidence_score,
        metadata=body.metadata,
    )
    return {
        "id": cap.id,
        "agent_id": cap.agent_id,
        "name": cap.name,
        "task_types": cap.task_types,
        "tools": cap.tools,
        "confidence_score": cap.confidence_score,
        "has_embedding": cap.embedding_id is not None,
    }


@router.get("")
async def list_capabilities(
    task_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all registered agent capabilities."""
    registry = AgentRegistryService()
    caps = await registry.list_capabilities(db, task_type=task_type)
    return {
        "capabilities": [
            {
                "id": c.id,
                "agent_id": c.agent_id,
                "name": c.name,
                "description": c.description,
                "task_types": c.task_types or [],
                "tools": c.tools or [],
                "confidence_score": c.confidence_score,
                "has_embedding": c.embedding_id is not None,
            }
            for c in caps
        ]
    }


@router.get("/{agent_id}")
async def get_capability(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a specific agent's capability profile."""
    registry = AgentRegistryService()
    cap = await registry.get_capability(db, agent_id)
    if not cap:
        raise HTTPException(404, "Agent capability not found")
    return {
        "id": cap.id,
        "agent_id": cap.agent_id,
        "name": cap.name,
        "description": cap.description,
        "task_types": cap.task_types or [],
        "tools": cap.tools or [],
        "confidence_score": cap.confidence_score,
        "has_embedding": cap.embedding_id is not None,
        "metadata": cap.metadata_,
    }


@router.delete("/{agent_id}")
async def delete_capability(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete an agent's capability profile."""
    registry = AgentRegistryService()
    deleted = await registry.delete_capability(db, agent_id)
    if not deleted:
        raise HTTPException(404, "Agent capability not found")
    return {"deleted": True}


@router.post("/discover")
async def discover_agents(
    body: DiscoverRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Find agents matching a task description via semantic search."""
    registry = AgentRegistryService()
    results = await registry.discover(
        db=db,
        task_description=body.task_description,
        task_type=body.task_type,
        limit=body.limit,
    )
    return {
        "matches": results,
        "total": len(results),
        "search_method": "qdrant" if registry._qdrant_available else "postgres",
    }


@router.post("/match")
async def match_agent(
    body: MatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Find the single best agent for a task."""
    registry = AgentRegistryService()
    result = await registry.match(
        db=db,
        task_description=body.task_description,
        task_type=body.task_type,
        required_tools=body.required_tools,
    )
    if not result:
        raise HTTPException(404, "No matching agent found for the given task")
    return {
        "match": result,
        "search_method": "qdrant" if registry._qdrant_available else "postgres",
    }
