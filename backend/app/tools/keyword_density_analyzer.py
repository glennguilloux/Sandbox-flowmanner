"""
SEO & Marketing Tools — Keyword Density Analyzer.

keyword_density_analyzer → Extract keywords and calculate TF-IDF scores
    from text to analyze keyword density and content relevance.
    Supports multi-language stopwords, configurable n-gram ranges, and density warnings.
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from typing import Any

from pydantic import Field
from sklearn.feature_extraction.text import TfidfVectorizer

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

DEFAULT_TOP_N = int(os.getenv("KEYWORD_DENSITY_TOP_N", "20"))
DEFAULT_OPTIMAL_DENSITY = float(os.getenv("KEYWORD_OPTIMAL_DENSITY", "2.5"))  # %
STUFFING_THRESHOLD = float(os.getenv("KEYWORD_STUFFING_THRESHOLD", "5.0"))  # %

# Common SEO stopwords (English default)
_SEO_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "shall", "you", "your",
    "we", "our", "they", "their", "it", "its", "this", "that", "these",
    "those", "what", "which", "who", "how", "all", "each", "every",
    "both", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "about", "also", "here", "there", "when", "where", "why", "get",
    "make", "like", "into", "over", "after", "before", "between",
}

# Multi-language stopword sets (NLTK-compatible language codes)
_LANG_STOPWORDS: dict[str, set[str]] = {
    "en": _SEO_STOPWORDS,
    "es": {  # Spanish
        "de", "la", "que", "el", "en", "y", "a", "los", "del", "se",
        "las", "por", "un", "para", "con", "no", "una", "su", "al",
        "lo", "como", "más", "pero", "sus", "le", "ya", "o", "este",
        "sí", "porque", "esta", "entre", "cuando", "muy", "sin", "sobre",
        "también", "me", "hasta", "hay", "donde", "quien", "todo",
        "nos", "durante", "todos", "uno", "les", "ni", "contra", "eso",
        "esa", "esos", "esas", "fue", "han", "era", "ser", "son",
    },
    "fr": {  # French
        "le", "la", "les", "de", "du", "des", "un", "une", "et", "à",
        "en", "au", "aux", "ce", "cette", "ces", "il", "elle", "ils",
        "elles", "que", "qui", "dans", "sur", "pour", "par", "pas",
        "ne", "se", "son", "sa", "ses", "nous", "vous", "leur", "leurs",
        "avec", "est", "sont", "était", "étaient", "plus", "moins",
    },
    "de": {  # German
        "der", "die", "das", "und", "in", "zu", "den", "des", "von",
        "mit", "auf", "für", "ist", "im", "dem", "nicht", "ein", "eine",
        "als", "auch", "es", "an", "werden", "aus", "er", "hat", "dass",
        "sie", "nach", "bei", "um", "noch", "wie", "über", "so", "war",
    },
}


def _get_stopwords(language: str) -> set[str]:
    """Get stopwords for a given language, falling back to English."""
    lang = language.lower()[:2]
    if lang in _LANG_STOPWORDS:
        return _LANG_STOPWORDS[lang]

    # Try NLTK for language not in our built-in set
    try:
        from nltk.corpus import stopwords
        nltk_stops = set(stopwords.words(lang if lang == "english" else _nltk_lang_map.get(lang, "english")))
        if nltk_stops:
            return nltk_stops
    except Exception:
        logger.debug("NLTK stopwords not available for language '%s', falling back to English", language)

    return _SEO_STOPWORDS


_nltk_lang_map: dict[str, str] = {
    "en": "english", "es": "spanish", "fr": "french", "de": "german",
    "it": "italian", "pt": "portuguese", "nl": "dutch", "ru": "russian",
    "ar": "arabic", "da": "danish", "fi": "finnish", "hu": "hungarian",
    "no": "norwegian", "sv": "swedish", "tr": "turkish",
}

# ── Input ─────────────────────────────────────────────────────────────

KEYWORD_ACTIONS = (
    "analyze_density",
    "extract_keywords",
    "compare_pages",
)


class KeywordDensityAnalyzerInput(ToolInput):
    """Input schema: text_content, top_n, language, ngram_range, include_scores."""

    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(KEYWORD_ACTIONS)}",
    )
    text_content: str = Field(
        ...,
        description="Text content to analyze for keyword density",
    )
    second_text: str | None = Field(
        None,
        description="Second page text for comparison (compare_pages action)",
    )
    keywords: list[str] | None = Field(
        None,
        description="Specific keywords to check density for (optional; auto-extracted if omitted)",
    )
    top_n: int = Field(
        DEFAULT_TOP_N, ge=5, le=100,
        description="Number of top keywords to return",
    )
    language: str = Field(
        "en",
        description="Language code for stopword filtering (e.g., 'en', 'es', 'fr', 'de'). "
        "Uses NLTK stopwords corpus when available.",
    )
    ngram_range: tuple[int, int] | list[int] = Field(
        default=(1, 3),
        description="N-gram range as [min_n, max_n] (e.g., [1, 3]). Default: [1, 3].",
    )
    include_scores: bool = Field(
        True,
        description="Include TF-IDF scores in keyword output",
    )
    optimal_density: float = Field(
        DEFAULT_OPTIMAL_DENSITY, ge=0.5, le=10.0,
        description="Target keyword density percentage (default: 2.5%)",
    )

    # Backward-compat alias
    @property
    def text(self) -> str | None:
        """Backward compat: text is an alias for text_content."""
        return self.text_content


# ── Tool ──────────────────────────────────────────────────────────────


class KeywordDensityAnalyzerTool(BaseTool):
    """Extract keywords and calculate TF-IDF density scores."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="keyword_density_analyzer",
            name="Keyword Density Analyzer",
            description=(
                "Extract keywords and calculate TF-IDF scores to analyze "
                "keyword density and content relevance for SEO. Supports "
                "multi-language stopwords, configurable n-gram ranges, "
                "and keyword stuffing detection."
            ),
            category="seo-marketing",
            input_schema=KeywordDensityAnalyzerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "term": {"type": "string"},
                            "count": {"type": "integer"},
                            "density_pct": {"type": "number"},
                            "tfidf_score": {"type": "number"},
                        },
                    }},
                    "total_words": {"type": "integer"},
                    "unique_words": {"type": "integer"},
                    "stuffing_warnings": {"type": "array", "items": {"type": "string"}},
                    "success": {"type": "boolean"},
                },
            },
            tags=["seo", "keywords", "density", "tf-idf", "content-analysis"],
            requires_auth=False,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = KeywordDensityAnalyzerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.action not in KEYWORD_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. "
                f"Use: {', '.join(KEYWORD_ACTIONS)}",
            )

        # Resolve text_content (support backward compat 'text' key)
        if not validated.text_content and "text" in input_data:
            validated.text_content = input_data["text"]

        try:
            result = await self._execute_action(validated)
            result["success"] = True
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.warning("keyword_density_analyzer failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(
        self, validated: KeywordDensityAnalyzerInput
    ) -> dict[str, Any]:
        if validated.action == "analyze_density":
            return await self._analyze_density(validated)
        elif validated.action == "extract_keywords":
            return await self._extract_keywords(validated)
        elif validated.action == "compare_pages":
            return await self._compare_pages(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}", "success": False}

    # ── Core helpers ─────────────────────────────────────────────

    def _get_stopwords_for_lang(self, language: str) -> set[str]:
        """Get stopwords for the configured language."""
        return _get_stopwords(language)

    def _tokenize(self, text: str, stopwords: set[str] | None = None) -> list[str]:
        """Tokenize text into lowercase words, filtering stopwords and short tokens."""
        if stopwords is None:
            stopwords = _SEO_STOPWORDS
        words = re.findall(r"[a-zA-Z0-9\u00C0-\u024F]+(?:'[a-zA-Z0-9\u00C0-\u024F]+)?", text.lower())
        return [
            w for w in words
            if len(w) > 1 and w not in stopwords
        ]

    def _count_words(self, text: str) -> int:
        """Count total words in text."""
        return len(re.findall(r"[a-zA-Z0-9\u00C0-\u024F]+(?:'[a-zA-Z0-9\u00C0-\u024F]+)?", text))

    def _compute_tfidf(
        self, documents: list[str], top_n: int, max_features: int = 500,
        ngram_range: tuple[int, int] | None = None,
    ) -> list[dict[str, Any]]:
        """Compute TF-IDF scores and return top keywords."""
        if not documents or not any(doc.strip() for doc in documents):
            return []

        ngram = ngram_range or (1, 3)

        try:
            vectorizer = TfidfVectorizer(
                stop_words="english",
                max_features=max_features,
                ngram_range=ngram,
                strip_accents="unicode",
            )
            tfidf_matrix = vectorizer.fit_transform(documents)
            feature_names = vectorizer.get_feature_names_out()

            # Sum scores across all documents
            combined_scores = (
                tfidf_matrix.sum(axis=0).A1 if tfidf_matrix.shape[0] > 1
                else tfidf_matrix.toarray()[0]
            )

            keyword_scores = []
            for name, score in zip(feature_names, combined_scores, strict=False):
                if score > 0 and len(name) > 1:
                    keyword_scores.append({
                        "keyword": name,
                        "score": round(float(score), 6),
                    })

            keyword_scores.sort(key=lambda x: x["score"], reverse=True)
            return keyword_scores[:top_n]
        except Exception as e:
            logger.warning("TF-IDF computation failed: %s", e)
            return []

    def _keyword_density(
        self, text: str, keywords: list[str]
    ) -> list[dict[str, Any]]:
        """Calculate density percentage for specific keywords."""
        total_words = max(self._count_words(text), 1)
        tokens = self._tokenize(text)
        token_counter = Counter(tokens)

        results = []
        for kw in keywords:
            kw_lower = kw.lower()
            if " " in kw_lower:
                pattern = re.escape(kw_lower)
                count = len(re.findall(pattern, text.lower()))
            else:
                count = token_counter.get(kw_lower, 0)
            density = round((count / total_words) * 100, 2)
            results.append({
                "term": kw,
                "count": count,
                "density_pct": density,
            })

        return results

    # ── Action handlers ──────────────────────────────────────────

    async def _analyze_density(
        self, validated: KeywordDensityAnalyzerInput
    ) -> dict[str, Any]:
        """Analyze keyword density for given or auto-extracted keywords."""
        if not validated.text_content:
            return {"error": "text_content is required for analyze_density", "success": False}

        stopwords = self._get_stopwords_for_lang(validated.language)
        total_words = self._count_words(validated.text_content)
        unique_words = len(set(self._tokenize(validated.text_content, stopwords)))

        # Determine keywords to analyze
        keywords = validated.keywords
        auto_extracted = False
        if not keywords:
            ngram = tuple(validated.ngram_range) if validated.ngram_range else None
            tfidf_results = self._compute_tfidf(
                [validated.text_content], validated.top_n, ngram_range=ngram
            )
            keywords = [k["keyword"] for k in tfidf_results[:10]]
            auto_extracted = True

        # Calculate density for each keyword
        density_data_raw = self._keyword_density(validated.text_content, keywords)

        # Enhance with TF-IDF scores if requested
        density_data: list[dict[str, Any]] = []
        stuffing_warnings: list[str] = []

        if validated.include_scores and density_data_raw:
            # Compute TF-IDF for scoring
            ngram = tuple(validated.ngram_range) if validated.ngram_range else None
            tfidf_scores = self._compute_tfidf(
                [validated.text_content], validated.top_n, ngram_range=ngram
            )
            tfidf_map = {k["keyword"]: k["score"] for k in tfidf_scores}

            for item in density_data_raw:
                kw_lower = item["term"].lower()
                tfidf_score = tfidf_map.get(item["term"], tfidf_map.get(kw_lower, 0.0))
                density_data.append({
                    "term": item["term"],
                    "count": item["count"],
                    "density_pct": item["density_pct"],
                    "tfidf_score": round(tfidf_score, 6),
                })
        else:
            density_data = [
                {**item, "tfidf_score": 0.0} for item in density_data_raw
            ]

        # Generate stuffing warnings (>5% density)
        for item in density_data:
            density = item["density_pct"]
            if density == 0:
                stuffing_warnings.append(f"Keyword '{item['term']}' not found in text")
            elif density > STUFFING_THRESHOLD:
                stuffing_warnings.append(
                    f"Keyword '{item['term']}' density is {density}% "
                    f"(exceeds {STUFFING_THRESHOLD}% stuffing threshold)"
                )
            elif density < validated.optimal_density * 0.3:
                stuffing_warnings.append(
                    f"Keyword '{item['term']}' density is low "
                    f"({density}% vs optimal {validated.optimal_density}%)"
                )

        return {
            "action": "analyze_density",
            "total_words": total_words,
            "unique_words": unique_words,
            "keyword_count": len(keywords),
            "keywords": density_data,
            "stuffing_warnings": stuffing_warnings,
            "language": validated.language,
            "auto_extracted": auto_extracted,
            "success": True,
        }

    async def _extract_keywords(
        self, validated: KeywordDensityAnalyzerInput
    ) -> dict[str, Any]:
        """Extract top keywords using TF-IDF without density analysis."""
        if not validated.text_content:
            return {"error": "text_content is required for extract_keywords", "success": False}

        total_words = self._count_words(validated.text_content)
        ngram = tuple(validated.ngram_range) if validated.ngram_range else None
        keywords = self._compute_tfidf(
            [validated.text_content], validated.top_n, ngram_range=ngram
        )

        # Format output per Plan 16: {term, count, density_pct, tfidf_score}
        formatted = []
        if validated.include_scores and keywords:
            token_counter = Counter(self._tokenize(validated.text_content))
            for kw in keywords:
                kw_name = kw["keyword"]
                count = token_counter.get(kw_name, 0)
                density = round((count / max(total_words, 1)) * 100, 2)
                formatted.append({
                    "term": kw_name,
                    "count": count,
                    "density_pct": density,
                    "tfidf_score": kw["score"],
                })
        else:
            formatted = keywords

        return {
            "action": "extract_keywords",
            "total_words": total_words,
            "keyword_count": len(keywords),
            "keywords": formatted,
            "language": validated.language,
            "ngram_range": list(ngram) if ngram else [1, 3],
            "success": True,
        }

    async def _compare_pages(
        self, validated: KeywordDensityAnalyzerInput
    ) -> dict[str, Any]:
        """Compare keyword usage across two pages."""
        if not validated.text_content:
            return {"error": "text_content is required for compare_pages", "success": False}
        if not validated.second_text:
            return {"error": "second_text is required for compare_pages", "success": False}

        ngram = tuple(validated.ngram_range) if validated.ngram_range else None
        docs = [validated.text_content, validated.second_text]
        combined_keywords = self._compute_tfidf(
            docs, validated.top_n, max_features=300, ngram_range=ngram
        )

        keywords_list = [k["keyword"] for k in combined_keywords]
        page1_density = self._keyword_density(validated.text_content, keywords_list)
        page2_density = self._keyword_density(validated.second_text, keywords_list)

        comparison = []
        for p1, p2 in zip(page1_density, page2_density, strict=False):
            diff = round(p1["density_pct"] - p2["density_pct"], 2)
            comparison.append({
                "term": p1["term"],
                "page1_density": p1["density_pct"],
                "page2_density": p2["density_pct"],
                "difference": abs(diff),
                "winner": "page1" if diff > 0 else ("page2" if diff < 0 else "tie"),
            })

        comparison.sort(key=lambda x: x["difference"], reverse=True)

        page1_win = sum(1 for c in comparison if c["winner"] == "page1")
        page2_win = sum(1 for c in comparison if c["winner"] == "page2")
        ties = sum(1 for c in comparison if c["winner"] == "tie")

        return {
            "action": "compare_pages",
            "total_keywords_compared": len(comparison),
            "page1_wins": page1_win,
            "page2_wins": page2_win,
            "ties": ties,
            "comparison": comparison,
            "language": validated.language,
            "success": True,
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(KeywordDensityAnalyzerTool())
