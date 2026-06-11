"""
AI-Powered Query Understanding Service
Provides intent classification, entity extraction, and query expansion
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SearchIntent(Enum):
    """User search intent classification"""

    INFORMATIONAL = "informational"  # Looking for information
    NAVIGATIONAL = "navigational"  # Looking for specific site/page
    TRANSACTIONAL = "transactional"  # Looking to perform action
    RESEARCH = "research"  # In-depth research query
    COMPARISON = "comparison"  # Comparing options
    DEFINITION = "definition"  # Looking for definition
    HOWTO = "howto"  # How-to/tutorial query
    NEWS = "news"  # News/current events
    SHOPPING = "shopping"  # Product search
    LOCAL = "local"  # Local business/place


@dataclass
class ExtractedEntity:
    """Extracted entity from query"""

    text: str
    entity_type: str  # person, organization, location, date, product, etc.
    confidence: float
    start_pos: int
    end_pos: int


@dataclass
class QueryUnderstanding:
    """Result of query understanding analysis"""

    original_query: str
    normalized_query: str
    intent: SearchIntent
    intent_confidence: float
    entities: list[ExtractedEntity]
    keywords: list[str]
    expanded_queries: list[str]
    suggested_providers: list[str]
    time_sensitive: bool
    location_sensitive: bool
    language: str
    complexity_score: float  # 0-1, higher = more complex


class QueryUnderstandingService:
    """Service for understanding and enhancing search queries"""

    # Intent patterns for classification
    INTENT_PATTERNS = {
        SearchIntent.NAVIGATIONAL: [
            r"^(go to|open|visit|login to|sign in to)\s+",
            r"\.(com|org|net|io|edu|gov)\b",
            r"^(website|site|homepage)\s+(of|for)\s+",
        ],
        SearchIntent.TRANSACTIONAL: [
            r"^(buy|purchase|order|book|download|install)\s+",
            r"^(price|cost|cheap|discount|deal)\s+",
            r"\b(store|shop|cart|checkout)\b",
        ],
        SearchIntent.HOWTO: [
            r"^(how\s+(to|do|can|does))\s+",
            r"^(tutorial|guide|steps|instructions)\s+",
            r"\b(learn|teach|explain)\s+(me|how)\b",
        ],
        SearchIntent.DEFINITION: [
            r"^(what\s+is|define|definition\s+of|meaning\s+of)\s+",
            r"\b(meaning|definition|defined)\b",
        ],
        SearchIntent.COMPARISON: [
            r"^(compare|difference\s+between|vs|versus)\s+",
            r"\b(or|versus|vs)\b.*\b(or|versus|vs)\b",
            r"\b(better|best|worse|worst)\b.*\b(than|of)\b",
        ],
        SearchIntent.NEWS: [
            r"^(news|latest|recent|breaking|today)\s+",
            r"\b(news|headlines|update|announcement)\b",
        ],
        SearchIntent.SHOPPING: [
            r"^(shop|buy|order|purchase|find)\s+",
            r"\b(price|review|rating|cheap|best)\b.*\b(product|item|buy)\b",
        ],
        SearchIntent.LOCAL: [
            r"^(near|nearby|local|closest)\s+",
            r"\b(in|at|near)\s+(my\s+)?(area|location|city)\b",
            r"\b(hours|address|phone|directions)\b",
        ],
        SearchIntent.RESEARCH: [
            r"^(research|study|analysis|paper|article)\s+",
            r"\b(academic|scientific|scholarly)\b",
            r"\b(paper|publication|journal|study)\b",
        ],
    }

    # Entity patterns
    ENTITY_PATTERNS = {
        "date": [
            r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
            r"\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
            r"\b(today|yesterday|tomorrow|this\s+week|last\s+week|next\s+week)\b",
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
        ],
        "location": [
            r"\b(in|at|near|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z]{2})\b",  # City, State
        ],
        "organization": [
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(Inc|Corp|LLC|Ltd|Company|Co)\b",
            r"\b(Google|Microsoft|Apple|Amazon|Meta|OpenAI|Anthropic)\b",
        ],
        "product": [
            r"\b(iPhone|Android|Windows|Mac|Linux|ChatGPT|GPT-4|Claude)\b",
            r"\b([A-Z][a-z]+\s+\d+(?:\s+(Pro|Max|Plus|Mini))?)\b",
        ],
        "person": [
            r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b",  # Simple name pattern
        ],
    }

    # Stop words for keyword extraction
    STOP_WORDS = {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "and",
        "but",
        "if",
        "or",
        "because",
        "until",
        "while",
        "about",
        "against",
        "up",
        "down",
        "out",
        "off",
        "over",
        "i",
        "me",
        "my",
        "myself",
        "we",
        "our",
        "ours",
        "ourselves",
        "you",
        "your",
        "yours",
    }

    def __init__(self):
        self.llm_client = None  # Will be set for advanced features

    async def understand_query(self, query: str) -> QueryUnderstanding:
        """Main entry point for query understanding"""
        # Normalize query
        normalized = self._normalize_query(query)

        # Classify intent
        intent, intent_confidence = self._classify_intent(normalized)

        # Extract entities
        entities = self._extract_entities(normalized)

        # Extract keywords
        keywords = self._extract_keywords(normalized)

        # Generate expanded queries
        expanded = await self._expand_query(normalized, intent, entities)

        # Suggest providers based on intent
        providers = self._suggest_providers(intent, normalized)

        # Check time/location sensitivity
        time_sensitive = self._check_time_sensitivity(normalized, entities)
        location_sensitive = self._check_location_sensitivity(normalized, entities)

        # Calculate complexity
        complexity = self._calculate_complexity(normalized, entities, intent)

        return QueryUnderstanding(
            original_query=query,
            normalized_query=normalized,
            intent=intent,
            intent_confidence=intent_confidence,
            entities=entities,
            keywords=keywords,
            expanded_queries=expanded,
            suggested_providers=providers,
            time_sensitive=time_sensitive,
            location_sensitive=location_sensitive,
            language="en",  # Default, could be detected
            complexity_score=complexity,
        )

    def _normalize_query(self, query: str) -> str:
        """Normalize query for processing"""
        # Convert to lowercase
        normalized = query.lower().strip()

        # Remove extra whitespace
        normalized = re.sub(r"\s+", " ", normalized)

        # Remove special characters but keep important ones
        normalized = re.sub(r"[^\w\s\-\?\.]", " ", normalized)

        return normalized.strip()

    def _classify_intent(self, query: str) -> tuple[SearchIntent, float]:
        """Classify search intent using pattern matching"""
        scores = {}

        for intent, patterns in self.INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    score += 1
            scores[intent] = score

        # Find best intent
        if not scores or max(scores.values()) == 0:
            return SearchIntent.INFORMATIONAL, 0.5

        best_intent = max(scores, key=scores.get)
        total_matches = sum(scores.values())
        confidence = scores[best_intent] / max(total_matches, 1)

        return best_intent, min(confidence, 1.0)

    def _extract_entities(self, query: str) -> list[ExtractedEntity]:
        """Extract named entities from query"""
        entities = []

        for entity_type, patterns in self.ENTITY_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, query, re.IGNORECASE):
                    entities.append(
                        ExtractedEntity(
                            text=match.group(0),
                            entity_type=entity_type,
                            confidence=0.8,  # Pattern-based confidence
                            start_pos=match.start(),
                            end_pos=match.end(),
                        )
                    )

        # Remove duplicates
        seen = set()
        unique_entities = []
        for e in entities:
            key = (e.text.lower(), e.entity_type)
            if key not in seen:
                seen.add(key)
                unique_entities.append(e)

        return unique_entities

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract important keywords from query"""
        words = re.findall(r"\b\w+\b", query.lower())
        keywords = [w for w in words if w not in self.STOP_WORDS and len(w) > 2]

        # Count frequency and sort
        from collections import Counter

        word_counts = Counter(keywords)

        return [w for w, _ in word_counts.most_common(10)]

    async def _expand_query(self, query: str, intent: SearchIntent, entities: list[ExtractedEntity]) -> list[str]:
        """Generate expanded/related queries"""
        expanded = []

        # Add intent-specific expansions
        if intent == SearchIntent.HOWTO:
            expanded.append(f"{query} tutorial")
            expanded.append(f"{query} guide")
            expanded.append(f"{query} step by step")
        elif intent == SearchIntent.DEFINITION:
            expanded.append(f"what is {query}")
            expanded.append(f"{query} meaning")
        elif intent == SearchIntent.COMPARISON:
            expanded.append(f"{query} comparison")
            expanded.append(f"{query} differences")
        elif intent == SearchIntent.NEWS:
            expanded.append(f"{query} latest")
            expanded.append(f"{query} 2024")

        # Add entity-based expansions
        for entity in entities:
            if entity.entity_type == "product":
                expanded.append(f"{query} review")
                expanded.append(f"{query} features")

        return list(set(expanded))[:5]  # Limit to 5 expansions

    def _suggest_providers(self, intent: SearchIntent, query: str) -> list[str]:
        """Suggest best providers for the query"""
        providers = ["duckduckgo"]  # Default

        if intent == SearchIntent.NEWS:
            providers = ["duckduckgo", "searxng"]
        elif intent == SearchIntent.RESEARCH:
            providers = ["searxng", "duckduckgo"]
        elif intent == SearchIntent.SHOPPING:
            providers = ["duckduckgo"]
        elif intent == SearchIntent.LOCAL:
            providers = ["duckduckgo", "searxng"]

        return providers

    def _check_time_sensitivity(self, query: str, entities: list[ExtractedEntity]) -> bool:
        """Check if query is time-sensitive"""
        time_keywords = [
            "latest",
            "recent",
            "today",
            "now",
            "current",
            "new",
            "breaking",
            "update",
            "2024",
            "2025",
            "2026",
        ]

        if any(kw in query for kw in time_keywords):
            return True

        return bool(any(e.entity_type == "date" for e in entities))

    def _check_location_sensitivity(self, query: str, entities: list[ExtractedEntity]) -> bool:
        """Check if query is location-sensitive"""
        location_keywords = [
            "near",
            "nearby",
            "local",
            "closest",
            "in my area",
            "around me",
            "here",
        ]

        if any(kw in query for kw in location_keywords):
            return True

        return bool(any(e.entity_type == "location" for e in entities))

    def _calculate_complexity(self, query: str, entities: list[ExtractedEntity], intent: SearchIntent) -> float:
        """Calculate query complexity score"""
        score = 0.0

        # Word count factor
        words = len(query.split())
        score += min(words / 20, 0.3)  # Max 0.3 for length

        # Entity factor
        score += min(len(entities) * 0.1, 0.3)  # Max 0.3 for entities

        # Intent factor
        complex_intents = {SearchIntent.RESEARCH, SearchIntent.COMPARISON}
        if intent in complex_intents:
            score += 0.2

        # Question marks indicate complex queries
        if "?" in query:
            score += 0.1

        # Boolean operators
        if " AND " in query.upper() or " OR " in query.upper():
            score += 0.1

        return min(score, 1.0)
