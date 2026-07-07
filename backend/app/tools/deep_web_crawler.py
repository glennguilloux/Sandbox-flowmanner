"""
Web Scraping Tools — Deep Web Crawler.

deep_web_crawler → Autonomous multi-page crawler that follows links based on semantic relevance.
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# Maximum crawl depth and pages
MAX_DEPTH = 5
MAX_PAGES = 50


class _LinkExtractor(HTMLParser):
    """Extract hrefs and their link text from HTML."""

    def __init__(self):
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href: str = ""
        self._current_text: list[str] = []
        self._in_a = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._in_a = True
            self._current_text = []
            attrs_dict = dict(attrs)
            self._current_href = attrs_dict.get("href", "")

    def handle_endtag(self, tag):
        if tag.lower() == "a":
            if self._current_href and not self._current_href.startswith(("#", "javascript:", "mailto:", "tel:")):
                text = " ".join(self._current_text).strip()
                self.links.append({"url": self._current_href, "text": text})
            self._in_a = False
            self._current_href = ""

    def handle_data(self, data):
        if self._in_a:
            self._current_text.append(data.strip())


def _score_relevance(text: str, query_terms: list[str]) -> float:
    """Simple TF-based relevance score."""
    if not query_terms or not text:
        return 0.0
    text_lower = text.lower()
    score = sum(text_lower.count(term) for term in query_terms)
    return score / max(len(text_lower.split()), 1)


class DeepWebCrawlerInput(ToolInput):
    start_url: str = Field(..., description="Starting URL to begin crawling from")
    query: str | None = Field(
        None,
        description="Search terms to guide relevance-based link following",
    )
    max_pages: int = Field(20, ge=1, le=MAX_PAGES, description="Maximum pages to crawl")
    max_depth: int = Field(2, ge=1, le=MAX_DEPTH, description="Maximum link depth from start URL")
    same_domain_only: bool = Field(
        True,
        description="Only follow links on the same domain as start_url",
    )
    extract_text: bool = Field(
        True,
        description="Extract visible text from each crawled page",
    )
    min_relevance: float = Field(
        0.01,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score to include a page (0 = include all)",
    )


class DeepWebCrawlerTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="deep_web_crawler",
            name="Deep Web Crawler",
            description="Autonomous multi-page crawler that follows links based on semantic relevance",
            category="web-scraping",
            input_schema=DeepWebCrawlerInput.schema_extra(),
            tags=["crawl", "deep", "spider", "links", "semantic"],
            requires_auth=False,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = DeepWebCrawlerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        start_url = validated.start_url.strip()
        if not start_url:
            return ToolResult.error_result(tool_id=self.tool_id, error="start_url is empty")

        parsed_start = urlparse(start_url)
        base_domain = parsed_start.netloc.lower()

        query_terms = []
        if validated.query:
            query_terms = [t.lower().strip() for t in validated.query.split() if len(t) > 1]

        visited: set[str] = set()
        results: list[dict[str, Any]] = []
        # Queue: (url, depth)
        queue: list[tuple[str, int]] = [(start_url, 0)]

        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; FlowmannerBot/1.0)",
                },
            ) as client:
                while queue and len(results) < validated.max_pages:
                    url, depth = queue.pop(0)

                    if url in visited:
                        continue
                    if depth > validated.max_depth:
                        continue

                    # Same-domain check
                    if validated.same_domain_only:
                        parsed = urlparse(url)
                        if parsed.netloc.lower() != base_domain:
                            continue

                    visited.add(url)

                    try:
                        response = await client.get(url)
                        if response.status_code != 200:
                            continue

                        html = response.text

                        # Extract text
                        text = ""
                        if validated.extract_text:
                            # Simple text extraction: strip tags
                            text = re.sub(r"<[^>]+>", " ", html)
                            text = re.sub(r"\s+", " ", text).strip()

                        # Extract title
                        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
                        title = title_match.group(1).strip() if title_match else ""

                        # Score relevance
                        relevance = _score_relevance(title + " " + text[:1000], query_terms)

                        if relevance >= validated.min_relevance:
                            results.append(
                                {
                                    "url": url,
                                    "title": title,
                                    "depth": depth,
                                    "relevance": round(relevance, 4),
                                    "text_preview": (text[:1000] if validated.extract_text else ""),
                                    "text_length": (len(text) if validated.extract_text else 0),
                                }
                            )

                        # Extract links for next depth level
                        if depth < validated.max_depth:
                            extractor = _LinkExtractor()
                            extractor.feed(html)
                            for link in extractor.links:
                                full_url = urljoin(url, link["url"])
                                if full_url not in visited and len(queue) < validated.max_pages * 3:
                                    queue.append((full_url, depth + 1))

                    except Exception as e:
                        logger.debug("Crawl error for %s: %s", url, e)
                        continue

            # Sort by relevance
            if query_terms:
                results.sort(key=lambda r: r["relevance"], reverse=True)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "start_url": start_url,
                    "domain": base_domain,
                    "query": validated.query,
                    "pages_crawled": len(visited),
                    "pages_returned": len(results),
                    "max_depth": validated.max_depth,
                    "results": results,
                },
            )

        except Exception as e:
            logger.exception("deep_web_crawler failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


register_tool(DeepWebCrawlerTool())
