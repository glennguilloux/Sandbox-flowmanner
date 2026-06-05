import asyncio
import logging

from app.models.swarm import SwarmTask

logger = logging.getLogger(__name__)


async def execute_tasks_parallel(
    tasks: list[SwarmTask],
    session_factory,
    execute_fn,
) -> list[SwarmTask]:
    async def _run_one(task: SwarmTask) -> SwarmTask:
        try:
            async with session_factory() as task_db:
                task_db.add(task)
                await task_db.commit()
                await task_db.refresh(task)
                result = await execute_fn(task_db, task)
                return result if result is not None else task
        except Exception:
            logger.exception("Parallel task %s failed", task.id)
            task.status = "failed"
            task.error = "Execution error"
            return task

    results = await asyncio.gather(*[_run_one(t) for t in tasks])
    return list(results)
