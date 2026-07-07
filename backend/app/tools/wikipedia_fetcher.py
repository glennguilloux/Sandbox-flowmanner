"""
Research & Knowledge Retrieval Tools — Wikipedia Fetcher.

wikipedia_fetcher → Retrieve articles, summaries, and search results
    from Wikipedia's REST API.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

WIKI_API_BASE = "https://en.wikipedia.org/w/api.php"
WIKI_REST_BASE = "https://en.wikipedia.org/api/rest_v1"
WIKI_TIMEOUT = int(os.getenv("WIKI_TIMEOUT", "30"))
DEFAULT_LANGUAGE = os.getenv("WIKI_LANGUAGE", "en")

# ── Input ─────────────────────────────────────────────────────────────

WIKI_ACTIONS = (
    "get_article",
    "get_summary",
    "search",
    "get_sections",
    "get_section_content",
)


def _wiki_api_base(lang: str | None = None) -> str:
    """Get the Wikipedia API base URL for a given language."""
    l = lang or DEFAULT_LANGUAGE
    return f"https://{l}.wikipedia.org/w/api.php"


def _wiki_rest_base(lang: str | None = None) -> str:
    """Get the Wikipedia REST base URL for a given language."""
    l = lang or DEFAULT_LANGUAGE
    return f"https://{l}.wikipedia.org/api/rest_v1"


class WikipediaFetcherInput(ToolInput):
    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(WIKI_ACTIONS)}",
    )
    title: str | None = Field(
        None,
        description="Article title to fetch (for get_article, get_summary, get_sections)",
    )
    query: str | None = Field(
        None,
        description="Search query (for search action)",
    )
    section_index: int | None = Field(
        None,
        description="Section index to fetch content from (for get_section_content)",
    )
    language: str = Field(
        "en",
        description=f"Wikipedia language code (default: en)",
    )
    max_results: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum search results to return",
    )
    max_chars: int = Field(
        50000,
        ge=100,
        le=200000,
        description="Maximum characters to return for article content",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class WikipediaFetcherTool(BaseTool):
    """Retrieve articles, summaries, and search Wikipedia."""

    def __init__(self):
        metadata = ToolMetadata(
            visibility="opt_in",
            tool_id="wikipedia_fetcher",
            name="Wikipedia Fetcher",
            description=(
                "Retrieve exact articles, summaries, section contents, and search "
                "results from Wikipedia. Supports multiple languages. "
                "No authentication required."
            ),
            category="research-knowledge-retrieval",
            input_schema=WikipediaFetcherInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "summary": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
            tags=["wikipedia", "encyclopedia", "knowledge", "research", "articles"],
            requires_auth=False,
            timeout_seconds=WIKI_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = WikipediaFetcherInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if validated.action not in WIKI_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(WIKI_ACTIONS)}",
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("Wikipedia API error: %s", e)
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Wikipedia API error ({e.response.status_code}): {e.response.text[:500]}",
            )
        except Exception as e:
            logger.warning("wikipedia_fetcher failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(self, validated: WikipediaFetcherInput) -> dict[str, Any]:
        if validated.action == "get_article":
            return await self._get_article(validated)
        elif validated.action == "get_summary":
            return await self._get_summary(validated)
        elif validated.action == "search":
            return await self._search(validated)
        elif validated.action == "get_sections":
            return await self._get_sections(validated)
        elif validated.action == "get_section_content":
            return await self._get_section_content(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}"}

    # ── Helpers ──────────────────────────────────────────────────

    def _build_article_url(self, title: str, lang: str | None = None) -> str:
        """Build the Wikipedia article URL."""
        l = lang or DEFAULT_LANGUAGE
        return f"https://{l}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"

    def _clean_html(self, html: str) -> str:
        """Extract readable text from HTML, removing infoboxes and references."""
        soup = BeautifulSoup(html, "lxml")

        # Remove unwanted elements
        for tag in soup.find_all(["style", "script", "table", "sup"]):
            tag.decompose()
        # Remove reference lists
        for ref in soup.find_all(class_=["reflist", "references", "navbox", "infobox"]):
            ref.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Collapse blank lines
        import re

        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # ── Action handlers ──────────────────────────────────────────

    async def _get_article(self, validated: WikipediaFetcherInput) -> dict[str, Any]:
        """Fetch a full Wikipedia article by title."""
        if not validated.title:
            return {"error": "title is required for get_article"}

        params = {
            "action": "parse",
            "page": validated.title,
            "prop": "text",
            "format": "json",
            "formatversion": "2",
        }

        async with httpx.AsyncClient(timeout=WIKI_TIMEOUT) as client:
            resp = await client.get(
                _wiki_api_base(validated.language),
                params=params,
                headers={"User-Agent": "Flowmanner/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

        error = data.get("error")
        if error:
            return {
                "action": "get_article",
                "title": validated.title,
                "error": error.get("info", "Article not found"),
            }

        parse = data.get("parse", {})
        raw_html = parse.get("text", "")
        content = self._clean_html(raw_html)

        return {
            "action": "get_article",
            "title": parse.get("title", validated.title),
            "page_id": parse.get("pageid"),
            "url": self._build_article_url(validated.title, validated.language),
            "content": content[: validated.max_chars],
            "content_length": len(content),
            "truncated": len(content) > validated.max_chars,
        }

    async def _get_summary(self, validated: WikipediaFetcherInput) -> dict[str, Any]:
        """Fetch the article summary (intro/extract) from Wikipedia."""
        if not validated.title:
            return {"error": "title is required for get_summary"}

        params = {
            "action": "query",
            "titles": validated.title,
            "prop": "extracts",
            "exintro": "1",
            "explaintext": "1",
            "exsectionformat": "plain",
            "format": "json",
            "formatversion": "2",
        }

        async with httpx.AsyncClient(timeout=WIKI_TIMEOUT) as client:
            resp = await client.get(
                _wiki_api_base(validated.language),
                params=params,
                headers={"User-Agent": "Flowmanner/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

        pages = data.get("query", {}).get("pages", [])
        if not pages or "missing" in pages[0]:
            return {
                "action": "get_summary",
                "title": validated.title,
                "error": "Article not found",
            }

        page = pages[0]
        return {
            "action": "get_summary",
            "title": page.get("title", validated.title),
            "page_id": page.get("pageid"),
            "url": self._build_article_url(validated.title, validated.language),
            "summary": page.get("extract", "")[: validated.max_chars],
        }

    async def _search(self, validated: WikipediaFetcherInput) -> dict[str, Any]:
        """Search Wikipedia articles by query."""
        if not validated.query:
            return {"error": "query is required for search"}

        params = {
            "action": "query",
            "list": "search",
            "srsearch": validated.query,
            "srlimit": validated.max_results,
            "format": "json",
            "formatversion": "2",
        }

        async with httpx.AsyncClient(timeout=WIKI_TIMEOUT) as client:
            resp = await client.get(
                _wiki_api_base(validated.language),
                params=params,
                headers={"User-Agent": "Flowmanner/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("query", {}).get("search", [])
        articles = [
            {
                "title": r.get("title", ""),
                "page_id": r.get("pageid"),
                "snippet": BeautifulSoup(r.get("snippet", ""), "html.parser").get_text(),
                "word_count": r.get("wordcount", 0),
                "url": self._build_article_url(r.get("title", ""), validated.language),
            }
            for r in results
        ]

        return {
            "action": "search",
            "query": validated.query,
            "language": validated.language or DEFAULT_LANGUAGE,
            "total_hits": data.get("query", {}).get("searchinfo", {}).get("totalhits", 0),
            "result_count": len(articles),
            "results": articles,
        }

    async def _get_sections(self, validated: WikipediaFetcherInput) -> dict[str, Any]:
        """List all sections of a Wikipedia article."""
        if not validated.title:
            return {"error": "title is required for get_sections"}

        params = {
            "action": "parse",
            "page": validated.title,
            "prop": "sections",
            "format": "json",
            "formatversion": "2",
        }

        async with httpx.AsyncClient(timeout=WIKI_TIMEOUT) as client:
            resp = await client.get(
                _wiki_api_base(validated.language),
                params=params,
                headers={"User-Agent": "Flowmanner/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

        error = data.get("error")
        if error:
            return {
                "action": "get_sections",
                "title": validated.title,
                "error": error.get("info", "Article not found"),
            }

        sections = data.get("parse", {}).get("sections", [])
        return {
            "action": "get_sections",
            "title": validated.title,
            "section_count": len(sections),
            "sections": [
                {
                    "index": s.get("index", ""),
                    "line": s.get("line", ""),
                    "level": int(s.get("level", 2)),
                    "anchor": s.get("anchor", ""),
                }
                for s in sections
            ],
        }

    async def _get_section_content(self, validated: WikipediaFetcherInput) -> dict[str, Any]:
        """Fetch content of a specific section by index."""
        if not validated.title:
            return {"error": "title is required for get_section_content"}
        if validated.section_index is None:
            return {"error": "section_index is required for get_section_content"}

        params = {
            "action": "parse",
            "page": validated.title,
            "section": validated.section_index,
            "prop": "text",
            "format": "json",
            "formatversion": "2",
        }

        async with httpx.AsyncClient(timeout=WIKI_TIMEOUT) as client:
            resp = await client.get(
                _wiki_api_base(validated.language),
                params=params,
                headers={"User-Agent": "Flowmanner/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

        error = data.get("error")
        if error:
            return {
                "action": "get_section_content",
                "title": validated.title,
                "section_index": validated.section_index,
                "error": error.get("info", "Section not found"),
            }

        parse = data.get("parse", {})
        content = self._clean_html(parse.get("text", ""))

        return {
            "action": "get_section_content",
            "title": parse.get("title", validated.title),
            "section_index": validated.section_index,
            "content": content[: validated.max_chars],
            "content_length": len(content),
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(WikipediaFetcherTool())
