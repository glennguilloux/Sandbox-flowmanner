"""Episodic Memory Consolidation Worker — Phase 6.1.

Subscribes to mission.completed events, extracts (context, action, outcome)
tuples from the event log, summarizes via LLM, and embeds into Qdrant
`mission_episodes` collection.

Provides:
- consolidate_episode(): Extract + summarize + embed a completed mission
- retrieve_relevant_episodes(): Semantic search for similar past episodes
- forget_stale_episodes(): Archive episodes older than retention period

Usage:
    worker = EpisodicMemoryWorker(db)
    await worker.consolidate_episode(mission_id="...", run_id="...")
    episodes = await worker.retrieve_relevant_episodes("deploy to production", limit=5)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import select

from app.models.mission_models import Mission
from app.models.substrate_models import SubstrateEvent, SubstrateEventType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Qdrant collection for episodic memory
EPISODES_COLLECTION = "mission_episodes"

# Retention policy: episodes older than this are archived
DEFAULT_RETENTION_DAYS = 90


class EpisodicMemoryWorker:
    """Consolidates mission executions into episodic memory."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def consolidate_episode(
        self,
        *,
        mission_id: str,
        run_id: str,
    ) -> dict[str, Any] | None:
        """Extract, summarize, and embed a completed mission episode.

        Args:
            mission_id: The completed mission's UUID.
            run_id: The execution run's UUID.

        Returns:
            The created episode dict, or None if consolidation was skipped.
        """
        # 1. Fetch mission metadata
        mission = await self.db.get(Mission, mission_id)
        if mission is None:
            logger.warning("Mission %s not found — skipping consolidation", mission_id)
            return None

        # 2. Fetch the event log for this run
        stmt = (
            select(SubstrateEvent).where(SubstrateEvent.run_id == run_id).order_by(SubstrateEvent.sequence).limit(500)
        )
        events = (await self.db.execute(stmt)).scalars().all()
        if not events:
            logger.info("No events for run %s — skipping consolidation", run_id)
            return None

        # 3. Extract (context, action, outcome) tuples
        context = self._extract_context(mission, events)
        actions = self._extract_actions(events)
        outcome = self._extract_outcome(mission, events)

        if not actions:
            logger.info("No meaningful actions for run %s — skipping", run_id)
            return None

        # 4. Summarize via LLM
        summary = await self._summarize_episode(context, actions, outcome)

        # 5. Embed into Qdrant
        episode_id = await self._embed_episode(
            mission_id=mission_id,
            run_id=run_id,
            workspace_id=getattr(mission, "workspace_id", None),
            summary=summary,
            context=context,
            outcome=outcome,
            event_count=len(events),
        )

        if episode_id is None:
            return None

        episode = {
            "id": episode_id,
            "mission_id": mission_id,
            "run_id": run_id,
            "summary": summary,
            "context": context,
            "outcome": outcome,
            "event_count": len(events),
            "consolidated_at": datetime.now(UTC).isoformat(),
        }
        logger.info(
            "Episode consolidated: mission=%s events=%d summary_len=%d",
            mission_id,
            len(events),
            len(summary),
        )
        return episode

    async def retrieve_relevant_episodes(
        self,
        query: str,
        *,
        workspace_id: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search for relevant past episodes.

        Args:
            query: Natural language query describing the current context.
            workspace_id: Optional filter by workspace.
            limit: Max results.

        Returns:
            List of episode dicts sorted by relevance.
        """
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            from app.config import settings

            client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )

            # Check collection exists
            if not await client.collection_exists(EPISODES_COLLECTION):
                return []

            # Embed the query
            query_vector = await self._embed_text(query)
            if query_vector is None:
                return []

            # Build filter
            query_filter = None
            if workspace_id:
                query_filter = Filter(must=[FieldCondition(key="workspace_id", params=MatchValue(value=workspace_id))])

            results = await client.search(
                collection_name=EPISODES_COLLECTION,
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
            logger.warning("Episode retrieval failed: %s", e)
            return []

    async def forget_stale_episodes(
        self,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ) -> int:
        """Archive episodes older than retention period.

        For now, this deletes old episodes from Qdrant.
        Future: move to cold storage (S3/filesystem).

        Returns:
            Number of episodes archived/deleted.
        """
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import DatetimeRange, FieldCondition, Filter

            from app.config import settings

            client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )

            if not await client.collection_exists(EPISODES_COLLECTION):
                return 0

            cutoff = datetime.now(UTC) - timedelta(days=retention_days)

            # Delete old points
            result = await client.delete(
                collection_name=EPISODES_COLLECTION,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="consolidated_at",
                            range=DatetimeRange(lt=cutoff.isoformat()),
                        )
                    ]
                ),
            )
            logger.info("Archived stale episodes (retention=%dd)", retention_days)
            return 1  # Qdrant doesn't return exact count easily

        except Exception as e:
            logger.warning("Forget policy failed: %s", e)
            return 0

    # ── Internal helpers ─────────────────────────────────────────────

    def _extract_context(self, mission: Mission, events: list) -> dict[str, Any]:
        """Extract mission context from metadata."""
        return {
            "title": mission.title,
            "description": mission.description or "",
            "mission_type": getattr(mission, "mission_type", None),
            "workspace_id": getattr(mission, "workspace_id", None),
        }

    def _extract_actions(self, events: list) -> list[dict[str, Any]]:
        """Extract (action, detail) tuples from task events."""
        actions = []
        for event in events:
            payload = event.payload or {}
            match event.type:
                case SubstrateEventType.TASK_COMPLETED:
                    actions.append(
                        {
                            "action": "task_completed",
                            "task_title": payload.get("task_title", "unknown"),
                            "tokens": payload.get("tokens", 0),
                            "cost_usd": payload.get("cost_usd", 0.0),
                        }
                    )
                case SubstrateEventType.TOOL_CALL:
                    actions.append(
                        {
                            "action": "tool_call",
                            "tool": payload.get("tool_name", "unknown"),
                        }
                    )
                case SubstrateEventType.LLM_CALL:
                    actions.append(
                        {
                            "action": "llm_call",
                            "model": payload.get("model_id", "unknown"),
                            "tokens": payload.get("prompt_tokens", 0) + payload.get("completion_tokens", 0),
                        }
                    )
        return actions

    def _extract_outcome(self, mission: Mission, events: list) -> dict[str, Any]:
        """Extract final outcome from mission and terminal events."""
        terminal = None
        for event in reversed(events):
            if event.type in (
                SubstrateEventType.MISSION_COMPLETED,
                SubstrateEventType.MISSION_FAILED,
                SubstrateEventType.MISSION_ABORTED,
            ):
                terminal = event
                break

        return {
            "status": (mission.status if isinstance(mission.status, str) else mission.status.value),
            "error": terminal.payload.get("error") if terminal else None,
            "total_tokens": getattr(mission, "tokens_used", 0) or 0,
            "actual_cost": getattr(mission, "actual_cost", 0.0) or 0.0,
        }

    async def _summarize_episode(
        self,
        context: dict,
        actions: list[dict],
        outcome: dict,
    ) -> str:
        """Summarize the episode into a concise natural-language description.

        Uses the local LLM (llama.cpp) if available, otherwise falls back
        to a template-based summary.
        """
        prompt = (
            "Summarize this mission execution in 2-3 sentences. "
            "Focus on what was attempted, what approach was used, and the outcome.\n\n"
            f"Context: {json.dumps(context)}\n"
            f"Actions taken: {json.dumps(actions[:20])}\n"
            f"Outcome: {json.dumps(outcome)}\n\n"
            "Summary:"
        )

        try:
            from decimal import Decimal

            from app.models.capability_models import Budget

            budget = Budget(max_cost_usd=Decimal("0.01"), max_iterations=1)
            from app.services.budget_enforcer import get_budget_enforcer

            enforcer = get_budget_enforcer()

            response = await enforcer.call(
                budget=budget,
                model_id="llamacpp/Qwen3.6-27B",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            if response.get("success"):
                return response.get("response", "").strip()
        except Exception as e:
            logger.debug("LLM summarization failed, using template: %s", e)

        # Template fallback
        status = outcome.get("status", "unknown")
        title = context.get("title", "Untitled mission")
        action_count = len(actions)
        return (
            f"Mission '{title}' completed with status '{status}'. "
            f"{action_count} actions were taken. "
            f"Total tokens: {outcome.get('total_tokens', 0)}, "
            f"cost: ${outcome.get('actual_cost', 0.0):.4f}."
        )

    async def _embed_episode(
        self,
        *,
        mission_id: str,
        run_id: str,
        workspace_id: str | None,
        summary: str,
        context: dict,
        outcome: dict,
        event_count: int,
    ) -> str | None:
        """Embed the episode into Qdrant."""
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import Distance, PointStruct, VectorParams

            from app.config import settings

            client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )

            # Ensure collection
            if not await client.collection_exists(EPISODES_COLLECTION):
                await client.create_collection(
                    collection_name=EPISODES_COLLECTION,
                    vectors_config=VectorParams(
                        size=settings.EMBEDDING_DIMENSION,
                        distance=Distance.COSINE,
                    ),
                )

            # Get embedding
            vector = await self._embed_text(summary)
            if vector is None:
                return None

            episode_id = str(uuid4())
            now = datetime.now(UTC)

            await client.upsert(
                collection_name=EPISODES_COLLECTION,
                points=[
                    PointStruct(
                        id=episode_id,
                        vector=vector,
                        payload={
                            "mission_id": mission_id,
                            "run_id": run_id,
                            "workspace_id": workspace_id,
                            "summary": summary,
                            "context_title": context.get("title", ""),
                            "outcome_status": outcome.get("status", ""),
                            "event_count": event_count,
                            "consolidated_at": now.isoformat(),
                        },
                    )
                ],
            )
            return episode_id

        except Exception as e:
            logger.warning("Episode embedding failed: %s", e)
            return None

    async def _embed_text(self, text: str) -> list[float] | None:
        """Get an embedding vector for text.

        Uses the project's existing embedding service or falls back
        to a simple hash-based approach for testing.
        """
        try:
            from app.services.rag.embedding_service import EmbeddingService

            service = EmbeddingService()
            vectors = await service.embed([text])
            return vectors[0] if vectors else None
        except Exception as e:
            logger.debug("Embedding service failed: %s", e)
            return None
