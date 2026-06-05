"""
Research & Knowledge Retrieval Tools — Google Search API.

google_search_api → Perform live web searches via the Google Custom Search
    JSON API to ground agent knowledge with real-time information.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, is_placeholder, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

GOOGLE_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
GOOGLE_SEARCH_CX = os.getenv("GOOGLE_SEARCH_CX", "")
GOOGLE_SEARCH_TIMEOUT = int(os.getenv("GOOGLE_SEARCH_TIMEOUT", "30"))

GOOGLE_SEARCH_API_BASE = "https://www.googleapis.com/customsearch/v1"

# ── Helpers ───────────────────────────────────────────────────────────


# ── Input ─────────────────────────────────────────────────────────────

SEARCH_ACTIONS = ("search", "search_images")


class GoogleSearchApiInput(ToolInput):
    action: str = Field(
        "search",
        description=f"Action: 'search' (web) or 'search_images' (image search)",
    )
    query: str = Field(
        ...,
        description="Search query string",
    )
    num_results: int = Field(
        10, ge=1, le=10,
        description="Number of results to return (1-10)",
    )
    start_index: int = Field(
        1, ge=1, le=91,
        description="Result start index for pagination (1, 11, 21, ...)",
    )
    language: str | None = Field(
        None,
        description="Language code (e.g., 'en', 'fr', 'de')",
    )
    country: str | None = Field(
        None,
        description="Country code for regional results (e.g., 'us', 'uk')",
    )
    safe_search: bool = Field(
        True,
        description="Enable SafeSearch filtering",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class GoogleSearchApiTool(BaseTool):
    """Perform live web searches via Google Custom Search API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="google_search_api",
            name="Google Search API",
            description=(
                "Perform live web searches via the Google Custom Search JSON API. "
                "Returns organic search results with titles, snippets, and links. "
                "Requires GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX env vars."
            ),
            category="research-knowledge-retrieval",
            input_schema=GoogleSearchApiInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "results": {"type": "array"},
                    "total_results": {"type": "string"},
                    "query": {"type": "string"},
                },
            },
            tags=["search", "google", "web", "research", "knowledge"],
            requires_auth=True,
            timeout_seconds=GOOGLE_SEARCH_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = GoogleSearchApiInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.action not in SEARCH_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(SEARCH_ACTIONS)}",
            )

        if not GOOGLE_API_KEY or not GOOGLE_SEARCH_CX:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Google Search not configured. Set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX.",
            )

        if is_placeholder(GOOGLE_API_KEY) or is_placeholder(GOOGLE_SEARCH_CX):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Google Search not configured. Replace placeholder values for GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX with real credentials.",
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("Google Search API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Google Search API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.warning("google_search_api failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(self, validated: GoogleSearchApiInput) -> dict[str, Any]:
        if validated.action == "search":
            return await self._search(validated)
        elif validated.action == "search_images":
            return await self._search_images(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}"}

    # ── Search helpers ───────────────────────────────────────────

    async def _search(self, validated: GoogleSearchApiInput) -> dict[str, Any]:
        """Perform a web search."""
        params: dict[str, Any] = {
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_SEARCH_CX,
            "q": validated.query,
            "num": validated.num_results,
            "start": validated.start_index,
            "safe": "active" if validated.safe_search else "off",
        }
        if validated.language:
            params["lr"] = f"lang_{validated.language}"
        if validated.country:
            params["cr"] = f"country{validated.country.upper()}"

        async with httpx.AsyncClient(timeout=GOOGLE_SEARCH_TIMEOUT) as client:
            resp = await client.get(GOOGLE_SEARCH_API_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        items = data.get("items", [])
        results = []
        for item in items:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "display_link": item.get("displayLink", ""),
            })

        search_info = data.get("searchInformation", {})
        return {
            "action": "search",
            "query": validated.query,
            "total_results": search_info.get("totalResults", "0"),
            "search_time_seconds": search_info.get("searchTime", 0),
            "result_count": len(results),
            "results": results,
        }

    async def _search_images(self, validated: GoogleSearchApiInput) -> dict[str, Any]:
        """Perform an image search."""
        params: dict[str, Any] = {
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_SEARCH_CX,
            "q": validated.query,
            "num": validated.num_results,
            "start": validated.start_index,
            "safe": validated.safe_search,
            "searchType": "image",
        }
        params["safe"] = "active" if validated.safe_search else "off"

        async with httpx.AsyncClient(timeout=GOOGLE_SEARCH_TIMEOUT) as client:
            resp = await client.get(GOOGLE_SEARCH_API_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        items = data.get("items", [])
        results = []
        for item in items:
            image = item.get("image", {})
            results.append({
                "title": item.get("title", ""),
                "link": item.get("image", {}).get("contextLink", ""),
                "thumbnail": image.get("thumbnailLink", ""),
                "image_url": item.get("link", ""),
                "width": image.get("width", 0),
                "height": image.get("height", 0),
                "size_bytes": image.get("byteSize", 0),
            })

        return {
            "action": "search_images",
            "query": validated.query,
            "result_count": len(results),
            "results": results,
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(GoogleSearchApiTool())
