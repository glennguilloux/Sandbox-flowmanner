"""
External API Tools — Agent-callable tools that call free external APIs.

weather_current   → current weather from Open-Meteo (no API key)
currency_convert  → currency conversion from frankfurter.app (no API key)
"""

from __future__ import annotations

import logging

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 15


# ── weather_current ──────────────────────────────────────────────────


class WeatherCurrentInput(ToolInput):
    location: str = Field(
        ...,
        description=(
            "City name or coordinates. Examples: 'Paris', 'New York', "
            "'48.8566,2.3522' (lat,lon)"
        ),
    )
    units: str = Field(
        "celsius",
        description="Temperature units: 'celsius' or 'fahrenheit'",
    )


async def _geocode(location: str) -> tuple[float, float, str]:
    """Resolve a location name to (lat, lon, display_name) via Open-Meteo geocoding."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": location, "count": 1, "language": "en"}

    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results")
    if not results:
        raise ValueError(f"Location not found: {location}")

    r = results[0]
    return r["latitude"], r["longitude"], r.get("name", location)


class WeatherCurrentTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="weather_current",
            name="Weather — Current",
            description="Get current weather conditions for a location (Open-Meteo, free, no API key)",
            category="external",
            input_schema=WeatherCurrentInput.schema_extra(),
            tags=["weather", "external", "api"],
            requires_auth=True,
            timeout_seconds=20,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = WeatherCurrentInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            lat, lon, display_name = await _geocode(validated.location)
        except ValueError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))
        except Exception as e:
            logger.exception("Geocoding failed")
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Geocoding failed: {e}"
            )

        try:
            temp_unit = "fahrenheit" if validated.units == "fahrenheit" else "celsius"
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "temperature_unit": temp_unit,
                "timezone": "auto",
            }

            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            current = data.get("current", {})

            # Map WMO weather codes to descriptions
            WMO_CODES = {
                0: "Clear sky",
                1: "Mainly clear",
                2: "Partly cloudy",
                3: "Overcast",
                45: "Fog",
                48: "Rime fog",
                51: "Light drizzle",
                53: "Moderate drizzle",
                55: "Dense drizzle",
                56: "Light freezing drizzle",
                57: "Dense freezing drizzle",
                61: "Slight rain",
                63: "Moderate rain",
                65: "Heavy rain",
                66: "Light freezing rain",
                67: "Heavy freezing rain",
                71: "Slight snow",
                73: "Moderate snow",
                75: "Heavy snow",
                77: "Snow grains",
                80: "Slight rain showers",
                81: "Moderate rain showers",
                82: "Violent rain showers",
                85: "Slight snow showers",
                86: "Heavy snow showers",
                95: "Thunderstorm",
                96: "Thunderstorm with slight hail",
                99: "Thunderstorm with heavy hail",
            }
            weather_code = current.get("weather_code", -1)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "location": display_name,
                    "latitude": lat,
                    "longitude": lon,
                    "temperature": current.get("temperature_2m"),
                    "units": validated.units,
                    "humidity_percent": current.get("relative_humidity_2m"),
                    "wind_speed_kmh": current.get("wind_speed_10m"),
                    "weather_code": weather_code,
                    "description": WMO_CODES.get(
                        weather_code, f"Unknown ({weather_code})"
                    ),
                },
            )
        except Exception as e:
            logger.exception("weather_current failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ── currency_convert ─────────────────────────────────────────────────


class CurrencyConvertInput(ToolInput):
    amount: float = Field(..., gt=0, description="Amount to convert")
    from_currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Source currency code (e.g. 'USD', 'EUR')",
    )
    to_currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Target currency code (e.g. 'GBP', 'JPY')",
    )


class CurrencyConvertTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="currency_convert",
            name="Currency Convert",
            description="Convert an amount between currencies (frankfurter.app, free, no API key)",
            category="external",
            input_schema=CurrencyConvertInput.schema_extra(),
            tags=["currency", "convert", "external", "api"],
            requires_auth=True,
            timeout_seconds=15,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = CurrencyConvertInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        from_ccy = validated.from_currency.upper()
        to_ccy = validated.to_currency.upper()

        if from_ccy == to_ccy:
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "input_amount": validated.amount,
                    "from_currency": from_ccy,
                    "to_currency": to_ccy,
                    "converted_amount": validated.amount,
                    "rate": 1.0,
                },
            )

        try:
            url = f"https://api.frankfurter.app/latest"
            params = {
                "amount": validated.amount,
                "from": from_ccy,
                "to": to_ccy,
            }

            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            rates = data.get("rates", {})
            converted = rates.get(to_ccy)

            if converted is None:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Currency not supported: {to_ccy}",
                )

            rate = converted / validated.amount if validated.amount else 0

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "input_amount": validated.amount,
                    "from_currency": from_ccy,
                    "to_currency": to_ccy,
                    "converted_amount": round(converted, 4),
                    "rate": round(rate, 6),
                    "date": data.get("date"),
                },
            )
        except httpx.HTTPStatusError as e:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"API error ({e.response.status_code}): {e.response.text[:200]}",
            )
        except Exception as e:
            logger.exception("currency_convert failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ── Register ─────────────────────────────────────────────────────────

register_tool(WeatherCurrentTool())
register_tool(CurrencyConvertTool())
