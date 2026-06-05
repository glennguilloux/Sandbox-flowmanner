"""API-level tests for RAG endpoints — auth, validation, and response shapes."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.api.deps import get_current_user
from app.main_fastapi import app

from app.services.rag.prompt_synthesizer import GeneratedPrompt

BASE = "/api/v1/rag"

# Module-level TestClient (lifespan runs once at import)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    """Clear auth overrides between tests."""
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_rag_api_services():
    """Patch RAG service accessors inside app.api.v1.rag (where they're called)."""
    with (
        patch("app.api.v1.rag.get_chunking_service") as mock_cs,
        patch("app.api.v1.rag.get_embedding_service") as mock_es,
        patch("app.api.v1.rag.get_vector_store") as mock_vs,
        patch("app.api.v1.rag.get_prompt_synthesizer") as mock_ps,
    ):
        mock_chunking = MagicMock()
        mock_chunking.chunk_book = AsyncMock()

        mock_embedding = MagicMock()
        mock_embedding.embed = AsyncMock()

        mock_vector_store = MagicMock()
        mock_vector_store.upsert_chunks = AsyncMock()
        mock_vector_store.list_books = AsyncMock()
        mock_vector_store.list_chunks = AsyncMock()
        mock_vector_store.delete_book_chunks = AsyncMock()

        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize = AsyncMock()

        mock_cs.return_value = mock_chunking
        mock_es.return_value = mock_embedding
        mock_vs.return_value = mock_vector_store
        mock_ps.return_value = mock_synthesizer

        yield {
            "chunking": mock_chunking,
            "embedding": mock_embedding,
            "vector_store": mock_vector_store,
            "synthesizer": mock_synthesizer,
        }


class MockUser:
    def __init__(self, user_id=1):
        self.id = user_id
        self.email = "raguser@example.com"
        self.username = "raguser"
        self.is_active = True
        self.role = "user"


def _auth():
    app.dependency_overrides[get_current_user] = lambda: MockUser()


def _no_auth():
    app.dependency_overrides.pop(get_current_user, None)


class TestRAGApiAuth:
    """Endpoints return 401 when not authenticated."""

    def test_ingest_returns_401(self):
        _no_auth()
        resp = client.post(f"{BASE}/ingest", json={"book_title": "b", "text": "hello"})
        assert resp.status_code == 401

    def test_list_books_returns_401(self):
        _no_auth()
        resp = client.get(f"{BASE}/books")
        assert resp.status_code == 401

    def test_list_chunks_returns_401(self):
        _no_auth()
        resp = client.get(f"{BASE}/books/test/chunks")
        assert resp.status_code == 401

    def test_delete_book_returns_401(self):
        _no_auth()
        resp = client.delete(f"{BASE}/books/test")
        assert resp.status_code == 401

    def test_generate_prompt_returns_401(self):
        _no_auth()
        resp = client.post(f"{BASE}/prompt", json={"goal": "test"})
        assert resp.status_code == 401


class TestRAGApiIngest:
    """POST /v1/rag/ingest"""

    def test_ingest_returns_202(self, mock_rag_api_services):
        """Successful ingest returns 202 with chunk_count."""
        mocks = mock_rag_api_services
        mocks["chunking"].chunk_book.return_value = [
            MagicMock(text="chunk1", id="1"),
            MagicMock(text="chunk2", id="2"),
        ]
        mocks["embedding"].embed.return_value = [[0.1], [0.2]]
        mocks["vector_store"].upsert_chunks.return_value = 2
        _auth()

        resp = client.post(f"{BASE}/ingest", json={"book_title": "my book", "text": "some long text"})
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["chunk_count"] == 2
        assert data["book_title"] == "my book"

    def test_ingest_with_empty_text_returns_400(self, mock_rag_api_services):
        """When chunking produces no chunks, returns 400."""
        mocks = mock_rag_api_services
        mocks["chunking"].chunk_book.return_value = []
        _auth()

        resp = client.post(f"{BASE}/ingest", json={"book_title": "test", "text": ""})
        assert resp.status_code == 400
        assert "No chunks" in resp.text


class TestRAGApiBooks:
    """GET /v1/rag/books"""

    def test_list_books_returns_200(self, mock_rag_api_services):
        """List books endpoint returns book list."""
        mocks = mock_rag_api_services
        mocks["vector_store"].list_books.return_value = [
            {"title": "Book A", "chunk_count": 10},
            {"title": "Book B", "chunk_count": 5},
        ]
        _auth()

        resp = client.get(f"{BASE}/books")
        assert resp.status_code == 200
        data = resp.json()
        assert "books" in data
        assert len(data["books"]) == 2

    def test_list_books_empty(self, mock_rag_api_services):
        """Empty library returns empty list."""
        mocks = mock_rag_api_services
        mocks["vector_store"].list_books.return_value = []
        _auth()

        resp = client.get(f"{BASE}/books")
        assert resp.status_code == 200
        assert resp.json()["books"] == []


class TestRAGApiChunks:
    """GET /v1/rag/books/{book_title}/chunks"""

    def test_list_chunks_returns_paginated(self, mock_rag_api_services):
        """Chunks endpoint returns paginated chunk list with total."""
        mocks = mock_rag_api_services
        mocks["vector_store"].list_chunks.return_value = (
            [{"id": "1", "text": "hello", "topics": ["role_definition"], "relevance_score": 0.8, "chunk_index": 0}],
            1,
        )
        _auth()

        resp = client.get(f"{BASE}/books/test-book/chunks?page=1&page_size=20")
        assert resp.status_code == 200
        data = resp.json()
        assert "chunks" in data
        assert "total" in data
        assert data["total"] == 1
        assert data["page"] == 1

    def test_list_chunks_default_pagination(self, mock_rag_api_services):
        """Chunks endpoint works without explicit page params."""
        mocks = mock_rag_api_services
        mocks["vector_store"].list_chunks.return_value = ([], 0)
        _auth()

        resp = client.get(f"{BASE}/books/test-book/chunks")
        assert resp.status_code == 200


class TestRAGApiDelete:
    """DELETE /v1/rag/books/{book_title}"""

    def test_delete_book_returns_200(self, mock_rag_api_services):
        """Delete book returns success status."""
        mocks = mock_rag_api_services
        mocks["vector_store"].delete_book_chunks.return_value = {"status": "ok"}
        _auth()

        resp = client.delete(f"{BASE}/books/my-book")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert data["book_title"] == "my-book"


class TestRAGApiPrompt:
    """POST /v1/rag/prompt"""

    def test_prompt_returns_generated_prompt(self, mock_rag_api_services):
        """Successful prompt generation returns a GeneratedPrompt."""
        mocks = mock_rag_api_services
        mocks["vector_store"].list_books.return_value = [
            {"title": "Prompt Book", "chunk_count": 10},
        ]
        mocks["synthesizer"].synthesize.return_value = GeneratedPrompt(
            system_prompt="You are a helpful assistant.",
            rationale={"role_definition": ["from Prompt Book"]},
            recommended_model="deepseek/deepseek-v4-flash",
            temperature=0.7,
        )
        _auth()

        resp = client.post(
            f"{BASE}/prompt",
            json={
                "goal": "build a chatbot",
                "role_description": "customer support",
                "topics": ["role_definition"],
                "books": ["Prompt Book"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["system_prompt"] == "You are a helpful assistant."
        assert "rationale" in data
        assert data["recommended_model"] == "deepseek/deepseek-v4-flash"

    def test_prompt_without_optional_fields(self, mock_rag_api_services):
        """role_description, topics, and books are optional."""
        mocks = mock_rag_api_services
        mocks["vector_store"].list_books.return_value = [
            {"title": "Book", "chunk_count": 1},
        ]
        mocks["synthesizer"].synthesize.return_value = GeneratedPrompt(
            system_prompt="Be concise.", rationale={}
        )
        _auth()

        resp = client.post(f"{BASE}/prompt", json={"goal": "be concise"})
        assert resp.status_code == 200
        assert resp.json()["system_prompt"] == "Be concise."

    def test_prompt_no_books_returns_400(self, mock_rag_api_services):
        """When no books are found in the library, returns 400."""
        mocks = mock_rag_api_services
        mocks["vector_store"].list_books.return_value = []
        _auth()

        resp = client.post(f"{BASE}/prompt", json={"goal": "test"})
        assert resp.status_code == 400
        assert "No book notes found" in resp.text

    def test_prompt_empty_system_prompt_returns_400(self, mock_rag_api_services):
        """When synthesizer returns empty system_prompt, returns 400."""
        mocks = mock_rag_api_services
        mocks["vector_store"].list_books.return_value = [
            {"title": "Book", "chunk_count": 1},
        ]
        mocks["synthesizer"].synthesize.return_value = GeneratedPrompt(
            system_prompt="",
            rationale={"error": ["No relevant book notes found."]},
        )
        _auth()

        resp = client.post(f"{BASE}/prompt", json={"goal": "test"})
        assert resp.status_code == 400
        assert "No book notes found" in resp.text
