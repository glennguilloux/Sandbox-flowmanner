"""Swarm Orchestration API — multi-agent goal execution."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.swarm.orchestrator import SwarmOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/swarm", tags=["swarm"])


class ExecuteRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=10000)
    strategy: str = Field("parallel", pattern="^(parallel|sequential|debate)$")
    max_agents: int = Field(5, ge=1, le=10)
    metadata: dict[str, Any] | None = None
    byok_key_id: int | None = Field(None, description="User API key ID to use instead of default LLM provider")
    model_override: str | None = Field(None, description="Override the model used by agents")


@router.post("/execute")
async def execute_swarm(
    body: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Execute a goal using multi-agent orchestration."""
    try:
        orchestrator = SwarmOrchestrator(db)
        execution = await orchestrator.execute(
            goal=body.goal,
            strategy=body.strategy,
            max_agents=body.max_agents,
            metadata=body.metadata,
            byok_key_id=body.byok_key_id,
            model_override=body.model_override,
        )
        tasks = await orchestrator.get_tasks(execution.id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Swarm execution failed")
        raise HTTPException(500, detail=str(e))

    return {
        "id": execution.id,
        "goal": execution.goal,
        "status": execution.status,
        "strategy": execution.strategy,
        "agent_count": execution.agent_count,
        "completed_count": execution.completed_count,
        "total_tokens": execution.total_tokens,
        "synthesis": execution.synthesis,
        "conflict_markers": execution.conflict_markers,
        "error_message": execution.error_message,
        "started_at": (execution.started_at.isoformat() if execution.started_at else None),
        "completed_at": (execution.completed_at.isoformat() if execution.completed_at else None),
        "tasks": [
            {
                "id": t.id,
                "agent_name": t.agent_name,
                "task_description": t.task_description,
                "task_type": t.task_type,
                "status": t.status,
                "output": t.output[:500] if t.output else None,
                "score": t.score,
                "tokens_used": t.tokens_used,
                "depends_on": t.depends_on,
            }
            for t in tasks
        ],
    }


@router.get("")
async def list_executions(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List recent swarm executions."""
    try:
        orchestrator = SwarmOrchestrator(db)
        executions = await orchestrator.list_executions(limit=limit)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list swarm executions")
        raise HTTPException(500, detail=str(e))

    return {
        "executions": [
            {
                "id": e.id,
                "goal": e.goal[:200],
                "status": e.status,
                "strategy": e.strategy,
                "agent_count": e.agent_count,
                "completed_count": e.completed_count,
                "total_tokens": e.total_tokens,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in executions
        ]
    }


@router.get("/{execution_id}")
async def get_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific swarm execution with all tasks."""
    try:
        orchestrator = SwarmOrchestrator(db)
        execution = await orchestrator.get_execution(execution_id)
        if not execution:
            raise HTTPException(404, "Execution not found")

        tasks = await orchestrator.get_tasks(execution_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get swarm execution")
        raise HTTPException(500, detail=str(e))

    return {
        "id": execution.id,
        "goal": execution.goal,
        "status": execution.status,
        "strategy": execution.strategy,
        "synthesis": execution.synthesis,
        "conflict_markers": execution.conflict_markers,
        "agent_count": execution.agent_count,
        "completed_count": execution.completed_count,
        "total_tokens": execution.total_tokens,
        "total_cost_usd": execution.total_cost_usd,
        "error_message": execution.error_message,
        "started_at": (execution.started_at.isoformat() if execution.started_at else None),
        "completed_at": (execution.completed_at.isoformat() if execution.completed_at else None),
        "tasks": [
            {
                "id": t.id,
                "agent_id": t.agent_id,
                "agent_name": t.agent_name,
                "task_description": t.task_description,
                "task_type": t.task_type,
                "status": t.status,
                "output": t.output,
                "score": t.score,
                "tokens_used": t.tokens_used,
                "error_message": t.error_message,
                "depends_on": t.depends_on,
                "priority": t.priority,
            }
            for t in tasks
        ],
    }
