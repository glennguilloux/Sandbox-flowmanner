"""One-time remediation: renumber dual-written blueprints to use Mission.id.

Before this fix, dual-write in ``commands.py::_dual_write_blueprint`` created
blueprints with a fresh ``uuid4()`` ID and stored the mission ID in
``definition['_source_mission_id']``.  This produced a 1-to-many linkage
instead of the desired 1-to-1 deterministic linkage required by the cutover
plan (Phase B stop-gate).

This script migrates those blueprints so that ``Blueprint.id == Mission.id``:

1. For every blueprint where ``id != _source_mission_id`` and
   ``_source_mission_id`` is present:
   - Insert a new blueprint row with ``id = _source_mission_id`` and the same
     fields as the old row.
   - Update ``runs.blueprint_id`` and ``blueprint_versions.blueprint_id`` to
     point to the new ID.
   - Delete the old blueprint row.
2. Standalone blueprints without ``_source_mission_id`` are left untouched.
3. The script is idempotent: re-running it after a successful migration is a
   no-op.

Usage (dry-run first):
    cd /opt/flowmanner
    docker compose exec backend python -m scripts.renumber_dual_write_blueprints --dry-run
    docker compose exec backend python -m scripts.renumber_dual_write_blueprints
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.models.blueprint_models import Blueprint, BlueprintVersion, Run

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _renumber_one(
    db: AsyncSession,
    old_bp: Blueprint,
    dry_run: bool,
) -> dict:
    """Renumber a single dual-written blueprint.

    Returns a dict describing the operation for logging.
    """
    source_mission_id = (old_bp.definition or {}).get("_source_mission_id")
    if not source_mission_id:
        return {"status": "skipped_no_source", "old_id": old_bp.id}

    new_id = str(source_mission_id)
    if old_bp.id == new_id:
        return {"status": "already_ok", "old_id": old_bp.id}

    # Check for collision: a blueprint with the deterministic ID already exists.
    existing = (
        await db.execute(select(Blueprint).where(Blueprint.id == new_id, Blueprint.deleted_at.is_(None)))
    ).scalar_one_or_none()

    if existing is not None:
        # We have both a random-ID dual-written blueprint AND a deterministic-ID
        # blueprint for the same mission. Merge by repointing child rows and
        # deleting the random-ID one.
        logger.warning(
            "Collision for mission %s: deterministic blueprint %s already exists; "
            "repointing children from %s and deleting duplicate",
            new_id,
            existing.id,
            old_bp.id,
        )
        if not dry_run:
            await db.execute(
                text("UPDATE runs SET blueprint_id = :new_id WHERE blueprint_id = :old_id"),
                {"new_id": new_id, "old_id": old_bp.id},
            )
            await db.execute(
                text("UPDATE blueprint_versions SET blueprint_id = :new_id WHERE blueprint_id = :old_id"),
                {"new_id": new_id, "old_id": old_bp.id},
            )
            await db.execute(
                text("DELETE FROM blueprints WHERE id = :old_id"),
                {"old_id": old_bp.id},
            )
            await db.commit()
        return {
            "status": "merged_collision",
            "old_id": old_bp.id,
            "new_id": new_id,
        }

    # No collision: create the deterministic-ID blueprint as a copy, repoint
    # children, then delete the old row.
    if not dry_run:
        await db.execute(
            text(
                """
                INSERT INTO blueprints (
                    id, workspace_id, user_id, title, description,
                    blueprint_type, definition, input_schema, output_schema,
                    status, version, tags, category, icon,
                    run_count, last_run_at,
                    created_at, updated_at, deleted_at, deleted_by
                )
                SELECT
                    :new_id,
                    workspace_id, user_id, title, description,
                    blueprint_type, definition, input_schema, output_schema,
                    status, version, tags, category, icon,
                    run_count, last_run_at,
                    created_at, updated_at, deleted_at, deleted_by
                FROM blueprints
                WHERE id = :old_id
                """
            ),
            {"new_id": new_id, "old_id": old_bp.id},
        )
        await db.execute(
            text("UPDATE runs SET blueprint_id = :new_id WHERE blueprint_id = :old_id"),
            {"new_id": new_id, "old_id": old_bp.id},
        )
        await db.execute(
            text("UPDATE blueprint_versions SET blueprint_id = :new_id WHERE blueprint_id = :old_id"),
            {"new_id": new_id, "old_id": old_bp.id},
        )
        await db.execute(
            text("DELETE FROM blueprints WHERE id = :old_id"),
            {"old_id": old_bp.id},
        )
        await db.commit()

    return {"status": "renumbered", "old_id": old_bp.id, "new_id": new_id}


async def _gather_candidates(db: AsyncSession) -> list[Blueprint]:
    """Return all live dual-written blueprints with id != _source_mission_id."""
    stmt = select(Blueprint).where(
        Blueprint.deleted_at.is_(None),
        Blueprint.definition.has_key("_source_mission_id"),
        Blueprint.definition["_source_mission_id"].astext.is_not(None),
        Blueprint.definition["_source_mission_id"].astext != "",
    )
    all_bps = list((await db.execute(stmt)).scalars().all())
    candidates = [bp for bp in all_bps if bp.id != bp.definition.get("_source_mission_id")]
    return candidates


async def main(dry_run: bool) -> int:
    logger.info("Starting blueprint renumbering (dry_run=%s)", dry_run)

    async with AsyncSessionLocal() as db:
        candidates = await _gather_candidates(db)
        logger.info("Found %d dual-written blueprints to renumber", len(candidates))

        results: list[dict] = []
        for bp in candidates:
            result = await _renumber_one(db, bp, dry_run=dry_run)
            results.append(result)
            logger.info("Renumbered blueprint: %s", result)

        if dry_run:
            logger.info("DRY RUN complete — no changes committed")
        else:
            logger.info("Renumbering complete")

    # Summary
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    logger.info("Summary: %s", by_status)

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Renumber dual-written blueprints to deterministic Mission.id")
    parser.add_argument("--dry-run", action="store_true", help="Log intended changes without modifying DB")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(dry_run=args.dry_run)))
