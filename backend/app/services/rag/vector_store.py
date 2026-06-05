from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import settings

if TYPE_CHECKING:
    from app.services.rag.chunking_service import Chunk

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    def __init__(self):
        self._client: AsyncQdrantClient | None = None

    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                grpc_port=settings.QDRANT_GRPC_PORT,
                prefer_grpc=True,
            )
        return self._client

    async def ensure_collection(self, user_id: str | int) -> str:
        collection_name = f"{settings.RAG_COLLECTION_PREFIX}{user_id}"
        exists = await self.client.collection_exists(collection_name)
        if not exists:
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=settings.EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection: %s", collection_name)
        return collection_name

    async def upsert_chunks(
        self,
        user_id: str | int,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> int:
        collection = await self.ensure_collection(user_id)
        points = [
            PointStruct(
                id=chunk.id,
                vector=vector,
                payload={
                    "book_title": chunk.book_title,
                    "text": chunk.text,
                    "topics": chunk.topics,
                    "relevance_score": chunk.relevance_score,
                    "chunk_index": chunk.chunk_index,
                    "total_chunks": chunk.total_chunks,
                    "created_at": chunk.created_at,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=False)
        ]
        result = await self.client.upsert(
            collection_name=collection,
            points=points,
        )
        return len(points)

    async def search(
        self,
        user_id: str | int,
        query_vector: list[float],
        *,
        topics: list[str] | None = None,
        book_title: str | None = None,
        limit: int = 15,
    ):
        collection = f"{settings.RAG_COLLECTION_PREFIX}{user_id}"
        must_conditions: list[FieldCondition] = []

        if topics:
            must_conditions.append(
                FieldCondition(key="topics", params=MatchAny(any=topics))
            )
        if book_title:
            must_conditions.append(
                FieldCondition(key="book_title", params=MatchValue(value=book_title))
            )

        return await self.client.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=Filter(must=must_conditions) if must_conditions else None,
            limit=limit,
        )

    async def delete_book_chunks(self, user_id: str | int, book_title: str) -> int:
        collection = f"{settings.RAG_COLLECTION_PREFIX}{user_id}"
        result = await self.client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="book_title",
                        params=MatchValue(value=book_title),
                    )
                ]
            ),
        )
        return result.status

    async def list_books(self, user_id: str | int) -> list[dict]:
        collection = f"{settings.RAG_COLLECTION_PREFIX}{user_id}"
        exists = await self.client.collection_exists(collection)
        if not exists:
            return []

        books: dict[str, int] = {}
        next_offset: int | None = None
        while True:
            records, next_offset = await self.client.scroll(
                collection_name=collection,
                limit=1000,
                offset=next_offset,
                with_payload=["book_title"],
                with_vectors=False,
            )
            for rec in records:
                title = rec.payload.get("book_title", "unknown")
                books[title] = books.get(title, 0) + 1
            if next_offset is None:
                break

        return [{"title": k, "chunk_count": v} for k, v in books.items()]

    async def list_chunks(
        self,
        user_id: str | int,
        book_title: str,
        page: int = 1,
        page_size: int = 20,
    ):
        collection = f"{settings.RAG_COLLECTION_PREFIX}{user_id}"
        exists = await self.client.collection_exists(collection)
        if not exists:
            return [], 0

        book_filter = Filter(
            must=[
                FieldCondition(
                    key="book_title",
                    params=MatchValue(value=book_title),
                )
            ]
        )

        # First scroll all records matching this book to get the total count
        all_records = []
        next_offset: int | None = None
        while True:
            records, next_offset = await self.client.scroll(
                collection_name=collection,
                limit=1000,
                offset=next_offset,
                with_payload=True,
                with_vectors=False,
                scroll_filter=book_filter,
            )
            all_records.extend(records)
            if next_offset is None:
                break

        total = len(all_records)

        # Apply page-based slicing
        start = (page - 1) * page_size
        end = start + page_size
        page_records = all_records[start:end]

        chunks = []
        for rec in page_records:
            p = rec.payload
            chunks.append(
                {
                    "id": rec.id,
                    "text": p.get("text", ""),
                    "topics": p.get("topics", []),
                    "relevance_score": p.get("relevance_score", 0),
                    "chunk_index": p.get("chunk_index", 0),
                }
            )

        return chunks, total
