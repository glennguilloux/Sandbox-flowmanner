from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_workspace_id
from app.database import get_db
from app.schemas.agent import (
    AgentCreate,
    AgentResponse,
    AgentTemplateCreate,
    AgentTemplateResponse,
    AgentTemplateUpdate,
    AgentUpdate,
)
from app.services.agent_service import (
    create_agent,
    create_agent_template,
    delete_agent,
    delete_agent_template,
    get_agent_templates,
    list_agent_templates,
    list_agents,
    require_agent_access,
    update_agent,
    update_agent_template,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/agents", tags=["agents"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


async def _list_agents(
    db: AsyncSession,
    user: User,
    page: int,
    per_page: int,
    workspace_id: str | None = None,
):
    offset = (page - 1) * per_page
    items, total = await list_agents(db, str(user.id), offset=offset, limit=per_page, workspace_id=workspace_id)
    pages = (total + per_page - 1) // per_page
    return {
        "items": items,
        "agents": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("")
@router.get("/")
async def list_items(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    return await _list_agents(db, user, page, per_page, workspace_id=workspace_id)


@router.post("")
@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    return await create_agent(
        db,
        payload.name,
        str(user.id),
        payload.description,
        payload.system_prompt,
        payload.model_preference,
        payload.config,
        workspace_id=workspace_id,
    )


# Templates routes BEFORE /{agent_id} routes
@router.get("/templates", response_model=list[AgentTemplateResponse])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, _total = await list_agent_templates(db)
    return items


@router.post(
    "/templates",
    response_model=AgentTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    payload: AgentTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await create_agent_template(db, payload.name, payload.description, payload.config, payload.is_public)


@router.patch("/templates/{template_id}", response_model=AgentTemplateResponse)
async def patch_template(
    template_id: uuid.UUID,
    payload: AgentTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    template = await get_agent_templates(db, template_id)
    if template is None:
        raise _not_found()
    updated = await update_agent_template(
        db,
        template_id,  # type: ignore[arg-type]
        payload.name,
        payload.description,
        payload.config,
        payload.is_public,
    )
    if updated is None:
        raise _not_found()
    return updated


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if await get_agent_templates(db, template_id) is None:
        raise _not_found()
    if not await delete_agent_template(db, template_id):  # type: ignore[arg-type]
        raise _not_found()


# /{agent_id} routes AFTER templates
@router.get("/{agent_id}", response_model=AgentResponse)
async def get_item(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent = await require_agent_access(db, agent_id, user.id)
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
async def patch_item(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_agent_access(db, agent_id, user.id)
    updated = await update_agent(
        db,
        agent_id,
        payload.name,
        payload.description,
        payload.system_prompt,
        payload.model_preference,
        payload.config,
    )
    if updated is None:
        raise _not_found()
    return updated


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_agent_access(db, agent_id, user.id)
    if not await delete_agent(db, agent_id):
        raise _not_found()
