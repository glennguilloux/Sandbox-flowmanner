"""
Airtable Connector

Provides integration with Airtable for base/table/record management via the BaseConnector framework.
Wraps the AirtableClient REST client to expose standard connector actions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

if TYPE_CHECKING:
    from app.services.airtable.airtable_client import AirtableClient

logger = logging.getLogger(__name__)


class AirtableConnector(BaseConnector):
    """Airtable database/spreadsheet connector."""

    CONNECTOR_TYPE = "airtable"

    AIRTABLE_RATE_LIMIT = RateLimitConfig(
        requests_per_second=5.0,
        requests_per_minute=300,
        requests_per_hour=18000,
        burst_size=5,
    )

    ACTIONS = [
        "list_bases",
        "get_base",
        "list_tables",
        "get_table",
        "list_records",
        "get_record",
        "create_record",
        "update_record",
        "delete_record",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.airtable.com/v0"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.AIRTABLE_RATE_LIMIT
        super().__init__(config)
        self._client: AirtableClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.services.airtable.airtable_client import AirtableClient

            token = self.config.auth_config.get("access_token", "") or self.config.auth_config.get("token", "")
            if not token:
                logger.debug("No Airtable token available — skipping credential validation")
                return True
            self._client = AirtableClient(auth_token=token)
            bases = await self._client.list_bases()
            return isinstance(bases, list)
        except Exception as e:
            logger.warning("Airtable credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "list_bases": self._list_bases,
            "get_base": self._get_base,
            "list_tables": self._list_tables,
            "get_table": self._get_table,
            "list_records": self._list_records,
            "get_record": self._get_record,
            "create_record": self._create_record,
            "update_record": self._update_record,
            "delete_record": self._delete_record,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Airtable action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _list_bases(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AirtableClient not initialized — call connect() first"
        bases = await self._client.list_bases()
        return ConnectorResponse(success=True, data={"bases": bases}, status_code=200)

    async def _get_base(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AirtableClient not initialized — call connect() first"
        base_id = params.get("base_id")
        if not base_id:
            return ConnectorResponse(success=False, error="Missing: base_id", status_code=400)
        base = await self._client.get_base(base_id)
        return ConnectorResponse(success=True, data=base, status_code=200)

    async def _list_tables(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AirtableClient not initialized — call connect() first"
        base_id = params.get("base_id")
        if not base_id:
            return ConnectorResponse(success=False, error="Missing: base_id", status_code=400)
        tables = await self._client.list_tables(base_id)
        return ConnectorResponse(success=True, data={"tables": tables}, status_code=200)

    async def _get_table(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AirtableClient not initialized — call connect() first"
        base_id = params.get("base_id")
        table_id = params.get("table_id")
        if not base_id or not table_id:
            return ConnectorResponse(success=False, error="Missing: base_id and table_id", status_code=400)
        table = await self._client.get_table(base_id, table_id)
        return ConnectorResponse(success=True, data=table, status_code=200)

    async def _list_records(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AirtableClient not initialized — call connect() first"
        base_id = params.get("base_id")
        table_id = params.get("table_id")
        if not base_id or not table_id:
            return ConnectorResponse(success=False, error="Missing: base_id and table_id", status_code=400)
        records = await self._client.list_records(
            base_id=base_id,
            table_id=table_id,
            max_records=params.get("max_records"),
            offset=params.get("offset"),
            view=params.get("view"),
            filter_by_formula=params.get("filter_by_formula"),
        )
        return ConnectorResponse(success=True, data=records, status_code=200)

    async def _get_record(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AirtableClient not initialized — call connect() first"
        base_id = params.get("base_id")
        table_id = params.get("table_id")
        record_id = params.get("record_id")
        if not base_id or not table_id or not record_id:
            return ConnectorResponse(success=False, error="Missing: base_id, table_id, record_id", status_code=400)
        record = await self._client.get_record(base_id, table_id, record_id)
        return ConnectorResponse(success=True, data=record, status_code=200)

    async def _create_record(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AirtableClient not initialized — call connect() first"
        base_id = params.get("base_id")
        table_id = params.get("table_id")
        fields = params.get("fields")
        if not base_id or not table_id or not fields:
            return ConnectorResponse(success=False, error="Missing: base_id, table_id, fields", status_code=400)
        record = await self._client.create_record(base_id, table_id, fields)
        return ConnectorResponse(success=True, data=record, status_code=201)

    async def _update_record(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AirtableClient not initialized — call connect() first"
        base_id = params.get("base_id")
        table_id = params.get("table_id")
        record_id = params.get("record_id")
        fields = params.get("fields")
        if not base_id or not table_id or not record_id or not fields:
            return ConnectorResponse(
                success=False, error="Missing: base_id, table_id, record_id, fields", status_code=400
            )
        record = await self._client.update_record(base_id, table_id, record_id, fields)
        return ConnectorResponse(success=True, data=record, status_code=200)

    async def _delete_record(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "AirtableClient not initialized — call connect() first"
        base_id = params.get("base_id")
        table_id = params.get("table_id")
        record_id = params.get("record_id")
        if not base_id or not table_id or not record_id:
            return ConnectorResponse(success=False, error="Missing: base_id, table_id, record_id", status_code=400)
        result = await self._client.delete_record(base_id, table_id, record_id)
        return ConnectorResponse(success=True, data=result, status_code=200)
