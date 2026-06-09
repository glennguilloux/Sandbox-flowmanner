"""
Memory Service - Core memory operations for agents

Provides persistent memory storage and retrieval for agents,
with support for different memory types and search.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Memory:
    """A single memory entry"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    content: str = ""
    memory_type: str = "episodic"  # episodic, semantic, procedural
    importance: float = 0.5
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "metadata": self.metadata,
        }


class MemoryService:
    """
    Core memory operations for agents.

    Features:
    - Store memories with type and importance
    - Recall memories by query, type, or time
    - Memory decay based on access patterns
    - Integration with RAG for semantic search
    """

    def __init__(self, storage_backend=None, embedding_service=None):
        self._storage = storage_backend
        self._embedding_service = embedding_service
        self._memories: dict[str, Memory] = {}  # In-memory cache
        self._agent_memories: dict[str, list[str]] = {}  # agent_id -> memory_ids

    async def store(
        self,
        agent_id: str,
        content: str,
        memory_type: str = "episodic",
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> Memory:
        """
        Store a new memory.

        Args:
            agent_id: The agent storing the memory
            content: The memory content
            memory_type: Type of memory (episodic, semantic, procedural)
            importance: Importance score (0-1)
            metadata: Additional metadata

        Returns:
            The created Memory object
        """
        memory = Memory(
            agent_id=agent_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            metadata=metadata or {},
        )

        # Generate embedding if service available
        if self._embedding_service:
            try:
                memory.embedding = await self._embedding_service.embed(content)
            except Exception as e:
                logger.warning('Failed to generate embedding: %s', e)

        # Store in cache
        self._memories[memory.id] = memory

        # Track by agent
        if agent_id not in self._agent_memories:
            self._agent_memories[agent_id] = []
        self._agent_memories[agent_id].append(memory.id)

        # Persist to storage if available
        if self._storage:
            await self._storage.save(memory.to_dict())

        logger.info('Stored memory %s for agent %s', memory.id, agent_id)
        return memory

    async def recall(
        self,
        agent_id: str,
        query: str | None = None,
        memory_type: str | None = None,
        limit: int = 10,
        min_importance: float = 0.0,
    ) -> list[Memory]:
        """
        Recall memories for an agent.

        Args:
            agent_id: The agent recalling memories
            query: Optional search query
            memory_type: Filter by memory type
            limit: Maximum number of memories to return
            min_importance: Minimum importance threshold

        Returns:
            List of matching Memory objects
        """
        # Get agent's memory IDs
        memory_ids = self._agent_memories.get(agent_id, [])

        # Get memories
        memories = [self._memories[mid] for mid in memory_ids if mid in self._memories]

        # Filter by type
        if memory_type:
            memories = [m for m in memories if m.memory_type == memory_type]

        # Filter by importance
        memories = [m for m in memories if m.importance >= min_importance]

        # Search by query if provided
        if query and self._embedding_service:
            memories = await self._semantic_search(memories, query)
        elif query:
            # Simple text search
            query_lower = query.lower()
            memories = [m for m in memories if query_lower in m.content.lower()]

        # Sort by importance and last accessed
        memories.sort(key=lambda m: (m.importance, m.last_accessed), reverse=True)

        # Update access info
        for memory in memories[:limit]:
            memory.last_accessed = datetime.now(UTC)
            memory.access_count += 1

        return memories[:limit]

    async def _semantic_search(
        self, memories: list[Memory], query: str
    ) -> list[Memory]:
        """Perform semantic search using embeddings"""
        if not self._embedding_service:
            return memories

        try:
            query_embedding = await self._embedding_service.embed(query)

            # Calculate similarities
            scored_memories = []
            for memory in memories:
                if memory.embedding:
                    similarity = self._cosine_similarity(
                        query_embedding, memory.embedding
                    )
                    scored_memories.append((memory, similarity))
                else:
                    scored_memories.append((memory, 0.0))

            # Sort by similarity
            scored_memories.sort(key=lambda x: x[1], reverse=True)
            return [m for m, s in scored_memories]
        except Exception as e:
            logger.error('Semantic search failed: %s', e)
            return memories

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        if len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    async def forget(self, memory_id: str) -> bool:
        """Delete a memory"""
        if memory_id not in self._memories:
            return False

        memory = self._memories.pop(memory_id)

        # Remove from agent tracking
        if memory.agent_id in self._agent_memories:
            self._agent_memories[memory.agent_id] = [
                mid for mid in self._agent_memories[memory.agent_id] if mid != memory_id
            ]

        # Remove from storage
        if self._storage:
            await self._storage.delete(memory_id)

        logger.info('Forgot memory %s', memory_id)
        return True

    async def update_importance(self, memory_id: str, importance: float) -> bool:
        """Update the importance of a memory"""
        if memory_id not in self._memories:
            return False

        self._memories[memory_id].importance = importance
        return True

    async def consolidate(self, agent_id: str) -> int:
        """
        Consolidate memories for an agent.

        Removes low-importance, unaccessed memories.
        Returns number of memories removed.
        """
        memory_ids = self._agent_memories.get(agent_id, [])
        to_remove = []

        for mid in memory_ids:
            if mid in self._memories:
                memory = self._memories[mid]
                # Remove if low importance and not accessed recently
                if (
                    memory.importance < 0.3
                    and memory.access_count == 0
                    and (datetime.now(UTC) - memory.created_at).days > 7
                ):
                    to_remove.append(mid)

        for mid in to_remove:
            await self.forget(mid)

        logger.info('Consolidated %s memories for agent %s', len(to_remove), agent_id)
        return len(to_remove)

    def get_stats(self, agent_id: str | None = None) -> dict[str, Any]:
        """Get memory statistics"""
        if agent_id:
            memory_ids = self._agent_memories.get(agent_id, [])
            memories = [
                self._memories[mid] for mid in memory_ids if mid in self._memories
            ]
        else:
            memories = list(self._memories.values())

        return {
            "total_memories": len(memories),
            "by_type": {
                mtype: len([m for m in memories if m.memory_type == mtype])
                for mtype in ["episodic", "semantic", "procedural"]
            },
            "avg_importance": (
                sum(m.importance for m in memories) / len(memories) if memories else 0
            ),
            "total_access_count": sum(m.access_count for m in memories),
        }
