"""
RAG Service - intelligent document retrieval using Qdrant vector database.

Provides context-aware document retrieval for missions, agents, and tools
via semantic search over indexed documents.
"""

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import settings

logger = logging.getLogger(__name__)


class RAGService:
    """Retrieve relevant document context from Qdrant vector store."""

    def __init__(self, qdrant_url: str | None = None, collection_name: str | None = None):
        self._qdrant_url = qdrant_url or settings.QDRANT_URL
        self._collection_name = collection_name or settings.QDRANT_COLLECTION_NAME
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            try:
                self._client = QdrantClient(url=self._qdrant_url)
                logger.info("Connected to Qdrant at %s", self._qdrant_url)
            except Exception as e:
                logger.warning("Failed to connect to Qdrant at %s: %s", self._qdrant_url, e)
                raise
        return self._client

    def _check_collection(self) -> bool:
        try:
            collections = self.client.get_collections().collections
            return any(c.name == self._collection_name for c in collections)
        except Exception as e:
            logger.warning("Could not verify collection '%s': %s", self._collection_name, e)
            return False

    def query_documents(
        self,
        query: str,
        n_results: int = 5,
        score_threshold: float | None = None,
        user_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        if not query or not query.strip():
            return []

        threshold = score_threshold if score_threshold is not None else settings.RAG_SIMILARITY_THRESHOLD

        # Fail-open per roadmap §9 mitigation: when no user_id is available
        # (e.g. during the multi-tenant migration window), skip the per-user
        # filter entirely rather than hard-failing. This keeps the shared
        # collection queryable by legacy call sites that have not yet been
        # taught to pass a user_id.
        query_filter = self._user_filter(user_id)

        try:
            if not self._check_collection():
                logger.warning(
                    "Collection '%s' does not exist at %s",
                    self._collection_name,
                    self._qdrant_url,
                )
                return []

            search_result = self.client.search(
                collection_name=self._collection_name,
                query_text=query,
                limit=n_results,
                score_threshold=threshold,
                query_filter=query_filter,
            )

            results = []
            for point in search_result:
                payload = point.payload or {}
                results.append(
                    {
                        "id": point.id,
                        "text": payload.get("text", payload.get("content", "")),
                        "score": point.score,
                        "source": payload.get("source", payload.get("url", "")),
                        "metadata": {k: v for k, v in payload.items() if k not in ("text", "content", "source", "url")},
                    }
                )

            logger.debug("RAG query '%s...' returned %s results", query[:50], len(results))
            return results

        except Exception as e:
            logger.error("RAG query failed: %s", e)
            return []

    def get_context(self, query: str, n_results: int = 5, user_id: str | int | None = None) -> str:
        docs = self.query_documents(query, n_results=n_results, user_id=user_id)
        if not docs:
            return ""
        sections = []
        for i, doc in enumerate(docs, 1):
            text = doc.get("text", "").strip()
            if text:
                source = doc.get("source", "")
                source_tag = f" (Source: {source})" if source else ""
                sections.append(f"[Document {i}]{source_tag}\n{text}")
        return "\n\n---\n\n".join(sections)

    def _user_filter(self, user_id: str | int | None) -> Filter | None:
        """Build a Qdrant payload filter scoping results to ``user_id``.

        Returns ``None`` when ``user_id`` is ``None`` — the call site then
        queries the shared collection without a per-user restriction
        (fail-open behaviour, see roadmap §9). The filter matches the
        ``user_id`` payload key on indexed points.
        """
        if user_id is None:
            logger.warning(
                "RAG user_id filter skipped: no user_id provided (fail-open). Results are NOT scoped to a single user."
            )
            return None
        return Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))])

    def health(self) -> dict[str, Any]:
        try:
            info = self.client.get_collections()
            collections = [c.name for c in info.collections]
            return {
                "connected": True,
                "url": self._qdrant_url,
                "collection": self._collection_name,
                "collection_exists": self._collection_name in collections,
                "available_collections": collections,
            }
        except Exception as e:
            return {
                "connected": False,
                "url": self._qdrant_url,
                "error": str(e),
            }
