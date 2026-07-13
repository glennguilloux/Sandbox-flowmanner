# mypy: disable-error-code=attr-defined
"""
Swarm Celery Tasks

Celery tasks for swarm operations including:
- Task execution by agents
- Consensus timeout checking
- Agent heartbeat monitoring
- Budget enforcement

This module provides background task processing for the swarm coordination system.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal, SessionLocal
from app.models.swarm import SwarmAgent, SwarmConsensusRound, SwarmProfile, SwarmTask

from .celery_app import celery_app

logger = logging.getLogger(__name__)


# --- Async DB helpers -------------------------------------------------------
# SessionLocal() aliases an ASYNC session. The legacy .query() API does NOT work
# on it directly, and objects returned from run_sync() are DETACHED (mutations on
# them + commit on the outer async session are silent no-ops — see Opus P1). The
# correct, unambiguous pattern is to do all read+mutation+commit inside ONE async
# coroutine and drive it with a single asyncio.run() from the sync Celery task.


async def _begin_task(task_id: str, agent_id: str) -> dict[str, Any]:
    """Load the task + agent (async), mark the task processing, commit, and
    return scalars the caller needs downstream. Opens its own session."""
    async with AsyncSessionLocal() as db:
        task = (await db.execute(select(SwarmTask).where(SwarmTask.id == task_id))).scalar_one_or_none()
        if not task:
            raise ValueError(f"Task {task_id} not found")
        task.status = "processing"
        agent = (
            await db.execute(select(SwarmAgent).where(SwarmAgent.agent_instance_id == agent_id))
        ).scalar_one_or_none()
        await db.commit()
        return {
            "task_type": task.task_type,
            "swarm_id": task.swarm_id,
            "agent_model": agent.assigned_model if agent else "default",
        }


async def _complete_task(task_id: str, result: dict[str, Any]) -> None:
    """Re-fetch the task by id (async), mark completed, commit. Opens its own session."""
    async with AsyncSessionLocal() as db:
        task = (await db.execute(select(SwarmTask).where(SwarmTask.id == task_id))).scalar_one_or_none()
        if task:
            task.mark_completed(result=result)
            await db.commit()


async def _fail_task(task_id: str, error: str) -> str | None:
    """Re-fetch the task by id (async), mark failed, commit. Returns the
    swarm_id (for Redis cleanup) if the task existed, else None. Opens its own session."""
    async with AsyncSessionLocal() as db:
        task = (await db.execute(select(SwarmTask).where(SwarmTask.id == task_id))).scalar_one_or_none()
        if not task:
            return None
        task.mark_failed(error=error)
        await db.commit()
        return task.swarm_id


async def _auto_resolve_consensus(redis_cache_manager) -> int:
    """Auto-reject expired consensus rounds (async), committing each. Returns
    the number of rounds resolved. Opens its own session."""
    async with AsyncSessionLocal() as db:
        pending_rounds = (
            (await db.execute(select(SwarmConsensusRound).where(SwarmConsensusRound.result == "pending")))
            .scalars()
            .all()
        )
        resolved = 0
        for consensus in pending_rounds:
            created_at = consensus.created_at
            if created_at and (datetime.now(UTC) - created_at) > timedelta(seconds=60):
                default_result = "rejected"  # both simple_majority & unanimous fail on timeout
                consensus.resolve(default_result)
                # Mirror status to Redis
                if redis_cache_manager.redis_client:
                    redis_cache_manager.redis_client.hset(
                        f"swarm:{consensus.swarm_id}:consensus:{consensus.id}",
                        mapping={
                            "status": "resolved",
                            "result": default_result,
                            "resolved_at": datetime.now(UTC).isoformat(),
                            "reason": "timeout",
                        },
                    )
                resolved += 1
                logger.info("Auto-resolved consensus %s due to timeout", consensus.id)
        await db.commit()
        return resolved


async def _mark_stale_agents_offline(redis_cache_manager) -> int:
    """Mark heartbeat-stale active agents offline (async), committing and
    mirroring status to Redis. Returns the count marked offline. Opens its own session."""
    async with AsyncSessionLocal() as db:
        active_agents = (await db.execute(select(SwarmAgent).where(SwarmAgent.status == "active"))).scalars().all()
        offline = 0
        heartbeat_threshold = timedelta(minutes=5)
        for agent in active_agents:
            last_active = agent.last_active_at
            if last_active and (datetime.now(UTC) - last_active) > heartbeat_threshold:
                agent.mark_inactive()
                offline += 1
                logger.warning(
                    "Agent %s marked offline - last heartbeat: %s",
                    agent.agent_instance_id,
                    last_active.isoformat(),
                )
                if redis_cache_manager.redis_client:
                    redis_cache_manager.redis_client.srem(
                        f"swarm:{agent.swarm_id}:agents:active",
                        agent.agent_instance_id,
                    )
                    redis_cache_manager.redis_client.hset(
                        f"swarm:{agent.swarm_id}:agent:{agent.agent_instance_id}",
                        "status",
                        "offline",
                    )
        await db.commit()
        return offline


@celery_app.task(name="swarm.execute_task", bind=True, max_retries=3)
def execute_swarm_task(self, task_id: str, agent_id: str, payload: dict[str, Any]):
    """
    Execute a swarm task using the assigned agent.

    Args:
        task_id: Task identifier
        agent_id: Assigned agent instance ID
        payload: Task payload data

    Returns:
        Task execution result
    """
    try:
        logger.info("Executing task %s with agent %s", task_id, agent_id)

        from app.services.agent_model_router import get_agent_model_router_service
        from app.services.swarm_coordinator import get_swarm_coordinator

        db = SessionLocal()

        try:
            # Begin the task on a SINGLE sync scope. Mutations + commit happen
            # INSIDE run_sync on the sync session that owns the rows (objects
            # returned from run_sync are detached, so we commit there and only
            # carry scalars back out).
            data = asyncio.run(_begin_task(task_id, agent_id))

            # Initialize services
            model_router = get_agent_model_router_service()
            coordinator = get_swarm_coordinator()

            model_name = data["agent_model"]

            # Execute task based on task_type
            task_result = _execute_task_by_type(task_type=data["task_type"], payload=payload, agent=model_name, db=db)

            # Mark completed on its own sync scope (re-fetches by id, mutates, commits)
            asyncio.run(_complete_task(task_id, task_result))

            # Track actual cost and performance
            actual_cost = task_result.get("cost", 0.01)
            tokens_in = task_result.get("tokens_in", 0)
            tokens_out = task_result.get("tokens_out", 0)
            success = task_result.get("success", True)
            latency_ms = task_result.get("latency_ms", 0)

            # Update cost tracking
            coordinator.track_swarm_cost(
                swarm_id=data["swarm_id"],
                agent_id=agent_id,
                model_name=model_name,
                cost=actual_cost,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )

            # Track model performance
            model_router.track_model_performance(
                agent_id=agent_id,
                model_name=model_name,
                success=success,
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost=actual_cost,
            )

            # Decrement agent load in Redis
            from app.cache.redis_cache import redis_cache_manager

            if redis_cache_manager.redis_client:
                redis_cache_manager.redis_client.decr(f"swarm:{data['swarm_id']}:agent:{agent_id}:active_tasks")

            logger.info("✅ Task %s completed successfully", task_id)

            return {"success": True, "task_id": task_id, "result": task_result}

        finally:
            db.close()

    except Exception as e:
        logger.error("❌ Task %s failed: %s", task_id, e)

        # Mark the task failed on its own sync scope (re-fetch by id, mutate, commit)
        try:
            db = SessionLocal()
            try:
                swarm_id = asyncio.run(_fail_task(task_id, str(e)))
                if swarm_id:
                    from app.cache.redis_cache import redis_cache_manager

                    if redis_cache_manager.redis_client:
                        redis_cache_manager.redis_client.decr(f"swarm:{swarm_id}:agent:{agent_id}:active_tasks")
            finally:
                db.close()
        except Exception as db_error:
            logger.error("Failed to update task failure status: %s", db_error)

        # Retry with exponential backoff
        if self.request.retries < 3:
            retry_in = 60 * (2**self.request.retries)
            logger.info(
                "Retrying task %s in %ss (attempt %s/3)",
                task_id,
                retry_in,
                self.request.retries + 1,
            )
            raise self.retry(exc=e, countdown=retry_in)

        return {"success": False, "task_id": task_id, "error": str(e)}


def _execute_task_by_type(task_type: str, payload: dict[str, Any], agent, db) -> dict[str, Any]:
    """
    Execute task based on its type.

    Args:
        task_type: Type of task
        payload: Task payload
        agent: Agent record
        db: Database session

    Returns:
        Task execution result
    """
    start_time = datetime.now(UTC)

    try:
        if task_type == "ingestion":
            # Document ingestion task
            return _execute_ingestion_task(payload)

        elif task_type == "query":
            # Query processing task
            return _execute_query_task(payload)

        elif task_type == "analysis":
            # Analysis task
            return _execute_analysis_task(payload)

        elif task_type == "optimization":
            # Optimization task
            return _execute_optimization_task(payload)

        else:
            # Generic task
            return {
                "success": True,
                "message": f"Executed generic task of type {task_type}",
                "payload": payload,
                "cost": 0.0,
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_ms": (datetime.now(UTC) - start_time).total_seconds() * 1000,
            }

    except Exception as e:
        logger.error("Task execution failed: %s", e)
        raise


def _execute_ingestion_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute document ingestion task."""
    start_time = datetime.now(UTC)

    # Use RAG service for ingestion
    from app.services.rag_service import get_rag_service

    rag_service = get_rag_service()
    file_ids = payload.get("file_ids", [])

    if not file_ids:
        return {
            "success": True,
            "message": "No files to ingest",
            "files_processed": 0,
            "cost": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "latency_ms": (datetime.now(UTC) - start_time).total_seconds() * 1000,
        }

    results = rag_service.add_documents(
        file_ids=file_ids,
        user_id=payload.get("user_id"),
        metadata=payload.get("metadata"),
    )

    latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

    # Estimate cost based on file count
    estimated_cost = len(file_ids) * 0.005

    return {
        "success": True,
        "files_processed": len(file_ids),
        "results": results,
        "cost": estimated_cost,
        "tokens_in": 0,
        "tokens_out": 0,
        "latency_ms": latency_ms,
    }


