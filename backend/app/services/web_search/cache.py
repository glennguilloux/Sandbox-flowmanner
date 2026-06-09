"""
Web Search Cache Service
Multi-layer caching with semantic deduplication
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any

import redis

from .models import CACHE_TTL, ContentType, SearchResponse, SearchResult, SearchType

logger = logging.getLogger(__name__)


class SearchCache:
    """
    Multi-layer caching for web search:
    1. Redis for distributed cache
    2. In-memory LRU for hot queries
    3. Semantic deduplication for similar results
    """

    def __init__(
        self,
        redis_url: str | None = None,
        max_memory_items: int = 1000,
        default_ttl: int = 86400,  # 1 day
    ):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.max_memory_items = max_memory_items
        self.default_ttl = default_ttl

        # In-memory LRU cache
        self._memory_cache: dict[str, Any] = {}
        self._access_times: dict[str, float] = {}

        # Redis client (lazy init)
        self._redis: redis.Redis | None = None
        self._redis_available = False

        # Stats
        self._hits = 0
        self._misses = 0

    def _get_redis(self) -> redis.Redis | None:
        """Lazy Redis connection"""
        if self._redis is None:
            try:
                self._redis = redis.from_url(self.redis_url, decode_responses=True)
                self._redis.ping()
                self._redis_available = True
            except Exception as e:
                logger.warning('Redis not available: %s', e)
                self._redis_available = False
        return self._redis if self._redis_available else None

    def _query_hash(self, query: str, search_type: SearchType) -> str:
        """Generate cache key for query"""
        normalized = query.lower().strip()
        return f"search:{search_type.value}:{hashlib.sha256(normalized.encode()).hexdigest()[:16]}"

    async def get(self, query: str, search_type: SearchType) -> SearchResponse | None:
        """Get cached search response"""
        cache_key = self._query_hash(query, search_type)

        # Try memory cache first
        if cache_key in self._memory_cache:
            self._access_times[cache_key] = time.time()
            self._hits += 1
            logger.debug('Memory cache hit for: %s', query[:50])
            return self._memory_cache[cache_key]

        # Try Redis
        redis_client = self._get_redis()
        if redis_client:
            try:
                cached = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis_client.get(cache_key)
                )
                if cached:
                    response = self._deserialize_response(cached)
                    self._memory_cache[cache_key] = response
                    self._access_times[cache_key] = time.time()
                    self._hits += 1
                    logger.debug('Redis cache hit for: %s', query[:50])
                    return response
            except Exception as e:
                logger.warning('Redis get error: %s', e)

        self._misses += 1
        return None

    async def set(self, response: SearchResponse, ttl: int | None = None) -> bool:
        """Cache search response"""
        cache_key = self._query_hash(response.query, response.search_type)

        # Determine TTL based on content type
        if ttl is None:
            ttl = self._determine_ttl(response)

        # Store in memory cache
        self._evict_if_needed()
        self._memory_cache[cache_key] = response
        self._access_times[cache_key] = time.time()

        # Store in Redis
        redis_client = self._get_redis()
        if redis_client:
            try:
                serialized = self._serialize_response(response)
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis_client.setex(cache_key, ttl, serialized)
                )
                logger.debug('Cached response for: %s', response.query[:50])
            except Exception as e:
                logger.warning('Redis set error: %s', e)

        return True

    def _determine_ttl(self, response: SearchResponse) -> int:
        """Determine TTL based on content type"""
        # Check result domains for content type hints
        for result in response.results[:3]:
            domain = result.domain.lower()

            # News sites - shorter TTL
            if any(news in domain for news in ["reuters", "bbc", "cnn", "nytimes"]):
                return CACHE_TTL[ContentType.NEWS]

            # Research - longer TTL
            if any(research in domain for research in ["arxiv", "scholar", "nature"]):
                return CACHE_TTL[ContentType.RESEARCH]

            # Documentation
            if "docs." in domain or "readthedocs" in domain:
                return CACHE_TTL[ContentType.DOCUMENTATION]

        return self.default_ttl

    def _serialize_response(self, response: SearchResponse) -> str:
        """Serialize response for Redis storage"""
        data = {
            "query": response.query,
            "results": [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "provider": r.provider.value,
                    "rank": r.rank,
                    "score": r.score,
                    "content": r.content,
                    "metadata": r.metadata,
                }
                for r in response.results
            ],
            "provider": response.provider.value,
            "search_type": response.search_type.value,
            "total_results": response.total_results,
            "latency_ms": response.latency_ms,
            "query_hash": response.query_hash,
        }
        return json.dumps(data)

    def _deserialize_response(self, data: str) -> SearchResponse:
        """Deserialize response from Redis"""
        obj = json.loads(data)
        return SearchResponse(
            query=obj["query"],
            results=[
                SearchResult(
                    title=r["title"],
                    url=r["url"],
                    snippet=r["snippet"],
                    provider=r["provider"],
                    rank=r["rank"],
                    score=r["score"],
                    content=r.get("content"),
                    metadata=r.get("metadata", {}),
                )
                for r in obj["results"]
            ],
            provider=obj["provider"],
            search_type=obj["search_type"],
            total_results=obj["total_results"],
            latency_ms=obj["latency_ms"],
            cached=True,
            query_hash=obj.get("query_hash", ""),
        )

    def _evict_if_needed(self):
        """Evict oldest items if cache is full"""
        if len(self._memory_cache) >= self.max_memory_items:
            # Remove oldest 10%
            items_to_remove = self.max_memory_items // 10
            sorted_keys = sorted(
                self._access_times.keys(), key=lambda k: self._access_times[k]
            )

            for key in sorted_keys[:items_to_remove]:
                del self._memory_cache[key]
                del self._access_times[key]

            logger.debug('Evicted %s items from memory cache', items_to_remove)

    async def clear(self):
        """Clear all cached search results (memory + Redis)."""
        self._memory_cache.clear()
        self._access_times.clear()
        self._hits = 0
        self._misses = 0

        redis_client = self._get_redis()
        if redis_client:
            try:
                keys = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis_client.keys("search:*")
                )
                if keys:
                    await asyncio.get_event_loop().run_in_executor(
                        None, lambda: redis_client.delete(*keys)
                    )
                logger.info("Cleared %d Redis cache keys", len(keys) if keys else 0)
            except Exception as e:
                logger.warning('Redis clear error: %s', e)

    async def invalidate(self, query: str, search_type: SearchType):
        """Invalidate cached response"""
        cache_key = self._query_hash(query, search_type)

        # Remove from memory
        self._memory_cache.pop(cache_key, None)
        self._access_times.pop(cache_key, None)

        # Remove from Redis
        redis_client = self._get_redis()
        if redis_client:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis_client.delete(cache_key)
                )
            except Exception as e:
                logger.warning('Redis delete error: %s', e)

    @property
    def stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 3),
            "memory_items": len(self._memory_cache),
            "redis_available": self._redis_available,
        }


class ResultDeduplicator:
    """
    Semantic deduplication for search results
    Removes near-duplicate results across providers
    """

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold

    def deduplicate(
        self, results: list[SearchResult], max_results: int = 10
    ) -> list[SearchResult]:
        """
        Remove duplicate/near-duplicate results
        """
        if not results:
            return results

        unique_results = []
        seen_hashes = set()

        # Sort by score first
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)

        for result in sorted_results:
            # Create content hash
            content_hash = self._content_hash(result)

            # Check for duplicates
            is_duplicate = False
            for seen_hash in seen_hashes:
                if (
                    self._similarity(content_hash, seen_hash)
                    >= self.similarity_threshold
                ):
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_results.append(result)
                seen_hashes.add(content_hash)

                if len(unique_results) >= max_results:
                    break

        return unique_results

    def _content_hash(self, result: SearchResult) -> str:
        """Create hash of result content"""
        # Normalize URL
        url = result.url.lower().rstrip("/")

        # Normalize title
        title = result.title.lower().strip()

        # Create hash
        return hashlib.sha256(f"{url}:{title}".encode()).hexdigest()[:16]

    def _similarity(self, hash1: str, hash2: str) -> float:
        """Calculate similarity between two hashes"""
        # Simple hamming distance on hex strings
        if hash1 == hash2:
            return 1.0

        # Count matching characters
        matches = sum(c1 == c2 for c1, c2 in zip(hash1, hash2, strict=False))
        return matches / max(len(hash1), len(hash2))
