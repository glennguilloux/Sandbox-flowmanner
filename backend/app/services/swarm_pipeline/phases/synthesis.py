import json
import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.swarm import SwarmAgent, SwarmTask
from app.models.swarm_pipeline import NexusPipeline
from app.services.swarm_executor import execute_swarm_task

logger = logging.getLogger(__name__)


def _select_synthesizer(agents: list[SwarmAgent]) -> SwarmAgent:
    for agent in agents:
        caps = agent.capabilities or {}
        if "synthesis" in caps or "writing" in caps:
            return agent
    return agents[0]


async def run_synthesis(
    db: AsyncSession,
    pipeline: NexusPipeline,
    consensus_result: dict,
    draft_tasks: list[SwarmTask],
    agents: list[SwarmAgent],
    session_factory=None,
) -> SwarmTask:
    synthesizer = _select_synthesizer(agents)

    agent_outputs_parts = []
    for task in draft_tasks:
        text = (task.result or {}).get("text", "")
        agent_outputs_parts.append(f"- Agent {task.assigned_agent_id}: {text}")
    agent_outputs = "\n".join(agent_outputs_parts)

    consensus_str = json.dumps(consensus_result)

    prompt = (
        f"Synthesize these agent outputs into a single cohesive response. "
        f"Original objective: {pipeline.objective}. "
        f"Agent outputs:\n{agent_outputs}\n"
        f"Consensus decisions: {consensus_str}. "
        f"Produce a unified, well-structured output."
    )

    task = SwarmTask(
        id=uuid4().hex[:12],
        swarm_id=pipeline.swarm_id,
        task_type="pipeline_subtask",
        payload={"prompt": prompt, "pipeline_id": pipeline.id, "phase": "synthesis"},
        assigned_agent_id=synthesizer.agent_instance_id,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    completed = await execute_swarm_task(db, task)
    return completed
