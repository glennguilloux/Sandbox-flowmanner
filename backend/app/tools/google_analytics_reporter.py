"""
SEO & Marketing Tools — Google Analytics Reporter.

google_analytics_reporter → Fetch pageviews, user metrics, and conversion
    data via the Google Analytics Data API v1 with OAuth2 authentication.
    Includes Redis caching (5 min TTL) and date range validation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, timedelta
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

GA_PROPERTY_ID = os.getenv("GA_PROPERTY_ID", "")
GA_SERVICE_ACCOUNT_JSON = os.getenv("GA_SERVICE_ACCOUNT_JSON", "")
GA_API_KEY = os.getenv("GA_API_KEY", "")
GA_TIMEOUT = int(os.getenv("GA_TIMEOUT", "30"))
GA_CACHE_TTL = int(os.getenv("GA_CACHE_TTL", "300"))  # 5 minutes default
GA_MAX_DATE_RANGE_DAYS = int(os.getenv("GA_MAX_DATE_RANGE_DAYS", "365"))

# Google Analytics Data API v1 endpoint
GA_API_BASE = "https://analyticsdata.googleapis.com/v1beta"

# Redis cache key prefix
_CACHE_PREFIX = "ga:reporter:"

# ── Input ─────────────────────────────────────────────────────────────

GA_ACTIONS = (
    "run_report",
    "get_realtime",
    "list_properties",
)

_VALID_METRICS = {
    "activeUsers", "active1DayUsers", "active7DayUsers", "active28DayUsers",
    "averageSessionDuration", "bounceRate", "conversions", "engagementRate",
    "eventCount", "newUsers", "screenPageViews", "sessions",
    "sessionConversionRate", "totalRevenue", "totalUsers", "userEngagementDuration",
}

_VALID_DIMENSIONS = {
    "browser", "city", "country", "date", "deviceCategory", "language",
    "newVsReturning", "pagePath", "pageTitle", "sessionDefaultChannelGrouping",
    "sessionMedium", "sessionSource", "userType",
}


def _parse_date(d: str) -> str:
    """Normalize date to YYYY-MM-DD, supporting relative aliases."""
    d = d.lower().strip()
    if d == "today":
        return date.today().isoformat()
    elif d == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    elif d.endswith("d"):
        try:
            n = int(d[:-1])
            return (date.today() - timedelta(days=n)).isoformat()
        except ValueError:
            pass
    return d


def _validate_date_range(start_str: str, end_str: str) -> tuple[str, str, str | None]:
    """Validate start/end dates. Returns (start, end, error_message_or_None)."""
    try:
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
    except ValueError as e:
        return start_str, end_str, f"Invalid date format: {e}"

    if start > end:
        return start_str, end_str, f"start_date ({start_str}) is after end_date ({end_str})"

    delta = (end - start).days
    if delta > GA_MAX_DATE_RANGE_DAYS:
        return start_str, end_str, (
            f"Date range ({delta} days) exceeds maximum allowed "
            f"({GA_MAX_DATE_RANGE_DAYS} days)"
        )

    return start_str, end_str, None


def _build_cache_key(property_id: str, body: dict) -> str:
    """Build a deterministic Redis cache key from property_id + request body."""
    raw = f"{property_id}:{json.dumps(body, sort_keys=True)}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return f"{_CACHE_PREFIX}{digest}"


class GoogleAnalyticsReporterInput(ToolInput):
    """Input schema: property_id, start_date, end_date, metrics, dimensions, limit."""

    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(GA_ACTIONS)}",
    )
    property_id: str = Field(
        ...,
        description="Google Analytics property ID (e.g., 'properties/123456') or numeric ID. "
        "Uses GA_PROPERTY_ID env var if omitted.",
    )
    start_date: str = Field(
        ...,
        description="Start date (YYYY-MM-DD, 'today', 'yesterday', '7d', '30d')",
    )
    end_date: str = Field(
        ...,
        description="End date (YYYY-MM-DD, 'today', 'yesterday')",
    )
    metrics: list[str] | None = Field(
        None,
        description=f"Metrics to fetch: {', '.join(sorted(_VALID_METRICS))}",
    )
    dimensions: list[str] | None = Field(
        None,
        description=f"Dimensions to group by: {', '.join(sorted(_VALID_DIMENSIONS))}",
    )
    limit: int = Field(
        100, ge=1, le=100000,
        description="Max rows to return. Default: 100.",
    )
    order_by: str | None = Field(
        None,
        description="Metric to sort by (must be in metrics list)",
    )
    bypass_cache: bool = Field(
        False,
        description="If True, skip Redis cache and fetch fresh data.",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class GoogleAnalyticsReporterTool(BaseTool):
    """Fetch Google Analytics metrics via the Data API v1 with Redis caching."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="google_analytics_reporter",
            name="Google Analytics Reporter",
            description=(
                "Fetch pageviews, user metrics, conversion data, and reports "
                "from Google Analytics using the Data API v1 with OAuth2. "
                "Results are cached in Redis for 5 minutes. Validates date "
                f"ranges (max {GA_MAX_DATE_RANGE_DAYS} days)."
            ),
            category="seo-marketing",
            input_schema=GoogleAnalyticsReporterInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "rows": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "dimension_values": {"type": "object"},
                            "metric_values": {"type": "object"},
                        },
                    }},
                    "totals": {"type": "object"},
                    "query_info": {
                        "type": "object",
                        "properties": {
                            "date_range": {"type": "string"},
                            "row_count": {"type": "integer"},
                        },
                    },
                    "success": {"type": "boolean"},
                },
            },
            tags=["google-analytics", "seo", "reporting", "metrics", "analytics"],
            requires_auth=True,
            timeout_seconds=GA_TIMEOUT + 15,
        )
        super().__init__(metadata=metadata)

    # ── Redis helper ─────────────────────────────────────────────

    async def _get_redis(self):
        """Get Redis client for caching."""
        try:
            from app.tools.redis_cache import get_redis
            return await get_redis()
        except Exception as e:
            logger.debug("Redis not available for GA caching: %s", e)
            return None

    async def _cache_get(self, key: str) -> dict | None:
        """Get cached GA result."""
        r = await self._get_redis()
        if r is None:
            return None
        try:
            data = await r.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug("Redis cache read failed: %s", e)
        return None

    async def _cache_set(self, key: str, value: dict, ttl: int = GA_CACHE_TTL) -> None:
        """Set cached GA result."""
        r = await self._get_redis()
        if r is None:
            return
        try:
            await r.setex(key, ttl, json.dumps(value, default=str))
        except Exception as e:
            logger.debug("Redis cache write failed: %s", e)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = GoogleAnalyticsReporterInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.action not in GA_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. "
                f"Use: {', '.join(GA_ACTIONS)}",
            )

        # Resolve property_id
        property_id = validated.property_id or GA_PROPERTY_ID
        if not property_id and validated.action != "list_properties":
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="No property_id provided. Set GA_PROPERTY_ID env var or pass property_id.",
            )

        # Add properties/ prefix if numeric
        if property_id and not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        try:
            result = await self._execute_action(validated, property_id)
            result["success"] = True
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("Google Analytics API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Google Analytics API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.warning("google_analytics_reporter failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(
        self, validated: GoogleAnalyticsReporterInput, property_id: str | None
    ) -> dict[str, Any]:
        if validated.action == "run_report":
            return await self._run_report(validated, property_id)
        elif validated.action == "get_realtime":
            return await self._get_realtime(validated, property_id)
        elif validated.action == "list_properties":
            return await self._list_properties(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}", "success": False}

    # ── Auth helpers ─────────────────────────────────────────────

    async def _get_headers(self) -> dict[str, str]:
        """Get authentication headers — prefers OAuth2, falls back to API key."""
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if GA_SERVICE_ACCOUNT_JSON:
            token = await self._get_oauth2_token()
            headers["Authorization"] = f"Bearer {token}"
        elif GA_API_KEY:
            pass
        else:
            raise ValueError(
                "No Google Analytics credentials configured. "
                "Set GA_SERVICE_ACCOUNT_JSON or GA_API_KEY."
            )

        return headers

    async def _get_oauth2_token(self) -> str:
        """Get OAuth2 access token using service account credentials."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.service_account import Credentials

            creds_dict = json.loads(GA_SERVICE_ACCOUNT_JSON)
            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/analytics.readonly"],
            )
            credentials.refresh(Request())
            return credentials.token  # type: ignore[attr-defined]
        except Exception as e:
            logger.error("Failed to get Google OAuth2 token: %s", e)
            raise ValueError(f"OAuth2 authentication failed: {e}") from e

    # ── Action handlers ──────────────────────────────────────────

    async def _run_report(
        self, validated: GoogleAnalyticsReporterInput, property_id: str | None
    ) -> dict[str, Any]:
        """Run a Google Analytics report with Redis caching."""
        if not validated.metrics:
            return {"error": "metrics is required for run_report", "success": False}

        # Build request body
        start_date = _parse_date(validated.start_date or "30d")
        end_date = _parse_date(validated.end_date or "today")

        # Validate date range
        sd, ed, range_err = _validate_date_range(start_date, end_date)
        if range_err:
            return {"error": range_err, "success": False}

        body: dict[str, Any] = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "metrics": [{"name": m} for m in validated.metrics],
            "limit": str(validated.limit),
        }

        if validated.dimensions:
            body["dimensions"] = [{"name": d} for d in validated.dimensions]

        if validated.order_by:
            body["orderBys"] = [
                {"metric": {"metricName": validated.order_by}, "desc": True}
            ]

        # Check Redis cache (skip for realtime or if bypass_cache set)
        cache_key = _build_cache_key(property_id or "unknown", body)
        if not validated.bypass_cache:
            cached = await self._cache_get(cache_key)
            if cached:
                cached["cached"] = True
                return cached

        # Fetch from API
        headers = await self._get_headers()
        params: dict[str, Any] = {}
        if GA_API_KEY and "Authorization" not in headers:
            params["key"] = GA_API_KEY

        async with httpx.AsyncClient(timeout=GA_TIMEOUT, headers=headers) as client:
            resp = await client.post(
                f"{GA_API_BASE}/{property_id}:runReport",
                params=params,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        rows = data.get("rows", [])
        dimension_headers = data.get("dimensionHeaders", [])
        metric_headers = data.get("metricHeaders", [])

        # Build table
        table = []
        for row in rows:
            dim_values = row.get("dimensionValues", [])
            metric_values = row.get("metricValues", [])
            entry: dict[str, Any] = {}
            for h, v in zip(dimension_headers, dim_values, strict=False):
                entry[h.get("name", "dim")] = v.get("value", "")
            for h, v in zip(metric_headers, metric_values, strict=False):
                entry[h.get("name", "metric")] = v.get("value", "")
            table.append(entry)

        result = {
            "action": "run_report",
            "property_id": property_id,
            "start_date": start_date,
            "end_date": end_date,
            "row_count": len(table),
            "rows": table,
            "totals": data.get("totals", []),
            "query_info": {
                "date_range": f"{start_date} to {end_date}",
                "row_count": len(table),
            },
            "metadata": {
                "metrics_used": validated.metrics,
                "dimensions_used": validated.dimensions,
                "currency": data.get("metadata", {}).get("currencyCode"),
                "timezone": data.get("metadata", {}).get("timeZone"),
            },
            "cached": False,
            "success": True,
        }

        # Cache result
        await self._cache_set(cache_key, result)

        return result

    async def _get_realtime(
        self, validated: GoogleAnalyticsReporterInput, property_id: str | None
    ) -> dict[str, Any]:
        """Get real-time analytics data (not cached)."""
        headers = await self._get_headers()
        params: dict[str, Any] = {}

        if GA_API_KEY and "Authorization" not in headers:
            params["key"] = GA_API_KEY

        async with httpx.AsyncClient(timeout=GA_TIMEOUT, headers=headers) as client:
            resp = await client.post(
                f"{GA_API_BASE}/{property_id}:runRealtimeReport",
                params=params,
                json={
                    "metrics": [
                        {"name": m}
                        for m in (validated.metrics or ["activeUsers"])
                    ],
                    "dimensions": [
                        {"name": d}
                        for d in (validated.dimensions or ["pagePath", "deviceCategory"])
                    ],
                    "limit": str(validated.limit),
                },
            )
            resp.raise_for_status()
            data = resp.json()

        rows = data.get("rows", [])
        dimension_headers = data.get("dimensionHeaders", [])
        metric_headers = data.get("metricHeaders", [])

        table = []
        for row in rows:
            dim_values = row.get("dimensionValues", [])
            metric_values = row.get("metricValues", [])
            entry: dict[str, Any] = {}
            for h, v in zip(dimension_headers, dim_values, strict=False):
                entry[h.get("name", "dim")] = v.get("value", "")
            for h, v in zip(metric_headers, metric_values, strict=False):
                entry[h.get("name", "metric")] = v.get("value", "")
            table.append(entry)

        active_now = sum(
            int(r.get("activeUsers", r.get("activeUsers", 0))) for r in table
        )

        return {
            "action": "get_realtime",
            "property_id": property_id,
            "active_users_now": active_now,
            "row_count": len(table),
            "rows": table,
            "success": True,
        }

    async def _list_properties(
        self, validated: GoogleAnalyticsReporterInput
    ) -> dict[str, Any]:
        """List available GA4 properties for the authenticated account."""
        headers = await self._get_headers()
        params: dict[str, Any] = {}

        if GA_API_KEY and "Authorization" not in headers:
            params["key"] = GA_API_KEY

        admin_url = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"

        # Check cache
        cache_key = f"{_CACHE_PREFIX}list_properties_{validated.limit}"
        if not validated.bypass_cache:
            cached = await self._cache_get(cache_key)
            if cached:
                cached["cached"] = True
                return cached

        async with httpx.AsyncClient(timeout=GA_TIMEOUT, headers=headers) as client:
            resp = await client.get(admin_url, params=params)
            resp.raise_for_status()
            data = resp.json()

        account_summaries = data.get("accountSummaries", [])
        properties = []
        for account in account_summaries:
            for prop in account.get("propertySummaries", []):
                properties.append({
                    "property_id": prop.get("property", "").split("/")[-1],
                    "property_name": prop.get("displayName", ""),
                    "account_name": account.get("displayName", ""),
                })

        result = {
            "action": "list_properties",
            "property_count": len(properties),
            "properties": properties[: validated.limit],
            "cached": False,
            "success": True,
        }

        await self._cache_set(cache_key, result, ttl=600)  # 10 min TTL for property list
        return result


# ── Register ──────────────────────────────────────────────────────────

register_tool(GoogleAnalyticsReporterTool())
