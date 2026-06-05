"""
Database Querying & Storage Tools — PostgreSQL Client.

postgresql_client → Execute SQL queries and retrieve results from Postgres databases.
"""

from __future__ import annotations

import logging
import os

from pydantic import Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class PostgresqlClientInput(ToolInput):
    query: str = Field(..., description="SQL query to execute (SELECT, INSERT, UPDATE, DELETE)")
    connection_string: str | None = Field(
        None,
        description="PostgreSQL connection string (uses DATABASE_URL env var if omitted)",
    )
    params: dict | None = Field(
        None,
        description="Query parameters for parameterized queries",
    )
    max_rows: int = Field(100, ge=1, le=10000, description="Maximum rows to return")


class PostgresqlClientTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="postgresql_client",
            name="PostgreSQL Client",
            description="Execute SQL queries and retrieve results from Postgres databases",
            category="database",
            input_schema=PostgresqlClientInput.schema_extra(),
            tags=["postgresql", "sql", "database", "query"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = PostgresqlClientInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        query = validated.query.strip()
        if not query:
            return ToolResult.error_result(tool_id=self.tool_id, error="Query is empty")

        conn_str = validated.connection_string or os.getenv("DATABASE_URL", "")
        if not conn_str:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="No connection string provided. Set DATABASE_URL env var or pass connection_string.",
            )

        # Ensure async driver
        if conn_str.startswith("postgresql://") or not conn_str.startswith("postgresql+asyncpg"):
            conn_str = conn_str.replace("postgresql://", "postgresql+asyncpg://", 1)

        try:
            engine = create_async_engine(conn_str, echo=False)

            async with engine.connect() as conn:
                result = await conn.execute(
                    text(query),
                    validated.params or {},
                )

                is_select = query.strip().upper().startswith(("SELECT", "WITH", "SHOW", "EXPLAIN"))

                if is_select:
                    rows = result.fetchmany(validated.max_rows)
                    columns = list(result.keys())
                    data = [dict(zip(columns, row, strict=False)) for row in rows]
                    row_count = len(data)
                    await conn.commit()
                else:
                    await conn.commit()
                    row_count = result.rowcount if hasattr(result, "rowcount") else 0
                    data = None

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "query": query[:500],
                        "is_select": is_select,
                        "row_count": row_count,
                        "rows": data,
                        "columns": columns if is_select else [],
                        "truncated": row_count >= validated.max_rows if is_select else False,
                    },
                )

        except Exception as e:
            logger.exception("postgresql_client failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


register_tool(PostgresqlClientTool())
