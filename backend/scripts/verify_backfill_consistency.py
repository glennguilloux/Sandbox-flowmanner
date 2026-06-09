"""Consistency verification script — validate backfill correctness.

Run after backfill to ensure data integrity between old and new tables.

Usage:
    cd /opt/flowmanner
    docker compose exec backend python -m scripts.verify_backfill_consistency
"""

from __future__ import annotations

import asyncio
import logging
import random

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.blueprint_models import Blueprint, Run
from app.models.graph import Workflow as GraphWorkflow
from app.models.graph import WorkflowExecution
from app.models.mission_models import Mission
from app.models.swarm_models import OrchestratorExecution

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def verify_counts(db: AsyncSession) -> list[str]:
    """Verify blueprint and run counts match expectations."""
    issues = []

    # Count missions (non-deleted)
    mission_count = (
        await db.execute(
            select(func.count())
            .select_from(Mission)
            .where(Mission.deleted_at.is_(None))
        )
    ).scalar() or 0

    # Count blueprints
    bp_count = (
        await db.execute(
            select(func.count())
            .select_from(Blueprint)
            .where(Blueprint.deleted_at.is_(None))
        )
    ).scalar() or 0

    logger.info("Missions: %d, Blueprints: %d", mission_count, bp_count)
    if bp_count < mission_count:
        issues.append(
            f"Blueprint count ({bp_count}) < Mission count ({mission_count}) — some missions may not have been backfilled"
        )

    # Count workflow executions
    wf_exec_count = (
        await db.execute(select(func.count()).select_from(WorkflowExecution))
    ).scalar() or 0

    # Count orchestrator executions
    orch_count = (
        await db.execute(select(func.count()).select_from(OrchestratorExecution))
    ).scalar() or 0

    # Count runs
    run_count = (await db.execute(select(func.count()).select_from(Run))).scalar() or 0

    expected_runs = wf_exec_count + orch_count
    logger.info(
        "Workflow executions: %d, Orchestrator executions: %d, Runs: %d",
        wf_exec_count,
        orch_count,
        run_count,
    )
    if run_count < expected_runs:
        issues.append(
            f"Run count ({run_count}) < expected ({expected_runs}) — some executions may not have been backfilled"
        )

    return issues


async def verify_sample_integrity(
    db: AsyncSession, sample_size: int = 100
) -> list[str]:
    """Sample random missions and verify corresponding blueprint data."""
    issues = []

    # Get random mission IDs
    mission_ids = (
        (
            await db.execute(
                select(Mission.id)
                .where(Mission.deleted_at.is_(None))
                .order_by(func.random())
                .limit(sample_size)
            )
        )
        .scalars()
        .all()
    )

    for mission_id in mission_ids:
        mission = (
            await db.execute(select(Mission).where(Mission.id == mission_id))
        ).scalar_one_or_none()

        if mission is None:
            continue

        # Check if blueprint exists for this mission
        bp = (
            await db.execute(
                select(Blueprint).where(
                    Blueprint.deleted_at.is_(None),
                    Blueprint.user_id == mission.user_id,
                    Blueprint.title == mission.title,
                )
            )
        ).scalar_one_or_none()

        if bp is None:
            issues.append(f"Mission {mission_id} has no corresponding blueprint")
            continue

        # Verify basic data match
        if bp.title != mission.title:
            issues.append(
                f"Mission {mission_id} title mismatch: '{mission.title}' vs '{bp.title}'"
            )
        if bp.user_id != mission.user_id:
            issues.append(f"Mission {mission_id} user_id mismatch")

    return issues


async def main():
    logger.info("Starting backfill consistency verification")

    issues = []

    async with AsyncSessionLocal() as db:
        count_issues = await verify_counts(db)
        issues.extend(count_issues)

        sample_issues = await verify_sample_integrity(db)
        issues.extend(sample_issues)

    if issues:
        logger.warning("=== ISSUES FOUND (%d) ===", len(issues))
        for issue in issues:
            logger.warning("  - %s", issue)
    else:
        logger.info("=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
