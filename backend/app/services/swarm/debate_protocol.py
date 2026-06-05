"""
DebateProtocol — round-by-round multi-agent debate with LLM judge scoring.

Flow:
  Agent A → Position A
  Agent B → Position B (responding to A)
  Agent A → Rebuttal A
  Agent B → Rebuttal B
  Judge → Score both positions → Consensus or deadlock
"""

import json
import logging
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent import AgentMessage, DebateRound

logger = logging.getLogger(__name__)


DEBATE_POSITION_PROMPT = """You are {agent_name}, a specialist agent. You are participating in a structured debate.

**Topic:** {topic}

**Your role:** Present a well-reasoned position. Be thorough, cite reasoning, and anticipate counter-arguments.

**Previous context (if any):**
{context}

**Evaluation criteria:**
{criteria}

Respond with ONLY your position. Be concise but complete."""


DEBATE_REBUTTAL_PROMPT = """You are {agent_name}, a specialist agent. You are responding to an opposing position in a debate.

**Topic:** {topic}

**Opposing position:**
{opposing_position}

**Your previous position:**
{my_previous_position}

**Your task:** Rebut the opposing position. Point out flaws, missing context, or stronger alternatives. Strengthen your own position in response.

**Evaluation criteria:**
{criteria}

Respond with ONLY your rebuttal. Be specific about which points you're addressing."""


JUDGE_PROMPT = """You are an impartial judge evaluating a debate between two agents.

**Topic:** {topic}

**Evaluation criteria:**
{criteria}

**Agent A position:**
{position_a}

**Agent A rebuttal:**
{rebuttal_a}

**Agent B position:**
{position_b}

**Agent B rebuttal:**
{rebuttal_b}

Score each agent on a 0-10 scale for each criterion, then provide an overall verdict.

Respond with ONLY valid JSON:
{{
  "score_a": <float 0-10>,
  "score_b": <float 0-10>,
  "reasoning": "<detailed explanation>",
  "verdict": "<a_wins|b_wins|tie|deadlock>",
  "strengths_a": ["<point>", ...],
  "strengths_b": ["<point>", ...],
  "consensus_possible": <true|false>,
  "synthesis": "<if consensus possible, a synthesized position combining the best of both>"
}}"""


SYNTHESIS_PROMPT = """You are a synthesis expert. Two agents debated a topic and the judge found consensus was possible.

**Topic:** {topic}

**Agent A key points:**
{strengths_a}

**Agent B key points:**
{strengths_b}

**Judge notes:**
{judge_notes}

Synthesize a unified position that incorporates the best arguments from both agents. Remove contradictions, blend complementary viewpoints, and produce a final answer that is stronger than either individual position."""


