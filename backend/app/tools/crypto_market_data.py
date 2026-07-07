"""
Finance & Data Analysis Tools — Crypto Market Data.

crypto_market_data → Get real-time cryptocurrency pricing, volume, market
    cap, price changes, and trend data via the free CoinGecko API.
    Results are cached in Redis with a 5-minute TTL. No API key required.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool
from app.tools.redis_cache import get_redis

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
CRYPTO_TIMEOUT = int(os.getenv("CRYPTO_TIMEOUT", "30"))
CRYPTO_CACHE_TTL = int(os.getenv("CRYPTO_CACHE_TTL", "300"))  # 5 min default


# ── Input ─────────────────────────────────────────────────────────────

CRYPTO_ACTIONS = (
    "get_price",
    "get_market_data",
    "get_trending",
    "search_coins",
    "get_historical",
)


class CryptoMarketDataInput(ToolInput):
    action: str = Field(
        "get_market_data",
        description=(
            "Action: 'get_price' (simple price), 'get_market_data' (full market data), "
            "'get_trending' (trending coins), 'search_coins' (find coin IDs), "
            "'get_historical' (historical data on a date)"
        ),
    )
    coins: list[str] | None = Field(
        None,
        description=(
            "CoinGecko coin IDs (e.g. ['bitcoin', 'ethereum', 'solana']). "
            "Use 'search_coins' action to find IDs. Not required for 'get_trending'."
        ),
    )
    vs_currency: str = Field(
        "usd",
        description="Quote currency (e.g. 'usd', 'eur', 'btc', 'eth')",
    )
    include_market_cap: bool = Field(
        True,
        description="Include market cap data",
    )
    include_24hr_vol: bool = Field(
        True,
        description="Include 24h volume",
    )
    include_24hr_change: bool = Field(
        True,
        description="Include 24h price change %",
    )
    include_24h_change: bool | None = Field(
        None,
        description="Backward-compat alias for include_24hr_change.",
    )
    include_24h_vol: bool | None = Field(
        None,
        description="Backward-compat alias for include_24hr_vol.",
    )
    include_7d_chart: bool = Field(
        False,
        description="Include 7-day sparkline price chart data",
    )
    search_query: str | None = Field(
        None,
        description="Search term for 'search_coins' action",
    )
    date: str | None = Field(
        None,
        description="Date for 'get_historical' in DD-MM-YYYY format (e.g. '30-12-2024')",
    )
    order: str = Field(
        "market_cap_desc",
        description="Sort order: 'market_cap_desc', 'market_cap_asc', 'volume_desc', 'id_asc'",
    )
    per_page: int = Field(
        10,
        ge=1,
        le=250,
        description="Results per page for search (1-250)",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class CryptoMarketDataTool(BaseTool):
    """Fetch cryptocurrency market data via the free CoinGecko API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="crypto_market_data",
            name="Crypto Market Data",
            description=(
                "Get real-time cryptocurrency pricing, market cap, 24h volume, "
                "price change percentages, and trending coins via the CoinGecko API "
                "(free tier — no API key required). Supports 14,000+ coins across "
                "70+ fiat/BTC/ETH quote currencies. Results cached in Redis (5 min TTL)."
            ),
            category="finance-data-analysis",
            input_schema=CryptoMarketDataInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "coins": {"type": "array"},
                    "cached": {"type": "boolean"},
                },
            },
            tags=[
                "crypto",
                "bitcoin",
                "ethereum",
                "coingecko",
                "finance",
                "trading",
                "web3",
                "defi",
            ],
            requires_auth=False,  # CoinGecko free API — no auth needed
            timeout_seconds=CRYPTO_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = CryptoMarketDataInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if validated.action not in CRYPTO_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(CRYPTO_ACTIONS)}",
            )

        if validated.action != "get_trending" and not validated.coins and not validated.search_query:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="coins required (except for 'get_trending' or 'search_coins'). Use 'search_coins' action to find IDs.",
            )

        try:
            result = await self._fetch_with_cache(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("CoinGecko API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            # CoinGecko 429 = rate limited
            if e.response.status_code == 429:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error="CoinGecko rate limit reached (10-30 req/min for free tier). Wait 60 seconds and try again.",
                )
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"CoinGecko API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.warning("crypto_market_data failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _fetch_with_cache ────────────────────────────────────────

    async def _fetch_with_cache(self, validated: CryptoMarketDataInput) -> dict[str, Any]:
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
        data = await self._call_coingecko(validated)
        data["cached"] = False

        # Store in Redis (but not for trending — it changes too fast)
        if redis_client and validated.action != "get_trending":
            try:
                import json

                await redis_client.setex(cache_key, CRYPTO_CACHE_TTL, json.dumps(data))
            except Exception as e:
                logger.warning("Redis setex failed (non-fatal): %s", e)

        return data

    # ── _call_coingecko ──────────────────────────────────────────

    async def _call_coingecko(self, validated: CryptoMarketDataInput) -> dict[str, Any]:
        """Route to the correct CoinGecko endpoint."""
        if validated.action == "get_price":
            return await self._get_price(validated)
        elif validated.action == "get_market_data":
            return await self._get_market_data(validated)
        elif validated.action == "get_trending":
            return await self._get_trending()
        elif validated.action == "search_coins":
            return await self._search_coins(validated)
        elif validated.action == "get_historical":
            return await self._get_historical(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}"}

    # ── Endpoint methods ─────────────────────────────────────────

    async def _get_price(self, validated: CryptoMarketDataInput) -> dict[str, Any]:
        """GET /simple/price — lightweight price-only endpoint."""
        coin_ids = ",".join(validated.coins or []).lower().replace(" ", "")
        params: dict[str, Any] = {
            "ids": coin_ids,
            "vs_currencies": validated.vs_currency,
        }
        if validated.include_market_cap:
            params["include_market_cap"] = "true"
        if validated.include_24hr_vol:
            params["include_24hr_vol"] = "true"
        if validated.include_24hr_change:
            params["include_24hr_change"] = "true"

        async with httpx.AsyncClient(timeout=CRYPTO_TIMEOUT) as client:
            resp = await client.get(f"{COINGECKO_BASE}/simple/price", params=params)
            resp.raise_for_status()
            raw = resp.json()

        coins = []
        for coin_id, data in raw.items():
            coins.append(
                {
                    "id": coin_id,
                    "price": data.get(validated.vs_currency, None),
                    "market_cap": data.get(f"{validated.vs_currency}_market_cap", None),
                    "24h_volume": data.get(f"{validated.vs_currency}_24h_vol", None),
                    "24h_change_pct": data.get(f"{validated.vs_currency}_24h_change", None),
                }
            )

        return {
            "action": "get_price",
            "vs_currency": validated.vs_currency,
            "coins": coins,
        }

    async def _get_market_data(self, validated: CryptoMarketDataInput) -> dict[str, Any]:
        """GET /coins/markets — full market data with optional 7d change."""
        coin_ids = ",".join(validated.coins or []).lower().replace(" ", "")
        params: dict[str, Any] = {
            "vs_currency": validated.vs_currency,
            "ids": coin_ids,
            "order": validated.order,
            "per_page": min(len(validated.coins), validated.per_page),
            "page": 1,
            "sparkline": "false",
        }
        if validated.include_7d_chart:
            params["price_change_percentage"] = "7d"
        elif validated.include_24hr_change:
            params["price_change_percentage"] = "24h"

        async with httpx.AsyncClient(timeout=CRYPTO_TIMEOUT) as client:
            resp = await client.get(f"{COINGECKO_BASE}/coins/markets", params=params)
            resp.raise_for_status()
            raw = resp.json()

        coins = []
        for c in raw:
            entry: dict[str, Any] = {
                "id": c.get("id", ""),
                "symbol": c.get("symbol", ""),
                "name": c.get("name", ""),
                "image": c.get("image", ""),
                "current_price": c.get("current_price"),
                "market_cap": c.get("market_cap"),
                "market_cap_rank": c.get("market_cap_rank"),
                "total_volume": c.get("total_volume"),
                "high_24h": c.get("high_24h"),
                "low_24h": c.get("low_24h"),
                "price_change_24h": c.get("price_change_24h"),
                "price_change_pct_24h": c.get("price_change_percentage_24h"),
                "circulating_supply": c.get("circulating_supply"),
                "total_supply": c.get("total_supply"),
                "ath": c.get("ath"),
                "ath_change_pct": c.get("ath_change_percentage"),
                "ath_date": c.get("ath_date"),
                "last_updated": c.get("last_updated"),
            }
            if validated.include_7d_chart:
                entry["price_change_pct_7d"] = c.get("price_change_percentage_7d_in_currency")
            coins.append(entry)

        return {
            "action": "get_market_data",
            "vs_currency": validated.vs_currency,
            "count": len(coins),
            "coins": coins,
        }

    async def _get_trending(self) -> dict[str, Any]:
        """GET /search/trending — trending coins in last 24h."""
        async with httpx.AsyncClient(timeout=CRYPTO_TIMEOUT) as client:
            resp = await client.get(f"{COINGECKO_BASE}/search/trending")
            resp.raise_for_status()
            raw = resp.json()

        coins = []
        for item in raw.get("coins", []):
            c = item.get("item", {})
            coins.append(
                {
                    "id": c.get("id", ""),
                    "name": c.get("name", ""),
                    "symbol": c.get("symbol", ""),
                    "market_cap_rank": c.get("market_cap_rank"),
                    "thumb": c.get("thumb", ""),
                    "score": c.get("score", 0),
                    "price_btc": c.get("price_btc"),
                }
            )

        nfts = []
        for item in raw.get("nfts", []):
            n = item.get("nft", {})
            nfts.append(
                {
                    "id": n.get("id", ""),
                    "name": n.get("name", ""),
                    "symbol": n.get("symbol", ""),
                    "thumb": n.get("thumb", ""),
                    "floor_price_24h_pct": n.get("floor_price_24h_percentage_change"),
                }
            )

        return {
            "action": "get_trending",
            "coins": coins,
            "nfts": nfts,
        }

    async def _search_coins(self, validated: CryptoMarketDataInput) -> dict[str, Any]:
        """GET /search — find coin IDs by name/symbol."""
        query = validated.search_query or ",".join(validated.coins or []) or ""
        params = {"query": query}

        async with httpx.AsyncClient(timeout=CRYPTO_TIMEOUT) as client:
            resp = await client.get(f"{COINGECKO_BASE}/search", params=params)
            resp.raise_for_status()
            raw = resp.json()

        coins = [
            {
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "symbol": c.get("symbol", ""),
                "market_cap_rank": c.get("market_cap_rank"),
                "thumb": c.get("thumb", ""),
            }
            for c in raw.get("coins", [])[: validated.per_page]
        ]

        return {
            "action": "search_coins",
            "query": query,
            "count": len(coins),
            "coins": coins,
            "also_found_exchanges": [e.get("id") for e in raw.get("exchanges", [])[:5]],
        }

    async def _get_historical(self, validated: CryptoMarketDataInput) -> dict[str, Any]:
        """GET /coins/{id}/history — historical data for a specific date."""
        coin_id = ",".join(validated.coins or []).lower().strip()
        if "," in coin_id:
            raise ValueError(
                "get_historical supports only a single coin ID. Use e.g. 'bitcoin' not 'bitcoin,ethereum'."
            )
        date = validated.date or ""

        params: dict[str, Any] = {
            "date": date,
            "localization": "false",
        }

        async with httpx.AsyncClient(timeout=CRYPTO_TIMEOUT) as client:
            resp = await client.get(f"{COINGECKO_BASE}/coins/{coin_id}/history", params=params)
            resp.raise_for_status()
            raw = resp.json()

        market = raw.get("market_data", {})
        return {
            "action": "get_historical",
            "coin_id": coin_id,
            "date": date,
            "name": raw.get("name", coin_id),
            "symbol": raw.get("symbol", ""),
            "price": market.get("current_price", {}).get(validated.vs_currency),
            "market_cap": market.get("market_cap", {}).get(validated.vs_currency),
            "total_volume": market.get("total_volume", {}).get(validated.vs_currency),
            "image": raw.get("image", {}).get("small", ""),
        }

    # ── _cache_key ───────────────────────────────────────────────

    @staticmethod
    def _cache_key(validated: CryptoMarketDataInput) -> str:
        """Build a deterministic cache key from input params."""
        parts = [
            "crypto",
            validated.action,
            ",".join(validated.coins or []).lower().replace(" ", ""),
            validated.vs_currency,
            validated.date or "",
            str(validated.include_market_cap),
            str(validated.include_24hr_change),
        ]
        return ":".join(parts)


# ── Register ──────────────────────────────────────────────────────────

register_tool(CryptoMarketDataTool())
