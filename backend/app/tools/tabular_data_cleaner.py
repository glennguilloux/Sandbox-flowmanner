"""
Data Processing Tools — Tabular Data Cleaner.

tabular_data_cleaner → Automatically detect and clean missing or malformed data in tables.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any

from pydantic import Field

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# tabular_data_cleaner
# ---------------------------------------------------------------------------

class TabularDataCleanerInput(ToolInput):
    data: str | None = Field(
        None,
        description="CSV content as text or Base64-encoded",
    )
    url: str | None = Field(
        None,
        description="URL to fetch CSV from (optional if 'data' is provided)",
    )
    fill_missing: str = Field(
        "auto",
        description="Strategy for missing values: 'auto', 'drop', 'mean', 'median', 'mode', or a literal value",
    )
    trim_whitespace: bool = Field(
        True,
        description="Strip leading/trailing whitespace from all cells",
    )
    normalize_headers: bool = Field(
        True,
        description="Lowercase headers and replace spaces with underscores",
    )
    remove_duplicates: bool = Field(
        True,
        description="Remove duplicate rows",
    )
    detect_types: bool = Field(
        True,
        description="Attempt to detect and cast numeric/boolean/date types",
    )
    max_rows: int = Field(
        0,
        description="Maximum rows to process (0 = all)",
    )


def _clean_header(header: str) -> str:
    """Normalize header: lowercase, underscores, strip special chars."""
    cleaned = header.strip().lower()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned


def _detect_and_cast(value: str) -> Any:
    """Try to cast string to int, float, bool, or keep as string."""
    if not value or not value.strip():
        return None

    stripped = value.strip()

    # Boolean
    if stripped.lower() in ("true", "false"):
        return stripped.lower() == "true"

    # Integer
    try:
        return int(stripped)
    except ValueError:
        pass

    # Float
    try:
        return float(stripped)
    except ValueError:
        pass

    return stripped


def _fill_missing_column(
    values: list[Any],
    strategy: str,
    column_name: str,
) -> list[Any]:
    """Fill missing (None) values in a column based on strategy."""
    non_nulls = [v for v in values if v is not None]

    if strategy == "drop":
        return values  # handled at row level
    elif strategy == "auto":
        # Try mean/median for numeric, mode for strings
        numeric_vals = [v for v in non_nulls if isinstance(v, (int, float))]
        if numeric_vals and len(numeric_vals) > len(non_nulls) * 0.5:
            fill = sum(numeric_vals) / len(numeric_vals)
            return [fill if v is None else v for v in values]
        elif non_nulls:
            # Mode
            from collections import Counter
            fill = Counter(str(v) for v in non_nulls).most_common(1)[0][0]
            return [fill if v is None else v for v in values]
        return values
    elif strategy == "mean":
        numeric_vals = [v for v in non_nulls if isinstance(v, (int, float))]
        if numeric_vals:
            fill = sum(numeric_vals) / len(numeric_vals)
            return [fill if v is None else v for v in values]
        return values
    elif strategy == "median":
        numeric_vals = sorted(v for v in non_nulls if isinstance(v, (int, float)))
        if numeric_vals:
            mid = len(numeric_vals) // 2
            fill = numeric_vals[mid]
            return [fill if v is None else v for v in values]
        return values
    elif strategy == "mode":
        from collections import Counter
        if non_nulls:
            fill = Counter(str(v) for v in non_nulls).most_common(1)[0][0]
            return [fill if v is None else v for v in values]
        return values
    else:
        # Literal value
        return [strategy if v is None else v for v in values]


class TabularDataCleanerTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="tabular_data_cleaner",
            name="Tabular Data Cleaner",
            description="Automatically detect and clean missing or malformed data in tables",
            category="data-processing",
            input_schema=TabularDataCleanerInput.schema_extra(),
            tags=["csv", "data", "clean", "tabular", "data-processing"],
            requires_auth=False,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = TabularDataCleanerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            csv_bytes = await resolve_input(validated.data, validated.url, label="CSV")
        except ValueError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Failed to read CSV: {e}"
            )

        try:
            csv_str = csv_bytes.decode("utf-8")
            reader = csv.reader(io.StringIO(csv_str))
            rows = list(reader)

            if len(rows) < 1:
                return ToolResult.error_result(
                    tool_id=self.tool_id, error="CSV has no rows"
                )

            # Extract and normalize headers
            original_headers = rows[0]
            headers = [
                _clean_header(h) if validated.normalize_headers else h.strip()
                for h in original_headers
            ]
            data_rows = rows[1:]

            # Limit rows
            if validated.max_rows > 0:
                data_rows = data_rows[:validated.max_rows]

            total_rows = len(data_rows)
            stats: dict[str, Any] = {
                "total_rows": total_rows,
                "total_columns": len(headers),
                "original_headers": original_headers,
                "cleaned_headers": headers if validated.normalize_headers else headers,
                "actions": [],
            }

            # Trim whitespace
            if validated.trim_whitespace:
                data_rows = [
                    [cell.strip() if isinstance(cell, str) else cell for cell in row]
                    for row in data_rows
                ]
                stats["actions"].append("trimmed_whitespace")

            # Detect types
            if validated.detect_types:
                data_rows = [[_detect_and_cast(cell) for cell in row] for row in data_rows]
                stats["actions"].append("detected_types")

            # Count missing values before filling
            missing_before = sum(
                1 for row in data_rows for cell in row if cell is None or cell == ""
            )
            stats["missing_values_before"] = missing_before

            # Fill missing values
            if validated.fill_missing != "drop" and validated.fill_missing != "none":
                # Fill column by column
                num_cols = len(headers)
                columns: list[list[Any]] = []
                for col_idx in range(num_cols):
                    col_values = [
                        row[col_idx] if col_idx < len(row) else None
                        for row in data_rows
                    ]
                    columns.append(
                        _fill_missing_column(col_values, validated.fill_missing, headers[col_idx])
                    )

                # Transpose back to rows
                data_rows = [list(col) for col in zip(*columns, strict=False)]
                stats["actions"].append(f"filled_missing_{validated.fill_missing}")

            # Remove rows where ALL values are None (if drop strategy)
            if validated.fill_missing == "drop":
                data_rows = [
                    row for row in data_rows
                    if not all(cell is None or cell == "" for cell in row)
                ]
                stats["actions"].append("dropped_empty_rows")
                stats["rows_after_drop"] = len(data_rows)

            # Remove duplicate rows
            if validated.remove_duplicates:
                seen: set[tuple] = set()
                unique_rows = []
                for row in data_rows:
                    row_tuple = tuple(str(c) for c in row)
                    if row_tuple not in seen:
                        seen.add(row_tuple)
                        unique_rows.append(row)
                duplicates_removed = len(data_rows) - len(unique_rows)
                data_rows = unique_rows
                stats["actions"].append("removed_duplicates")
                stats["duplicates_removed"] = duplicates_removed

            # Count missing after
            missing_after = sum(
                1 for row in data_rows for cell in row if cell is None or cell == ""
            )
            stats["missing_values_after"] = missing_after
            stats["final_rows"] = len(data_rows)

            # Build output CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(data_rows)
            cleaned_csv = output.getvalue()

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "headers": headers,
                    "rows": data_rows,
                    "csv": cleaned_csv,
                    "stats": stats,
                },
            )

        except Exception as e:
            logger.exception("tabular_data_cleaner failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

register_tool(TabularDataCleanerTool())
