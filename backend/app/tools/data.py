"""
Data Tools — Agent-callable tools for structured data processing.

json_transform  → apply a jq-like filter to JSON data
csv_parse       → parse CSV text into rows
regex_extract   → extract all regex matches from text
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from typing import Any

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


# ── json_transform ───────────────────────────────────────────────────


class JsonTransformInput(ToolInput):
    json_data: str = Field(..., description="JSON string to transform")
    jq_filter: str = Field(
        ...,
        description=(
            "A simple jq-like filter expression. Supported syntax:\n"
            "  '.'        — return the root object\n"
            "  '.key'     — access a top-level key\n"
            "  '.a.b.c'   — nested key access\n"
            "  '.[0]'     — array index\n"
            "  '.[]'      — iterate array/object values\n"
            "  '.key | .subkey' — pipe (chained access)\n"
        ),
    )


def _apply_jq_filter(data: Any, expr: str) -> Any:
    """Minimal jq-like evaluator supporting dot-notation, array index, and pipes."""
    expr = expr.strip()
    if not expr or expr == ".":
        return data

    # Split on top-level pipes (not inside brackets)
    segments: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in expr:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "|" and depth == 0:
            segments.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    segments.append("".join(current).strip())

    result = data
    for seg in segments:
        if not seg or seg == ".":
            continue

        # Handle '.[]' — iterate
        if seg == ".[]":
            if isinstance(result, list):
                result = result
            elif isinstance(result, dict):
                result = list(result.values())
            else:
                raise ValueError(f"Cannot iterate over {type(result).__name__}")
            continue

        # Strip leading dot
        path = seg.lstrip(".")

        # Split into parts respecting bracket notation
        parts: list[str] = []
        buf: list[str] = []
        in_bracket = False
        for ch in path:
            if ch == "[":
                in_bracket = True
                if buf:
                    parts.append("".join(buf))
                    buf = []
            elif ch == "]":
                in_bracket = False
                parts.append(f"[{''.join(buf)}]")
                buf = []
            else:
                buf.append(ch)
        if buf:
            parts.append("".join(buf))

        for part in parts:
            if part.startswith("[") and part.endswith("]"):
                inner = part[1:-1].strip().strip("'\"")
                if inner.isdigit():
                    idx = int(inner)
                    result = result[idx]
                else:
                    # key lookup inside bracket
                    result = result[inner]
            else:
                result = result[part]

    return result


class JsonTransformTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="json_transform",
            name="JSON Transform",
            description="Apply a jq-like filter to transform JSON data",
            category="data",
            input_schema=JsonTransformInput.schema_extra(),
            tags=["json", "transform", "data"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = JsonTransformInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        try:
            data = json.loads(validated.json_data)
        except json.JSONDecodeError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid JSON: {e}")

        try:
            result = _apply_jq_filter(data, validated.jq_filter)
            # Ensure result is JSON-serialisable for the response
            serialised = json.dumps(result, ensure_ascii=False, default=str)
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={"output": result, "output_json": serialised},
            )
        except (KeyError, IndexError, TypeError, ValueError) as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Filter error: {e}")
        except Exception as e:
            logger.exception("json_transform failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ── csv_parse ────────────────────────────────────────────────────────


class CsvParseInput(ToolInput):
    csv_text: str = Field(..., description="CSV text to parse")
    delimiter: str = Field(",", description="Column delimiter character")
    has_header: bool = Field(True, description="Whether the first row is a header")


class CsvParseTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="csv_parse",
            name="CSV Parse",
            description="Parse CSV text into structured rows (list of dicts)",
            category="data",
            input_schema=CsvParseInput.schema_extra(),
            tags=["csv", "parse", "data"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = CsvParseInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        try:
            reader = csv.DictReader(
                io.StringIO(validated.csv_text),
                delimiter=validated.delimiter,
            )
            rows: list[dict] = []
            for row in reader:
                rows.append(dict(row))

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "rows": rows,
                    "row_count": len(rows),
                    "columns": list(rows[0].keys()) if rows else [],
                },
            )
        except Exception as e:
            logger.exception("csv_parse failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ── regex_extract ────────────────────────────────────────────────────


class RegexExtractInput(ToolInput):
    text: str = Field(..., description="Text to search")
    pattern: str = Field(..., description="Regular expression pattern (Python re syntax)")


class RegexExtractTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="regex_extract",
            name="Regex Extract",
            description="Extract all regex matches (and groups) from text",
            category="data",
            input_schema=RegexExtractInput.schema_extra(),
            tags=["regex", "extract", "text", "data"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = RegexExtractInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        try:
            pattern = re.compile(validated.pattern)
        except re.error as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid regex: {e}")

        matches = []
        for m in pattern.finditer(validated.text):
            entry: dict[str, Any] = {
                "match": m.group(0),
                "start": m.start(),
                "end": m.end(),
            }
            if m.groups():
                entry["groups"] = list(m.groups())
            if m.groupdict():
                entry["named_groups"] = m.groupdict()
            matches.append(entry)

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "matches": matches,
                "count": len(matches),
            },
        )


# ── Register ─────────────────────────────────────────────────────────

register_tool(JsonTransformTool())
register_tool(CsvParseTool())
register_tool(RegexExtractTool())
