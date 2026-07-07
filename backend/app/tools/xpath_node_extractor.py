"""
Browser-based Data Extraction Tools — XPath Node Extractor.

xpath_node_extractor → Query HTML/XML content using XPath expressions
    to extract text, attributes, and structured data with namespace support.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from lxml import etree
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class XpathNodeExtractorInput(ToolInput):
    """Input schema: html, xpath, extract, namespaces, limit, format."""

    html: str = Field(
        ...,
        min_length=1,
        max_length=500000,
        description="Raw HTML or XML content to query with XPath",
    )
    queries: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="XPath expressions (e.g., ['//div[@class=\"product\"]/h2', '//p[contains(text(),\"price\")]'])",
    )
    return_type: Literal["text", "html", "attribute", "all", "node_name", "count"] = Field(
        "text",
        description="What to return: 'text', 'html', 'attribute', 'all', 'node_name' (tag name), or 'count' (match count only)",
    )
    attribute_name: str | None = Field(
        None,
        description="Attribute name to extract. Required when return_type='attribute'.",
    )
    namespaces: dict[str, str] | None = Field(
        None,
        description="XML namespace mapping (e.g., {'re': 'http://example.com/ns'})",
    )
    max_results: int | None = Field(
        None,
        ge=1,
        le=10000,
        description="Maximum number of results per query",
    )
    first_only: bool = Field(
        False,
        description="Return only the first matching node per query",
    )
    normalize_text: bool = Field(
        True,
        description="Strip and collapse whitespace in extracted text",
    )
    as_xml: bool = Field(
        False,
        description="Return HTML/XML as serialized XML instead of lxml's HTML method",
    )


class XpathNodeExtractorTool(BaseTool):
    """Query HTML/XML using XPath expressions."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="xpath_node_extractor",
            visibility="opt_in",
            required_scopes=[],
            name="XPath Node Extractor",
            description=(
                "Query HTML/XML content using XPath expressions to extract "
                "text, attributes, and structured data. Supports namespace "
                "mappings, multiple extraction modes, and configurable "
                "result limits. Uses lxml for parsing."
            ),
            category="browser-extraction",
            input_schema=XpathNodeExtractorInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "queries": {"type": "array", "items": {"type": "string"}},
                    "total_match_count": {"type": "integer"},
                    "per_query": {"type": "array"},
                    "first_match": {"type": "string"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["html", "xml", "xpath", "extraction", "scraping", "lxml"],
            requires_auth=False,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = XpathNodeExtractorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if validated.return_type == "attribute" and not validated.attribute_name:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="attribute_name is required when return_type='attribute'",
            )

        try:
            # Parse with lxml for XPath support
            parser = etree.HTMLParser()
            tree = etree.fromstring(validated.html.encode("utf-8"), parser)

            namespaces = validated.namespaces or {}

            all_query_results: list[dict[str, Any]] = []
            total_matches = 0

            for xpath_expr in validated.queries:
                elements = tree.xpath(xpath_expr, namespaces=namespaces)

                if validated.first_only and elements:
                    elements = elements[:1]

                if validated.return_type == "count":
                    results = [len(elements)]
                elif validated.max_results:
                    elements = elements[: validated.max_results]
                    results = self._extract_results(elements, validated)
                else:
                    results = self._extract_results(elements, validated)
                total_matches += len(results)
                all_query_results.append(
                    {
                        "xpath": xpath_expr,
                        "match_count": len(results),
                        "results": results,
                    }
                )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "queries": validated.queries,
                    "total_match_count": total_matches,
                    "per_query": all_query_results,
                    "first_match": (
                        all_query_results[0]["results"][0]
                        if all_query_results and all_query_results[0]["results"]
                        else None
                    ),
                    "success": True,
                },
            )
        except etree.XPathEvalError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid XPath expression: {e}")
        except Exception as e:
            logger.exception("xpath_node_extractor failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    def _extract_results(self, elements: list, validated: XpathNodeExtractorInput) -> list[Any]:
        results: list[Any] = []

        for el in elements:
            if validated.return_type == "text":
                text = "".join(el.itertext()) if hasattr(el, "itertext") else str(el.text or "")
                text = re.sub(r"\s+", " ", text.strip()) if validated.normalize_text else text.strip()
                results.append(text)
            elif validated.return_type == "html":
                method = "xml" if validated.as_xml else "html"
                results.append(etree.tostring(el, encoding="unicode", method=method) if hasattr(el, "tag") else str(el))
            elif validated.return_type == "attribute":
                val = el.get(validated.attribute_name) if hasattr(el, "get") else ""
                results.append(val or "")
            elif validated.return_type == "node_name":
                results.append(el.tag if hasattr(el, "tag") else "text")
            elif validated.return_type == "all":
                item: dict[str, Any] = {"tag": el.tag if hasattr(el, "tag") else "text"}
                if hasattr(el, "text") and el.text:
                    item["text"] = el.text.strip()
                if hasattr(el, "attrib"):
                    item.update(el.attrib)
                results.append(item)

        return results


register_tool(XpathNodeExtractorTool())
