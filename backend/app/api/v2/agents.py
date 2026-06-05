"""V2 Agents endpoints — catalog, registry, standardized envelope."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.v2.base import ok, paginated
from app.api.v2.cursor_pagination import CursorParams, cursor_paginated
from app.database import get_db
from app.models.agent import Agent
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
    get_agent,
    list_agent_templates,
    list_agents,
    update_agent,
    update_agent_template,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/agents", tags=["v2-agents"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _require_owner(agent: Agent | None, user: User) -> None:
    if agent is None or str(agent.owner_id) != str(user.id):
        raise _not_found()


async def _list_agents(db: AsyncSession, user: User, page: int, per_page: int):
    offset = (page - 1) * per_page
    items, total = await list_agents(db, str(user.id), offset=offset, limit=per_page)
    return paginated(
        items=[AgentResponse.model_validate(a).model_dump() for a in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("")
@router.get("/")
async def list_items(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, description="Opaque cursor token for keyset pagination"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if cursor:
        cp = CursorParams(cursor=cursor, direction="after", limit=per_page)
        decoded = cp.decoded
        query = select(Agent).where(
            Agent.owner_id == str(user.id),
            Agent.id > str(decoded["id"]),
        ).order_by(Agent.id.asc()).limit(per_page + 1)
        result = await db.execute(query)
        items = list(result.scalars().all())
        serialized = [AgentResponse.model_validate(a).model_dump() for a in items]
        return cursor_paginated(
            items=serialized,
            limit=per_page,
            cursor_params=cp,
            item_id_fn=lambda x: x["id"],
            item_ts_fn=lambda x: x.get("created_at"),
        )
    return await _list_agents(db, user, page, per_page)


@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent = await create_agent(
        db,
        payload.name,
        str(user.id),
        payload.description,
        payload.system_prompt,
        payload.model_preference,
        payload.config,
    )
    return ok(AgentResponse.model_validate(agent).model_dump())


@router.get("/{agent_id}")
@router.get("/{agent_id}/")
async def get_item(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent = await get_agent(db, agent_id)
    _require_owner(agent, user)
    return ok(AgentResponse.model_validate(agent).model_dump())


@router.patch("/{agent_id}")
async def patch_item(
    agent_id: str,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent = await get_agent(db, agent_id)
    _require_owner(agent, user)
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
    return ok(AgentResponse.model_validate(updated).model_dump())


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent = await get_agent(db, agent_id)
    _require_owner(agent, user)
    if not await delete_agent(db, agent_id):
        raise _not_found()


@router.get("/templates/list")
async def list_templates(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * per_page
    items, total = await list_agent_templates(db, offset=offset, limit=per_page)
    return paginated(
        items=[AgentTemplateResponse.model_validate(t).model_dump() for t in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: AgentTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    template = await create_agent_template(
        db,
        payload.name,
        payload.description,
        payload.agent_type,
        payload.system_prompt,
        payload.model_config,
    )
    return ok(AgentTemplateResponse.model_validate(template).model_dump())


@router.patch("/templates/{template_id}")
async def update_template(
    template_id: str,
    payload: AgentTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    updated = await update_agent_template(
        db,
        template_id,
        payload.name,
        payload.description,
        payload.system_prompt,
        payload.model_config,
    )
    if updated is None:
        raise _not_found()
    return ok(AgentTemplateResponse.model_validate(updated).model_dump())


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await delete_agent_template(db, template_id):
        raise _not_found()
