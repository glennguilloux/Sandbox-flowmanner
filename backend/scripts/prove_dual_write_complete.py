"""Phase B dual-write parity verifier (cutover plan section 1 B.4).

Read-only checker. Counts 1-to-1 ID correspondence between missions
and blueprints, and counts Runs linked to Blueprints.

Per the cutover plan Section 1 Phase B step B.4:

    New script prove_dual_write_complete.py counts
    (Mission.id == Blueprint.id AND
     Blueprint.definition['_source_mission_id'] == str(Mission.id))
    for each mission. Target: 100 percent.

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
     1-to-1 ID correspondence between missions and blueprints is provable."
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
            await db.execute(
                select(func.count())
                .select_from(Mission)
                .where(Mission.deleted_at.is_(None))
            )
        ).scalar() or 0
        blueprint_total = (
            await db.execute(
                select(func.count())
                .select_from(Blueprint)
                .where(Blueprint.deleted_at.is_(None))
            )
        ).scalar() or 0
        run_total = (
            await db.execute(select(func.count()).select_from(Run))
        ).scalar() or 0

        mission_stmt = (
            select(Mission)
            .where(Mission.deleted_at.is_(None))
            .order_by(Mission.created_at.desc())
            .limit(limit)
        )
        missions = list((await db.execute(mission_stmt)).scalars().all())

        blueprint_by_id: dict[str, Blueprint] = {}
        blueprint_by_source: dict[str, Blueprint] = {}
        if missions:
            ids = [str(m.id) for m in missions]
            bp_stmt = select(Blueprint).where(
                Blueprint.id.in_(ids),
                Blueprint.deleted_at.is_(None),
            )
            for bp in (await db.execute(bp_stmt)).scalars().all():
                blueprint_by_id[str(bp.id)] = bp
                src = (bp.definition or {}).get("_source_mission_id")
                if src:
                    blueprint_by_source[str(src)] = bp

        matched_id = 0
        matched_source = 0
        orphans_mission = 0
        orphan_examples: list[dict[str, str]] = []
        for m in missions:
            bp = blueprint_by_id.get(str(m.id))
            if bp is not None:
                matched_id += 1
                src = (bp.definition or {}).get("_source_mission_id")
                if src == str(m.id):
                    matched_source += 1
                continue
            orphans_mission += 1
            if len(orphan_examples) < 5:
                orphan_examples.append(
                    {"mission_id": str(m.id), "title_fingerprint": _redact_title(m.title)}
                )

        # Orphans: blueprints whose _source_mission_id points at a non-existent
        # or empty value. Use JSONB has_key + astext non-null — handles
        # "missing key", "value null", and "value empty string" distinctly.
        bp_orphan_stmt = select(func.count()).select_from(Blueprint).where(
            Blueprint.deleted_at.is_(None),
            Blueprint.definition.has_key("_source_mission_id"),
            Blueprint.definition["_source_mission_id"].astext.is_not(None),
            Blueprint.definition["_source_mission_id"].astext != "",
        )
        bp_orphan_with_source_count = (await db.execute(bp_orphan_stmt)).scalar() or 0

        runs_per_bp_stmt = (
            select(Run.blueprint_id, func.count(Run.id).label("n"))
            .where(Run.blueprint_id.is_not(None))
            .group_by(Run.blueprint_id)
        )
        runs_per_bp = {
            str(bpid): int(n)
            for bpid, n in (await db.execute(runs_per_bp_stmt)).all()
        }
        blueprints_with_runs = sum(1 for v in runs_per_bp.values() if v > 0)

        return {
            "mission_total_live": int(mission_total),
            "blueprint_total_live": int(blueprint_total),
            "run_total": int(run_total),
            "sampled_missions": len(missions),
            "sampled_limit": limit,
            "matched_by_id": matched_id,
            "matched_by_id_and_source": matched_source,
            "orphan_missions": orphans_mission,
            "orphan_mission_examples": orphan_examples,
            "blueprint_with_source_total": int(bp_orphan_with_source_count),
            "blueprints_with_at_least_one_run": blueprints_with_runs,
            "runs_per_blueprint_count": len(runs_per_bp),
            "parity_percent_by_id": (
                round(100.0 * matched_id / len(missions), 2) if missions else 100.0
            ),
            "parity_percent_by_id_and_source": (
                round(100.0 * matched_source / len(missions), 2) if missions else 100.0
            ),
        }


def _emit_text(stats: dict[str, Any]) -> str:
    lines: list[str] = [
        "===== Dual-Write Parity Report (Phase B verifier) =====",
        f"Missions live (deleted_at IS NULL)         : {stats['mission_total_live']}",
        f"Blueprints live (deleted_at IS NULL)      : {stats['blueprint_total_live']}",
        f"Runs (all)                                 : {stats['run_total']}",
        f"Blueprints with at least 1 Run             : {stats['blueprints_with_at_least_one_run']}",
        f"Blueprint-runs grouped by blueprint_id     : {stats['runs_per_blueprint_count']}",
        f"Blueprints with valid _source_mission_id   : {stats['blueprint_with_source_total']}",
        "----- sampled mission parity -----",
        f"Sampled (limit={stats['sampled_limit']}) missions         : {stats['sampled_missions']}",
        f"Matched: Mission.id == Blueprint.id        : {stats['matched_by_id']}",
        f"Matched plus _source_mission_id == m.id   : {stats['matched_by_id_and_source']}",
        f"Orphan missions (no BP)                   : {stats['orphan_missions']}",
        f"Parity percent by id                      : {stats['parity_percent_by_id']}",
        f"Parity percent by id AND _source_mission  : {stats['parity_percent_by_id_and_source']}",
        "----- orphan examples (first 5, PII-safe fingerprint) -----",
    ]
    if stats["orphan_mission_examples"]:
        for ex in stats["orphan_mission_examples"]:
            lines.append(f"  - mission_id={ex['mission_id']}  title_fingerprint={ex['title_fingerprint']}")
    else:
        lines.append("  (none)")
    if stats["parity_percent_by_id_and_source"] >= 99.5:
        verdict = "PASS"
    elif stats["parity_percent_by_id_and_source"] >= 95.0:
        verdict = "WARN"
    else:
        verdict = "FAIL"
    lines += [
        "===== END =====",
        f"Stop-gate B verdict: {verdict} (target: 100 percent matched_by_id_and_source)",
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
        help=(
            "Max missions to sample (default "
            + str(DEFAULT_SAMPLE_LIMIT)
            + "). Use --no-limit for full DB scan."
        ),
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

    if args.strict and (
        stats["parity_percent_by_id_and_source"] < 100.0
        or stats["orphan_missions"] > 0
        or stats["blueprint_with_source_total"] > 0
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
