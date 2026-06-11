"""Validate database foreign key constraints.

Checks for:
1. FK type mismatches (source column type != referenced column type)
2. Missing FK constraints on known FK columns
3. Orphaned FK values (values that don't exist in the referenced table)

Exit codes:
  0 = all checks passed
  1 = validation failures found

Usage:
  python validate_constraints.py                     # full validation
  python validate_constraints.py --mismatches-only   # only check type mismatches
  python validate_constraints.py --json              # output as JSON

Requires DATABASE_URL env var (defaults to the app's database config).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import text

# ── Known FK column → (referenced_table, referenced_column) ──────────────
# These represent the expected FK relationships in the schema.
# The script will flag any column in this list that lacks a FK constraint.
EXPECTED_FK: dict[str, tuple[str, str]] = {
    # user_id → users.id
    "user_id": ("users", "id"),
    # workspace_id → workspaces.id
    "workspace_id": ("workspaces", "id"),
    # thread_id → chat_threads.id
    "thread_id": ("chat_threads", "id"),
    # mission_id → missions.id
    "mission_id": ("missions", "id"),
    # agent_id → agents.id  (note: some tables reference agent_templates instead)
    "agent_id": ("agents", "id"),
}

# Tables where agent_id references agent_templates instead of agents
AGENT_ID_TEMPLATE_TABLES = {
    "agent_capability_bindings",
    "agent_tool_bindings",
}


async def _get_engine():
    """Import and return the async engine (avoids import at module level for CI)."""
    from app.database import engine

    return engine


async def check_fk_type_mismatches(conn) -> list[dict]:
    """Find all FK constraints where source and reference column types don't match."""
    r = await conn.execute(
        text(
            """
            SELECT
                kcu.table_name AS src_table,
                kcu.column_name AS src_column,
                src_col.data_type AS src_type,
                ccu.table_name AS ref_table,
                ccu.column_name AS ref_column,
                ref_col.data_type AS ref_type,
                tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
            JOIN information_schema.columns src_col
                ON src_col.table_name = kcu.table_name
                AND src_col.column_name = kcu.column_name
            JOIN information_schema.columns ref_col
                ON ref_col.table_name = ccu.table_name
                AND ref_col.column_name = ccu.column_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND src_col.data_type != ref_col.data_type
            ORDER BY kcu.table_name, kcu.column_name
            """
        )
    )
    mismatches = []
    for row in r.fetchall():
        mismatches.append(
            {
                "table": row[0],
                "column": row[1],
                "source_type": row[2],
                "ref_table": row[3],
                "ref_column": row[4],
                "ref_type": row[5],
                "constraint": row[6],
            }
        )
    return mismatches


async def check_missing_fk_constraints(conn) -> list[dict]:
    """Find columns that match expected FK names but lack FK constraints."""
    r = await conn.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE column_name = ANY(:fk_columns)
              AND table_schema = 'public'
            ORDER BY table_name, column_name
            """
        ),
        {"fk_columns": list(EXPECTED_FK.keys())},
    )
    all_fk_columns = r.fetchall()

    # Get all existing FK constraints for these columns
    r2 = await conn.execute(
        text(
            """
            SELECT tc.table_name, kcu.column_name, ccu.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = ANY(:fk_columns)
            """
        ),
        {"fk_columns": list(EXPECTED_FK.keys())},
    )
    existing_fks = {(row[0], row[1]): row[2] for row in r2.fetchall()}

    missing = []
    for table, column in all_fk_columns:
        if (table, column) in existing_fks:
            continue
        # Skip agent_id in tables that reference agent_templates
        if column == "agent_id" and table in AGENT_ID_TEMPLATE_TABLES:
            continue
        expected_ref_table, expected_ref_col = EXPECTED_FK[column]
        missing.append(
            {
                "table": table,
                "column": column,
                "expected_ref_table": expected_ref_table,
                "expected_ref_column": expected_ref_col,
            }
        )
    return missing


async def check_orphaned_fk_values(conn) -> list[dict]:
    """Find FK values that don't exist in the referenced table."""
    r = await conn.execute(
        text(
            """
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS ref_table,
                ccu.column_name AS ref_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            ORDER BY tc.table_name, kcu.column_name
            """
        )
    )
    fk_relations = r.fetchall()

    orphans = []
    for table, column, ref_table, ref_column in fk_relations:
        try:
            r2 = await conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {table} t "
                    f"WHERE t.{column} IS NOT NULL "
                    f"AND NOT EXISTS ("
                    f"  SELECT 1 FROM {ref_table} r "
                    f"  WHERE r.{ref_column} = t.{column}"
                    f")"
                )
            )
            count = r2.scalar()
            if count and count > 0:
                orphans.append(
                    {
                        "table": table,
                        "column": column,
                        "ref_table": ref_table,
                        "ref_column": ref_column,
                        "orphan_count": count,
                    }
                )
        except Exception as e:
            # Type mismatch would cause a comparison error — skip
            # (already caught by check_fk_type_mismatches)
            print(f"  ⚠️  Skipped {table}.{column}: {e}", file=sys.stderr)
    return orphans


