"""Phase 3.5 cutover — reconcile_dual_write.py (Phase C.1 deliverable).

Daily reconciliation: detect mission↔blueprint divergence → optionally fix.
Read-only by default (--dry-run). With --fix, create missing blueprints
plus their initial Run records for missions with execution results.

This script is the B4 deliverable from the cutover plan and the Phase C.1
prerequisite for production soak:

- Cutover plan §0 row B4: "Add daily reconciliation script
  ``scripts/reconcile_dual_write.py`` that re-syncs from missions→blueprints
  when divergence detected. Schedule via cron 04:00 UTC."
- Cutover plan §1 step C.1: "Land the ``reconcile_dual_write.py`` cron
  script (from fix B4).  Cron installed but DISABLED.  Manual run shows
  expected reconciliation logic on a 1k-row sample."

Usage:
    cd /opt/flowmanner
    docker compose exec backend python -m scripts.reconcile_dual_write \\
        [--dry-run] [--fix] [--limit N] [--batch-size N] [--json-only]

Safety constraints:
- --dry-run is the default.  The script must not write anything unless
  --fix is explicitly passed.
- --fix mode must NOT delete anything.  Drift on existing blueprints is
  reported but NOT auto-corrected.
- Idempotent: re-running with --fix makes zero new rows once every orphan
  has a matching blueprint via ``_source_mission_id``.
- Cron-friendly exit codes:
    0  = clean (no orphans, OR orphans fixed in --fix mode)
    1  = dry-run found divergence (signal for cron to raise alert)
    2  = error (DB connection failure, invalid --limit, …)

Increments ``dual_write_failures_total{site="reconcile"}`` for every
orphan mission, even in --dry-run mode, so Prometheus has a direct
divergence-rate signal independent of the operational counter.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import uuid4

import structlog
from sqlalchemy import func, select

# NOTE: ``from app import database`` + ``database.AsyncSessionLocal()`` form
# (NOT ``from app.database import AsyncSessionLocal``) is critical here:
# test_reconcile_dual_write.py imports this module at collection time
# (BEFORE any patch is active), so a local-bound ``AsyncSessionLocal``
# symbol would capture the original.  Attribute access at call time lets
# ``patch("app.database.AsyncSessionLocal", ...)`` propagate.  This is
# the same pattern the B4-test (test_dual_write_failure_logged_at_warning_b4.py)
# uses for ``AsyncSessionLocal`` mocking.
from app import database
from app.core.metrics import dual_write_failures_total
from app.models.blueprint_models import Blueprint, BlueprintVersion, Run
from app.models.mission_models import Mission

_log = structlog.get_logger(__name__)


# ── Pure helpers (unit-testable; no DB or network state) ────────────────────────


def find_orphan_mission_ids(missions, blueprints) -> set[str]:
    """Return the set of ``str(Mission.id)`` values that have NO matching blueprint.

    A mission is matched if EITHER (cutover plan §0 row B1 dual-write):
    - ``Blueprint.id == str(Mission.id)`` [direct id match]
    - ``Blueprint.definition.get("_source_mission_id") == str(Mission.id)``
      [canonical dual-write linkage — used by ``compat._find_blueprint``,
      ``prove_dual_write_complete.py``, ``verify_backfill_consistency.py``]

    Soft-deleted blueprints (``deleted_at IS NOT NULL``) are ignored so
    they cannot mask an orphan — the dual-write for a deleted mission
    must be replaceable.
    """
    bp_by_id: dict[str, object] = {}
    bp_by_source: dict[str, object] = {}
    for bp in blueprints:
        if bp.deleted_at is not None:
            continue
        bp_id_str = str(bp.id)
        bp_by_id[bp_id_str] = bp
        src = (bp.definition or {}).get("_source_mission_id")
        if src:
            bp_by_source[str(src)] = bp

    orphans: set[str] = set()
    for m in missions:
        m_id = str(m.id)
        if m_id in bp_by_source or m_id in bp_by_id:
            continue
        orphans.add(m_id)
    return orphans


def map_mission_status_to_run_status(mission_status: str) -> str:
    """MissionStatus.value → Run.status string.

    Mirrors ``backfill_dual_write.py::_mission_status_to_run_status`` so the
    reconcile script's Run records line up with production rows byte-for-byte.
    """
    _MAP = {
        "running": "executing",
        "planning": "pending",
        "planned": "pending",
        "approved": "completed",
    }
    return _MAP.get(mission_status, mission_status)


def should_create_run(mission_status: str) -> bool:
    """Whether to also create a Run record for the orphan mission.

    Only creates Runs for terminal-with-results statuses (completed, failed,
    aborted) — pending/planning/draft have no execution data worth linking,
    so an empty Run row would be misleading.
    """
    return mission_status in ("completed", "failed", "aborted")


def make_blueprint_from_mission(mission) -> dict:
    """Build the field dict for a Blueprint created from a Mission.

    Critical implementations choices (per cutover plan §0 row B1):
    - ``Blueprint.id == str(Mission.id)`` so re-running backfill / reconcile
      is idempotent: the next gather pass sees ``bp.id in bp_by_id``
      and the mission is no longer orphaned.
    - ``Blueprint.definition["_source_mission_id"] == str(Mission.id)`` so
      other tooling (``compat._find_blueprint``, ``prove_dual_write_complete``)
      can find the blueprint via the canonical dual-write linkage.
    """
    mission_id = str(mission.id)
    raw_status = mission.status.value if hasattr(mission.status, "value") else mission.status
    bp_status = "published" if raw_status in ("completed", "approved") else "draft"

    return {
        "id": mission_id,
        "user_id": mission.user_id,
        "title": mission.title or "",
        "description": mission.description or "",
        "blueprint_type": mission.mission_type or "solo",
        "definition": {"_source_mission_id": mission_id},
        "status": bp_status,
        "version": 1,
        "workspace_id": mission.workspace_id,
        "run_count": 0,
        "last_run_at": None,
    }


# ── Async DB operations ────────────────────────────────────────────────────────


async def _gather_stats(db, limit: int) -> dict:
    """Read-only: collect counts and the orphan mission list.

    Args:
        db: An open AsyncSession (the script wraps ``AsyncSessionLocal`` in
            ``async with`` and yields this).
        limit: Max missions to sample.

    Returns:
        Mapping with mission/blueprint counts, sampled-mission summary,
        and the set+list of orphan mission ids / Mission objects.
    """
    mission_total = (
        await db.execute(select(func.count()).select_from(Mission).where(Mission.deleted_at.is_(None)))
    ).scalar() or 0
    blueprint_total = (
        await db.execute(select(func.count()).select_from(Blueprint).where(Blueprint.deleted_at.is_(None)))
    ).scalar() or 0

    bp_with_source_stmt = (
        select(func.count())
        .select_from(Blueprint)
        .where(
            Blueprint.deleted_at.is_(None),
            Blueprint.definition.has_key("_source_mission_id"),
            Blueprint.definition["_source_mission_id"].astext.is_not(None),
            Blueprint.definition["_source_mission_id"].astext != "",
        )
    )
    bp_with_source_count = (await db.execute(bp_with_source_stmt)).scalar() or 0

    blueprint_stmt = select(Blueprint).where(Blueprint.deleted_at.is_(None))
    all_blueprints = list((await db.execute(blueprint_stmt)).scalars().all())

    mission_stmt = select(Mission).where(Mission.deleted_at.is_(None)).order_by(Mission.created_at.desc()).limit(limit)
    missions = list((await db.execute(mission_stmt)).scalars().all())

    orphan_ids = find_orphan_mission_ids(missions, all_blueprints)
    orphan_missions = [m for m in missions if str(m.id) in orphan_ids]

    sampled_count = len(missions)
    parity_percent = round(100.0 * (sampled_count - len(orphan_ids)) / sampled_count, 2) if sampled_count else 100.0

    return {
        "mission_total_live": int(mission_total),
        "blueprint_total_live": int(blueprint_total),
        "blueprints_with_source_id": int(bp_with_source_count),
        "sampled_missions": sampled_count,
        "sampled_limit": limit,
        "orphan_ids": orphan_ids,
        "orphan_missions": orphan_missions,
        "parity_percent": parity_percent,
    }


async def _reconcile_missing(db, orphan_missions, batch_size: int) -> int:
    """Create missing blueprints (+ optional Runs) for orphan missions.

    Idempotent by construction: callers gate on ``find_orphan_mission_ids``
    first, so this function is invoked only when at least one mission lacks
    a matching blueprint.  Re-running ``_amain`` after a successful --fix
    finds no orphans and skips this function entirely.

    Commits after each batch so partial progress survives a mid-batch crash.

    Returns the number of blueprints created.
    """
    if not orphan_missions:
        return 0

    created_count = 0
    total_batches = (len(orphan_missions) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        batch = orphan_missions[batch_idx * batch_size : (batch_idx + 1) * batch_size]
        batch_created = 0

        for mission in batch:
            fields = make_blueprint_from_mission(mission)
            raw_status = mission.status.value if hasattr(mission.status, "value") else mission.status

            bp = Blueprint(
                id=fields["id"],
                user_id=fields["user_id"],
                title=fields["title"],
                description=fields["description"],
                blueprint_type=fields["blueprint_type"],
                definition=fields["definition"],
                status=fields["status"],
                version=fields["version"],
                workspace_id=fields["workspace_id"],
                run_count=fields["run_count"],
                last_run_at=fields["last_run_at"],
            )
            db.add(bp)

            bv = BlueprintVersion(
                id=str(uuid4()),
                blueprint_id=fields["id"],
                version=1,
                snapshot={
                    "blueprint_type": fields["blueprint_type"],
                    "title": fields["title"],
                    "description": fields["description"],
                    **fields["definition"],
                },
                description="Reconciled by reconcile_dual_write.py",
                created_by=fields["user_id"],
            )
            db.add(bv)

            if should_create_run(raw_status):
                run_status = map_mission_status_to_run_status(raw_status)
                db.add(
                    Run(
                        id=str(uuid4()),
                        blueprint_id=fields["id"],
                        workspace_id=fields["workspace_id"],
                        user_id=fields["user_id"],
                        status=run_status,
                        snapshot=fields["definition"],
                        output_data=mission.results if hasattr(mission, "results") else None,
                        error_message=mission.error_message,
                        total_tokens=mission.tokens_used or 0,
                        total_cost_usd=float(mission.actual_cost) if getattr(mission, "actual_cost", None) else 0.0,
                        started_at=mission.started_at,
                        completed_at=mission.completed_at,
                    )
                )
                bp.run_count = 1
                bp.last_run_at = mission.completed_at or mission.started_at

            batch_created += 1
            _log.info(
                "reconcile_blueprint_created",
                mission_id=fields["id"],
                blueprint_id=fields["id"],
                blueprint_status=fields["status"],
                create_run=should_create_run(raw_status),
            )

        await db.commit()
        created_count += batch_created
        _log.info(
            "reconcile_batch_committed",
            batch_index=batch_idx + 1,
            total_batches=total_batches,
            batch_created=batch_created,
            total_created=created_count,
        )

    return created_count


# ── CLI ────────────────────────────────────────────────────────────────────────


def _format_report_text(report: dict, *, fix_created: int) -> str:
    """Build the human-readable report string.

    Mirrors the layout of ``prove_dual_write_complete.py::_emit_text`` so
    ops can grep the same field names across both tools.
    """
    mode_label = "fix" if fix_created else "dry-run"
    lines = [
        "===== Dual-Write Reconciliation Report (Phase 3.5 cutover) =====",
        f"Mode                                : {mode_label}",
        f"Missions live (deleted_at IS NULL)  : {report['mission_total_live']}",
        f"Blueprints live (deleted_at IS NULL): {report['blueprint_total_live']}",
        f"Blueprints with _source_mission_id  : {report['blueprints_with_source_id']}",
        f"Sampled (limit={report['sampled_limit']}) missions     : {report['sampled_missions']}",
        f"Orphan missions                     : {len(report['orphan_ids'])}",
        f"Parity percent                      : {report['parity_percent']}",
    ]
    if fix_created:
        lines.append(f"Blueprints created in this run     : {fix_created}")
    if report["orphan_ids"]:
        ids = sorted(report["orphan_ids"])
        shown = ", ".join(ids[:5])
        suffix = f" ... (+{len(ids) - 5} more)" if len(ids) > 5 else ""
        lines.append(f"First orphan IDs (max 5)           : {shown}{suffix}")
    lines.append("===== END =====")
    return "\n".join(lines)


async def _amain(args) -> int:
    """CLI entry point. Returns 0 / 1 / 2 (see module docstring)."""
    if args.limit <= 0:
        print(f"ERROR: --limit must be positive (got {args.limit}).", file=sys.stderr)
        return 2

    # First session: read-only gather pass.
    try:
        async with database.AsyncSessionLocal() as db:
            report = await _gather_stats(db, args.limit)
    except Exception as exc:
        print(f"ERROR: failed to read mission/blueprint stats: {exc!r}", file=sys.stderr)
        return 2

    orphan_count = len(report["orphan_ids"])

    # B4 observability: increment the divergence counter for every orphan
    # *even in dry-run*, so cron / Prometheus alerts have visibility.
    # Single atomic .inc(n) avoids N label-bindings during scripted cron runs.
    if orphan_count:
        dual_write_failures_total.labels(site="reconcile").inc(orphan_count)

    # Second session (optional): the fix pass.
    fix_created = 0
    if args.fix:
        try:
            async with database.AsyncSessionLocal() as db:
                fix_created = await _reconcile_missing(db, report["orphan_missions"], args.batch_size)
        except Exception as exc:
            print(f"ERROR: failed to write missing blueprints: {exc!r}", file=sys.stderr)
            return 2

    # Emit summary (human-readable or JSON).
    report_for_emit = {
        "mission_total_live": report["mission_total_live"],
        "blueprint_total_live": report["blueprint_total_live"],
        "blueprints_with_source_id": report["blueprints_with_source_id"],
        "sampled_missions": report["sampled_missions"],
        "sampled_limit": report["sampled_limit"],
        "orphan_mission_count": orphan_count,
        "parity_percent": report["parity_percent"],
        "blueprints_created": fix_created,
        "first_orphan_ids": sorted(report["orphan_ids"])[:5],
    }
    if args.json_only:
        print(json.dumps(report_for_emit, indent=2))
    else:
        print(_format_report_text(report, fix_created=fix_created))

    # Exit-code semantics (spec — cutover plan §3 step C.1):
    # - 0 = clean (no orphans) OR --fix successfully resolved every orphan.
    # - 1 = divergence not auto-resolved — either dry-run finding OR partial fix
    #       (cron signal in both cases: there's still drift to investigate).
    if orphan_count == 0:
        return 0
    if args.fix and fix_created == orphan_count:
        return 0
    return 1  # unfixed divergence (dry-run finding or partial fix)


def main() -> int:
    """Parse argv and dispatch to async entry point."""
    parser = argparse.ArgumentParser(
        prog="reconcile_dual_write",
        description=(
            "Detect mission↔blueprint divergence and optionally re-sync. "
            "Read-only by default; --fix performs idempotent blueprint creation."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Read-only mode (DEFAULT). Reports divergences, performs no writes.",
    )
    parser.add_argument(
        "--fix",
        dest="fix",
        action="store_true",
        default=False,
        help="Create missing blueprints (and Runs for terminal-status missions).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Max missions to scan. (default: 1000)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for --fix writes. (default: 100)",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Emit JSON-only summary (machine-readable).",
    )
    parsed = parser.parse_args()
    # Explicit precedence: --fix overrides --dry-run (cannot both be true).
    if parsed.fix:
        parsed.dry_run = False
    return asyncio.run(_amain(parsed))


if __name__ == "__main__":
    raise SystemExit(main())
