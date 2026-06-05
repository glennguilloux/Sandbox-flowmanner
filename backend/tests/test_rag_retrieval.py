"""Tests for RetrievalService — mock Qdrant, EmbeddingService, ModelRouter."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.rag.retrieval_service import RetrievalService, _cosine_similarity_approx


@pytest.fixture
def mock_vector_store():
    vs = MagicMock()
    vs.search = AsyncMock()
    return vs


@pytest.fixture
def mock_embedding_service():
    es = MagicMock()
    es.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    return es


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route_request = AsyncMock()
    return router


def _make_point(
    point_id: int,
    text: str,
    score: float = 0.9,
    book_title: str = "test book",
    topics: list[str] | None = None,
    relevance_score: float = 0.8,
    chunk_index: int = 0,
):
    """Create a mock ScoredPoint-like object Qdrant returns."""
    point = MagicMock()
    point.id = point_id
    point.score = score
    point.payload = {
        "book_title": book_title,
        "text": text,
        "topics": topics or [],
        "relevance_score": relevance_score,
        "chunk_index": chunk_index,
    }
    return point


class TestRetrievalService:
    """Unit tests for RetrievalService.retrieve()."""

    @pytest.fixture
    def service(self, mock_vector_store, mock_embedding_service, mock_llm_router):
        return RetrievalService(
            vector_store=mock_vector_store,
            embedding_service=mock_embedding_service,
            llm_router=mock_llm_router,
        )

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty_list(self, service, mock_vector_store):
        """When vector_store.search returns [], retrieve() returns []."""
        mock_vector_store.search.return_value = []
        result = await service.retrieve(user_id=1, query="test query")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_llm_router_skips_rerank(self):
        """When llm_router is None, retrieval skips re-rank."""
        vs = MagicMock()
        vs.search = AsyncMock(
            return_value=[_make_point(1, "first chunk", 0.9), _make_point(2, "second chunk", 0.8)]
        )
        es = MagicMock()
        es.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

        svc = RetrievalService(vector_store=vs, embedding_service=es, llm_router=None)
        result = await svc.retrieve(user_id=1, query="test", limit=5)

        assert len(result) == 2
        assert result[0].id == "1"
        assert result[1].id == "2"

    @pytest.mark.asyncio
    async def test_deduplication_removes_duplicates(self, service, mock_vector_store):
        """Two nearly identical chunks are deduplicated, only one returned."""
        dup_text = "This is a test chunk with lots of words that repeat for deduplication purposes"
        mock_vector_store.search.return_value = [
            _make_point(1, dup_text, 0.95),
            _make_point(2, dup_text, 0.94),
            _make_point(3, "completely different content here", 0.85),
        ]
        result = await service.retrieve(user_id=1, query="test", limit=5)
        assert len(result) == 2
        ids = {r.id for r in result}
        assert "1" in ids
        assert "3" in ids

    @pytest.mark.asyncio
    async def test_deduplication_preserves_different_chunks(self, service, mock_vector_store):
        """Different chunks are all kept."""
        mock_vector_store.search.return_value = [
            _make_point(1, "alpha content here", 0.9),
            _make_point(2, "beta content here", 0.85),
            _make_point(3, "gamma content here", 0.8),
        ]
        result = await service.retrieve(user_id=1, query="test", limit=5)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_limit_respects_max(self, service, mock_vector_store):
        """Result is capped at the limit parameter."""
        mock_vector_store.search.return_value = [
            _make_point(i, f"chunk {i}", 0.9 - i * 0.01) for i in range(10)
        ]
        result = await service.retrieve(user_id=1, query="test", limit=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_topic_filter_passed_to_vector_store(self, service, mock_vector_store):
        """topics arg is forwarded to vector_store.search."""
        mock_vector_store.search.return_value = []
        await service.retrieve(user_id=1, query="test", topics=["role_definition", "constraints"])
        mock_vector_store.search.assert_called_once()
        _kwargs = mock_vector_store.search.call_args.kwargs
        assert _kwargs["topics"] == ["role_definition", "constraints"]

    @pytest.mark.asyncio
    async def test_book_title_filter_passed_to_vector_store(self, service, mock_vector_store):
        """book_title arg is forwarded to vector_store.search."""
        mock_vector_store.search.return_value = []
        await service.retrieve(user_id=1, query="test", book_title="my book")
        _kwargs = mock_vector_store.search.call_args.kwargs
        assert _kwargs["book_title"] == "my book"

    @pytest.mark.asyncio
    async def test_llm_rerank_called_when_available(self, service, mock_llm_router, mock_vector_store):
        """When llm_router is set, re-rank is called for multiple candidates."""
        mock_vector_store.search.return_value = [
            _make_point(1, "first chunk about testing", 0.9),
            _make_point(2, "second chunk about testing", 0.85),
        ]
        mock_llm_router.route_request.return_value = {"response": "[0, 1]"}
        result = await service.retrieve(user_id=1, query="test", limit=5)
        assert len(result) == 2
        mock_llm_router.route_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_rerank_fallback_on_error(self, service, mock_llm_router, mock_vector_store):
        """When LLM re-rank errors, results fall back to Qdrant ordering."""
        mock_vector_store.search.return_value = [
            _make_point(1, "first chunk", 0.9),
            _make_point(2, "second chunk", 0.85),
        ]
        mock_llm_router.route_request.side_effect = RuntimeError("LLM unavailable")
        result = await service.retrieve(user_id=1, query="test", limit=5)
        assert len(result) == 2
        assert result[0].id == "1"

    @pytest.mark.asyncio
    async def test_llm_rerack_unparseable_json_falls_back(self, service, mock_llm_router, mock_vector_store):
        """When LLM returns unparseable JSON, falls back to Qdrant ordering."""
        mock_vector_store.search.return_value = [
            _make_point(1, "first chunk", 0.9),
            _make_point(2, "second chunk", 0.85),
        ]
        mock_llm_router.route_request.return_value = {"response": "not json at all"}
        result = await service.retrieve(user_id=1, query="test", limit=5)
        assert len(result) == 2
        assert result[0].id == "1"

    @pytest.mark.asyncio
    async def test_retrieve_embeds_query(self, service, mock_embedding_service, mock_vector_store):
        """embed_query is called with the query string."""
        mock_vector_store.search.return_value = []
        await service.retrieve(user_id=1, query="how to prompt")
        mock_embedding_service.embed_query.assert_called_once_with("how to prompt")

    @pytest.mark.asyncio
    async def test_chunk_with_null_payload_handled(self, service, mock_vector_store):
        """A ScoredPoint with None payload doesn't crash."""
        point = MagicMock()
        point.id = 99
        point.score = 0.5
        point.payload = None
        mock_vector_store.search.return_value = [point]
        result = await service.retrieve(user_id=1, query="test", limit=5)
        assert len(result) == 1
        assert result[0].book_title == ""


