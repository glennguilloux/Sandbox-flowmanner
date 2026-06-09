"""Backfill workspace_id on existing rows that have NULL workspace_id.

Strategy:
1. Build a map: user_id → workspace_id (from workspace_members or workspace owner_id)
2. For each table with a workspace_id column, UPDATE rows WHERE workspace_id IS NULL
3. Match by user_id where possible (missions, agents), else use the first workspace
4. Idempotent — safe to re-run (only touches NULL rows)

Usage:
    python scripts/backfill_workspace_id.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run():
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        # ── 1. Build user_id → workspace_id map ────────────────────
        # Primary: workspace.owner_id (each user owns exactly one workspace)
        owner_rows = await conn.execute(
            sa_text(
                "SELECT id, owner_id FROM workspaces WHERE is_active = true ORDER BY created_at"
            )
        )
        all_workspaces = owner_rows.fetchall()

        if not all_workspaces:
            logger.error("No workspaces found — cannot backfill")
            await engine.dispose()
            return

        # user_id → workspace_id map
        user_ws_map: dict[int, str] = {}
        for ws in all_workspaces:
            # owner_id is int — keep FIRST (oldest) workspace per user
            if ws.owner_id not in user_ws_map:
                user_ws_map[ws.owner_id] = ws.id

        # Also pull from workspace_members for completeness
        member_rows = await conn.execute(
            sa_text(
                "SELECT user_id, workspace_id FROM workspace_members WHERE is_active = true"
            )
        )
        for row in member_rows.fetchall():
            if row.user_id not in user_ws_map:
                user_ws_map[row.user_id] = row.workspace_id

        # Default workspace: the oldest (first created)
        default_ws_id = all_workspaces[0].id
        logger.info(
            "Default workspace: %s (%d user→workspace mappings built)",
            default_ws_id,
            len(user_ws_map),
        )

        # ── 2. Backfill each table ─────────────────────────────────
        # Tables with user_id column → match by user_id
        user_scoped_tables = [
            ("missions", "user_id"),
            ("agents", "owner_id"),
            ("workflows", "user_id"),
            ("chat_threads", "user_id"),
        ]

        # Tables without direct user_id → assign to default workspace
        default_tables = [
            "workflow_executions",
            "agent_templates",
            "tools_catalog",
            "capabilities_catalog",
        ]

        total_updated = 0

        # 2a. User-scoped tables
        for table, uid_col in user_scoped_tables:
            # Count NULLs first
            r = await conn.execute(
                sa_text(f"SELECT count(*) FROM {table} WHERE workspace_id IS NULL")
            )
            null_count = r.scalar()
            if null_count == 0:
                logger.info("%s: no NULLs — skipped", table)
                continue

            # Determine if uid_col is string-typed (e.g. agents.owner_id is VARCHAR)
            col_info = await conn.execute(
                sa_text(
                    """SELECT data_type FROM information_schema.columns
                           WHERE table_name = :tbl AND column_name = :col"""
                ),
                {"tbl": table, "col": uid_col},
            )
            col_type = col_info.scalar() or ""
            uid_is_string = "char" in col_type or "text" in col_type

            # Update rows where we can match user_id
            matched = 0
            for uid, ws_id in user_ws_map.items():
                match_uid = str(uid) if uid_is_string else uid
                result = await conn.execute(
                    sa_text(
                        f"""
                        UPDATE {table}
                        SET workspace_id = :ws_id
                        WHERE workspace_id IS NULL AND {uid_col} = :uid
                    """
                    ),
                    {"ws_id": ws_id, "uid": match_uid},
                )
                matched += result.rowcount

            # Remaining NULLs → default workspace
            result = await conn.execute(
                sa_text(
                    f"""
                    UPDATE {table}
                    SET workspace_id = :ws_id
                    WHERE workspace_id IS NULL
                """
                ),
                {"ws_id": default_ws_id},
            )
            fallback = result.rowcount
            total_updated += matched + fallback
            logger.info(
                "%s: %d matched by user, %d assigned to default workspace",
                table,
                matched,
                fallback,
            )

        # 2b. Default-only tables
        for table in default_tables:
            result = await conn.execute(
                sa_text(
                    f"""
                    UPDATE {table}
                    SET workspace_id = :ws_id
                    WHERE workspace_id IS NULL
                """
                ),
                {"ws_id": default_ws_id},
            )
            if result.rowcount > 0:
                total_updated += result.rowcount
                logger.info(
                    "%s: %d rows assigned to default workspace", table, result.rowcount
                )
            else:
                logger.info("%s: no NULLs — skipped", table)

    await engine.dispose()
    logger.info("Backfill complete: %d total rows updated", total_updated)


if __name__ == "__main__":
    asyncio.run(run())
