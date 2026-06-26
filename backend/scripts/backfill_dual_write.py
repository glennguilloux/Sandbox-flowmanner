"""Backfill dual-write blueprints for missions that were missed.

The dual-write in ``commands.py::_dual_write_blueprint`` creates blueprints
with fresh ``uuid4()`` IDs and stores the mission ID as
``definition['_source_mission_id']``.  This script finds missions that lack
such a linked blueprint and creates one for each.

This script is IDEMPOTENT — it skips missions that already have a blueprint
linked via ``_source_mission_id``.

Usage:
    cd /opt/flowmanner
    docker compose exec backend python -m scripts.backfill_dual_write \\
        [--batch-size 100] [--dry-run]

Options:
    --batch-size N   Process N missions per batch (default: 100).
    --dry-run        Report what would be done without writing to the DB.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from uuid import uuid4

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.blueprint_models import Blueprint, BlueprintVersion, Run
from app.models.mission_models import Mission

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _mission_status_to_run_status(mission_status: str) -> str:
    """Map MissionStatus value → Run status string.

    Keeps the mapping local to avoid coupling this standalone script to
    internal module paths (``app.api._mission_cqrs.compat``).
    """
    _MAP = {
        "running": "executing",
        "planning": "pending",
        "planned": "pending",
        "approved": "completed",
    }
    return _MAP.get(mission_status, mission_status)


async def backfill_dual_write(batch_size: int = 100, dry_run: bool = False) -> dict:
    """Create blueprints (+ optional runs) for missions without a dual-write link.

    Returns a dict with counts for reporting.
    """
    async with AsyncSessionLocal() as db:
        # 1. Fetch all blueprints that have a _source_mission_id
        bp_source_stmt = select(Blueprint.definition["_source_mission_id"].astext.label("src_id")).where(
            Blueprint.deleted_at.is_(None),
            Blueprint.definition.has_key("_source_mission_id"),
            Blueprint.definition["_source_mission_id"].astext.is_not(None),
            Blueprint.definition["_source_mission_id"].astext != "",
        )
        result = await db.execute(bp_source_stmt)
        already_linked = {row.src_id for row in result if row.src_id}

        logger.info("Missions already linked via _source_mission_id: %d", len(already_linked))

        # 2. Find orphaned missions (no blueprint via _source_mission_id)
        mission_stmt = select(Mission).where(Mission.deleted_at.is_(None)).order_by(Mission.created_at)
        all_missions = list((await db.execute(mission_stmt)).scalars().all())
        orphans = [m for m in all_missions if str(m.id) not in already_linked]

        logger.info(
            "Total missions: %d | Already linked: %d | Orphans: %d",
            len(all_missions),
            len(already_linked),
            len(orphans),
        )

        if not orphans:
            logger.info("No orphaned missions to backfill")
            return {
                "total_missions": len(all_missions),
                "already_linked": len(already_linked),
                "backfilled": 0,
                "runs_created": 0,
            }

        # 3. Process in batches
        batch = orphans[:batch_size]
        bp_count = 0
        run_count = 0

        for mission in batch:
            mission_id = str(mission.id)
            bp_id = str(uuid4())  # Fresh UUID, matching dual-write behavior
            m_status = mission.status.value if hasattr(mission.status, "value") else mission.status

            definition = {
                "_source_mission_id": mission_id,
            }

            bp_status = "published" if m_status in ("completed", "approved") else "draft"

            bp = Blueprint(
                id=bp_id,
                user_id=mission.user_id,
                title=mission.title or "",
                description=mission.description or "",
                blueprint_type=mission.mission_type or "solo",
                definition=definition,
                status=bp_status,
                version=1,
                workspace_id=mission.workspace_id,
                run_count=0,
                last_run_at=None,
            )

            if not dry_run:
                db.add(bp)

                # Create initial version snapshot (matches BlueprintService.create)
                bv = BlueprintVersion(
                    id=str(uuid4()),
                    blueprint_id=bp_id,
                    version=1,
                    snapshot={
                        "blueprint_type": bp.blueprint_type,
                        "title": bp.title,
                        "description": bp.description,
                        **definition,
                    },
                    description="Backfilled from missed dual-write",
                    created_by=mission.user_id,
                )
                db.add(bv)

            bp_count += 1

            # Create a Run if the mission has execution results
            has_execution = m_status in ("completed", "failed", "aborted")

            if has_execution:
                run_status = _mission_status_to_run_status(m_status)
                run = Run(
                    id=str(uuid4()),
                    blueprint_id=bp_id,
                    workspace_id=mission.workspace_id,
                    user_id=mission.user_id,
                    status=run_status,
                    snapshot=definition,
                    output_data=mission.results if hasattr(mission, "results") else None,
                    error_message=mission.error_message,
                    total_tokens=mission.tokens_used or 0,
                    total_cost_usd=float(mission.actual_cost)
                    if hasattr(mission, "actual_cost") and mission.actual_cost
                    else 0.0,
                    started_at=mission.started_at,
                    completed_at=mission.completed_at,
                )
                if not dry_run:
                    db.add(run)
                    bp.run_count = 1
                    bp.last_run_at = mission.completed_at or mission.started_at
                run_count += 1

            logger.info(
                "  %s blueprint for mission %s (%s) [%s]",
                "Would create" if dry_run else "Created",
                mission_id,
                (mission.title or "")[:50],
                f"status={m_status}, run={'yes' if has_execution else 'no'}",
            )

        if not dry_run:
            await db.commit()
            logger.info("Committed %d blueprints + %d runs to database", bp_count, run_count)
        else:
            logger.info("DRY RUN: would have created %d blueprints + %d runs", bp_count, run_count)

        remaining = len(orphans) - len(batch)
        if remaining > 0:
            logger.info("Remaining orphans: %d (re-run with larger --batch-size or re-run script)", remaining)

        return {
            "total_missions": len(all_missions),
            "already_linked": len(already_linked),
            "backfilled": bp_count,
            "runs_created": run_count,
            "remaining_orphans": remaining,
        }


async def main():
    dry_run = "--dry-run" in sys.argv
    batch_size = 100
    for arg in sys.argv:
        if arg.startswith("--batch-size="):
            batch_size = int(arg.split("=")[1])

    logger.info("Starting dual-write backfill (dry_run=%s, batch_size=%d)", dry_run, batch_size)
    result = await backfill_dual_write(batch_size=batch_size, dry_run=dry_run)

    logger.info(
        "Backfill complete: %d/%d missions backfilled, %d runs created, %d remaining",
        result["backfilled"],
        result["total_missions"],
        result["runs_created"],
        result["remaining_orphans"],
    )


if __name__ == "__main__":
    asyncio.run(main())
