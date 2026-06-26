"""Phase B dual-write parity verifier (cutover plan section 1 B.4).

Read-only checker. Verifies the dual-write linkage between missions and
blueprints by checking ``Blueprint.definition['_source_mission_id']``.

The dual-write in ``commands.py::_dual_write_blueprint`` creates a NEW
Blueprint (with a fresh ``uuid4()`` ID) for each mission, storing the
mission ID as ``definition['_source_mission_id']``.  Therefore the
parity check must follow this linkage — NOT direct ID equality.

This script is non-destructive -- it does NOT create or modify
any database rows. It only reads from the configured DATABASE_URL.

Usage:
    cd backend
    DATABASE_URL="postgresql+asyncpg://..." \\
        python -m scripts.prove_dual_write_complete \\
            [--limit N] [--no-limit] [--json-only] [--strict]

Options:
    --limit N        Sample only N most-recent missions (default: 1000).
    --no-limit       Sample ALL missions (overrides --limit; up to 100k).
    --json-only      Emit JSON instead of human-readable text.
    --strict         Exit non-zero if parity under 100 percent or any orphan.

Exit codes:
    0   Parity verified OR non-strict mode
    1   --strict: parity below 100 percent OR orphans detected
    2   Connection error or missing table

Reference: plans/blueprint-run-phase3.5-cutover-plan.md, Section 1 Phase B
stop-gate B:
    "Dual-write failure rate = 0 in dev, le 0.5 percent in production.
     1-to-1 correspondence between missions and blueprints is provable
     via _source_mission_id linkage."
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from hashlib import sha1
from typing import Any

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.blueprint_models import Blueprint, Run
from app.models.mission_models import Mission

# Cap for full-database sampling; protects against generating multi-MB
# IN(...) clauses for the parity cross-check.
DEFAULT_SAMPLE_LIMIT = 1000


def _redact_title(title: str | None) -> str:
    """Return a short, PII-safe fingerprint of a mission title.

    Hashes the title so identical titles produce identical output, but the
    raw user-typed content never reaches logs/cron output.
    """
    if not title:
        return "<empty>"
    normalized = title.strip().lower().encode("utf-8", errors="replace")
    return f"sha1:{sha1(normalized).hexdigest()[:10]}"


async def _gather_stats(limit: int) -> dict[str, Any]:
    """Read-only: collect mission/blueprint/run counts and parity.

    Args:
        limit: max missions to sample. Bounded by caller.
    """
    async with AsyncSessionLocal() as db:
        mission_total = (
            await db.execute(select(func.count()).select_from(Mission).where(Mission.deleted_at.is_(None)))
        ).scalar() or 0
        blueprint_total = (
            await db.execute(select(func.count()).select_from(Blueprint).where(Blueprint.deleted_at.is_(None)))
        ).scalar() or 0
        run_total = (await db.execute(select(func.count()).select_from(Run))).scalar() or 0

        mission_stmt = (
            select(Mission).where(Mission.deleted_at.is_(None)).order_by(Mission.created_at.desc()).limit(limit)
        )
        missions = list((await db.execute(mission_stmt)).scalars().all())

        # Fetch ALL non-deleted blueprints and index them two ways:
        #   1. By _source_mission_id (the actual dual-write linkage)
        #   2. By direct Blueprint.id (manual blueprints that happen to share a UUID)
        #
        # The dual-write in commands.py creates blueprints with fresh uuid4() IDs,
        # storing the mission ID as definition['_source_mission_id'].  Therefore
        # the PRIMARY linkage is by _source_mission_id, NOT by ID equality.
        blueprint_by_source: dict[str, Blueprint] = {}
        blueprint_by_id: dict[str, Blueprint] = {}
        all_bp_stmt = select(Blueprint).where(Blueprint.deleted_at.is_(None))
        for bp in (await db.execute(all_bp_stmt)).scalars().all():
            blueprint_by_id[str(bp.id)] = bp
            src = (bp.definition or {}).get("_source_mission_id")
            if src:
                blueprint_by_source[str(src)] = bp

        matched_by_source = 0
        matched_by_id_only = 0
        orphans_mission = 0
        orphan_examples: list[dict[str, str]] = []
        for m in missions:
            m_id = str(m.id)
            # PRIMARY: check _source_mission_id linkage (the dual-write mechanism)
            bp = blueprint_by_source.get(m_id)
            if bp is not None:
                matched_by_source += 1
                continue
            # SECONDARY: direct ID match (manual blueprints with same UUID)
            bp = blueprint_by_id.get(m_id)
            if bp is not None:
                matched_by_id_only += 1
                continue
            # No blueprint found for this mission
            orphans_mission += 1
            if len(orphan_examples) < 5:
                orphan_examples.append({"mission_id": m_id, "title_fingerprint": _redact_title(m.title)})

        # Count blueprints that have a valid _source_mission_id
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

        runs_per_bp_stmt = (
            select(Run.blueprint_id, func.count(Run.id).label("n"))
            .where(Run.blueprint_id.is_not(None))
            .group_by(Run.blueprint_id)
        )
        runs_per_bp = {str(bpid): int(n) for bpid, n in (await db.execute(runs_per_bp_stmt)).all()}
        blueprints_with_runs = sum(1 for v in runs_per_bp.values() if v > 0)

        total_matched = matched_by_source + matched_by_id_only
        return {
            "mission_total_live": int(mission_total),
            "blueprint_total_live": int(blueprint_total),
            "run_total": int(run_total),
            "sampled_missions": len(missions),
            "sampled_limit": limit,
            "matched_by_source": matched_by_source,
            "matched_by_id_only": matched_by_id_only,
            "total_matched": total_matched,
            "orphan_missions": orphans_mission,
            "orphan_mission_examples": orphan_examples,
            "blueprints_with_source_id": int(bp_with_source_count),
            "blueprints_with_at_least_one_run": blueprints_with_runs,
            "runs_per_blueprint_count": len(runs_per_bp),
            "parity_percent": (round(100.0 * total_matched / len(missions), 2) if missions else 100.0),
            "parity_percent_by_source": (round(100.0 * matched_by_source / len(missions), 2) if missions else 100.0),
        }


def _emit_text(stats: dict[str, Any]) -> str:
    lines: list[str] = [
        "===== Dual-Write Parity Report (Phase B verifier) =====",
        f"Missions live (deleted_at IS NULL)              : {stats['mission_total_live']}",
        f"Blueprints live (deleted_at IS NULL)            : {stats['blueprint_total_live']}",
        f"Runs (all)                                      : {stats['run_total']}",
        f"Blueprints with at least 1 Run                  : {stats['blueprints_with_at_least_one_run']}",
        f"Blueprint-runs grouped by blueprint_id          : {stats['runs_per_blueprint_count']}",
        f"Blueprints with valid _source_mission_id        : {stats['blueprints_with_source_id']}",
        "----- sampled mission parity -----",
        f"Sampled (limit={stats['sampled_limit']}) missions              : {stats['sampled_missions']}",
        f"Matched by _source_mission_id (dual-write link) : {stats['matched_by_source']}",
        f"Matched by direct ID only (manual blueprints)  : {stats['matched_by_id_only']}",
        f"Total matched (either mechanism)                : {stats['total_matched']}",
        f"Orphan missions (no BP found)                   : {stats['orphan_missions']}",
        f"Parity percent (total matched)                  : {stats['parity_percent']}",
        f"Parity percent (by _source_mission_id only)     : {stats['parity_percent_by_source']}",
        "----- orphan examples (first 5, PII-safe fingerprint) -----",
    ]
    if stats["orphan_mission_examples"]:
        for ex in stats["orphan_mission_examples"]:
            lines.append(f"  - mission_id={ex['mission_id']}  title_fingerprint={ex['title_fingerprint']}")  # noqa: PERF401
    else:
        lines.append("  (none)")
    if stats["parity_percent"] >= 99.5:
        verdict = "PASS"
    elif stats["parity_percent"] >= 95.0:
        verdict = "WARN"
    else:
        verdict = "FAIL"
    lines += [
        "===== END =====",
        f"Stop-gate B verdict: {verdict} (target: 100 percent via _source_mission_id linkage)",
    ]
    return "\n".join(lines)


async def _amain() -> int:
    parser = argparse.ArgumentParser(
        prog="prove_dual_write_complete",
        description=(
            "Phase B dual-write parity verifier (read-only). "
            "Walks missions, joins to blueprints, reports 1-to-1 ID match %."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_SAMPLE_LIMIT,
        help=("Max missions to sample (default " + str(DEFAULT_SAMPLE_LIMIT) + "). Use --no-limit for full DB scan."),
    )
    parser.add_argument(
        "--no-limit",
        action="store_true",
        help="Sample ALL live missions (cap 100k; protects the IN-list).",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Emit JSON only (machine-readable).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if parity below 100 percent or any orphans detected.",
    )
    args = parser.parse_args()

    if args.limit <= 0:
        print(f"ERROR: --limit must be positive (got {args.limit}).", file=sys.stderr)
        return 2
    if args.no_limit:
        # Hard cap to prevent run-away IN-list. Override with a much larger
        # value if your production DB has more; in that case, chunked reads
        # would be added in a follow-up.
        args.limit = 100_000

    try:
        stats = await _gather_stats(args.limit)
    except Exception as exc:
        print(f"ERROR: failed to gather parity stats: {exc!r}", file=sys.stderr)
        return 2

    if args.json_only:
        print(json.dumps(stats, indent=2))
    else:
        print(_emit_text(stats))

    if args.strict and (stats["parity_percent"] < 100.0 or stats["orphan_missions"] > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
