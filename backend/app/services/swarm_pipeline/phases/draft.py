import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.swarm import SwarmAgent, SwarmTask
from app.models.swarm_pipeline import NexusPipeline
from app.services.swarm_executor import execute_swarm_task
from app.services.swarm_pipeline.phases._parallel import execute_tasks_parallel

logger = logging.getLogger(__name__)


async def run_draft(
    db: AsyncSession,
    pipeline: NexusPipeline,
    research_tasks: list[SwarmTask],
    agents: list[SwarmAgent],
    session_factory=None,
) -> list[SwarmTask]:
    if session_factory is None:
        from app.database import AsyncSessionLocal

        session_factory = AsyncSessionLocal

    draft_tasks: list[SwarmTask] = []
    for research_task in research_tasks:
        agent_id = research_task.assigned_agent_id
        research_result_text = (research_task.result or {}).get("text", "")
        sub_task_description = (research_task.payload or {}).get("prompt", "")

        draft_prompt = (
            f"Based on your research findings: {research_result_text}. "
            f"Produce a detailed draft for: {sub_task_description}. "
            f"Original objective: {pipeline.objective}"
        )

        draft_task = SwarmTask(
            id=uuid4().hex[:12],
            swarm_id=pipeline.swarm_id,
            assigned_agent_id=agent_id,
            task_type="pipeline_subtask",
            status="pending",
            payload={
                "prompt": draft_prompt,
                "pipeline_id": pipeline.id,
                "phase": "draft",
            },
        )
        draft_tasks.append(draft_task)

    return await execute_tasks_parallel(draft_tasks, session_factory, execute_swarm_task)
