import json
import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.swarm import SwarmAgent, SwarmTask
from app.models.swarm_pipeline import NexusPipeline
from app.services.swarm_executor import execute_swarm_task

logger = logging.getLogger(__name__)


def _select_reviewer(agents: list[SwarmAgent], synthesizer_agent: SwarmAgent) -> SwarmAgent:
    non_synthesizers = [a for a in agents if a.agent_instance_id != synthesizer_agent.agent_instance_id]
    candidates = non_synthesizers if non_synthesizers else agents

    for agent in candidates:
        caps = agent.capabilities or {}
        if "review" in caps or "quality" in caps:
            return agent

    return candidates[0]


async def run_review(
    db: AsyncSession,
    pipeline: NexusPipeline,
    synthesis_task: SwarmTask,
    agents: list[SwarmAgent],
    session_factory=None,
) -> dict:
    synthesizer_id = synthesis_task.assigned_agent_id
    synthesizer_mock = next(
        (a for a in agents if a.agent_instance_id == synthesizer_id),
        agents[0],
    )
    reviewer = _select_reviewer(agents, synthesizer_mock)

    synthesis_text = (synthesis_task.result or {}).get("text", "")

    prompt = (
        f"Evaluate this output against the original objective. "
        f"Objective: {pipeline.objective}. "
        f"Output: {synthesis_text}. "
        f'Respond with JSON: {{"verdict": "PASS"|"FAIL", '
        f'"feedback": "detailed feedback if FAIL, null if PASS", '
        f'"score": 1-10}}'
    )

    task = SwarmTask(
        id=uuid4().hex[:12],
        swarm_id=pipeline.swarm_id,
        task_type="pipeline_subtask",
        payload={"prompt": prompt, "pipeline_id": pipeline.id, "phase": "review"},
        assigned_agent_id=reviewer.agent_instance_id,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    completed = await execute_swarm_task(db, task)
    response_text = (completed.result or {}).get("text", "") if completed else ""

    try:
        parsed = json.loads(response_text)
        verdict = parsed.get("verdict", "PASS")
        if verdict not in ("PASS", "FAIL"):
            verdict = "PASS"
        return {
            "verdict": verdict,
            "feedback": parsed.get("feedback"),
            "score": int(parsed.get("score", 7)),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("Review phase: non-JSON response from LLM, defaulting to PASS")
        return {
            "verdict": "PASS",
            "feedback": response_text or None,
            "score": 7,
        }
