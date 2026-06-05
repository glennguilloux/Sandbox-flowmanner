"""
Research & Knowledge Retrieval Tools — ArXiv Paper Finder.

arxiv_paper_finder → Search and extract abstracts for academic papers
    from the ArXiv API.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from xml.etree import ElementTree

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

ARXIV_API_BASE = "https://export.arxiv.org/api/query"
ARXIV_TIMEOUT = int(os.getenv("ARXIV_TIMEOUT", "30"))
ARXIV_MAX_RESULTS = int(os.getenv("ARXIV_MAX_RESULTS", "10"))

# ArXiv API namespaces
_ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# ── Input ─────────────────────────────────────────────────────────────

ARXIV_ACTIONS = (
    "search",
    "get_paper",
    "list_categories",
)


class ArxivPaperFinderInput(ToolInput):
    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(ARXIV_ACTIONS)}",
    )
    query: str = Field(
        ...,
        description="Search query (supports ArXiv API syntax: 'ti:title', 'au:author', 'abs:abstract', 'cat:cs.AI', etc.)",
    )
    paper_id: str | None = Field(
        None,
        description="ArXiv paper ID (e.g., '2301.12345' or '2301.12345v1') for get_paper",
    )
    max_results: int = Field(
        ARXIV_MAX_RESULTS,
        ge=1,
        le=50,
        description="Maximum number of papers to return",
    )
    sort_by: str = Field(
        "relevance",
        description="Sort order: 'relevance', 'lastUpdatedDate', or 'submittedDate'",
    )
    start: int = Field(
        0,
        ge=0,
        le=1000,
        description="Starting index for pagination",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class ArxivPaperFinderTool(BaseTool):
    """Search and retrieve academic papers from ArXiv."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="arxiv_paper_finder",
            name="ArXiv Paper Finder",
            description=(
                "Search and extract abstracts for academic papers from ArXiv. "
                "Supports advanced query syntax (ti:, au:, abs:, cat:). "
                "Returns paper metadata including title, authors, abstract, and links. "
                "No authentication required."
            ),
            category="research-knowledge-retrieval",
            input_schema=ArxivPaperFinderInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "papers": {"type": "array"},
                    "total_results": {"type": "integer"},
                    "query": {"type": "string"},
                },
            },
            tags=["arxiv", "academic", "papers", "research", "science", "scholar"],
            requires_auth=False,
            timeout_seconds=ARXIV_TIMEOUT + 15,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ArxivPaperFinderInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.action not in ARXIV_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(ARXIV_ACTIONS)}",
            )

        if validated.sort_by not in ("relevance", "lastUpdatedDate", "submittedDate"):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="sort_by must be 'relevance', 'lastUpdatedDate', or 'submittedDate'",
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("ArXiv API error: %s", e)
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"ArXiv API error ({e.response.status_code}): {e.response.text[:500]}",
            )
        except Exception as e:
            logger.warning("arxiv_paper_finder failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(self, validated: ArxivPaperFinderInput) -> dict[str, Any]:
        if validated.action == "search":
            return await self._search(validated)
        elif validated.action == "get_paper":
            return await self._get_paper(validated)
        elif validated.action == "list_categories":
            return await self._list_categories()
        else:
            return {"error": f"Unhandled action: {validated.action}"}

    # ── XML helpers ──────────────────────────────────────────────

    def _parse_paper_entry(self, entry: ElementTree.Element) -> dict[str, Any]:
        """Parse an ArXiv Atom entry into a dict."""

        def _text(tag: str) -> str:
            el = entry.find(f"atom:{tag}", _ARXIV_NS)
            return (el.text or "").strip() if el is not None else ""

        paper_id_url = _text("id")
        paper_id = paper_id_url.replace("http://arxiv.org/abs/", "").rstrip("/")

        authors = []
        for author_el in entry.findall("atom:author", _ARXIV_NS):
            name_el = author_el.find("atom:name", _ARXIV_NS)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        links = []
        for link_el in entry.findall("atom:link", _ARXIV_NS):
            links.append(
                {
                    "href": link_el.get("href", ""),
                    "rel": link_el.get("rel", ""),
                    "title": link_el.get("title", ""),
                }
            )

        # Categories
        categories = []
        for cat_el in entry.findall("atom:category", _ARXIV_NS):
            categories.append(cat_el.get("term", ""))

        # ArXiv-specific
        primary_cat = entry.find("arxiv:primary_category", _ARXIV_NS)
        primary_category = (
            primary_cat.get("term", "") if primary_cat is not None else ""
        )

        return {
            "paper_id": paper_id,
            "title": _text("title"),
            "summary": _text("summary"),
            "authors": authors,
            "author_count": len(authors),
            "published": _text("published"),
            "updated": _text("updated"),
            "categories": categories,
            "primary_category": primary_category,
            "comment": _text("arxiv:comment") if "arxiv" in _ARXIV_NS else "",
            "journal_ref": _text("arxiv:journal_ref") if "arxiv" in _ARXIV_NS else "",
            "doi": _text("arxiv:doi") if "arxiv" in _ARXIV_NS else "",
            "links": links,
            "pdf_url": next((l["href"] for l in links if l.get("title") == "pdf"), ""),
            "abs_url": f"https://arxiv.org/abs/{paper_id}",
        }

    # ── Action handlers ──────────────────────────────────────────

    async def _search(self, validated: ArxivPaperFinderInput) -> dict[str, Any]:
        """Search for papers on ArXiv."""
        if not validated.query:
            return {"error": "query is required for search"}

        params = {
            "search_query": validated.query,
            "max_results": validated.max_results,
            "start": validated.start,
            "sortBy": validated.sort_by,
        }

        async with httpx.AsyncClient(timeout=ARXIV_TIMEOUT) as client:
            resp = await client.get(ARXIV_API_BASE, params=params)
            resp.raise_for_status()
            raw_xml = resp.text

        try:
            root = ElementTree.fromstring(raw_xml)
        except ElementTree.ParseError as e:
            return {"action": "search", "error": f"Failed to parse ArXiv response: {e}"}

        entries = root.findall("atom:entry", _ARXIV_NS)
        papers = [self._parse_paper_entry(e) for e in entries]

        # Total results
        total_el = root.find("atom:totalResults", _ARXIV_NS)
        total_results = int(total_el.text) if total_el is not None else len(papers)

        return {
            "action": "search",
            "query": validated.query,
            "total_results": total_results,
            "result_count": len(papers),
            "start": validated.start,
            "sort_by": validated.sort_by,
            "papers": papers,
        }

    async def _get_paper(self, validated: ArxivPaperFinderInput) -> dict[str, Any]:
        """Fetch a specific paper by ID."""
        if not validated.paper_id:
            return {"error": "paper_id is required for get_paper"}

        # Strip version suffix and URL prefix
        pid = validated.paper_id.strip()
        pid = pid.replace("http://arxiv.org/abs/", "").rstrip("/")

        params = {
            "id_list": pid,
            "max_results": 1,
        }

        async with httpx.AsyncClient(timeout=ARXIV_TIMEOUT) as client:
            resp = await client.get(ARXIV_API_BASE, params=params)
            resp.raise_for_status()
            raw_xml = resp.text

        try:
            root = ElementTree.fromstring(raw_xml)
        except ElementTree.ParseError as e:
            return {
                "action": "get_paper",
                "error": f"Failed to parse ArXiv response: {e}",
            }

        entries = root.findall("atom:entry", _ARXIV_NS)
        if not entries:
            return {"action": "get_paper", "paper_id": pid, "error": "Paper not found"}

        paper = self._parse_paper_entry(entries[0])
        paper["action"] = "get_paper"
        return paper

    async def _list_categories(self) -> dict[str, Any]:
        """Return a curated list of major ArXiv categories."""
        categories = [
            {"id": "cs.AI", "name": "Artificial Intelligence"},
            {"id": "cs.CL", "name": "Computation and Language (NLP)"},
            {"id": "cs.CV", "name": "Computer Vision and Pattern Recognition"},
            {"id": "cs.LG", "name": "Machine Learning"},
            {"id": "cs.NE", "name": "Neural and Evolutionary Computing"},
            {"id": "cs.RO", "name": "Robotics"},
            {"id": "cs.SE", "name": "Software Engineering"},
            {"id": "cs.DB", "name": "Databases"},
            {"id": "cs.CR", "name": "Cryptography and Security"},
            {"id": "cs.DC", "name": "Distributed, Parallel, and Cluster Computing"},
            {"id": "stat.ML", "name": "Machine Learning (Statistics)"},
            {"id": "math.OC", "name": "Optimization and Control"},
            {"id": "q-bio.QM", "name": "Quantitative Methods (Biology)"},
            {"id": "physics.comp-ph", "name": "Computational Physics"},
            {"id": "econ.EM", "name": "Econometrics"},
        ]
        return {
            "action": "list_categories",
            "category_count": len(categories),
            "categories": categories,
            "note": "Use these IDs in search queries: 'cat:cs.AI' for filtering by category",
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(ArxivPaperFinderTool())
