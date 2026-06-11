"""ToolDiscoveryService — semantic tool discovery via Qdrant vector search.

Indexes all tools from the ToolRegistry into a dedicated Qdrant collection
and provides semantic search and task planning capabilities to the orchestrator.

Uses sentence-transformers (all-MiniLM-L6-v2, 384-dim) for embedding —
already available in the project's requirements.txt, no extra deps needed.
"""

import contextlib
import logging
import uuid
from dataclasses import dataclass, field

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings

logger = logging.getLogger(__name__)

TOOLS_COLLECTION = "workflows_tools"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


# ------------------------------------------------------------------
# Data types
# ------------------------------------------------------------------


@dataclass
class ToolResult:
    """A tool matched by semantic search with a relevance score.

    ``tool`` is a ``BaseTool`` from ``app.tools.base`` — the same registry
    the orchestrator uses for capability execution.
    """

    tool: object  # app.tools.base.BaseTool (lazy import to avoid circular deps)
    score: float = 0.0
    match_reasons: list[str] = field(default_factory=list)


@dataclass
class ToolPlan:
    """A ranked plan of recommended tools for a task."""

    recommended_tools: list[ToolResult] = field(default_factory=list)
    confidence: float = 0.0
    task_summary: str = ""


# ------------------------------------------------------------------
# Service
# ------------------------------------------------------------------


