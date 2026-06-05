"""
Finance & Data Analysis Tools — Stock Price Tracker.

stock_price_tracker → Fetch end-of-day or intraday stock prices via Alpha
    Vantage API with Redis-backed caching (5 min TTL).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import (
    BaseTool,
    ToolInput,
    ToolMetadata,
    ToolResult,
    is_placeholder,
    register_tool,
)
from app.tools.redis_cache import get_redis

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"
STOCK_TIMEOUT = int(os.getenv("STOCK_TIMEOUT", "30"))
STOCK_CACHE_TTL = int(os.getenv("STOCK_CACHE_TTL", "300"))  # 5 min default


# ── Helpers ───────────────────────────────────────────────────────────


def _interval_for_raw(raw: dict) -> str:
    """Extract interval from raw response metadata for intraday."""
    meta = raw.get("Meta Data", {})
    for key in meta:
        if "interval" in key.lower():
            return key.split("(")[-1].rstrip(")")
    return "5min"


# ── Input ─────────────────────────────────────────────────────────────

QUOTE_FUNCTIONS = (
    "GLOBAL_QUOTE",
    "TIME_SERIES_DAILY",
    "TIME_SERIES_INTRADAY",
    "SYMBOL_SEARCH",
    "CURRENCY_EXCHANGE_RATE",
    "FX_DAILY",
    "CRYPTO_INTRADAY",
    "DIGITAL_CURRENCY_DAILY",
)


class StockPriceTrackerInput(ToolInput):
    action: str = Field(
        "GLOBAL_QUOTE",
        description=(
            "Alpha Vantage function: 'GLOBAL_QUOTE' (current price), "
            "'TIME_SERIES_DAILY' (daily history), "
            "'TIME_SERIES_INTRADAY' (intraday), "
            "'SYMBOL_SEARCH' (find symbols), "
            "'CURRENCY_EXCHANGE_RATE' (forex), "
            "'FX_DAILY' (forex history), "
            "'CRYPTO_INTRADAY' (crypto intraday), "
            "'DIGITAL_CURRENCY_DAILY' (crypto daily)"
        ),
    )
    symbols: list[str] = Field(
        ...,
        description="Stock/forex/crypto symbols (e.g., ['IBM', 'AAPL']), max 20. First symbol used for single-symbol endpoints.",
    )
    range: str = Field(
        "1d",
        description="Data range: '1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', 'max'",
    )
    include_extended: bool = Field(
        False,
        description="Include pre/post market data (only for '1d' range)",
    )
    market: str | None = Field(
        None,
        description="Exchange market for crypto (e.g., 'USD'). Required for CRYPTO_INTRADAY/DIGITAL_CURRENCY_DAILY.",
    )
    interval: str = Field(
        "5min",
        description="Interval for TIME_SERIES_INTRADAY: '1min', '5min', '15min', '30min', '60min'",
    )
    outputsize: str = Field(
        "compact",
        description="Output size: 'compact' (latest 100) or 'full' (all data)",
    )
    keywords: str | None = Field(
        None,
        description="Keywords for SYMBOL_SEARCH",
    )
    from_currency: str | None = Field(
        None,
        description="From currency for CURRENCY_EXCHANGE_RATE (e.g. 'USD')",
    )
    to_currency: str | None = Field(
        None,
        description="To currency for CURRENCY_EXCHANGE_RATE (e.g. 'EUR')",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class StockPriceTrackerTool(BaseTool):
    """Fetch stock, forex, and crypto prices via Alpha Vantage API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="stock_price_tracker",
            name="Stock Price Tracker",
            description=(
                "Fetch end-of-day, intraday, or current stock prices, forex rates, "
                "and crypto quotes via the Alpha Vantage API. Supports symbol search "
                "and daily/intraday time series. Results are cached in Redis for 5 min. "
                "Requires ALPHA_VANTAGE_API_KEY env var."
            ),
            category="finance-data-analysis",
            input_schema=StockPriceTrackerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "function": {"type": "string"},
                    "data": {"type": "object"},
                    "cached": {"type": "boolean"},
                },
            },
            tags=["stocks", "finance", "trading", "forex", "crypto", "alpha-vantage"],
            requires_auth=True,
            timeout_seconds=STOCK_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = StockPriceTrackerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.action not in QUOTE_FUNCTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown function: '{validated.action}'. Use: {', '.join(QUOTE_FUNCTIONS)}",
            )

        api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")

        if not api_key:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Alpha Vantage not configured. Set ALPHA_VANTAGE_API_KEY env var. "
                "Get a free key at https://www.alphavantage.co/support/#api-key",
            )

        if is_placeholder(api_key):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Alpha Vantage not configured. Replace placeholder value for "
                "ALPHA_VANTAGE_API_KEY with a real key from https://www.alphavantage.co/support/#api-key",
            )

        try:
            result = await self._fetch_with_cache(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("Alpha Vantage API error: %s", e)
            detail = e.response.text[:500] if e.response.text else str(e)
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Alpha Vantage API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.warning("stock_price_tracker failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _fetch_with_cache ────────────────────────────────────────

    async def _fetch_with_cache(
        self, validated: StockPriceTrackerInput
    ) -> dict[str, Any]:
        """Try Redis cache first, fall back to API call."""
        cache_key = self._cache_key(validated)

        # Try Redis
        redis_client = get_redis()
        if redis_client:
            try:
                cached = await redis_client.get(cache_key)
                if cached:
                    import json

                    data = json.loads(cached)
                    data["cached"] = True
                    return data
            except Exception as e:
                logger.warning("Redis get failed (non-fatal): %s", e)

        # Fetch from API
        data = await self._call_alpha_vantage(validated)
        data["cached"] = False

        # Store in Redis
        if redis_client:
            try:
                import json

                await redis_client.setex(cache_key, STOCK_CACHE_TTL, json.dumps(data))
            except Exception as e:
                logger.warning("Redis setex failed (non-fatal): %s", e)

        return data

    # ── _call_alpha_vantage ──────────────────────────────────────

    async def _call_alpha_vantage(
        self, validated: StockPriceTrackerInput
    ) -> dict[str, Any]:
        """Call Alpha Vantage API."""
        sym = self._primary_symbol(validated)
        params: dict[str, Any] = {
            "function": validated.action,
            "apikey": os.getenv("ALPHA_VANTAGE_API_KEY", ""),
        }

        if validated.action == "SYMBOL_SEARCH":
            params["keywords"] = validated.keywords or sym
        elif validated.action == "CURRENCY_EXCHANGE_RATE":
            params["from_currency"] = (
                validated.from_currency or sym.split("/")[0] if "/" in sym else sym
            )
            params["to_currency"] = validated.to_currency or (
                sym.split("/")[1] if "/" in sym else "USD"
            )
        elif validated.action in ("CRYPTO_INTRADAY", "DIGITAL_CURRENCY_DAILY"):
            params["symbol"] = sym
            params["market"] = validated.market or "USD"
        elif validated.action == "FX_DAILY":
            params["from_symbol"] = (
                validated.from_currency or sym.split("/")[0] if "/" in sym else sym
            )
            params["to_symbol"] = validated.to_currency or (
                sym.split("/")[1] if "/" in sym else "USD"
            )
            params["outputsize"] = validated.outputsize
        elif validated.action == "TIME_SERIES_INTRADAY":
            params["symbol"] = sym
            params["interval"] = validated.interval
            params["outputsize"] = validated.outputsize
        elif validated.action == "TIME_SERIES_DAILY":
            params["symbol"] = sym
            params["outputsize"] = validated.outputsize
        else:
            # GLOBAL_QUOTE and others
            params["symbol"] = sym

        async with httpx.AsyncClient(timeout=STOCK_TIMEOUT) as client:
            resp = await client.get(ALPHA_VANTAGE_BASE, params=params)
            resp.raise_for_status()
            raw = resp.json()

        # Alpha Vantage returns errors in a "Error Message" or "Note" key
        if "Error Message" in raw:
            raise ValueError(raw["Error Message"])
        if "Note" in raw and "API call frequency" in raw["Note"]:
            raise ValueError("Alpha Vantage rate limit reached. " + raw["Note"])

        # Extract and normalize the response
        result_data = self._normalize_response(validated.action, sym, raw)

        return {
            "symbols": validated.symbols,
            "primary_symbol": sym,
            "function": validated.action,
            "data": result_data,
        }

    # ── _primary_symbol ──────────────────────────────────────────

    @staticmethod
    def _primary_symbol(validated: StockPriceTrackerInput) -> str:
        """Get the primary symbol for single-symbol API endpoints."""
        return validated.symbols[0] if validated.symbols else ""

    # ── _normalize_response ──────────────────────────────────────

    def _normalize_response(
        self, action: str, symbol: str, raw: dict
    ) -> dict[str, Any]:
        """Extract the meaningful data from Alpha Vantage's verbose response."""
        if action == "GLOBAL_QUOTE":
            quote = raw.get("Global Quote", {})
            return {
                "symbol": quote.get("01. symbol", symbol),
                "price": quote.get("05. price", ""),
                "change": quote.get("09. change", ""),
                "change_percent": quote.get("10. change percent", ""),
                "volume": quote.get("06. volume", ""),
                "latest_trading_day": quote.get("07. latest trading day", ""),
                "previous_close": quote.get("08. previous close", ""),
                "open": quote.get("02. open", ""),
                "high": quote.get("03. high", ""),
                "low": quote.get("04. low", ""),
            }

        if action == "SYMBOL_SEARCH":
            matches = raw.get("bestMatches", [])
            return {
                "query": symbol,
                "matches": [
                    {
                        "symbol": m.get("1. symbol", ""),
                        "name": m.get("2. name", ""),
                        "type": m.get("3. type", ""),
                        "region": m.get("4. region", ""),
                        "currency": m.get("8. currency", ""),
                    }
                    for m in matches[:10]
                ],
                "count": len(matches),
            }

        if action == "CURRENCY_EXCHANGE_RATE":
            rate = raw.get("Realtime Currency Exchange Rate", {})
            return {
                "from": rate.get("1. From_Currency Code", ""),
                "to": rate.get("3. To_Currency Code", ""),
                "rate": rate.get("5. Exchange Rate", ""),
                "last_refreshed": rate.get("6. Last Refreshed", ""),
            }

        # For time series, return the series key
        time_series_keys = {
            "TIME_SERIES_DAILY": "Time Series (Daily)",
            "TIME_SERIES_INTRADAY": f"Time Series ({_interval_for_raw(raw)})",
            "FX_DAILY": "Time Series FX (Daily)",
            "CRYPTO_INTRADAY": "Time Series Crypto",
            "DIGITAL_CURRENCY_DAILY": "Time Series (Digital Currency Daily)",
        }

        series_key = time_series_keys.get(action)
        if series_key and series_key in raw:
            series = raw[series_key]
            # Return last 5 data points as summary + full series count
            items = list(series.items())
            summary = dict(items[:5])
            return {
                "latest": items[0][1] if items else {},
                "recent": summary,
                "data_points": len(items),
                "meta": raw.get("Meta Data", {}),
            }

        # Fallback: return raw response (stripped of the API key)
        raw.pop("apikey", None)
        return raw

    # ── _cache_key ───────────────────────────────────────────────

    @staticmethod
    def _cache_key(validated: StockPriceTrackerInput) -> str:
        """Build a deterministic cache key from input params."""
        sym = validated.symbols[0] if validated.symbols else ""
        parts = [
            "stock",
            validated.action,
            sym.upper(),
            validated.market or "",
            validated.interval,
            validated.outputsize,
            validated.from_currency or "",
            validated.to_currency or "",
        ]
        return ":".join(parts)


# ── Register ──────────────────────────────────────────────────────────

register_tool(StockPriceTrackerTool())