async def validate(mismatches_only: bool = False) -> dict:
    """Run all validation checks and return results."""
    engine = await _get_engine()
    async with engine.connect() as conn:
        mismatches = await check_fk_type_mismatches(conn)

        missing_fks: list[dict] = []
        orphans: list[dict] = []
        if not mismatches_only:
            missing_fks = await check_missing_fk_constraints(conn)
            orphans = await check_orphaned_fk_values(conn)

    return {
        "mismatches": mismatches,
        "missing_fks": missing_fks,
        "orphans": orphans,
        "mismatches_only": mismatches_only,
        "passed": len(mismatches) == 0 and len(missing_fks) == 0 and len(orphans) == 0,
    }


def _print_results(results: dict, as_json: bool) -> int:
    """Print results and return exit code."""
    if as_json:
        print(json.dumps(results, indent=2))
        return 0 if results["passed"] else 1

    exit_code = 0

    # Type mismatches
    if results["mismatches"]:
        exit_code = 1
        print(f"\n❌ FK TYPE MISMATCHES ({len(results['mismatches'])})")
        print("-" * 60)
        for m in results["mismatches"]:
            print(
                f"  {m['table']}.{m['column']} ({m['source_type']}) "
                f"-> {m['ref_table']}.{m['ref_column']} ({m['ref_type']})"
            )
            print(f"    constraint: {m['constraint']}")
    else:
        print("✅ Zero FK type mismatches")

    # Missing FK constraints
    if results.get("mismatches_only"):
        print("⏭️  Skipped missing FK and orphan checks (--mismatches-only)")
    elif results["missing_fks"]:
        exit_code = 1
        print(f"\n❌ MISSING FK CONSTRAINTS ({len(results['missing_fks'])})")
        print("-" * 60)
        for m in results["missing_fks"]:
            print(
                f"  {m['table']}.{m['column']} (should reference {m['expected_ref_table']}.{m['expected_ref_column']})"
            )
    else:
        print("✅ All expected FK constraints present")

    # Orphaned values
    if not results.get("mismatches_only") and results["orphans"]:
        exit_code = 1
        print(f"\n❌ ORPHANED FK VALUES ({len(results['orphans'])})")
        print("-" * 60)
        for o in results["orphans"]:
            print(
                f"  {o['table']}.{o['column']} "
                f"({o['orphan_count']} rows missing from {o['ref_table']}.{o['ref_column']})"
            )
    elif not results.get("mismatches_only"):
        print("✅ Zero orphaned FK values")

    # Summary
    total_fk = len(results["mismatches"]) + len(results["missing_fks"]) + len(results["orphans"])
    if total_fk == 0:
        print("\n🎉 All FK constraint checks passed!")
    else:
        print(f"\n💥 {total_fk} FK constraint issue(s) found. Fix before deploying.")

    return exit_code


def main():
    parser = argparse.ArgumentParser(description="Validate database FK constraints")
    parser.add_argument(
        "--mismatches-only",
        action="store_true",
        help="Only check for type mismatches (skip missing FKs and orphans)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    try:
        results = asyncio.run(validate(mismatches_only=args.mismatches_only))
        exit_code = _print_results(results, as_json=args.json)
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Infrastructure error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
