"""
Swarm Celery Tasks

Celery tasks for swarm operations including:
- Task execution by agents
- Consensus timeout checking
- Agent heartbeat monitoring
- Budget enforcement

This module provides background task processing for the swarm coordination system.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from .celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name='swarm.execute_task', bind=True, max_retries=3)
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
        logger.info(f"Executing task {task_id} with agent {agent_id}")
        
        # Import models and services
        from app.database import SessionLocal
        from app.models.swarm_models import SwarmAgent, SwarmTask
        from app.services.agent_model_router import get_agent_model_router_service
        from app.services.swarm_coordinator import get_swarm_coordinator
        
        db = SessionLocal()
        
        try:
            # Get task record
            task = db.query(SwarmTask).filter(SwarmTask.id == task_id).first()
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            # Update task status to processing
            task.status = "processing"
            db.commit()
            
            # Get agent info
            agent = db.query(SwarmAgent).filter(
                SwarmAgent.agent_instance_id == agent_id
            ).first()
            
            # Initialize services
            model_router = get_agent_model_router_service()
            coordinator = get_swarm_coordinator()
            
            # Track cost estimate
            estimated_cost = 0.01  # Base estimate
            model_name = agent.assigned_model if agent else "default"
            
            # Execute task based on task_type
            task_result = _execute_task_by_type(
                task_type=task.task_type,
                payload=payload,
                agent=agent,
                db=db
            )
            
            # Update task as completed
            task.mark_completed(result=task_result)
            db.commit()
            
            # Track actual cost and performance
            actual_cost = task_result.get("cost", estimated_cost)
            tokens_in = task_result.get("tokens_in", 0)
            tokens_out = task_result.get("tokens_out", 0)
            success = task_result.get("success", True)
            latency_ms = task_result.get("latency_ms", 0)
            
            # Update cost tracking
            coordinator.track_swarm_cost(
                swarm_id=task.swarm_id,
                agent_id=agent_id,
                model_name=model_name,
                cost=actual_cost,
                tokens_in=tokens_in,
                tokens_out=tokens_out
            )
            
            # Track model performance
            model_router.track_model_performance(
                agent_id=agent_id,
                model_name=model_name,
                success=success,
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost=actual_cost
            )
            
            # Decrement agent load in Redis
            from app.cache.redis_cache import redis_cache_manager
            if redis_cache_manager.redis_client:
                redis_cache_manager.redis_client.decr(
                    f"swarm:{task.swarm_id}:agent:{agent_id}:active_tasks"
                )
            
            logger.info(f"✅ Task {task_id} completed successfully")
            
            return {
                "success": True,
                "task_id": task_id,
                "result": task_result
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Task {task_id} failed: {e}")
        
        # Update task as failed
        try:
            from app.database import SessionLocal
            from app.models.swarm_models import SwarmTask
            
            db = SessionLocal()
            try:
                task = db.query(SwarmTask).filter(SwarmTask.id == task_id).first()
                if task:
                    task.mark_failed(error=str(e))
                    db.commit()
                    
                    # Decrement agent load
                    from app.cache.redis_cache import redis_cache_manager
                    if redis_cache_manager.redis_client:
                        redis_cache_manager.redis_client.decr(
                            f"swarm:{task.swarm_id}:agent:{agent_id}:active_tasks"
                        )
            finally:
                db.close()
        except Exception as db_error:
            logger.error(f"Failed to update task failure status: {db_error}")
        
        # Retry with exponential backoff
        if self.request.retries < 3:
            retry_in = 60 * (2 ** self.request.retries)
            logger.info(f"Retrying task {task_id} in {retry_in}s (attempt {self.request.retries + 1}/3)")
            raise self.retry(exc=e, countdown=retry_in)
        
        return {
            "success": False,
            "task_id": task_id,
            "error": str(e)
        }


def _execute_task_by_type(
    task_type: str,
    payload: dict[str, Any],
    agent,
    db
) -> dict[str, Any]:
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
                "latency_ms": (datetime.now(UTC) - start_time).total_seconds() * 1000
            }
            
    except Exception as e:
        logger.error(f"Task execution failed: {e}")
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
            "latency_ms": (datetime.now(UTC) - start_time).total_seconds() * 1000
        }
    
    results = rag_service.add_documents(
        file_ids=file_ids,
        user_id=payload.get("user_id"),
        metadata=payload.get("metadata")
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
        "latency_ms": latency_ms
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
            "latency_ms": 0
        }
    
    result = rag_service.search(
        query=query,
        search_type=payload.get("search_type", "hybrid"),
        expansion_type=payload.get("expansion_type", "none")
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
        "latency_ms": latency_ms
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
        "latency_ms": latency_ms
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
        "latency_ms": latency_ms
    }


@celery_app.task(name='swarm.consensus_timeout')
def check_consensus_timeouts():
    """
    Check for expired consensus rounds and auto-resolve them.
    Runs periodically via Celery beat.
    """
    try:
        logger.info("Checking for consensus timeouts")
        
        from app.cache.redis_cache import redis_cache_manager
        from app.database import SessionLocal
        from app.models.swarm_models import SwarmConsensusRound
        
        db = SessionLocal()
        
        try:
            # Find all pending consensus rounds
            pending_rounds = db.query(SwarmConsensusRound).filter(
                SwarmConsensusRound.result == "pending"
            ).all()
            
            resolved_count = 0
            for consensus in pending_rounds:
                # Check if timeout expired (60 seconds default)
                created_at = consensus.created_at
                if created_at and (datetime.now(UTC) - created_at) > timedelta(seconds=60):
                    # Get strategy default behavior
                    strategy = consensus.strategy_used or "simple_majority"
                    
                    # Auto-reject on timeout for simple strategies
                    default_result = "rejected"
                    if strategy == "unanimous":
                        default_result = "rejected"  # Can't achieve unanimous on timeout
                    
                    # Resolve the round
                    consensus.resolve(default_result)
                    db.commit()
                    
                    # Update Redis
                    if redis_cache_manager.redis_client:
                        redis_cache_manager.redis_client.hset(
                            f"swarm:{consensus.swarm_id}:consensus:{consensus.id}",
                            mapping={
                                "status": "resolved",
                                "result": default_result,
                                "resolved_at": datetime.now(UTC).isoformat(),
                                "reason": "timeout"
                            }
                        )
                    
                    resolved_count += 1
                    logger.info(f"Auto-resolved consensus {consensus.id} due to timeout")
            
            logger.info(f"Consensus timeout check complete: {resolved_count} rounds resolved")
            
            return {
                "success": True,
                "resolved_count": resolved_count
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Consensus timeout check failed: {e}")
        return {"success": False, "error": str(e)}


@celery_app.task(name='swarm.agent_heartbeat_check')
def check_agent_heartbeats():
    """
    Check for agents with stale heartbeats and mark them offline.
    Runs periodically via Celery beat.
    """
    try:
        logger.info("Checking agent heartbeats")
        
        from app.cache.redis_cache import redis_cache_manager
        from app.database import SessionLocal
        from app.models.swarm_models import SwarmAgent
        
        db = SessionLocal()
        
        try:
            # Find active agents
            active_agents = db.query(SwarmAgent).filter(
                SwarmAgent.status == "active"
            ).all()
            
            offline_count = 0
            heartbeat_threshold = timedelta(minutes=5)
            
            for agent in active_agents:
                last_active = agent.last_active_at
                
                # Check if heartbeat is stale
                if last_active and (datetime.now(UTC) - last_active) > heartbeat_threshold:
                    agent.mark_inactive()
                    offline_count += 1
                    
                    logger.warning(
                        f"Agent {agent.agent_instance_id} marked offline - "
                        f"last heartbeat: {last_active.isoformat()}"
                    )
                    
                    # Update Redis
                    if redis_cache_manager.redis_client:
                        redis_cache_manager.redis_client.srem(
                            f"swarm:{agent.swarm_id}:agents:active",
                            agent.agent_instance_id
                        )
                        redis_cache_manager.redis_client.hset(
                            f"swarm:{agent.swarm_id}:agent:{agent.agent_instance_id}",
                            "status", "offline"
                        )
            
            db.commit()
            
            logger.info(f"Heartbeat check complete: {offline_count} agents marked offline")
            
            return {
                "success": True,
                "offline_count": offline_count,
                "checked_count": len(active_agents)
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Heartbeat check failed: {e}")
        return {"success": False, "error": str(e)}


@celery_app.task(name='swarm.cost_budget_check')
def check_swarm_budgets():
    """
    Check all active swarms against budget limits.
    Pause or downgrade swarms that have exceeded budgets.
    Runs periodically via Celery beat.
    """
    try:
        logger.info("Checking swarm budgets")
        
        from app.database import SessionLocal
        from app.models.swarm_models import SwarmProfile
        from app.services.swarm_coordinator import get_swarm_coordinator
        
        db = SessionLocal()
        coordinator = get_swarm_coordinator()
        
        try:
            # Find active swarms
            active_swarms = db.query(SwarmProfile).filter(
                SwarmProfile.status == "active"
            ).all()
            
            action_count = 0
            warning_count = 0
            
            for swarm in active_swarms:
                # Check budget
                budget_check = coordinator.check_swarm_budget(swarm.swarm_id)
                
                if not budget_check.get("budget_available", True):
                    # Budget exceeded - pause swarm
                    coordinator.pause_swarm(swarm.swarm_id)
                    action_count += 1
                    logger.warning(f"Swarm {swarm.swarm_id} paused due to budget exceeded")
                    
                elif budget_check.get("warnings", []):
                    # Budget warning
                    warning_count += 1
                    warnings = budget_check.get("warnings", [])
                    logger.warning(f"Swarm {swarm.swarm_id} budget warnings: {warnings}")
            
            logger.info(
                f"Budget check complete: {action_count} swarms paused, "
                f"{warning_count} swarms with warnings"
            )
            
            return {
                "success": True,
                "swarms_checked": len(active_swarms),
                "paused_count": action_count,
                "warning_count": warning_count
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Budget check failed: {e}")
        return {"success": False, "error": str(e)}