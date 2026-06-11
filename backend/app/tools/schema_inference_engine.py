"""
Database Querying & Storage Tools — Schema Inference Engine.

schema_inference_engine → Automatically infer database schemas to help LLMs write better SQL.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import Field
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class SchemaInferenceEngineInput(ToolInput):
    connection_string: str | None = Field(
        None,
        description="Database connection string (uses DATABASE_URL env var if omitted)",
    )
    schema_name: str | None = Field(
        None,
        description="Database schema to inspect (default: 'public' for Postgres)",
    )
    include_sample_data: bool = Field(
        True,
        description="Include a sample row from each table",
    )
    format: str = Field(
        "markdown",
        description="Output format: 'markdown', 'json', or 'ddl'",
    )


class SchemaInferenceEngineTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="schema_inference_engine",
            name="Schema Inference Engine",
            description="Automatically infer database schemas to help LLMs write better SQL",
            category="database",
            input_schema=SchemaInferenceEngineInput.schema_extra(),
            tags=["schema", "database", "sql", "infer", "sqlalchemy"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SchemaInferenceEngineInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        conn_str = validated.connection_string or os.getenv("DATABASE_URL", "")
        if not conn_str:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="No connection string. Set DATABASE_URL env var or pass connection_string.",
            )

        # Ensure async driver
        if conn_str.startswith("postgresql://"):
            conn_str = conn_str.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif not any(conn_str.startswith(p) for p in ("postgresql+", "mysql+", "sqlite+")):
            conn_str = conn_str.replace("://", "+asyncpg://", 1) if "://" in conn_str else conn_str

        try:
            engine = create_async_engine(conn_str, echo=False)

            async with engine.connect() as conn:
                inspector = inspect(engine)

                schema_name = validated.schema_name or "public"
                tables = []

                for table_name in await conn.run_sync(lambda sync_conn: inspector.get_table_names(schema=schema_name)):
                    columns_info = await conn.run_sync(
                        lambda sync_conn: inspector.get_columns(table_name, schema=schema_name)
                    )
                    pk_info = await conn.run_sync(
                        lambda sync_conn: inspector.get_pk_constraint(table_name, schema=schema_name)
                    )
                    fk_info = await conn.run_sync(
                        lambda sync_conn: inspector.get_foreign_keys(table_name, schema=schema_name)
                    )
                    indexes_info = await conn.run_sync(
                        lambda sync_conn: inspector.get_indexes(table_name, schema=schema_name)
                    )

                    primary_keys = pk_info.get("constrained_columns", [])
                    columns = []

                    for col in columns_info:
                        col_data: dict[str, Any] = {
                            "name": col["name"],
                            "type": str(col["type"]),
                            "nullable": col.get("nullable", True),
                            "default": (str(col.get("default")) if col.get("default") is not None else None),
                            "is_primary_key": col["name"] in primary_keys,
                        }
                        # Check if it's a foreign key
                        for fk in fk_info:
                            if col["name"] in fk.get("constrained_columns", []):
                                col_data["foreign_key"] = {
                                    "table": fk.get("referred_table", ""),
                                    "column": (
                                        fk.get("referred_columns", [""])[0] if fk.get("referred_columns") else ""
                                    ),
                                }
                        columns.append(col_data)

                    # Sample data
                    sample_row = None
                    if validated.include_sample_data:
                        try:
                            result = await conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT 1'))
                            row = result.fetchone()
                            if row:
                                sample_row = dict(zip(result.keys(), row, strict=False))
                                # Convert non-serializable types
                                for k, v in sample_row.items():
                                    if hasattr(v, "isoformat"):
                                        sample_row[k] = v.isoformat()
                                    elif not isinstance(v, (str, int, float, bool, type(None))):
                                        sample_row[k] = str(v)
                        except Exception:
                            sample_row = None

                    tables.append(
                        {
                            "name": table_name,
                            "columns": columns,
                            "primary_keys": primary_keys,
                            "foreign_keys": [
                                {
                                    "columns": fk.get("constrained_columns", []),
                                    "references": f"{fk.get('referred_table', '')}.{fk.get('referred_columns', [''])[0] if fk.get('referred_columns') else ''}",
                                }
                                for fk in fk_info
                            ],
                            "indexes": [
                                {
                                    "name": idx["name"],
                                    "columns": idx.get("column_names", []),
                                }
                                for idx in indexes_info
                            ],
                            "row_count_estimate": None,
                            "sample_row": sample_row,
                        }
                    )

                # Format output
                fmt = validated.format.lower()
                if fmt == "markdown":
                    schema_text = self._format_markdown(tables, schema_name)
                elif fmt == "ddl":
                    schema_text = self._format_ddl(tables)
                else:
                    schema_text = None

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "database_type": conn_str.split("://")[0].split("+")[-1],
                        "schema": schema_name,
                        "table_count": len(tables),
                        "tables": tables,
                        "formatted": schema_text,
                    },
                )

        except Exception as e:
            logger.exception("schema_inference_engine failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    def _format_markdown(self, tables: list[dict], schema: str) -> str:
        """Format schema as Markdown."""
        lines = [f"# Database Schema: {schema}", f"\n**{len(tables)} tables**\n"]

        for table in tables:
            lines.append(f"## `{table['name']}`")
            lines.append("")
            lines.append("| Column | Type | Nullable | Key | Default |")
            lines.append("|--------|------|----------|-----|---------|")

            for col in table["columns"]:
                key = ""
                if col.get("is_primary_key"):
                    key = "PK"
                if col.get("foreign_key"):
                    fk = col["foreign_key"]
                    key = f"FK → `{fk['table']}.{fk['column']}`"

                lines.append(
                    f"| `{col['name']}` | {col['type']} | "
                    f"{'YES' if col['nullable'] else 'NO'} | "
                    f"{key} | {col.get('default', '') or ''} |"
                )

            if table.get("indexes"):
                lines.append("")
                lines.append(
                    "**Indexes:** "
                    + ", ".join(f"`{idx['name']}` ({', '.join(idx['columns'])})" for idx in table["indexes"])
                )

            lines.append("")

        return "\n".join(lines)

    def _format_ddl(self, tables: list[dict]) -> str:
        """Generate approximate DDL statements."""
        lines = []
        for table in tables:
            cols = []
            for col in table["columns"]:
                nullable = "" if col["nullable"] else " NOT NULL"
                default = f" DEFAULT {col['default']}" if col.get("default") else ""
                pk = " PRIMARY KEY" if col.get("is_primary_key") else ""
                cols.append(f"  {col['name']} {col['type']}{nullable}{default}{pk}")

            for fk in table.get("foreign_keys", []):
                for _i, col_name in enumerate(fk.get("columns", [])):
                    ref = fk["references"].replace(".", "(") + ")"
                    cols.append(f"  FOREIGN KEY ({col_name}) REFERENCES {ref}")

            lines.append(f"CREATE TABLE {table['name']} (\n" + ",\n".join(cols) + "\n);\n")

        return "\n".join(lines)


register_tool(SchemaInferenceEngineTool())
