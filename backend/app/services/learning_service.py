"""
Learning Service — Provides historical learning context for planner/orchestrator
decisions and records mission execution outcomes for future learning.

Uses Qdrant for semantic similarity search on task descriptions and PostgreSQL
for structured queries on mission history. Falls back to PostgreSQL text search
when Qdrant is unavailable.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Qdrant collection for mission task embeddings
MISSION_EMBEDDINGS_COLLECTION = "mission_embeddings"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


class LearningService:
    """Historical learning context provider backed by Qdrant + PostgreSQL."""

    def __init__(self) -> None:
        self._qdrant_client = None
        self._embedding_model = None
        self._qdrant_available: bool | None = None  # tri-state: None = unchecked

    # ------------------------------------------------------------------
    # Lazy resource loaders
    # ------------------------------------------------------------------

    def _get_qdrant(self):
        """Lazy-init Qdrant client. Returns None if unreachable."""
        if self._qdrant_client is not None:
            return self._qdrant_client
        try:
            from qdrant_client import QdrantClient

            from app.config import settings

            client = QdrantClient(url=settings.QDRANT_URL, timeout=10)
            # Verify connectivity
            client.get_collections()
            self._qdrant_client = client
            self._qdrant_available = True
            logger.info("LearningService connected to Qdrant at %s", settings.QDRANT_URL)
            return self._qdrant_client
        except Exception as e:
            logger.warning("LearningService: Qdrant unavailable (%s), falling back to PostgreSQL", e)
            self._qdrant_available = False
            return None

    def _get_embedding_model(self):
        """Lazy-load sentence-transformers model (class-level cache)."""
        if self._embedding_model is not None:
            return self._embedding_model
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("LearningService loading embedding model '%s'...", EMBEDDING_MODEL_NAME)
            self._embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info("LearningService embedding model loaded")
            return self._embedding_model
        except Exception as e:
            logger.warning("LearningService: embedding model unavailable (%s)", e)
            return None

    def _ensure_collection(self) -> bool:
        """Ensure the mission_embeddings collection exists in Qdrant."""
        client = self._get_qdrant()
        if client is None:
            return False
        try:
            from qdrant_client.models import Distance, VectorParams

            collections = client.get_collections().collections
            names = {c.name for c in collections}
            if MISSION_EMBEDDINGS_COLLECTION not in names:
                client.create_collection(
                    collection_name=MISSION_EMBEDDINGS_COLLECTION,
                    vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
                )
                logger.info("Created Qdrant collection '%s'", MISSION_EMBEDDINGS_COLLECTION)
            return True
        except Exception as e:
            logger.warning("LearningService: failed to ensure collection: %s", e)
            return False

    def _embed(self, text_content: str) -> list[float] | None:
        """Encode text into a vector. Returns None if model unavailable."""
        model = self._get_embedding_model()
        if model is None:
            return None
        try:
            return model.encode(text_content).tolist()
        except Exception as e:
            logger.warning("LearningService: embedding failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def inject_into_planner_context(
        self,
        task_description: str,
        mission_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Query similar past executions and return context for the planner.

        Returns a dict with keys the orchestrator expects:
        - has_historical_data: bool
        - context_summary: str
        - similar_tasks: list[dict]
        - success_patterns: list[str]
        - recommended_model: str | None
        Returns None on failure (orchestrator handles gracefully).
        """
        try:
            similar_tasks = await self.get_similar_tasks(task_description, limit=5)
            if not similar_tasks:
                return None

            # Build context summary from similar tasks
            success_count = sum(1 for t in similar_tasks if t.get("success_rate", 0) > 0.5)
            total = len(similar_tasks)
            avg_success = (
                sum(t.get("success_rate", 0) for t in similar_tasks) / total if total else 0
            )

            # Extract success patterns
            success_patterns: list[str] = []
            for task in similar_tasks:
                if task.get("success_rate", 0) >= 0.7:
                    desc = task.get("task_description", "")[:120]
                    rate = task.get("success_rate", 0)
                    success_patterns.append(f"{desc} (success rate: {rate:.0%})")

            # Recommend best model
            recommended_model = await self.get_best_model_for_task(task_description)

            # Build summary
            summary_parts = [
                f"Found {total} similar past missions ({success_count} with >50% success rate).",
            ]
            if recommended_model:
                summary_parts.append(f"Recommended model: {recommended_model}.")
            if success_patterns:
                summary_parts.append(
                    f"Top success pattern: {success_patterns[0]}"
                )

            return {
                "has_historical_data": True,
                "context_summary": " ".join(summary_parts),
                "similar_tasks": similar_tasks,
                "success_patterns": success_patterns,
                "recommended_model": recommended_model,
                "average_success_rate": round(avg_success, 3),
            }
        except Exception as e:
            logger.warning("LearningService.inject_into_planner_context failed: %s", e)
            return None

    async def record_execution(
        self,
        task_description: str,
        plan: dict,
        result: dict,
        success: bool,
        *,
        mission_id: str | None = None,
        user_id: int | None = None,
        model_used: str | None = None,
        tokens_used: int | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        """Persist mission execution for future learning.

        Stores in learning_feedback table + Qdrant embedding for similarity search.
        """
        try:
            # 1. Store structured record in learning_feedback
            await self._store_feedback(
                task_description=task_description,
                plan=plan,
                result=result,
                success=success,
                mission_id=mission_id,
                user_id=user_id,
                model_used=model_used,
                tokens_used=tokens_used,
                duration_seconds=duration_seconds,
            )

            # 2. Store embedding in Qdrant for similarity search
            await self._store_embedding(
                task_description=task_description,
                mission_id=mission_id,
                success=success,
                model_used=model_used,
                tokens_used=tokens_used,
                duration_seconds=duration_seconds,
            )

            logger.debug(
                "LearningService.record_execution: stored for mission %s (success=%s)",
                mission_id,
                success,
            )
        except Exception as e:
            logger.warning("LearningService.record_execution failed: %s", e)

    async def get_similar_tasks(
        self,
        task_description: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find similar past tasks using vector similarity.

        Falls back to PostgreSQL text search if Qdrant unavailable.
        Returns list of dicts with: task_description, success_rate, avg_duration, best_model, mission_id.
        """
        # Try Qdrant first
        qdrant_results = await self._search_qdrant(task_description, limit)
        if qdrant_results:
            return qdrant_results

        # Fallback to PostgreSQL text search
        return await self._search_postgres(task_description, limit)

    async def get_best_model_for_task(self, task_description: str) -> str | None:
        """Recommend best model based on historical success rates for similar tasks."""
        try:
            similar = await self.get_similar_tasks(task_description, limit=10)
            if not similar:
                return None

            # Aggregate success by model
            model_stats: dict[str, dict[str, Any]] = {}
            for task in similar:
                model = task.get("best_model")
                if not model:
                    continue
                if model not in model_stats:
                    model_stats[model] = {"success": 0, "total": 0}
                model_stats[model]["total"] += 1
                if task.get("success_rate", 0) > 0.5:
                    model_stats[model]["success"] += 1

            if not model_stats:
                return None

            # Pick model with highest success rate (with minimum sample size)
            best_model = None
            best_rate = -1.0
            for model, stats in model_stats.items():
                if stats["total"] < 1:
                    continue
                rate = stats["success"] / stats["total"]
                if rate > best_rate:
                    best_rate = rate
                    best_model = model

            return best_model
        except Exception as e:
            logger.warning("LearningService.get_best_model_for_task failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Private: PostgreSQL storage
    # ------------------------------------------------------------------

    async def _store_feedback(
        self,
        task_description: str,
        plan: dict,
        result: dict,
        success: bool,
        mission_id: str | None,
        user_id: int | None,
        model_used: str | None,
        tokens_used: int | None,
        duration_seconds: float | None,
    ) -> None:
        """Store execution record in learning_feedback table."""
        from app.database import AsyncSessionLocal
        from app.models.learning_models import LearningFeedbackDB

        async with AsyncSessionLocal() as db:
            try:
                feedback = LearningFeedbackDB(
                    feedback_type="mission_execution",
                    content={
                        "task_description": task_description,
                        "plan_summary": _summarize_plan(plan),
                        "result_summary": _summarize_result(result),
                        "success": success,
                        "model_used": model_used,
                        "tokens_used": tokens_used,
                        "duration_seconds": duration_seconds,
                    },
                    agent_id=str(user_id) if user_id else None,
                    mission_id=mission_id,
                )
                db.add(feedback)
                await db.commit()
            except Exception as e:
                logger.warning("Failed to store learning feedback: %s", e)
                await db.rollback()

    # ------------------------------------------------------------------
    # Private: Qdrant vector storage & search
    # ------------------------------------------------------------------

    async def _store_embedding(
        self,
        task_description: str,
        mission_id: str | None,
        success: bool,
        model_used: str | None,
        tokens_used: int | None,
        duration_seconds: float | None,
    ) -> None:
        """Store task description embedding in Qdrant."""
        if not self._ensure_collection():
            return

        vector = self._embed(task_description)
        if vector is None:
            return

        try:
            from qdrant_client.models import PointStruct

            point_id = str(uuid4())
            self._qdrant_client.upsert(
                collection_name=MISSION_EMBEDDINGS_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "task_description": task_description,
                            "mission_id": mission_id,
                            "success": success,
                            "model_used": model_used,
                            "tokens_used": tokens_used,
                            "duration_seconds": duration_seconds,
                            "recorded_at": datetime.now(UTC).isoformat(),
                        },
                    )
                ],
            )
        except Exception as e:
            logger.warning("LearningService: Qdrant upsert failed: %s", e)

    async def _search_qdrant(
        self,
        task_description: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Search Qdrant for similar task descriptions."""
        if not self._ensure_collection():
            return []

        vector = self._embed(task_description)
        if vector is None:
            return []

        try:
            # Use query_points (qdrant-client >=1.15) instead of deprecated search
            response = self._qdrant_client.query_points(
                collection_name=MISSION_EMBEDDINGS_COLLECTION,
                query=vector,
                limit=limit,
                score_threshold=0.3,
            )

            tasks: list[dict[str, Any]] = []
            for point in response.points:
                payload = point.payload or {}
                tasks.append({
                    "task_description": payload.get("task_description", ""),
                    "mission_id": payload.get("mission_id"),
                    "success_rate": 1.0 if payload.get("success") else 0.0,
                    "avg_duration": payload.get("duration_seconds"),
                    "best_model": payload.get("model_used"),
                    "similarity_score": point.score,
                })

            return tasks
        except Exception as e:
            logger.warning("LearningService: Qdrant search failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Private: PostgreSQL fallback search
    # ------------------------------------------------------------------

    async def _search_postgres(
        self,
        task_description: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fallback: search PostgreSQL for similar missions using text search."""
        from app.database import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as db:
                # Extract keywords from task description for matching
                keywords = _extract_keywords(task_description)
                if not keywords:
                    return []

                # Build OR conditions for keyword matching
                conditions = " OR ".join(
                    f"(title ILIKE :kw{i} OR description ILIKE :kw{i})"
                    for i in range(len(keywords))
                )
                params: dict[str, Any] = {f"kw{i}": f"%{kw}%" for i, kw in enumerate(keywords)}

                query = text(
                    f"SELECT id, title, description, mission_type, status, "
                    f"tokens_used, actual_cost, started_at, completed_at "
                    f"FROM missions "
                    f"WHERE ({conditions}) AND status IN ('completed', 'failed') "
                    f"ORDER BY created_at DESC "
                    f"LIMIT :limit"
                )
                params["limit"] = limit

                result = await db.execute(query, params)
                rows = result.fetchall()

                tasks: list[dict[str, Any]] = []
                for row in rows:
                    mission_id = str(row[0])
                    success = row[4] == "completed"

                    # Get model info from mission_runs via raw SQL (no ORM model exists)
                    model_used = await self._get_model_from_runs(db, mission_id)

                    # Calculate duration
                    duration = None
                    if row[7] and row[8]:  # started_at, completed_at
                        duration = (row[8] - row[7]).total_seconds()

                    tasks.append({
                        "task_description": f"{row[1] or ''} {row[2] or ''}".strip()[:200],
                        "mission_id": mission_id,
                        "success_rate": 1.0 if success else 0.0,
                        "avg_duration": duration,
                        "best_model": model_used,
                    })

                return tasks
        except Exception as e:
            logger.warning("LearningService: PostgreSQL fallback search failed: %s", e)
            return []

    async def _get_model_from_runs(self, db, mission_id: str) -> str | None:
        """Get the model_used from mission_runs for a given mission via raw SQL."""
        try:
            result = await db.execute(
                text(
                    "SELECT model_used FROM mission_runs "
                    "WHERE mission_id = :mid AND model_used IS NOT NULL "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"mid": mission_id},
            )
            row = result.scalar()
            return row
        except Exception:
            return None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _summarize_plan(plan: dict) -> dict:
    """Extract a lightweight summary from a plan dict."""
    if not plan:
        return {}
    tasks = plan.get("tasks", [])
    return {
        "task_count": len(tasks),
        "task_types": list({t.get("task_type", "unknown") for t in tasks}) if tasks else [],
    }


def _summarize_result(result: dict) -> dict:
    """Extract a lightweight summary from a result dict."""
    if not result:
        return {}
    summary = result.get("summary", {})
    return {
        "total_tasks": summary.get("total_tasks"),
        "completed": summary.get("completed"),
        "failed": summary.get("failed"),
    }


def _extract_keywords(task_description: str, max_keywords: int = 5) -> list[str]:
    """Extract meaningful keywords from a task description for text search."""
    import re

    # Remove common stop words and short tokens
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "out", "off", "over",
        "under", "again", "further", "then", "once", "and", "but", "or", "nor",
        "not", "so", "very", "just", "about", "up", "that", "this", "these",
        "those", "it", "its", "i", "me", "my", "we", "our", "you", "your",
        "he", "him", "his", "she", "her", "they", "them", "their", "which",
        "what", "who", "whom", "how", "when", "where", "why", "all", "each",
        "every", "both", "few", "more", "most", "other", "some", "such",
        "than", "too", "also", "only", "own", "same",
    }

    words = re.findall(r"[a-zA-Z]{3,}", task_description.lower())
    keywords = [w for w in words if w not in stop_words]
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique[:max_keywords]


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_learning_service: LearningService | None = None


def get_learning_service() -> LearningService | None:
    """Get or create the learning service singleton."""
    global _learning_service
    if _learning_service is None:
        _learning_service = LearningService()
    return _learning_service
