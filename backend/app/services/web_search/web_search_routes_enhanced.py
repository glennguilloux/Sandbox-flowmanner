"""
Enhanced Web Search API Routes with AI features
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .models import SearchConfig
from .service_enhanced import EnhancedWebSearchService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/web-search", tags=["Web Search"])

# Global service instance
_search_service = None


def get_search_service() -> EnhancedWebSearchService:
    """Get or create search service instance"""
    global _search_service
    if _search_service is None:
        config = SearchConfig(
            duckduckgo_enabled=True,
            searxng_enabled=True,
            searxng_url="http://localhost:55510",
        )
        _search_service = EnhancedWebSearchService(config)
    return _search_service


class SearchRequest(BaseModel):
    """Search request model"""

    query: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(default=10, ge=1, le=50)
    providers: list[str] | None = None
    use_query_understanding: bool = Field(default=True)
    use_reranking: bool = Field(default=True)
    use_cache: bool = Field(default=True)


class SearchResponse(BaseModel):
    """Search response model"""

    query: str
    results: list[dict[str, Any]]
    total_results: int
    latency_ms: float
    cached: bool
    providers_used: list[str]
    query_analysis: dict[str, Any] | None = None


@router.get("/health")
async def health_check():
    """Check web search service health"""
    service = get_search_service()
    return await service.health_check()


@router.get("/providers")
async def list_providers():
    """List available search providers"""
    service = get_search_service()
    return {"providers": service.get_providers()}


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """Perform web search with AI enhancements"""
    try:
        service = get_search_service()
        results = await service.search(
            query=request.query,
            max_results=request.max_results,
            providers=request.providers,
            use_query_understanding=request.use_query_understanding,
            use_reranking=request.use_reranking,
            use_cache=request.use_cache,
        )
        return results
    except Exception as e:
        logger.error("Search error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract")
async def extract_content(
    url: str = Query(..., description="URL to extract content from"),
    max_length: int = Query(default=5000, ge=100, le=50000),
):
    """Extract and summarize content from a URL"""
    try:
        from .content_extractor import ContentExtractor

        extractor = ContentExtractor()
        content = await extractor.extract(url)

        if not content:
            raise HTTPException(status_code=404, detail="Could not extract content")

        # Truncate if needed
        if len(content.get("text", "")) > max_length:
            content["text"] = content["text"][:max_length] + "..."
            content["truncated"] = True

        return content
    except Exception as e:
        logger.error("Content extraction error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_cache():
    """Clear search cache"""
    service = get_search_service()
    if service.cache:
        await service.cache.clear()
        return {"status": "cache cleared"}
    return {"status": "cache not enabled"}


@router.get("/query/understand")
async def understand_query(query: str = Query(..., description="Query to analyze")):
    """Analyze and understand a search query"""
    try:
        from .query_understanding import QueryUnderstandingService

        service = QueryUnderstandingService()
        understanding = await service.understand_query(query)

        return {
            "original_query": understanding.original_query,
            "normalized_query": understanding.normalized_query,
            "intent": understanding.intent.value,
            "intent_confidence": understanding.intent_confidence,
            "complexity_score": understanding.complexity_score,
            "time_sensitive": understanding.time_sensitive,
            "location_sensitive": understanding.location_sensitive,
            "keywords": understanding.keywords,
            "entities": [
                {"text": e.text, "type": e.entity_type, "confidence": e.confidence}
                for e in understanding.entities
            ],
            "expanded_queries": understanding.expanded_queries,
            "suggested_providers": understanding.suggested_providers,
        }
    except Exception as e:
        logger.error("Query understanding error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
