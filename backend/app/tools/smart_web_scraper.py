"""
Web Scraping Tools — Smart Web Scraper.

smart_web_scraper → Extract main article content from URLs while stripping ads and nav.
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


# ── HTML text extractor ───────────────────────────────────────────────────


class _TextExtractor(HTMLParser):
    """Extract readable text while stripping script, style, nav, footer, etc."""

    SKIP_TAGS = {
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "aside",
        "noscript",
        "iframe",
        "svg",
        "form",
        "select",
        "button",
    }
    BLOCK_TAGS = {
        "div",
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "tr",
        "section",
        "article",
        "main",
        "blockquote",
        "pre",
        "table",
        "ul",
        "ol",
        "dl",
        "hr",
        "br",
    }

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0
        self.in_block = False

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if tag_lower in self.SKIP_TAGS:
            self.skip_depth += 1
        elif (
            tag_lower in self.BLOCK_TAGS
            and self.parts
            and not self.parts[-1].endswith("\n")
        ):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in self.SKIP_TAGS:
            if self.skip_depth > 0:
                self.skip_depth -= 1
        elif (
            tag_lower in self.BLOCK_TAGS
            and self.parts
            and not self.parts[-1].endswith("\n")
        ):
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth > 0:
            return
        text = data.strip()
        if text:
            self.parts.append(text)
            self.parts.append(" ")

    def get_text(self) -> str:
        raw = "".join(self.parts)
        # Collapse whitespace
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        return raw.strip()


def _extract_links(html: str, base_url: str) -> list[dict[str, str]]:
    """Extract all links from HTML."""
    links: list[dict[str, str]] = []
    link_pattern = re.compile(
        r'<a\s+(?:[^>]*?\s+)?href=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    text_pattern = re.compile(r">([^<]+)</a>", re.IGNORECASE)

    for match in link_pattern.finditer(html):
        href = match.group(1)
        if href.startswith("#") or href.startswith("javascript:"):
            continue
        full_url = urljoin(base_url, href)
        links.append({"url": full_url, "text": ""})

    return links


def _extract_title(html: str) -> str:
    """Extract page title."""
    match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_meta(html: str) -> dict[str, str]:
    """Extract meta tags."""
    meta: dict[str, str] = {}
    pattern = re.compile(
        r'<meta\s+(?:[^>]*?\s+)?(?:name|property)=["\']([^"\']+)["\'][^>]*?content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        meta[match.group(1).lower()] = match.group(2)
    return meta


# ── Input ─────────────────────────────────────────────────────────────────


class SmartWebScraperInput(ToolInput):
    url: str = Field(..., description="URL of the web page to scrape")
    extract_links: bool = Field(True, description="Extract all links from the page")
    extract_meta: bool = Field(
        True, description="Extract meta tags (description, keywords)"
    )
    max_text_length: int = Field(50000, description="Maximum text length to return")


class SmartWebScraperTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="smart_web_scraper",
            name="Smart Web Scraper",
            description="Extract main article content from URLs while stripping ads and nav",
            category="web-scraping",
            input_schema=SmartWebScraperInput.schema_extra(),
            tags=["web", "scrape", "extract", "article", "content"],
            requires_auth=False,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SmartWebScraperInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        url = validated.url.strip()
        if not url:
            return ToolResult.error_result(tool_id=self.tool_id, error="URL is empty")

        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid URL: {url}"
            )

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; FlowmannerBot/1.0; +https://flowmanner.com)",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text

            # Extract text
            extractor = _TextExtractor()
            extractor.feed(html)
            text = extractor.get_text()

            # Truncate
            if len(text) > validated.max_text_length:
                text = text[: validated.max_text_length] + "\n\n... [truncated]"

            result: dict[str, Any] = {
                "url": url,
                "title": _extract_title(html),
                "text": text,
                "text_length": len(text),
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
            }

            if validated.extract_meta:
                result["meta"] = _extract_meta(html)

            if validated.extract_links:
                result["links"] = _extract_links(html, url)
                result["link_count"] = len(result["links"])

            return ToolResult.success_result(tool_id=self.tool_id, result=result)

        except httpx.HTTPStatusError as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"HTTP {e.response.status_code}: {url}",
            )
        except httpx.RequestError as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Request failed: {e}"
            )
        except Exception as e:
            logger.exception("smart_web_scraper failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


register_tool(SmartWebScraperTool())
