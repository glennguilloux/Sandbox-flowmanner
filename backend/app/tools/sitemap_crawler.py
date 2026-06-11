"""
Web Scraping Tools — Sitemap Crawler.

sitemap_crawler → Automatically discover and queue all URLs from a website's XML sitemap.
"""

from __future__ import annotations

import logging
from typing import Any
from xml.etree import ElementTree as ET

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# Sitemap XML namespaces
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class SitemapCrawlerInput(ToolInput):
    sitemap_url: str = Field(
        ...,
        description="URL of the sitemap or sitemap index (e.g., https://example.com/sitemap.xml)",
    )
    max_urls: int = Field(
        500,
        ge=1,
        le=10000,
        description="Maximum number of URLs to return",
    )
    filter_pattern: str | None = Field(
        None,
        description="Optional regex pattern to filter URLs (e.g., '/blog/')",
    )
    include_lastmod: bool = Field(
        True,
        description="Include lastmod dates if present in sitemap",
    )
    follow_indexes: bool = Field(
        True,
        description="Follow sitemap index files to discover nested sitemaps",
    )


async def _fetch_sitemap(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a sitemap XML."""
    response = await client.get(url)
    response.raise_for_status()
    return response.text


def _parse_sitemap(xml_str: str) -> tuple[list[dict[str, str]], list[str]]:
    """
    Parse a sitemap XML. Returns (urls, nested_sitemaps).
    - urls: list of {"loc": url, "lastmod": date, "changefreq": freq, "priority": prio}
    - nested_sitemaps: list of sitemap URLs (from sitemap index)
    """
    urls: list[dict[str, str]] = []
    nested: list[str] = []

    try:
        root = ET.fromstring(xml_str)

        # Check if it's a sitemap index
        tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
        if tag == "sitemapindex":
            for sitemap_el in root.findall("sm:sitemap", SITEMAP_NS) or root.findall("sitemap"):
                loc_el = sitemap_el.find("sm:loc", SITEMAP_NS) or sitemap_el.find("loc")
                if loc_el is not None and loc_el.text:
                    nested.append(loc_el.text.strip())
            return urls, nested

        # Regular sitemap
        for url_el in root.findall("sm:url", SITEMAP_NS) or root.findall("url"):
            entry: dict[str, str] = {}
            for field in ("loc", "lastmod", "changefreq", "priority"):
                field_el = url_el.find(f"sm:{field}", SITEMAP_NS) or url_el.find(field)
                if field_el is not None and field_el.text:
                    entry[field] = field_el.text.strip()
            if "loc" in entry:
                urls.append(entry)

    except ET.ParseError as e:
        logger.warning("XML parse error in sitemap: %s", e)

    return urls, nested


class SitemapCrawlerTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="sitemap_crawler",
            name="Sitemap Crawler",
            description="Automatically discover and queue all URLs from a website's XML sitemap",
            category="web-scraping",
            input_schema=SitemapCrawlerInput.schema_extra(),
            tags=["sitemap", "crawl", "discover", "urls", "seo"],
            requires_auth=False,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SitemapCrawlerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        sitemap_url = validated.sitemap_url.strip()
        if not sitemap_url:
            return ToolResult.error_result(tool_id=self.tool_id, error="sitemap_url is empty")

        try:
            import re as _re

            filter_re = _re.compile(validated.filter_pattern) if validated.filter_pattern else None

            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; FlowmannerBot/1.0)",
                },
            ) as client:
                # Fetch initial sitemap
                xml_str = await _fetch_sitemap(client, sitemap_url)
                all_urls, nested = _parse_sitemap(xml_str)

                # Follow sitemap indexes
                visited_indexes: set[str] = {sitemap_url}
                while nested and validated.follow_indexes:
                    next_nested: list[str] = []
                    for nested_url in nested:
                        if nested_url in visited_indexes:
                            continue
                        if len(all_urls) >= validated.max_urls:
                            break
                        visited_indexes.add(nested_url)
                        try:
                            nested_xml = await _fetch_sitemap(client, nested_url)
                            more_urls, more_nested = _parse_sitemap(nested_xml)
                            all_urls.extend(more_urls)
                            next_nested.extend(more_nested)
                        except Exception as e:
                            logger.warning("Failed to fetch nested sitemap %s: %s", nested_url, e)
                    nested = next_nested

                # Apply filter
                if filter_re:
                    all_urls = [u for u in all_urls if filter_re.search(u.get("loc", ""))]

                # Limit results
                total_found = len(all_urls)
                all_urls = all_urls[: validated.max_urls]

                # Build result entries
                entries = []
                for entry in all_urls:
                    item: dict[str, Any] = {"url": entry.get("loc", "")}
                    if validated.include_lastmod and "lastmod" in entry:
                        item["last_modified"] = entry["lastmod"]
                    if "changefreq" in entry:
                        item["change_frequency"] = entry["changefreq"]
                    if "priority" in entry:
                        item["priority"] = float(entry["priority"]) if entry["priority"] else None
                    entries.append(item)

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "sitemap_url": sitemap_url,
                        "total_urls_found": total_found,
                        "returned_urls": len(entries),
                        "sitemaps_crawled": len(visited_indexes),
                        "urls": entries,
                    },
                )

        except httpx.HTTPStatusError as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"HTTP {e.response.status_code} fetching sitemap",
            )
        except Exception as e:
            logger.exception("sitemap_crawler failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


register_tool(SitemapCrawlerTool())
