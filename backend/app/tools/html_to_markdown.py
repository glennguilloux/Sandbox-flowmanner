"""
Web Scraping Tools — HTML to Markdown Converter.

html_to_markdown → Convert raw HTML pages into clean, LLM-friendly Markdown text.
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from pydantic import Field

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


# ── HTML → Markdown converter ─────────────────────────────────────────────

class _MarkdownConverter(HTMLParser):
    """Convert HTML to Markdown."""

    SKIP_TAGS = {"script", "style", "noscript", "iframe", "svg"}

    INLINE_TAGS = {
        "b", "strong", "i", "em", "code", "a", "span",
        "sub", "sup", "del", "ins", "mark", "small", "abbr",
    }

    BLOCK_TAGS = {"p", "div", "section", "article", "main", "aside",
                  "header", "footer", "nav", "blockquote"}

    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self, base_url: str = ""):
        super().__init__()
        self.output: list[str] = []
        self.skip_depth = 0
        self.base_url = base_url
        self._list_stack: list[str] = []  # "ul" or "ol"
        self._list_idx: list[int] = [0]
        self._link_href: str = ""
        self._in_pre = False
        self._pre_content: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = dict(attrs)

        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        if self.skip_depth > 0:
            return

        if tag in self.HEADING_TAGS:
            level = int(tag[1])
            self.output.append(f"\n\n{'#' * level} ")
        elif tag == "br":
            self.output.append("\n")
        elif tag == "hr":
            self.output.append("\n\n---\n\n")
        elif tag == "img":
            src = attrs_dict.get("src", "")
            alt = attrs_dict.get("alt", "image")
            if src:
                src = urljoin(self.base_url, src)
            self.output.append(f"![{alt}]({src})")
        elif tag == "a":
            self._link_href = attrs_dict.get("href", "")
            if self._link_href:
                self._link_href = urljoin(self.base_url, self._link_href)
            self.output.append("[")
        elif tag in ("b", "strong"):
            self.output.append("**")
        elif tag in ("i", "em"):
            self.output.append("*")
        elif tag == "code" and not self._in_pre:
            self.output.append("`")
        elif tag == "pre":
            self._in_pre = True
            self._pre_content = []
        elif tag == "li":
            self.output.append("\n")
            if self._list_stack and self._list_stack[-1] == "ol":
                self._list_idx[-1] += 1
                self.output.append(f"{self._list_idx[-1]}. ")
            else:
                self.output.append("- ")
        elif tag == "ul":
            self._list_stack.append("ul")
            self._list_idx.append(0)
            self.output.append("\n")
        elif tag == "ol":
            self._list_stack.append("ol")
            self._list_idx.append(0)
            self.output.append("\n")
        elif tag == "blockquote":
            self.output.append("\n\n> ")
        elif tag in ("p", "div", "section", "article"):
            if self.output and not self.output[-1].endswith("\n\n"):
                self.output.append("\n\n")

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in self.SKIP_TAGS:
            if self.skip_depth > 0:
                self.skip_depth -= 1
            return

        if self.skip_depth > 0:
            return

        if tag in self.HEADING_TAGS:
            self.output.append("\n\n")
        elif tag == "a":
            if self._link_href:
                self.output.append(f"]({self._link_href})")
            else:
                self.output.append("]()")
            self._link_href = ""
        elif tag in ("b", "strong"):
            self.output.append("**")
        elif tag in ("i", "em"):
            self.output.append("*")
        elif tag == "code" and not self._in_pre:
            self.output.append("`")
        elif tag == "pre":
            if self._pre_content:
                code = "".join(self._pre_content).strip()
                self.output.append(f"\n\n```\n{code}\n```\n\n")
            self._in_pre = False
            self._pre_content = []
        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
                self._list_idx.pop()
            self.output.append("\n")
        elif tag in ("p", "div", "section", "article") and not self.output[-1].endswith("\n\n"):
            self.output.append("\n\n")

    def handle_data(self, data):
        if self.skip_depth > 0:
            return
        if self._in_pre:
            self._pre_content.append(data)
            return
        text = data.replace("\n", " ").replace("\r", "")
        if text.strip():
            self.output.append(text)

    def get_markdown(self) -> str:
        raw = "".join(self.output)
        # Clean up excessive whitespace
        raw = re.sub(r"\n{4,}", "\n\n\n", raw)
        raw = re.sub(r" {2,}", " ", raw)
        # Remove trailing whitespace on each line
        raw = "\n".join(line.rstrip() for line in raw.split("\n"))
        return raw.strip()


# ── Input ─────────────────────────────────────────────────────────────────

class HtmlToMarkdownInput(ToolInput):
    data: str | None = Field(
        None,
        description="Raw HTML string or Base64-encoded HTML content",
    )
    url: str | None = Field(
        None,
        description="URL to fetch HTML from (optional if 'data' is provided)",
    )
    strip_images: bool = Field(
        False,
        description="Remove all image references from output",
    )
    preserve_links: bool = Field(
        True,
        description="Keep hyperlinks in Markdown format",
    )


class HtmlToMarkdownTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="html_to_markdown",
            name="HTML to Markdown",
            description="Convert raw HTML pages into clean, LLM-friendly Markdown text",
            category="web-scraping",
            input_schema=HtmlToMarkdownInput.schema_extra(),
            tags=["html", "markdown", "convert", "web", "scraping"],
            requires_auth=False,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = HtmlToMarkdownInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            html_bytes = await resolve_input(validated.data, validated.url, label="HTML")
        except ValueError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Failed to read HTML: {e}"
            )

        try:
            html_str = html_bytes.decode("utf-8", errors="replace")
            base_url = validated.url or ""

            converter = _MarkdownConverter(base_url=base_url)
            converter.feed(html_str)
            markdown = converter.get_markdown()

            # Post-process
            if validated.strip_images:
                markdown = re.sub(r"!\[.*?\]\(.*?\)", "", markdown)
            if not validated.preserve_links:
                markdown = re.sub(r"\[([^\]]*?)\]\(.*?\)", r"\1", markdown)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "html_length": len(html_str),
                    "markdown_length": len(markdown),
                    "markdown": markdown,
                    "compression_ratio": round(len(markdown) / max(len(html_str), 1), 4),
                },
            )

        except Exception as e:
            logger.exception("html_to_markdown failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


register_tool(HtmlToMarkdownTool())
