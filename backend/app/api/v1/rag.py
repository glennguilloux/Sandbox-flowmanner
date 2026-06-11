from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.config import settings
from app.services.rag import (
    get_chunking_service,
    get_embedding_service,
    get_prompt_synthesizer,
    get_vector_store,
)
from app.services.rag_service import RAGService

if TYPE_CHECKING:
    from app.models.user import User

from app.services.rag.prompt_synthesizer import (
    GeneratedPrompt,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/rag", tags=["rag"])


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_book(
    book_title: str = Body(...),
    text: str = Body(...),
    user: User = Depends(get_current_user),
):
    chunking = get_chunking_service()
    embedding = get_embedding_service()
    vector_store = get_vector_store()

    chunks = await chunking.chunk_book(text=text, book_title=book_title)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No chunks could be extracted from the provided text",
        )

    texts = [c.text for c in chunks]
    vectors = await embedding.embed(texts)

    count = await vector_store.upsert_chunks(
        user_id=user.id,
        chunks=chunks,
        vectors=vectors,
    )

    logger.info("Ingested %d chunks for book '%s' (user %s)", count, book_title, user.id)
    return {
        "status": "accepted",
        "chunk_count": count,
        "book_title": book_title,
    }


@router.get("/books")
async def list_books(
    user: User = Depends(get_current_user),
):
    vector_store = get_vector_store()
    books = await vector_store.list_books(user_id=user.id)
    return {"books": books}


@router.get("/books/{book_title}/chunks")
async def list_chunks(
    book_title: str,
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    vector_store = get_vector_store()
    chunks, count = await vector_store.list_chunks(
        user_id=user.id,
        book_title=book_title,
        page=page,
        page_size=page_size,
    )
    return {
        "chunks": chunks,
        "page": page,
        "page_size": page_size,
        "total": count,
    }


@router.delete("/books/{book_title}")
async def delete_book(
    book_title: str,
    user: User = Depends(get_current_user),
):
    vector_store = get_vector_store()
    result = await vector_store.delete_book_chunks(
        user_id=user.id,
        book_title=book_title,
    )
    return {"status": "deleted", "book_title": book_title, "result": result}


@router.post("/prompt")
async def generate_prompt(
    goal: str = Body(...),
    role_description: str | None = Body(None),
    topics: list[str] | None = Body(None),
    books: list[str] | None = Body(None),
    user: User = Depends(get_current_user),
) -> GeneratedPrompt:
    vector_store = get_vector_store()
    book_list = await vector_store.list_books(user_id=user.id)
    if not book_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No book notes found. Ingest notes first via /ingest.",
        )

    synthesizer = get_prompt_synthesizer()
    result = await synthesizer.synthesize(
        user_id=user.id,
        goal=goal,
        role_description=role_description,
        topics=topics,
        books=books,
    )

    if not result.system_prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No book notes found. Ingest notes first via /ingest.",
        )

    return result


class ContextSearchRequest(BaseModel):
    query: str = Field(..., max_length=4096)
    top_k: int = Field(default=5, ge=1, le=20)


@router.post("/context/search")
async def search_context(
    payload: ContextSearchRequest,
    user: User = Depends(get_current_user),
):
    try:
        # Use per-user collection (matching VectorStore naming convention)
        collection_name = f"{settings.RAG_COLLECTION_PREFIX}{user.id}"
        rag = RAGService(collection_name=collection_name)

        context = rag.get_context(
            payload.query,
            n_results=payload.top_k,
        )

        if not context or not context.strip():
            return {"context": "", "results": [], "query": payload.query}

        results = rag.query_documents(
            payload.query,
            n_results=payload.top_k,
        )
    except Exception as e:
        logger.error("RAG context search failed for user %s: %s", user.id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search service temporarily unavailable. Please try again later.",
        )

    formatted_results = [
        {
            "text": r.get("text", "")[:300],
            "score": r.get("score", 0.0),
            "source": r.get("source", "unknown"),
        }
        for r in results
    ]

    return {
        "context": context,
        "results": formatted_results,
        "query": payload.query,
    }
