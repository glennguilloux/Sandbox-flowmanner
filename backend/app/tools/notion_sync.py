"""
API & SaaS Integration Tools — Notion Sync.

notion_sync → Read, create, and update databases and pages in Notion workspaces.
"""

from __future__ import annotations

import logging
import os

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

NOTION_VERSION = "2022-06-28"


class NotionSyncInput(ToolInput):
    action: str = Field(
        ...,
        description="Action: 'query_database', 'get_page', 'create_page', 'update_page', "
        "'get_block_children', 'append_blocks', 'search'",
    )
    database_id: str | None = Field(None, description="Notion database ID")
    page_id: str | None = Field(None, description="Notion page ID")
    block_id: str | None = Field(None, description="Notion block ID")
    filter_query: dict | None = Field(None, description="Notion filter object for database queries")
    sorts: list[dict] | None = Field(None, description="Notion sort array")
    properties: dict | None = Field(None, description="Page properties (for create/update)")
    children: list[dict] | None = Field(None, description="Block children (for create/append)")
    query: str | None = Field(None, description="Search query text")
    limit: int = Field(50, ge=1, le=100)
    token: str | None = Field(None, description="Notion API token (uses NOTION_TOKEN env var if omitted)")


class NotionSyncTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="notion_sync",
            name="Notion Sync",
            description="Read, create, and update databases and pages in Notion workspaces",
            category="api-integrations",
            input_schema=NotionSyncInput.schema_extra(),
            tags=["notion", "docs", "database", "pages", "integration"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = NotionSyncInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        token = validated.token or os.getenv("NOTION_TOKEN", "")
        if not token:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="No Notion token. Set NOTION_TOKEN or pass token.",
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }
        base_url = "https://api.notion.com/v1"
        action = validated.action.lower().strip()

        try:
            async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
                if action == "query_database":
                    return await self._query_database(client, base_url, validated)
                elif action == "get_page":
                    return await self._get_page(client, base_url, validated)
                elif action == "create_page":
                    return await self._create_page(client, base_url, validated)
                elif action == "update_page":
                    return await self._update_page(client, base_url, validated)
                elif action == "get_block_children":
                    return await self._get_block_children(client, base_url, validated)
                elif action == "append_blocks":
                    return await self._append_blocks(client, base_url, validated)
                elif action == "search":
                    return await self._search(client, base_url, validated)
                else:
                    return ToolResult.error_result(tool_id=self.tool_id, error=f"Unknown action: {action}")
        except Exception as e:
            logger.exception("notion_sync failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _check_error(self, r: httpx.Response) -> ToolResult | None:
        if r.status_code not in (200, 201):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Notion API error {r.status_code}: {r.text[:300]}",
            )
        return None

    async def _query_database(self, client, base_url, v) -> ToolResult:
        if not v.database_id:
            return ToolResult.error_result(tool_id=self.tool_id, error="database_id required")
        payload: dict = {"page_size": v.limit}
        if v.filter_query:
            payload["filter"] = v.filter_query
        if v.sorts:
            payload["sorts"] = v.sorts
        r = await client.post(f"{base_url}/databases/{v.database_id}/query", json=payload)
        if err := await self._check_error(r):
            return err
        data = r.json()
        pages = [
            {
                "id": p["id"],
                "properties": p.get("properties", {}),
                "url": p.get("url"),
                "created_time": p.get("created_time"),
            }
            for p in data.get("results", [])
        ]
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "query_database",
                "count": len(pages),
                "has_more": data.get("has_more"),
                "pages": pages,
            },
        )

    async def _get_page(self, client, base_url, v) -> ToolResult:
        if not v.page_id:
            return ToolResult.error_result(tool_id=self.tool_id, error="page_id required")
        r = await client.get(f"{base_url}/pages/{v.page_id}")
        if err := await self._check_error(r):
            return err
        p = r.json()
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "get_page",
                "page": {
                    "id": p["id"],
                    "properties": p.get("properties", {}),
                    "url": p.get("url"),
                    "created_time": p.get("created_time"),
                },
            },
        )

    async def _create_page(self, client, base_url, v) -> ToolResult:
        if not v.database_id or not v.properties:
            return ToolResult.error_result(tool_id=self.tool_id, error="database_id and properties required")
        payload: dict = {
            "parent": {"database_id": v.database_id},
            "properties": v.properties,
        }
        if v.children:
            payload["children"] = v.children
        r = await client.post(f"{base_url}/pages", json=payload)
        if err := await self._check_error(r):
            return err
        p = r.json()
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "create_page",
                "page": {"id": p["id"], "url": p.get("url")},
            },
        )

    async def _update_page(self, client, base_url, v) -> ToolResult:
        if not v.page_id or not v.properties:
            return ToolResult.error_result(tool_id=self.tool_id, error="page_id and properties required")
        r = await client.patch(f"{base_url}/pages/{v.page_id}", json={"properties": v.properties})
        if err := await self._check_error(r):
            return err
        return ToolResult.success_result(tool_id=self.tool_id, result={"action": "update_page", "ok": True})

    async def _get_block_children(self, client, base_url, v) -> ToolResult:
        if not v.block_id:
            return ToolResult.error_result(tool_id=self.tool_id, error="block_id required")
        r = await client.get(f"{base_url}/blocks/{v.block_id}/children", params={"page_size": v.limit})
        if err := await self._check_error(r):
            return err
        data = r.json()
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "get_block_children",
                "count": len(data.get("results", [])),
                "blocks": data.get("results"),
            },
        )

    async def _append_blocks(self, client, base_url, v) -> ToolResult:
        if not v.block_id or not v.children:
            return ToolResult.error_result(tool_id=self.tool_id, error="block_id and children required")
        r = await client.patch(f"{base_url}/blocks/{v.block_id}/children", json={"children": v.children})
        if err := await self._check_error(r):
            return err
        return ToolResult.success_result(tool_id=self.tool_id, result={"action": "append_blocks", "ok": True})

    async def _search(self, client, base_url, v) -> ToolResult:
        if not v.query:
            return ToolResult.error_result(tool_id=self.tool_id, error="query required")
        r = await client.post(f"{base_url}/search", json={"query": v.query, "page_size": v.limit})
        if err := await self._check_error(r):
            return err
        data = r.json()
        results = [
            {
                "id": i["id"],
                "object": i.get("object"),
                "title": str(i.get("properties", {}).get("title", i.get("id"))),
                "url": i.get("url"),
            }
            for i in data.get("results", [])
        ]
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "search",
                "query": v.query,
                "count": len(results),
                "results": results,
            },
        )


register_tool(NotionSyncTool())
