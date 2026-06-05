"""
Data Processing Tools — XML to JSON Converter.

xml_to_json_converter → Convert legacy XML API responses into structured JSON for agent use.
"""

from __future__ import annotations

import logging
from typing import Any
from xml.etree import ElementTree as ET

from pydantic import Field

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# xml_to_json_converter
# ---------------------------------------------------------------------------

class XmlToJsonInput(ToolInput):
    data: str | None = Field(
        None,
        description="Raw XML string or Base64-encoded XML content",
    )
    url: str | None = Field(
        None,
        description="URL to fetch XML from (optional if 'data' is provided)",
    )
    pretty: bool = Field(
        False,
        description="Pretty-print the output JSON",
    )


def _element_to_dict(element: ET.Element) -> dict[str, Any]:
    """Recursively convert an XML element tree to a dict."""
    result: dict[str, Any] = {}

    # Attributes
    if element.attrib:
        result["@attributes"] = dict(element.attrib)

    # Child elements
    children = list(element)
    if children:
        child_dict: dict[str, Any] = {}
        for child in children:
            child_data = _element_to_dict(child)
            tag = child.tag
            # Handle duplicate tags → convert to list
            if tag in child_dict:
                existing = child_dict[tag]
                if not isinstance(existing, list):
                    child_dict[tag] = [existing]
                child_dict[tag].append(child_data.get(tag, child_data))
            else:
                # If child_data has a single key matching the tag, unwrap
                if len(child_data) == 1 and tag in child_data:
                    child_dict[tag] = child_data[tag]
                else:
                    child_dict[tag] = child_data
        result.update(child_dict)

    # Text content (only if there are children OR no children but has text)
    text = element.text
    if text is not None:
        text = text.strip()
        if text:
            if not children:
                # Leaf node: just return the text value
                if not element.attrib:
                    return {element.tag: text}
            result["#text"] = text

    # Tail text (text after closing tag)
    tail = element.tail
    if tail is not None:
        tail = tail.strip()
        if tail:
            result["#tail"] = tail

    return {element.tag: result} if element.tag else result


class XmlToJsonConverterTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="xml_to_json_converter",
            name="XML to JSON Converter",
            description="Convert legacy XML API responses into structured JSON for agent use",
            category="data-processing",
            input_schema=XmlToJsonInput.schema_extra(),
            tags=["xml", "json", "convert", "data-processing"],
            requires_auth=False,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = XmlToJsonInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            xml_bytes = await resolve_input(validated.data, validated.url, label="XML")
        except ValueError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Failed to read XML: {e}"
            )

        try:
            xml_str = xml_bytes.decode("utf-8")
            root = ET.fromstring(xml_str)
            result = _element_to_dict(root)

            import json as _json

            json_str = (
                _json.dumps(result, indent=2, ensure_ascii=False)
                if validated.pretty
                else _json.dumps(result, ensure_ascii=False)
            )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "root_tag": root.tag,
                    "json": json_str if validated.pretty else result,
                    "pretty": json_str if validated.pretty else None,
                },
            )
        except ET.ParseError as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"XML parse error: {e}"
            )
        except Exception as e:
            logger.exception("xml_to_json_converter failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

register_tool(XmlToJsonConverterTool())
