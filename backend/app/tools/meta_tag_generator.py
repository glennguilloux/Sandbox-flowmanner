"""
SEO & Marketing Tools — Meta Tag Generator.

meta_tag_generator → Analyze existing HTML meta tags and generate optimized
    title and description tags using TF-IDF keyword analysis.
    Supports URL fetching, HTML content, and page content inputs.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import Field
from sklearn.feature_extraction.text import TfidfVectorizer

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── SSRF Protection ───────────────────────────────────────────────────

_BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript", "gopher", "dict"}
_BLOCKED_HOSTS = {"localhost", "0.0.0.0", "::1", "127.0.0.1"}
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
]


def _validate_url(url: str) -> tuple[bool, str | None]:
    """Validate a URL for safe fetching (SSRF protection)."""
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            return False, f"URL scheme '{scheme}://' is not allowed. Only http/https."

        hostname = parsed.hostname
        if not hostname:
            return False, "URL has no valid hostname"

        hostname_lower = hostname.lower()
        if hostname_lower in _BLOCKED_HOSTS:
            return False, f"Hostname '{hostname}' is blocked"

        # Check if hostname resolves to a private/internal IP
        try:
            addr = ipaddress.ip_address(hostname_lower)
        except ValueError:
            pass  # Not an IP literal, DNS resolution needed — allow
        else:
            for net in _BLOCKED_NETWORKS:
                if addr in net:
                    return False, f"IP address '{hostname}' is in blocked range {net}"

        return True, None
    except Exception as e:
        return False, f"URL validation error: {e}"


# ── Configuration ─────────────────────────────────────────────────────

DEFAULT_TITLE_MAX_LENGTH = int(os.getenv("META_TITLE_MAX_LENGTH", "60"))
DEFAULT_DESC_MAX_LENGTH = int(os.getenv("META_DESC_MAX_LENGTH", "160"))
FETCH_TIMEOUT = int(os.getenv("META_FETCH_TIMEOUT", "15"))

# ── Input ─────────────────────────────────────────────────────────────

META_ACTIONS = (
    "analyze_meta",
    "generate_title",
    "generate_description",
    "analyze_and_generate",
)

# Common SEO stopwords to exclude from TF-IDF
_SEO_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
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
    "can",
    "shall",
    "you",
    "your",
    "we",
    "our",
    "they",
    "their",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "what",
    "which",
    "who",
    "how",
    "all",
    "each",
    "every",
    "both",
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
    "about",
    "also",
    "here",
    "there",
    "when",
    "where",
    "why",
}


class MetaTagGeneratorInput(ToolInput):
    """Input schema matching Plan 16: url, target_keywords, page_content, length limits."""

    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(META_ACTIONS)}",
    )
    url: str = Field(
        ...,
        description="URL of the page to analyze and generate meta tags for. "
        "The page will be fetched automatically.",
    )
    target_keywords: list[str] = Field(
        ...,
        description="Target keywords to optimize for (e.g., ['seo tools', 'meta tags'])",
    )
    page_content: str | None = Field(
        None,
        description="Raw HTML content of the page. Takes precedence over url if both provided.",
    )
    max_title_length: int = Field(
        DEFAULT_TITLE_MAX_LENGTH,
        ge=20,
        le=120,
        description="Maximum character length for generated title",
    )
    max_description_length: int = Field(
        DEFAULT_DESC_MAX_LENGTH,
        ge=50,
        le=320,
        description="Maximum character length for generated description",
    )

    # Backward-compat aliases available via model_validator or property
    @property
    def focus_keywords(self) -> list[str] | None:
        """Backward compat: focus_keywords is an alias for target_keywords."""
        return self.target_keywords

    @property
    def html_content(self) -> str | None:
        """Backward compat: html_content is an alias for page_content."""
        return self.page_content


# ── Tool ──────────────────────────────────────────────────────────────


class MetaTagGeneratorTool(BaseTool):
    """Generate optimized meta title and description tags using TF-IDF."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="meta_tag_generator",
            name="Meta Tag Generator",
            description=(
                "Analyze HTML meta tags and generate SEO-optimized title "
                "and description tags using TF-IDF keyword analysis. "
                "Supports URL fetching, HTML content, and raw page content inputs."
            ),
            category="seo-marketing",
            input_schema=MetaTagGeneratorInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "existing_tags": {"type": "object"},
                    "suggestions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "score": {"type": "number"},
                            },
                        },
                    },
                    "issues": {"type": "array", "items": {"type": "string"}},
                    "success": {"type": "boolean"},
                },
            },
            tags=["seo", "meta-tags", "title", "description", "tf-idf", "optimization"],
            requires_auth=False,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = MetaTagGeneratorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.action not in META_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. "
                f"Use: {', '.join(META_ACTIONS)}",
            )

        # Resolve content source: page_content > url fetch
        html_content = validated.page_content
        if not html_content and validated.url:
            try:
                html_content = await self._fetch_url(validated.url)
            except Exception as e:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Failed to fetch URL '{validated.url}': {e}",
                )

        if not html_content and validated.action != "generate_title":
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="No content provided. Provide page_content, url, or html_content.",
            )

        # Store resolved HTML on validated for downstream use
        validated.page_content = html_content

        try:
            result = await self._execute_action(validated)
            result["success"] = True
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.warning("meta_tag_generator failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── URL fetching ─────────────────────────────────────────────

    async def _fetch_url(self, url: str) -> str:
        """Fetch HTML content from a URL with SSRF protection."""
        valid, error = _validate_url(url)
        if not valid:
            raise ValueError(f"URL validation failed: {error}")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; FlowmannerBot/1.0; "
                "+https://flowmanner.com/bot)"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(self, validated: MetaTagGeneratorInput) -> dict[str, Any]:
        """Route to the appropriate meta tag handler."""
        if validated.action == "analyze_meta":
            return await self._analyze_meta(validated)
        elif validated.action == "generate_title":
            return await self._generate_title(validated)
        elif validated.action == "generate_description":
            return await self._generate_description(validated)
        elif validated.action == "analyze_and_generate":
            return await self._analyze_and_generate(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}", "success": False}

    # ── Helpers ──────────────────────────────────────────────────

    def _parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML content with BeautifulSoup."""
        return BeautifulSoup(html, "lxml")

    def _extract_existing_meta(self, soup: BeautifulSoup) -> dict[str, str | None]:
        """Extract existing title and meta description from HTML."""
        title = None
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        description = None
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()

        # Also extract OG and Twitter tags for full picture
        og_title = None
        og_tag = soup.find("meta", property="og:title")
        if og_tag and og_tag.get("content"):
            og_title = og_tag["content"].strip()

        og_desc = None
        og_desc_tag = soup.find("meta", property="og:description")
        if og_desc_tag and og_desc_tag.get("content"):
            og_desc = og_desc_tag["content"].strip()

        twitter_title = None
        tw_tag = soup.find("meta", attrs={"name": "twitter:title"})
        if tw_tag and tw_tag.get("content"):
            twitter_title = tw_tag["content"].strip()

        return {
            "title": title,
            "description": description,
            "og_title": og_title,
            "og_description": og_desc,
            "twitter_title": twitter_title,
        }

    def _extract_text_content(self, soup: BeautifulSoup) -> str:
        """Extract meaningful text content from HTML body."""
        # Remove script and style elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        body = soup.body or soup
        text = body.get_text(separator=" ", strip=True)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text

    def _compute_tfidf_keywords(
        self, text: str, top_n: int = 15
    ) -> list[dict[str, Any]]:
        """Compute TF-IDF scores for words in text and return top keywords."""
        if not text or len(text) < 50:
            return []

        try:
            vectorizer = TfidfVectorizer(
                stop_words="english",
                max_features=200,
                ngram_range=(1, 2),
                strip_accents="unicode",
            )
            tfidf_matrix = vectorizer.fit_transform([text])
            feature_names = vectorizer.get_feature_names_out()
            scores = tfidf_matrix.toarray()[0]

            # Filter custom stopwords
            keyword_scores = []
            for name, score in zip(feature_names, scores, strict=False):
                if score > 0 and name.lower() not in _SEO_STOPWORDS and len(name) > 1:
                    keyword_scores.append(
                        {
                            "keyword": name,
                            "score": round(float(score), 4),
                        }
                    )

            keyword_scores.sort(key=lambda x: x["score"], reverse=True)
            return keyword_scores[:top_n]
        except Exception as e:
            logger.warning("TF-IDF computation failed: %s", e)
            return []

    # ── Action handlers ──────────────────────────────────────────

    async def _analyze_meta(self, validated: MetaTagGeneratorInput) -> dict[str, Any]:
        """Analyze existing meta tags and compute keyword relevance."""
        if not validated.page_content:
            return {
                "error": "page_content or url is required for analyze_meta",
                "success": False,
            }

        soup = self._parse_html(validated.page_content)
        meta = self._extract_existing_meta(soup)
        text = self._extract_text_content(soup)
        keywords = self._compute_tfidf_keywords(text)

        issues: list[str] = []
        existing_tags: dict[str, str | None] = {
            "title": meta["title"],
            "description": meta["description"],
            "og_title": meta["og_title"],
            "og_description": meta["og_description"],
            "twitter_title": meta["twitter_title"],
        }

        if meta["title"]:
            title_len = len(meta["title"])
            if title_len < 30:
                issues.append(
                    f"Title is too short ({title_len} chars). "
                    f"Aim for 50-{validated.max_title_length} chars."
                )
            elif title_len > validated.max_title_length:
                issues.append(
                    f"Title is too long ({title_len} chars). "
                    f"Keep under {validated.max_title_length} chars."
                )
        else:
            issues.append("No <title> tag found. Add one immediately.")

        if meta["description"]:
            desc_len = len(meta["description"])
            if desc_len < 70:
                issues.append(
                    f"Description is too short ({desc_len} chars). "
                    f"Aim for 120-{validated.max_description_length} chars."
                )
            elif desc_len > validated.max_description_length:
                issues.append(
                    f"Description is too long ({desc_len} chars). "
                    f"Keep under {validated.max_description_length} chars."
                )
        else:
            issues.append(
                "No meta description found. Add one for better SERP appearance."
            )

        if not meta["og_title"] and not meta["og_description"]:
            issues.append(
                "Missing Open Graph tags — social sharing previews will be limited."
            )

        # Check keyword relevance in title
        if validated.target_keywords and meta["title"]:
            title_lower = meta["title"].lower()
            present = [
                kw for kw in validated.target_keywords if kw.lower() in title_lower
            ]
            missing = [
                kw for kw in validated.target_keywords if kw.lower() not in title_lower
            ]
            if missing:
                issues.append(f"Missing target keywords in title: {', '.join(missing)}")

        # Build suggestions
        suggestions: list[dict[str, Any]] = []
        if validated.target_keywords:
            # Generate a suggested title + description
            title_result = await self._generate_title(validated)
            desc_result = await self._generate_description(validated)

            # Score based on keyword coverage
            top_kw_names = [k["keyword"] for k in keywords[:10]] if keywords else []
            kw_match = sum(
                1
                for kw in validated.target_keywords
                if any(kw.lower() in tk.lower() for tk in top_kw_names)
            )
            score = round((kw_match / max(len(validated.target_keywords), 1)) * 100)

            suggestions.append(
                {
                    "title": title_result.get("generated_title", ""),
                    "description": desc_result.get("generated_description", ""),
                    "score": score,
                }
            )

        return {
            "action": "analyze_meta",
            "existing_tags": existing_tags,
            "suggestions": suggestions,
            "top_keywords": keywords,
            "issues": issues,
            "success": True,
        }

    async def _generate_title(self, validated: MetaTagGeneratorInput) -> dict[str, Any]:
        """Generate an SEO-optimized title tag."""
        keywords = validated.target_keywords
        if not keywords:
            # Try to extract from content if available
            if validated.page_content:
                soup = self._parse_html(validated.page_content)
                text = self._extract_text_content(soup)
                tfidf_kw = self._compute_tfidf_keywords(text, top_n=5)
                keywords = [k["keyword"] for k in tfidf_kw[:3]]
            if not keywords:
                return {
                    "error": "target_keywords is required for generate_title",
                    "success": False,
                }

        # Build a title from primary keyword + secondary keywords
        primary = keywords[0].strip().title()
        secondary = (
            " | " + " & ".join(k.strip().title() for k in keywords[1:3])
            if len(keywords) > 1
            else ""
        )

        # If we have HTML content, enrich with site name or page context
        site_name = ""
        if validated.page_content:
            soup = self._parse_html(validated.page_content)
            meta = self._extract_existing_meta(soup)
            if meta["title"]:
                # Try to extract a site name from existing title (after separator)
                parts = re.split(r"\s*[|\-–—]\s*", meta["title"])
                if len(parts) > 1:
                    site_name = " | " + parts[-1].strip()

        # Assemble title
        title = f"{primary}{secondary}{site_name}"
        if len(title) > validated.max_title_length:
            # Truncate intelligently: keep primary + site name
            title = f"{primary}{site_name}"
            if len(title) > validated.max_title_length:
                title = title[: validated.max_title_length - 3].rstrip() + "..."

        return {
            "action": "generate_title",
            "generated_title": title,
            "length": len(title),
            "within_limit": len(title) <= validated.max_title_length,
            "success": True,
        }

    async def _generate_description(
        self, validated: MetaTagGeneratorInput
    ) -> dict[str, Any]:
        """Generate an SEO-optimized meta description."""
        keywords = validated.target_keywords
        if not keywords:
            if validated.page_content:
                soup = self._parse_html(validated.page_content)
                text = self._extract_text_content(soup)
                tfidf_kw = self._compute_tfidf_keywords(text, top_n=5)
                keywords = [k["keyword"] for k in tfidf_kw[:3]]
            if not keywords:
                return {
                    "error": "target_keywords is required for generate_description",
                    "success": False,
                }

        # Start with a value proposition using target keywords
        kw_list = ", ".join(kw for kw in keywords[:3])
        description = f"Discover everything about {kw_list}. "

        # Enrich with text content summary if available
        if validated.page_content:
            soup = self._parse_html(validated.page_content)
            text = self._extract_text_content(soup)
            # Get first meaningful sentence (up to ~100 chars)
            sentences = re.split(r"[.!?]+", text)
            if sentences:
                sentence = sentences[0].strip()
                if len(sentence) > 30:
                    description += f"{sentence[:100].rstrip()}. "
                if len(sentences) > 1:
                    sentence2 = sentences[1].strip()
                    if len(sentence2) > 20:
                        remaining = (
                            validated.max_description_length - len(description) - 1
                        )
                        if remaining > 20:
                            description += f"{sentence2[:remaining].rstrip()}."

        # Default CTA if still too short
        if len(description) < 80:
            description += (
                f"Learn more about {keywords[0]} with our comprehensive guide."
            )

        # Truncate to limit
        if len(description) > validated.max_description_length:
            # Find last complete word within limit
            truncated = description[: validated.max_description_length]
            last_space = truncated.rfind(" ")
            if last_space > 0:
                truncated = truncated[:last_space]
            description = truncated.rstrip(".,;:") + "..."

        return {
            "action": "generate_description",
            "generated_description": description,
            "length": len(description),
            "within_limit": len(description) <= validated.max_description_length,
            "success": True,
        }

    async def _analyze_and_generate(
        self, validated: MetaTagGeneratorInput
    ) -> dict[str, Any]:
        """Run full analysis and generate optimized tags."""
        analysis = await self._analyze_meta(validated)
        title_result = await self._generate_title(validated)
        desc_result = await self._generate_description(validated)

        return {
            "action": "analyze_and_generate",
            "existing_tags": analysis.get("existing_tags", {}),
            "generated_title": title_result.get("generated_title"),
            "title_length": title_result.get("length"),
            "generated_description": desc_result.get("generated_description"),
            "description_length": desc_result.get("length"),
            "suggestions": [
                {
                    "title": title_result.get("generated_title", ""),
                    "description": desc_result.get("generated_description", ""),
                    "score": (
                        100
                        if title_result.get("within_limit")
                        and desc_result.get("within_limit")
                        else 70
                    ),
                }
            ],
            "top_keywords": analysis.get("top_keywords"),
            "issues": analysis.get("issues", []),
            "success": True,
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(MetaTagGeneratorTool())
