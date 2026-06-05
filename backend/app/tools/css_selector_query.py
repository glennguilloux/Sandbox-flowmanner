"""
Browser-based Data Extraction Tools — CSS Selector Query.

css_selector_query → Query HTML content using CSS selectors to extract
    text, attributes, and structured data with configurable output formats.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from bs4 import BeautifulSoup
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class CssSelectorQueryInput(ToolInput):
    """Input schema: html, selector, extract, attribute, limit, format."""

    html: str = Field(
        ...,
        min_length=1,
        max_length=500000,
        description="Raw HTML content to query",
    )
    selectors: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="CSS selectors to query (e.g., ['div.product > h2.title', 'a.nav-link'])",
    )
    extract: Literal["text", "html", "outer_html", "attribute", "all"] = Field(
        "text",
        description="What to extract: 'text' (inner text), 'html' (inner HTML), 'outer_html' (element + inner HTML), 'attribute' (specific attribute), or 'all'",
    )
    attribute_name: str | None = Field(
        None,
        description="Attribute name to extract (e.g., 'href', 'src', 'data-id'). Required when extract='attribute'.",
    )
    max_results_per_selector: int | None = Field(
        None,
        ge=1,
        le=10000,
        description="Maximum number of results to return per selector",
    )
    format: Literal["list", "json"] = Field(
        "list",
        description="Output format: 'list' of strings or 'json' array of objects",
    )
    first_only: bool = Field(
        False,
        description="Return only the first matching element per selector",
    )
    normalize_text: bool = Field(
        True,
        description="Strip and collapse whitespace in extracted text",
    )
    include_empty: bool = Field(
        False,
        description="Include elements with empty text content in results",
    )
    base_url: str | None = Field(
        None,
        description="Base URL for resolving relative links (e.g., href, src attributes)",
    )


class CssSelectorQueryTool(BaseTool):
    """Query HTML using CSS selectors with BeautifulSoup."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="css_selector_query",
            name="CSS Selector Query",
            description=(
                "Query HTML content using CSS selectors to extract text, "
                "attributes, and structured data. Supports configurable "
                "extraction modes (text, html, attribute, all) and output "
                "formats (list, json). Uses BeautifulSoup for parsing."
            ),
            category="browser-extraction",
            input_schema=CssSelectorQueryInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "selectors": {"type": "array", "items": {"type": "string"}},
                    "total_match_count": {"type": "integer"},
                    "per_selector": {"type": "array"},
                    "first_match": {"type": "string"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["html", "css", "selector", "extraction", "scraping", "beautifulsoup"],
            requires_auth=False,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = CssSelectorQueryInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.extract == "attribute" and not validated.attribute_name:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="attribute_name is required when extract='attribute'",
            )

        try:
            soup = BeautifulSoup(validated.html, "lxml")

            all_selector_results: list[dict[str, Any]] = []
            total_matches = 0

            for selector in validated.selectors:
                elements = soup.select(selector)

                if validated.max_results_per_selector:
                    elements = elements[: validated.max_results_per_selector]

                if validated.first_only and elements:
                    elements = elements[:1]

                results = self._extract_results(elements, validated)
                total_matches += len(results)
                all_selector_results.append(
                    {
                        "selector": selector,
                        "match_count": len(results),
                        "results": results,
                    }
                )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "selectors": validated.selectors,
                    "total_match_count": total_matches,
                    "per_selector": all_selector_results,
                    "first_match": (
                        all_selector_results[0]["results"][0]
                        if all_selector_results and all_selector_results[0]["results"]
                        else None
                    ),
                    "success": True,
                },
            )
        except Exception as e:
            logger.exception("css_selector_query failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    def _extract_results(
        self, elements: list, validated: CssSelectorQueryInput
    ) -> list[Any]:
        results: list[Any] = []

        for el in elements:
            if validated.extract == "text":
                text = el.get_text(strip=True)
                if validated.normalize_text:
                    text = re.sub(r"\s+", " ", text)
                if not validated.include_empty and not text:
                    continue
                results.append(text)
            elif validated.extract == "html":
                results.append(
                    el.decode_contents() if hasattr(el, "decode_contents") else str(el)
                )
            elif validated.extract == "outer_html":
                results.append(str(el))
            elif validated.extract == "attribute":
                val = el.get(validated.attribute_name, "")
                if (
                    validated.base_url
                    and validated.attribute_name in ("href", "src")
                    and val
                    and not val.startswith(("http", "data:", "#"))
                ):
                    from urllib.parse import urljoin

                    val = urljoin(validated.base_url, val)
                if not validated.include_empty and not val:
                    continue
                results.append(val if val is not None else "")
            elif validated.extract == "all":
                attrs = dict(el.attrs.items())
                if validated.base_url:
                    from urllib.parse import urljoin

                    for attr in ("href", "src"):
                        if (
                            attr in attrs
                            and attrs[attr]
                            and not attrs[attr].startswith(("http", "data:", "#"))
                        ):
                            attrs[attr] = urljoin(validated.base_url, attrs[attr])
                attrs["text"] = el.get_text(strip=validated.normalize_text)
                results.append(attrs)

        return results


register_tool(CssSelectorQueryTool())
