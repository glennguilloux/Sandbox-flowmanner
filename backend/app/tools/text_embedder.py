"""
Vector & Embedding Tools — Text Embedder.

text_embedder → Generate vector embeddings from text using OpenAI, Cohere,
    or local (llama.cpp) models. Includes Redis caching (24h TTL), batch
    optimization, rate limiting, and BYOK support.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any, Literal

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_PROVIDER: Literal["openai", "cohere", "local"] = os.getenv("EMBEDDING_PROVIDER", "openai")  # type: ignore[assignment]
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
LOCAL_EMBED_URL = os.getenv(
    "EMBEDDING_LOCAL_URL", "http://localhost:11434/api/embeddings"
)
EMBED_TIMEOUT = int(os.getenv("EMBED_TIMEOUT", "30"))
CACHE_TTL = int(os.getenv("EMBED_CACHE_TTL", "86400"))  # 24 hours
MAX_BATCH_SIZE = int(os.getenv("EMBED_MAX_BATCH_SIZE", "100"))
_OPENAI_MODELS = {
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
}
_COHERE_MODELS = {
    "embed-english-v3.0",
    "embed-multilingual-v3.0",
    "embed-english-light-v3.0",
}

_CACHE_PREFIX = "embed:"


class TextEmbedderInput(ToolInput):
    """Input schema: texts, model, provider, dimensions, normalize, timeout."""

    texts: list[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_BATCH_SIZE,
        description=f"List of texts to embed (max {MAX_BATCH_SIZE})",
    )
    model: str = Field(
        DEFAULT_MODEL,
        description="Embedding model (e.g., 'text-embedding-3-small', 'embed-english-v3.0')",
    )
    provider: Literal["openai", "cohere", "local"] = Field(
        DEFAULT_PROVIDER,
        description="Provider: 'openai', 'cohere', or 'local' (llama.cpp)",
    )
    api_key: str | None = Field(
        None,
        description="Bring-your-own API key. Uses env var if omitted.",
    )
    dimensions: int | None = Field(
        None,
        description="Reduce embedding dimensions (OpenAI: 256-3072). Omit for default.",
    )
    encoding_format: Literal["float", "base64"] = Field(
        "float",
        description="Output encoding format",
    )
    normalize: bool = Field(
        True,
        description="L2-normalize embeddings after generation",
    )
    timeout_seconds: int = Field(
        EMBED_TIMEOUT,
        ge=5,
        le=120,
        description="Request timeout in seconds",
    )


class TextEmbedderTool(BaseTool):
    """Generate text embeddings via OpenAI, Cohere, or local models."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="text_embedder",
            name="Text Embedder",
            description=(
                "Generate vector embeddings from text using OpenAI, Cohere, "
                "or local (llama.cpp) models. Supports Redis caching (24h TTL), "
                "batch optimization, rate limiting with exponential backoff, "
                "and BYOK. Returns normalized float vectors."
            ),
            category="vector-embedding",
            input_schema=TextEmbedderInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "embeddings": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                    },
                    "model": {"type": "string"},
                    "dimensions": {"type": "integer"},
                    "total_tokens_used": {"type": "integer"},
                    "cached_count": {"type": "integer"},
                    "processing_time_ms": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["embeddings", "vectors", "openai", "cohere", "local", "rag"],
            requires_auth=True,
            timeout_seconds=EMBED_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    # ── Redis ────────────────────────────────────────────────────

    async def _get_redis(self):
        try:
            from app.tools.redis_cache import get_redis

            return await get_redis()
        except Exception:
            return None

    async def _cache_get(self, key: str) -> dict | None:
        r = await self._get_redis()
        if r is None:
            return None
        try:
            data = await r.get(key)
            return json.loads(data) if data else None
        except Exception:
            return None

    async def _cache_set(self, key: str, value: dict, ttl: int = CACHE_TTL) -> None:
        r = await self._get_redis()
        if r is None:
            return
        try:
            await r.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.debug("Embed cache write failed: %s", e)

    def _cache_key(
        self, text: str, model: str, provider: str, dimensions: int | None
    ) -> str:
        raw = f"{provider}:{model}:{dimensions}:{text}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{_CACHE_PREFIX}{digest}"

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = TextEmbedderInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        start = time.monotonic()

        try:
            embeddings, cached_count, token_count = await self._embed_all(validated)

            processing_time = int((time.monotonic() - start) * 1000)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "embeddings": embeddings,
                    "model": validated.model,
                    "provider": validated.provider,
                    "dimensions": len(embeddings[0]) if embeddings else 0,
                    "count": len(embeddings),
                    "total_tokens_used": token_count,
                    "cached_count": cached_count,
                    "processing_time_ms": processing_time,
                    "normalized": validated.normalize,
                    "success": True,
                },
            )
        except Exception as e:
            logger.exception("text_embedder failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _embed_all(
        self, validated: TextEmbedderInput
    ) -> tuple[list[list[float]], int, int]:
        embeddings: list[list[float]] = []
        cached_count = 0
        token_count = 0
        texts_to_embed: list[str] = []
        indices: list[int] = []

        # Check cache first
        for i, text in enumerate(validated.texts):
            key = self._cache_key(
                text, validated.model, validated.provider, validated.dimensions
            )
            cached = await self._cache_get(key)
            if cached and "embedding" in cached:
                embeddings.append(cached["embedding"])
                cached_count += 1
            else:
                texts_to_embed.append(text)
                indices.append(i)

        # Embed uncached texts
        if texts_to_embed:
            new_embeddings, tok_count = await self._embed_texts(
                validated, texts_to_embed
            )
            token_count += tok_count

            # Insert new embeddings at correct positions and cache them
            pos = 0
            result_embeddings: list[list[float]] = []
            ni = 0
            for i in range(len(validated.texts)):
                if i in indices:
                    emb = new_embeddings[ni]
                    result_embeddings.append(emb)
                    # Cache
                    key = self._cache_key(
                        validated.texts[i],
                        validated.model,
                        validated.provider,
                        validated.dimensions,
                    )
                    await self._cache_set(
                        key,
                        {
                            "embedding": emb,
                            "model": validated.model,
                            "provider": validated.provider,
                        },
                    )
                    ni += 1
                else:
                    result_embeddings.append(embeddings[i - ni])
            embeddings = result_embeddings
        else:
            # All cached, maintain original order
            pass

        return embeddings, cached_count, token_count

    async def _embed_texts(
        self, validated: TextEmbedderInput, texts: list[str]
    ) -> tuple[list[list[float]], int]:
        if validated.provider == "openai":
            return await self._embed_openai(validated, texts)
        elif validated.provider == "cohere":
            return await self._embed_cohere(validated, texts)
        elif validated.provider == "local":
            return await self._embed_local(validated, texts)
        raise ValueError(f"Unknown provider: {validated.provider}")

    # ── OpenAI ───────────────────────────────────────────────────

    async def _embed_openai(
        self, validated: TextEmbedderInput, texts: list[str]
    ) -> tuple[list[list[float]], int]:
        api_key = validated.api_key or OPENAI_API_KEY
        if not api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY or pass api_key."
            )

        body: dict[str, Any] = {
            "model": validated.model,
            "input": texts,
            "encoding_format": validated.encoding_format,
        }
        if validated.dimensions:
            body["dimensions"] = validated.dimensions

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(5):
            async with httpx.AsyncClient(timeout=validated.timeout_seconds) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/embeddings", json=body, headers=headers
                )
                if resp.status_code == 429:
                    wait = 2**attempt
                    logger.warning(
                        "OpenAI rate limited, retrying in %ds (attempt %d/5)",
                        wait,
                        attempt + 1,
                    )
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                embeddings = [item["embedding"] for item in data["data"]]
                token_count = data.get("usage", {}).get("total_tokens", 0)

                if validated.normalize:
                    embeddings = [self._l2_normalize(e) for e in embeddings]

                return embeddings, token_count

        raise RuntimeError("OpenAI embedding failed after 5 retries (rate limited)")

    # ── Cohere ───────────────────────────────────────────────────

    async def _embed_cohere(
        self, validated: TextEmbedderInput, texts: list[str]
    ) -> tuple[list[list[float]], int]:
        api_key = validated.api_key or COHERE_API_KEY
        if not api_key:
            raise ValueError(
                "Cohere API key required. Set COHERE_API_KEY or pass api_key."
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": validated.model,
            "texts": texts,
            "input_type": "search_document",
            "embedding_types": ["float"],
        }

        for attempt in range(5):
            async with httpx.AsyncClient(timeout=validated.timeout_seconds) as client:
                resp = await client.post(
                    "https://api.cohere.com/v2/embed", json=body, headers=headers
                )
                if resp.status_code == 429:
                    await asyncio.sleep(2**attempt)
                    continue
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings", {}).get("float", [])
                token_count = sum(len(t.split()) for t in texts)  # Approximate

                if validated.normalize:
                    embeddings = [self._l2_normalize(e) for e in embeddings]

                return embeddings, token_count

        raise RuntimeError("Cohere embedding failed after 5 retries")

    # ── Local (llama.cpp) ────────────────────────────────────────

    async def _embed_local(
        self, validated: TextEmbedderInput, texts: list[str]
    ) -> tuple[list[list[float]], int]:
        headers = {"Content-Type": "application/json"}
        embeddings: list[list[float]] = []
        token_count = 0

        async with httpx.AsyncClient(timeout=validated.timeout_seconds) as client:
            for text in texts:
                resp = await client.post(
                    LOCAL_EMBED_URL,
                    json={"model": validated.model, "prompt": text},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                emb = data.get("embedding", [])
                if validated.normalize and emb:
                    emb = self._l2_normalize(emb)
                embeddings.append(emb)

        return embeddings, token_count

    # ── Normalize ────────────────────────────────────────────────

    @staticmethod
    def _l2_normalize(vec: list[float]) -> list[float]:
        norm = sum(v * v for v in vec) ** 0.5
        if norm == 0:
            return [0.0] * len(vec)
        return [v / norm for v in vec]


register_tool(TextEmbedderTool())
