"""
Web Search Providers - Abstraction Layer
Supports SearXNG, Tavily, Exa, and DuckDuckGo
"""

import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime

import httpx

from .models import (
    ProviderConfig,
    SearchProvider,
    SearchResponse,
    SearchResult,
    SearchType,
)

logger = logging.getLogger(__name__)


class BaseSearchProvider(ABC):
    """Abstract base class for search providers"""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._request_count = 0
        self._error_count = 0

    @property
    @abstractmethod
    def provider_name(self) -> SearchProvider:
        pass

    @abstractmethod
    async def search(self, query: str, search_type: SearchType, max_results: int) -> SearchResponse:
        pass

    @property
    def is_available(self) -> bool:
        return self.config.enabled and (
            self.config.api_key is not None or self.provider_name in [SearchProvider.SEARXNG, SearchProvider.DUCKDUCKGO]
        )

    def _create_result(self, **kwargs) -> SearchResult:
        return SearchResult(provider=self.provider_name, **kwargs)


class SearXNGProvider(BaseSearchProvider):
    """SearXNG - Self-hosted metasearch engine (FREE)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or os.getenv("SEARXNG_URL", "http://localhost:55510")

    @property
    def provider_name(self) -> SearchProvider:
        return SearchProvider.SEARXNG

    async def search(self, query: str, search_type: SearchType, max_results: int) -> SearchResponse:
        start_time = time.time()
        results = []
        error = None

        try:
            # Map search type to SearXNG categories
            categories = self._get_categories(search_type)

            params: dict[str, str | int] = {
                "q": query,
                "format": "json",
                "engines": "google,bing,duckduckgo",
                "max_results": max_results,
            }

            if categories:
                params["categories"] = categories

            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.get(f"{self.base_url}/search", params=params)
                response.raise_for_status()
                data = response.json()

            for i, item in enumerate(data.get("results", [])[:max_results]):
                results.append(
                    self._create_result(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        rank=i + 1,
                        score=1.0 - (i * 0.1),
                        published_date=self._parse_date(item.get("publishedDate")),
                        metadata={
                            "engine": item.get("engine"),
                            "category": item.get("category"),
                        },
                    )
                )

        except Exception as e:
            logger.error("SearXNG search error: %s", e)
            error = str(e)
            self._error_count += 1

        latency = (time.time() - start_time) * 1000
        self._request_count += 1

        return SearchResponse(
            query=query,
            results=results,
            provider=self.provider_name,
            search_type=search_type,
            total_results=len(results),
            latency_ms=latency,
            error=error,
        )

    def _get_categories(self, search_type: SearchType) -> str | None:
        mapping = {
            SearchType.NEWS: "news",
            SearchType.CODE: "it",
            SearchType.RESEARCH: "science",
        }
        return mapping.get(search_type)

    def _parse_date(self, date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            logger.debug("Failed to parse date from search result: %s", date_str)
            return None


class TavilyProvider(BaseSearchProvider):
    """Tavily - AI-optimized search API"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = "https://api.tavily.com"

    @property
    def provider_name(self) -> SearchProvider:
        return SearchProvider.TAVILY

    async def search(self, query: str, search_type: SearchType, max_results: int) -> SearchResponse:
        start_time = time.time()
        results = []
        error = None

        if not self.config.api_key:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.provider_name,
                search_type=search_type,
                total_results=0,
                latency_ms=0,
                error="API key not configured",
            )

        try:
            # Tavily search depth based on type
            search_depth = "advanced" if search_type == SearchType.DEEP else "basic"

            payload = {
                "api_key": self.config.api_key,
                "query": query,
                "search_depth": search_depth,
                "max_results": max_results,
                "include_raw_content": False,
                "include_images": False,
            }

            if search_type == SearchType.NEWS:
                payload["topic"] = "news"

            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/search", json=payload)
                response.raise_for_status()
                data = response.json()

            for i, item in enumerate(data.get("results", [])):
                results.append(
                    self._create_result(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        rank=i + 1,
                        score=item.get("score", 1.0 - (i * 0.1)),
                        metadata={"tavily_score": item.get("score")},
                    )
                )

        except Exception as e:
            logger.error("Tavily search error: %s", e)
            error = str(e)
            self._error_count += 1

        latency = (time.time() - start_time) * 1000
        self._request_count += 1

        return SearchResponse(
            query=query,
            results=results,
            provider=self.provider_name,
            search_type=search_type,
            total_results=len(results),
            latency_ms=latency,
            error=error,
        )


