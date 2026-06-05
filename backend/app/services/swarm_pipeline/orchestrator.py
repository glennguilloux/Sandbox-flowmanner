import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.swarm import SwarmAgent
from app.models.swarm_pipeline import NexusPipeline
from app.services.swarm_pipeline.enums import PipelinePhase, PipelineStatus
from app.services.swarm_pipeline.phases.consensus import run_consensus
from app.services.swarm_pipeline.phases.debate import run_debate
from app.services.swarm_pipeline.phases.dispatch import run_dispatch
from app.services.swarm_pipeline.phases.draft import run_draft
from app.services.swarm_pipeline.phases.research import run_research
from app.services.swarm_pipeline.phases.review import run_review
from app.services.swarm_pipeline.phases.synthesis import run_synthesis
from app.services.swarm_pipeline.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

active_pipelines: set[str] = set()


async def run_pipeline(
    db: AsyncSession,
    pipeline: NexusPipeline,
    agents: list[SwarmAgent],
    user_id: str = "system",
    session_factory=None,
) -> NexusPipeline:
    if pipeline.status != PipelineStatus.PENDING.value:
        raise ValueError(f"Pipeline must be in PENDING status, got {pipeline.status}")
    if not agents:
        raise ValueError("Cannot run pipeline with no agents")

    prev_status = pipeline.status
    active_pipelines.add(pipeline.id)
    pipeline.status = PipelineStatus.RUNNING.value
    pipeline.current_phase = PipelinePhase.DISPATCH.value
    await db.commit()
    await db.refresh(pipeline)

    # Structured state transition log
    logger.info(
        "Pipeline %s state transition: %s → %s (cause: run_pipeline started)",
        pipeline.id, prev_status, PipelineStatus.RUNNING.value,
    )

    dispatch_tasks = None
    research_tasks = None
    draft_tasks = None
    debate_tasks = None
    consensus_result = None
    synthesis_task = None
    review_feedback = None
    pipeline_start_time = datetime.now(UTC)

    phases = [
        PipelinePhase.DISPATCH,
        PipelinePhase.RESEARCH,
        PipelinePhase.DRAFT,
        PipelinePhase.DEBATE,
        PipelinePhase.CONSENSUS,
        PipelinePhase.SYNTHESIS,
        PipelinePhase.REVIEW,
    ]

    while True:
        for phase in phases:
            try:
                await db.refresh(pipeline)
                if pipeline.status == PipelineStatus.CANCELLED.value:
                    logger.info("Pipeline %s cancelled, stopping", pipeline.id)
                    active_pipelines.discard(pipeline.id)
                    return pipeline

                if pipeline.status == PipelineStatus.PAUSED.value:
                    logger.info("Pipeline %s paused at phase %s, waiting", pipeline.id, phase.value)
                    while pipeline.status == PipelineStatus.PAUSED.value:
                        await asyncio.sleep(3)
                        await db.refresh(pipeline, attribute_names=["status"])
                        if pipeline.status == PipelineStatus.CANCELLED.value:
                            logger.info("Pipeline %s cancelled while paused", pipeline.id)
                            active_pipelines.discard(pipeline.id)
                            return pipeline
                    logger.info("Pipeline %s resumed at phase %s", pipeline.id, phase.value)

                pipeline.current_phase = phase.value
                await db.commit()
                # Structured phase transition log
                logger.info(
                    "Pipeline %s phase transition: → %s (cause: phase_started)",
                    pipeline.id, phase.value,
                )
                await ws_manager.send_event(pipeline.id, "phase_started", {"phase": phase.value})
                phase_start_time = datetime.now(UTC)

                match phase:
                    case PipelinePhase.DISPATCH:
                        dispatch_tasks = await run_dispatch(db, pipeline, agents, user_id)
                    case PipelinePhase.RESEARCH:
                        research_tasks = await run_research(db, pipeline, dispatch_tasks, agents, session_factory)
                    case PipelinePhase.DRAFT:
                        draft_tasks = await run_draft(db, pipeline, research_tasks, agents, session_factory)
                    case PipelinePhase.DEBATE:
                        debate_tasks = await run_debate(
                            db, pipeline, draft_tasks, agents, review_feedback, session_factory
                        )
                    case PipelinePhase.CONSENSUS:
                        consensus_result = await run_consensus(db, pipeline, debate_tasks, draft_tasks, agents)
                    case PipelinePhase.SYNTHESIS:
                        synthesis_task = await run_synthesis(
                            db, pipeline, consensus_result, draft_tasks, agents, session_factory
                        )
                    case PipelinePhase.REVIEW:
                        review_result = await run_review(db, pipeline, synthesis_task, agents, session_factory)
                        elapsed = (datetime.now(UTC) - phase_start_time).total_seconds()
                        if pipeline.phase_durations is None:
                            pipeline.phase_durations = {}
                        pipeline.phase_durations[phase.value] = elapsed
                        _append_phase_history(pipeline, phase)
                        if review_result.get("verdict") == "PASS":
                            pipeline.status = PipelineStatus.COMPLETED.value
                            pipeline.result = {"output": synthesis_task.result, "score": review_result.get("score")}
                            pipeline.completed_at = datetime.now(UTC)
                            pipeline.total_duration = (datetime.now(UTC) - pipeline_start_time).total_seconds()
                            from app.models.swarm import SwarmTask

                            task_count_result = await db.execute(
                                select(func.count()).where(SwarmTask.swarm_id == pipeline.swarm_id)
                            )
                            pipeline.task_count = task_count_result.scalar() or 0
                            error_count_result = await db.execute(
                                select(func.count()).where(
                                    SwarmTask.swarm_id == pipeline.swarm_id,
                                    SwarmTask.status == "failed",
                                )
                            )
                            pipeline.error_count = error_count_result.scalar() or 0
                            await db.commit()
                            await db.refresh(pipeline)
                            await ws_manager.send_event(
                                pipeline.id, "pipeline_completed", {"status": "completed", "result": pipeline.result}
                            )
                            active_pipelines.discard(pipeline.id)
                            return pipeline
                        pipeline.retry_count += 1
                        if pipeline.retry_count > 3:
                            pipeline.status = PipelineStatus.FAILED.value
                            pipeline.error = f"Max retries exceeded. Last feedback: {review_result.get('feedback', '')}"
                            await db.commit()
                            await db.refresh(pipeline)
                            active_pipelines.discard(pipeline.id)
                            return pipeline
                        review_feedback = review_result.get("feedback")
                        await ws_manager.send_event(
                            pipeline.id, "review_retry", {"attempt": pipeline.retry_count, "max_retries": 3}
                        )
                        phases = [
                            PipelinePhase.DEBATE,
                            PipelinePhase.CONSENSUS,
                            PipelinePhase.SYNTHESIS,
                            PipelinePhase.REVIEW,
                        ]
                        await db.commit()
                        break

                if phase != PipelinePhase.REVIEW:
                    elapsed = (datetime.now(UTC) - phase_start_time).total_seconds()
                    if pipeline.phase_durations is None:
                        pipeline.phase_durations = {}
                    pipeline.phase_durations[phase.value] = elapsed
                    _append_phase_history(pipeline, phase)
                    await ws_manager.send_event(pipeline.id, "phase_completed", {"phase": phase.value})
                    await db.commit()

            except Exception as e:
                logger.exception("Pipeline %s failed in phase %s", pipeline.id, phase.value)
                pipeline.status = PipelineStatus.FAILED.value
                pipeline.error = str(e)
                pipeline.current_phase = phase.value
                await db.commit()
                await db.refresh(pipeline)
                await ws_manager.send_event(pipeline.id, "pipeline_failed", {"phase": phase.value, "error": str(e)})
                active_pipelines.discard(pipeline.id)
                return pipeline
        else:
            break

    active_pipelines.discard(pipeline.id)
    return pipeline


def _append_phase_history(pipeline: NexusPipeline, phase: PipelinePhase) -> None:
    if pipeline.phase_history is None:
        pipeline.phase_history = []
    pipeline.phase_history.append(
        {
            "phase": phase.value,
            "completed_at": datetime.now(UTC).isoformat(),
            "status": "completed",
        }
    )


async def cancel_pipeline(db: AsyncSession, pipeline: NexusPipeline) -> NexusPipeline:
    pipeline.status = PipelineStatus.CANCELLED.value
    await db.commit()
    await db.refresh(pipeline)
    return pipeline
