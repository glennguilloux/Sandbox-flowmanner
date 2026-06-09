"""Standalone mission tool functions — extracted from mission_executor.py.

These functions have no dependency on the MissionExecutor class state.
They are pure async functions that use only external services and the sandbox.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.mission_code_sandbox import execute_python_in_sandbox

logger = logging.getLogger(__name__)


# ── Web Search ────────────────────────────────────────────────────────────────


async def tool_web_search(params: dict, input_data: dict) -> dict[str, Any]:
    """Search the web using the configured search service."""
    query = params.get("query", input_data.get("query"))
    if not query:
        return {"success": False, "error": "No query provided"}

    try:
        from app.services.web_search.models import SearchRequest, SearchType
        from app.services.web_search.service import get_search_service

        service = get_search_service()
        request = SearchRequest(
            query=query,
            search_type=SearchType.GENERAL,
            max_results=5,
        )
        response = await service.search(request)

        results = []
        for r in response.results:
            results.append(
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "score": r.score,
                    "domain": r.domain if hasattr(r, "domain") else "",
                }
            )

        if not results and response.error:
            return {
                "success": False,
                "output": {"query": query, "results": []},
                "error": f"Search returned no results: {response.error}",
            }

        return {
            "success": True,
            "output": {
                "query": query,
                "results": results,
                "provider": response.provider.value if response.provider else "unknown",
            },
        }
    except Exception as e:
        logger.warning("Web search failed for query '%s': %s", query, e)
        return {
            "success": True,
            "output": {
                "query": query,
                "results": [],
                "note": f"Web search unavailable: {e!s}. Configure TAVILY_API_KEY or SEARXNG_URL to enable.",
            },
        }


# ── File Reader ───────────────────────────────────────────────────────────────


async def tool_file_reader(params: dict, input_data: dict) -> dict[str, Any]:
    """Read a file from the file storage service."""
    file_id = params.get("file_id", input_data.get("file_id"))
    if not file_id:
        return {"success": False, "error": "No file_id provided"}

    try:
        from app.services.file_storage import FileStorageService

        storage = FileStorageService()
        file_info = storage.get_file_info(file_id)

        if not file_info:
            return {"success": False, "error": f"File {file_id} not found"}

        with open(file_info.get("path"), "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        return {
            "success": True,
            "output": {
                "filename": file_info.get("filename"),
                "content": content[:50000],
                "size": len(content),
            },
        }
    except Exception as e:
        return {"success": False, "error": f"File read failed: {e!s}"}


# ── API Caller ────────────────────────────────────────────────────────────────


async def execute_web_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: Any = None,
) -> dict[str, Any]:
    """Make an HTTP request and return the response."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.request(
                method,
                url,
                headers=headers or {},
                json=body if body else None,
            )
            return {
                "success": True,
                "output": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text[:10000],
                },
            }
        except Exception as e:
            return {"success": False, "error": f"Request failed: {e!s}"}


async def tool_api_caller(params: dict, input_data: dict) -> dict[str, Any]:
    """Call an external API endpoint."""
    url = params.get("url", input_data.get("url"))
    if not url:
        return {"success": False, "error": "No URL provided"}

    method = params.get("method", "GET")
    headers = params.get("headers", {})
    body = params.get("body")
    return await execute_web_request(url, method, headers, body)


# ── Web Scrape ────────────────────────────────────────────────────────────────


async def execute_web_scrape(url: str) -> dict[str, Any]:
    """Scrape a web page and extract readable text."""
    result = await execute_web_request(url)

    if not result.get("success"):
        return result

    try:
        from bs4 import BeautifulSoup

        body = result["output"]["body"]
        soup = BeautifulSoup(body, "html.parser")

        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        return {
            "success": True,
            "output": {
                "url": url,
                "title": soup.title.string if soup.title else None,
                "text": text[:50000],
                "links": [a.get("href") for a in soup.find_all("a", href=True)][:50],
            },
        }
    except ImportError:
        return {"success": False, "error": "BeautifulSoup not installed"}
    except Exception as e:
        return {"success": False, "error": f"Scraping failed: {e!s}"}


# ── Code / Data Analysis (delegates to sandbox) ───────────────────────────────


async def tool_code_executor(params: dict, input_data: dict) -> dict[str, Any]:
    """Execute arbitrary Python code in a sandbox."""
    code = params.get("code", input_data.get("code"))
    if not code:
        return {"success": False, "error": "No code provided"}
    return execute_python_in_sandbox(code)


async def tool_data_analyzer(params: dict, input_data: dict) -> dict[str, Any]:
    """Analyze a CSV file using pandas in a sandbox."""
    file_id = params.get("file_id", input_data.get("file_id"))
    if not file_id:
        return {"success": False, "error": "No file_id provided"}

    code = (
        "import pandas as pd\n"
        "import json\n"
        f"df = pd.read_csv('{file_id}')\n"
        "result = {\n"
        "    'shape': list(df.shape),\n"
        "    'columns': list(df.columns),\n"
        "    'dtypes': {col: str(dt) for col, dt in df.dtypes.items()},\n"
        "    'missing': df.isnull().sum().to_dict(),\n"
        "    'summary': df.describe().to_dict()\n"
        "}\n"
        "print(json.dumps(result, indent=2, default=str))\n"
    )
    return execute_python_in_sandbox(code)
