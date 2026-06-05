"""
Agent Registry API Router
Aliases /api/agent-registry/agents/* to the existing /api/agents/* routes.
The frontend built JS calls /api/agent-registry/agents/ but the backend
only has /api/agents/. This router provides the missing prefix alias
plus additional endpoints the frontend expects (/start, /register).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.agent import (
    AgentCreate,
    AgentResponse,
)
from app.services.agent_service import (
    create_agent,
    delete_agent,
    get_agent,
    list_agents,
    update_agent,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.agent import Agent
    from app.models.user import User

router = APIRouter(prefix="/agent-registry", tags=["agent-registry"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _require_owner(agent: Agent | None, user: User) -> None:
    if agent is None or agent.owner_id != user.id:
        raise _not_found()


# ---- /api/agent-registry/agents ----


@router.get("/agents")
@router.get("/agents/")
async def list_agents_registry(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List agents for the current user."""
    try:
        offset = (page - 1) * per_page
        items, total = await list_agents(db, user.id, offset=offset, limit=per_page)
        pages = (total + per_page - 1) // per_page
        return {
            "items": items,
            "agents": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/agents")
@router.post(
    "/agents/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED
)
async def create_agent_registry(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new agent."""
    try:
        return await create_agent(
            db,
            payload.name,
            user.id,
            payload.description,
            payload.system_prompt,
            payload.model_preference,
            payload.config,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# ---- /api/agent-registry/register ----


class RegisterAgentPayload:
    """Simple registration payload."""

    pass


@router.post("/register")
async def register_agent(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Register a new agent (alias for create)."""
    try:
        name = payload.get("name", "Unnamed Agent")
        description = payload.get("description")
        system_prompt = payload.get("system_prompt")
        model_reference = payload.get(
            "model_reference", payload.get("model_preference")
        )
        config = payload.get("config")
        agent = await create_agent(
            db,
            name,
            user.id,
            description,
            system_prompt,
            model_reference,
            config,
        )
        return {"status": "registered", "agent": agent}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# ---- /api/agent-registry/agents/{agent_id} ----


@router.get("/agents/{agent_id}")
async def get_agent_registry(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a single agent by ID."""
    try:
        agent = await get_agent(db, agent_id)
        _require_owner(agent, user)
        return agent
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/agents/{agent_id}")
async def update_agent_registry(
    agent_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update an agent (full update via PUT)."""
    try:
        agent = await get_agent(db, agent_id)
        _require_owner(agent, user)
        updated = await update_agent(
            db,
            agent_id,
            payload.get("name"),
            payload.get("description"),
            payload.get("system_prompt"),
            payload.get("model_preference"),
            payload.get("config"),
        )
        if updated is None:
            raise _not_found()
        return updated
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_registry(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete an agent."""
    try:
        agent = await get_agent(db, agent_id)
        _require_owner(agent, user)
        if not await delete_agent(db, agent_id):
            raise _not_found()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# ---- /api/agent-registry/agents/{agent_id}/start ----


@router.post("/agents/{agent_id}/start")
async def start_agent(
    agent_id: uuid.UUID,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Start an agent — marks it active and returns configuration for the frontend to initialize a chat."""
    try:
        agent = await get_agent(db, agent_id)
        _require_owner(agent, user)

        # Update agent status to active
        agent.status = "active"
        await db.flush()

        return {
            "status": "started",
            "agent_id": str(agent_id),
            "agent_name": agent.name,
            "model_preference": agent.model_preference,
            "system_prompt": agent.system_prompt or "You are a helpful assistant.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
