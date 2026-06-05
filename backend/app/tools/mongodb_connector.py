"""
Database Querying & Storage Tools — MongoDB Connector.

mongodb_connector → Perform CRUD operations on MongoDB collections.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class MongoDbConnectorInput(ToolInput):
    action: str = Field(
        ...,
        description="Action: 'find', 'find_one', 'insert_one', 'insert_many', 'update_one', "
                    "'update_many', 'delete_one', 'delete_many', 'aggregate', 'count'",
    )
    collection: str = Field(..., description="MongoDB collection name")
    database: str = Field("default", description="MongoDB database name")
    filter_query: dict | str | None = Field(
        None,
        description="Filter query as JSON string or dict (for find, update, delete)",
    )
    data: dict | list | str | None = Field(
        None,
        description="Data to insert or update (as JSON string, dict, or list of dicts)",
    )
    update: dict | str | None = Field(
        None,
        description="Update operations for update actions (as JSON string or dict)",
    )
    pipeline: list | str | None = Field(
        None,
        description="Aggregation pipeline as JSON string or list (for 'aggregate' action)",
    )
    sort: str | None = Field(
        None,
        description='Sort field and direction (e.g., "created_at:-1" for descending)',
    )
    limit: int = Field(50, ge=1, le=1000, description="Maximum documents to return")
    skip: int = Field(0, ge=0, description="Number of documents to skip")
    connection_string: str | None = Field(
        None,
        description="MongoDB connection string (uses MONGODB_URL env var if omitted)",
    )


class MongoDbConnectorTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="mongodb_connector",
            name="MongoDB Connector",
            description="Perform CRUD operations on MongoDB collections",
            category="database",
            input_schema=MongoDbConnectorInput.schema_extra(),
            tags=["mongodb", "nosql", "database", "crud"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    @staticmethod
    def _parse_json(val: str | dict | list | None) -> Any:
        """Parse JSON string to Python object."""
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return val
        return json.loads(val)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = MongoDbConnectorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        conn_str = validated.connection_string or os.getenv("MONGODB_URL", "")
        if not conn_str:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="No MongoDB connection string. Set MONGODB_URL env var or pass connection_string.",
            )

        try:
            # Try importing motor (async) first, fall back to pymongo (sync)
            try:
                import motor.motor_asyncio
                client = motor.motor_asyncio.AsyncIOMotorClient(conn_str)
                db = client[validated.database]
                collection = db[validated.collection]
                return await self._execute_async(validated, collection, client)
            except ImportError:
                pass

            # Fall back to pymongo
            from pymongo import MongoClient

            sync_client = MongoClient(conn_str)
            db = sync_client[validated.database]
            collection = db[validated.collection]
            return self._execute_sync(validated, collection, sync_client)

        except Exception as e:
            logger.exception("mongodb_connector failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _execute_async(self, validated, collection, client) -> ToolResult:
        """Execute using motor (async MongoDB driver)."""
        action = validated.action.lower()
        filter_q = self._parse_json(validated.filter_query)
        data = self._parse_json(validated.data)
        update = self._parse_json(validated.update)
        pipeline = self._parse_json(validated.pipeline)

        try:
            if action == "find":
                cursor = collection.find(filter_q or {}).skip(validated.skip).limit(validated.limit)
                if validated.sort:
                    field, direction = validated.sort.rsplit(":", 1)
                    cursor = cursor.sort(field, int(direction))
                docs = await cursor.to_list(length=validated.limit)
                return self._result(action, {"count": len(docs), "documents": docs})

            elif action == "find_one":
                doc = await collection.find_one(filter_q or {})
                return self._result(action, {"document": doc})

            elif action == "insert_one":
                if not data or not isinstance(data, dict):
                    return ToolResult.error_result(tool_id=self.tool_id, error="data must be a dict for insert_one")
                result = await collection.insert_one(data)
                return self._result(action, {"inserted_id": str(result.inserted_id)})

            elif action == "insert_many":
                if not data or not isinstance(data, list):
                    return ToolResult.error_result(tool_id=self.tool_id, error="data must be a list for insert_many")
                result = await collection.insert_many(data)
                return self._result(action, {"inserted_count": len(result.inserted_ids)})

            elif action == "update_one":
                if not filter_q or not update:
                    return ToolResult.error_result(tool_id=self.tool_id, error="filter_query and update required")
                result = await collection.update_one(filter_q, update)
                return self._result(action, {"matched_count": result.matched_count, "modified_count": result.modified_count})

            elif action == "update_many":
                if not filter_q or not update:
                    return ToolResult.error_result(tool_id=self.tool_id, error="filter_query and update required")
                result = await collection.update_many(filter_q, update)
                return self._result(action, {"matched_count": result.matched_count, "modified_count": result.modified_count})

            elif action == "delete_one":
                result = await collection.delete_one(filter_q or {})
                return self._result(action, {"deleted_count": result.deleted_count})

            elif action == "delete_many":
                result = await collection.delete_many(filter_q or {})
                return self._result(action, {"deleted_count": result.deleted_count})

            elif action == "aggregate":
                if not pipeline or not isinstance(pipeline, list):
                    return ToolResult.error_result(tool_id=self.tool_id, error="pipeline must be a list for aggregate")
                cursor = collection.aggregate(pipeline)
                docs = await cursor.to_list(length=validated.limit)
                return self._result(action, {"count": len(docs), "documents": docs})

            elif action == "count":
                count = await collection.count_documents(filter_q or {})
                return self._result(action, {"count": count})

            else:
                return ToolResult.error_result(tool_id=self.tool_id, error=f"Unknown action: {action}")

        finally:
            client.close()

    def _execute_sync(self, validated, collection, client) -> ToolResult:
        """Execute using pymongo (sync driver)."""
        action = validated.action.lower()
        filter_q = self._parse_json(validated.filter_query)
        data = self._parse_json(validated.data)
        update = self._parse_json(validated.update)
        pipeline = self._parse_json(validated.pipeline)

        try:
            if action == "find":
                cursor = collection.find(filter_q or {}).skip(validated.skip).limit(validated.limit)
                if validated.sort:
                    field, direction = validated.sort.rsplit(":", 1)
                    cursor = cursor.sort(field, int(direction))
                docs = list(cursor)
                return self._result(action, {"count": len(docs), "documents": docs})
            elif action == "find_one":
                doc = collection.find_one(filter_q or {})
                return self._result(action, {"document": doc})
            elif action == "insert_one":
                if not data or not isinstance(data, dict):
                    return ToolResult.error_result(tool_id=self.tool_id, error="data must be a dict")
                result = collection.insert_one(data)
                return self._result(action, {"inserted_id": str(result.inserted_id)})
            elif action == "insert_many":
                if not data or not isinstance(data, list):
                    return ToolResult.error_result(tool_id=self.tool_id, error="data must be a list")
                result = collection.insert_many(data)
                return self._result(action, {"inserted_count": len(result.inserted_ids)})
            elif action == "update_one":
                if not filter_q or not update:
                    return ToolResult.error_result(tool_id=self.tool_id, error="filter_query and update required")
                result = collection.update_one(filter_q, update)
                return self._result(action, {"matched_count": result.matched_count, "modified_count": result.modified_count})
            elif action == "update_many":
                if not filter_q or not update:
                    return ToolResult.error_result(tool_id=self.tool_id, error="filter_query and update required")
                result = collection.update_many(filter_q, update)
                return self._result(action, {"matched_count": result.matched_count, "modified_count": result.modified_count})
            elif action == "delete_one":
                result = collection.delete_one(filter_q or {})
                return self._result(action, {"deleted_count": result.deleted_count})
            elif action == "delete_many":
                result = collection.delete_many(filter_q or {})
                return self._result(action, {"deleted_count": result.deleted_count})
            elif action == "aggregate":
                if not pipeline or not isinstance(pipeline, list):
                    return ToolResult.error_result(tool_id=self.tool_id, error="pipeline must be a list")
                docs = list(collection.aggregate(pipeline))
                return self._result(action, {"count": len(docs), "documents": docs})
            elif action == "count":
                count = collection.count_documents(filter_q or {})
                return self._result(action, {"count": count})
            else:
                return ToolResult.error_result(tool_id=self.tool_id, error=f"Unknown action: {action}")
        finally:
            client.close()

    def _result(self, action: str, data: dict) -> ToolResult:
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={"action": action, **data},
        )


register_tool(MongoDbConnectorTool())