def _execute_query_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute query processing task."""
    start_time = datetime.now(UTC)

    # Use RAG service for query
    from app.services.rag_service import get_rag_service

    rag_service = get_rag_service()
    query = payload.get("query", "")

    if not query:
        return {
            "success": False,
            "error": "No query provided",
            "cost": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "latency_ms": 0,
        }

    result = rag_service.search(
        query=query,
        search_type=payload.get("search_type", "hybrid"),
        expansion_type=payload.get("expansion_type", "none"),
    )

    latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

    # Estimate cost based on query length
    estimated_cost = len(query) * 0.0001
    tokens_in = len(query) // 4
    tokens_out = len(result.get("answer", "")) // 4

    return {
        "success": True,
        "answer": result.get("answer", ""),
        "sources": result.get("results", []),
        "cost": estimated_cost,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
    }


def _execute_analysis_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute analysis task."""
    start_time = datetime.now(UTC)

    # Placeholder for analysis logic
    # In production, this would call appropriate analysis services

    latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

    return {
        "success": True,
        "analysis_type": payload.get("analysis_type", "general"),
        "message": "Analysis completed",
        "cost": 0.01,
        "tokens_in": 100,
        "tokens_out": 200,
        "latency_ms": latency_ms,
    }


def _execute_optimization_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute optimization task."""
    start_time = datetime.now(UTC)

    # Placeholder for optimization logic
    # In production, this would call appropriate optimization services

    latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

    return {
        "success": True,
        "optimization_type": payload.get("optimization_type", "general"),
        "message": "Optimization completed",
        "cost": 0.01,
        "tokens_in": 100,
        "tokens_out": 150,
        "latency_ms": latency_ms,
    }


@celery_app.task(name="swarm.consensus_timeout")
def check_consensus_timeouts():
    """
    Check for expired consensus rounds and auto-resolve them.
    Runs periodically via Celery beat.
    """
    try:
        logger.info("Checking for consensus timeouts")

        from app.cache.redis_cache import redis_cache_manager
        from app.database import SessionLocal
        from app.models.swarm import SwarmConsensusRound

        db = SessionLocal()

        try:
            # All reads + mutations + the commit happen INSIDE run_sync on the
            # sync session that owns the rows (objects from run_sync are detached,
            # so mutations on them via the outer async session's commit are no-ops).
            resolved_count = asyncio.run(_auto_resolve_consensus(redis_cache_manager))

            logger.info("Consensus timeout check complete: %s rounds resolved", resolved_count)

            return {"success": True, "resolved_count": resolved_count}

        finally:
            db.close()

    except Exception as e:
        logger.error("❌ Consensus timeout check failed: %s", e)
        return {"success": False, "error": str(e)}


@celery_app.task(name="swarm.agent_heartbeat_check")
def check_agent_heartbeats():
    """
    Check for agents with stale heartbeats and mark them offline.
    Runs periodically via Celery beat.
    """
    try:
        logger.info("Checking agent heartbeats")

        from app.cache.redis_cache import redis_cache_manager
        from app.database import SessionLocal
        from app.models.swarm import SwarmAgent

        db = SessionLocal()

        try:
            # All reads + mutations + the commit happen INSIDE run_sync on the
            # sync session that owns the rows (objects from run_sync are detached,
            # so mutations on them via the outer async session's commit are no-ops).
            offline_count = asyncio.run(_mark_stale_agents_offline(redis_cache_manager))

            logger.info("Heartbeat check complete: %s agents marked offline", offline_count)

            return {
                "success": True,
                "offline_count": offline_count,
                "checked_count": offline_count,
            }

        finally:
            db.close()

    except Exception as e:
        logger.error("❌ Heartbeat check failed: %s", e)
        return {"success": False, "error": str(e)}


@celery_app.task(name="swarm.cost_budget_check")
def check_swarm_budgets():
    """
    Check all active swarms against budget limits.
    Pause or downgrade swarms that have exceeded budgets.
    Runs periodically via Celery beat.
    """
    try:
        logger.info("Checking swarm budgets")

        from app.database import SessionLocal
        from app.models.swarm import SwarmProfile
        from app.services.swarm_coordinator import get_swarm_coordinator

        db = SessionLocal()
        coordinator = get_swarm_coordinator()

        try:
            # Find active swarms
            active_swarms = asyncio.run(
                db.run_sync(lambda s: s.query(SwarmProfile).filter(SwarmProfile.status == "active").all())
            )

            action_count = 0
            warning_count = 0

            for swarm in active_swarms:
                # Check budget
                budget_check = coordinator.check_swarm_budget(swarm.swarm_id)

                if not budget_check.get("budget_available", True):
                    # Budget exceeded - pause swarm
                    coordinator.pause_swarm(swarm.swarm_id)
                    action_count += 1
                    logger.warning("Swarm %s paused due to budget exceeded", swarm.swarm_id)

                elif budget_check.get("warnings", []):
                    # Budget warning
                    warning_count += 1
                    warnings = budget_check.get("warnings", [])
                    logger.warning("Swarm %s budget warnings: %s", swarm.swarm_id, warnings)

            logger.info(
                "Budget check complete: %s swarms paused, %s swarms with warnings",
                action_count,
                warning_count,
            )

            return {
                "success": True,
                "swarms_checked": len(active_swarms),
                "paused_count": action_count,
                "warning_count": warning_count,
            }

        finally:
            db.close()

    except Exception as e:
        logger.error("❌ Budget check failed: %s", e)
        return {"success": False, "error": str(e)}
