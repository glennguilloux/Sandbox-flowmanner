from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from app.models.agent import AgentTemplate
from app.models.swarm import SwarmAgent, SwarmProfile, SwarmTask
from app.schemas.swarm import (
    SwarmCreate,
    SwarmStatsResponse,
    SwarmTaskCreate,
    SwarmTaskUpdate,
    SwarmUpdate,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def create_swarm(
    db: AsyncSession, user_id: int, data: SwarmCreate
) -> SwarmProfile:
    swarm_id = uuid4().hex[:12]
    swarm = SwarmProfile(
        swarm_id=swarm_id,
        swarm_name=data.swarm_name,
        task_type=data.task_type,
        task_description=data.task_description,
        status="active",
        consensus_strategy=data.consensus_strategy,
        consensus_config=data.consensus_config,
        daily_limit=data.daily_limit,
        monthly_limit=data.monthly_limit,
        created_by=user_id,
    )
    db.add(swarm)
    await db.commit()
    await db.refresh(swarm)
    return swarm


async def get_swarm(db: AsyncSession, swarm_id: str) -> SwarmProfile | None:
    result = await db.execute(
        select(SwarmProfile).where(SwarmProfile.swarm_id == swarm_id)
    )
    return result.scalars().first()


async def list_swarms(
    db: AsyncSession, user_id: int | None = None, status: str | None = None
) -> list[SwarmProfile]:
    q = select(SwarmProfile).order_by(SwarmProfile.created_at.desc())
    if user_id is not None:
        q = q.where(SwarmProfile.created_by == user_id)
    if status:
        q = q.where(SwarmProfile.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_swarm(
    db: AsyncSession, swarm_id: str, data: SwarmUpdate
) -> SwarmProfile | None:
    swarm = await get_swarm(db, swarm_id)
    if not swarm:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(swarm, field, value)
    swarm.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(swarm)
    return swarm


async def dissolve_swarm(db: AsyncSession, swarm_id: str) -> SwarmProfile | None:
    swarm = await get_swarm(db, swarm_id)
    if not swarm:
        return None
    swarm.status = "dissolved"
    swarm.dissolved_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(swarm)
    return swarm


async def delete_swarm(db: AsyncSession, swarm_id) -> bool:
    result = await dissolve_swarm(db, str(swarm_id))
    return result is not None


async def add_agent_to_swarm(
    db: AsyncSession,
    swarm_id: str,
    template_id: int,
    role: str | None = None,
    assigned_model: str | None = None,
) -> SwarmAgent | None:
    swarm = await get_swarm(db, swarm_id)
    if not swarm:
        return None

    tmpl_result = await db.execute(
        select(AgentTemplate).where(AgentTemplate.id == template_id)
    )
    template = tmpl_result.scalars().first()
    if not template:
        return None

    agent = SwarmAgent(
        agent_instance_id=f"{swarm_id}-{uuid4().hex[:8]}",
        swarm_id=swarm_id,
        agent_template_id=template_id,
        role=role or template.agent_type,
        display_name=template.name,
        capabilities=template.capabilities,
        specializations=template.specializations,
        assigned_model=assigned_model or template.default_model,
        status="idle",
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def add_agent_by_slug(
    db: AsyncSession,
    swarm_id: str,
    slug: str,
    role: str | None = None,
    assigned_model: str | None = None,
) -> SwarmAgent | None:
    tmpl_result = await db.execute(
        select(AgentTemplate).where(AgentTemplate.model_config["slug"].astext == slug)
    )
    template = tmpl_result.scalars().first()
    if not template:
        logger.warning(f"Agent template not found for slug: {slug}")
        return None
    return await add_agent_to_swarm(db, swarm_id, template.id, role, assigned_model)


async def populate_swarm_from_division(
    db: AsyncSession, swarm_id: str, division: str
) -> list[SwarmAgent]:
    swarm = await get_swarm(db, swarm_id)
    if not swarm:
        return []

    result = await db.execute(
        select(AgentTemplate)
        .where(AgentTemplate.model_config["division"].astext == division)
        .where(AgentTemplate.is_active == True)
    )
    templates = list(result.scalars().all())

    agents = []
    for template in templates:
        agent = await add_agent_to_swarm(db, swarm_id, template.id)
        if agent:
            agents.append(agent)

    logger.info(
        f"Populated swarm {swarm_id} with {len(agents)} agents from division '{division}'"
    )
    return agents


async def populate_swarm_from_slugs(
    db: AsyncSession, swarm_id: str, slugs: list[str]
) -> list[SwarmAgent]:
    agents = []
    for slug in slugs:
        agent = await add_agent_by_slug(db, swarm_id, slug)
        if agent:
            agents.append(agent)
    logger.info(
        f"Populated swarm {swarm_id} with {len(agents)} agents from {len(slugs)} slugs"
    )
    return agents


async def list_swarm_agents(db: AsyncSession, swarm_id: str) -> list[SwarmAgent]:
    result = await db.execute(
        select(SwarmAgent)
        .where(SwarmAgent.swarm_id == swarm_id)
        .order_by(SwarmAgent.joined_at)
    )
    return list(result.scalars().all())


async def remove_agent(db: AsyncSession, agent_instance_id: str) -> bool:
    result = await db.execute(
        select(SwarmAgent).where(SwarmAgent.agent_instance_id == agent_instance_id)
    )
    agent = result.scalars().first()
    if not agent:
        return False
    await db.delete(agent)
    await db.commit()
    return True


async def create_swarm_task(
    db: AsyncSession, swarm_id: str, data: SwarmTaskCreate
) -> SwarmTask | None:
    swarm = await get_swarm(db, swarm_id)
    if not swarm:
        return None

    task = SwarmTask(
        id=uuid4().hex[:12],
        swarm_id=swarm_id,
        task_type=data.task_type,
        payload=data.payload,
        assigned_agent_id=data.assigned_agent_id,
        priority=data.priority,
        max_retries=data.max_retries,
        dependencies=data.dependencies,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def list_swarm_tasks(
    db: AsyncSession, swarm_id: str, status: str | None = None
) -> list[SwarmTask]:
    q = (
        select(SwarmTask)
        .where(SwarmTask.swarm_id == swarm_id)
        .order_by(SwarmTask.created_at)
    )
    if status:
        q = q.where(SwarmTask.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_swarm_task(db: AsyncSession, task_id: str) -> SwarmTask | None:
    result = await db.execute(select(SwarmTask).where(SwarmTask.id == task_id))
    return result.scalars().first()


async def update_swarm_task(
    db: AsyncSession, task_id: str, data: SwarmTaskUpdate
) -> SwarmTask | None:
    task = await get_swarm_task(db, task_id)
    if not task:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    if data.status == "running" and not task.started_at:
        task.started_at = datetime.now(UTC)
    if data.status in ("completed", "failed", "cancelled"):
        task.completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(task)
    return task


async def get_swarm_stats(db: AsyncSession, swarm_id: str) -> SwarmStatsResponse | None:
    swarm = await get_swarm(db, swarm_id)
    if not swarm:
        return None

    agents = await list_swarm_agents(db, swarm_id)
    tasks = await list_swarm_tasks(db, swarm_id)

    tasks_by_status: dict[str, int] = {}
    for t in tasks:
        s = t.status or "unknown"
        tasks_by_status[s] = tasks_by_status.get(s, 0) + 1

    return SwarmStatsResponse(
        total_agents=len(agents),
        active_agents=sum(1 for a in agents if a.status in ("idle", "busy")),
        total_tasks=len(tasks),
        tasks_by_status=tasks_by_status,
    )


remove_swarm_agent = remove_agent
