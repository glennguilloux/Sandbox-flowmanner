"""
Airtable REST API Client

Async client for Airtable's REST API.
Used by the user-facing Airtable integration — agents manage bases,
tables, and records on behalf of the USER.

Auth: per-user OAuth token (stored in IntegrationConnection, decrypted at call time).
Works with Airtable's standard OAuth2 flow (PKCE recommended but not enforced server-side).

Token URL: https://airtable.com/oauth2/v1/token
API Base: https://api.airtable.com/v0
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

AIRTABLE_API_BASE = "https://api.airtable.com/v0"


class AirtableAPIError(Exception):
    """Airtable API error."""

    pass


class AirtableClient:
    """Async REST client for Airtable REST API."""

    def __init__(self, auth_token: str, base_url: str = AIRTABLE_API_BASE):
        """
        Args:
            auth_token: Airtable OAuth access token
            base_url: Airtable API base URL (default: https://api.airtable.com/v0)
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=self._headers, **kwargs)
            if resp.status_code == 429:
                retry_after = resp.headers.get("retry-after", "?")
                raise AirtableAPIError(f"Airtable rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise AirtableAPIError(f"Airtable API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            if resp.status_code == 204:
                return {}
            return resp.json()

    # ── Meta: Bases ─────────────────────────────────────────────

    async def list_bases(self) -> list[dict[str, Any]]:
        """GET /v0/meta/bases — List all accessible bases."""
        data = await self._request("GET", "/meta/bases")
        if isinstance(data, dict):
            return data.get("bases", [])
        return []  # type: ignore[return-value]

    async def get_base(self, base_id: str) -> dict[str, Any]:
        """GET /v0/meta/bases/{baseId} — Get base details."""
        return await self._request("GET", f"/meta/bases/{base_id}")  # type: ignore[return-value]

    # ── Meta: Tables ────────────────────────────────────────────

    async def list_tables(self, base_id: str) -> list[dict[str, Any]]:
        """GET /v0/meta/bases/{baseId}/tables — List tables in a base."""
        data = await self._request("GET", f"/meta/bases/{base_id}/tables")
        if isinstance(data, dict):
            return data.get("tables", [])
        return []  # type: ignore[return-value]

    async def get_table(self, base_id: str, table_id: str) -> dict[str, Any]:
        """GET /v0/meta/bases/{baseId}/tables/{tableId} — Get table schema."""
        tables = await self.list_tables(base_id)
        for table in tables:
            if table.get("id") == table_id or table.get("name") == table_id:
                return table
        raise AirtableAPIError(f"Table '{table_id}' not found in base '{base_id}'")

    # ── Records ─────────────────────────────────────────────────

    async def list_records(
        self,
        base_id: str,
        table_id: str,
        max_records: int | None = None,
        offset: str | None = None,
        view: str | None = None,
        sort: list[dict[str, Any]] | None = None,
        filter_by_formula: str | None = None,
    ) -> dict[str, Any]:
        """GET /v0/{baseId}/{tableIdOrName} — List records in a table."""
        params: dict[str, Any] = {}
        if max_records is not None:
            params["maxRecords"] = max_records
        if offset:
            params["offset"] = offset
        if view:
            params["view"] = view
        if filter_by_formula:
            params["filterByFormula"] = filter_by_formula
        if sort:
            for i, s in enumerate(sort):
                for k, v in s.items():
                    params[f"sort[{i}][{k}]"] = v
        return await self._request("GET", f"/{base_id}/{table_id}", params=params)  # type: ignore[return-value]

    async def get_record(
        self,
        base_id: str,
        table_id: str,
        record_id: str,
    ) -> dict[str, Any]:
        """GET /v0/{baseId}/{tableIdOrName}/{recordId} — Get a single record."""
        return await self._request("GET", f"/{base_id}/{table_id}/{record_id}")  # type: ignore[return-value]

    async def create_record(
        self,
        base_id: str,
        table_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """POST /v0/{baseId}/{tableIdOrName} — Create a record."""
        payload = {"fields": fields}
        return await self._request("POST", f"/{base_id}/{table_id}", json=payload)  # type: ignore[return-value]

    async def update_record(
        self,
        base_id: str,
        table_id: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """PATCH /v0/{baseId}/{tableIdOrName}/{recordId} — Update a record."""
        payload = {"fields": fields}
        return await self._request("PATCH", f"/{base_id}/{table_id}/{record_id}", json=payload)  # type: ignore[return-value]

    async def delete_record(
        self,
        base_id: str,
        table_id: str,
        record_id: str,
    ) -> dict[str, Any]:
        """DELETE /v0/{baseId}/{tableIdOrName}/{recordId} — Delete a record."""
        return await self._request("DELETE", f"/{base_id}/{table_id}/{record_id}")  # type: ignore[return-value]
