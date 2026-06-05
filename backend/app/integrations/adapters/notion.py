"""Notion integration adapter — 3 actions using the Notion API v1."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.integrations.adapters.base import BaseIntegrationAdapter

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionAdapter(BaseIntegrationAdapter):
    """Adapter for Notion actions using stored OAuth tokens.

    Actions:
        - ``create_page``: Create a new page in a parent page/database.
        - ``query_database``: Query a database with filters and sorts.
        - ``append_block``: Append content blocks to a page or block.
    """

    provider = "notion"

    # ── Action dispatch ────────────────────────────────────────────────────

    async def _execute_action(
        self, action: str, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        match action:
            case "create_page":
                return await self._create_page(params, access_token)
            case "query_database":
                return await self._query_database(params, access_token)
            case "append_block":
                return await self._append_block(params, access_token)
            case _:
                return {
                    "success": False,
                    "error": f"Unknown Notion action: {action}",
                }

    @staticmethod
    def _headers(access_token: str) -> dict:
        return {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    # ── Action: create_page ────────────────────────────────────────────────

    async def _create_page(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Create a new Notion page.

        Required: ``parent_page_id``, ``properties`` (dict of property values)
        Optional: ``children`` (list of block objects)
        """
        parent_page_id = params.get("parent_page_id")
        properties = params.get("properties")
        children = params.get("children")

        if not parent_page_id:
            return {"success": False, "error": "Missing required param: parent_page_id"}
        if not properties or not isinstance(properties, dict):
            return {
                "success": False,
                "error": "Missing required param: properties (dict)",
            }

        body: dict = {
            "parent": {"page_id": parent_page_id},
            "properties": properties,
        }
        if children and isinstance(children, list) and len(children) > 0:
            body["children"] = children

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{NOTION_API_BASE}/pages",
                json=body,
                headers=self._headers(access_token),
            )
            return _parse_notion_response(resp)

    # ── Action: query_database ─────────────────────────────────────────────

    async def _query_database(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Query a Notion database with optional filters and sorting.

        Required: ``database_id``
        Optional: ``filter`` (dict), ``sorts`` (list), ``limit`` (default 100)
        """
        database_id = params.get("database_id")
        if not database_id:
            return {"success": False, "error": "Missing required param: database_id"}

        body: dict = {}
        if params.get("filter") and isinstance(params["filter"], dict):
            body["filter"] = params["filter"]
        if params.get("sorts") and isinstance(params["sorts"], list):
            body["sorts"] = params["sorts"]
        if params.get("limit"):
            body["page_size"] = min(int(params["limit"]), 100)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{NOTION_API_BASE}/databases/{database_id}/query",
                json=body,
                headers=self._headers(access_token),
            )
            return _parse_notion_response(resp)

    # ── Action: append_block ───────────────────────────────────────────────

    async def _append_block(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Append block children to a page or block.

        Required: ``block_id``, ``children`` (list of block objects)
        """
        block_id = params.get("block_id")
        children = params.get("children")

        if not block_id:
            return {"success": False, "error": "Missing required param: block_id"}
        if not children or not isinstance(children, list) or len(children) == 0:
            return {
                "success": False,
                "error": "Missing required param: children (non-empty list of blocks)",
            }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.patch(
                f"{NOTION_API_BASE}/blocks/{block_id}/children",
                json={"children": children},
                headers=self._headers(access_token),
            )
            return _parse_notion_response(resp)


# ── Response parser ───────────────────────────────────────────────────────────


def _parse_notion_response(resp: httpx.Response) -> dict[str, Any]:
    """Parse a Notion API response and return a structured result."""
    try:
        data = resp.json()
    except Exception:
        return {
            "success": False,
            "error": f"Notion returned non-JSON response (HTTP {resp.status_code})",
        }

    if resp.status_code < 400:
        return {"success": True, "response": data}

    # Notion error — extract a clear message
    error_msg = data.get("message", f"Notion API error (HTTP {resp.status_code})")
    error_code = data.get("code", _notion_error_code(error_msg))

    # Token errors → trigger refresh in base adapter
    if resp.status_code == 401:
        return {"success": False, "error": "token_expired", "error_detail": error_msg}

    return {"success": False, "error": error_msg, "error_code": error_code}


def _notion_error_code(message: str) -> str:
    """Map Notion error messages/patterns to stable codes."""
    patterns = [
        ("validation_error", "validation_error"),
        ("object_not_found", "object_not_found"),
        ("invalid_json", "invalid_json"),
        ("invalid_request_url", "invalid_request_url"),
        ("invalid_request", "invalid_request"),
        ("restricted_resource", "restricted_resource"),
        ("conflict_error", "conflict_error"),
        ("rate_limited", "rate_limited"),
        ("internal_server_error", "internal_server_error"),
        ("service_unavailable", "service_unavailable"),
    ]
    msg_lower = message.lower()
    for pattern, code in patterns:
        # Check both underscored and space-separated forms
        if pattern in msg_lower or pattern.replace("_", " ") in msg_lower:
            return code
    return "unknown_error"