class ExaProvider(BaseSearchProvider):
    """Exa - Neural search API for high-quality results"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = "https://api.exa.ai"

    @property
    def provider_name(self) -> SearchProvider:
        return SearchProvider.EXA

    async def search(self, query: str, search_type: SearchType, max_results: int) -> SearchResponse:
        start_time = time.time()
        results = []
        error = None

        if not self.config.api_key:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.provider_name,
                search_type=search_type,
                total_results=0,
                latency_ms=0,
                error="API key not configured",
            )

        try:
            # Exa type mapping
            use_autoprompt = True
            type_ = "auto"

            if search_type == SearchType.RESEARCH or search_type == SearchType.NEWS:
                type_ = "keyword"

            payload = {
                "query": query,
                "type": type_,
                "numResults": max_results,
                "useAutoprompt": use_autoprompt,
                "contents": {"text": {"maxCharacters": 500}},
            }

            headers = {
                "x-api-key": self.config.api_key,
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/search", json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            for i, item in enumerate(data.get("results", [])):
                results.append(
                    self._create_result(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("text", "")[:500] if item.get("text") else "",
                        rank=i + 1,
                        score=item.get("score", 1.0 - (i * 0.1)),
                        published_date=self._parse_exa_date(item.get("publishedDate")),
                        content=item.get("text"),
                        metadata={
                            "exa_score": item.get("score"),
                            "author": item.get("author"),
                        },
                    )
                )

        except Exception as e:
            logger.error("Exa search error: %s", e)
            error = str(e)
            self._error_count += 1

        latency = (time.time() - start_time) * 1000
        self._request_count += 1

        return SearchResponse(
            query=query,
            results=results,
            provider=self.provider_name,
            search_type=search_type,
            total_results=len(results),
            latency_ms=latency,
            error=error,
        )

    def _parse_exa_date(self, date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            logger.debug("Failed to parse Exa date: %s", date_str)
            return None


class DuckDuckGoProvider(BaseSearchProvider):
    """DuckDuckGo - Free search via HTML scraping (fallback)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = "https://html.duckduckgo.com/html/"

    @property
    def provider_name(self) -> SearchProvider:
        return SearchProvider.DUCKDUCKGO

    async def search(self, query: str, search_type: SearchType, max_results: int) -> SearchResponse:
        start_time = time.time()
        results = []
        error = None

        try:
            # Use DuckDuckGo HTML endpoint
            params = {"q": query}

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.get(self.base_url, params=params, headers=headers)
                response.raise_for_status()
                html = response.text

            # Parse HTML results
            results = self._parse_html_results(html, max_results)

        except Exception as e:
            logger.error("DuckDuckGo search error: %s", e)
            error = str(e)
            self._error_count += 1

        latency = (time.time() - start_time) * 1000
        self._request_count += 1

        return SearchResponse(
            query=query,
            results=results,
            provider=self.provider_name,
            search_type=search_type,
            total_results=len(results),
            latency_ms=latency,
            error=error,
        )

    def _parse_html_results(self, html: str, max_results: int) -> list[SearchResult]:
        """Parse DuckDuckGo HTML response"""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        results = []

        for i, result_div in enumerate(soup.select(".result")[:max_results]):
            title_elem = result_div.select_one(".result__a")
            snippet_elem = result_div.select_one(".result__snippet")

            if title_elem:
                url = str(title_elem.get("href", ""))
                # Extract actual URL from redirect
                if "uddg=" in url:
                    from urllib.parse import unquote

                    url = unquote(url.split("uddg=")[-1].split("&")[0])

                results.append(
                    self._create_result(
                        title=title_elem.get_text(strip=True),
                        url=url,
                        snippet=(snippet_elem.get_text(strip=True) if snippet_elem else ""),
                        rank=i + 1,
                        score=1.0 - (i * 0.1),
                    )
                )

        return results


def create_provider(config: ProviderConfig) -> BaseSearchProvider:
    """Factory function to create provider instances"""
    providers = {
        SearchProvider.SEARXNG: SearXNGProvider,
        SearchProvider.TAVILY: TavilyProvider,
        SearchProvider.EXA: ExaProvider,
        SearchProvider.DUCKDUCKGO: DuckDuckGoProvider,
    }

    provider_class = providers.get(config.provider)
    if not provider_class:
        raise ValueError(f"Unknown provider: {config.provider}")

    return provider_class(config)  # type: ignore[abstract]
