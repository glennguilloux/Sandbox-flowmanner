"""
Research & Knowledge Retrieval Tools — Global News Aggregator.

global_news_aggregator → Fetch recent top headlines and search news articles
    from around the world via NewsAPI.org.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import (
    BaseTool,
    ToolInput,
    ToolMetadata,
    ToolResult,
    is_placeholder,
    register_tool,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

NEWS_API_KEY = os.getenv("NEWS_API_KEY", os.getenv("NEWSAPI_KEY", ""))
NEWS_API_BASE = "https://newsapi.org/v2"
NEWS_TIMEOUT = int(os.getenv("NEWS_TIMEOUT", "30"))
NEWS_DEFAULT_COUNTRY = os.getenv("NEWS_DEFAULT_COUNTRY", "us")

# Supported countries and categories for the /top-headlines endpoint
_SUPPORTED_COUNTRIES = {
    "ae",
    "ar",
    "at",
    "au",
    "be",
    "bg",
    "br",
    "ca",
    "ch",
    "cn",
    "co",
    "cu",
    "cz",
    "de",
    "eg",
    "fr",
    "gb",
    "gr",
    "hk",
    "hu",
    "id",
    "ie",
    "il",
    "in",
    "it",
    "jp",
    "kr",
    "lt",
    "lv",
    "ma",
    "mx",
    "my",
    "ng",
    "nl",
    "no",
    "nz",
    "ph",
    "pl",
    "pt",
    "ro",
    "rs",
    "ru",
    "sa",
    "se",
    "sg",
    "si",
    "sk",
    "th",
    "tr",
    "tw",
    "ua",
    "us",
    "ve",
    "za",
}

_SUPPORTED_CATEGORIES = {
    "business",
    "entertainment",
    "general",
    "health",
    "science",
    "sports",
    "technology",
}

# ── Helpers ───────────────────────────────────────────────────────────


# ── Input ─────────────────────────────────────────────────────────────

NEWS_ACTIONS = (
    "top_headlines",
    "search",
    "sources",
)


class GlobalNewsAggregatorInput(ToolInput):
    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(NEWS_ACTIONS)}",
    )
    query: str = Field(
        ...,
        description="Search query keywords or phrases (for 'search' action)",
    )
    country: str | None = Field(
        None,
        description=f"Country code for headlines (e.g., 'us', 'gb', 'de'). Default: {NEWS_DEFAULT_COUNTRY}",
    )
    category: str | None = Field(
        None,
        description="News category: 'business', 'entertainment', 'general', 'health', 'science', 'sports', 'technology'",
    )
    sources: list[str] | None = Field(
        None,
        description="News source IDs (e.g., ['bbc-news', 'cnn']). Overrides country/category.",
    )
    max_results: int = Field(
        20,
        ge=1,
        le=100,
        description="Maximum number of articles to return",
    )
    language: str | None = Field(
        None,
        description="Language code for articles (e.g., 'en', 'fr', 'de') — search action only",
    )
    sort_by: str = Field(
        "publishedAt",
        description="Sort order for search: 'relevancy', 'popularity', or 'publishedAt'",
    )
    from_date: str | None = Field(
        None,
        description="Start date for articles (YYYY-MM-DD). Default: 30 days ago.",
    )
    to_date: str | None = Field(
        None,
        description="End date for articles (YYYY-MM-DD). Default: today.",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class GlobalNewsAggregatorTool(BaseTool):
    """Fetch top headlines and search news from NewsAPI.org."""

    def __init__(self):
        metadata = ToolMetadata(
            visibility="opt_in",
            tool_id="global_news_aggregator",
            name="Global News Aggregator",
            description=(
                "Fetch recent top headlines and search news articles from around "
                "the world via NewsAPI.org. Supports country filtering, categories, "
                "and keyword search with date range support. "
                "Requires NEWS_API_KEY env var."
            ),
            category="research-knowledge-retrieval",
            input_schema=GlobalNewsAggregatorInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "articles": {"type": "array"},
                    "total_results": {"type": "integer"},
                    "source": {"type": "string"},
                },
            },
            tags=["news", "headlines", "current-events", "media", "research"],
            requires_auth=True,
            timeout_seconds=NEWS_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = GlobalNewsAggregatorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if validated.action not in NEWS_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(NEWS_ACTIONS)}",
            )

        if not NEWS_API_KEY:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="NewsAPI not configured. Set NEWS_API_KEY env var.",
            )

        if is_placeholder(NEWS_API_KEY):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="NewsAPI not configured. Replace placeholder value for NEWS_API_KEY with a real API key.",
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("News API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"News API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.warning("global_news_aggregator failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(self, validated: GlobalNewsAggregatorInput) -> dict[str, Any]:
        if validated.action == "top_headlines":
            return await self._top_headlines(validated)
        elif validated.action == "search":
            return await self._search_news(validated)
        elif validated.action == "sources":
            return await self._get_sources(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}"}

    # ── Helpers ──────────────────────────────────────────────────

    def _summarize_article(self, article: dict) -> dict[str, Any]:
        """Extract key fields from a news article."""
        source = article.get("source", {})
        return {
            "title": article.get("title", ""),
            "description": article.get("description", ""),
            "url": article.get("url", ""),
            "url_to_image": article.get("urlToImage", ""),
            "published_at": article.get("publishedAt", ""),
            "source_name": source.get("name", ""),
            "author": article.get("author", ""),
            "content": (article.get("content", "") or "")[:500],
        }

    def _get_date_range(self, validated: GlobalNewsAggregatorInput) -> dict[str, str]:
        """Resolve from_date and to_date with defaults."""
        to_date = validated.to_date or date.today().isoformat()
        from_date = validated.from_date or (date.today() - timedelta(days=30)).isoformat()
        return {"from": from_date, "to": to_date}

    # ── Action handlers ──────────────────────────────────────────

    async def _top_headlines(self, validated: GlobalNewsAggregatorInput) -> dict[str, Any]:
        """Fetch top headlines."""
        params: dict[str, Any] = {
            "apiKey": NEWS_API_KEY,
            "pageSize": validated.max_results,
        }

        if validated.sources:
            params["sources"] = ",".join(validated.sources)
        else:
            params["country"] = validated.country or NEWS_DEFAULT_COUNTRY
            if validated.category:
                if validated.category not in _SUPPORTED_CATEGORIES:
                    return {
                        "error": f"Invalid category: '{validated.category}'. "
                        f"Use: {', '.join(sorted(_SUPPORTED_CATEGORIES))}",
                    }
                params["category"] = validated.category

        async with httpx.AsyncClient(timeout=NEWS_TIMEOUT) as client:
            resp = await client.get(f"{NEWS_API_BASE}/top-headlines", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "ok":
            return {
                "action": "top_headlines",
                "error": data.get("message", "Unknown error"),
            }

        articles = [self._summarize_article(a) for a in data.get("articles", [])]

        return {
            "action": "top_headlines",
            "country": validated.country or NEWS_DEFAULT_COUNTRY,
            "category": validated.category,
            "total_results": data.get("totalResults", len(articles)),
            "article_count": len(articles),
            "articles": articles,
        }

    async def _search_news(self, validated: GlobalNewsAggregatorInput) -> dict[str, Any]:
        """Search news articles by query."""
        if not validated.query:
            return {"error": "query is required for search action"}

        if validated.sort_by not in ("relevancy", "popularity", "publishedAt"):
            return {
                "error": f"Invalid sort_by: '{validated.sort_by}'. Use: 'relevancy', 'popularity', or 'publishedAt'",
            }

        dates = self._get_date_range(validated)
        params: dict[str, Any] = {
            "apiKey": NEWS_API_KEY,
            "q": validated.query,
            "pageSize": validated.max_results,
            "sortBy": validated.sort_by,
            "from": dates["from"],
            "to": dates["to"],
        }

        if validated.language:
            params["language"] = validated.language
        if validated.sources:
            params["sources"] = ",".join(validated.sources)

        async with httpx.AsyncClient(timeout=NEWS_TIMEOUT) as client:
            resp = await client.get(f"{NEWS_API_BASE}/everything", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "ok":
            return {
                "action": "search",
                "error": data.get("message", "Unknown error"),
            }

        articles = [self._summarize_article(a) for a in data.get("articles", [])]

        return {
            "action": "search",
            "query": validated.query,
            "total_results": data.get("totalResults", len(articles)),
            "article_count": len(articles),
            "from_date": dates["from"],
            "to_date": dates["to"],
            "sort_by": validated.sort_by,
            "articles": articles,
        }

    async def _get_sources(self) -> dict[str, Any]:
        """List available news sources."""
        params: dict[str, Any] = {
            "apiKey": NEWS_API_KEY,
        }

        async with httpx.AsyncClient(timeout=NEWS_TIMEOUT) as client:
            resp = await client.get(f"{NEWS_API_BASE}/top-headlines/sources", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "ok":
            return {
                "action": "sources",
                "error": data.get("message", "Unknown error"),
            }

        sources = data.get("sources", [])
        return {
            "action": "sources",
            "source_count": len(sources),
            "sources": [
                {
                    "id": s.get("id", ""),
                    "name": s.get("name", ""),
                    "description": s.get("description", ""),
                    "category": s.get("category", ""),
                    "language": s.get("language", ""),
                    "country": s.get("country", ""),
                }
                for s in sources
            ],
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(GlobalNewsAggregatorTool())
