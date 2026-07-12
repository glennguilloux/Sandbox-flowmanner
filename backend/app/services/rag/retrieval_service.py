from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.llm_result import normalize_llm_result

if TYPE_CHECKING:
    from app.services.model_router import ModelRouter
    from app.services.rag.embedding_service import EmbeddingService
    from app.services.rag.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    id: str
    book_title: str
    text: str
    topics: list[str]
    relevance_score: float
    chunk_index: int
    score: float


class RetrievalService:
    def __init__(
        self,
        vector_store: QdrantVectorStore,
        embedding_service: EmbeddingService,
        llm_router: ModelRouter | None = None,
    ):
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.llm_router = llm_router

    async def retrieve(
        self,
        user_id: str | int,
        query: str,
        *,
        topics: list[str] | None = None,
        book_title: str | None = None,
        limit: int = 5,
    ) -> list[RetrievedChunk]:
        query_vector = await self.embedding_service.embed_query(query)
        candidates = await self.vector_store.search(
            user_id=user_id,
            query_vector=query_vector,
            topics=topics,
            book_title=book_title,
            limit=15,
        )

        if not candidates:
            return []

        if self.llm_router is not None and len(candidates) > 1:
            try:
                candidates = await self._rerank_llm(query, candidates)
            except Exception as e:
                logger.warning("LLM re-rank failed, using Qdrant ordering: %s", e)

        deduplicated = self._deduplicate(candidates)

        result = []
        for point in deduplicated[:limit]:
            p = point.payload or {}
            result.append(
                RetrievedChunk(
                    id=str(point.id),
                    book_title=p.get("book_title", ""),
                    text=p.get("text", ""),
                    topics=p.get("topics", []),
                    relevance_score=p.get("relevance_score", 0.0),
                    chunk_index=p.get("chunk_index", 0),
                    score=point.score,
                )
            )
        return result

    async def _rerank_llm(self, query: str, candidates: list) -> list:
        prompt = (
            f'Given the query: "{query}"\n'
            f"Rank these excerpts by relevance (1=best). Return ONLY a JSON array of indices in order of relevance.\n\n"
        )
        for i, c in enumerate(candidates):
            excerpt = (c.payload.get("text", "") or "")[:200]
            prompt += f"[{i}] {excerpt}...\n"

        response = await self.llm_router.route_request(
            messages=[{"role": "user", "content": prompt}],
            model_preference="deepseek/deepseek-v4-flash",
            max_tokens=200,
            temperature=0,
        )

        # Normalize across router return shapes (llm_router returns an object
        # when bound to a DB session); a success=False is surfaced and the
        # rerank is skipped via the existing except -> Qdrant ordering.
        try:
            content = normalize_llm_result(response, context="retrieval_service._rerank_llm")
        except Exception as e:
            logger.warning("LLM re-rank failed, using Qdrant ordering: %s", e)
            return candidates

        try:
            indices = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            logger.warning("LLM re-rank returned unparseable result, using original order")
            return candidates

        if isinstance(indices, list):
            reordered = []
            seen = set()
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(candidates) and idx not in seen:
                    reordered.append(candidates[idx])
                    seen.add(idx)
            remaining = [c for i, c in enumerate(candidates) if i not in seen]
            return reordered + remaining

        return candidates

    @staticmethod
    def _deduplicate(candidates: list) -> list:
        if len(candidates) < 2:
            return candidates
        result = [candidates[0]]
        for candidate in candidates[1:]:
            dup = False
            c_text = (candidate.payload or {}).get("text", "") or ""
            for existing in result:
                e_text = (existing.payload or {}).get("text", "") or ""
                if _cosine_similarity_approx(c_text, e_text) > 0.95:
                    dup = True
                    break
            if not dup:
                result.append(candidate)
        return result


def _cosine_similarity_approx(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a_tokens = set(a.lower().split())
    b_tokens = set(b.lower().split())
    if not a_tokens or not b_tokens:
        return 0.0
    intersection = a_tokens & b_tokens
    return len(intersection) / max(len(a_tokens), len(b_tokens))
