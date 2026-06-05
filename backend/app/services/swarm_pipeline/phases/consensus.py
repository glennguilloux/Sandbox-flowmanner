import json
import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.swarm import SwarmAgent, SwarmConsensusRound, SwarmTask
from app.models.swarm_pipeline import NexusPipeline

logger = logging.getLogger(__name__)


def _extract_disputed_points(debate_tasks: list[SwarmTask]) -> list[dict]:
    disputed: list[dict] = []
    for task in debate_tasks:
        text = (task.result or {}).get("text", "")
        try:
            review = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        weaknesses = review.get("weaknesses", [])
        if not weaknesses:
            continue
        for weakness in weaknesses:
            topic = weakness.replace(" ", "_").lower()[:50] if isinstance(weakness, str) else "disputed_point"
            disputed.append({"topic": topic, "description": weakness if isinstance(weakness, str) else str(weakness)})
    return disputed


def _tally_votes(agent_votes: dict[str, str], agents: list[SwarmAgent]) -> str:
    approve_count = sum(1 for v in agent_votes.values() if v == "approve")
    reject_count = sum(1 for v in agent_votes.values() if v == "reject")
    if approve_count > reject_count:
        return "approved"
    if reject_count > approve_count:
        return "rejected"
    tiebreaker = sorted(agents, key=lambda a: a.agent_instance_id)[0]
    return "approved" if agent_votes.get(tiebreaker.agent_instance_id) == "approve" else "rejected"


async def run_consensus(
    db: AsyncSession,
    pipeline: NexusPipeline,
    debate_tasks: list[SwarmTask],
    draft_tasks: list[SwarmTask],
    agents: list[SwarmAgent],
    user_id: str = "system",
    disputed_points: list[dict] | None = None,
    agent_votes: dict[str, str] | None = None,
) -> dict:
    if disputed_points is None:
        disputed_points = _extract_disputed_points(debate_tasks)

    if not disputed_points:
        return {
            "resolved_points": [],
            "strategy": "unanimous",
            "rounds": [],
            "drafts": {
                agent.agent_instance_id: draft_tasks[i].result for i, agent in enumerate(agents) if i < len(draft_tasks)
            },
        }

    default_votes: dict[str, str] = {}
    if agent_votes is None:
        agent_votes = default_votes

    resolved_points: list[dict] = []
    round_ids: list[str] = []

    for point in disputed_points:
        votes_for_round = {agent_id: {"vote": vote} for agent_id, vote in agent_votes.items()}
        resolution = _tally_votes(agent_votes, agents) if agent_votes else "approved"

        consensus_round = SwarmConsensusRound(
            id=uuid4().hex[:12],
            swarm_id=pipeline.swarm_id,
            proposal={
                "topic": point["topic"],
                "description": point.get("description", ""),
                "positions": [
                    {"agent_id": a.agent_instance_id, "vote": agent_votes.get(a.agent_instance_id, "approve")}
                    for a in agents
                ],
            },
            votes=votes_for_round,
            result=resolution,
            strategy_used="simple_majority",
        )

        db.add(consensus_round)
        await db.commit()
        await db.refresh(consensus_round)

        resolved_points.append({"topic": point["topic"], "resolution": resolution})
        round_ids.append(consensus_round.id)

    return {
        "resolved_points": resolved_points,
        "strategy": "simple_majority",
        "rounds": round_ids,
    }
