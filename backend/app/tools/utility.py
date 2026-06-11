"""
Utility Tools — Agent-callable tools for common utility operations.

uuid_generator      → generate a UUID v4
timestamp_converter → convert timestamps between formats
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


# ── uuid_generator ───────────────────────────────────────────────────


class UUIDGeneratorInput(ToolInput):
    count: int = Field(1, description="Number of UUIDs to generate (1-100)")
    namespace: str = Field(
        "v4",
        description="UUID version: 'v4' (random) or 'v5' (deterministic — requires 'name' field)",
    )
    name: str | None = Field(None, description="Name for v5 UUID (required when namespace='v5')")
    name_namespace: str | None = Field(
        None,
        description="DNS URL for v5 namespace (e.g. 'dns:example.com'). Defaults to DNS namespace.",
    )


class UUIDGeneratorTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="uuid_generator",
            name="UUID Generator",
            description="Generate one or more UUIDs (v4 random or v5 deterministic)",
            category="utility",
            input_schema=UUIDGeneratorInput.schema_extra(),
            tags=["uuid", "generator", "utility"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = UUIDGeneratorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        count = max(1, min(validated.count, 100))

        try:
            if validated.namespace == "v5":
                if not validated.name:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error="'name' field is required for v5 UUIDs",
                    )
                # Parse namespace UUID
                ns_str = validated.name_namespace or "dns:"
                if ns_str.startswith("dns:"):
                    ns = uuid.NAMESPACE_DNS
                elif ns_str.startswith("url:"):
                    ns = uuid.NAMESPACE_URL
                elif ns_str.startswith("oid:"):
                    ns = uuid.NAMESPACE_OID
                elif ns_str.startswith("x500:"):
                    ns = uuid.NAMESPACE_X500
                else:
                    # Try parsing as a raw UUID string
                    ns = uuid.UUID(ns_str)

                uuids = [str(uuid.uuid5(ns, validated.name)) for _ in range(count)]
            else:
                uuids = [str(uuid.uuid4()) for _ in range(count)]

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "uuids": uuids if count > 1 else uuids[0],
                    "count": len(uuids),
                    "version": validated.namespace,
                },
            )
        except Exception as e:
            logger.exception("uuid_generator failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ── timestamp_converter ──────────────────────────────────────────────


class TimestampConverterInput(ToolInput):
    timestamp: str = Field(
        ...,
        description=(
            "Timestamp string to convert. Special values: 'now' for current time. "
            "Examples: '2024-01-15T10:30:00', '1705312200' (unix epoch)"
        ),
    )
    from_format: str = Field(
        "iso",
        description=(
            "Input format: 'iso' (ISO 8601), 'unix' (epoch seconds), "
            "'unix_ms' (epoch milliseconds), 'rfc2822', or a strptime pattern"
        ),
    )
    to_format: str = Field(
        "iso",
        description=(
            "Output format: 'iso' (ISO 8601), 'unix' (epoch seconds), "
            "'unix_ms' (epoch milliseconds), 'rfc2822', 'human' (readable), "
            "or a strptime pattern"
        ),
    )
    timezone_name: str = Field(
        "UTC",
        description="Target timezone name (e.g. 'UTC', 'US/Eastern', 'Europe/Paris')",
    )


def _parse_timestamp(ts_str: str, fmt: str) -> datetime:
    """Parse a timestamp string into a datetime object."""
    ts = ts_str.strip()

    if fmt == "iso":
        # Handle both with and without timezone
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)

    if fmt == "unix":
        return datetime.fromtimestamp(float(ts), tz=UTC)

    if fmt == "unix_ms":
        return datetime.fromtimestamp(float(ts) / 1000.0, tz=UTC)

    if fmt == "rfc2822":
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(ts)

    # strptime pattern
    return datetime.strptime(ts, fmt).replace(tzinfo=UTC)


def _format_timestamp(dt: datetime, fmt: str) -> str:
    """Format a datetime object into a string."""
    if fmt == "iso":
        return dt.isoformat()

    if fmt == "unix":
        return str(int(dt.timestamp()))

    if fmt == "unix_ms":
        return str(int(dt.timestamp() * 1000))

    if fmt == "rfc2822":
        from email.utils import format_datetime

        return format_datetime(dt, usegmt=True)

    if fmt == "human":
        return dt.strftime("%A, %B %d, %Y at %I:%M:%S %p %Z").strip()

    # strptime pattern
    return dt.strftime(fmt)


class TimestampConverterTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="timestamp_converter",
            name="Timestamp Converter",
            description="Convert timestamps between formats (ISO, Unix, RFC2822, custom patterns)",
            category="utility",
            input_schema=TimestampConverterInput.schema_extra(),
            tags=["timestamp", "convert", "datetime", "utility"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = TimestampConverterInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        try:
            ts_str = validated.timestamp.lower().strip()
            dt = datetime.now(UTC) if ts_str == "now" else _parse_timestamp(validated.timestamp, validated.from_format)

            output = _format_timestamp(dt, validated.to_format)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "input": validated.timestamp,
                    "output": output,
                    "from_format": validated.from_format,
                    "to_format": validated.to_format,
                    "unix_epoch": int(dt.timestamp()),
                    "iso": dt.isoformat(),
                },
            )
        except ValueError as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Parse error — check your input format: {e}",
            )
        except Exception as e:
            logger.exception("timestamp_converter failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ── Register ─────────────────────────────────────────────────────────

register_tool(UUIDGeneratorTool())
register_tool(TimestampConverterTool())
