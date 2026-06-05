import json
import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.swarm import SwarmAgent, SwarmTask
from app.models.swarm_pipeline import NexusPipeline
from app.services.llm_router import ModelRouter

logger = logging.getLogger(__name__)


class DispatchError(Exception):
    """Raised when DISPATCH phase fails."""


_router: ModelRouter | None = None


def _get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


def _build_messages(pipeline: NexusPipeline, agents: list[SwarmAgent]) -> list[dict]:
    agent_list = [
        {
            "id": a.agent_instance_id,
            "name": a.display_name,
            "capabilities": a.capabilities,
            "specializations": a.specializations,
        }
        for a in agents
    ]
    system_content = (
        "You are a task decomposition engine. Given an objective and a list of available agents, "
        "break the objective into concrete sub-tasks and assign each to the most suitable agent. "
        "Respond ONLY with valid JSON in this exact schema, no markdown, no explanation:\n"
        '{"tasks": [{"title": "<short title>", "description": "<what to do>", "assigned_agent_id": "<agent id>"}]}\n'
        "Rules:\n"
        "- assigned_agent_id MUST be one of the provided agent IDs\n"
        "- At least one task must be returned\n"
        "- No two tasks may share the same title"
    )
    user_content = f"Objective: {pipeline.objective}\n\nAvailable agents:\n{json.dumps(agent_list, indent=2)}"
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def _parse_tasks(response_text: str) -> list[dict]:
    try:
        data = json.loads(response_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise DispatchError(f"LLM returned invalid JSON: {exc}") from exc

    if not isinstance(data, dict) or "tasks" not in data:
        raise DispatchError("LLM response missing 'tasks' key")

    tasks = data["tasks"]
    if not tasks:
        raise DispatchError("Empty decomposition: LLM returned at least 0 tasks; at least 1 required")

    return tasks


def _validate_tasks(tasks: list[dict], agents: list[SwarmAgent]) -> None:
    valid_ids = {a.agent_instance_id for a in agents}
    seen_titles: set[str] = set()

    for task in tasks:
        agent_id = task.get("assigned_agent_id", "")
        if agent_id not in valid_ids:
            raise DispatchError(f"Task references unknown agent '{agent_id}'. Valid agent IDs: {sorted(valid_ids)}")
        title = task.get("title", "")
        if title in seen_titles:
            raise DispatchError(f"Duplicate task title: '{title}'")
        seen_titles.add(title)


async def run_dispatch(
    db: AsyncSession,
    pipeline: NexusPipeline,
    agents: list[SwarmAgent],
    user_id: str = "system",
) -> list[SwarmTask]:
    messages = _build_messages(pipeline, agents)

    router = _get_router()
    response = await router.route_request(
        messages=messages,
        user_id=user_id,
        is_admin=False,
    )

    if not response.get("success"):
        raise DispatchError(f"LLM routing failed: {response.get('response', 'unknown error')}")

    raw_tasks = _parse_tasks(response["response"])
    _validate_tasks(raw_tasks, agents)

    created: list[SwarmTask] = []
    for item in raw_tasks:
        task = SwarmTask(
            id=uuid4().hex[:12],
            swarm_id=pipeline.swarm_id,
            task_type="pipeline_subtask",
            payload={
                "prompt": item["description"],
                "pipeline_id": pipeline.id,
                "phase": "dispatch",
            },
            assigned_agent_id=item["assigned_agent_id"],
            status="pending",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        created.append(task)

    logger.info("DISPATCH created %d sub-tasks for pipeline %s", len(created), pipeline.id)
    return created
