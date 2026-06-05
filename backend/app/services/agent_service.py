"""Agent template CRUD operations and seeding."""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentTemplate
from app.services.agent_parser import load_all_agents

logger = logging.getLogger(__name__)


async def create_agent(
    db: AsyncSession,
    name: str,
    owner_id: str,
    description: str | None = None,
    system_prompt: str | None = None,
    model_preference: str | None = None,
    config: dict | None = None,
    workspace_id: str | None = None,
) -> Agent:
    agent = Agent(
        name=name,
        owner_id=owner_id,
        description=description,
        system_prompt=system_prompt,
        model_preference=model_preference,
        config=json.dumps(config) if config else None,
        workspace_id=workspace_id,
    )
    db.add(agent)
    await db.flush()
    return agent


async def require_agent_access(
    db: AsyncSession,
    agent_id: uuid.UUID,
    user_id: int,
) -> Agent:
    """Fetch an agent and verify the user has access.

    Access rules:
    1. If the agent has a workspace_id → verify the user is an active member
       of that workspace.
    2. If the agent has no workspace_id → fall back to owner_id ownership.
    3. If the agent doesn't exist → 404.
    """
    agent = await db.get(Agent, str(agent_id))
    if agent is None:
        raise HTTPException(status_code=404, detail="Not found")

    if agent.workspace_id:
        from app.models.workspace_models import WorkspaceMember

        result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == agent.workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.is_active == True,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Not found")
    else:
        if str(agent.owner_id) != str(user_id):
            raise HTTPException(status_code=404, detail="Not found")

    return agent


async def get_agent(db: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
    return await db.get(Agent, str(agent_id))


async def list_agents(
    db: AsyncSession,
    owner_id: str,
    offset: int = 0,
    limit: int = 20,
    workspace_id: str | None = None,
) -> tuple[list[Agent], int]:
    base_filter = (
        Agent.workspace_id == workspace_id
        if workspace_id is not None
        else Agent.owner_id == owner_id
    )
    count_query = select(func.count()).select_from(Agent).where(base_filter)
    total = (await db.execute(count_query)).scalar() or 0
    query = select(Agent).where(base_filter)
    result = await db.execute(
        query.offset(offset).limit(limit).order_by(Agent.created_at.desc())
    )
    return list(result.scalars().all()), total


async def update_agent(
    db: AsyncSession,
    agent_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
    system_prompt: str | None = None,
    model_preference: str | None = None,
    config: dict | None = None,
) -> Agent | None:
    agent = await db.get(Agent, str(agent_id))
    if agent is None:
        return None
    if name is not None:
        agent.name = name
    if description is not None:
        agent.description = description
    if system_prompt is not None:
        agent.system_prompt = system_prompt
    if model_preference is not None:
        agent.model_preference = model_preference
    if config is not None:
        agent.config = json.dumps(config)
    await db.flush()
    return agent


async def delete_agent(db: AsyncSession, agent_id: uuid.UUID) -> bool:
    agent = await db.get(Agent, str(agent_id))
    if agent is None:
        return False
    await db.delete(agent)
    await db.flush()
    return True


async def get_agent_templates(
    db: AsyncSession, template_id: uuid.UUID
) -> AgentTemplate | None:
    return await db.get(AgentTemplate, str(template_id))


def _build_model_config(
    emoji: str, color: str, vibe: str, slug: str, division: str
) -> dict:
    return {
        "emoji": emoji,
        "color": color,
        "vibe": vibe,
        "slug": slug,
        "division": division,
    }


# ---------------------------------------------------------------------------
# AgentTemplate CRUD
# ---------------------------------------------------------------------------


async def create_agent_template(
    db: AsyncSession,
    name: str,
    description: str | None,
    system_prompt: str | None,
    agent_type: str = "domain",
    model_config: dict | None = None,
    is_active: bool = True,
) -> AgentTemplate:
    template = AgentTemplate(
        template_id=str(uuid.uuid4()),
        name=name,
        description=description,
        agent_type=agent_type,
        system_prompt=system_prompt,
        model_config=model_config,
        is_active=is_active,
    )
    db.add(template)
    await db.flush()
    return template


async def get_agent_template(
    db: AsyncSession, template_id: int
) -> AgentTemplate | None:
    return await db.get(AgentTemplate, template_id)


async def get_agent_template_by_slug(
    db: AsyncSession, slug: str
) -> AgentTemplate | None:
    result = await db.execute(
        select(AgentTemplate).where(AgentTemplate.model_config["slug"].astext == slug)
    )
    return result.scalar_one_or_none()


async def list_agent_templates(
    db: AsyncSession,
    division: str | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> tuple[list[AgentTemplate], int]:
    query = select(AgentTemplate).where(AgentTemplate.is_active.is_(True))
    count_query = (
        select(func.count())
        .select_from(AgentTemplate)
        .where(AgentTemplate.is_active.is_(True))
    )

    if division:
        query = query.where(AgentTemplate.model_config["division"].astext == division)
        count_query = count_query.where(
            AgentTemplate.model_config["division"].astext == division
        )

    if search:
        pattern = f"%{search}%"
        query = query.where(
            (AgentTemplate.name.ilike(pattern))
            | (AgentTemplate.description.ilike(pattern))
        )
        count_query = count_query.where(
            (AgentTemplate.name.ilike(pattern))
            | (AgentTemplate.description.ilike(pattern))
        )

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.offset(offset).limit(limit).order_by(AgentTemplate.name)
    )
    return list(result.scalars().all()), total


async def update_agent_template(
    db: AsyncSession, template_id: int, **kwargs: Any
) -> AgentTemplate | None:
    template = await db.get(AgentTemplate, template_id)
    if template is None:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(template, key):
            setattr(template, key, value)
    await db.flush()
    return template


async def delete_agent_template(db: AsyncSession, template_id: int) -> bool:
    template = await db.get(AgentTemplate, template_id)
    if template is None:
        return False
    await db.delete(template)
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# Seed / Upsert
# ---------------------------------------------------------------------------


async def seed_agent_templates(
    db: AsyncSession, definitions_dir: Path | None = None
) -> dict:
    agents = load_all_agents(definitions_dir)
    new_count = 0
    updated_count = 0

    for agent_data in agents:
        slug = agent_data["slug"]
        existing = await get_agent_template_by_slug(db, slug)

        config = _build_model_config(
            emoji=agent_data["emoji"],
            color=agent_data["color"],
            vibe=agent_data["vibe"],
            slug=slug,
            division=agent_data["division"],
        )

        if existing is not None:
            existing.name = agent_data["name"]
            existing.description = agent_data["description"]
            existing.system_prompt = agent_data["system_prompt"]
            existing.agent_type = agent_data["division"]
            existing.model_config = config
            updated_count += 1
        else:
            template = AgentTemplate(
                template_id=str(uuid.uuid4()),
                name=agent_data["name"],
                description=agent_data["description"],
                agent_type=agent_data["division"],
                system_prompt=agent_data["system_prompt"],
                model_config=config,
                is_active=True,
            )
            db.add(template)
            new_count += 1

    await db.flush()
    summary = {"total": len(agents), "new": new_count, "updated": updated_count}
    logger.info("Seeded agent templates: %s", summary)
    return summary
