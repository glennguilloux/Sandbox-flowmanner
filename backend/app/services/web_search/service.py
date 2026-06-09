"""
Web Search Service - Main Orchestrator
Coordinates providers, extraction, and caching
"""

import asyncio
import logging
import os
import time
from typing import Any

from .cache import ResultDeduplicator, SearchCache
from .content_extractor import ContentExtractor
from .models import (
    PROVIDER_MATRIX,
    TRUSTED_DOMAINS,
    ExtractionDepth,
    ProviderConfig,
    SearchProvider,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchType,
)
from .providers import BaseSearchProvider, create_provider

logger = logging.getLogger(__name__)


class WebSearchService:
    """
    Main web search service with:
    - Multi-provider aggregation
    - Smart content extraction
    - Multi-layer caching
    - Result deduplication
    - Quality scoring
    """

    def __init__(
        self,
        provider_configs: dict[SearchProvider, ProviderConfig] | None = None,
        enable_cache: bool = True,
        enable_extraction: bool = True,
    ):
        self.provider_configs = provider_configs or self._default_configs()
        self.providers: dict[SearchProvider, BaseSearchProvider] = {}
        self.cache = SearchCache() if enable_cache else None
        self.extractor = ContentExtractor() if enable_extraction else None
        self.deduplicator = ResultDeduplicator()

        # Stats
        self._search_count = 0
        self._total_latency = 0.0
        self._provider_stats: dict[SearchProvider, dict] = {}

        # Initialize providers
        self._init_providers()

    def _default_configs(self) -> dict[SearchProvider, ProviderConfig]:
        """Default provider configurations"""
        return {
            SearchProvider.SEARXNG: ProviderConfig(
                provider=SearchProvider.SEARXNG,
                base_url=os.getenv("SEARXNG_URL", "http://localhost:55510"),
                enabled=True,
                priority=0,
            ),
            SearchProvider.TAVILY: ProviderConfig(
                provider=SearchProvider.TAVILY,
                api_key=os.getenv("TAVILY_API_KEY"),
                enabled=bool(os.getenv("TAVILY_API_KEY")),
                priority=1,
            ),
            SearchProvider.EXA: ProviderConfig(
                provider=SearchProvider.EXA,
                api_key=os.getenv("EXA_API_KEY"),
                enabled=bool(os.getenv("EXA_API_KEY")),
                priority=2,
            ),
            SearchProvider.DUCKDUCKGO: ProviderConfig(
                provider=SearchProvider.DUCKDUCKGO, enabled=True, priority=3
            ),
        }

    def _init_providers(self):
        """Initialize available providers"""
        for provider_type, config in self.provider_configs.items():
            if config.enabled:
                try:
                    self.providers[provider_type] = create_provider(config)
                    self._provider_stats[provider_type] = {
                        "requests": 0,
                        "errors": 0,
                        "total_latency": 0.0,
                    }
                    logger.info("Initialized provider: %s", provider_type.value)
                except Exception as e:
                    logger.warning("Failed to init provider %s: %s", provider_type, e)

    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        Execute search with caching and aggregation
        """
        start_time = time.time()
        self._search_count += 1

        # Check cache first
        if self.cache and request.use_cache:
            cached = await self.cache.get(request.query, request.search_type)
            if cached:
                logger.info("Cache hit for query: %s", request.query[:50])
                return cached

        # Determine providers to use
        providers = request.providers or self._select_providers(request.search_type)

        # Execute searches
        if len(providers) == 1:
            # Single provider
            response = await self._search_single(request, providers[0])
        else:
            # Multi-provider aggregation
            response = await self._search_aggregated(request, providers)

        # Deduplicate results
        if response.results:
            response.results = self.deduplicator.deduplicate(
                response.results, request.max_results
            )
            response.total_results = len(response.results)

        # Score results
        self._score_results(response.results)

        # Extract content if requested
        if request.extract_content and response.results and self.extractor:
            await self._extract_content(response.results, request.extraction_depth)

        # Cache response
        if self.cache and request.use_cache:
            await self.cache.set(response)

        # Update stats
        latency = (time.time() - start_time) * 1000
        response.latency_ms = latency
        self._total_latency += latency

        return response

    def _select_providers(self, search_type: SearchType) -> list[SearchProvider]:
        """Select best providers for search type"""
        preferred = PROVIDER_MATRIX.get(search_type, [SearchProvider.SEARXNG])

        # Filter to available providers
        available = []
        for provider in preferred:
            if provider in self.providers and self.providers[provider].is_available:
                available.append(provider)

        # Fallback to any available
        if not available:
            available = [p for p in self.providers if self.providers[p].is_available]

        return available[:2]  # Max 2 providers for aggregation

    async def _search_single(
        self, request: SearchRequest, provider: SearchProvider
    ) -> SearchResponse:
        """Execute search with single provider"""
        provider_instance = self.providers.get(provider)
        if not provider_instance:
            return SearchResponse(
                query=request.query,
                results=[],
                provider=provider,
                search_type=request.search_type,
                total_results=0,
                latency_ms=0,
                error=f"Provider {provider.value} not available",
            )

        response = await provider_instance.search(
            request.query, request.search_type, request.max_results
        )

        self._update_provider_stats(provider, response.latency_ms, bool(response.error))

        return response

    async def _search_aggregated(
        self, request: SearchRequest, providers: list[SearchProvider]
    ) -> SearchResponse:
        """Execute parallel search across multiple providers"""
        tasks = []
        for provider in providers:
            if provider in self.providers:
                tasks.append(
                    self.providers[provider].search(
                        request.query, request.search_type, request.max_results
                    )
                )

        if not tasks:
            return SearchResponse(
                query=request.query,
                results=[],
                provider=providers[0] if providers else SearchProvider.SEARXNG,
                search_type=request.search_type,
                total_results=0,
                latency_ms=0,
                error="No providers available",
            )

        # Execute in parallel
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        all_results = []
        primary_provider = None
        errors = []

        for _i, response in enumerate(responses):
            if isinstance(response, Exception):
                errors.append(str(response))
                continue

            if isinstance(response, SearchResponse):
                if response.error:
                    errors.append(response.error)
                    continue

                if not primary_provider:
                    primary_provider = response.provider

                all_results.extend(response.results)

                self._update_provider_stats(
                    response.provider, response.latency_ms, False
                )

        return SearchResponse(
            query=request.query,
            results=all_results,
            provider=primary_provider or providers[0],
            search_type=request.search_type,
            total_results=len(all_results),
            latency_ms=0,
            error="; ".join(errors) if errors and not all_results else None,
        )

    def _score_results(self, results: list[SearchResult]):
        """Apply quality scoring to results"""
        for result in results:
            score = result.score

            # Boost trusted domains
            domain = result.domain.lower()
            if any(trusted in domain for trusted in TRUSTED_DOMAINS):
                score += 0.2

            # Boost by rank
            score += max(0, (10 - result.rank) * 0.05)

            # Boost if has content
            if result.content:
                score += 0.1

            # Normalize
            result.score = min(1.0, max(0.0, score))

    async def _extract_content(
        self, results: list[SearchResult], depth: ExtractionDepth
    ):
        """Extract content for top results"""
        # Extract for top 3 results
        for result in results[:3]:
            if not result.content:
                try:
                    extracted = await self.extractor.extract(result.url, depth)
                    if extracted.success:
                        result.extracted_content = extracted.content
                        result.content = extracted.content
                except Exception as e:
                    logger.warning(
                        "Content extraction failed for %s: %s", result.url, e
                    )

    def _update_provider_stats(
        self, provider: SearchProvider, latency: float, error: bool
    ):
        """Update provider statistics"""
        if provider in self._provider_stats:
            self._provider_stats[provider]["requests"] += 1
            self._provider_stats[provider]["total_latency"] += latency
            if error:
                self._provider_stats[provider]["errors"] += 1

    @property
    def stats(self) -> dict[str, Any]:
        """Get service statistics"""
        avg_latency = (
            self._total_latency / self._search_count if self._search_count > 0 else 0
        )

        provider_stats = {}
        for provider, stats in self._provider_stats.items():
            avg = (
                stats["total_latency"] / stats["requests"]
                if stats["requests"] > 0
                else 0
            )
            provider_stats[provider.value] = {
                "requests": stats["requests"],
                "errors": stats["errors"],
                "avg_latency_ms": round(avg, 2),
            }

        return {
            "total_searches": self._search_count,
            "avg_latency_ms": round(avg_latency, 2),
            "providers": provider_stats,
            "cache": self.cache.stats if self.cache else None,
        }

    async def health_check(self) -> dict[str, Any]:
        """Check health of all providers"""
        health = {"status": "healthy", "providers": {}, "cache": None}

        for provider_type, provider in self.providers.items():
            health["providers"][provider_type.value] = {
                "available": provider.is_available,
                "enabled": self.provider_configs[provider_type].enabled,
            }

        if self.cache:
            health["cache"] = self.cache.stats

        # Determine overall status
        available_count = sum(1 for p in health["providers"].values() if p["available"])
        if available_count == 0:
            health["status"] = "degraded"

        return health


# Singleton instance
_search_service: WebSearchService | None = None


def get_search_service() -> WebSearchService:
    """Get or create singleton search service"""
    global _search_service
    if _search_service is None:
        _search_service = WebSearchService()
    return _search_service
