"""
Monday.com GraphQL API Client

Async client for Monday.com GraphQL API v2.
Auth: Authorization: Bearer header.

API Base: https://api.monday.com/v2
Quirk: GraphQL API — all requests are POST with a {"query": "..."} body.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MONDAY_API_BASE = "https://api.monday.com/v2"


class MondayAPIError(Exception):
    """Monday.com API error."""

    pass


class MondayClient:
    """Async GraphQL client for Monday.com API v2."""

    def __init__(
        self,
        access_token: str,
        base_url: str = MONDAY_API_BASE,
    ):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "API-Version": "2024-01",
        }

    async def _query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query/mutation."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.base_url, headers=self._headers, json=payload)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After", "?")
                raise MondayAPIError(f"Monday rate limited — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise MondayAPIError(f"Monday API failed: {resp.status_code} {resp.text[:300]}")
            result = resp.json()
            if "errors" in result:
                raise MondayAPIError(f"Monday GraphQL errors: {result['errors']}")
            return result.get("data", result)

    # ── Me ───────────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """Query { me { id name email } } — Credential validation."""
        result = await self._query("{ me { id name email } }")
        return result.get("me", {})

    # ── Boards ───────────────────────────────────────────────────

    async def list_boards(self, limit: int = 50) -> list[dict[str, Any]]:
        """Query { boards(limit) { id name state description } }"""
        result = await self._query(f"{{ boards(limit: {limit}) {{ id name state description }} }}")
        return result.get("boards", [])

    async def get_board(self, board_id: str) -> dict[str, Any]:
        """Query { boards(ids: [id]) { id name columns { id title type } groups { id title } } }"""
        result = await self._query(
            f"{{ boards(ids: [{board_id}]) {{ id name columns {{ id title type }} groups {{ id title }} }} }}"
        )
        boards = result.get("boards", [])
        return boards[0] if boards else {}

    # ── Items ────────────────────────────────────────────────────

    async def list_items(self, board_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Query boards(ids) { items_page(limit) { items { id name column_values { id text value } } } }"""
        result = await self._query(
            f"{{ boards(ids: [{board_id}]) {{ items_page(limit: {limit}) {{ items {{ id name column_values {{ id text value }} }} }} }} }}"
        )
        boards = result.get("boards", [])
        if not boards:
            return []
        items_page = boards[0].get("items_page", {})
        return items_page.get("items", [])

    async def get_item(self, item_id: str) -> dict[str, Any]:
        """Query { items(ids: [id]) { id name column_values { id text value } } }"""
        result = await self._query(f"{{ items(ids: [{item_id}]) {{ id name column_values {{ id text value }} }} }}")
        items = result.get("items", [])
        return items[0] if items else {}

    async def create_item(
        self, board_id: str, item_name: str, group_id: str | None = None, column_values: str | None = None
    ) -> dict[str, Any]:
        """Mutation { create_item(...) { id } }"""
        parts = [f"board_id: {board_id}", f'item_name: "{item_name}"']
        if group_id:
            parts.append(f'group_id: "{group_id}"')
        if column_values:
            parts.append(f'column_values: "{column_values}"')
        result = await self._query(f'{{ create_item({", ".join(parts)}) {{ id name }} }}')
        return result.get("create_item", {})

    async def update_item(self, item_id: str, board_id: str, column_values: str) -> dict[str, Any]:
        """Mutation { change_column_values(...) { id } }"""
        result = await self._query(
            f'{{ change_column_values(item_id: {item_id}, board_id: {board_id}, column_values: "{column_values}") {{ id name }} }}'
        )
        return result.get("change_column_values", {})

    async def create_update(self, item_id: str, body: str) -> dict[str, Any]:
        """Mutation { create_update(...) { id } }"""
        result = await self._query(f'{{ create_update(item_id: {item_id}, body: "{body}") {{ id }} }}')
        return result.get("create_update", {})

    # ── Users ────────────────────────────────────────────────────

    async def list_users(self, limit: int = 50) -> list[dict[str, Any]]:
        """Query { users(limit) { id name email } }"""
        result = await self._query(f"{{ users(limit: {limit}) {{ id name email }} }}")
        return result.get("users", [])

    # ── Workspaces ───────────────────────────────────────────────

    async def list_workspaces(self) -> list[dict[str, Any]]:
        """Query { workspaces { id name } }"""
        result = await self._query("{ workspaces { id name } }")
        return result.get("workspaces", [])