class TestDeduplicate:
    """Direct tests for RetrievalService._deduplicate()."""

    def test_empty_list(self):
        result = RetrievalService._deduplicate([])
        assert result == []

    def test_single_item(self):
        pts = [_make_point(1, "text")]
        result = RetrievalService._deduplicate(pts)
        assert len(result) == 1

    def test_all_duplicates(self):
        pts = [_make_point(1, "duplicate text here"), _make_point(2, "duplicate text here")]
        result = RetrievalService._deduplicate(pts)
        assert len(result) == 1

    def test_no_duplicates(self):
        pts = [_make_point(1, "alpha beta gamma"), _make_point(2, "delta epsilon zeta")]
        result = RetrievalService._deduplicate(pts)
        assert len(result) == 2


class TestCosineSimilarityApprox:
    """Direct tests for _cosine_similarity_approx()."""

    def test_identical_texts(self):
        score = _cosine_similarity_approx("hello world", "hello world")
        assert score == 1.0

    def test_partial_overlap(self):
        score = _cosine_similarity_approx("hello world", "hello there")
        assert 0.0 < score < 1.0

    def test_no_overlap(self):
        score = _cosine_similarity_approx("hello world", "foo bar")
        assert score == 0.0

    def test_empty_strings(self):
        assert _cosine_similarity_approx("", "hello") == 0.0
        assert _cosine_similarity_approx("hello", "") == 0.0
        assert _cosine_similarity_approx("", "") == 0.0

    def test_case_insensitive(self):
        score = _cosine_similarity_approx("Hello World", "hello world")
        assert score == 1.0
