"""Graph execution analytics — aggregate data from graph_executions table."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.models.graph import GraphExecution, GraphState, GraphWorkflow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_execution_stats(db: AsyncSession, user_id: int) -> dict[str, Any]:
    """Total runs, success rate, avg duration, failed count for a user."""
    rows = await db.execute(
        select(
            func.count().label("total_runs"),
            func.count().filter(GraphExecution.status == "completed").label("success"),
            func.count().filter(GraphExecution.status == "failed").label("failed"),
            func.count().filter(GraphExecution.status == "running").label("running"),
            func.count().filter(GraphExecution.status == "paused").label("paused"),
        ).where(GraphExecution.user_id == user_id)
    )
    row = rows.one_or_none()
    if row is None:
        return {"total_runs": 0, "success": 0, "failed": 0, "running": 0, "paused": 0, "success_rate": 0.0, "avg_duration_seconds": 0.0}

    total = row.total_runs or 0
    success = row.success or 0
    success_rate = (success / total * 100) if total > 0 else 0.0

    # Average duration for completed executions
    dur_rows = await db.execute(
        select(
            func.avg(
                func.extract("epoch", GraphExecution.completed_at - GraphExecution.started_at)
            ).label("avg_duration")
        ).where(
            GraphExecution.user_id == user_id,
            GraphExecution.status == "completed",
            GraphExecution.completed_at.isnot(None),
            GraphExecution.started_at.isnot(None),
        )
    )
    avg_dur = dur_rows.scalar() or 0.0

    return {
        "total_runs": total,
        "success": success,
        "failed": row.failed or 0,
        "running": row.running or 0,
        "paused": row.paused or 0,
        "success_rate": round(success_rate, 1),
        "avg_duration_seconds": round(float(avg_dur), 2),
    }


async def get_workflow_stats(db: AsyncSession, user_id: int) -> list[dict]:
    """Top workflows by execution count with success rate."""
    rows = await db.execute(
        select(
            GraphWorkflow.id,
            GraphWorkflow.name,
            func.count().label("total_runs"),
            func.count().filter(GraphExecution.status == "completed").label("success"),
            func.count().filter(GraphExecution.status == "failed").label("failed"),
        )
        .join(GraphExecution, GraphExecution.workflow_id == GraphWorkflow.id)
        .where(GraphExecution.user_id == user_id)
        .group_by(GraphWorkflow.id, GraphWorkflow.name)
        .order_by(func.count().desc())
        .limit(10)
    )
    results = []
    for row in rows.all():
        total = row.total_runs or 0
        success = row.success or 0
        results.append({
            "workflow_id": str(row.id),
            "name": row.name,
            "total_runs": total,
            "success": success,
            "failed": row.failed or 0,
            "success_rate": round((success / total * 100) if total > 0 else 0.0, 1),
        })
    return results


async def get_recent_executions(db: AsyncSession, user_id: int, limit: int = 20) -> list[dict]:
    """Recent executions with status/timing."""
    rows = await db.execute(
        select(GraphExecution)
        .where(GraphExecution.user_id == user_id)
        .order_by(GraphExecution.created_at.desc())
        .limit(limit)
    )
    results = []
    for ex in rows.scalars().all():
        duration = None
        if ex.started_at and ex.completed_at:
            duration = (ex.completed_at - ex.started_at).total_seconds()
        results.append({
            "id": str(ex.id),
            "workflow_id": str(ex.workflow_id),
            "status": ex.status,
            "started_at": ex.started_at.isoformat() if ex.started_at else None,
            "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
            "duration_seconds": round(duration, 2) if duration else None,
            "error_message": ex.error_message,
        })
    return results


async def get_execution_detail(db: AsyncSession, execution_id: str) -> dict | None:
    """Full execution detail with node-level results."""
    rows = await db.execute(
        select(GraphExecution).where(GraphExecution.id == execution_id)
    )
    ex = rows.scalar_one_or_none()
    if ex is None:
        return None

    # Get node states
    state_rows = await db.execute(
        select(GraphState)
        .where(GraphState.execution_id == execution_id)
        .order_by(GraphState.created_at)
    )
    node_states = [
        {
            "id": str(s.id),
            "state_data": s.state_data,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in state_rows.scalars().all()
    ]

    duration = None
    if ex.started_at and ex.completed_at:
        duration = (ex.completed_at - ex.started_at).total_seconds()

    return {
        "id": str(ex.id),
        "workflow_id": str(ex.workflow_id),
        "status": ex.status,
        "input_data": ex.input_data,
        "output_data": ex.output_data,
        "error_message": ex.error_message,
        "started_at": ex.started_at.isoformat() if ex.started_at else None,
        "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
        "duration_seconds": round(duration, 2) if duration else None,
        "node_states": node_states,
    }


async def get_usage_stats(db: AsyncSession, user_id: int, period: str = "30d") -> dict:
    """Usage stats for a period."""
    days = int(period.replace("d", "")) if period.endswith("d") else 30
    since = datetime.now(UTC) - timedelta(days=days)

    rows = await db.execute(
        select(
            func.count().label("total_executions"),
            func.count().filter(GraphExecution.status == "completed").label("completed"),
            func.count().filter(GraphExecution.status == "failed").label("failed"),
        ).where(
            GraphExecution.user_id == user_id,
            GraphExecution.created_at >= since,
        )
    )
    row = rows.one_or_none()

    return {
        "period": period,
        "total_executions": row.total_executions if row else 0,
        "completed": row.completed if row else 0,
        "failed": row.failed if row else 0,
    }
