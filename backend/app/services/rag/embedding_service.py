from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger(__name__)

_EMBEDDING_CACHE_TTL = 86400


class EmbeddingService:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self._openai_client: Any = None
        self._local_model: Any = None
        self._redis: Redis | None = None

    async def _get_redis(self) -> Redis | None:
        if self._redis is None:
            try:
                self._redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
                await self._redis.ping()
            except Exception as e:
                logger.warning("Redis unavailable for embedding cache: %s", e)
                self._redis = None
        return self._redis

    async def _cache_key(self, text: str) -> str:
        return f"embed:{hashlib.sha256(text.encode()).hexdigest()}"

    async def _get_cached(self, text: str) -> list[float] | None:
        redis = await self._get_redis()
        if redis is None:
            return None
        try:
            raw = await redis.get(await self._cache_key(text))
            if raw:
                return json.loads(raw)
        except Exception:
            logger.debug("embedding_cache_get_failed", exc_info=True)
        return None

    async def _set_cached(self, text: str, vector: list[float]) -> None:
        redis = await self._get_redis()
        if redis is None:
            return
        try:
            await redis.setex(await self._cache_key(text), _EMBEDDING_CACHE_TTL, json.dumps(vector))
        except Exception:
            logger.debug("embedding_cache_set_failed", exc_info=True)

    def _is_openai_model(self) -> bool:
        return self.model_name.startswith("text-embedding") or "openai" in self.model_name.lower()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, t in enumerate(texts):
            cached = await self._get_cached(t)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(t)

        if not uncached_texts:
            return results  # type: ignore

        try:
            if self._is_openai_model():
                vectors = await self._embed_openai(uncached_texts)
            else:
                vectors = await self._embed_local(uncached_texts)
        except Exception as e:
            logger.error(
                "Embedding failed with %s, falling back to local: %s",
                self.model_name,
                e,
            )
            vectors = await self._embed_local(uncached_texts)

        for idx, vec in zip(uncached_indices, vectors, strict=False):
            results[idx] = vec
            await self._set_cached(uncached_texts[uncached_indices.index(idx)], vec)

        return results  # type: ignore

    async def embed_query(self, query: str) -> list[float]:
        vectors = await self.embed([query])
        return vectors[0] if vectors else []

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        if self._openai_client is None:
            from openai import AsyncOpenAI

            api_key = settings.LLM_API_KEY or "sk-no-key-required"
            self._openai_client = AsyncOpenAI(
                api_key=api_key,
                base_url=settings.LLM_API_BASE,
            )

        response = await self._openai_client.embeddings.create(
            model=self.model_name,
            input=texts,
        )
        return [d.embedding for d in response.data]

    async def _embed_local(self, texts: list[str]) -> list[list[float]]:
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer

            self._local_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

        embeddings = self._local_model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()
