"""Swarm Protocol API — debate, handoff, and escalation endpoints.

These endpoints wire the existing DebateProtocol, HandoffProtocol, and
EscalationChain services to HTTP routes expected by the frontend SwarmDashboard.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.swarm.debate_protocol import DebateProtocol
from app.services.swarm.escalation_chain import EscalationChain
from app.services.swarm.handoff_protocol import HandoffProtocol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/protocol", tags=["swarm-protocol"])


# ── Pydantic request/response models ──────────────────────────────────────


class DebateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=5000)
    agent_a_id: str
    agent_a_name: str
    agent_b_id: str
    agent_b_name: str
    max_rounds: int = Field(2, ge=1, le=5)


class HandoffDelegateRequest(BaseModel):
    from_agent_id: str
    from_agent_name: str
    task_description: str = Field(..., min_length=1, max_length=5000)
    task_type: str = "general"
    to_agent_id: str | None = None
    priority: int = Field(0, ge=-1, le=2)


class HandoffCompleteRequest(BaseModel):
    result: str
    result_metadata: dict[str, Any] | None = None


class HandoffRejectRequest(BaseModel):
    reason: str = "Agent declined the handoff"


class EscalateRequest(BaseModel):
    task_id: str
    task_description: str = Field(..., min_length=1, max_length=5000)
    error_message: str
    current_agent_id: str | None = None
    current_agent_name: str | None = None
    policy: str = Field(
        "default", pattern="^(default|aggressive|conservative|never_escalate)$"
    )


class ResolveEscalationRequest(BaseModel):
    resolution_output: str


# ── Helpers ────────────────────────────────────────────────────────────────


def _handoff_to_dict(h) -> dict[str, Any]:
    """Map backend HandoffRecord to frontend HandoffRecord shape."""
    return {
        "handoff_id": h.id,
        "from": h.from_agent_name or h.from_agent_id,
        "to": h.to_agent_name or h.to_agent_id,
        "task": h.task_description,
        "task_description": h.task_description,
        "status": h.status,
        "priority": h.priority,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


def _escalation_to_dict(e) -> dict[str, Any]:
    """Map backend EscalationRecord to frontend EscalationRecord shape."""
    return {
        "escalation_id": e.id,
        "task_id": e.task_id,
        "task_description": e.task_description,
        "level": e.level,
        "status": e.status,
        "escalated_to": e.escalated_to_agent_name,
        "resolved": e.resolved,
        "error_message": e.error_message,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ── Debate ─────────────────────────────────────────────────────────────────


@router.post("/debate")
async def start_debate(
    body: DebateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Start a multi-agent debate with LLM judge scoring."""
    protocol = DebateProtocol(db)
    try:
        round_result = await protocol.debate(
            topic=body.topic,
            agent_a_id=body.agent_a_id,
            agent_a_name=body.agent_a_name,
            agent_b_id=body.agent_b_id,
            agent_b_name=body.agent_b_name,
            max_rounds=body.max_rounds,
        )
    except Exception as e:
        logger.exception("Debate failed")
        raise HTTPException(500, f"Debate execution failed: {e}")

    return {
        "debate_id": round_result.debate_id,
        "round_number": round_result.round_number,
        "judge_verdict": round_result.judge_verdict,
        "judge_score_a": round_result.judge_score_a,
        "judge_score_b": round_result.judge_score_b,
        "consensus_reached": round_result.consensus_reached,
        "consensus_synthesis": round_result.consensus_synthesis,
        "status": round_result.status,
    }


