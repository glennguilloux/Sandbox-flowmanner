import asyncio
import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.swarm import SwarmAgent, SwarmTask
from app.models.swarm_pipeline import NexusPipeline
from app.services.swarm_executor import execute_swarm_task

logger = logging.getLogger(__name__)


def build_round_robin_pairs(agents: list[SwarmAgent]) -> list[tuple[SwarmAgent, SwarmAgent]]:
    return [(agents[i], agents[(i + 1) % len(agents)]) for i in range(len(agents))]


async def run_debate(
    db: AsyncSession,
    pipeline: NexusPipeline,
    draft_tasks: list[SwarmTask],
    agents: list[SwarmAgent],
    review_feedback: str | None = None,
    session_factory=None,
) -> list[SwarmTask]:
    if len(agents) <= 1:
        return draft_tasks

    if session_factory is None:
        from app.database import AsyncSessionLocal

        session_factory = AsyncSessionLocal

    draft_by_agent: dict[str, SwarmTask] = {t.assigned_agent_id: t for t in draft_tasks}
    pairs = build_round_robin_pairs(agents)

    review_tasks: list[SwarmTask] = []
    for reviewer, reviewee in pairs:
        reviewee_draft = draft_by_agent.get(reviewee.agent_instance_id)
        reviewee_draft_text = reviewee_draft.result.get("text", "") if reviewee_draft else ""

        prompt = (
            f"You are reviewing another agent's draft. "
            f"Original objective: {pipeline.objective}. "
            f"Draft to review: {reviewee_draft_text}."
        )
        if review_feedback is not None:
            prompt += (
                f" Additionally, a quality reviewer provided this feedback on the previous iteration: "
                f"{review_feedback}. Address these concerns in your review."
            )
        prompt += (
            " Provide constructive critique: strengths, weaknesses, suggestions for improvement. "
            'Output structured JSON: {"strengths": [...], "weaknesses": [...], "suggestions": [...]}'
        )

        task = SwarmTask(
            id=uuid4().hex[:12],
            swarm_id=pipeline.swarm_id,
            task_type="pipeline_subtask",
            payload={"prompt": prompt, "pipeline_id": pipeline.id, "phase": "debate"},
            assigned_agent_id=reviewer.agent_instance_id,
            status="pending",
        )
        review_tasks.append(task)

    async def _run_one(task: SwarmTask) -> SwarmTask:
        try:
            async with session_factory() as task_db:
                task_db.add(task)
                await task_db.commit()
                await task_db.refresh(task)
                result = await execute_swarm_task(task_db, task)
                return result if result is not None else task
        except Exception:
            logger.exception("Parallel debate task %s failed", task.id)
            task.status = "failed"
            task.error = "Execution error"
            return task

    results = await asyncio.gather(*[_run_one(t) for t in review_tasks])
    return list(results)
