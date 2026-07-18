"""
DeepSeek Service

AI provider service for DeepSeek API.
Supports deepseek-chat and deepseek-reasoner models.
"""

import hashlib
import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

# Config was imported from a non-existent 'app.app_config' module. Use the
# real settings/env instead. DeepSeek OpenAI-compatible base is
# https://api.deepseek.com (per ops). The Anthropic-compatible mirror lives at
# https://api.deepseek.com/anthropic but is not used on this path.
from app.config import settings

_DEEPSEEK_BASE_URL = getattr(settings, "DEEPSEEK_BASE_URL", None) or os.getenv(
    "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
)

logger = logging.getLogger(__name__)


class DeepSeekService:
    """
    Service for interacting with DeepSeek API.

    Handles:
    - Chat completions (deepseek-chat)
    - Reasoning completions (deepseek-reasoner)
    - Streaming support
    - Cost tracking
    - Retry logic
    """

    def __init__(self, api_key: str | None = None):
        # Use provided API key (user key) or fall back to platform key from Config
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = _DEEPSEEK_BASE_URL

        # Rate limiting
        self.max_retries = int(os.getenv("DEEPSEEK_MAX_RETRIES", "3"))
        self.retry_delay = float(os.getenv("DEEPSEEK_RETRY_DELAY", "1.0"))

        # HTTP client
        self.timeout = float(os.getenv("DEEPSEEK_TIMEOUT", "120.0"))
        self._client: httpx.AsyncClient | None = None

        # Supported models
        self.supported_models = [
            "deepseek-chat",
            "deepseek-reasoner",
        ]

        # Model IDs for API
        self.model_ids = {
            "deepseek-chat": "deepseek-chat",
            "deepseek-reasoner": "deepseek-reasoner",
        }

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout, headers=self._get_headers())
        return self._client

    def _get_headers(self) -> dict[str, str]:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get_cache_key(self, model: str, messages: list[dict], max_tokens: int) -> str:
        """Generate cache key for request."""
        content = json.dumps(
            {"model": model, "messages": messages, "max_tokens": max_tokens},
            sort_keys=True,
        )
        return f"deepseek:cache:{hashlib.md5(content.encode()).hexdigest()}"

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
        Make a chat completion request to DeepSeek.

        Args:
            model: Model to use ("deepseek-chat" or "deepseek-reasoner")
            messages: List of message dictionaries
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            stream: Whether to stream the response
            user_id: User ID for cost tracking
            request_id: Request ID for tracing

        Returns:
            Dict containing response and metadata
        """
        request_id = request_id or f"ds-{int(time.time() * 1000)}"
        start_time = time.time()

        # Validate model
        if model not in self.supported_models:
            logger.warning("Model %s not in supported list, proceeding anyway", model)

        # Prepare request payload
        payload = {
            "model": self.model_ids.get(model, model),
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
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = await self._make_request(payload, request_id)

                # Calculate cost
                cost = self._calculate_cost(response, model)

                # Extract content from response
                content = self._extract_content(response, model)

                # Prepare result
                result = {
                    "success": True,
                    "content": content,
                    "response": response,
                    "model": model,
                    "provider": "deepseek",
                    "cost_usd": cost["total"],
                    "input_tokens": cost["input_tokens"],
                    "output_tokens": cost["output_tokens"],
                    "reasoning_tokens": cost.get("reasoning_tokens", 0),
                    "duration": time.time() - start_time,
                    "request_id": request_id,
                }

                # Extract reasoning content if applicable
                if model == "deepseek-reasoner":
                    result["reasoning_content"] = self._extract_reasoning(response)

                return result

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning("DeepSeek request failed (attempt %s): %s", attempt + 1, e)

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
                logger.error("DeepSeek request error: %s", e)
                await asyncio.sleep(self.retry_delay * (attempt + 1))

        # All retries failed
        return {
            "success": False,
            "error": str(last_error),
            "model": model,
            "provider": "deepseek",
            "request_id": request_id,
            "duration": time.time() - start_time,
        }

    async def _make_request(self, payload: dict[str, Any], request_id: str) -> dict[str, Any]:
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
        Stream chat completion from DeepSeek.

        Yields:
            Dict containing response chunks and metadata
        """
        request_id = f"ds-stream-{int(time.time() * 1000)}"

        payload = {
            "model": self.model_ids.get(model, model),
            "messages": messages,
            "stream": True,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        payload.update(kwargs)

        client = self._get_client()
        reasoning_buffer = ""

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

                            # Handle reasoning content for deepseek-reasoner
                            is_reasoning = False
                            if model == "deepseek-reasoner":
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                if delta.get("reasoning_content"):
                                    reasoning_buffer += delta["reasoning_content"]
                                    is_reasoning = True

                            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")

                            yield {
                                "success": True,
                                "chunk": chunk,
                                "content": content,
                                "reasoning_content": (reasoning_buffer if is_reasoning else None),
                                "model": model,
                                "provider": "deepseek",
                                "request_id": request_id,
                                "is_reasoning": is_reasoning,
                            }
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse streaming response: %s", data)

        except Exception as e:
            logger.error("Streaming error: %s", e)
            yield {
                "success": False,
                "error": str(e),
                "model": model,
                "provider": "deepseek",
                "request_id": request_id,
            }

    def _extract_content(self, response: dict[str, Any], model: str) -> str:
        """Extract text content from response."""
        choices = response.get("choices", [])
        if not choices:
            return ""

        message = choices[0].get("message", {})
        content = message.get("content", "")

        return content if content else ""

    def _extract_reasoning(self, response: dict[str, Any]) -> str:
        """Extract reasoning content from deepseek-reasoner response."""
        choices = response.get("choices", [])
        if not choices:
            return ""

        message = choices[0].get("message", {})
        reasoning = message.get("reasoning_content", "")

        return reasoning

    def _calculate_cost(self, response: dict[str, Any], model: str) -> dict[str, float]:
        """Calculate cost for DeepSeek response."""
        usage = response.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)

        # DeepSeek pricing (USD per token)
        # https://api.deepseek.com/docs/pricing
        if model == "deepseek-reasoner":
            # Reasoning model has different pricing
            input_rate = 0.55e-6  # $0.55 per million input tokens
            output_rate = 2.55e-6  # $2.55 per million output tokens
            reasoning_rate = 7.15e-6  # $7.15 per million reasoning tokens
        else:
            # Standard chat model
            input_rate = 0.14e-6  # $0.14 per million input tokens
            output_rate = 0.28e-6  # $0.28 per million output tokens
            reasoning_rate = 0

        input_cost = input_tokens * input_rate
        output_cost = output_tokens * output_rate
        reasoning_cost = reasoning_tokens * reasoning_rate

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "reasoning_cost": reasoning_cost,
            "total": input_cost + output_cost + reasoning_cost,
        }

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models from DeepSeek."""
        # DeepSeek doesn't have a models endpoint, return static list
        return [
            {
                "id": "deepseek-chat",
                "object": "model",
                "created": 1700000000,
                "owned_by": "deepseek",
            },
            {
                "id": "deepseek-reasoner",
                "object": "model",
                "created": 1700000000,
                "owned_by": "deepseek",
            },
        ]

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
