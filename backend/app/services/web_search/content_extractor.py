"""
Content extraction service for web search.
Extracts and processes content from web pages.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExtractedContent:
    """Extracted content from a web page."""

    url: str
    title: str
    text: str
    html: str | None = None
    metadata: dict[str, Any] = None
    links: list[str] = None
    images: list[dict[str, str]] = None
    quality_score: float = 0.0

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.links is None:
            self.links = []
        if self.images is None:
            self.images = []


class ContentExtractor:
    """Extract and process content from web pages."""

    def __init__(self):
        self.min_text_length = 100
        self.max_text_length = 50000
        self._playwright = None
        self._browser = None

    async def _get_playwright_browser(self):
        """Get or create Playwright browser instance."""
        if self._browser is None:
            try:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)
            except ImportError:
                logger.warning("Playwright not installed, falling back to HTTP-only extraction")
                return None
        return self._browser

    async def extract(self, url: str, use_javascript: bool = False) -> ExtractedContent:
        """Extract content from a URL.

        Args:
            url: URL to extract content from
            use_javascript: Whether to use JavaScript rendering

        Returns:
            ExtractedContent object
        """
        if use_javascript:
            return await self._extract_with_playwright(url)
        else:
            return await self._extract_with_http(url)

    async def _extract_with_http(self, url: str) -> ExtractedContent:
        """Extract content using HTTP requests."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        return ExtractedContent(url=url, title="", text="", quality_score=0.0)

                    html = await response.text()
                    return self._parse_html(url, html)
        except Exception as e:
            logger.error("HTTP extraction failed for %s: %s", url, e)
            return ExtractedContent(url=url, title="", text="", quality_score=0.0)

    async def _extract_with_playwright(self, url: str) -> ExtractedContent:
        """Extract content using Playwright for JavaScript rendering."""
        browser = await self._get_playwright_browser()
        if browser is None:
            return await self._extract_with_http(url)

        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            html = await page.content()
            await page.close()
            return self._parse_html(url, html)
        except Exception as e:
            logger.error("Playwright extraction failed for %s: %s", url, e)
            return await self._extract_with_http(url)

    def _parse_html(self, url: str, html: str) -> ExtractedContent:
        """Parse HTML and extract content."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("BeautifulSoup not installed")
            return ExtractedContent(url=url, title="", text="", quality_score=0.0)

        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()

        # Extract title
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)

        # Extract metadata
        metadata = {}
        for meta in soup.find_all("meta"):
            name = str(meta.get("name") or meta.get("property", ""))
            content = str(meta.get("content", ""))
            if name and content:
                metadata[name] = content

        # Extract main content
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile(r"content|article|post|entry", re.I))
            or soup.find("div", id=re.compile(r"content|article|post|entry", re.I))
            or soup.body
        )

        text = ""
        if main_content:
            # Extract text with proper newline escaping
            text = main_content.get_text(separator="\n", strip=True)

            # Clean up whitespace
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            text = "\n".join(lines)

        # Extract links
        links = []
        for a in soup.find_all("a", href=True):
            href = str(a["href"])
            if href.startswith("http"):
                links.append(href)

        # Extract images
        images = []
        for img in soup.find_all("img", src=True):
            images.append({"src": str(img["src"]), "alt": str(img.get("alt", ""))})

        # Calculate quality score
        quality_score = self._calculate_quality(text, metadata)

        return ExtractedContent(
            url=url,
            title=title,
            text=text[: self.max_text_length],
            html=html,
            metadata=metadata,
            links=links[:50],
            images=images[:20],
            quality_score=quality_score,
        )

    def _calculate_quality(self, text: str, metadata: dict[str, Any]) -> float:
        """Calculate content quality score."""
        score = 0.0

        # Text length score
        text_len = len(text)
        if text_len >= self.min_text_length:
            score += 0.3
        if text_len >= 500:
            score += 0.2
        if text_len >= 1000:
            score += 0.1

        # Metadata score
        if metadata.get("description"):
            score += 0.2
        if metadata.get("author"):
            score += 0.1
        if metadata.get("og:type"):
            score += 0.1

        return min(score, 1.0)

    async def close(self):
        """Clean up resources."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


# Convenience functions
async def extract_content(url: str, use_javascript: bool = False) -> ExtractedContent:
    """Extract content from a URL."""
    extractor = ContentExtractor()
    try:
        return await extractor.extract(url, use_javascript)
    finally:
        await extractor.close()


def extract_text_from_html(html: str) -> str:
    """Extract plain text from HTML string."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        # Get text with proper newline handling
        text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)
    except Exception as e:
        logger.error("HTML text extraction failed: %s", e)
        return ""
