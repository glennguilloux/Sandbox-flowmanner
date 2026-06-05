"""
Agent Registry Service — capability-aware agent discovery and matching.

Uses Qdrant for semantic search over agent capability embeddings,
falling back to PostgreSQL text search when Qdrant is unavailable.
"""

import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentCapability

logger = logging.getLogger(__name__)

QDRANT_COLLECTION = "agent_capabilities"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


class AgentRegistryService:
    """Register, discover, and match agents by capability profiles."""

    def __init__(self) -> None:
        self._qdrant_client = None
        self._embedding_model = None
        self._qdrant_available: bool | None = None

    # ------------------------------------------------------------------
    # Lazy resource loaders
    # ------------------------------------------------------------------

    def _get_qdrant(self):
        if self._qdrant_client is not None:
            return self._qdrant_client
        try:
            from qdrant_client import QdrantClient

            from app.config import settings

            client = QdrantClient(url=settings.QDRANT_URL, timeout=10)
            client.get_collections()
            self._qdrant_client = client
            self._qdrant_available = True
            logger.info("AgentRegistry connected to Qdrant at %s", settings.QDRANT_URL)
            return self._qdrant_client
        except Exception as e:
            logger.warning(
                "AgentRegistry: Qdrant unavailable (%s), falling back to PostgreSQL", e
            )
            self._qdrant_available = False
            return None

    def _get_embedding_model(self):
        if self._embedding_model is not None:
            return self._embedding_model
        try:
            from sentence_transformers import SentenceTransformer

            self._embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info(
                "AgentRegistry loaded embedding model: %s", EMBEDDING_MODEL_NAME
            )
            return self._embedding_model
        except Exception as e:
            logger.warning("AgentRegistry: embedding model unavailable (%s)", e)
            return None

    def _ensure_collection(self) -> None:
        client = self._get_qdrant()
        if client is None:
            return
        try:
            from qdrant_client.models import Distance, VectorParams

            collections = [c.name for c in client.get_collections().collections]
            if QDRANT_COLLECTION not in collections:
                client.create_collection(
                    collection_name=QDRANT_COLLECTION,
                    vectors_config=VectorParams(
                        size=EMBEDDING_DIM, distance=Distance.COSINE
                    ),
                )
                logger.info("Created Qdrant collection: %s", QDRANT_COLLECTION)
        except Exception as e:
            logger.warning("Failed to ensure Qdrant collection: %s", e)

    def _embed(self, text: str) -> list[float] | None:
        model = self._get_embedding_model()
        if model is None:
            return None
        try:
            return model.encode(text).tolist()
        except Exception as e:
            logger.warning("Embedding failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    async def register(
        self,
        db: AsyncSession,
        agent_id: str,
        name: str,
        description: str,
        task_types: list[str] | None = None,
        tools: list[str] | None = None,
        confidence_score: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> AgentCapability:
        """Register or update an agent's capability profile."""
        # Check if capability already exists for this agent
        result = await db.execute(
            select(AgentCapability).where(AgentCapability.agent_id == agent_id)
        )
        cap = result.scalar_one_or_none()

        # Build embedding text from name + description + task_types
        embed_text = f"{name}: {description}"
        if task_types:
            embed_text += f" Tasks: {', '.join(task_types)}"

        # Store embedding in Qdrant (delete old point first if re-registering)
        embedding_id = None
        embedding = self._embed(embed_text)
        if embedding:
            self._ensure_collection()
            client = self._get_qdrant()
            if client:
                try:
                    from qdrant_client.models import PointStruct

                    # Clean up old embedding
                    if cap and cap.embedding_id:
                        try:
                            client.delete(
                                collection_name=QDRANT_COLLECTION,
                                points_selector=[cap.embedding_id],
                            )
                        except Exception:
                            logger.debug(
                                "qdrant_old_point_delete_failed", exc_info=True
                            )

                    embedding_id = str(uuid4())
                    client.upsert(
                        collection_name=QDRANT_COLLECTION,
                        points=[
                            PointStruct(
                                id=embedding_id,
                                vector=embedding,
                                payload={
                                    "agent_id": agent_id,
                                    "name": name,
                                    "description": description,
                                    "task_types": task_types or [],
                                },
                            )
                        ],
                    )
                except Exception as e:
                    logger.warning("Failed to store embedding: %s", e)
                    embedding_id = None

        if cap:
            cap.name = name
            cap.description = description
            cap.task_types = task_types
            cap.tools = tools
            cap.confidence_score = confidence_score
            cap.embedding_id = embedding_id or cap.embedding_id
            cap.metadata_ = metadata
        else:
            cap = AgentCapability(
                agent_id=agent_id,
                name=name,
                description=description,
                task_types=task_types,
                tools=tools,
                confidence_score=confidence_score,
                embedding_id=embedding_id,
                metadata_=metadata,
            )
            db.add(cap)

        await db.flush()
        return cap

    # ------------------------------------------------------------------
    # Discover (semantic search)
    # ------------------------------------------------------------------

    async def discover(
        self,
        db: AsyncSession,
        task_description: str,
        task_type: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find agents matching a task description via semantic search."""
        # Try Qdrant first
        results = await self._discover_qdrant(task_description, task_type, limit)
        if results is not None:
            return results

        # Fallback: PostgreSQL text search
        return await self._discover_postgres(db, task_description, task_type, limit)

    async def _discover_qdrant(
        self,
        task_description: str,
        task_type: str | None,
        limit: int,
    ) -> list[dict[str, Any]] | None:
        embedding = self._embed(task_description)
        if embedding is None:
            return None

        client = self._get_qdrant()
        if client is None:
            return None

        try:
            from qdrant_client.models import FieldCondition, Filter, MatchAny

            query_filter = None
            if task_type:
                query_filter = Filter(
                    must=[
                        FieldCondition(
                            key="task_types",
                            match=MatchAny(any=[task_type]),
                        )
                    ]
                )

            results = client.search(
                collection_name=QDRANT_COLLECTION,
                query_vector=embedding,
                query_filter=query_filter,
                limit=limit,
            )

            return [
                {
                    "agent_id": hit.payload.get("agent_id"),
                    "name": hit.payload.get("name"),
                    "description": hit.payload.get("description"),
                    "task_types": hit.payload.get("task_types", []),
                    "score": round(hit.score, 4),
                }
                for hit in results
            ]
        except Exception as e:
            logger.warning("Qdrant search failed: %s", e)
            return None

    async def _discover_postgres(
        self,
        db: AsyncSession,
        task_description: str,
        task_type: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fallback: PostgreSQL text search on capabilities."""
        stmt = select(AgentCapability)

        if task_type:
            stmt = stmt.where(
                or_(
                    AgentCapability.task_types.contains([task_type]),
                    AgentCapability.description.ilike(f"%{task_type}%"),
                )
            )
        else:
            # Simple text match on description
            keywords = task_description.lower().split()[:5]
            conditions = [
                AgentCapability.description.ilike(f"%{kw}%")
                for kw in keywords
                if len(kw) > 3
            ]
            if conditions:
                stmt = stmt.where(or_(*conditions))

        stmt = stmt.order_by(AgentCapability.confidence_score.desc()).limit(limit)
        result = await db.execute(stmt)
        caps = result.scalars().all()

        return [
            {
                "agent_id": cap.agent_id,
                "name": cap.name,
                "description": cap.description,
                "task_types": cap.task_types or [],
                "score": cap.confidence_score,
            }
            for cap in caps
        ]

    # ------------------------------------------------------------------
    # Match (find single best agent)
    # ------------------------------------------------------------------

    async def match(
        self,
        db: AsyncSession,
        task_description: str,
        task_type: str | None = None,
        required_tools: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Find the single best agent for a task."""
        candidates = await self.discover(db, task_description, task_type, limit=10)

        if not candidates:
            return None

        # Filter by required tools if specified
        if required_tools:
            filtered = []
            for c in candidates:
                cap_result = await db.execute(
                    select(AgentCapability).where(
                        AgentCapability.agent_id == c["agent_id"]
                    )
                )
                cap = cap_result.scalar_one_or_none()
                if (
                    cap
                    and cap.tools
                    and all(tool in cap.tools for tool in required_tools)
                ):
                    filtered.append(c)
            if filtered:
                candidates = filtered

        return candidates[0] if candidates else None

    # ------------------------------------------------------------------
    # List / Get
    # ------------------------------------------------------------------

    async def list_capabilities(
        self,
        db: AsyncSession,
        task_type: str | None = None,
    ) -> list[AgentCapability]:
        """List all registered agent capabilities."""
        stmt = select(AgentCapability).order_by(AgentCapability.confidence_score.desc())
        if task_type:
            stmt = stmt.where(AgentCapability.task_types.contains([task_type]))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_capability(
        self, db: AsyncSession, agent_id: str
    ) -> AgentCapability | None:
        result = await db.execute(
            select(AgentCapability).where(AgentCapability.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def delete_capability(self, db: AsyncSession, agent_id: str) -> bool:
        result = await db.execute(
            select(AgentCapability).where(AgentCapability.agent_id == agent_id)
        )
        cap = result.scalar_one_or_none()
        if not cap:
            return False

        # Remove from Qdrant
        if cap.embedding_id:
            client = self._get_qdrant()
            if client:
                try:
                    client.delete(
                        collection_name=QDRANT_COLLECTION,
                        points_selector=[cap.embedding_id],
                    )
                except Exception as e:
                    logger.warning("Failed to delete Qdrant point: %s", e)

        await db.delete(cap)
        await db.flush()
        return True
