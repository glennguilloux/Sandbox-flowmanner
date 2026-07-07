"""
SEO & Marketing Tools — SEO Content Scorer.

seo_content_scorer → Score HTML drafts against focus keywords using TF-IDF
    analysis, readability checks, and meta tag audits. Supports competitor
    URL benchmarking with content comparison.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
from collections import Counter
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

        try:
            addr = ipaddress.ip_address(hostname_lower)
        except ValueError:
            pass
        else:
            for net in _BLOCKED_NETWORKS:
                if addr in net:
                    return False, f"IP address '{hostname}' is in blocked range {net}"

        return True, None
    except Exception as e:
        return False, f"URL validation error: {e}"


# ── Configuration ─────────────────────────────────────────────────────

DEFAULT_TARGET_GRADE = int(os.getenv("SEO_TARGET_READING_GRADE", "8"))
FETCH_TIMEOUT = int(os.getenv("SEO_FETCH_TIMEOUT", "15"))

# ── Input ─────────────────────────────────────────────────────────────

SEO_ACTIONS = (
    "score_content",
    "analyze_readability",
    "check_meta",
    "full_audit",
)


class SeoContentScorerInput(ToolInput):
    """Input schema: content, target_keywords, url, reading_level_target, competitor_urls."""

    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(SEO_ACTIONS)}",
    )
    content: str = Field(
        ...,
        description="Raw HTML content to score for SEO quality",
    )
    target_keywords: list[str] = Field(
        ...,
        description="Target keywords the content should rank for",
    )
    url: str | None = Field(
        None,
        description="Target URL to fetch and analyze. Used if content is not provided directly.",
    )
    reading_level_target: str | None = Field(
        "grade-8",
        description="Target reading level (e.g., 'grade-6', 'grade-8', 'grade-12')",
    )
    competitor_urls: list[str] | None = Field(
        None,
        description="Competitor URLs to fetch and benchmark against. "
        "Each competitor is scored and compared side-by-side.",
    )
    max_issues: int = Field(
        20,
        ge=1,
        le=100,
        description="Maximum number of issues to return",
    )

    # Backward-compat aliases
    @property
    def html_content(self) -> str | None:
        """Backward compat: html_content is an alias for content."""
        return self.content

    @property
    def focus_keywords(self) -> list[str] | None:
        """Backward compat: focus_keywords is an alias for target_keywords."""
        return self.target_keywords

    def _parse_reading_level(self) -> int:
        """Parse reading_level_target string like 'grade-8' into int."""
        if not self.reading_level_target:
            return DEFAULT_TARGET_GRADE
        match = re.search(r"(\d+)", self.reading_level_target)
        if match:
            return int(match.group(1))
        return DEFAULT_TARGET_GRADE


# ── Tool ──────────────────────────────────────────────────────────────


class SeoContentScorerTool(BaseTool):
    """Score SEO content quality with readability and keyword analysis."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="seo_content_scorer",
            name="SEO Content Scorer",
            description=(
                "Score HTML drafts against focus keywords using TF-IDF analysis, "
                "readability checks, and meta tag audits for comprehensive SEO scoring. "
                "Supports competitor URL benchmarking with side-by-side comparison."
            ),
            category="seo-marketing",
            input_schema=SeoContentScorerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "overall_score": {"type": "number"},
                    "breakdown": {
                        "type": "object",
                        "properties": {
                            "keyword_score": {"type": "number"},
                            "readability_score": {"type": "number"},
                            "structure_score": {"type": "number"},
                            "meta_score": {"type": "number"},
                        },
                    },
                    "reading_level": {"type": "string"},
                    "keyword_analysis": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "keyword": {"type": "string"},
                                "found": {"type": "boolean"},
                                "count": {"type": "integer"},
                                "density_pct": {"type": "number"},
                                "positions": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "issues": {"type": "array", "items": {"type": "string"}},
                    "recommendations": {"type": "array", "items": {"type": "string"}},
                    "success": {"type": "boolean"},
                },
            },
            tags=[
                "seo",
                "content-scoring",
                "readability",
                "tf-idf",
                "keyword-analysis",
            ],
            requires_auth=False,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SeoContentScorerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if validated.action not in SEO_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(SEO_ACTIONS)}",
            )

        # Resolve content: content > url fetch
        html_content = validated.content
        if not html_content and validated.url:
            try:
                html_content = await self._fetch_url(validated.url)
                validated.content = html_content
            except Exception as e:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Failed to fetch URL '{validated.url}': {e}",
                )

        try:
            result = await self._execute_action(validated)
            result["success"] = True
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.warning("seo_content_scorer failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── URL fetching ─────────────────────────────────────────────

    async def _fetch_url(self, url: str) -> str:
        """Fetch HTML content from a URL with SSRF protection."""
        valid, error = _validate_url(url)
        if not valid:
            raise ValueError(f"URL validation failed: {error}")

        headers = {
            "User-Agent": ("Mozilla/5.0 (compatible; FlowmannerBot/1.0; +https://flowmanner.com/bot)"),
            "Accept": "text/html,application/xhtml+xml",
        }
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text

    async def _fetch_competitors(self, urls: list[str]) -> dict[str, str]:
        """Fetch competitor pages in parallel."""
        results: dict[str, str] = {}
        tasks = [self._fetch_competitor_safe(u, results) for u in urls]

        await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def _fetch_competitor_safe(self, url: str, results: dict[str, str]) -> None:
        """Fetch a single competitor safely, storing result or error."""
        try:
            results[url] = await self._fetch_url(url)
        except Exception as e:
            logger.warning("Failed to fetch competitor %s: %s", url, e)
            results[url] = f"__ERROR__: {e}"

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(self, validated: SeoContentScorerInput) -> dict[str, Any]:
        if validated.action == "score_content":
            return await self._score_content(validated)
        elif validated.action == "analyze_readability":
            return await self._analyze_readability(validated)
        elif validated.action == "check_meta":
            return await self._check_meta(validated)
        elif validated.action == "full_audit":
            return await self._full_audit(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}", "success": False}

    # ── Core helpers ─────────────────────────────────────────────

    def _parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    def _extract_text(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        body = soup.body or soup
        text = body.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text)

    def _extract_headings(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        headings = []
        for level in range(1, 7):
            for tag in soup.find_all(f"h{level}"):
                text = tag.get_text(strip=True)
                if text:
                    headings.append({"level": level, "text": text})
        return headings

    def _extract_links(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        links = []
        for tag in soup.find_all("a", href=True):
            text = tag.get_text(strip=True)
            href = tag["href"]
            if text:
                links.append({"text": text, "href": href})
        return links

    def _extract_images(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        return [
            {
                "src": tag.get("src", ""),
                "alt": tag.get("alt", ""),
                "has_alt": bool(tag.get("alt", "").strip()),
            }
            for tag in soup.find_all("img")
        ]

    def _extract_meta(self, soup: BeautifulSoup) -> dict[str, str | None]:
        title = None
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        description = None
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()

        h1 = None
        h1_tag = soup.find("h1")
        if h1_tag:
            h1 = h1_tag.get_text(strip=True)

        return {"title": title, "description": description, "h1": h1}

    def _word_count(self, text: str) -> int:
        return len(re.findall(r"[a-zA-Z0-9]+(?:'[a-zA-Z]+)?", text))

    def _sentence_count(self, text: str) -> int:
        return len(re.findall(r"[.!?]+", text))

    def _syllable_count(self, text: str) -> int:
        """Approximate syllable count for English text."""
        text = text.lower()
        text = re.sub(r"[^a-z]", " ", text)
        words = text.split()
        count = 0
        for word in words:
            word = word.strip()
            if not word:
                continue
            syllables = len(re.findall(r"[aeiouy]+", word))
            if word.endswith("e") and syllables > 1:
                syllables -= 1
            count += max(syllables, 1)
        return count

    def _flesch_kincaid_grade(self, text: str) -> float:
        words = max(self._word_count(text), 1)
        sentences = max(self._sentence_count(text), 1)
        syllables = self._syllable_count(text)
        grade = (0.39 * (words / sentences)) + (11.8 * (syllables / words)) - 15.59
        return round(max(0, grade), 1)

    def _flesch_reading_ease(self, text: str) -> float:
        words = max(self._word_count(text), 1)
        sentences = max(self._sentence_count(text), 1)
        syllables = self._syllable_count(text)
        ease = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
        return round(max(0, min(100, ease)), 1)

    def _gunning_fog(self, text: str) -> float:
        """Gunning Fog Index."""
        words = max(self._word_count(text), 1)
        sentences = max(self._sentence_count(text), 1)

        # Count complex words (3+ syllables)
        text_lower = text.lower()
        text_lower = re.sub(r"[^a-z]", " ", text_lower)
        complex_count = 0
        for word in text_lower.split():
            syllables = len(re.findall(r"[aeiouy]+", word))
            if word.endswith("e") and syllables > 1:
                syllables -= 1
            if max(syllables, 1) >= 3:
                complex_count += 1

        fog = 0.4 * ((words / sentences) + 100 * (complex_count / max(words, 1)))
        return round(max(0, fog), 1)

    def _smog_index(self, text: str) -> float:
        """SMOG Readability Index."""
        sentences = max(self._sentence_count(text), 1)

        # Count polysyllabic words (3+ syllables)
        text_lower = text.lower()
        text_lower = re.sub(r"[^a-z]", " ", text_lower)
        poly_count = 0
        for word in text_lower.split():
            if not word:
                continue
            syllables = len(re.findall(r"[aeiouy]+", word))
            if word.endswith("e") and syllables > 1:
                syllables -= 1
            if max(syllables, 1) >= 3:
                poly_count += 1

        if sentences < 30:
            return 0.0  # SMOG requires 30+ sentences for accuracy

        smog = 1.043 * ((poly_count * (30.0 / sentences)) ** 0.5) + 3.1291
        return round(max(0, smog), 1)

    def _keyword_coverage(self, text: str, keywords: list[str]) -> list[dict[str, Any]]:
        """Analyze keyword coverage with positions in text."""
        text_lower = text.lower()
        total_words = max(self._word_count(text), 1)

        results = []
        for kw in keywords:
            kw_lower = kw.lower()
            if " " in kw_lower:
                pattern = re.escape(kw_lower)
                count = len(re.findall(pattern, text_lower))
                # Find positions (sentence contexts)
                positions = []
                for m in re.finditer(pattern, text_lower):
                    start = max(0, m.start() - 40)
                    end = min(len(text_lower), m.end() + 40)
                    context = text_lower[start:end].strip()
                    positions.append(f"...{context}...")
            else:
                words_list = re.findall(r"[a-zA-Z0-9]+(?:'[a-zA-Z]+)?", text_lower)
                count = Counter(words_list).get(kw_lower, 0)
                positions = []
                # Find sentence-level positions
                sentences = re.split(r"(?<=[.!?])\s+", text)
                for s in sentences:
                    if kw_lower in s.lower():
                        positions.append(s.strip()[:100])

            results.append(
                {
                    "keyword": kw,
                    "found": count > 0,
                    "count": count,
                    "density_pct": round((count / total_words) * 100, 2),
                    "positions": positions[:5],  # Limit to 5 positions
                }
            )

        return results

    def _compute_tfidf(self, text: str, top_n: int = 10) -> list[dict[str, Any]]:
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

            keyword_scores = []
            for name, score in zip(feature_names, scores, strict=False):
                if score > 0 and len(name) > 1:
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

    def _reading_ease_label(self, ease: float) -> str:
        if ease >= 90:
            return "Very Easy"
        elif ease >= 80:
            return "Easy"
        elif ease >= 70:
            return "Fairly Easy"
        elif ease >= 60:
            return "Standard"
        elif ease >= 50:
            return "Fairly Difficult"
        elif ease >= 30:
            return "Difficult"
        else:
            return "Very Difficult"

    def _grade_label(self, score: int) -> str:
        if score >= 90:
            return "A+"
        elif score >= 85:
            return "A"
        elif score >= 80:
            return "A-"
        elif score >= 75:
            return "B+"
        elif score >= 70:
            return "B"
        elif score >= 65:
            return "B-"
        elif score >= 60:
            return "C+"
        elif score >= 55:
            return "C"
        elif score >= 50:
            return "D"
        else:
            return "F"

    # ── Action handlers ──────────────────────────────────────────

    async def _score_content(self, validated: SeoContentScorerInput) -> dict[str, Any]:
        """Score content comprehensively for SEO per Plan 16: 40% keyword, 30% readability, 20% structure, 10% meta."""
        if not validated.content:
            return {
                "error": "content or url is required for score_content",
                "success": False,
            }

        soup = self._parse_html(validated.content)
        text = self._extract_text(soup)
        word_count = self._word_count(text)
        meta = self._extract_meta(soup)
        headings = self._extract_headings(soup)
        images = self._extract_images(soup)
        links = self._extract_links(soup)

        issues: list[str] = []
        recommendations: list[str] = []

        # -- Keyword score (40%) --
        keyword_score = 0.0
        keyword_analysis: list[dict[str, Any]] = []

        if validated.target_keywords:
            keyword_analysis = self._keyword_coverage(text, validated.target_keywords)
            found_count = sum(1 for k in keyword_analysis if k["found"])
            total_kw = len(validated.target_keywords)
            keyword_score = (found_count / total_kw) * 40

            for kw_info in keyword_analysis:
                if kw_info["found"]:
                    if kw_info["density_pct"] < 0.5:
                        issues.append(
                            f"Keyword '{kw_info['keyword']}' found but density is low "
                            f"({kw_info['density_pct']}%). Consider more usage."
                        )
                else:
                    issues.append(f"Keyword '{kw_info['keyword']}' not found in content")
                    recommendations.append(f"Add '{kw_info['keyword']}' naturally into headings and body text.")
        else:
            issues.append("No target keywords provided for scoring")
            recommendations.append("Provide target_keywords for accurate keyword scoring.")

        # -- Readability score (30%) --
        reading_target = validated._parse_reading_level()
        grade = self._flesch_kincaid_grade(text)
        ease = self._flesch_reading_ease(text)
        fog = self._gunning_fog(text)
        smog = self._smog_index(text)

        diff = abs(grade - reading_target)
        if diff <= 1:
            readability_score = 30
        elif diff <= 3:
            readability_score = 22
        elif diff <= 5:
            readability_score = 15
        else:
            readability_score = 8

        if grade > reading_target + 2:
            issues.append(
                f"Reading level is too high (grade {grade} vs target {reading_target}). "
                "Simplify vocabulary and shorten sentences."
            )
            recommendations.append("Use shorter sentences and simpler words to lower reading level.")
        elif grade < reading_target - 2:
            issues.append(
                f"Reading level is below target (grade {grade} vs target {reading_target}). "
                "Add more sophisticated vocabulary if appropriate."
            )

        # -- Structure score (20%) --
        structure_score = 0.0

        # Word count
        if word_count >= 1500:
            structure_score += 8
        elif word_count >= 800:
            structure_score += 6
        elif word_count >= 300:
            structure_score += 4
        else:
            structure_score += 1
            issues.append(f"Content is thin ({word_count} words). Aim for 800+ words.")

        # Headings
        h1_count = sum(1 for h in headings if h["level"] == 1)
        h2_count = sum(1 for h in headings if h["level"] == 2)
        if h1_count == 1:
            structure_score += 6
        elif h1_count == 0:
            issues.append("Missing H1 tag.")
            recommendations.append("Add exactly one H1 tag with your primary keyword.")
        else:
            issues.append(f"Multiple H1 tags ({h1_count}). Use only one.")
            structure_score += 3

        if h2_count >= 2:
            structure_score += 6
        elif h2_count == 1:
            structure_score += 3
        else:
            issues.append("No H2 tags found. Use H2s to structure sections.")
            recommendations.append("Add H2 tags to break content into scannable sections.")

        # -- Meta score (10%) --
        meta_score = 0.0
        if meta["title"]:
            tl = len(meta["title"])
            if 50 <= tl <= 60:
                meta_score += 5
            elif 30 <= tl <= 70:
                meta_score += 3
            else:
                meta_score += 1
                issues.append(f"Title length ({tl} chars) is suboptimal. Aim for 50-60.")
        else:
            issues.append("Missing <title> tag.")
            recommendations.append("Add a <title> tag with your primary keyword.")

        if meta["description"]:
            dl = len(meta["description"])
            if 120 <= dl <= 160:
                meta_score += 3
            elif 70 <= dl <= 200:
                meta_score += 2
            else:
                meta_score += 1
        else:
            meta_score += 0
            issues.append("Missing meta description.")
            recommendations.append("Add a meta description (120-160 chars) with target keywords.")

        if meta["h1"]:
            meta_score += 2

        # Composite score
        overall_score = round(keyword_score + readability_score + structure_score + meta_score)
        grade_label = self._grade_label(int(overall_score))

        # Competitor comparison
        competitor_results = None
        if validated.competitor_urls:
            competitor_html = await self._fetch_competitors(validated.competitor_urls)
            competitor_scores: list[dict[str, Any]] = []
            for comp_url, comp_html in competitor_html.items():
                if comp_html.startswith("__ERROR__"):
                    competitor_scores.append(
                        {
                            "url": comp_url,
                            "error": comp_html.replace("__ERROR__: ", ""),
                            "overall_score": 0,
                        }
                    )
                    continue
                # Quick score for competitor
                comp_soup = self._parse_html(comp_html)
                comp_text = self._extract_text(comp_soup)
                comp_wc = self._word_count(comp_text)
                comp_grade = self._flesch_kincaid_grade(comp_text)

                # Simple competitor scoring
                comp_kw_score = 0.0
                if validated.target_keywords:
                    comp_cov = self._keyword_coverage(comp_text, validated.target_keywords)
                    comp_kw_score = (sum(1 for k in comp_cov if k["found"]) / max(len(comp_cov), 1)) * 40

                comp_read_score = max(0, 30 - abs(comp_grade - reading_target) * 5)
                comp_struct_score = min(20, (comp_wc / 1500) * 20)
                comp_total = round(comp_kw_score + comp_read_score + comp_struct_score)
                comp_grade_label = self._grade_label(int(comp_total))

                competitor_scores.append(
                    {
                        "url": comp_url,
                        "overall_score": comp_total,
                        "grade": comp_grade_label,
                        "word_count": comp_wc,
                        "reading_grade": comp_grade,
                    }
                )

            competitor_results = {
                "count": len(competitor_scores),
                "competitors": competitor_scores,
                "your_score": overall_score,
                "ranking": sorted(
                    [{"source": "You", "score": overall_score}]
                    + [{"source": c["url"], "score": c["overall_score"]} for c in competitor_scores],
                    key=lambda x: x["score"],
                    reverse=True,
                ),
            }

        return {
            "action": "score_content",
            "overall_score": overall_score,
            "grade": grade_label,
            "breakdown": {
                "keyword_score": round(keyword_score, 1),
                "readability_score": round(readability_score, 1),
                "structure_score": round(structure_score, 1),
                "meta_score": round(meta_score, 1),
            },
            "reading_level": f"Grade {grade} (target: grade-{reading_target})",
            "readability": {
                "flesch_kincaid_grade": grade,
                "flesch_reading_ease": ease,
                "gunning_fog": fog,
                "smog_index": smog,
                "label": self._reading_ease_label(ease),
            },
            "word_count": word_count,
            "heading_count": len(headings),
            "image_count": len(images),
            "link_count": len(links),
            "keyword_analysis": keyword_analysis,
            "issues": issues[: validated.max_issues],
            "recommendations": recommendations[: validated.max_issues],
            "competitor_benchmark": competitor_results,
            "success": True,
        }

    async def _analyze_readability(self, validated: SeoContentScorerInput) -> dict[str, Any]:
        """Analyze readability of text content with multiple metrics."""
        if not validated.content:
            return {
                "error": "content or url is required for analyze_readability",
                "success": False,
            }

        soup = self._parse_html(validated.content)
        text = self._extract_text(soup)

        grade = self._flesch_kincaid_grade(text)
        ease = self._flesch_reading_ease(text)
        fog = self._gunning_fog(text)
        smog = self._smog_index(text)
        word_count = self._word_count(text)
        sentence_count = self._sentence_count(text)
        avg_sentence_length = round(word_count / max(sentence_count, 1), 1)
        syllable_count = self._syllable_count(text)
        avg_syllables_per_word = round(syllable_count / max(word_count, 1), 2)

        reading_target = validated._parse_reading_level()
        issues: list[str] = []
        recommendations: list[str] = []
        diff = abs(grade - reading_target)

        if diff <= 1:
            pass  # on target
        elif diff <= 3:
            issues.append(f"Reading grade ({grade}) is {diff} levels off target ({reading_target})")
        else:
            issues.append(f"Reading grade ({grade}) is significantly off target ({reading_target}).")
            if grade > reading_target:
                recommendations.append("Shorten sentences and use simpler words.")
            else:
                recommendations.append("Use more sophisticated vocabulary and longer sentences.")

        if avg_sentence_length > 25:
            issues.append(f"Sentences are long (avg {avg_sentence_length} words).")
            recommendations.append("Break up sentences longer than 25 words.")
        elif avg_sentence_length < 5 and sentence_count > 2:
            issues.append(f"Sentences are very short (avg {avg_sentence_length} words).")

        if avg_syllables_per_word > 2.0:
            issues.append(f"High syllable count per word ({avg_syllables_per_word}).")
            recommendations.append("Replace complex words with simpler alternatives.")

        readability_score = round(max(0, min(100, (ease * 0.7) + (10 - diff) * 3)))

        return {
            "action": "analyze_readability",
            "flesch_kincaid_grade": grade,
            "flesch_reading_ease": ease,
            "gunning_fog": fog,
            "smog_index": smog,
            "reading_ease_label": self._reading_ease_label(ease),
            "reading_level": f"Grade {grade} (target: grade-{reading_target})",
            "target_grade": reading_target,
            "grade_diff": round(diff, 1),
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_sentence_length": avg_sentence_length,
            "avg_syllables_per_word": avg_syllables_per_word,
            "readability_score": readability_score,
            "issues": issues[: validated.max_issues],
            "recommendations": recommendations[: validated.max_issues],
            "success": True,
        }

    async def _check_meta(self, validated: SeoContentScorerInput) -> dict[str, Any]:
        """Audit meta tags for SEO best practices."""
        if not validated.content:
            return {
                "error": "content or url is required for check_meta",
                "success": False,
            }

        soup = self._parse_html(validated.content)
        meta = self._extract_meta(soup)

        issues: list[str] = []
        recommendations: list[str] = []

        # Title check
        if not meta["title"]:
            issues.append("Missing <title> tag — critical for SEO")
            recommendations.append("Add a <title> tag (50-60 chars) with your primary keyword.")
        else:
            title_len = len(meta["title"])
            if title_len < 30:
                issues.append(f"Title too short ({title_len} chars). Aim for 50-60.")
            elif title_len > 70:
                issues.append(f"Title too long ({title_len} chars). Keep under 60.")

        # Description check
        if not meta["description"]:
            issues.append("Missing meta description — important for CTR")
            recommendations.append("Add a meta description (120-160 chars) with target keywords.")
        else:
            desc_len = len(meta["description"])
            if desc_len < 70:
                issues.append(f"Description too short ({desc_len} chars). Aim for 120-160.")
            elif desc_len > 160:
                issues.append(f"Description too long ({desc_len} chars). Keep under 160.")

            if validated.target_keywords and meta["description"]:
                present = [kw for kw in validated.target_keywords if kw.lower() in meta["description"].lower()]
                if not present:
                    issues.append("No target keywords found in meta description")
                    recommendations.append("Include target keywords naturally in meta description.")

        # H1 check
        if not meta["h1"]:
            issues.append("Missing H1 tag — every page needs one")
            recommendations.append("Add exactly one H1 tag that includes your primary keyword.")
        elif validated.target_keywords:
            h1_lower = meta["h1"].lower()
            present = [kw for kw in validated.target_keywords if kw.lower() in h1_lower]
            if not present:
                issues.append("No target keywords found in H1")
                recommendations.append("Include your primary keyword in the H1 tag.")

        # Viewport, canonical, OG, robots
        viewport = soup.find("meta", attrs={"name": "viewport"})
        if not viewport:
            issues.append("Missing viewport meta tag — important for mobile SEO")

        canonical = soup.find("link", rel="canonical")
        if not canonical:
            issues.append("Missing canonical URL tag")

        og_title = soup.find("meta", property="og:title")
        if not og_title:
            issues.append("Missing Open Graph tags — social sharing previews won't render well")
            recommendations.append("Add og:title, og:description, and og:image meta tags.")

        robots = soup.find("meta", attrs={"name": "robots"})
        if robots:
            content = robots.get("content", "")
            if "noindex" in content:
                issues.append("Page has 'noindex' — will not appear in search results")

        return {
            "action": "check_meta",
            "title": meta["title"],
            "title_length": len(meta["title"]) if meta["title"] else 0,
            "description": meta["description"],
            "description_length": (len(meta["description"]) if meta["description"] else 0),
            "h1": meta["h1"],
            "issues": issues[: validated.max_issues],
            "recommendations": recommendations[: validated.max_issues],
            "success": True,
        }

    async def _full_audit(self, validated: SeoContentScorerInput) -> dict[str, Any]:
        """Run a comprehensive SEO audit combining all checks."""
        if not validated.content:
            return {
                "error": "content or url is required for full_audit",
                "success": False,
            }

        content_result = await self._score_content(validated)
        readability_result = await self._analyze_readability(validated)
        meta_result = await self._check_meta(validated)

        all_issues = (
            content_result.get("issues", []) + readability_result.get("issues", []) + meta_result.get("issues", [])
        )
        all_recommendations = (
            content_result.get("recommendations", [])
            + readability_result.get("recommendations", [])
            + meta_result.get("recommendations", [])
        )

        # Weighted composite: 40% keyword, 30% readability, 20% structure, 10% meta
        breakdown = content_result.get("breakdown", {})
        composite = round(
            breakdown.get("keyword_score", 0)
            + breakdown.get("readability_score", 0)
            + breakdown.get("structure_score", 0)
            + breakdown.get("meta_score", 0)
        )
        grade = self._grade_label(composite)

        return {
            "action": "full_audit",
            "overall_score": composite,
            "grade": grade,
            "breakdown": breakdown,
            "reading_level": readability_result.get("reading_level", "Unknown"),
            "readability": {
                "grade_level": readability_result.get("flesch_kincaid_grade"),
                "reading_ease": readability_result.get("flesch_reading_ease"),
                "gunning_fog": readability_result.get("gunning_fog"),
                "smog_index": readability_result.get("smog_index"),
                "label": readability_result.get("reading_ease_label"),
            },
            "word_count": content_result.get("word_count"),
            "heading_count": content_result.get("heading_count"),
            "image_count": content_result.get("image_count"),
            "link_count": content_result.get("link_count"),
            "keyword_analysis": content_result.get("keyword_analysis", []),
            "issues": all_issues[: validated.max_issues],
            "recommendations": all_recommendations[: validated.max_issues],
            "issue_count": len(all_issues),
            "competitor_benchmark": content_result.get("competitor_benchmark"),
            "success": True,
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(SeoContentScorerTool())
