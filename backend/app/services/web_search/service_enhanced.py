"""
Enhanced Web Search Service with AI-powered features
Integrates query understanding, result reranking, and intelligent caching
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

from .cache import SearchCache
from .models import ProviderConfig, SearchConfig
from .models import SearchProvider as SearchProviderEnum
from .providers import SearchProvider, create_provider
from .query_understanding import QueryUnderstanding, QueryUnderstandingService
from .result_reranking import ResultReranker

logger = logging.getLogger(__name__)


@dataclass
class EnhancedSearchResult:
    """Search result with AI enhancements"""

    # Original result fields
    title: str
    url: str
    snippet: str
    domain: str
    provider: str
    rank: int
    score: float

    # AI-enhanced fields
    relevance_score: float = 0.0
    authority_score: float = 0.0
    freshness_score: float = 0.0
    final_score: float = 0.0
    rerank_reasons: list[str] = None

    # Query understanding
    query_intent: str = "informational"
    query_entities: list[dict] = None
    expanded_queries: list[str] = None

    def __post_init__(self):
        if self.rerank_reasons is None:
            self.rerank_reasons = []
        if self.query_entities is None:
            self.query_entities = []
        if self.expanded_queries is None:
            self.expanded_queries = []


class EnhancedWebSearchService:
    """Web search service with AI-powered enhancements"""

    def __init__(self, config: SearchConfig | None = None):
        self.config = config or SearchConfig()
        self.providers: dict[str, SearchProvider] = {}
        self.cache = SearchCache()
        self.query_understanding = QueryUnderstandingService()
        self.result_reranker = ResultReranker()

        # Initialize providers
        self._init_providers()

    def _init_providers(self):
        """Initialize search providers"""
        # DuckDuckGo (free, no API key required)
        if self.config.duckduckgo_enabled:
            try:
                ddg_config = ProviderConfig(
                    provider=SearchProviderEnum.DUCKDUCKGO,
                    enabled=True,
                    priority=3,
                )
                self.providers["duckduckgo"] = create_provider(ddg_config)
                logger.info("Initialized provider: duckduckgo")
            except Exception as e:
                logger.warning("Failed to init duckduckgo: %s", e)

        # SearXNG (self-hosted)
        if self.config.searxng_enabled and self.config.searxng_url:
            try:
                searxng_config = ProviderConfig(
                    provider=SearchProviderEnum.SEARXNG,
                    enabled=True,
                    priority=1,
                    base_url=self.config.searxng_url,
                )
                self.providers["searxng"] = create_provider(searxng_config)
                logger.info("Initialized provider: searxng")
            except Exception as e:
                logger.warning("Failed to init searxng: %s", e)

    async def search(
        self,
        query: str,
        max_results: int = 10,
        providers: list[str] | None = None,
        use_query_understanding: bool = True,
        use_reranking: bool = True,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Perform enhanced web search with AI features"""
        start_time = time.time()

        # Step 1: Query Understanding
        query_understanding = None
        if use_query_understanding:
            try:
                query_understanding = await self.query_understanding.understand_query(
                    query
                )
                logger.info(
                    "Query intent: %s, complexity: %.2f",
                    query_understanding.intent.value,
                    query_understanding.complexity_score,
                )
            except Exception as e:
                logger.warning("Query understanding failed: %s", e)

        # Step 2: Check Cache
        from .models import SearchType
        from .query_understanding import SearchIntent

        search_type = SearchType.QUICK
        if query_understanding:
            if query_understanding.intent in (
                SearchIntent.RESEARCH,
                SearchIntent.COMPARISON,
            ):
                search_type = SearchType.DEEP
        if use_cache:
            cached = await self.cache.get(query, search_type)
            if cached:
                logger.info("Cache hit for query: %s", query)
                return self._format_response(
                    query=query,
                    results=cached,
                    latency_ms=(time.time() - start_time) * 1000,
                    cached=True,
                    query_understanding=query_understanding,
                )

        # Step 3: Execute Search
        search_providers = providers or self._select_providers(query_understanding)
        all_results = []
        providers_used = []

        for provider_name in search_providers:
            if provider_name not in self.providers:
                continue

            provider = self.providers[provider_name]
            try:
                search_resp = await provider.search(query, search_type, max_results)
                if search_resp and hasattr(search_resp, "results"):
                    results = search_resp.results
                elif isinstance(search_resp, list):
                    results = search_resp
                else:
                    results = []
                all_results.extend(results)
                providers_used.append(provider_name)
                logger.info(
                    "Provider %s returned %s results", provider_name, len(results)
                )
            except Exception as e:
                logger.error("Provider %s error: %s", provider_name, e)

        # Step 4: Deduplicate and Merge
        deduped_results = self._deduplicate_results(all_results)

        # Step 5: Rerank Results
        if use_reranking and deduped_results:
            try:
                intent = (
                    query_understanding.intent.value
                    if query_understanding
                    else "informational"
                )
                time_sensitive = (
                    query_understanding.time_sensitive if query_understanding else False
                )

                reranked = await self.result_reranker.rerank_results(
                    results=deduped_results,
                    query=query,
                    intent=intent,
                    time_sensitive=time_sensitive,
                )

                # Convert back to dict format
                deduped_results = [
                    {
                        "title": r.title,
                        "url": r.url,
                        "snippet": r.snippet,
                        "domain": r.domain,
                        "provider": r.provider,
                        "rank": i + 1,
                        "score": r.final_score,
                        "relevance_score": r.relevance_score,
                        "authority_score": r.authority_score,
                        "freshness_score": r.freshness_score,
                        "rerank_reasons": r.rerank_reasons,
                    }
                    for i, r in enumerate(reranked[:max_results])
                ]
            except Exception as e:
                logger.warning("Reranking failed: %s", e)

        # Step 6: Cache Results
        if use_cache and deduped_results:
            from .models import SearchProvider, SearchResponse

            cache_resp = SearchResponse(
                query=query,
                results=deduped_results,
                provider=SearchProvider.SEARCH,
                search_type=search_type,
                total_results=len(deduped_results),
                latency_ms=(time.time() - start_time) * 1000,
            )
            await self.cache.set(cache_resp, ttl=self.config.cache_ttl)

        # Step 7: Format Response
        latency_ms = (time.time() - start_time) * 1000

        return self._format_response(
            query=query,
            results=deduped_results[:max_results],
            latency_ms=latency_ms,
            cached=False,
            providers_used=providers_used,
            query_understanding=query_understanding,
        )

    def _select_providers(
        self, query_understanding: QueryUnderstanding | None
    ) -> list[str]:
        """Select best providers based on query understanding"""
        if query_understanding:
            return query_understanding.suggested_providers
        return list(self.providers.keys())

    def _generate_cache_key(
        self, query: str, max_results: int, providers: list[str] | None
    ) -> str:
        """Generate cache key for search"""
        provider_str = ",".join(sorted(providers or []))
        return f"search:{query}:{max_results}:{provider_str}"

    def _deduplicate_results(self, results: list[dict]) -> list[dict]:
        """Remove duplicate results based on URL"""
        seen_urls = set()
        unique_results = []

        for result in results:
            url = (
                result.get("url", "")
                if isinstance(result, dict)
                else getattr(result, "url", "") or ""
            )
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)

        return unique_results

    def _format_response(
        self,
        query: str,
        results: list[dict],
        latency_ms: float,
        cached: bool,
        providers_used: list[str],
        query_understanding: QueryUnderstanding | None,
    ) -> dict[str, Any]:
        """Format the search response"""
        response = {
            "query": query,
            "results": results,
            "total_results": len(results),
            "latency_ms": latency_ms,
            "cached": cached,
            "providers_used": providers_used,
        }

        # Add query understanding metadata
        if query_understanding:
            response["query_analysis"] = {
                "intent": query_understanding.intent.value,
                "intent_confidence": query_understanding.intent_confidence,
                "complexity_score": query_understanding.complexity_score,
                "time_sensitive": query_understanding.time_sensitive,
                "location_sensitive": query_understanding.location_sensitive,
                "keywords": query_understanding.keywords,
                "entities": [
                    {"text": e.text, "type": e.entity_type, "confidence": e.confidence}
                    for e in query_understanding.entities
                ],
                "expanded_queries": query_understanding.expanded_queries,
            }

        return response

    async def health_check(self) -> dict[str, Any]:
        """Check service health"""
        return {
            "status": "healthy",
            "providers": dict.fromkeys(self.providers.keys(), "available"),
            "cache": "connected" if self.cache else "disabled",
        }

    def get_providers(self) -> list[dict[str, Any]]:
        """Get list of available providers"""
        return [
            {"name": name, "type": provider.__class__.__name__, "enabled": True}
            for name, provider in self.providers.items()
        ]
