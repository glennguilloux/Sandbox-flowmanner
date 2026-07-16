#!/usr/bin/env python
"""Upsert historical churn-case documents into the fixed-name Qdrant collection
`churn_history`, so the harness candidate's `rag_query` node (collection
`churn_history`) returns real matches.

This is the out-of-band path: backend `QdrantVectorStore.ensure_collection`
only ever creates `{RAG_COLLECTION_PREFIX}{user_id}` collections, never a
fixed-name `churn_history`. Run this once (or re-run idempotently) to populate it.

Idempotent: points are upserted by stable ids derived from the source case id,
so a re-run does not duplicate.

Real embeddings only: vectors come from the backend `EmbeddingService`
(`app/services/rag/embedding_service.py`). No random/fake vectors are ever used.
If embeddings or Qdrant are unreachable, the script prints the error and exits
non-zero — it never claims success it did not achieve.

Usage:
    python ingest_churn_history.py --help
    python ingest_churn_history.py                 # 12 synthetic cases
    python ingest_churn_history.py --source cases.jsonl --limit 50
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings
from app.services.rag.embedding_service import EmbeddingService

COLLECTION = "churn_history"

logger = logging.getLogger("ingest_churn_history")


def _point_id(case_id: str) -> int:
    # Stable 64-bit unsigned id so re-runs overwrite the same point.
    return int(hashlib.sha256(case_id.encode()).hexdigest()[:16], 16)


def _synthetic_cases() -> list[dict]:
    """Small labeled fixture so the live smoke has something to retrieve.

    Synthetic docs are clearly marked in `book_title`/`topics` so they are never
    mistaken for production data.
    """
    high = [
        "Customer opened 4 support tickets in one week and threatened to cancel after the outage.",
        "Account login failed repeatedly; user posted a negative review and downgraded their plan.",
        "Billing error double-charged the customer who then emailed intent to churn immediately.",
        "Power user went silent for 60 days after a feature regression broke their core workflow.",
        "Customer complained about price hike and said a competitor offered a cheaper alternative.",
        "Renewal reminder ignored twice; support escalations show rising frustration and churn risk.",
    ]
    low = [
        "Customer asked a routine how-to question and resolved it within the same session.",
        "New user completed onboarding and sent a thank-you note to the success team.",
        "Account upgraded voluntarily after the quarterly product webinar.",
        "User reported a minor typo in docs and accepted the quick fix graciously.",
        "Customer requested an invoice copy and renewed without further contact.",
        "Long-time user gave positive feedback on a new integration they adopted.",
    ]
    cases: list[dict] = []
    for i, text in enumerate(high):
        cases.append(
            {
                "case_id": f"synthetic-high-{i:02d}",
                "book_title": "SYNTHETIC churn fixture (not production data)",
                "text": text,
                "topics": ["synthetic", "churn", "high-risk"],
                "relevance_score": 0.9,
            }
        )
    for i, text in enumerate(low):
        cases.append(
            {
                "case_id": f"synthetic-low-{i:02d}",
                "book_title": "SYNTHETIC churn fixture (not production data)",
                "text": text,
                "topics": ["synthetic", "churn", "low-risk"],
                "relevance_score": 0.3,
            }
        )
    return cases


def _load_source(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("cases", [])
    return [
        {
            "case_id": item["case_id"],
            "book_title": item.get("book_title", "churn_history"),
            "text": item["text"],
            "topics": item.get("topics", ["churn"]),
            "relevance_score": item.get("relevance_score", 0.5),
        }
        for item in items
    ]


async def _run(source: str | None, limit: int | None) -> int:
    if source:
        cases = _load_source(source)
    else:
        cases = _synthetic_cases()
    if limit is not None:
        cases = cases[:limit]

    client = AsyncQdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        grpc_port=settings.QDRANT_GRPC_PORT,
        prefer_grpc=True,
    )

    exists = await client.collection_exists(COLLECTION)
    before = (await client.count(COLLECTION)).count if exists else 0
    if not exists:
        await client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(
                size=settings.EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        )
        logger.info("Created collection %s", COLLECTION)

    embedder = EmbeddingService()
    vectors = await embedder.embed([c["text"] for c in cases])
    # Real vectors required; refuse to proceed with fabricated data.
    if any(len(v) != settings.EMBEDDING_DIMENSION for v in vectors):
        raise RuntimeError("embedder returned a vector with the wrong dimension")

    now = datetime.now(timezone.utc).isoformat()
    points = [
        PointStruct(
            id=_point_id(c["case_id"]),
            vector=v,
            payload={
                "book_title": c["book_title"],
                "text": c["text"],
                "topics": c["topics"],
                "relevance_score": c["relevance_score"],
                "chunk_index": 0,
                "total_chunks": 1,
                "created_at": now,
            },
        )
        for c, v in zip(cases, vectors)
    ]

    await client.upsert(collection_name=COLLECTION, points=points)
    after = (await client.count(COLLECTION)).count

    print(
        f"collection={COLLECTION} upserted={len(points)} "
        f"dim={settings.EMBEDDING_DIMENSION} before={before} after={after}"
    )
    await client.close()
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Idempotently upsert historical churn cases into Qdrant collection 'churn_history'."
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Path to a JSON/JSONL file of churn cases "
        "({case_id, text, book_title?, topics?, relevance_score?}). "
        "If omitted, a small synthetic fixture (12 cases) is used.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Upsert at most N cases (applied after loading the source).",
    )
    args = parser.parse_args()

    import asyncio

    try:
        return asyncio.run(_run(args.source, args.limit))
    except Exception as exc:  # noqa: BLE001 - surface and fail loudly, no silent success
        logger.error("Ingest failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
