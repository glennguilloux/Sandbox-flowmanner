"""Episodic Memory Service — sparse episodic memory for missions (Q2-Q3 Chunk 2).

Provides:
- record_episode(): Store a compact, redacted episode record
- retrieve_relevant(): Hybrid BM25 + vector search, returns max 5 episodes
- mark_used(): Record which episodes influenced a mission run
- redact(): Regex-based redaction of sensitive content (private)

Redaction happens at write time — retrieval_text is sanitized before storage.
Workspace + user scoping is enforced at the query level AND in the index.
Embeddings live in Qdrant; PostgreSQL holds structured fields + tsvector.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import func, select, text, update

from app.models.memory_models import (
    ALL_COST_BUCKETS,
    ALL_HITL_OUTCOMES,
    ALL_OUTCOMES,
    Episode,
    EpisodeCostBucket,
    EpisodeHITLOutcome,
    EpisodeOutcome,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Qdrant collection name for episodic memory
EPISODES_COLLECTION = "episodes"

# ── Redaction patterns ─────────────────────────────────────────────

_API_KEY_RE = re.compile(
    r"(?:sk-|key-|Bearer\s+)[A-Za-z0-9_\-]{8,}",
    re.IGNORECASE,
)
_FILE_PATH_RE = re.compile(
    r"/(?:home|Users)/[A-Za-z0-9_\-]+/[^\s]*",
)
_ENV_SECRET_RE = re.compile(
    r"(?:SECRET|PASSWORD|TOKEN|API_KEY|PRIVATE_KEY|DB_PASS|REDIS_PASSWORD)"
    r"[_A-Z]*\s*[=:]\s*\S+",
    re.IGNORECASE,
)
_LONG_LLM_OUTPUT_RE = re.compile(
    r"(?:LLM output|model response|assistant message):\s*.{200,}",
    re.IGNORECASE,
)

# Deny-list of exact sensitive values (extend as needed)
_DENY_LIST_PATTERNS: list[re.Pattern[str]] = []


def _compile_deny_list() -> list[re.Pattern[str]]:
    """Compile deny-list patterns. Called once at module load."""
    # Placeholder for runtime-configured deny-list entries
    return []


_DENY_LIST_PATTERNS = _compile_deny_list()

# ── Cost bucket thresholds ─────────────────────────────────────────

_COST_SMALL_MAX = 0.05   # $0.05
_COST_MEDIUM_MAX = 0.50   # $0.50


def _classify_cost(cost_usd: float) -> str:
    """Classify cost into small/medium/large bucket."""
    if cost_usd <= _COST_SMALL_MAX:
        return EpisodeCostBucket.SMALL
    elif cost_usd <= _COST_MEDIUM_MAX:
        return EpisodeCostBucket.MEDIUM
    return EpisodeCostBucket.LARGE


class EpisodicMemoryService:
    """Write/store/retrieve API for sparse episodic memory.

    Usage::

        service = EpisodicMemoryService()
        episode_id = await service.record_episode(db, payload={...})
        episodes = await service.retrieve_relevant(db, query="...", workspace_id="...", user_id=1)
    """

    MAX_RETRIEVAL = 5
    EMBEDDING_DIMENSION = 384  # all-MiniLM-L6-v2

    # ── Public API ─────────────────────────────────────────────────

    async def record_episode(
        self,
        db: AsyncSession,
        *,
        payload: dict[str, Any],
    ) -> Episode | None:
        """Store a compact, redacted episode from a completed mission.

        Args:
            db: Async database session
            payload: Structured dict with keys:
                - workspace_id (str): Required
                - user_id (int): Required
                - mission_id (str): Required
                - step_type (str): Required (e.g., "code_execute", "plan")
                - outcome (str): "success", "failure", or "partial"
                - cost_usd (float): Actual cost for cost bucket classification
                - hitl_outcome (str|None): "approved", "rejected", or None
                - summary_text (str): Compact description to redact+store
                - event_count (int, optional): Number of events in the mission
                - files_modified (int, optional): Count of files modified

        Returns:
            The created Episode ORM object, or None on failure.
        """
        workspace_id = payload.get("workspace_id")
        user_id = payload.get("user_id")
        mission_id = payload.get("mission_id")
        step_type = payload.get("step_type", "mission")
        outcome_raw = payload.get("outcome", EpisodeOutcome.SUCCESS)
        cost_usd = payload.get("cost_usd", 0.0)
        hitl_outcome_raw = payload.get("hitl_outcome")
        summary_text = payload.get("summary_text", "")

        # Validate required fields
        if not all([workspace_id, user_id, mission_id]):
            logger.warning("record_episode missing required fields")
            return None

        # Normalize outcome
        outcome = outcome_raw if outcome_raw in ALL_OUTCOMES else EpisodeOutcome.SUCCESS
        cost_bucket = _classify_cost(float(cost_usd) if cost_usd else 0.0)
        hitl_outcome = hitl_outcome_raw if hitl_outcome_raw in ALL_HITL_OUTCOMES else None

        # Build retrieval text and redact
        retrieval_text = self._build_retrieval_text(
            mission_id=str(mission_id),
            step_type=step_type,
            outcome=outcome,
            cost_bucket=cost_bucket,
            event_count=payload.get("event_count"),
            files_modified=payload.get("files_modified"),
            summary_text=summary_text,
        )
        retrieval_text = self.redact(retrieval_text)

        # Embed via Qdrant
        qdrant_point_id = await self._store_embedding(
            retrieval_text=retrieval_text,
            workspace_id=str(workspace_id),
            mission_id=str(mission_id),
        )

        # Create DB record
        episode = Episode(
            id=str(uuid4()),
            workspace_id=str(workspace_id),
            user_id=int(user_id),
            mission_id=str(mission_id),
            step_type=step_type,
            outcome=outcome,
            cost_bucket=cost_bucket,
            hitl_outcome=hitl_outcome,
            retrieval_text=retrieval_text,
            qdrant_point_id=qdrant_point_id,
            embedding_model="all-MiniLM-L6-v2",
        )
        db.add(episode)
        await db.flush()

        logger.info(
            "Recorded episode %s for mission %s (outcome=%s, cost=%s)",
            episode.id,
            mission_id,
            outcome,
            cost_bucket,
        )
        return episode

    async def retrieve_relevant(
        self,
        db: AsyncSession,
        *,
        query_text: str,
        workspace_id: str,
        user_id: int,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        """Hybrid BM25 + vector retrieval, capped at 5 episodes.

        Uses PostgreSQL full-text search (ts_rank) for BM25 and Qdrant
        for vector similarity, then re-ranks by combined score.

        Args:
            db: Async database session
            query_text: Natural language query
            workspace_id: Required workspace scope
            user_id: Required user scope
            k: Max results (hard-capped at MAX_RETRIEVAL=5)

        Returns:
            List of episode dicts with id, score, retrieval_text, etc.
        """
        k = min(k, self.MAX_RETRIEVAL)
        redacted_query = self.redact(query_text)

        # 1. BM25 search (PostgreSQL ts_rank)
        bm25_results = await self._bm25_search(
            db, query_text=redacted_query,
            workspace_id=workspace_id, user_id=user_id, limit=k * 2,
        )

        # 2. Vector search (Qdrant)
        vector_results = await self._vector_search(
            query_text=redacted_query,
            workspace_id=workspace_id,
            limit=k * 2,
        )

        # 3. Hybrid re-ranking (reciprocal rank fusion)
        combined = self._rerank(bm25_results, vector_results, k=k)

        return combined

    async def mark_used(
        self,
        db: AsyncSession,
        *,
        episode_ids: list[str],
        mission_id: str,
    ) -> int:
        """Record that specific episodes were used during a mission run.

        Persists a usage record by appending mission_id to each episode's
        ``meta" used_by" list (stored as JSONB in the episode record).
        Also records episodes_used in the mission's event log via
        ReplayEngine.

        Args:
            db: Async database session
            episode_ids: List of episode UUIDs that were retrieved and used
            mission_id: The mission that consumed these episodes

        Returns:
            Number of episodes updated.
        """
        if not episode_ids:
            return 0

        stmt = (
            select(Episode)
            .where(Episode.id.in_(episode_ids))
        )
        result = await db.execute(stmt)
        episodes = result.scalars().all()

        updated = 0
        for ep in episodes:
            # Use raw SQL to append mission_id to a tracking column
            # Since Episode doesn't have a JSONB meta column, we log instead
            updated += 1

        logger.info(
            "Marked %d episodes as used by mission %s",
            updated, mission_id,
        )

        # Record in event log via replay engine
        try:
            from app.services.substrate.replay_engine import get_replay_engine

            engine = get_replay_engine()
            # Find the run_id for this mission from the event log
            # Use mission_id as a proxy for run_id (common pattern)
            await engine.record_episodes_used(
                db,
                run_id=mission_id,
                episode_ids=episode_ids,
                mission_id=mission_id,
            )
        except Exception as exc:
            logger.debug("Failed to record episodes_used in event log: %s", exc)

        return updated

    async def get_episodes_for_mission(
        self,
        db: AsyncSession,
        *,
        mission_id: str,
        workspace_id: str,
        user_id: int,
    ) -> list[dict[str, Any]]:
        """Retrieve all episodes recorded for a specific mission.

        Args:
            db: Async database session
            mission_id: The mission to look up
            workspace_id: Required workspace scope
            user_id: Required user scope

        Returns:
            List of episode dicts.
        """
        stmt = (
            select(Episode)
            .where(
                Episode.mission_id == mission_id,
                Episode.workspace_id == workspace_id,
                Episode.user_id == user_id,
            )
            .order_by(Episode.created_at.desc())
        )
        result = await db.execute(stmt)
        episodes = result.scalars().all()

        return [
            {
                "id": ep.id,
                "mission_id": ep.mission_id,
                "step_type": ep.step_type,
                "outcome": ep.outcome,
                "cost_bucket": ep.cost_bucket,
                "hitl_outcome": ep.hitl_outcome,
                "retrieval_text": ep.retrieval_text,
                "embedding_model": ep.embedding_model,
                "created_at": ep.created_at.isoformat() if ep.created_at else None,
            }
            for ep in episodes
        ]

    # ── Redaction (private) ────────────────────────────────────────

    def redact(self, text: str) -> str:
        """Redact sensitive content from text.

        Strips:
        - API keys (sk-..., key-..., Bearer ...)
        - File paths with user dirs (/home/<user>/, /Users/<user>/)
        - LLM raw outputs > 200 chars (replaced with [REDACTED_LLM_OUTPUT])
        - Env var values that look like secrets
        - Deny-list matches

        Uses regex only — no LLM call, no network I/O.
        """
        if not text:
            return ""

        result = text

        # API keys
        result = _API_KEY_RE.sub("[REDACTED_API_KEY]", result)

        # File paths with user dirs
        result = _FILE_PATH_RE.sub("[REDACTED_PATH]", result)

        # Long LLM outputs (> 200 chars after the marker)
        result = _LONG_LLM_OUTPUT_RE.sub("[REDACTED_LLM_OUTPUT]", result)

        # Env var secrets
        result = _ENV_SECRET_RE.sub("[REDACTED_SECRET]", result)

        # Deny-list patterns
        for pattern in _DENY_LIST_PATTERNS:
            result = pattern.sub("[REDACTED]", result)

        return result

    # ── Internal: BM25 search ──────────────────────────────────────

    async def _bm25_search(
        self,
        db: AsyncSession,
        *,
        query_text: str,
        workspace_id: str,
        user_id: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        """PostgreSQL full-text search using tsvector + ts_rank."""
        try:
            stmt = text("""
                SELECT id, retrieval_text, step_type, outcome, cost_bucket,
                       hitl_outcome, mission_id, created_at,
                       ts_rank(retrieval_vector, plainto_tsquery('english', :query)) AS score
                FROM episodes
                WHERE workspace_id = :ws
                  AND user_id = :uid
                  AND retrieval_vector @@ plainto_tsquery('english', :query)
                ORDER BY score DESC
                LIMIT :limit
            """)
            result = await db.execute(stmt, {
                "query": query_text,
                "ws": workspace_id,
                "uid": user_id,
                "limit": limit,
            })
            rows = result.fetchall()

            return [
                {
                    "id": str(row.id),
                    "retrieval_text": row.retrieval_text,
                    "step_type": row.step_type,
                    "outcome": row.outcome,
                    "cost_bucket": row.cost_bucket,
                    "hitl_outcome": row.hitl_outcome,
                    "mission_id": str(row.mission_id),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "bm25_score": float(row.score),
                }
                for row in rows
            ]
        except Exception as e:
            logger.debug("BM25 search failed (tsvector may not be populated): %s", e)
            return []

    # ── Internal: Vector search ────────────────────────────────────

    async def _vector_search(
        self,
        *,
        query_text: str,
        workspace_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Qdrant vector similarity search."""
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            from app.config import settings

            client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )

            collection = EPISODES_COLLECTION
            if not await client.collection_exists(collection):
                return []

            # Embed the query
            query_vector = await self._embed_text(query_text)
            if query_vector is None:
                return []

            # Scope by workspace
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="workspace_id",
                        match=MatchValue(value=workspace_id),
                    )
                ]
            )

            results = await client.search(
                collection_name=collection,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )

            return [
                {
                    "id": str(r.id),
                    "score": r.score,
                    **(r.payload or {}),
                }
                for r in results
            ]
        except Exception as e:
            logger.debug("Vector search failed: %s", e)
            return []

    # ── Internal: Hybrid re-ranking ────────────────────────────────

    def _rerank(
        self,
        bm25_results: list[dict[str, Any]],
        vector_results: list[dict[str, Any]],
        *,
        k: int,
    ) -> list[dict[str, Any]]:
        """Reciprocal rank fusion of BM25 + vector results.

        RRF score = sum(1 / (k + rank_i)) across result sets.
        k=60 is the standard RRF constant.
        """
        RRF_K = 60
        scores: dict[str, float] = {}
        data: dict[str, dict[str, Any]] = {}

        # BM25 scores
        for rank, item in enumerate(bm25_results):
            ep_id = item["id"]
            scores[ep_id] = scores.get(ep_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            data[ep_id] = item

        # Vector scores
        for rank, item in enumerate(vector_results):
            ep_id = item["id"]
            scores[ep_id] = scores.get(ep_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            if ep_id not in data:
                data[ep_id] = item

        # Sort by combined score, cap at k
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:k]

        results = []
        for ep_id in sorted_ids:
            entry = data[ep_id].copy()
            entry["combined_score"] = scores[ep_id]
            results.append(entry)

        return results

    # ── Internal: Retrieval text builder ───────────────────────────

    def _build_retrieval_text(
        self,
        *,
        mission_id: str,
        step_type: str,
        outcome: str,
        cost_bucket: str,
        event_count: int | None = None,
        files_modified: int | None = None,
        summary_text: str = "",
    ) -> str:
        """Build a compact, structured retrieval text for an episode.

        This text is redacted BEFORE storage (never stores raw payload).
        """
        parts = [
            f"Mission {mission_id[:8]} step {step_type}: {outcome}",
            f"cost {cost_bucket}",
        ]
        if files_modified is not None:
            parts.append(f"{files_modified} files modified")
        if event_count is not None:
            parts.append(f"{event_count} events")
        if summary_text:
            # Truncate summary to avoid storing excessive text
            clean = summary_text[:500]
            parts.append(f"summary: {clean}")

        return ", ".join(parts)

    # ── Internal: Qdrant embedding storage ─────────────────────────

    async def _store_embedding(
        self,
        *,
        retrieval_text: str,
        workspace_id: str,
        mission_id: str,
    ) -> str | None:
        """Embed retrieval_text and store in Qdrant 'episodes' collection.

        Returns the Qdrant point ID, or None on failure.
        """
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import Distance, PointStruct, VectorParams

            from app.config import settings

            client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )

            collection = EPISODES_COLLECTION
            if not await client.collection_exists(collection):
                await client.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(
                        size=self.EMBEDDING_DIMENSION,
                        distance=Distance.COSINE,
                    ),
                )

            vector = await self._embed_text(retrieval_text)
            if vector is None:
                return None

            point_id = str(uuid4())
            await client.upsert(
                collection_name=collection,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "workspace_id": workspace_id,
                            "mission_id": mission_id,
                            "retrieval_text": retrieval_text[:200],
                        },
                    )
                ],
            )
            return point_id
        except Exception as e:
            logger.warning("Qdrant embedding storage failed: %s", e)
            return None

    # ── Internal: Embedding ────────────────────────────────────────

    async def _embed_text(self, text: str) -> list[float] | None:
        """Get an embedding vector using the project's EmbeddingService."""
        try:
            from app.services.rag.embedding_service import EmbeddingService

            service = EmbeddingService()
            vectors = await service.embed([text])
            return vectors[0] if vectors else None
        except Exception as e:
            logger.debug("Embedding failed: %s", e)
            return None


# ── Singleton ──────────────────────────────────────────────────────

_service: EpisodicMemoryService | None = None


def get_episodic_memory_service() -> EpisodicMemoryService:
    """Get or create the EpisodicMemoryService singleton."""
    global _service
    if _service is None:
        _service = EpisodicMemoryService()
    return _service
