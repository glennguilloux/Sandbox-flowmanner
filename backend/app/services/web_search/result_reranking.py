"""
AI-Powered Result Reranking Service
Provides semantic similarity, relevance scoring, and intelligent reranking
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RerankedResult:
    """A search result with reranking scores"""

    original_rank: int
    title: str
    url: str
    snippet: str
    domain: str
    provider: str

    # Reranking scores
    relevance_score: float = 0.0
    authority_score: float = 0.0
    freshness_score: float = 0.0
    diversity_score: float = 0.0
    final_score: float = 0.0

    # Metadata
    rerank_reasons: list[str] = field(default_factory=list)


class ResultReranker:
    """Service for reranking search results"""

    # Authority domains (higher = more authoritative)
    AUTHORITY_DOMAINS = {
        # Academic
        "arxiv.org": 0.95,
        "scholar.google.com": 0.95,
        "pubmed.gov": 0.95,
        "nature.com": 0.90,
        "science.org": 0.90,
        # Official documentation
        "docs.python.org": 0.95,
        "developer.mozilla.org": 0.90,
        "react.dev": 0.90,
        "typescriptlang.org": 0.90,
        # Trusted tech
        "stackoverflow.com": 0.85,
        "github.com": 0.85,
        "medium.com": 0.70,
        "dev.to": 0.70,
        # News
        "reuters.com": 0.90,
        "bbc.com": 0.85,
        "nytimes.com": 0.80,
        "theguardian.com": 0.80,
        # Reference
        "wikipedia.org": 0.85,
        "w3schools.com": 0.75,
        "geeksforgeeks.org": 0.70,
    }

    # Low quality domains
    LOW_QUALITY_DOMAINS = {
        "pinterest.com": 0.3,
        "quora.com": 0.5,
        "yahoo.com": 0.5,
    }

    # Freshness date patterns
    DATE_PATTERNS = [
        r"(\d{4}[-/]\d{2}[-/]\d{2})",
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}",
        r"(\d{1,2}\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})",
    ]

    def __init__(self):
        self.embedding_model = None  # For semantic similarity

    async def rerank_results(
        self,
        results: list[dict[str, Any]],
        query: str,
        intent: str = "informational",
        time_sensitive: bool = False,
        diversity_factor: float = 0.3,
    ) -> list[RerankedResult]:
        """Main entry point for result reranking"""

        if not results:
            return []

        # Convert to RerankedResult objects
        reranked = []
        for i, r in enumerate(results):
            reranked.append(
                RerankedResult(
                    original_rank=i + 1,
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                    domain=r.get("domain", self._extract_domain(r.get("url", ""))),
                    provider=r.get("provider", "unknown"),
                )
            )

        # Calculate individual scores
        for result in reranked:
            result.relevance_score = self._calculate_relevance(result, query)
            result.authority_score = self._calculate_authority(result)
            result.freshness_score = self._calculate_freshness(result, time_sensitive)

        # Calculate diversity scores (requires all results)
        self._calculate_diversity_scores(reranked)

        # Calculate final scores
        weights = self._get_intent_weights(intent, time_sensitive)
        for result in reranked:
            result.final_score = (
                weights["relevance"] * result.relevance_score
                + weights["authority"] * result.authority_score
                + weights["freshness"] * result.freshness_score
                + weights["diversity"] * result.diversity_score
            )

        # Sort by final score
        reranked.sort(key=lambda x: x.final_score, reverse=True)

        # Add rerank reasons
        for i, result in enumerate(reranked):
            if i < result.original_rank - 1:
                result.rerank_reasons.append(
                    f"Moved up from position {result.original_rank}"
                )
            elif i > result.original_rank - 1:
                result.rerank_reasons.append(
                    f"Moved down from position {result.original_rank}"
                )

        return reranked

    def _calculate_relevance(self, result: RerankedResult, query: str) -> float:
        """Calculate relevance score based on query-result matching"""
        score = 0.0
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        # Title matching (most important)
        title_lower = result.title.lower()
        title_terms = set(title_lower.split())
        title_overlap = len(query_terms & title_terms) / max(len(query_terms), 1)
        score += title_overlap * 0.5

        # Exact phrase match in title
        if query_lower in title_lower:
            score += 0.3
            result.rerank_reasons.append("Exact phrase match in title")

        # Snippet matching
        snippet_lower = result.snippet.lower()
        snippet_terms = set(snippet_lower.split())
        snippet_overlap = len(query_terms & snippet_terms) / max(len(query_terms), 1)
        score += snippet_overlap * 0.2

        # URL matching
        url_lower = result.url.lower()
        if any(term in url_lower for term in query_terms):
            score += 0.1

        return min(score, 1.0)

    def _calculate_authority(self, result: RerankedResult) -> float:
        """Calculate authority score based on domain reputation"""
        domain = result.domain.lower()

        # Check high authority domains
        for auth_domain, score in self.AUTHORITY_DOMAINS.items():
            if auth_domain in domain:
                result.rerank_reasons.append(f"High authority domain: {auth_domain}")
                return score

        # Check low quality domains
        for low_domain, score in self.LOW_QUALITY_DOMAINS.items():
            if low_domain in domain:
                result.rerank_reasons.append(f"Lower quality domain: {low_domain}")
                return score

        # Default score for unknown domains
        # Check if it's an official domain (contains company name)
        if any(part in domain for part in [".gov", ".edu", ".org"]):
            return 0.75

        return 0.6  # Default for .com and others

    def _calculate_freshness(
        self, result: RerankedResult, time_sensitive: bool
    ) -> float:
        """Calculate freshness score based on date indicators"""
        # Look for dates in snippet and title
        text = f"{result.title} {result.snippet}"

        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    date_str = match.group(1)
                    # Parse date (simplified)
                    if "2024" in date_str or "2025" in date_str or "2026" in date_str:
                        result.rerank_reasons.append("Recent content")
                        return 0.9
                    elif "2023" in date_str:
                        return 0.7
                    elif "2022" in date_str:
                        return 0.5
                except Exception:
                    logger.debug(
                        "Failed to parse date from result text for freshness scoring"
                    )

        # Check for freshness keywords
        freshness_keywords = [
            "latest",
            "new",
            "updated",
            "recent",
            "2024",
            "2025",
            "2026",
        ]
        if any(kw in text.lower() for kw in freshness_keywords):
            result.rerank_reasons.append("Freshness keywords detected")
            return 0.8

        # Default freshness
        return 0.5 if time_sensitive else 0.7

    def _calculate_diversity_scores(self, results: list[RerankedResult]) -> None:
        """Calculate diversity scores to promote varied results"""
        seen_domains = set()

        for result in results:
            if result.domain in seen_domains:
                result.diversity_score = 0.3  # Penalize duplicate domains
                result.rerank_reasons.append("Duplicate domain")
            else:
                result.diversity_score = 1.0
                seen_domains.add(result.domain)

    def _get_intent_weights(
        self, intent: str, time_sensitive: bool
    ) -> dict[str, float]:
        """Get scoring weights based on search intent"""
        base_weights = {
            "relevance": 0.4,
            "authority": 0.3,
            "freshness": 0.1,
            "diversity": 0.2,
        }

        # Adjust for intent
        if intent == "news":
            base_weights["freshness"] = 0.4
            base_weights["relevance"] = 0.3
        elif intent == "research":
            base_weights["authority"] = 0.4
            base_weights["relevance"] = 0.35
        elif intent == "howto":
            base_weights["authority"] = 0.35
            base_weights["relevance"] = 0.4

        # Adjust for time sensitivity
        if time_sensitive:
            base_weights["freshness"] = min(base_weights["freshness"] + 0.2, 0.5)

        return base_weights

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return parsed.netloc or url
        except Exception:
            logger.debug("Failed to parse domain from URL: %s", url)
            return url
