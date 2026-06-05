"""
Vector & Embedding Tools — Pinecone Manager.

pinecone_manager → Manage Pinecone vector database indexes: upsert, query,
    delete, fetch vectors, and list index stats. Uses the pinecone-client SDK
    with connection reuse and metadata filter support.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Literal

from pydantic import Field, field_validator

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "")
PINECONE_TIMEOUT = int(os.getenv("PINECONE_TIMEOUT", "30"))

OPERATIONS = ("upsert", "query", "delete", "fetch", "describe_index", "list_indexes", "stats")


class PineconeManagerInput(ToolInput):
    """Input schema for Pinecone vector DB operations."""

    operation: Literal["upsert", "query", "delete", "fetch", "describe_index", "list_indexes", "stats"] = Field(
        ..., description=f"Operation: {', '.join(OPERATIONS)}",
    )
    index_name: str = Field(
        ...,
        description="Pinecone index name (lowercase alphanumeric/hyphens, 1-45 chars)",
    )
    api_key: str | None = Field(
        None,
        description="Pinecone API key. Uses PINECONE_API_KEY env var if omitted.",
    )
    environment: str | None = Field(
        None,
        description="Pinecone environment/region. Uses PINECONE_ENVIRONMENT if omitted.",
    )
    # Upsert params
    vectors: list[dict[str, Any]] | None = Field(
        None,
        description="List of vectors to upsert. Each: {id, values, metadata?}",
    )
    namespace: str = Field(
        "",
        description="Namespace for the operation (empty string = Pinecone default)",
    )
    # Query params
    query_vector: list[float] | None = Field(
        None,
        description="Query vector for similarity search",
    )
    query_id: str | None = Field(
        None,
        description="Vector ID to fetch (for query by ID or fetch)",
    )
    top_k: int = Field(
        10, ge=1, le=10000,
        description="Number of results to return for queries",
    )
    metadata_filter: dict[str, Any] | None = Field(
        None,
        description="Metadata filter for queries (Pinecone filter syntax)",
    )
    include_values: bool = Field(
        True,
        description="Include vector values in query results",
    )
    include_metadata: bool = Field(
        True,
        description="Include metadata in query results",
    )
    @field_validator("index_name")
    @classmethod
    def validate_index_name(cls, v: str) -> str:
        """Validate index name: 1-45 chars, lowercase alphanumeric/hyphens."""
        if not 1 <= len(v) <= 45:
            raise ValueError("index_name must be 1-45 characters")
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("index_name must contain only lowercase letters, digits, and hyphens")
        return v

    # Delete params
    delete_ids: list[str] | None = Field(
        None,
        description="Vector IDs to delete",
    )
    delete_all: bool = Field(
        False,
        description="Delete ALL vectors in the namespace (requires confirmation)",
    )
    confirmed: bool = Field(
        False,
        description="Confirmation flag for destructive operations (delete_all)",
    )
    # Fetch params
    fetch_ids: list[str] | None = Field(
        None,
        description="Vector IDs to fetch",
    )


class PineconeManagerTool(BaseTool):
    """Manage Pinecone vector database indexes."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="pinecone_manager",
            name="Pinecone Manager",
            description=(
                "Manage Pinecone vector database indexes: upsert, query, delete, "
                "fetch vectors, and list index stats. Uses the pinecone-client SDK "
                "with connection reuse and metadata filter translation. "
                "Requires confirmation for delete_all."
            ),
            category="vector-embedding",
            input_schema=PineconeManagerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "index_name": {"type": "string"},
                    "namespace": {"type": "string"},
                    "matches": {"type": "array", "items": {"type": "object"}},
                    "count": {"type": "integer"},
                    "processing_time_ms": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["pinecone", "vectors", "embeddings", "vector-db", "rag"],
            requires_auth=True,
            timeout_seconds=PINECONE_TIMEOUT + 15,
        )
        super().__init__(metadata=metadata)
        self._pc = None

    def _get_client(self, api_key: str):
        """Get or create Pinecone client (connection reuse)."""
        if self._pc is None:
            try:
                from pinecone import Pinecone
                self._pc = Pinecone(api_key=api_key)
            except ImportError:
                raise RuntimeError("pinecone-client not installed. Run: pip install pinecone-client")
        return self._pc

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = PineconeManagerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        # Security: require confirmation for destructive ops
        if validated.delete_all and validated.operation == "delete" and not validated.confirmed:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="delete_all requires confirmation. Set confirmed=true to proceed.",
            )

        start = time.monotonic()
        api_key = validated.api_key or PINECONE_API_KEY
        if not api_key:
            return ToolResult.error_result(tool_id=self.tool_id, error="Pinecone API key required")

        try:
            pc = self._get_client(api_key)

            if validated.operation == "list_indexes":
                result = await self._list_indexes(pc)
            elif validated.operation == "stats":
                idx = pc.Index(validated.index_name)
                result = await self._stats(idx, validated)
            else:
                idx = pc.Index(validated.index_name)

                if validated.operation == "upsert":
                    result = await self._upsert(idx, validated)
                elif validated.operation == "query":
                    result = await self._query(idx, validated)
                elif validated.operation == "delete":
                    result = await self._delete(idx, validated)
                elif validated.operation == "fetch":
                    result = await self._fetch(idx, validated)
                elif validated.operation == "describe_index":
                    result = await self._describe_index(pc, validated)
                else:
                    return ToolResult.error_result(tool_id=self.tool_id, error=f"Unknown operation: {validated.operation}")

            result["processing_time_ms"] = int((time.monotonic() - start) * 1000)
            result["success"] = True
            return ToolResult.success_result(tool_id=self.tool_id, result=result)

        except Exception as e:
            logger.exception("pinecone_manager failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _upsert(self, idx, validated: PineconeManagerInput) -> dict[str, Any]:
        if not validated.vectors:
            raise ValueError("vectors is required for upsert")

        # Batch upsert in chunks of 100
        chunks = [validated.vectors[i:i + 100] for i in range(0, len(validated.vectors), 100)]
        upserted = 0
        for chunk in chunks:
            idx.upsert(vectors=chunk, namespace=validated.namespace)
            upserted += len(chunk)

        return {
            "operation": "upsert",
            "index_name": validated.index_name,
            "namespace": validated.namespace,
            "count": upserted,
        }

    async def _query(self, idx, validated: PineconeManagerInput) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "top_k": validated.top_k,
            "namespace": validated.namespace,
            "include_values": validated.include_values,
            "include_metadata": validated.include_metadata,
        }
        if validated.metadata_filter:
            kwargs["filter"] = validated.metadata_filter

        if validated.query_vector:
            kwargs["vector"] = validated.query_vector
        elif validated.query_id:
            kwargs["id"] = validated.query_id
        else:
            raise ValueError("Either query_vector or query_id is required for query")

        response = idx.query(**kwargs)
        matches = response.get("matches", [])
        return {
            "operation": "query",
            "index_name": validated.index_name,
            "namespace": validated.namespace,
            "matches": matches,
            "count": len(matches),
        }

    async def _delete(self, idx, validated: PineconeManagerInput) -> dict[str, Any]:
        if validated.delete_all:
            idx.delete(delete_all=True, namespace=validated.namespace)
            return {
                "operation": "delete",
                "index_name": validated.index_name,
                "namespace": validated.namespace,
                "delete_all": True,
                "count": 0,
            }

        if validated.delete_ids:
            idx.delete(ids=validated.delete_ids, namespace=validated.namespace)
            return {
                "operation": "delete",
                "index_name": validated.index_name,
                "namespace": validated.namespace,
                "deleted_ids": validated.delete_ids,
                "count": len(validated.delete_ids),
            }

        raise ValueError("Either delete_ids or delete_all must be provided for delete")

    async def _fetch(self, idx, validated: PineconeManagerInput) -> dict[str, Any]:
        if not validated.fetch_ids:
            raise ValueError("fetch_ids is required for fetch")

        response = idx.fetch(ids=validated.fetch_ids, namespace=validated.namespace)
        vectors_data = response.get("vectors", {})
        return {
            "operation": "fetch",
            "index_name": validated.index_name,
            "namespace": validated.namespace,
            "vectors": vectors_data,
            "count": len(vectors_data),
        }

    async def _describe_index(self, pc, validated: PineconeManagerInput) -> dict[str, Any]:
        desc = pc.describe_index(validated.index_name)
        return {
            "operation": "describe_index",
            "index_name": validated.index_name,
            "index_info": desc.to_dict() if hasattr(desc, "to_dict") else dict(desc),
        }

    async def _stats(self, idx, validated: PineconeManagerInput) -> dict[str, Any]:
        stats = idx.describe_index_stats()
        return {
            "operation": "stats",
            "index_name": validated.index_name,
            "stats": stats.to_dict() if hasattr(stats, "to_dict") else dict(stats),
        }

    async def _list_indexes(self, pc) -> dict[str, Any]:
        indexes = pc.list_indexes()
        names = [i["name"] for i in indexes] if isinstance(indexes, list) else [i.name for i in indexes]
        return {
            "operation": "list_indexes",
            "indexes": names,
            "count": len(names),
        }


register_tool(PineconeManagerTool())
