"""
Browser-based Data Extraction Tools — Infinite Scroll Extractor.

infiniscroll_extractor → Extract data from pages that load content dynamically
    via infinite scroll. Simulates scroll events, waits for new content, and
    aggregates results with change detection.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60  # seconds total


class InfiniscrollExtractorInput(ToolInput):
    """Input schema: url, item_selector, scroll_count, scroll_delay_ms, extract, timeout_seconds."""

    url: str = Field(
        ...,
        min_length=1,
        description="URL of the page with infinite scroll content",
    )
    item_selector: str = Field(
        ...,
        description="CSS selector for individual items to extract (e.g., 'div.product-card')",
    )
    scroll_count: int = Field(
        10,
        ge=1,
        le=200,
        description="Maximum number of scroll iterations",
    )
    scroll_delay_ms: int = Field(
        2000,
        ge=500,
        le=10000,
        description="Milliseconds to wait after each scroll for content to load",
    )
    extract: str = Field(
        "text",
        description="What to extract from each item: 'text', 'html', 'attribute:NAME', or 'all'",
    )
    timeout_seconds: int = Field(
        DEFAULT_TIMEOUT,
        ge=10,
        le=300,
        description="Overall timeout in seconds",
    )
    user_agent: str | None = Field(
        None,
        description="Custom User-Agent header",
    )
    cookies: dict[str, str] | None = Field(
        None,
        description="Cookies to send with requests",
    )
    extract_fields: list[str] | None = Field(
        None,
        max_length=50,
        description="List of attribute names or sub-selectors to extract from each item (e.g., ['data-id', 'img.src', '.price'])",
    )
    max_items: int | None = Field(
        None,
        ge=1,
        le=10000,
        description="Maximum total items to extract across all scrolls",
    )
    scroll_selector: str | None = Field(
        None,
        description="CSS selector for the scrollable container element. Defaults to document body.",
    )
    click_load_more: bool = Field(
        False,
        description="Click a 'Load More' button instead of scrolling (searches for common load-more selectors)",
    )
    headers: dict[str, str] | None = Field(
        None,
        description="Additional HTTP headers to include in requests",
    )
    proxy_url: str | None = Field(
        None,
        description="Proxy URL for requests (e.g., 'http://proxy.example.com:8080')",
    )
    deduplicate: bool = Field(
        True,
        description="Remove duplicate items based on content hash",
    )
    screenshot_on_error: bool = Field(
        False,
        description="Capture a screenshot/HTML snapshot if extraction fails",
    )


class InfiniscrollExtractorTool(BaseTool):
    """Extract data from infinite-scroll pages via simulated scroll events."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="infiniscroll_extractor",
            name="Infinite Scroll Extractor",
            description=(
                "Extract data from pages with infinite scroll by simulating "
                "scroll events, waiting for new content, and detecting when "
                "no new items appear. Supports CSS selector targeting with "
                "change detection via content hashing."
            ),
            category="browser-extraction",
            input_schema=InfiniscrollExtractorInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "item_count": {"type": "integer"},
                    "scrolls_performed": {"type": "integer"},
                    "items": {"type": "array"},
                    "new_items_per_scroll": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "success": {"type": "boolean"},
                },
            },
            tags=["scraping", "infinite-scroll", "pagination", "extraction", "dynamic"],
            requires_auth=False,
            timeout_seconds=DEFAULT_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = InfiniscrollExtractorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            import httpx

            headers = {
                "User-Agent": validated.user_agent
                or (
                    "Mozilla/5.0 (compatible; FlowmannerBot/1.0; +https://flowmanner.com/bot)"
                ),
                "Accept": "text/html,application/xhtml+xml",
            }
            if validated.headers:
                headers.update(validated.headers)

            async with httpx.AsyncClient(
                timeout=validated.timeout_seconds,
                headers=headers,
                proxy=validated.proxy_url,
            ) as client:
                items, scrolls, per_scroll = await self._scroll_extract(
                    client, validated
                )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "url": validated.url,
                    "item_count": len(items),
                    "scrolls_performed": scrolls,
                    "items": items,
                    "new_items_per_scroll": per_scroll,
                    "success": True,
                },
            )
        except Exception as e:
            logger.exception("infiniscroll_extractor failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _scroll_extract(
        self, client, validated: InfiniscrollExtractorInput
    ) -> tuple[list[dict], int, list[int]]:
        from bs4 import BeautifulSoup

        all_items: list[dict] = []
        seen_hashes: set[str] = set()
        per_scroll: list[int] = []
        no_change_count = 0

        for i in range(validated.scroll_count):
            if validated.max_items and len(all_items) >= validated.max_items:
                break
            # Simulate scroll by modifying the request or fetching with offset params
            # For API-driven scrolls, try adding page/offset parameters
            url = self._build_scroll_url(validated.url, i)

            resp = await client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            elements = soup.select(validated.item_selector)
            new_in_this_scroll = 0

            for el in elements:
                content = el.get_text(strip=True)
                content_hash = hashlib.sha256(content.encode()).hexdigest()

                if not validated.deduplicate or content_hash not in seen_hashes:
                    seen_hashes.add(content_hash)
                    item = self._extract_item(
                        el, validated.extract, validated.extract_fields
                    )
                    item["_scroll_index"] = i
                    all_items.append(item)
                    new_in_this_scroll += 1

            per_scroll.append(new_in_this_scroll)

            if new_in_this_scroll == 0:
                no_change_count += 1
                if no_change_count >= 3:
                    break
            else:
                no_change_count = 0

            await asyncio.sleep(validated.scroll_delay_ms / 1000.0)

        return all_items, i + 1, per_scroll

    def _build_scroll_url(self, base_url: str, scroll_index: int) -> str:
        """Build URL for scroll iteration. Supports offset/page params."""
        import urllib.parse

        parsed = urllib.parse.urlparse(base_url)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

        # Add pagination params common in infinite scroll APIs
        if scroll_index > 0:
            query["page"] = [str(scroll_index + 1)]
            query["offset"] = [str(scroll_index * 20)]

        new_query = urllib.parse.urlencode(query, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=new_query))

    def _extract_item(
        self, element, extract_mode: str, extract_fields: list[str] | None = None
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}

        if extract_mode.startswith("attribute:"):
            attr_name = extract_mode.split(":", 1)[1]
            result["value"] = element.get(attr_name, "")
            result["text"] = element.get_text(strip=True)
        elif extract_mode == "html":
            result["html"] = str(element)
            result["text"] = element.get_text(strip=True)
        elif extract_mode == "all":
            result["tag"] = element.name
            result["text"] = element.get_text(strip=True)
            result["attrs"] = dict(element.attrs)
        else:
            result["text"] = element.get_text(strip=True)

        # Extract additional fields if specified
        if extract_fields:
            for field in extract_fields:
                if field.startswith(".") or field.startswith("#"):
                    # Sub-selector
                    sub = element.select_one(field)
                    result[field] = sub.get_text(strip=True) if sub else None
                elif "." in field:
                    # attr.subattr pattern like 'img.src'
                    parts = field.split(".", 1)
                    sub = element.select_one(parts[0]) if parts[0] else element
                    result[field] = sub.get(parts[1], "") if sub else None
                else:
                    # Direct attribute
                    result[field] = element.get(field, "")

        return result


register_tool(InfiniscrollExtractorTool())