@router.get("/debate/{debate_id}")
async def get_debate(
    debate_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all rounds for a debate."""
    protocol = DebateProtocol(db)
    rounds = await protocol.get_debate(debate_id)
    if not rounds:
        raise HTTPException(404, "Debate not found")

    return {
        "debate_id": debate_id,
        "rounds": [
            {
                "round_number": r.round_number,
                "position_a": r.position_a,
                "position_b": r.position_b,
                "rebuttal_a": r.rebuttal_a,
                "rebuttal_b": r.rebuttal_b,
                "judge_verdict": r.judge_verdict,
                "judge_score_a": r.judge_score_a,
                "judge_score_b": r.judge_score_b,
                "judge_reasoning": r.judge_reasoning,
                "consensus_reached": r.consensus_reached,
                "consensus_synthesis": r.consensus_synthesis,
                "consensus_score": r.consensus_score,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rounds
        ],
    }


# ── Handoffs ───────────────────────────────────────────────────────────────


@router.post("/handoff/delegate")
async def delegate_handoff(
    body: HandoffDelegateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delegate a subtask from one agent to another."""
    protocol = HandoffProtocol(db)
    try:
        handoff = await protocol.delegate(
            from_agent_id=body.from_agent_id,
            from_agent_name=body.from_agent_name,
            task_description=body.task_description,
            task_type=body.task_type,
            to_agent_id=body.to_agent_id,
            priority=body.priority,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("Handoff delegate failed")
        raise HTTPException(500, f"Handoff delegation failed: {e}")

    return _handoff_to_dict(handoff)


@router.post("/handoff/{handoff_id}/accept")
async def accept_handoff(
    handoff_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Accept a pending handoff."""
    protocol = HandoffProtocol(db)
    handoff = await protocol.accept(handoff_id)
    if not handoff:
        raise HTTPException(404, "Handoff not found")
    return _handoff_to_dict(handoff)


@router.post("/handoff/{handoff_id}/complete")
async def complete_handoff(
    handoff_id: str,
    body: HandoffCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Complete a handoff with results."""
    protocol = HandoffProtocol(db)
    handoff = await protocol.complete(
        handoff_id=handoff_id,
        result=body.result,
        result_metadata=body.result_metadata,
    )
    if not handoff:
        raise HTTPException(404, "Handoff not found")
    return _handoff_to_dict(handoff)


@router.post("/handoff/{handoff_id}/reject")
async def reject_handoff(
    handoff_id: str,
    body: HandoffRejectRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending handoff."""
    protocol = HandoffProtocol(db)
    handoff = await protocol.reject(handoff_id=handoff_id, reason=body.reason)
    if not handoff:
        raise HTTPException(404, "Handoff not found")
    return _handoff_to_dict(handoff)


@router.get("/handoffs")
async def list_handoffs(
    agent_id: str | None = None,
    status: str | None = None,
    execution_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List handoffs with optional filters."""
    protocol = HandoffProtocol(db)
    handoffs = await protocol.list_handoffs(
        agent_id=agent_id,
        status=status,
        execution_id=execution_id,
        limit=limit,
    )
    return {"handoffs": [_handoff_to_dict(h) for h in handoffs]}


@router.get("/handoff/{handoff_id}/chain")
async def get_handoff_chain(
    handoff_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the full parent→child chain for a handoff."""
    protocol = HandoffProtocol(db)
    chain = await protocol.get_chain(handoff_id)
    return {
        "handoff_id": handoff_id,
        "chain": [_handoff_to_dict(h) for h in chain],
    }


# ── Escalation ─────────────────────────────────────────────────────────────


@router.post("/escalate")
async def escalate_task(
    body: EscalateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Start or continue an escalation chain for a failed task."""
    chain = EscalationChain(db)
    try:
        record = await chain.escalate(
            task_id=body.task_id,
            task_description=body.task_description,
            error_message=body.error_message,
            current_agent_id=body.current_agent_id,
            current_agent_name=body.current_agent_name,
            policy=body.policy,
        )
    except Exception as e:
        logger.exception("Escalation failed")
        raise HTTPException(500, f"Escalation failed: {e}")

    return _escalation_to_dict(record)


@router.post("/escalate/{escalation_id}/resolve")
async def resolve_escalation(
    escalation_id: str,
    body: ResolveEscalationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Mark an escalation as resolved."""
    chain = EscalationChain(db)
    record = await chain.resolve(
        escalation_id=escalation_id,
        resolution_output=body.resolution_output,
    )
    if not record:
        raise HTTPException(404, "Escalation not found")
    return _escalation_to_dict(record)


@router.get("/escalations")
async def list_escalations(
    resolved: bool | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List escalation records, optionally filtered by resolution status."""
    chain = EscalationChain(db)
    records = await chain.list_escalations(resolved=resolved, limit=limit)
    return {"escalations": [_escalation_to_dict(r) for r in records]}


@router.get("/dead-letters")
async def list_dead_letters(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all dead-letter escalations (max retries exceeded)."""
    chain = EscalationChain(db)
    records = await chain.list_dead_letters(limit=limit)
    return {"dead_letters": [_escalation_to_dict(r) for r in records]}
