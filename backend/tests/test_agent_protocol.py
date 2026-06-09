"""
Tests for Phase 26 Week 3: Agent Protocol — AgentMessage, Debate, Handoff, Escalation.

Tests the inter-agent communication protocol layer: message persistence,
debate orchestration, task handoff delegation, and failure escalation chains.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ["OPENAI_API_KEY"] = "sk-test-key-123"
os.environ["LANGFUSE_PUBLIC_KEY"] = "test-public-key"
os.environ["LANGFUSE_SECRET_KEY"] = "test-secret-key"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-123"
os.environ["AES_ENCRYPTION_KEY"] = "test-aes-key-16-char"
os.environ["APP_ENV"] = "test"
os.environ["LANGFUSE_ENABLED"] = "false"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_db():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def make_llm_response(content: str) -> dict:
    """Build a fake LLM API response."""
    return {"choices": [{"message": {"content": content}}]}


# ---------------------------------------------------------------------------
# AgentMessage Model Tests
# ---------------------------------------------------------------------------


class TestAgentMessage:
    """AgentMessage model persistence and validation."""

    def test_create_basic_message(self):
        from app.models.agent import AgentMessage

        msg = AgentMessage(
            sender_id="agent_a",
            sender_name="Agent A",
            recipient_id="agent_b",
            recipient_name="Agent B",
            type="task",
            content="Analyze this dataset",
            priority=1,
            status="delivered",
        )
        assert msg.sender_id == "agent_a"
        assert msg.type == "task"
        assert msg.priority == 1
        assert msg.status == "delivered"

    def test_message_threading(self):
        from app.models.agent import AgentMessage

        parent = AgentMessage(
            sender_id="a",
            recipient_id="b",
            type="query",
            content="What is the answer?",
            priority=0,
        )
        child = AgentMessage(
            sender_id="b",
            recipient_id="a",
            type="response",
            content="The answer is 42.",
            priority=0,
            parent_message_id=parent.id,
            correlation_id=parent.id,
        )
        assert child.parent_message_id == parent.id
        assert child.correlation_id == parent.id

    def test_all_message_types(self):
        from app.models.agent import AgentMessage

        types = [
            "task",
            "query",
            "response",
            "error",
            "handoff",
            "status",
            "debate_position",
        ]
        for t in types:
            msg = AgentMessage(sender_id="a", recipient_id="b", type=t, content="test")
            assert msg.type == t, f"Type {t} failed"


class TestDebateRound:
    """DebateRound model."""

    def test_create_round(self):
        from app.models.agent import DebateRound

        round_ = DebateRound(
            debate_id="debate-1",
            round_number=1,
            topic="Is X better than Y?",
            position_a="Position A...",
            position_b="Position B...",
            agent_a_id="agent-1",
            agent_b_id="agent-2",
            status="pending",
            consensus_reached=False,
        )
        assert round_.debate_id == "debate-1"
        assert round_.round_number == 1
        assert round_.consensus_reached is False


class TestHandoffRecord:
    """HandoffRecord model."""

    def test_create_handoff(self):
        from app.models.agent import HandoffRecord

        h = HandoffRecord(
            from_agent_id="agent_a",
            from_agent_name="Agent A",
            to_agent_id="agent_b",
            to_agent_name="Agent B",
            task_description="Summarize the document",
            task_type="summarization",
            priority=1,
            status="pending",
        )
        assert h.status == "pending"
        assert h.task_type == "summarization"


class TestEscalationRecord:
    """EscalationRecord model."""

    def test_create_escalation(self):
        from app.models.agent import EscalationRecord

        e = EscalationRecord(
            task_id="task-1",
            task_description="Complex analysis",
            level=0,
            attempted_agent_name="General Agent",
            error_message="Timeout",
            status="active",
            resolved=False,
        )
        assert e.level == 0
        assert e.resolved is False


# ---------------------------------------------------------------------------
# DebateProtocol Tests
# ---------------------------------------------------------------------------


class TestDebateProtocol:
    """DebateProtocol service — round-by-round debate with LLM judge."""

    @pytest.mark.asyncio
    async def test_debate_flow(self):
        from app.services.swarm.debate_protocol import DebateProtocol

        db = make_mock_db()

        judge_json = (
            '{"score_a": 8.0, "score_b": 6.5, '
            '"reasoning": "Agent A was more thorough.", '
            '"verdict": "a_wins", '
            '"strengths_a": ["Strong logic"], '
            '"strengths_b": ["Good examples"], '
            '"consensus_possible": true}'
        )

        with patch("httpx.AsyncClient.post") as mock_post:
            # Mock 5 LLM calls: positions A+B, rebuttals A+B, judge, synthesis
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json = MagicMock(
                side_effect=[
                    make_llm_response("Position A: X is better because..."),
                    make_llm_response("Position B: Y is better because..."),
                    make_llm_response("Rebuttal A: B's argument has flaws..."),
                    make_llm_response("Rebuttal B: A missed key context..."),
                    make_llm_response(judge_json),
                    make_llm_response("Synthesis: Both X and Y have merits..."),
                ]
            )

            protocol = DebateProtocol(db)
            result = await protocol.debate(
                topic="Is Python better than JavaScript?",
                agent_a_id="agent-python",
                agent_a_name="Python Advocate",
                agent_b_id="agent-js",
                agent_b_name="JS Advocate",
            )

            assert result is not None
            assert result.consensus_reached is True
            assert result.judge_verdict == "a_wins"
            assert db.flush.call_count >= 1

    @pytest.mark.asyncio
    async def test_debate_no_consensus(self):
        from app.services.swarm.debate_protocol import DebateProtocol

        db = make_mock_db()

        judge_json = (
            '{"score_a": 5.0, "score_b": 5.0, '
            '"reasoning": "Both sides equally valid.", '
            '"verdict": "tie", '
            '"strengths_a": [], '
            '"strengths_b": [], '
            '"consensus_possible": false}'
        )

        with patch("httpx.AsyncClient.post") as mock_post:
            # Each round: 4 agent calls + 1 judge = 5 calls per round
            # Round 1 + Round 2 = 10 calls (no synthesis since no consensus)
            responses = []
            for _ in range(2):  # 2 rounds
                responses.extend(
                    [
                        make_llm_response("Position A..."),
                        make_llm_response("Position B..."),
                        make_llm_response("Rebuttal A..."),
                        make_llm_response("Rebuttal B..."),
                        make_llm_response(judge_json),
                    ]
                )
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json = MagicMock(side_effect=responses)

            protocol = DebateProtocol(db)
            result = await protocol.debate(
                topic="Tabs vs Spaces?",
                agent_a_id="tab-advocate",
                agent_a_name="Tab User",
                agent_b_id="space-advocate",
                agent_b_name="Space User",
                max_rounds=2,
            )

            assert result.consensus_reached is False
            assert result.judge_verdict is None or result.status == "deadlocked"


# ---------------------------------------------------------------------------
# HandoffProtocol Tests
# ---------------------------------------------------------------------------


class TestHandoffProtocol:
    """HandoffProtocol service — structured subtask delegation."""

    @pytest.mark.asyncio
    async def test_delegate_with_explicit_target(self):
        from app.services.swarm.handoff_protocol import HandoffProtocol

        db = make_mock_db()

        protocol = HandoffProtocol(db)
        # Patch registry.get_capability
        with patch.object(
            protocol.registry, "get_capability", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = MagicMock(name="Data Analyst")

            handoff = await protocol.delegate(
                from_agent_id="agent-main",
                from_agent_name="Main Agent",
                task_description="Analyze the sales data",
                task_type="analysis",
                to_agent_id="specialist-1",
            )

            assert handoff.status == "pending"
            assert handoff.to_agent_id == "specialist-1"
            assert handoff.from_agent_name == "Main Agent"
            assert db.flush.call_count >= 1  # handoff + message flushed

    @pytest.mark.asyncio
    async def test_accept_handoff(self):
        from app.models.agent import HandoffRecord
        from app.services.swarm.handoff_protocol import HandoffProtocol

        db = make_mock_db()

        handoff = HandoffRecord(
            from_agent_id="a",
            from_agent_name="Agent A",
            to_agent_id="b",
            to_agent_name="Agent B",
            task_description="Do the thing",
            status="pending",
        )

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=handoff)),
        ]

        protocol = HandoffProtocol(db)
        result = await protocol.accept(handoff.id)

        assert result is not None
        assert result.status == "accepted"

    @pytest.mark.asyncio
    async def test_complete_handoff(self):
        from app.models.agent import HandoffRecord
        from app.services.swarm.handoff_protocol import HandoffProtocol

        db = make_mock_db()

        handoff = HandoffRecord(
            from_agent_id="a",
            from_agent_name="Agent A",
            to_agent_id="b",
            to_agent_name="Agent B",
            task_description="Do the thing",
            status="accepted",
        )

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=handoff)),
        ]

        protocol = HandoffProtocol(db)
        result = await protocol.complete(
            handoff.id,
            result="Task completed successfully.",
            result_metadata={"tokens": 500},
        )

        assert result is not None
        assert result.status == "completed"
        assert result.result == "Task completed successfully."

    @pytest.mark.asyncio
    async def test_reject_handoff(self):
        from app.models.agent import HandoffRecord
        from app.services.swarm.handoff_protocol import HandoffProtocol

        db = make_mock_db()

        handoff = HandoffRecord(
            from_agent_id="a",
            to_agent_id="b",
            task_description="Do the thing",
            status="pending",
        )
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=handoff)),
        ]

        protocol = HandoffProtocol(db)
        result = await protocol.reject(handoff.id, "Not my area")

        assert result is not None
        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_fail_handoff(self):
        from app.models.agent import HandoffRecord
        from app.services.swarm.handoff_protocol import HandoffProtocol

        db = make_mock_db()

        handoff = HandoffRecord(
            from_agent_id="a",
            to_agent_id="b",
            task_description="Do the thing",
            status="in_progress",
        )
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=handoff)),
        ]

        protocol = HandoffProtocol(db)
        result = await protocol.fail(handoff.id, "LLM timeout")

        assert result is not None
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_handoff_not_found(self):
        from app.services.swarm.handoff_protocol import HandoffProtocol

        db = make_mock_db()
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        protocol = HandoffProtocol(db)
        result = await protocol.accept("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# EscalationChain Tests
# ---------------------------------------------------------------------------


class TestEscalationChain:
    """EscalationChain service — failure escalation with retry policies."""

    @pytest.mark.asyncio
    async def test_new_escalation_level_0(self):
        from app.services.swarm.escalation_chain import EscalationChain

        db = make_mock_db()
        # First query: _get_active returns None (no existing escalation)
        db.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=None))
                )
            ),
        ]

        chain = EscalationChain(db)
        record = await chain.escalate(
            task_id="task-1",
            task_description="Complex analysis",
            error_message="LLM timeout",
            current_agent_id="agent-1",
            current_agent_name="General Agent",
            policy="default",
        )

        assert record is not None
        assert record.level == 0  # default: max_retries_same=2, so stays at 0
        assert record.status == "retrying"
        assert record.task_id == "task-1"

    @pytest.mark.asyncio
    async def test_continue_escalation(self):
        from app.models.agent import EscalationRecord
        from app.services.swarm.escalation_chain import EscalationChain

        db = make_mock_db()

        existing = EscalationRecord(
            task_id="task-1",
            task_description="Complex analysis",
            level=0,
            attempted_agent_name="General Agent",
            error_message="Timeout",
            max_retries_per_level=2,
            retries_at_level=1,
            status="retrying",
            resolved=False,
        )

        db.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=existing))
                )
            ),
        ]

        with patch.object(
            EscalationChain, "_find_specialist", new_callable=AsyncMock
        ) as mock_find:
            mock_find.return_value = {
                "agent_id": "specialist-1",
                "name": "Specialist Agent",
            }

            chain = EscalationChain(db)
            record = await chain.escalate(
                task_id="task-1",
                task_description="Complex analysis",
                error_message="Still failing",
                current_agent_id="agent-1",
                current_agent_name="General Agent",
            )

            # Level 0, retry 1 → should escalate to level 1
            assert record.level == 1
            assert record.status == "escalated"
            assert record.escalated_to_agent_name == "Specialist Agent"

    @pytest.mark.asyncio
    async def test_aggressive_policy(self):
        from app.services.swarm.escalation_chain import (
            POLICY_CONFIGS,
            EscalationChain,
        )

        # Aggressive: max_retries_same=1 → first call stays at level 0 (one retry allowed)
        aggressive = POLICY_CONFIGS["aggressive"]
        assert aggressive["max_retries_same"] == 1
        assert aggressive["max_retries_specialist"] == 1
        assert aggressive["max_retries_human"] == 1

        db = make_mock_db()
        db.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=None))
                )
            ),
        ]

        chain = EscalationChain(db)
        record = await chain.escalate(
            task_id="task-1",
            task_description="Urgent task",
            error_message="Failed",
            current_agent_id="agent-1",
            current_agent_name="Gen Agent",
            policy="aggressive",
        )

        # First escalation: max_retries_same=1 > 0, so stays at level 0 with retry
        assert record.level == 0
        assert record.status == "retrying"

    @pytest.mark.asyncio
    async def test_conservative_policy(self):
        from app.services.swarm.escalation_chain import POLICY_CONFIGS

        conservative = POLICY_CONFIGS["conservative"]
        assert conservative["max_retries_same"] == 3
        assert conservative["max_retries_specialist"] == 3
        assert conservative["total_max_retries"] == 8

    @pytest.mark.asyncio
    async def test_never_escalate_policy(self):
        from app.services.swarm.escalation_chain import EscalationChain

        db = make_mock_db()
        db.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=None))
                )
            ),
        ]

        chain = EscalationChain(db)
        record = await chain.escalate(
            task_id="task-1",
            task_description="Task",
            error_message="Failed",
            current_agent_id="agent-1",
            policy="never_escalate",
        )

        # Never-escalate: max_retries same=3, specialist=0, human=0
        # Since retries remaining > 0, stays at level 0
        assert record.status == "retrying"

    @pytest.mark.asyncio
    async def test_dead_letter_after_max_retries(self):
        from app.models.agent import EscalationRecord
        from app.services.swarm.escalation_chain import EscalationChain

        db = make_mock_db()

        # Existing escalation at level 3 = dead letter threshold
        existing = EscalationRecord(
            task_id="task-1",
            task_description="Dead task",
            level=2,
            max_retries_per_level=1,
            retries_at_level=0,
            status="escalated",
            resolved=False,
        )

        db.execute.side_effect = [
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=existing))
                )
            ),
        ]

        # Use aggressive policy with total_max_retries=3
        chain = EscalationChain(db)
        record = await chain.escalate(
            task_id="task-1",
            task_description="Dead task",
            error_message="Still failing after multiple attempts",
            current_agent_id="agent-1",
            policy="aggressive",
        )

        # Aggressive total_max_retries=3, retries_at_level=0 → level 3 is dead letter
        assert record.level == 3
        assert record.status == "dead_letter"

    @pytest.mark.asyncio
    async def test_resolve_escalation(self):
        from app.models.agent import EscalationRecord
        from app.services.swarm.escalation_chain import EscalationChain

        db = make_mock_db()

        escalation = EscalationRecord(
            task_id="task-1",
            task_description="Task",
            level=1,
            status="escalated",
            resolved=False,
        )
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=escalation)),
        ]

        chain = EscalationChain(db)
        result = await chain.resolve(
            escalation.id,
            resolution_output="Fixed by specialist.",
            resolution_agent_id="specialist-1",
        )

        assert result is not None
        assert result.resolved is True
        assert result.status == "resolved"
        assert result.resolution_output == "Fixed by specialist."
