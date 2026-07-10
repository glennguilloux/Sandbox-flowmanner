"""Tests for app.services.rag_service — user_id filtering (roadmap §5 2c.2).

These run inside the backend container (qdrant_client is installed there).
The Qdrant client is mocked so tests are hermetic and need no live vector DB.

Coverage focuses on three multi-tenant behaviours:
  1. The user_id filter IS applied on a shared collection when user_id is set.
  2. user_id=None fails OPEN (no filter) AND logs a warning.
  3. A query against a shared collection returns ONLY the requesting user's docs.
"""

import logging
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


def _qdrant_filter_side_effect(candidates):
    """Emulate Qdrant's server-side payload filtering.

    The real Qdrant client applies ``query_filter`` to the indexed points
    and returns only matching payloads. This side_effect reproduces that
    behaviour so tests can assert the *effective* result set rather than
    just the filter that was passed.
    """

    def _search(**kwargs):
        query_filter = kwargs.get("query_filter")
        if query_filter is None:
            return list(candidates)
        allowed = {fc.match.value for fc in query_filter.must}
        return [p for p in candidates if p.payload.get("user_id") in allowed]

    return _search


# --------------------------------------------------------------------------- #
# Low-level _user_filter unit tests
# --------------------------------------------------------------------------- #


def test_user_filter_none_returns_none(service):
    """Fail-open: no user_id -> no filter (backward compatible)."""
    assert service._user_filter(None) is None


def test_user_filter_fails_open_with_warning(service, caplog):
    """Case 2: user_id=None fails OPEN and logs a warning.

    Skipping the per-user filter is a deliberate fail-open choice (roadmap
    §9). It must not happen silently — a warning must be emitted so the
    unscoped query is observable.
    """
    with caplog.at_level(logging.WARNING, logger="app.services.rag_service"):
        result = service._user_filter(None)

    assert result is None
    assert any(
        "fail-open" in record.message for record in caplog.records
    ), "expected a fail-open warning when user_id is None"


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


# --------------------------------------------------------------------------- #
# query_documents integration-style tests (mocked Qdrant)
# --------------------------------------------------------------------------- #


def test_query_documents_applies_user_filter_on_shared_collection(service):
    """Case 1: a shared collection gets a per-user filter when user_id set.

    A shared collection holds documents from many users. When a caller
    supplies user_id, the search MUST be scoped via a Qdrant Filter rather
    than returning the whole collection.
    """
    # Shared collection with docs from several users.
    shared = [
        _fake_point(1, user_id=7),
        _fake_point(2, user_id=99),
        _fake_point(3, user_id=7),
        _fake_point(4, user_id=13),
    ]
    service._client.search.side_effect = _qdrant_filter_side_effect(shared)

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


def test_query_documents_returns_only_requesting_users_docs(service):
    """Case 3: a query on a shared collection returns ONLY the requester's docs.

    The candidate set mixes multiple users' points. Because the Filter is
    applied server-side, the result must contain solely the requesting
    user's documents — never another tenant's.
    """
    candidates = [
        _fake_point(1, user_id=7, text="mine"),
        _fake_point(2, user_id=99, text="theirs"),
        _fake_point(3, user_id=7, text="also mine"),
        _fake_point(4, user_id=13, text="someone elses"),
    ]
    service._client.search.side_effect = _qdrant_filter_side_effect(candidates)

    with patch.object(service, "_check_collection", return_value=True):
        results = service.query_documents("hello", user_id=7)

    # Only the requesting user's two points survive the filter.
    assert len(results) == 2
    returned_ids = {r["id"] for r in results}
    assert returned_ids == {1, 3}
    # Every returned doc carries the requesting user_id in its metadata,
    # proving no other tenant's data leaked into the result set.
    assert all(r["metadata"]["user_id"] == 7 for r in results)


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
