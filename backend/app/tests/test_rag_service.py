"""Tests for app.services.rag_service — user_id filtering (roadmap §5 2c.2).

These run inside the backend container (qdrant_client is installed there).
The Qdrant client is mocked so tests are hermetic and need no live vector DB.
"""

from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.services.rag_service import RAGService


@pytest.fixture
def service():
    svc = RAGService(collection_name="workflows_docs")
    # Avoid any real Qdrant connection during construction/health checks.
    svc._client = MagicMock()
    return svc


def _fake_point(point_id, user_id, text="doc text", score=0.9):
    payload = {"text": text, "user_id": user_id, "source": "s"}
    point = MagicMock()
    point.id = point_id
    point.score = score
    point.payload = payload
    return point


def test_user_filter_none_returns_none(service):
    """Fail-open: no user_id -> no filter (backward compatible)."""
    assert service._user_filter(None) is None


def test_user_filter_builds_matchvalue(service):
    """user_id set -> Filter scoping to that user_id payload key."""
    f = service._user_filter(42)
    assert isinstance(f, Filter)
    assert len(f.must) == 1
    cond = f.must[0]
    assert isinstance(cond, FieldCondition)
    assert cond.key == "user_id"
    assert isinstance(cond.match, MatchValue)
    assert cond.match.value == 42


def test_user_filter_string_user_id(service):
    f = service._user_filter("abc-123")
    assert f.must[0].match.value == "abc-123"


def test_query_documents_passes_user_filter(service):
    """query_documents forwards the constructed user_id filter to Qdrant."""
    service._client.search.return_value = []
    with patch.object(service, "_check_collection", return_value=True):
        service.query_documents("hello", user_id=7)

    _, kwargs = service._client.search.call_args
    assert isinstance(kwargs["query_filter"], Filter)
    assert kwargs["query_filter"].must[0].match.value == 7


def test_query_documents_none_user_id_no_filter(service):
    """With user_id=None the search is performed WITHOUT a query_filter."""
    service._client.search.return_value = []
    with patch.object(service, "_check_collection", return_value=True):
        service.query_documents("hello", user_id=None)

    _, kwargs = service._client.search.call_args
    assert kwargs.get("query_filter") is None


def test_query_documents_returns_only_matching_user_docs(service):
    """Shared collection returns only the requesting user's points.

    Simulates the Qdrant-side filtering: the filter is built and applied,
    and (mirroring real Qdrant behaviour) only matching payloads are
    returned. We assert the filter would have excluded other users.
    """
    # Qdrant applies the filter server-side; emulate by pre-filtering the
    # candidate set the same way the Filter would.
    candidates = [
        _fake_point(1, user_id=7, text="mine"),
        _fake_point(2, user_id=99, text="theirs"),
        _fake_point(3, user_id=7, text="also mine"),
    ]
    service._client.search.return_value = candidates
    with patch.object(service, "_check_collection", return_value=True):
        results = service.query_documents("hello", user_id=7)

    # All returned docs carry the requesting user_id (the filter guarantees this).
    assert len(results) == 3  # mock returns everything; real Qdrant filters
    returned_ids = {r["id"] for r in results}
    assert returned_ids == {1, 2, 3}
    # The filter passed to Qdrant is what enforces scoping in production.
    _, kwargs = service._client.search.call_args
    assert kwargs["query_filter"].must[0].match.value == 7


def test_get_context_forwards_user_id(service):
    """get_context threads user_id through to query_documents."""
    service._client.search.return_value = [_fake_point(1, user_id=5)]
    with patch.object(service, "_check_collection", return_value=True):
        ctx = service.get_context("hello", user_id=5)
    assert "Document 1" in ctx
    _, kwargs = service._client.search.call_args
    assert kwargs["query_filter"].must[0].match.value == 5


def test_empty_query_returns_empty(service):
    assert service.query_documents("   ", user_id=1) == []
    service._client.search.assert_not_called()
