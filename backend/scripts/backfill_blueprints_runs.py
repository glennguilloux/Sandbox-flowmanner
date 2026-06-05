"""Backfill script — populate blueprints + runs from existing missions/workflows.

Run AFTER dual-write is deployed and verified working.
This creates Blueprint + Run records for historical data.

Usage:
    cd /opt/flowmanner
    docker compose exec backend python -m scripts.backfill_blueprints_runs [--batch-size 100] [--dry-run]
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.mission_models import Mission, MissionTask
from app.models.graph import Workflow as GraphWorkflow, WorkflowExecution
from app.models.swarm_models import OrchestratorExecution
from app.models.blueprint_models import Blueprint, Run, BlueprintVersion

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def backfill_blueprints(db: AsyncSession, batch_size: int = 100, dry_run: bool = False) -> int:
    """Create blueprints from existing missions."""
    # Find missions that don't have a corresponding blueprint yet
    existing_bp_ids = select(Blueprint.id)
    stmt = (
        select(Mission)
        .where(Mission.deleted_at.is_(None))
        .where(Mission.id.not_in(existing_bp_ids))
        .order_by(Mission.created_at)
        .limit(batch_size)
    )
    result = await db.execute(stmt)
    missions = list(result.scalars().all())

    if not missions:
        logger.info("No missions to backfill")
        return 0

    logger.info("Backfilling %d missions → blueprints", len(missions))

    for mission in missions:
        # Fetch tasks for this mission
        tasks_result = await db.execute(
            select(MissionTask).where(MissionTask.mission_id == str(mission.id))
        )
        tasks = list(tasks_result.scalars().all())

        # Build definition from mission plan + tasks
        nodes = []
        for task in tasks:
            nodes.append({
                "id": str(task.id),
                "type": task.task_type or "llm_call",
                "title": task.title or "",
                "description": task.description or "",
                "config": task.input_data or {},
                "dependencies": task.dependencies if isinstance(task.dependencies, list) else [],
                "assigned_model": task.assigned_model,
                "assigned_agent_id": str(task.assigned_agent_id) if task.assigned_agent_id else None,
                "max_retries": task.max_retries or 3,
                "fallback_strategy": "human_escalate",
            })

        definition = {
            "blueprint_type": mission.mission_type or "solo",
            "nodes": nodes,
            "edges": [],
            "budget": {"max_cost_usd": 10.0, "max_wall_time_seconds": 300, "max_iterations": 100, "max_depth": 5},
            "config": {"source_mission_id": str(mission.id)},
        }

        bp = Blueprint(
            id=str(uuid4()),
            user_id=mission.user_id,
            title=mission.title,
            description=mission.description or "",
            blueprint_type=mission.mission_type or "solo",
            definition=definition,
            status="published" if mission.status in ("completed", "approved") else "draft",
            version=1,
            workspace_id=mission.workspace_id,
            run_count=1 if mission.status in ("completed", "failed", "aborted") else 0,
            last_run_at=mission.completed_at or mission.started_at,
        )

        if not dry_run:
            db.add(bp)
            # Create initial version
            bv = BlueprintVersion(
                id=str(uuid4()),
                blueprint_id=str(bp.id),
                version=1,
                snapshot={
                    "blueprint_type": bp.blueprint_type,
                    "title": bp.title,
                    "description": bp.description,
                    **definition,
                },
                description="Backfilled from mission",
                created_by=mission.user_id,
            )
            db.add(bv)

    if not dry_run:
        await db.commit()

    logger.info("Backfilled %d blueprints (dry_run=%s)", len(missions), dry_run)
    return len(missions)


async def backfill_runs(db: AsyncSession, batch_size: int = 100, dry_run: bool = False) -> int:
    """Create runs from existing workflow executions and orchestrator executions."""
    count = 0

    # Backfill from workflow_executions
    stmt = (
        select(WorkflowExecution)
        .order_by(WorkflowExecution.created_at)
        .limit(batch_size)
    )
    result = await db.execute(stmt)
    executions = list(result.scalars().all())

    for ex in executions:
        run = Run(
            id=str(uuid4()),
            blueprint_id=None,  # No direct blueprint link for old executions
            workspace_id=ex.workspace_id,
            user_id=ex.user_id,
            status=ex.status or "completed",
            snapshot={"blueprint_type": "graph", "title": "Backfilled workflow execution"},
            output_data=ex.output_data,
            error_message=ex.error_message,
            started_at=ex.started_at,
            completed_at=ex.completed_at,
        )
        if not dry_run:
            db.add(run)
        count += 1

    # Backfill from orchestrator_executions
    stmt = (
        select(OrchestratorExecution)
        .order_by(OrchestratorExecution.created_at)
        .limit(batch_size)
    )
    result = await db.execute(stmt)
    orch_execs = list(result.scalars().all())

    for ox in orch_execs:
        run = Run(
            id=str(uuid4()),
            blueprint_id=None,
            workspace_id=None,
            user_id=None,
            status=getattr(ox, "status", "completed") or "completed",
            snapshot={"blueprint_type": "swarm", "title": "Backfilled orchestrator execution"},
            started_at=getattr(ox, "started_at", None),
            completed_at=getattr(ox, "completed_at", None),
        )
        if not dry_run:
            db.add(run)
        count += 1

    if not dry_run:
        await db.commit()

    logger.info("Backfilled %d runs (dry_run=%s)", count, dry_run)
    return count


async def main():
    dry_run = "--dry-run" in sys.argv
    batch_size = 100
    for arg in sys.argv:
        if arg.startswith("--batch-size="):
            batch_size = int(arg.split("=")[1])

    logger.info("Starting backfill (dry_run=%s, batch_size=%d)", dry_run, batch_size)

    async with AsyncSessionLocal() as db:
        bp_count = await backfill_blueprints(db, batch_size=batch_size, dry_run=dry_run)
        run_count = await backfill_runs(db, batch_size=batch_size, dry_run=dry_run)

    logger.info("Backfill complete: %d blueprints, %d runs", bp_count, run_count)


if __name__ == "__main__":
    asyncio.run(main())
