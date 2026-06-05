"""Mission decomposition and DAG execution service."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

from app.services.dag_executor import (
    get_downstream,
    topological_sort,
    validate_dag,
)
from app.services.mission_service import (
    create_mission_log,
    create_mission_task,
    get_mission,
    get_mission_tasks,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.mission_models import MissionTask


async def decompose_manual(
    db: AsyncSession,
    mission_id: str,
    tasks: list[dict],
) -> list[MissionTask]:
    """Create tasks with dependency edges from a manual task list.

    Each task dict: {title, description, task_type, depends_on: [int], assigned_model}
    depends_on uses list indices (0-based) into the tasks list.
    """
    created_tasks: list[MissionTask] = []

    # First pass: create all tasks
    for idx, task_def in enumerate(tasks):
        task = await create_mission_task(
            db,
            mission_id=mission_id,
            title=task_def.get("title", f"Task {idx + 1}"),
            description=task_def.get("description", ""),
            task_type=task_def.get("task_type", "general"),
            order_index=idx,
            assigned_model=task_def.get("assigned_model"),
        )
        created_tasks.append(task)

    # Second pass: resolve index-based depends_on to UUID-based
    for idx, task_def in enumerate(tasks):
        dep_indices = task_def.get("depends_on", [])
        if dep_indices:
            dep_uuids = [str(created_tasks[i].id) for i in dep_indices]
            task = created_tasks[idx]
            task.dependencies = {"depends_on": dep_uuids}

    await db.flush()
    return created_tasks


async def decompose_mission(
    db: AsyncSession,
    mission_id: str,
    mode: str = "manual",
    tasks: list[dict] | None = None,
) -> dict:
    """Entry point for mission decomposition.

    Returns: {tasks: [...], dag_valid: bool, errors: [...]}
    """
    mission = await get_mission(db, mission_id)
    if mission is None:
        return {"tasks": [], "dag_valid": False, "errors": ["Mission not found"]}

    if mode == "manual":
        if not tasks:
            return {"tasks": [], "dag_valid": False, "errors": ["No tasks provided"]}
        created = await decompose_manual(db, mission_id, tasks)
    else:
        return {"tasks": [], "dag_valid": False, "errors": [f"Unknown mode: {mode}"]}

    # Validate the resulting DAG
    errors = validate_dag(created)

    # Update mission status
    if not errors:
        mission.status = "decomposed"
        await db.flush()

    return {
        "tasks": [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "dependencies": t.dependencies or {},
            }
            for t in created
        ],
        "dag_valid": len(errors) == 0,
        "errors": errors,
    }


async def execute_dag(
    db: AsyncSession,
    mission_id: str,
    executor: Callable | None = None,
) -> dict:
    """Execute mission tasks in dependency order.

    executor: async callable(task: MissionTask) -> dict (output_data)
              If None, tasks are marked completed without execution.
    Returns: {completed: int, failed: int, skipped: int, errors: [...]}
    """
    mission = await get_mission(db, mission_id)
    if mission is None:
        return {"completed": 0, "failed": 0, "skipped": 0, "errors": ["Mission not found"]}

    tasks = await get_mission_tasks(db, mission_id)
    if not tasks:
        return {"completed": 0, "failed": 0, "skipped": 0, "errors": ["No tasks"]}

    # Validate DAG
    errors = validate_dag(tasks)
    if errors:
        return {"completed": 0, "failed": 0, "skipped": 0, "errors": errors}

    # Update mission status
    mission.status = "running"
    from datetime import datetime
    if mission.started_at is None:
        mission.started_at = datetime.now(UTC)
    await db.flush()

    completed = 0
    failed = 0
    skipped = 0
    exec_errors: list[str] = []
    task_map = {str(t.id): t for t in tasks}

    try:
        layers = topological_sort(tasks)
    except ValueError as e:
        return {"completed": 0, "failed": 0, "skipped": 0, "errors": [str(e)]}

    for layer in layers:
        for task_id in layer:
            task = task_map[task_id]

            # Skip if any dependency failed
            deps = task.dependencies or {}
            dep_list = deps.get("depends_on", [])
            if any(task_map[d].status == "failed" for d in dep_list if d in task_map):
                task.status = "skipped"
                skipped += 1
                await create_mission_log(
                    db, mission_id, "info",
                    f"Skipped task '{task.title}' due to failed dependency",
                    task_id=task_id,
                )
                continue

            # Execute task
            task.status = "running"
            task.started_at = datetime.now(UTC)
            await db.flush()

            try:
                if executor:
                    output = await executor(task)
                    task.output_data = output
                task.status = "completed"
                task.completed_at = datetime.now(UTC)
                completed += 1
                await create_mission_log(
                    db, mission_id, "info",
                    f"Completed task '{task.title}'",
                    task_id=task_id,
                )
            except Exception as e:
                task.status = "failed"
                task.error_message = str(e)
                task.completed_at = datetime.now(UTC)
                failed += 1
                exec_errors.append(f"Task '{task.title}': {e}")
                await create_mission_log(
                    db, mission_id, "error",
                    f"Failed task '{task.title}': {e}",
                    task_id=task_id,
                )

                # Skip downstream tasks
                downstream = get_downstream(task_id, tasks)
                for ds_id in downstream:
                    ds_task = task_map[ds_id]
                    if ds_task.status == "pending":
                        ds_task.status = "skipped"
                        skipped += 1

            await db.flush()

    # Final mission status
    if failed > 0:
        mission.status = "failed"
    elif skipped > 0:
        mission.status = "completed_with_skips"
    else:
        mission.status = "completed"
    mission.completed_at = datetime.now(UTC)
    await db.flush()

    return {
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "errors": exec_errors,
    }