class DebateProtocol:
    """Orchestrates round-by-round debates between two agents with an LLM judge."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def debate(
        self,
        topic: str,
        agent_a_id: str,
        agent_a_name: str,
        agent_b_id: str,
        agent_b_name: str,
        judge_id: str = "llm-judge",
        criteria: dict[str, Any] | None = None,
        max_rounds: int = 2,
        metadata: dict[str, Any] | None = None,
    ) -> DebateRound:
        """Run a complete debate between two agents."""
        if criteria is None:
            criteria = {
                "accuracy": "Factual correctness and precision",
                "completeness": "Coverage of all relevant aspects",
                "reasoning": "Logical coherence and argument strength",
                "creativity": "Novelty and originality of approach",
                "clarity": "Clear, concise communication",
            }

        debate_id = str(uuid4())

        for round_num in range(1, max_rounds + 1):
            debate_round = await self._run_round(
                debate_id=debate_id,
                topic=topic,
                agent_a_id=agent_a_id,
                agent_a_name=agent_a_name,
                agent_b_id=agent_b_id,
                agent_b_name=agent_b_name,
                judge_id=judge_id,
                criteria=criteria,
                round_number=round_num,
                metadata=metadata,
            )

            # If consensus reached, return
            if debate_round.consensus_reached:
                logger.info(
                    f"Debate {debate_id} reached consensus in round {round_num}"
                )
                return debate_round

        # Max rounds reached without consensus — mark deadlock
        debate_round = DebateRound(
            debate_id=debate_id,
            round_number=max_rounds,
            topic=topic,
            criteria=criteria,
            judge_verdict="deadlock",
            consensus_reached=False,
            status="deadlocked",
            metadata_=metadata,
        )
        self.db.add(debate_round)
        await self.db.flush()
        return debate_round

    async def _run_round(
        self,
        debate_id: str,
        topic: str,
        agent_a_id: str,
        agent_a_name: str,
        agent_b_id: str,
        agent_b_name: str,
        judge_id: str,
        criteria: dict[str, Any],
        round_number: int,
        metadata: dict[str, Any] | None = None,
    ) -> DebateRound:
        """Execute one debate round: positions → rebuttals → judge scoring."""

        criteria_text = "\n".join(f"- {k}: {v}" for k, v in criteria.items())

        # Step 1: Both agents present positions (can be parallel)
        position_a = await self._call_llm(
            system=DEBATE_POSITION_PROMPT.format(
                agent_name=agent_a_name,
                topic=topic,
                context="This is round " + str(round_number),
                criteria=criteria_text,
            ),
            user_content=topic,
        )

        position_b = await self._call_llm(
            system=DEBATE_POSITION_PROMPT.format(
                agent_name=agent_b_name,
                topic=topic,
                context=f"This is round {round_number}. Agent A's position: {position_a[:500]}",
                criteria=criteria_text,
            ),
            user_content=f"Topic: {topic}\n\nAgent A's position:\n{position_a[:1000]}",
        )

        # Record message for A
        msg_a = AgentMessage(
            sender_id=agent_a_id,
            sender_name=agent_a_name,
            recipient_id=debate_id,
            type="debate_position",
            sub_type="opening",
            content=position_a,
            priority=0,
            correlation_id=debate_id,
            metadata_=metadata,
        )
        self.db.add(msg_a)

        # Record message for B
        msg_b = AgentMessage(
            sender_id=agent_b_id,
            sender_name=agent_b_name,
            recipient_id=debate_id,
            type="debate_position",
            sub_type="opening",
            content=position_b,
            priority=0,
            correlation_id=debate_id,
            metadata_=metadata,
        )
        self.db.add(msg_b)

        # Step 2: Rebuttals
        rebuttal_a = await self._call_llm(
            system=DEBATE_REBUTTAL_PROMPT.format(
                agent_name=agent_a_name,
                topic=topic,
                opposing_position=position_b[:1500],
                my_previous_position=position_a[:500],
                criteria=criteria_text,
            ),
            user_content=f"Opposing position:\n{position_b[:1500]}",
        )

        rebuttal_b = await self._call_llm(
            system=DEBATE_REBUTTAL_PROMPT.format(
                agent_name=agent_b_name,
                topic=topic,
                opposing_position=position_a[:1500],
                my_previous_position=position_b[:500],
                criteria=criteria_text,
            ),
            user_content=f"Opposing position:\n{position_a[:1500]}",
        )

        # Record rebuttal messages
        msg_rebuttal_a = AgentMessage(
            sender_id=agent_a_id,
            sender_name=agent_a_name,
            recipient_id=debate_id,
            type="debate_position",
            sub_type="rebuttal",
            content=rebuttal_a,
            priority=0,
            correlation_id=debate_id,
            parent_message_id=msg_a.id,
            metadata_=metadata,
        )
        self.db.add(msg_rebuttal_a)

        msg_rebuttal_b = AgentMessage(
            sender_id=agent_b_id,
            sender_name=agent_b_name,
            recipient_id=debate_id,
            type="debate_position",
            sub_type="rebuttal",
            content=rebuttal_b,
            priority=0,
            correlation_id=debate_id,
            parent_message_id=msg_b.id,
            metadata_=metadata,
        )
        self.db.add(msg_rebuttal_b)

        # Step 3: Judge scores both
        judge_result = await self._judge(
            topic=topic,
            criteria_text=criteria_text,
            position_a=position_a,
            position_b=position_b,
            rebuttal_a=rebuttal_a,
            rebuttal_b=rebuttal_b,
        )

        # Record judge message
        judge_msg = AgentMessage(
            sender_id=judge_id,
            sender_name="LLM Judge",
            recipient_id=debate_id,
            type="debate_position",
            sub_type="judge_verdict",
            content=judge_result.get("reasoning", ""),
            priority=1,
            correlation_id=debate_id,
            metadata_={
                "score_a": judge_result.get("score_a"),
                "score_b": judge_result.get("score_b"),
                "verdict": judge_result.get("verdict"),
                "consensus_possible": judge_result.get("consensus_possible"),
                **(metadata or {}),
            },
        )
        self.db.add(judge_msg)

        # Build round record
        debate_round = DebateRound(
            debate_id=debate_id,
            round_number=round_number,
            topic=topic,
            criteria=criteria,
            position_a=position_a,
            position_b=position_b,
            rebuttal_a=rebuttal_a,
            rebuttal_b=rebuttal_b,
            agent_a_id=agent_a_id,
            agent_b_id=agent_b_id,
            judge_id=judge_id,
            judge_score_a=judge_result.get("score_a"),
            judge_score_b=judge_result.get("score_b"),
            judge_reasoning=judge_result.get("reasoning"),
            judge_verdict=judge_result.get("verdict"),
            status="completed",
            metadata_=metadata,
        )

        # Consensus check
        if judge_result.get("consensus_possible"):
            # Synthesize a unified position
            synthesis = await self._call_llm(
                system=SYNTHESIS_PROMPT.format(
                    topic=topic,
                    strengths_a=json.dumps(judge_result.get("strengths_a", [])),
                    strengths_b=json.dumps(judge_result.get("strengths_b", [])),
                    judge_notes=judge_result.get("reasoning", ""),
                ),
                user_content=f"Topic: {topic}",
            )

            debate_round.consensus_reached = True
            debate_round.consensus_synthesis = synthesis
            debate_round.consensus_score = (
                max(
                    judge_result.get("score_a", 5),
                    judge_result.get("score_b", 5),
                )
                / 10.0
            )

            # Record synthesis message
            synth_msg = AgentMessage(
                sender_id=judge_id,
                sender_name="LLM Judge",
                recipient_id=debate_id,
                type="debate_position",
                sub_type="consensus_synthesis",
                content=synthesis,
                priority=1,
                correlation_id=debate_id,
                metadata_=metadata,
            )
            self.db.add(synth_msg)

        self.db.add(debate_round)
        await self.db.flush()
        return debate_round

    async def _judge(
        self,
        topic: str,
        criteria_text: str,
        position_a: str,
        position_b: str,
        rebuttal_a: str,
        rebuttal_b: str,
    ) -> dict[str, Any]:
        """LLM judge scores both positions."""
        raw = await self._call_llm(
            system=JUDGE_PROMPT.format(
                topic=topic,
                criteria=criteria_text,
                position_a=position_a,
                position_b=position_b,
                rebuttal_a=rebuttal_a,
                rebuttal_b=rebuttal_b,
            ),
            user_content="Evaluate the debate and return JSON.",
        )

        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse judge output: {raw[:200]}")
            return {
                "score_a": 5.0,
                "score_b": 5.0,
                "reasoning": "Judge output unparseable — defaulting to tie.",
                "verdict": "tie",
                "strengths_a": [],
                "strengths_b": [],
                "consensus_possible": False,
            }

    async def _call_llm(self, system: str, user_content: str) -> str:
        """Call the LLM API."""
        model_name = settings.LLM_MODEL_NAME
        if "/" in model_name:
            model_name = model_name.split("/", 1)[1]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.LLM_API_KEY}",
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.4,
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.LLM_API_BASE}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def get_debate(self, debate_id: str) -> list[DebateRound]:
        """Get all rounds for a debate."""
        result = await self.db.execute(
            select(DebateRound)
            .where(DebateRound.debate_id == debate_id)
            .order_by(DebateRound.round_number)
        )
        return list(result.scalars().all())

    async def list_debates(self, limit: int = 20) -> list[DebateRound]:
        """List recent debate rounds."""
        result = await self.db.execute(
            select(DebateRound).order_by(DebateRound.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
