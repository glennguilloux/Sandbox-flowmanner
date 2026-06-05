"""
Database Querying & Storage Tools — GraphQL Fetcher.

graphql_fetcher → Construct and execute GraphQL queries and mutations.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class GraphqlFetcherInput(ToolInput):
    endpoint: str = Field(..., description="GraphQL endpoint URL")
    query: str = Field(..., description="GraphQL query or mutation string")
    variables: dict | None = Field(None, description="Query variables as a dict")
    headers: dict | None = Field(None, description="Additional HTTP headers (e.g., Authorization)")
    operation_name: str | None = Field(None, description="Operation name for multi-operation documents")


class GraphqlFetcherTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="graphql_fetcher",
            name="GraphQL Fetcher",
            description="Construct and execute GraphQL queries and mutations",
            category="database",
            input_schema=GraphqlFetcherInput.schema_extra(),
            tags=["graphql", "api", "query", "database"],
            requires_auth=False,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = GraphqlFetcherInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if not validated.query.strip():
            return ToolResult.error_result(tool_id=self.tool_id, error="Query is empty")

        payload: dict[str, Any] = {"query": validated.query}
        if validated.variables:
            payload["variables"] = validated.variables
        if validated.operation_name:
            payload["operationName"] = validated.operation_name

        default_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if validated.headers:
            default_headers.update(validated.headers)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    validated.endpoint,
                    json=payload,
                    headers=default_headers,
                )

                if response.status_code != 200:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=f"GraphQL endpoint returned HTTP {response.status_code}: {response.text[:500]}",
                    )

                data = response.json()

                # Check for GraphQL errors
                if "errors" in data:
                    error_messages = [
                        e.get("message", str(e)) for e in data["errors"]
                    ]
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=f"GraphQL errors: {'; '.join(error_messages[:3])}",
                    )

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "endpoint": validated.endpoint,
                        "operation": validated.operation_name or "anonymous",
                        "data": data.get("data"),
                    },
                )

        except httpx.RequestError as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Request failed: {e}"
            )
        except json.JSONDecodeError:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid JSON response from {validated.endpoint}"
            )
        except Exception as e:
            logger.exception("graphql_fetcher failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


register_tool(GraphqlFetcherTool())
