"""Analytics service for NEXUS Pipeline."""

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.swarm import SwarmTask
from app.models.swarm_pipeline import NexusPipeline
from app.services.swarm_pipeline.enums import PipelineStatus


async def get_summary_analytics(db: AsyncSession) -> dict:
    """Aggregate stats across all pipelines."""
    total_result = await db.execute(select(func.count()).select_from(NexusPipeline))
    total_pipelines = total_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count()).where(NexusPipeline.status == PipelineStatus.COMPLETED.value)
    )
    completed_pipelines = completed_result.scalar() or 0

    failed_result = await db.execute(select(func.count()).where(NexusPipeline.status == PipelineStatus.FAILED.value))
    failed_pipelines = failed_result.scalar() or 0

    avg_duration_result = await db.execute(
        select(func.avg(NexusPipeline.total_duration)).where(NexusPipeline.total_duration.isnot(None))
    )
    avg_total_duration = avg_duration_result.scalar()

    avg_task_count_result = await db.execute(
        select(func.avg(NexusPipeline.task_count)).where(NexusPipeline.task_count.isnot(None))
    )
    avg_task_count = avg_task_count_result.scalar()

    return {
        "total_pipelines": total_pipelines,
        "completed_pipelines": completed_pipelines,
        "failed_pipelines": failed_pipelines,
        "avg_total_duration": float(avg_total_duration) if avg_total_duration is not None else None,
        "avg_task_count": float(avg_task_count) if avg_task_count is not None else None,
    }


async def get_pipeline_analytics(db: AsyncSession, pipeline_id: str) -> dict | None:
    """Per-pipeline analytics."""
    result = await db.execute(select(NexusPipeline).where(NexusPipeline.id == pipeline_id))
    pipeline = result.scalars().first()
    if not pipeline:
        return None
    return {
        "pipeline_id": pipeline.id,
        "phase_durations": pipeline.phase_durations,
        "total_duration": pipeline.total_duration,
        "task_count": pipeline.task_count,
        "error_count": pipeline.error_count,
    }


async def get_agent_analytics(db: AsyncSession) -> dict:
    """Per-agent stats from SwarmTask data."""
    result = await db.execute(
        select(
            SwarmTask.assigned_agent_id,
            func.count().label("task_count"),
            func.sum(func.cast(SwarmTask.status == "failed", type_=Integer)).label("error_count"),
        )
        .where(SwarmTask.assigned_agent_id.isnot(None))
        .group_by(SwarmTask.assigned_agent_id)
    )
    rows = result.all()
    agents = [
        {
            "agent_id": row.assigned_agent_id,
            "task_count": row.task_count,
            "error_count": row.error_count or 0,
        }
        for row in rows
    ]
    return {"agents": agents}
