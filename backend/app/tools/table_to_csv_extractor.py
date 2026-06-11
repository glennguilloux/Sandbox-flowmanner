"""
Browser-based Data Extraction Tools — Table to CSV Extractor.

table_to_csv_extractor → Extract HTML tables from web pages and convert
    them to structured CSV, JSON, Markdown, or Pandas JSON format with
    column header detection, row/column spanning support, and multiple
    table selection strategies.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any, Literal

from bs4 import BeautifulSoup
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class TableToCsvExtractorInput(ToolInput):
    """Input schema: html, table_index, selector, include_headers, delimiter."""

    html: str = Field(
        ...,
        min_length=1,
        description="Raw HTML content containing tables to extract",
    )
    table_index: int | None = Field(
        None,
        ge=0,
        description="Index of the table to extract (0-based). None extracts all tables.",
    )
    selector: str | None = Field(
        None,
        description="CSS selector to target a specific table (e.g., 'table.data-table')",
    )
    include_headers: bool = Field(
        True,
        description="Include column headers as the first CSV row",
    )
    delimiter: Literal[",", ";", "\t", "|"] = Field(
        ",",
        description="CSV delimiter character",
    )
    max_rows: int | None = Field(
        None,
        ge=1,
        description="Maximum number of data rows to extract",
    )
    output_format: Literal["csv", "json", "markdown", "pandas_json"] = Field(
        "csv",
        description="Output format for extracted table data",
    )
    normalize_whitespace: bool = Field(
        True,
        description="Collapse multiple whitespace characters into single spaces",
    )
    strip_cells: bool = Field(
        True,
        description="Strip leading/trailing whitespace from cell values",
    )
    skip_empty_rows: bool = Field(
        True,
        description="Omit rows where all cells are empty",
    )
    encoding: str | None = Field(
        None,
        description="Character encoding for HTML (e.g., 'utf-8', 'latin-1'). Auto-detected if omitted.",
    )
    include_table_metadata: bool = Field(
        False,
        description="Include table-level metadata (caption, summary, id, class) in output",
    )


class TableToCsvExtractorTool(BaseTool):
    """Extract HTML tables and convert to CSV."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="table_to_csv_extractor",
            name="Table to CSV Extractor",
            description=(
                "Extract HTML tables from web pages and convert them to "
                "structured CSV format. Supports column header detection, "
                "row/column spanning, CSS selector targeting, and configurable "
                "delimiters. Returns CSV string ready for import."
            ),
            category="browser-extraction",
            input_schema=TableToCsvExtractorInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "tables_found": {"type": "integer"},
                    "format": {"type": "string"},
                    "tables": {"type": "array"},
                    "total_rows": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["html", "tables", "csv", "extraction", "scraping", "data"],
            requires_auth=False,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = TableToCsvExtractorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        try:
            soup = BeautifulSoup(validated.html, "lxml", from_encoding=validated.encoding)
            tables = soup.find_all("table") if not validated.selector else soup.select(validated.selector)

            if not tables:
                return ToolResult.error_result(tool_id=self.tool_id, error="No tables found in HTML")

            # Extract requested table(s)
            selected_index = validated.table_index
            if selected_index is not None:
                if selected_index >= len(tables):
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=f"Table index {selected_index} out of range. {len(tables)} table(s) found.",
                    )
                tables = [tables[selected_index]]

            all_table_results: list[dict[str, Any]] = []
            for idx, table in enumerate(tables):
                headers, rows = self._extract_table(table, validated)
                formatted = self._format_output(headers, rows, validated)
                actual_idx = selected_index if selected_index is not None else idx
                entry: dict[str, Any] = {
                    "table_index": actual_idx,
                    "data": formatted,
                    "row_count": len(rows),
                    "column_count": (len(headers) if headers else (len(rows[0]) if rows else 0)),
                    "headers": headers,
                }
                if validated.include_table_metadata:
                    entry["metadata"] = {
                        "caption": (table.find("caption").get_text(strip=True) if table.find("caption") else None),
                        "summary": table.get("summary", ""),
                        "id": table.get("id", ""),
                        "class": table.get("class", []),
                    }
                all_table_results.append(entry)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "tables_found": len(tables),
                    "format": validated.output_format,
                    "tables": all_table_results,
                    "total_rows": sum(t["row_count"] for t in all_table_results),
                    "success": True,
                },
            )
        except Exception as e:
            logger.exception("table_to_csv_extractor failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    def _extract_table(self, table, validated: TableToCsvExtractorInput) -> tuple[list[str], list[list[str]]]:
        headers: list[str] = []
        data_rows: list[list[str]] = []

        # Extract thead headers
        thead = table.find("thead")
        if thead:
            for th in thead.find_all("th"):
                headers.append(self._clean_cell(th.get_text(), validated))

        # If no thead, try first row as headers
        if not headers and validated.include_headers:
            first_row = table.find("tr")
            if first_row:
                for th in first_row.find_all(["th", "td"]):
                    headers.append(self._clean_cell(th.get_text(), validated))

        # Extract data rows (skip header row if we already extracted headers)
        rows = table.find_all("tr")
        start = 1 if headers and validated.include_headers else 0

        for row in rows[start:]:
            if validated.max_rows and len(data_rows) >= validated.max_rows:
                break
            cells = row.find_all(["td", "th"])
            if cells:
                cell_values = [self._clean_cell(cell.get_text(), validated) for cell in cells]
                if validated.skip_empty_rows and not any(v for v in cell_values):
                    continue
                data_rows.append(cell_values)

        return headers, data_rows

    @staticmethod
    def _clean_cell(text: str, validated: TableToCsvExtractorInput) -> str:
        """Apply whitespace normalization and stripping to a cell value."""
        if validated.strip_cells:
            text = text.strip()
        if validated.normalize_whitespace:
            text = re.sub(r"\s+", " ", text)
        return text

    def _to_csv(
        self,
        headers: list[str],
        rows: list[list[str]],
        include_headers: bool,
        delimiter: str,
    ) -> str:
        output = io.StringIO()
        writer = csv.writer(output, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)

        if include_headers and headers:
            writer.writerow(headers)
        for row in rows:
            writer.writerow(row)

        return output.getvalue()

    def _format_output(
        self,
        headers: list[str],
        rows: list[list[str]],
        validated: TableToCsvExtractorInput,
    ) -> str | list[dict] | list[list]:
        """Format extracted table data in the requested output format."""
        if validated.output_format == "csv":
            return self._to_csv(headers, rows, validated.include_headers, validated.delimiter)
        elif validated.output_format == "json":
            if validated.include_headers and headers:
                return [dict(zip(headers, row, strict=False)) for row in rows]
            return rows
        elif validated.output_format == "markdown":
            lines: list[str] = []
            if validated.include_headers and headers:
                lines.append("| " + " | ".join(headers) + " |")
                lines.append("|" + "|".join(["---" for _ in headers]) + "|")
            for row in rows:
                lines.append("| " + " | ".join(row) + " |")
            return "\n".join(lines)
        elif validated.output_format == "pandas_json":
            if validated.include_headers and headers:
                return [dict(zip(headers, row, strict=False)) for row in rows]
            # Orient='values' style
            return rows
        return validated.output_format  # fallback


register_tool(TableToCsvExtractorTool())
