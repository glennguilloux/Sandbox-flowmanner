"""
OpenRouter Service

AI provider service for OpenRouter API.
Supports moonshotai/kimi-k2.5 and other OpenRouter models.
"""

import hashlib
import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OpenRouterService:
    """
    Service for interacting with OpenRouter API.

    Handles:
    - Chat completions
    - Cost tracking
    - Response caching
    - Retry logic
    """

    def __init__(self, api_key: str | None = None):
        # Use provided API key (user key) or fall back to platform key from environment
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.site_url = os.getenv(
            "OPENROUTER_SITE_URL", "https://workflows.glennguilloux.com"
        )
        self.referer = os.getenv(
            "OPENROUTER_REFERER", "https://workflows.glennguilloux.com"
        )

        # Rate limiting
        self.max_retries = int(os.getenv("OPENROUTER_MAX_RETRIES", "3"))
        self.retry_delay = float(os.getenv("OPENROUTER_RETRY_DELAY", "1.0"))

        # Caching
        self.cache_enabled = (
            os.getenv("OPENROUTER_CACHE_ENABLED", "true").lower() == "true"
        )
        self.cache_ttl = int(os.getenv("OPENROUTER_CACHE_TTL", "3600"))

        # HTTP client
        self.timeout = float(os.getenv("OPENROUTER_TIMEOUT", "60.0"))
        self._client: httpx.AsyncClient | None = None

        # Supported models
        self.supported_models = [
            "moonshotai/kimi-k2.5",
            "openrouter/google/gemma-2-9b-it:free",
            "openrouter/deepseek/deepseek-coder",
            "openrouter/anthropic/claude-3.5-sonnet",
            "openrouter/openai/gpt-4o",
            "openrouter/google/gemini-2.0-flash",
        ]

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout, headers=self._get_headers()
            )
        return self._client

    def _get_headers(self) -> dict[str, str]:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": "Workflows Platform",
        }

    def _get_cache_key(self, model: str, messages: list[dict], max_tokens: int) -> str:
        """Generate cache key for request."""
        content = json.dumps(
            {"model": model, "messages": messages, "max_tokens": max_tokens},
            sort_keys=True,
        )
        return f"openrouter:cache:{hashlib.md5(content.encode()).hexdigest()}"

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        stream: bool = False,
        user_id: str | None = None,
        request_id: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Make a chat completion request to OpenRouter.

        Args:
            model: Model to use (e.g., "moonshotai/kimi-k2.5")
            messages: List of message dictionaries
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            stream: Whether to stream the response
            user_id: User ID for cost tracking
            request_id: Request ID for tracing

        Returns:
            Dict containing response and metadata
        """
        request_id = request_id or f"or-{int(time.time() * 1000)}"
        start_time = time.time()

        # Validate model
        if model not in self.supported_models:
            logger.warning("Model %s not in supported list, proceeding anyway", model)

        # Check cache
        if self.cache_enabled and not stream:
            cache_key = self._get_cache_key(model, messages, max_tokens or 4096)
            cached = await self._get_cache(cache_key)
            if cached:
                logger.info("Cache hit for %s", model)
                return cached

        # Prepare request payload
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        # Add any additional kwargs
        payload.update(kwargs)

        # Make request with retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = await self._make_request(payload, request_id)

                # Calculate cost
                cost = await self._calculate_cost(response, model)

                # Prepare result
                result = {
                    "success": True,
                    "response": response,
                    "model": model,
                    "provider": "openrouter",
                    "cost_usd": cost["total"],
                    "input_tokens": cost["input_tokens"],
                    "output_tokens": cost["output_tokens"],
                    "duration": time.time() - start_time,
                    "request_id": request_id,
                    "cached": False,
                }

                # Cache response
                if self.cache_enabled and not stream:
                    await self._set_cache(cache_key, result, self.cache_ttl)

                return result

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(
                    "OpenRouter request failed (attempt %s): %s", attempt + 1, e
                )

                if e.response.status_code == 429:
                    # Rate limited - wait longer
                    await asyncio.sleep(self.retry_delay * (2**attempt))
                elif e.response.status_code >= 500:
                    # Server error - retry
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    # Client error - don't retry
                    break

            except Exception as e:
                last_error = e
                logger.error("OpenRouter request error: %s", e)
                await asyncio.sleep(self.retry_delay * (attempt + 1))

        # All retries failed
        return {
            "success": False,
            "error": str(last_error),
            "model": model,
            "provider": "openrouter",
            "request_id": request_id,
            "duration": time.time() - start_time,
        }

    async def _make_request(
        self, payload: dict[str, Any], request_id: str
    ) -> dict[str, Any]:
        """Make the actual HTTP request."""
        client = self._get_client()

        response = await client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers={
                **self._get_headers(),
                "X-Request-ID": request_id,
            },
        )
        response.raise_for_status()

        return response.json()

    async def stream_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        user_id: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream chat completion from OpenRouter.

        Yields:
            Dict containing response chunks and metadata
        """
        request_id = f"or-stream-{int(time.time() * 1000)}"

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        payload.update(kwargs)

        client = self._get_client()

        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={
                    **self._get_headers(),
                    "X-Request-ID": request_id,
                },
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            yield {
                                "success": True,
                                "chunk": chunk,
                                "model": model,
                                "provider": "openrouter",
                                "request_id": request_id,
                            }
                        except json.JSONDecodeError:
                            logger.warning(
                                "Failed to parse streaming response: %s", data
                            )

        except Exception as e:
            logger.error("Streaming error: %s", e)
            yield {
                "success": False,
                "error": str(e),
                "model": model,
                "provider": "openrouter",
                "request_id": request_id,
            }

    async def _calculate_cost(
        self, response: dict[str, Any], model: str
    ) -> dict[str, float]:
        """Calculate cost for OpenRouter response."""
        # OpenRouter provides usage info in response
        usage = response.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        # Cost rates (USD per token)
        rates = {
            "moonshotai/kimi-k2.5": {"input": 0.0, "output": 0.0},  # Free during beta
            "openrouter/google/gemma-2-9b-it:free": {"input": 0.0, "output": 0.0},
            "openrouter/deepseek/deepseek-coder": {"input": 0.14e-6, "output": 0.28e-6},
            "openrouter/anthropic/claude-3.5-sonnet": {
                "input": 3.0e-6,
                "output": 15.0e-6,
            },
            "openrouter/openai/gpt-4o": {"input": 2.5e-6, "output": 10.0e-6},
            "openrouter/google/gemini-2.0-flash": {"input": 0.35e-6, "output": 1.4e-6},
        }

        model_rates = rates.get(model, {"input": 1.0e-6, "output": 2.0e-6})

        input_cost = input_tokens * model_rates["input"]
        output_cost = output_tokens * model_rates["output"]

        # OpenRouter adds 5.5% platform fee for non-free models
        if model not in [
            "moonshotai/kimi-k2.5",
            "openrouter/google/gemma-2-9b-it:free",
        ]:
            platform_fee = 1.055
            input_cost *= platform_fee
            output_cost *= platform_fee

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total": input_cost + output_cost,
        }

    async def _get_cache(self, key: str) -> dict[str, Any] | None:
        """Get cached response."""
        try:
            import redis

            redis_client = redis.Redis.from_url(
                os.getenv("REDIS_URL", "redis://redis:6379/2"), decode_responses=True
            )
            cached = redis_client.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning("Cache read error: %s", e)
        return None

    async def _set_cache(self, key: str, value: dict[str, Any], ttl: int):
        """Set cached response."""
        try:
            import redis

            redis_client = redis.Redis.from_url(
                os.getenv("REDIS_URL", "redis://redis:6379/2"), decode_responses=True
            )
            redis_client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.warning("Cache write error: %s", e)

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models from OpenRouter."""
        try:
            client = self._get_client()
            response = await client.get(
                f"{self.base_url}/models", headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.error("Failed to list models: %s", e)
            return []

    async def get_model_info(self, model: str) -> dict[str, Any] | None:
        """Get information about a specific model."""
        models = await self.list_models()
        for m in models:
            if m.get("id") == model:
                return m
        return None

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Import asyncio for async operations
import asyncio
