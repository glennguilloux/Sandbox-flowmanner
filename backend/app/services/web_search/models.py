"""
Web Search Tool - Data Models
Following Opus 4.6 Architecture Recommendations
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SearchProvider(str, Enum):
    """Available search providers"""

    SEARXNG = "searxng"
    TAVILY = "tavily"
    EXA = "exa"
    DUCKDUCKGO = "duckduckgo"


class SearchType(str, Enum):
    """Types of search queries"""

    QUICK = "quick"  # Fast, few results
    DEEP = "deep"  # Comprehensive search
    NEWS = "news"  # Real-time news
    RESEARCH = "research"  # Academic/research
    CODE = "code"  # Code/technical


class ContentType(str, Enum):
    """Content types for caching TTL"""

    NEWS = "news"
    RESEARCH = "research"
    DOCUMENTATION = "documentation"
    GENERAL = "general"
    STOCK_PRICE = "stock_price"


class ExtractionDepth(str, Enum):
    """Content extraction depth levels"""

    AUTO = "auto"
    STATIC = "static"  # HTTP + BeautifulSoup
    MODERATE = "moderate"  # Jina Reader
    COMPLEX = "complex"  # Playwright


@dataclass
class SearchResult:
    """Individual search result"""

    title: str
    url: str
    snippet: str
    provider: SearchProvider
    rank: int = 0
    score: float = 0.0
    published_date: datetime | None = None
    content: str | None = None
    extracted_content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def domain(self) -> str:
        """Extract domain from URL"""
        from urllib.parse import urlparse

        return urlparse(self.url).netloc

    @property
    def query_hash(self) -> str:
        """Generate hash for caching"""
        return hashlib.sha256(f"{self.url}:{self.title}".encode()).hexdigest()[:16]


@dataclass
class SearchResponse:
    """Complete search response"""

    query: str
    results: list[SearchResult]
    provider: SearchProvider
    search_type: SearchType
    total_results: int
    latency_ms: float
    cached: bool = False
    query_hash: str = ""
    error: str | None = None

    def __post_init__(self):
        if not self.query_hash:
            self.query_hash = hashlib.sha256(self.query.encode()).hexdigest()[:16]


@dataclass
class ExtractedContent:
    """Extracted content from URL"""

    url: str
    title: str
    content: str
    extraction_method: str  # "http", "jina", "playwright"
    word_count: int
    latency_ms: float
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderConfig:
    """Configuration for a search provider"""

    provider: SearchProvider
    api_key: str | None = None
    base_url: str | None = None
    enabled: bool = True
    priority: int = 0  # Lower = higher priority
    daily_limit: int = 1000
    timeout_seconds: int = 15


@dataclass
class SearchRequest:
    """Search request parameters"""

    query: str
    search_type: SearchType = SearchType.QUICK
    providers: list[SearchProvider] | None = None
    max_results: int = 10
    extract_content: bool = False
    extraction_depth: ExtractionDepth = ExtractionDepth.AUTO
    use_cache: bool = True
    user_id: int | None = None
    thread_id: int | None = None

    @property
    def query_hash(self) -> str:
        return hashlib.sha256(self.query.encode()).hexdigest()[:16]


# Provider priority matrix based on query type
PROVIDER_MATRIX: dict[SearchType, list[SearchProvider]] = {
    SearchType.NEWS: [
        SearchProvider.TAVILY,
        SearchProvider.EXA,
        SearchProvider.SEARXNG,
    ],
    SearchType.RESEARCH: [
        SearchProvider.EXA,
        SearchProvider.TAVILY,
        SearchProvider.SEARXNG,
    ],
    SearchType.QUICK: [SearchProvider.SEARXNG, SearchProvider.DUCKDUCKGO],
    SearchType.CODE: [SearchProvider.SEARXNG, SearchProvider.EXA],
    SearchType.DEEP: [
        SearchProvider.TAVILY,
        SearchProvider.EXA,
        SearchProvider.SEARXNG,
    ],
}

# Cache TTL by content type (seconds)
CACHE_TTL: dict[ContentType, int] = {
    ContentType.NEWS: 3600,  # 1 hour
    ContentType.STOCK_PRICE: 60,  # 1 minute
    ContentType.RESEARCH: 86400 * 7,  # 7 days
    ContentType.DOCUMENTATION: 86400 * 3,  # 3 days
    ContentType.GENERAL: 86400,  # 1 day
}

# Trusted domains for quality scoring
TRUSTED_DOMAINS = {
    "wikipedia.org",
    "github.com",
    "stackoverflow.com",
    "docs.python.org",
    "arxiv.org",
    "scholar.google.com",
    "nature.com",
    "science.org",
    "reuters.com",
    "bbc.com",
    "nytimes.com",
    "bloomberg.com",
}

# Provider costs (USD per search)
PROVIDER_COSTS = {
    SearchProvider.SEARXNG: 0.0,
    SearchProvider.DUCKDUCKGO: 0.0,
    SearchProvider.EXA: 0.001,
    SearchProvider.TAVILY: 0.005,
}


@dataclass
class SearchConfig:
    """Configuration for web search service"""

    duckduckgo_enabled: bool = True
    searxng_enabled: bool = False
    searxng_url: str = "http://localhost:55510"
    cache_ttl: int = 3600  # 1 hour
    max_results_per_provider: int = 10
    timeout: float = 10.0