class ToolDiscoveryService:
    """Semantic tool discovery backed by Qdrant vector search.

    On initialize():
    1. Deletes any stale ``workflows_tools`` collection (to fix incompatible
       vector params from prior FastEmbed-based runs).
    2. Creates a fresh collection with explicit 384-dim COSINE vectors.
    3. Reads every tool from the ToolRegistry.
    4. Encodes tool descriptions via sentence-transformers and upserts
       them into Qdrant.

    search() and plan_for_task() encode the query with the same embedding
    model and run a vector similarity search.

    NOTE: search/plan_for_task are synchronous and will briefly block the
    event loop (~20-100ms for embedding + Qdrant round-trip).  If this
    becomes a bottleneck, wrap calls in asyncio.to_thread().
    """

    _embedding_model = None  # class-level cache — lazy loaded once
    UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace

    def __init__(self) -> None:
        self._qdrant_url: str = settings.QDRANT_URL
        self._collection_name: str = TOOLS_COLLECTION
        self._client: QdrantClient | None = None
        self._initialized: bool = False
        self._indexed_count: int = 0

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self._qdrant_url, timeout=15)
            logger.info("ToolDiscoveryService connected to Qdrant at %s", self._qdrant_url)
        return self._client

    def _collection_exists(self) -> bool:
        try:
            collections = self.client.get_collections().collections
            return any(c.name == self._collection_name for c in collections)
        except Exception:
            return False

    @classmethod
    def _get_embedding_model(cls):
        """Lazy-load the sentence-transformers model once per process."""
        if cls._embedding_model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model '%s' ...", EMBEDDING_MODEL_NAME)
            cls._embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info("Embedding model loaded")
        return cls._embedding_model

    # ------------------------------------------------------------------
    # Initialization & indexing
    # ------------------------------------------------------------------

    def initialize(self) -> int:
        """Create the tools collection (if needed) and index all registered tools.

        Returns the number of tools indexed.
        Safe to call multiple times — skips re-indexing when already done.
        """
        if self._initialized:
            logger.debug(
                "ToolDiscoveryService already initialized (%d tools)",
                self._indexed_count,
            )
            return self._indexed_count

        try:
            self._ensure_collection()
            self._indexed_count = self._index_all_tools()
            self._initialized = True
            logger.info(
                "ToolDiscoveryService initialized: %d tools indexed in '%s'",
                self._indexed_count,
                self._collection_name,
            )
        except Exception as exc:
            logger.warning(
                "ToolDiscoveryService initialization failed (will retry on next search): %s",
                exc,
            )
            # Don't set _initialized — allow retry on next call

        return self._indexed_count

    def _ensure_collection(self) -> None:
        """Ensure a compatible collection exists.

        Only deletes+recreates when the existing collection has incompatible
        vector params (e.g. leftover from a prior FastEmbed-based setup).
        In the common case (correct params already), we keep the collection
        and rely on upsert to refresh points — avoiding race conditions
        between workers.
        """
        if not self._collection_exists():
            self.client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                "Created Qdrant collection '%s' (dim=%d, distance=COSINE)",
                self._collection_name,
                EMBEDDING_DIM,
            )
            return

        # Collection exists — check params
        try:
            info = self.client.get_collection(self._collection_name)
            config = info.config.params.vectors
            needs_recreate = getattr(config, "size", None) != EMBEDDING_DIM or not isinstance(
                getattr(config, "distance", None), Distance
            )
        except Exception:
            needs_recreate = True

        if needs_recreate:
            logger.info(
                "Recreating collection '%s' (incompatible vector params)",
                self._collection_name,
            )
            try:
                self.client.delete_collection(self._collection_name)
            except Exception as exc:
                logger.warning("Failed to delete stale collection: %s", exc)

            self.client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Recreated Qdrant collection '%s'", self._collection_name)

    def _index_all_tools(self) -> int:
        """Read every tool from the ToolRegistry, encode, and upsert into Qdrant.

        Reads from ``app.tools.base.ToolRegistry`` — the same singleton
        used by the orchestrator, so every indexed tool is executable.
        """
        from app.tools.base import get_tool_registry

        registry = get_tool_registry()
        tools = registry.list_all()
        if not tools:
            logger.info("No tools in registry to index")
            return 0

        model = self._get_embedding_model()

        documents = []
        ids_list = []
        payloads = []
        for tool in tools:
            search_text = self._build_search_text(tool)
            documents.append(search_text)
            ids_list.append(tool.tool_id)
            payloads.append(
                {
                    "tool_id": tool.tool_id,
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category,
                    "tier": getattr(tool, "tier", 1),
                    "tags": tool.tags,
                    "source_service": getattr(tool, "source_service", ""),
                }
            )

        # Generate embeddings via sentence-transformers
        logger.info("Encoding %d tool documents ...", len(documents))
        vectors = model.encode(documents, normalize_embeddings=True)

        # Upsert points with explicit vectors.
        # Qdrant requires UUID or unsigned-integer point IDs —
        # use uuid5 to deterministically map string tool_ids to UUIDs.
        points = [
            PointStruct(
                id=str(uuid.uuid5(self.UUID_NAMESPACE, tool_id)),
                vector=vec.tolist(),
                payload=payload,
            )
            for tool_id, vec, payload in zip(ids_list, vectors, payloads, strict=False)
        ]
        self.client.upsert(
            collection_name=self._collection_name,
            points=points,
            wait=True,
        )

        logger.info("Indexed %d tools into Qdrant", len(documents))
        return len(documents)

    def reindex(self) -> int:
        """Force re-index all tools (clears and rebuilds the collection).

        NOTE: Between delete and recreate, concurrent searches will return
        empty.  This is a manual/admin operation, not called during normal
        operation.
        """
        try:
            self.client.delete_collection(self._collection_name)
            logger.info("Deleted collection '%s' for reindex", self._collection_name)
        except Exception:
            logger.debug("reindex_delete_collection_failed", exc_info=True)
        self._initialized = False
        self._indexed_count = 0
        return self.initialize()

    async def reindex_from_db(self, session) -> dict:
        """Rebuild the Qdrant index from Postgres tools_catalog + capabilities_catalog.

        Phase 2.5 — reads directly from DB rather than the in-memory registry,
        so the index reflects the canonical DB state even if hydration hasn't
        run yet.

        Returns a dict with counts: ``{tools_indexed, capabilities_indexed, total}``.
        """
        from sqlalchemy import select

        from app.models.capability_catalog_models import Capability as CapModel
        from app.models.tool_catalog_models import Tool as ToolModel

        # 1. Load tools from DB
        tool_result = await session.execute(select(ToolModel).where(ToolModel.enabled.is_(True)))
        db_tools = tool_result.scalars().all()

        # 2. Load capabilities from DB
        cap_result = await session.execute(select(CapModel).where(CapModel.enabled.is_(True)))
        db_caps = cap_result.scalars().all()

        # 3. Build documents for embedding
        documents = []
        ids_list = []
        payloads = []

        for tool_row in db_tools:
            search_text = self._build_search_text_from_row(
                name=tool_row.name,
                description=tool_row.description or "",
                tags=tool_row.tags or [],
                category=tool_row.category or "general",
            )
            documents.append(search_text)
            ids_list.append(f"tool:{tool_row.slug}")
            payloads.append(
                {
                    "tool_id": tool_row.slug,
                    "name": tool_row.name,
                    "description": tool_row.description or "",
                    "category": tool_row.category or "general",
                    "tags": tool_row.tags or [],
                    "source": "tools_catalog",
                    "handler_ref": tool_row.handler_ref or "",
                }
            )

        for cap_row in db_caps:
            search_text = self._build_search_text_from_row(
                name=cap_row.name,
                description=cap_row.description or "",
                tags=[],
                category=cap_row.category or "general",
            )
            documents.append(search_text)
            ids_list.append(f"cap:{cap_row.slug}")
            payloads.append(
                {
                    "capability_id": cap_row.slug,
                    "name": cap_row.name,
                    "description": cap_row.description or "",
                    "category": cap_row.category or "general",
                    "source": "capabilities_catalog",
                    "handler_ref": cap_row.handler_ref or "",
                }
            )

        if not documents:
            logger.info("reindex_from_db: no tools or capabilities to index")
            return {"tools_indexed": 0, "capabilities_indexed": 0, "total": 0}

        # 4. Recreate collection and upsert
        with contextlib.suppress(Exception):
            self.client.delete_collection(self._collection_name)
        self._ensure_collection()

        model = self._get_embedding_model()
        logger.info("Encoding %d documents for reindex ...", len(documents))
        vectors = model.encode(documents, normalize_embeddings=True)

        points = [
            PointStruct(
                id=str(uuid.uuid5(self.UUID_NAMESPACE, item_id)),
                vector=vec.tolist(),
                payload=payload,
            )
            for item_id, vec, payload in zip(ids_list, vectors, payloads, strict=False)
        ]
        self.client.upsert(
            collection_name=self._collection_name,
            points=points,
            wait=True,
        )

        self._initialized = True
        self._indexed_count = len(documents)

        result = {
            "tools_indexed": len(db_tools),
            "capabilities_indexed": len(db_caps),
            "total": len(documents),
        }
        logger.info("reindex_from_db complete: %s", result)
        return result

    @staticmethod
    def _build_search_text_from_row(name: str, description: str, tags: list, category: str) -> str:
        """Build a rich text blob for embedding from DB row fields."""
        parts = [name, description]
        if tags:
            parts.append("Tags: " + ", ".join(str(t) for t in tags))
        parts.append(f"Category: {category}")
        return " | ".join(filter(None, parts))

    # ------------------------------------------------------------------
    # Search helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_search_text(tool) -> str:
        """Build a rich text blob for embedding."""
        return ToolDiscoveryService._build_search_text_from_row(
            name=tool.name,
            description=tool.description,
            tags=tool.tags,
            category=tool.category,
        )

    # ------------------------------------------------------------------
    # Public API (called by orchestrator)
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
        tier_filter: list[int] | None = None,
        category_filter: list[str] | None = None,
    ) -> list[ToolResult]:
        """Semantic search for tools matching the natural-language *query*.

        Encodes the query with sentence-transformers and runs a vector
        similarity search against Qdrant.

        Returns ranked ``ToolResult`` objects with hydrated tool instances.
        Fallback: returns empty list on any error.
        """
        if not self._initialized:
            logger.debug("ToolDiscoveryService.search skipped (not initialized)")
            return []

        if not query or not query.strip():
            return []

        try:
            from app.tools.base import get_tool_registry

            registry = get_tool_registry()
            model = self._get_embedding_model()

            # Encode query and search with explicit vector
            query_vector = model.encode([query], normalize_embeddings=True)[0].tolist()

            hits = self.client.search(
                collection_name=self._collection_name,
                query_vector=query_vector,
                limit=top_k * 2,  # extra for post-filtering
            )

            results: list[ToolResult] = []
            for hit in hits:
                payload = hit.payload or {}
                tool_id = payload.get("tool_id", "")
                tool = registry.get(tool_id)
                if tool is None:
                    continue

                # Optional post-filters
                if tier_filter and getattr(tool, "tier", 1) not in tier_filter:
                    continue
                if category_filter and tool.category not in category_filter:
                    continue

                score = hit.score or 0.0
                reasons = self._build_match_reasons(tool, query)
                results.append(ToolResult(tool=tool, score=score, match_reasons=reasons))

                if len(results) >= top_k:
                    break

            logger.debug("Tool discovery search for '%s' -> %d results", query[:50], len(results))
            return results

        except Exception as exc:
            logger.warning("Tool discovery search failed (falling back): %s", exc)
            return []

    def plan_for_task(self, task_description: str, max_tools: int = 10) -> ToolPlan | None:
        """Build a ranked tool plan for a natural-language task description.

        Uses semantic search to find relevant tools.  Confidence is estimated
        from the top result's score (simplified — calibrate with real data).
        """
        if not self._initialized:
            logger.debug("ToolDiscoveryService.plan_for_task skipped (not initialized)")
            return None

        if not task_description or not task_description.strip():
            return None

        try:
            results = self.search(task_description, top_k=max_tools)

            if not results:
                return None

            # Simplified confidence: top score is the primary signal
            confidence = round(min(max(results[0].score, 0.0), 1.0), 3)

            # Build a short summary
            tool_names = [r.tool.name for r in results[:3]]  # type: ignore[attr-defined]
            summary = f"Plan for: {task_description[:80]}. Top tools: {', '.join(tool_names)}"

            return ToolPlan(
                recommended_tools=results,
                confidence=confidence,
                task_summary=summary,
            )

        except Exception as exc:
            logger.warning("Tool discovery plan_for_task failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Match reasons
    # ------------------------------------------------------------------

    @staticmethod
    def _build_match_reasons(tool, query: str) -> list[str]:
        """Build human-readable reasons why a tool matched the query."""
        reasons: list[str] = []
        q = query.lower()

        if q in tool.name.lower():
            reasons.append("Tool name matches query")
        if any(word in tool.description.lower() for word in q.split() if len(word) > 3):
            reasons.append("Description keyword match")
        if any(q in tag.lower() or tag.lower() in q for tag in tool.tags):
            reasons.append("Tag match")
        if q in tool.category.lower():
            reasons.append("Category match")

        if not reasons:
            reasons.append("Semantic similarity match")
        return reasons

    # ------------------------------------------------------------------
    # Health & introspection
    # ------------------------------------------------------------------

    def health(self) -> dict:
        """Return health status for monitoring."""
        try:
            exists = self._collection_exists()
            return {
                "initialized": self._initialized,
                "url": self._qdrant_url,
                "collection": self._collection_name,
                "collection_exists": exists,
                "tools_indexed": self._indexed_count,
            }
        except Exception as exc:
            return {
                "initialized": self._initialized,
                "url": self._qdrant_url,
                "collection": self._collection_name,
                "error": str(exc),
            }


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_discovery_service: ToolDiscoveryService | None = None


def get_discovery_service() -> ToolDiscoveryService:
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = ToolDiscoveryService()
    return _discovery_service
