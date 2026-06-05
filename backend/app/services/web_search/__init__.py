"""
Web Search Service Module
Provides multi-provider web search with caching and content extraction
"""

from .cache import ResultDeduplicator, SearchCache
from .content_extractor import ContentExtractor
from .models import (
    CACHE_TTL,
    PROVIDER_COSTS,
    PROVIDER_MATRIX,
    TRUSTED_DOMAINS,
    ContentType,
    ExtractedContent,
    ExtractionDepth,
    ProviderConfig,
    SearchProvider,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchType,
)
from .providers import (
    BaseSearchProvider,
    DuckDuckGoProvider,
    ExaProvider,
    SearXNGProvider,
    TavilyProvider,
    create_provider,
)
from .service import WebSearchService, get_search_service

__all__ = [
    "CACHE_TTL",
    "PROVIDER_COSTS",
    "PROVIDER_MATRIX",
    "TRUSTED_DOMAINS",
    # Providers
    "BaseSearchProvider",
    # Services
    "ContentExtractor",
    "ContentType",
    "DuckDuckGoProvider",
    "ExaProvider",
    "ExtractedContent",
    "ExtractionDepth",
    "ProviderConfig",
    "ResultDeduplicator",
    "SearXNGProvider",
    "SearchCache",
    # Models
    "SearchProvider",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "SearchType",
    "TavilyProvider",
    "WebSearchService",
    "create_provider",
    "get_search_service",
]
