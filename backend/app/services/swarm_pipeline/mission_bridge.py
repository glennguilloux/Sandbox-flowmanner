import asyncio
import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mission_models import Mission
from app.models.swarm_pipeline import NexusPipeline
from app.services import swarm_service

logger = logging.getLogger(__name__)


async def create_pipeline_from_mission(db: AsyncSession, mission_id: str) -> NexusPipeline:
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalars().first()
    if not mission:
        raise ValueError(f"Mission {mission_id} not found")

    constraints = mission.constraints or {}
    swarm_id = constraints.get("swarm_id")
    if not swarm_id:
        plan = mission.plan or {}
        swarm_id = plan.get("swarm_id")

    if not swarm_id:
        raise ValueError(f"Mission {mission_id} does not have a swarm_id in constraints or plan")

    objective = mission.description or mission.title

    pipeline = NexusPipeline(
        id=uuid4().hex[:12],
        swarm_id=swarm_id,
        objective=objective,
        config={"mission_id": mission_id},
        status="pending",
        current_phase="pending",
        retry_count=0,
        phase_history=[],
    )
    db.add(pipeline)
    await db.commit()
    await db.refresh(pipeline)
    return pipeline


async def start_pipeline_from_mission(db: AsyncSession, mission_id: str) -> str:
    pipeline = await create_pipeline_from_mission(db, mission_id)

    swarm = await swarm_service.get_swarm(db, pipeline.swarm_id)
    agents = await swarm_service.list_swarm_agents(db, pipeline.swarm_id)
    user_id = str(swarm.created_by) if swarm and swarm.created_by else "system"

    asyncio.create_task(_run_and_sync(pipeline.id, mission_id, agents, user_id))

    return pipeline.id


async def _run_and_sync(pipeline_id: str, mission_id: str, agents, user_id: str) -> None:
    from app.database import AsyncSessionLocal
    from app.services.swarm_pipeline.orchestrator import run_pipeline

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(NexusPipeline).where(NexusPipeline.id == pipeline_id))
        pipeline = result.scalars().first()
        if not pipeline:
            logger.warning("Pipeline %s not found in background runner", pipeline_id)
            return
        await run_pipeline(db, pipeline, agents, user_id)
        await sync_pipeline_result_to_mission(db, pipeline_id, mission_id)


async def sync_pipeline_result_to_mission(db: AsyncSession, pipeline_id: str, mission_id: str) -> None:
    pipeline_result = await db.execute(select(NexusPipeline).where(NexusPipeline.id == pipeline_id))
    pipeline = pipeline_result.scalars().first()
    if not pipeline:
        return

    mission_result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = mission_result.scalars().first()
    if not mission:
        return

    if pipeline.status == "completed":
        mission.results = pipeline.result
        mission.status = "completed"
        mission.completed_at = datetime.now(UTC)
    elif pipeline.status == "failed":
        mission.error_message = pipeline.error
        mission.status = "failed"

    await db.commit()
