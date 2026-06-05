import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.swarm import SwarmAgent, SwarmTask
from app.models.swarm_pipeline import NexusPipeline
from app.services.swarm_executor import execute_swarm_task
from app.services.swarm_pipeline.phases._parallel import execute_tasks_parallel

logger = logging.getLogger(__name__)


async def _execute_tasks_parallel(
    tasks: list[SwarmTask],
    session_factory,
) -> list[SwarmTask]:
    return await execute_tasks_parallel(tasks, session_factory, execute_swarm_task)


async def run_research(
    db: AsyncSession,
    pipeline: NexusPipeline,
    tasks: list[SwarmTask],
    agents: list[SwarmAgent],
    session_factory=None,
) -> list[SwarmTask]:
    if session_factory is None:
        from app.database import AsyncSessionLocal

        session_factory = AsyncSessionLocal

    for task in tasks:
        sub_task_description = (task.payload or {}).get("prompt", "")
        research_prompt = (
            f"Research and gather information about: {sub_task_description}. Context: {pipeline.objective}"
        )
        task.payload = {
            **(task.payload or {}),
            "prompt": research_prompt,
            "phase": "research",
        }

    return await _execute_tasks_parallel(tasks, session_factory)
